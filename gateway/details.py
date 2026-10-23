"""Construction details read off the sketch by a vision LLM (llama-swap, OpenAI-compatible API).

Flux follows the sketch's silhouette well but drops small things: buttons, ties, vents, pockets, embroidery.
Naming them in the prompt brings them back. The LLM looks at the sketch photos once per design and returns:
    garment  features of the whole garment, written into every view's prompt (e.g. "one-piece jumpsuit")
    front    details only visible from the front ("five-button placket", "two chest flap pockets")
    back     details only visible from the back ("centre back vent", "pointed collar visible at the neck")
The app shows them as chips the user can remove or add to before rendering. Any failure (LLM off, slow,
nonsense) just means no details: rendering never depends on the LLM.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from pathlib import Path

import httpx
from PIL import Image
from pydantic import BaseModel, Field, field_validator

from gateway.config import LlmSettings

log = logging.getLogger(__name__)

MAX_ITEMS = 8
MAX_ITEM_CHARS = 60
IMAGE_LONG_SIDE = 1024  # plenty to read a sketch; keeps the request small and the model fast

# Words that would fight the tapped choices (colour, fabric, scene) or describe the drawing, not the garment.
BANNED = re.compile(
    r"\b(colou?r|black|white|grey|gray|red|blue|green|yellow|pink|purple|brown|orange|beige|navy|"
    r"pencil|ink|sketch|drawing|drawn|paper|line art|outline|mannequin|model|person|background|text|label|"
    r"handwrit\w*|cotton|denim|silk|satin|linen|wool|leather|polyester)\b",
    re.IGNORECASE,
)


def _clean_item(text: str) -> str:
    text = re.sub(r"[{}<>\[\]\"`]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .,;:-").lower()
    return text[:MAX_ITEM_CHARS].strip()


def _clean_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    seen: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = _clean_item(item)
        if text and text not in seen:
            seen.append(text)
    return seen[:MAX_ITEMS]


class SketchDetails(BaseModel):
    """Details per view. Validation also guards details the user typed in the app."""

    garment: list[str] = Field(default_factory=list)
    front: list[str] = Field(default_factory=list)
    back: list[str] = Field(default_factory=list)
    side: list[str] = Field(default_factory=list)

    @field_validator("garment", "front", "back", "side", mode="before")
    @classmethod
    def _items(cls, value: object) -> list[str]:
        return _clean_list(value)

    def for_view(self, view: str) -> list[str]:
        own = {"front": self.front, "back": self.back, "side": self.side}.get(view, [])
        return [*self.garment, *(item for item in own if item not in self.garment)]

    @property
    def empty(self) -> bool:
        return not (self.garment or self.front or self.back or self.side)


class DetailsError(RuntimeError):
    pass


def _image_url(path: Path) -> str:
    image = Image.open(path).convert("RGB")
    image.thumbnail((IMAGE_LONG_SIDE, IMAGE_LONG_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def instructions(garment: str, views: list[str]) -> str:
    shown = " and ".join(f"the {v} view" for v in views)
    return (
        f"You are a fashion technical designer. The image(s) show a hand-drawn sketch of a {garment}: {shown}, "
        "in that order. List the construction details a pattern maker would need, as short noun phrases.\n"
        "Rules:\n"
        "- Only what is drawn: neckline, collar, closures and how many buttons, pockets and flaps, seams, "
        "darts, pleats, gathers, yokes, cuffs, hems, slits, vents, belts, ties, hoods, drawstrings, "
        "ribbing, trims, embroidery placement, sleeve and length, silhouette.\n"
        "- No colours, fabrics, background, mannequin or anything about the drawing itself. "
        "Ignore handwritten text unless it names a construction detail.\n"
        '- "garment": what is true for the whole garment and must look the same from every side '
        "(e.g. 'one-piece jumpsuit, top and trousers joined at the waist', 'wide-leg trousers', "
        "'pointed shirt collar', 'long sleeves with buttoned cuffs').\n"
        '- "front" / "back": what is only visible from that side. If the garment has a collar or hood, say '
        "in back how it looks from behind.\n"
        f"- At most {MAX_ITEMS} items per list, each under {MAX_ITEM_CHARS} characters.\n"
        'Answer with JSON only: {"garment": [...], "front": [...], "back": [...]}'
    )


def parse_details(content: str) -> SketchDetails:
    """Accepts bare JSON, JSON in a ```json fence, or JSON after some chatter / a <think> block."""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise DetailsError("The model did not answer with JSON")
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DetailsError(f"The model's JSON did not parse: {exc}") from exc
    if not isinstance(data, dict):
        raise DetailsError("The model's JSON is not an object")
    details = SketchDetails(**{k: v for k, v in data.items() if k in ("garment", "front", "back", "side")})
    # Drop phrases that would fight the tapped colour/fabric or describe the drawing.
    for name in ("garment", "front", "back", "side"):
        setattr(details, name, [item for item in getattr(details, name) if not BANNED.search(item)])
    return details


class DetailsClient:
    def __init__(self, settings: LlmSettings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        self._http = httpx.AsyncClient(
            base_url=settings.url or "http://llm.disabled", transport=transport, timeout=settings.timeout_s, headers=headers
        )

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    async def close(self) -> None:
        await self._http.aclose()

    async def extract(self, garment: str, sketches: dict[str, Path]) -> SketchDetails:
        """`sketches` maps view -> sketch image (the original photo or drawing, not the cleaned lines:
        the photo shows faint details the cleaning drops). Raises DetailsError."""
        if not self.enabled:
            raise DetailsError("Detail reading is not set up on the server (LLM_URL)")
        views = [v for v in ("front", "back", "side") if v in sketches]
        if not views:
            raise DetailsError("No sketches to read")
        content: list[dict[str, object]] = [{"type": "text", "text": instructions(garment, views)}]
        for view in views:
            content.append({"type": "image_url", "image_url": {"url": _image_url(sketches[view])}})
        payload = {
            "model": self.settings.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
            "max_tokens": 700,
            # Qwen3 thinks out loud by default; that only costs time here.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = await self._http.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise DetailsError(f"Could not reach the LLM ({exc.__class__.__name__})") from exc
        if response.status_code != 200:
            raise DetailsError(f"The LLM answered {response.status_code}: {response.text[:200]}")
        try:
            message = response.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DetailsError("Unexpected answer from the LLM") from exc
        details = parse_details(message)
        log.info("Sketch details for %s: %s", garment, details.model_dump())
        return details
