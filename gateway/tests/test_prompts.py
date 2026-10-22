from __future__ import annotations

import pytest
from pydantic import ValidationError

from gateway.catalog import load_catalog
from gateway.prompts import StyleOptions, build_prompt, garment_description, nearest_colour

CATALOG = load_catalog()


def style(**overrides: object) -> StyleOptions:
    base: dict[str, object] = {"garment": "shirt", "body": "female_slim", "colour": "camel", "fabric": "cotton_twill"}
    base.update(overrides)
    return StyleOptions(**base)  # type: ignore[arg-type]


def test_garment_description_reads_naturally() -> None:
    text = garment_description(CATALOG, style(buttons="wood"))
    assert text == "a regular fit camel tan (#C2A878) cotton twill button-up shirt with wooden buttons and tonal stitching"


def test_light_room_prompt_matches_proven_recipe() -> None:
    prompt = build_prompt(CATALOG, style(), "front")
    assert prompt.startswith(
        "Photorealistic fashion product photograph of a faceless matte dark grey fashion mannequin wearing the garment,"
        " a regular fit camel tan (#C2A878) cotton twill button-up shirt"
    )
    assert "faceless sculpted mannequin with a slim female figure standing straight" in prompt
    assert "large window on the left, natural daylight casting crisp window-frame shadows" in prompt
    assert "light grey wall and polished floor" in prompt and prompt.endswith("high-end fashion lookbook")


def test_front_and_back_share_garment_wording() -> None:
    front = build_prompt(CATALOG, style(), "front")
    back = build_prompt(CATALOG, style(), "back")
    assert back == "Back view. " + front
    assert build_prompt(CATALOG, style(), "back", view_hint=False) == front


def test_product_shot_has_no_mannequin() -> None:
    prompt = build_prompt(CATALOG, style(scene="product_shot"), "front")
    assert prompt.startswith("Photorealistic ghost mannequin product photograph of a regular fit camel tan")
    assert "nothing below the hem" in prompt and "faceless" not in prompt


def test_custom_hex_uses_nearest_name_and_exact_hex() -> None:
    assert nearest_colour(CATALOG, "#C4AA7A").id == "camel"
    text = garment_description(CATALOG, style(custom_hex="#1e2b45"))
    assert "navy blue (#1E2B45)" in text


def test_prints_wrap_the_colour() -> None:
    assert "floral print on a emerald green (#1E7A53) ground cotton" in garment_description(
        CATALOG, style(print="floral", colour="emerald", fabric="cotton")
    )


def test_kitenge_fabric_implies_the_print_once() -> None:
    text = garment_description(CATALOG, style(fabric="kitenge", garment="gomesi"))
    assert text.count("kitenge") == 1
    assert "African kitenge wax print with a dominant camel tan (#C2A878) pattern cotton gomesi" in text


def test_hidden_buttons_and_contrast_stitching() -> None:
    text = garment_description(CATALOG, style(buttons="hidden", stitching="contrast"))
    assert text.endswith("with a concealed button placket and contrast topstitching")


def test_notes_are_tidied_and_appended() -> None:
    text = garment_description(CATALOG, style(notes="  rolled   sleeves,\n patch pockets. "))
    assert text.endswith(", rolled sleeves, patch pockets")


def test_mannequin_uses_finish_and_body() -> None:
    prompt = build_prompt(CATALOG, style(finish="chrome_silver", body="girl_teen"), "front")
    assert "a faceless chrome silver fashion mannequin wearing the garment" in prompt
    assert "with a teenage girl figure" in prompt


def test_check_ids_and_validation() -> None:
    style().check_ids(CATALOG)
    with pytest.raises(KeyError, match="fabrics"):
        style(fabric="velvet").check_ids(CATALOG)
    with pytest.raises(ValidationError):
        style(custom_hex="tan")


def test_mannequin_scenes_say_the_garment_is_worn() -> None:
    for scene in ("light_room", "plain_studio"):
        prompt = build_prompt(CATALOG, style(scene=scene), "front")
        assert "a faceless matte dark grey fashion mannequin wearing the garment" in prompt
        assert "the garment fully dressed on the mannequin, never shown nude" in prompt
    assert "nude" not in build_prompt(CATALOG, style(scene="product_shot"), "front")
