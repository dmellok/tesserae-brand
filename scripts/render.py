# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.60,<1.61", "pillow>=10.2"]
# ///
"""Rasterise every SVG in this repo into its PNG set.

The SVGs are the source of truth; every PNG and ``.ico`` here is generated
from them and committed, so nobody needs a toolchain to use a logo. Run this
after changing or adding an SVG:

    uv run scripts/render.py

Headless Chromium draws each SVG at its target size (rather than resampling
one large render down), so small icons get their own hinting and the 1 px
hairline on the on-dark server mark and the on-light cloud mark stays exactly
1 px at every size. If Chromium is missing, install it once with
``uv run --with 'playwright>=1.60,<1.61' playwright install chromium``.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from urllib.parse import quote

from PIL import Image
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent

# Rounded tile, transparent corners. Edge length in px.
MARK_SIZES = (16, 24, 32, 48, 64, 96, 128, 180, 192, 256, 384, 512, 1024)
# Full-bleed square, for platforms that apply their own mask (iOS, Android).
SQUARE_SIZES = (180, 192, 512, 1024)
# Wordmarks are sized by height; width follows the drawing.
WORDMARK_HEIGHTS = (32, 48, 64, 96, 128, 256, 512)
# Badges are drawn at their intended display size (48 px and 96 px tall).
BADGE_SCALES = (1, 2, 3, 4)
ICO_SIZES = (16, 32, 48)


def view_box(svg: str) -> tuple[float, float]:
    match = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not match:
        raise ValueError("SVG has no viewBox starting at 0 0")
    return float(match.group(1)), float(match.group(2))


def rasterise(page: Page, svg: str, width: int, height: int) -> Image.Image:
    uri = "data:image/svg+xml," + quote(svg, safe="")
    page.set_viewport_size({"width": width, "height": height})
    page.set_content(
        '<html><body style="margin:0;background:transparent">'
        f'<img src="{uri}" width="{width}" height="{height}" style="display:block">'
        "</body></html>"
    )
    page.wait_for_function("document.images[0].complete")
    png = page.locator("img").screenshot(omit_background=True)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    count = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)

        def save(svg: str, width: int, height: int, out: Path) -> Image.Image:
            nonlocal count
            out.parent.mkdir(parents=True, exist_ok=True)
            image = rasterise(page, svg, width, height)
            image.save(out, optimize=True)
            count += 1
            return image

        marks = ROOT / "marks"
        for src in sorted(marks.glob("*.svg")):
            # The favicon SVGs follow the system theme; a raster cannot.
            if src.stem.endswith("-favicon"):
                continue
            svg = src.read_text(encoding="utf-8")
            sizes = SQUARE_SIZES if src.stem.endswith("-square") else MARK_SIZES
            renders = {
                size: save(svg, size, size, marks / "png" / f"{src.stem}-{size}.png")
                for size in sizes
            }
            # A classic multi-size favicon.ico from the light-ground mark.
            if "-" not in src.stem:
                frames = [renders[size] for size in ICO_SIZES]
                frames[-1].save(
                    marks / f"{src.stem}-favicon.ico",
                    format="ICO",
                    append_images=frames[:-1],
                    sizes=[(size, size) for size in ICO_SIZES],
                )
                count += 1

        wordmarks = ROOT / "wordmarks"
        for src in sorted(wordmarks.glob("*.svg")):
            svg = src.read_text(encoding="utf-8")
            w, h = view_box(svg)
            for height in WORDMARK_HEIGHTS:
                width = round(w * height / h)
                save(svg, width, height, wordmarks / "png" / f"{src.stem}-h{height}.png")

        badges = ROOT / "badges"
        for src in sorted(badges.glob("*.svg")):
            svg = src.read_text(encoding="utf-8")
            w, h = view_box(svg)
            for scale in BADGE_SCALES:
                suffix = "" if scale == 1 else f"@{scale}x"
                save(
                    svg,
                    round(w * scale),
                    round(h * scale),
                    badges / "png" / f"{src.stem}{suffix}.png",
                )

        browser.close()
    print(f"Wrote {count} files")


if __name__ == "__main__":
    main()
