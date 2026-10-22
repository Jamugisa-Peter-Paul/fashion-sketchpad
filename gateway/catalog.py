"""Loads catalog.yaml and merges in which body templates exist on disk."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import BaseModel

from gateway.templates import available_views

CATALOG_PATH = Path(__file__).with_name("catalog.yaml")


class Choice(BaseModel):
    id: str
    label: str
    prompt: str
    default: bool = False


class Garment(Choice):
    placement: Literal["top", "bottom", "full"]


class Colour(Choice):
    hex: str


class Scene(Choice):
    on_mannequin: bool


class Body(Choice):
    group: Literal["women", "men", "kids"]


class Catalog(BaseModel):
    garments: list[Garment]
    fabrics: list[Choice]
    colours: list[Colour]
    prints: list[Choice]
    fits: list[Choice]
    buttons: list[Choice]
    stitching: list[Choice]
    scenes: list[Scene]
    mannequin_finishes: list[Choice]
    bodies: list[Body]

    def find(self, section: str, item_id: str) -> Choice:
        for item in getattr(self, section):
            if item.id == item_id:
                return item
        raise KeyError(f"Unknown {section} id: {item_id}")

    def garment(self, item_id: str) -> Garment:
        return cast(Garment, self.find("garments", item_id))

    def scene(self, item_id: str) -> Scene:
        return cast(Scene, self.find("scenes", item_id))

    def colour(self, item_id: str) -> Colour:
        return cast(Colour, self.find("colours", item_id))


class BodyStatus(Body):
    views: list[str]
    available: bool


class CatalogResponse(BaseModel):
    garments: list[Garment]
    fabrics: list[Choice]
    colours: list[Colour]
    prints: list[Choice]
    fits: list[Choice]
    buttons: list[Choice]
    stitching: list[Choice]
    scenes: list[Scene]
    mannequin_finishes: list[Choice]
    bodies: list[BodyStatus]


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    with path.open(encoding="utf-8") as fh:
        return Catalog.model_validate(yaml.safe_load(fh))


def catalog_with_templates(catalog: Catalog, templates_dir: Path) -> CatalogResponse:
    bodies = []
    for body in catalog.bodies:
        views = available_views(templates_dir, body.id)
        # Front is the minimum needed to design anything.
        bodies.append(BodyStatus(**body.model_dump(), views=views, available="front" in views))
    return CatalogResponse(**catalog.model_dump(exclude={"bodies"}), bodies=bodies)
