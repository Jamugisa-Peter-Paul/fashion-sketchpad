"""Prompt builder: tapped choices -> prompt text. Pure functions, no I/O.

Front and back renders of a design share the seed and the exact same garment wording (colour name + hex,
fabric, buttons, stitching). Changing those words between views makes the colour drift (olive vs tan).
Only the construction details differ per view: what the sketch shows from that side (gateway/details.py),
after the details shared by every view.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from gateway.catalog import Catalog, Colour
from gateway.details import SketchDetails

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
VIEW_HINTS = {"front": "", "back": "Back view. ", "side": "Side view. "}


class StyleOptions(BaseModel):
    """Everything the user picks on the Style screen (catalog ids), plus optional free-text notes."""

    garment: str
    body: str
    colour: str = "camel"
    custom_hex: str | None = None  # from the colour picker; overrides `colour`
    print: str = "plain"
    fabric: str = "cotton"
    fit: str = "regular"
    buttons: str = "default"
    stitching: str = "tonal"
    scene: str = "light_room"
    finish: str = "matte_dark_grey"
    notes: str = Field(default="", max_length=300)
    # Construction details per view (chips on the Style screen). None = read them off the sketch at render
    # time (if the LLM is set up); an empty SketchDetails = the user removed them all.
    details: SketchDetails | None = None

    @field_validator("custom_hex")
    @classmethod
    def _hex(cls, value: str | None) -> str | None:
        if value is not None and not HEX.match(value):
            raise ValueError("custom_hex must look like #RRGGBB")
        return value.upper() if value else None

    def check_ids(self, catalog: Catalog) -> None:
        """Raises KeyError naming the first unknown catalog id."""
        for section, value in (
            ("garments", self.garment),
            ("bodies", self.body),
            ("colours", self.colour),
            ("prints", self.print),
            ("fabrics", self.fabric),
            ("fits", self.fit),
            ("buttons", self.buttons),
            ("stitching", self.stitching),
            ("scenes", self.scene),
            ("mannequin_finishes", self.finish),
        ):
            catalog.find(section, value)


def _rgb(hex_value: str) -> tuple[int, int, int]:
    return int(hex_value[1:3], 16), int(hex_value[3:5], 16), int(hex_value[5:7], 16)


def nearest_colour(catalog: Catalog, hex_value: str) -> Colour:
    """Closest named colour, using the cheap 'redmean' perceptual distance."""
    r1, g1, b1 = _rgb(hex_value)

    def distance(colour: Colour) -> float:
        r2, g2, b2 = _rgb(colour.hex)
        rm = (r1 + r2) / 2
        return (2 + rm / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - rm) / 256) * (b1 - b2) ** 2

    return min(catalog.colours, key=distance)


def colour_words(catalog: Catalog, style: StyleOptions) -> str:
    """e.g. 'camel tan (#C2A878)'. Flux follows colour names better than hex, the hex pins the shade."""
    if style.custom_hex:
        return f"{nearest_colour(catalog, style.custom_hex).prompt} ({style.custom_hex})"
    colour = catalog.colour(style.colour)
    return f"{colour.prompt} ({colour.hex})"


def clean_notes(notes: str) -> str:
    return re.sub(r"\s+", " ", notes).strip().rstrip(".,;")


def garment_description(catalog: Catalog, style: StyleOptions) -> str:
    """e.g. 'a regular fit camel tan (#C2A878) cotton twill button-up shirt with wooden buttons and tonal stitching'."""
    print_id, fabric_id = style.print, style.fabric
    if fabric_id == "kitenge":
        # Kitenge is a printed cloth: describe the print once and let the fabric be the cotton base.
        print_id, fabric_words = "kitenge" if print_id == "plain" else print_id, "cotton"
    else:
        fabric_words = catalog.find("fabrics", fabric_id).prompt

    pattern = catalog.find("prints", print_id).prompt.format(colour=colour_words(catalog, style))
    fit = catalog.find("fits", style.fit).prompt
    garment = catalog.find("garments", style.garment).prompt
    details = [catalog.find("buttons", style.buttons).prompt, catalog.find("stitching", style.stitching).prompt]
    details = [d for d in details if d]

    text = f"a {fit} {pattern} {fabric_words} {garment}"
    if details:
        text += " with " + " and ".join(details)
    notes = clean_notes(style.notes)
    if notes:
        text += f", {notes}"
    return text


def view_details(catalog: Catalog, style: StyleOptions, view: str, details: SketchDetails | None = None) -> list[str]:
    """Construction details for one view: the garment's own back-view wording from the catalog (e.g. the
    shirt collar seen from behind), then what the sketch shows. `details` overrides style.details."""
    details = details if details is not None else style.details
    items = list(details.for_view(view)) if details else []
    if view == "back":
        back = catalog.garment(style.garment).back
        if back and back not in items:
            items.insert(0, back)
    return items


def build_prompt(
    catalog: Catalog, style: StyleOptions, view: str, view_hint: bool = True, details: SketchDetails | None = None
) -> str:
    scene = catalog.scene(style.scene)
    finish = catalog.find("mannequin_finishes", style.finish).prompt
    figure = catalog.find("bodies", style.body).prompt
    garment = garment_description(catalog, style)
    items = view_details(catalog, style, view, details)
    if items:
        garment += ", with these exact construction details: " + ", ".join(items)
    prompt = scene.prompt.format(garment=garment, finish=finish, figure=figure, mannequin=f"{finish} {figure}")
    return (VIEW_HINTS.get(view, "") if view_hint else "") + prompt
