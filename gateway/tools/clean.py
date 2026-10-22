"""Preview sketch cleaning without the API or ComfyUI.

    python -m gateway.tools.clean photo.jpg [more.jpg ...] [--scene product_shot] [--garment trousers]
    python -m gateway.tools.clean drawing.png --source drawn
    python -m gateway.tools.clean photo.jpg --templates /home/dct/ComfyUI/output/templates --body female_slim

For each input it writes to --out (default gateway/tools/out/):
    <name>_lines.png    cleaned garment, cropped (white on black)
    <name>_control.png  final 832x1216 control image sent to ComfyUI
    <name>_check.png    original with the crop box (red) | control image over the body guide
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from gateway.catalog import load_catalog
from gateway.placement import (
    BodyLandmarks,
    check_image,
    default_landmarks,
    ink_extent,
    landmarks_from_mask,
    load_mask,
    suggest_placement,
)
from gateway.sketch import (
    CANVAS_H,
    CANVAS_W,
    PaperParams,
    Placement,
    clean_drawn,
    clean_paper,
    crop_to_content,
    decode_image,
    place_on_canvas,
    product_shot_placement,
)
from gateway.templates import find_view

DEFAULT_OUT = Path(__file__).parent / "out"


def _check_sheet(
    original: Image.Image,
    bbox: tuple[int, int, int, int] | None,
    control: np.ndarray,
    body: BodyLandmarks | None,
    background: Path | None,
) -> Image.Image:
    """Original with the crop box (red) | placement check: control lines over the template with landmarks."""
    left = original.convert("RGB")
    if bbox:
        ImageDraw.Draw(left).rectangle(bbox, outline=(220, 30, 30), width=max(2, left.width // 200))
    left.thumbnail((CANVAS_W, CANVAS_H))
    right = check_image(control, body, background)

    sheet = Image.new("RGB", (CANVAS_W * 2 + 16, CANVAS_H), (60, 60, 60))
    sheet.paste(left, (0, 0))
    sheet.paste(right, (CANVAS_W + 16, 0))
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--source", choices=["paper", "drawn"], default="paper")
    parser.add_argument("--scene", default="light_room", help="light_room | plain_studio | product_shot")
    parser.add_argument("--garment", default="shirt")
    parser.add_argument("--whole-body", action="store_true", help="the sketch shows a whole figure")
    parser.add_argument("--templates", type=Path, help="TEMPLATES_DIR, for real body placement")
    parser.add_argument("--body", default="female_slim")
    parser.add_argument("--view", default="front")
    parser.add_argument("--boost", type=float, default=PaperParams.boost)
    parser.add_argument("--sigma", type=float, default=PaperParams.sigma)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    catalog = load_catalog()
    scene = catalog.scene(args.scene)
    garment = catalog.garment(args.garment)
    template = find_view(args.templates, args.body, args.view) if args.templates else None
    params = PaperParams(boost=args.boost, sigma=args.sigma)
    args.out.mkdir(parents=True, exist_ok=True)

    for path in args.images:
        picture = decode_image(path.read_bytes())
        bbox = None
        if args.source == "paper":
            result = clean_paper(picture, params)
            crop, bbox = result.lines, result.bbox
        else:
            lines = clean_drawn(picture)
            crop = lines if scene.on_mannequin else crop_to_content(lines)

        h, w = crop.shape
        body = None
        if not scene.on_mannequin:
            placement = product_shot_placement(w, h)
        else:
            mask = template.mask if template else None
            body = landmarks_from_mask(load_mask(mask)) if mask else default_landmarks()
            if args.source == "drawn":
                placement = Placement(CANVAS_W / 2, CANVAS_H / 2, 1.0)
            else:
                placement = suggest_placement(crop, "figure" if args.whole_body else garment.placement, body)
        control = place_on_canvas(crop, placement)

        stem = args.out / path.stem.replace(" ", "_")
        Image.fromarray(crop).save(f"{stem}_lines.png")
        Image.fromarray(control).save(f"{stem}_control.png")
        background = (template.photo or template.guide) if template else None
        _check_sheet(picture, bbox, control, body, background).save(f"{stem}_check.png")
        x0, y0, x1, y1 = ink_extent(control)
        print(f"{path.name}: crop {w}x{h}, scale {placement.scale:.2f}, on canvas x {x0}-{x1} y {y0}-{y1} -> {stem}_*.png")
        if body:
            print(
                f"  body: neck {body.neck:.0f}, shoulders {body.shoulder:.0f} (width {body.shoulder_width:.0f}),"
                f" waist {body.waist:.0f}, hips {body.hip:.0f}; garment width {x1 - x0 + 1}"
            )


if __name__ == "__main__":
    main()
