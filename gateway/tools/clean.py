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
from gateway.placement import default_landmarks, landmarks_from_mask, load_mask, suggest_placement
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


def _check_image(original: Image.Image, bbox: tuple[int, int, int, int] | None, control: np.ndarray, guide: Path | None) -> Image.Image:
    left = original.convert("RGB")
    if bbox:
        ImageDraw.Draw(left).rectangle(bbox, outline=(220, 30, 30), width=max(2, left.width // 200))
    left.thumbnail((CANVAS_W, CANVAS_H))

    right = Image.new("RGB", (CANVAS_W, CANVAS_H), (255, 255, 255))
    if guide:
        right.paste(Image.open(guide).convert("RGBA"), (0, 0), Image.open(guide).convert("RGBA"))
    ink = Image.fromarray(np.minimum(control.astype(np.uint16) * 2, 255).astype(np.uint8))
    right.paste(Image.new("RGB", right.size, (20, 20, 20)), (0, 0), ink)

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
        if not scene.on_mannequin:
            placement = product_shot_placement(w, h)
        elif args.source == "drawn":
            placement = Placement(CANVAS_W / 2, CANVAS_H / 2, 1.0)
        else:
            mask = template.mask if template else None
            landmarks = landmarks_from_mask(load_mask(mask)) if mask else default_landmarks()
            placement = suggest_placement(w, h, "figure" if args.whole_body else garment.placement, landmarks)
        control = place_on_canvas(crop, placement)

        stem = args.out / path.stem.replace(" ", "_")
        Image.fromarray(crop).save(f"{stem}_lines.png")
        Image.fromarray(control).save(f"{stem}_control.png")
        _check_image(picture, bbox, control, template.guide if template else None).save(f"{stem}_check.png")
        print(f"{path.name}: crop {w}x{h}, placement cx={placement.cx:.0f} cy={placement.cy:.0f} scale={placement.scale:.2f} -> {stem}_*.png")


if __name__ == "__main__":
    main()
