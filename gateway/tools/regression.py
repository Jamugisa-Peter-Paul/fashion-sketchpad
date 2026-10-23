"""Render the 10 regression garments through a running gateway and build a contact sheet.

    APP_TOKEN=... python -m gateway.tools.regression --url http://127.0.0.1:8190 --scenes product_shot light_room

For every garment in gateway/tests/samples/garments/ and every scene: clean front + back, read the details
(if the LLM is set up), generate, wait, then save the renders, the placement checks and the depth maps to
--out, plus contact_<scene>.png: one row per garment (sketch front/back, render front/back). Takes about
two minutes per garment per scene on the A4000; --only limits it to some garments (e.g. --only 06 10).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

GARMENTS_DIR = Path(__file__).resolve().parents[1] / "tests" / "samples" / "garments"
# file stem -> catalog garment id
GARMENTS = {
    "01_aline_dress": "dress",
    "02_short_sleeve_shirt": "shirt",
    "03_pencil_skirt": "skirt",
    "04_hoodie": "hoodie",
    "05_blazer": "jacket",
    "06_belted_jumpsuit": "jumpsuit",
    "07_kaftan": "kaftan",
    "08_cargo_shorts": "shorts",
    "09_wrap_maxi_dress": "dress",
    "10_bomber_jacket": "jacket",
}
TILE_W, TILE_H = 208, 304  # quarter of 832x1216


def _tile(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    image.thumbnail((TILE_W, TILE_H))
    tile = Image.new("RGB", (TILE_W, TILE_H), "white")
    tile.paste(image, ((TILE_W - image.width) // 2, (TILE_H - image.height) // 2))
    return tile


class Gateway:
    def __init__(self, url: str, token: str) -> None:
        self.http = httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=300)

    def clean(self, path: Path, garment: str, scene: str, view: str) -> str:
        response = self.http.post(
            "/api/sketch/clean",
            files={"image": (path.name, path.read_bytes(), "image/png")},
            data={"source": "paper", "scene": scene, "garment": garment, "body": "female_slim", "view": view},
        )
        response.raise_for_status()
        return response.json()["clean_id"]

    def details(self, garment: str, views: dict[str, str]) -> dict[str, object] | None:
        response = self.http.post("/api/sketch/details", json={"garment": garment, "views": views})
        response.raise_for_status()
        body = response.json()
        if body["error"]:
            print(f"    details: {body['error']}")
        return body["details"]

    def generate(self, style: dict[str, object], views: dict[str, str], title: str) -> str:
        payload = {"style": style, "title": title, "views": {v: {"clean_id": c} for v, c in views.items()}}
        response = self.http.post("/api/generate", json=payload)
        response.raise_for_status()
        return response.json()["job_id"]

    def wait(self, job_id: str, timeout: float = 1800) -> dict[str, object]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.http.get(f"/api/jobs/{job_id}").json()
            if status["status"] in ("done", "error"):
                return status
            time.sleep(3)
        raise TimeoutError(job_id)

    def image(self, path: str) -> Image.Image | None:
        response = self.http.get(path)
        return Image.open(io.BytesIO(response.content)) if response.status_code == 200 else None


def run(args: argparse.Namespace) -> int:
    token = os.environ.get("APP_TOKEN", "")
    if not token:
        print("Set APP_TOKEN to one of the gateway's APP_TOKENS", file=sys.stderr)
        return 2
    gateway = Gateway(args.url, token)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stems = [s for s in GARMENTS if not args.only or any(s.startswith(o) for o in args.only)]

    for scene in args.scenes:
        rows: list[Image.Image] = []
        for stem in stems:
            garment = GARMENTS[stem]
            print(f"{scene}: {stem} ({garment})")
            sketches = {view: GARMENTS_DIR / f"{stem}_{view}.png" for view in ("front", "back")}
            views = {view: gateway.clean(path, garment, scene, view) for view, path in sketches.items()}
            style: dict[str, object] = {
                "garment": garment,
                "body": "female_slim",
                "scene": scene,
                "colour": args.colour,
                "fabric": args.fabric,
            }
            if not args.no_details:
                details = gateway.details(garment, views)
                if details is not None:
                    style["details"] = details
                    print(f"    details: {json.dumps(details)}")
            job_id = gateway.generate(style, views, title=f"regression {stem}")
            status = gateway.wait(job_id)
            print(f"    job {job_id}: {status['status']}")

            tiles = [_tile(Image.open(p)) for p in sketches.values()]
            for view in ("front", "back"):
                render = gateway.image(f"/api/jobs/{job_id}/{view}.png")
                for name, path in (
                    ("render", f"/api/jobs/{job_id}/{view}.png"),
                    ("check", f"/api/jobs/{job_id}/{view}/check.png"),
                    ("depth", f"/api/jobs/{job_id}/{view}/depth.png"),
                ):
                    image = render if name == "render" else gateway.image(path)
                    if image is not None:
                        image.save(out / f"{scene}_{stem}_{view}_{name}.png")
                tiles.append(_tile(render) if render else Image.new("RGB", (TILE_W, TILE_H), (240, 200, 200)))
            row = Image.new("RGB", (TILE_W * len(tiles), TILE_H + 20), "white")
            for i, tile in enumerate(tiles):
                row.paste(tile, (i * TILE_W, 20))
            ImageDraw.Draw(row).text((6, 4), f"{stem}  ({garment}, job {job_id})", fill="black")
            rows.append(row)

        if rows:
            sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), "white")
            y = 0
            for row in rows:
                sheet.paste(row, (0, y))
                y += row.height
            sheet.save(out / f"contact_{scene}.png")
            print(f"Contact sheet: {out / f'contact_{scene}.png'}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8190")
    parser.add_argument("--scenes", nargs="+", default=["product_shot", "light_room"])
    parser.add_argument("--only", nargs="*", help="garment file prefixes, e.g. 06 10")
    parser.add_argument("--colour", default="camel")
    parser.add_argument("--fabric", default="cotton_twill")
    parser.add_argument("--no-details", action="store_true", help="render without asking the LLM for details")
    parser.add_argument("--out", default="regression_out")
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
