#!/usr/bin/env python3
"""Create a side-by-side visual evidence contact sheet for IP reports."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

try:
    import requests
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError as exc:  # pragma: no cover - intentionally user-facing
    print(
        "missing dependency. run: bash scripts/setup_env.sh",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


CANVAS_BG = (248, 249, 251)
CARD_BG = (255, 255, 255)
BORDER = (208, 214, 222)
TEXT = (30, 41, 59)
MUTED = (100, 116, 139)
ACCENT = (20, 83, 136)


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def fetch_image(source: str) -> tuple[Image.Image, str]:
    if is_url(source):
        response = requests.get(source, timeout=20)
        response.raise_for_status()
        name = Path(urlparse(source).path).name or "remote-image"
        return Image.open(io.BytesIO(response.content)), name
    path = Path(source).expanduser()
    return Image.open(path), path.name


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode not in {"RGB", "RGBA"}:
        img = img.convert("RGBA")
    if img.mode == "RGBA":
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        img = bg.convert("RGB")
    else:
        img = img.convert("RGB")
    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return img


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int
) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines() or [""]:
        current = ""
        for ch in raw:
            trial = current + ch
            if current and text_width(draw, trial, font) > max_width:
                lines.append(current)
                current = ch
            else:
                current = trial
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_gap: int = 4,
) -> int:
    x, y = xy
    for line in wrap_text(draw, text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + line_gap
    return y


def normalize_lists(left: list[str], right: list[str]) -> list[tuple[str | None, str | None]]:
    total = max(len(left), len(right))
    return [
        (left[idx] if idx < len(left) else None, right[idx] if idx < len(right) else None)
        for idx in range(total)
    ]


def build_sheet(
    plaintiff_sources: list[str],
    accused_sources: list[str],
    output: Path,
    title: str,
    plaintiff_label: str,
    accused_label: str,
) -> dict:
    pairs = normalize_lists(plaintiff_sources, accused_sources)
    if not pairs:
        raise ValueError("at least one plaintiff or accused image is required")

    width = 1800
    margin = 48
    gap = 32
    col_w = (width - margin * 2 - gap) // 2
    image_h = 560
    caption_h = 110
    header_h = 180
    row_h = image_h + caption_h + 42
    height = header_h + row_h * len(pairs) + margin

    canvas = Image.new("RGB", (width, height), CANVAS_BG)
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(44, bold=True)
    label_font = load_font(28, bold=True)
    body_font = load_font(24)
    small_font = load_font(20)

    draw.text((margin, 42), title, font=title_font, fill=TEXT)
    draw.text((margin, 104), "Visual evidence contact sheet", font=body_font, fill=MUTED)
    draw.text((margin, 144), plaintiff_label, font=label_font, fill=ACCENT)
    draw.text((margin + col_w + gap, 144), accused_label, font=label_font, fill=ACCENT)

    metadata = {"output": str(output), "pairs": []}

    for idx, (left_source, right_source) in enumerate(pairs, 1):
        y = header_h + idx * 0 + (idx - 1) * row_h
        for col_idx, source in enumerate([left_source, right_source]):
            x = margin + col_idx * (col_w + gap)
            draw.rounded_rectangle(
                (x, y, x + col_w, y + image_h + caption_h),
                radius=12,
                fill=CARD_BG,
                outline=BORDER,
                width=2,
            )
            if source:
                try:
                    img, name = fetch_image(source)
                    original_size = img.size
                    fitted = fit_image(img, col_w - 48, image_h - 48)
                    ix = x + (col_w - fitted.width) // 2
                    iy = y + 24 + (image_h - 48 - fitted.height) // 2
                    canvas.paste(fitted, (ix, iy))
                    caption = f"{idx}. {name} | {original_size[0]} x {original_size[1]}"
                    status = "ok"
                except Exception as exc:  # pragma: no cover - user artifact dependent
                    caption = f"{idx}. failed to load: {source}"
                    status = f"error: {exc}"
                    draw.text((x + 24, y + 230), "Image load failed", font=label_font, fill=(185, 28, 28))
                draw_wrapped(draw, (x + 24, y + image_h + 22), caption, small_font, MUTED, col_w - 48)
            else:
                status = "missing"
                source = ""
                draw.text((x + 24, y + 230), "No image provided", font=label_font, fill=MUTED)

            side = "plaintiff" if col_idx == 0 else "accused"
            metadata["pairs"].append({"pair": idx, "side": side, "source": source, "status": status})

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    metadata_path = output.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        left = Image.new("RGB", (500, 700), (235, 242, 255))
        right = Image.new("RGB", (500, 700), (255, 242, 235))
        ImageDraw.Draw(left).rectangle((80, 90, 420, 610), outline=(20, 83, 136), width=12)
        ImageDraw.Draw(right).rectangle((90, 100, 410, 600), outline=(180, 83, 9), width=12)
        left_path = tmp_path / "plaintiff.png"
        right_path = tmp_path / "accused.png"
        out_path = tmp_path / "sheet.png"
        left.save(left_path)
        right.save(right_path)
        build_sheet([str(left_path)], [str(right_path)], out_path, "Self Test", "Plaintiff", "Accused")
        if not out_path.exists() or out_path.stat().st_size <= 0:
            raise RuntimeError("self-test output missing")
    print("visual contact sheet self-test passed")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plaintiff", action="append", default=[], help="plaintiff image path or URL; repeatable")
    parser.add_argument("--accused", action="append", default=[], help="accused image path or URL; repeatable")
    parser.add_argument("--output", type=Path, default=Path("visual-contact-sheet.png"))
    parser.add_argument("--title", default="IP Packaging / Expression Comparison")
    parser.add_argument("--plaintiff-label", default="Right holder product / packaging")
    parser.add_argument("--accused-label", default="Accused product / packaging")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return self_test()

    metadata = build_sheet(
        args.plaintiff,
        args.accused,
        args.output,
        args.title,
        args.plaintiff_label,
        args.accused_label,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
