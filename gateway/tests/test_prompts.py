from __future__ import annotations

import pytest
from pydantic import ValidationError

from gateway.catalog import load_catalog
from gateway.details import SketchDetails
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
    assert "faceless matte dark grey sculpted mannequin with a smooth featureless egg-shaped head and a slim female figure standing straight" in prompt
    assert "large window on the left, natural daylight casting crisp window-frame shadows" in prompt
    assert "light grey wall and polished floor" in prompt and prompt.endswith(
        "high-end fashion lookbook. Colours: the garment is camel tan (#C2A878), the mannequin is matte dark grey"
    )


def test_front_and_back_share_garment_wording() -> None:
    front = build_prompt(CATALOG, style(), "front")
    back = build_prompt(CATALOG, style(), "back")
    garment = garment_description(CATALOG, style())
    assert garment in front and garment in back
    # The back adds what Flux tends to lose from behind (here: the collar), nothing else changes.
    back_extra = ", with these exact construction details: the shirt collar visible folded around the back of the neck, a back yoke seam"
    assert back == "Back view. " + front.replace(garment, garment + back_extra)
    assert build_prompt(CATALOG, style(), "front", view_hint=False) == front


def test_one_piece_garments_stay_one_piece_from_behind() -> None:
    back = build_prompt(CATALOG, style(garment="jumpsuit"), "back")
    assert "one-piece jumpsuit" in back and "not a separate top and trousers" in back
    assert "not a separate" not in build_prompt(CATALOG, style(garment="jumpsuit"), "front")


def test_details_go_into_their_own_view_after_the_shared_ones() -> None:
    details = SketchDetails(garment=["pointed collar"], front=["five-button placket", "pointed collar"], back=["box pleat"])
    s = style(details=details)
    front = build_prompt(CATALOG, s, "front")
    back = build_prompt(CATALOG, s, "back")
    assert "with these exact construction details: pointed collar, five-button placket, Photo" not in front
    assert "construction details: pointed collar, five-button placket. A faceless" in front
    assert "construction details: the shirt collar visible folded around the back of the neck, a back yoke seam," \
        " pointed collar, box pleat. A faceless" in back
    assert "box pleat" not in front and "five-button" not in back


def test_explicit_details_override_the_style_ones() -> None:
    s = style(details=SketchDetails(front=["patch pockets"]))
    prompt = build_prompt(CATALOG, s, "front", details=SketchDetails(front=["welt pockets"]))
    assert "welt pockets" in prompt and "patch pockets" not in prompt


def test_user_details_are_sanitised() -> None:
    details = SketchDetails(front=["  Two {flap} pockets. ", "x" * 200, "", "two flap pockets"] + [f"d{i}" for i in range(20)])
    assert details.front[0] == "two flap pockets"
    assert len(details.front[1]) == 60
    assert len(details.front) == 8 and details.front.count("two flap pockets") == 1


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
    assert "and a teenage girl figure" in prompt


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
