#!/usr/bin/env python3
"""Generate every Zence logo asset from one set of measurements.

The mark arrived as two 1000×1000 PNGs — dark ink for light backgrounds, white
ink for dark ones. PNGs are the wrong thing to ship: a favicon, a README badge
and an OG image all want different sizes, and rescaling a raster mark that is
mostly hairline-straight edges makes it look soft.

So the geometry below was measured off those PNGs — least-squares fits to the
diagonal edges, exact scanline transitions for the bars and tabs — and every
asset is emitted from it. One source of truth: change a coordinate here and the
favicon, the header logo and the social image all move together.

Normalized deliberately, and noted in README.md:

* The two exports disagreed on bar height by 2px out of 81, and on tab centring
  by 1.5px out of 944. Averaged and made symmetric — at that scale nobody can
  see the difference, but a vector logo whose two bars visibly differ reads as
  a mistake.

Reproduced as drawn, because both exports agree to within 2px and that makes it
artwork rather than export noise:

* The bottom tabs are shorter than the top ones — 55 against 93.
* There is an upward tab at the bottom bar's right end with no counterpart at
  the top bar's left end. The mark is not rotationally symmetric; a 180° overlay
  of either export mismatches by 44%.
* The diagonal is a trapezoid, not a parallelogram: 172 wide where it meets the
  top bar, 183 where it meets the bottom one.

Run: python3 brand/build.py       (stdlib only for the vectors; nothing here is
                                   imported by the app, the package, or the CI
                                   build — the outputs are committed)

Two assets have to be raster, and only those two: iOS ignores an SVG
apple-touch-icon, and no social scraper renders SVG. Both are produced from the
same vectors via ImageMagick, which is skipped with a warning if it is missing
rather than failing the run — the vectors are the part that matters.

Then `python3 brand/verify.py` diffs the result against the supplied artwork.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent

# --- the mark ---------------------------------------------------------------
# Tight bounding box: no padding baked in, so callers control their own space.

W, H = 945, 655

TOP_BAR_Y, TOP_BAR_H = 93, 82
BOTTOM_BAR_Y, BOTTOM_BAR_H = 520, 80

TAB_W = 66
TAB_X_LEFT = 45
TAB_X_RIGHT = W - TAB_W - TAB_X_LEFT
TOP_TAB_H = 93  # taller than the bottom tabs — see the module docstring
BOTTOM_TAB_H = 55
MID_TAB_Y = 449  # the unpaired upward tab, right end of the bottom bar

RADIUS = 3  # measured off the corner falloff in both exports

# The diagonal is NOT one stroke. It is two parallelograms of the same slope,
# the upper one offset to the right of the lower one, overlapping in the middle
# — the stroke is severed and displaced. The accent slab is exactly the union
# of the two in that band, which is how the construction gave itself away: fit
# the outline as a single straight edge and the residual is 9px, fit it as two
# and each lands inside a pixel.
#
# For a tool whose whole subject is interrupting something mid-flight, a cut
# diagonal with the intervention laid across the break is not decoration. It
# would have been quietly destroyed by drawing the obvious single stroke.
SLOPE = -4 / 3  # every edge in the mark, to within 0.04

ACCENT_TOP, ACCENT_BOTTOM = 242, 429

#: x = intercept + SLOPE·y, one per edge.
UPPER_LEFT, UPPER_RIGHT = 832.3, 1006.7
LOWER_LEFT, LOWER_RIGHT = 777.5, 960.0


def _edge(intercept: float, y: float) -> int:
    return round(intercept + SLOPE * y)


def _band(left: float, right: float, y_top: int, y_bottom: int):
    """The quadrilateral cut from a sloped stroke between two heights."""
    return (
        (_edge(left, y_top), y_top),
        (_edge(right, y_top), y_top),
        (_edge(right, y_bottom), y_bottom),
        (_edge(left, y_bottom), y_bottom),
    )


# Each stroke runs past the accent's far edge, so the two overlap and no seam
# can open up between them if the accent is ever recoloured or made partial.
DIAGONAL_UPPER = _band(UPPER_LEFT, UPPER_RIGHT, TOP_BAR_Y + TOP_BAR_H, ACCENT_BOTTOM)
DIAGONAL_LOWER = _band(LOWER_LEFT, LOWER_RIGHT, ACCENT_TOP, BOTTOM_BAR_Y)
ACCENT = _band(LOWER_LEFT, UPPER_RIGHT, ACCENT_TOP, ACCENT_BOTTOM)

# --- colour -----------------------------------------------------------------
# Sampled from the supplied files. The two greens differ on purpose: the muted
# one is what was drawn for light backgrounds, the vivid one for dark. That is
# also the correct instinct — a green needs more chroma to hold its weight
# against a dark field.

INK_DARK = "#29333D"
INK_LIGHT = "#FFFFFF"
ACCENT_ON_LIGHT = "#86A967"
ACCENT_ON_DARK = "#86C34A"


def _shapes(ink: str, accent: str, indent: str = "  ") -> str:
    """The mark's geometry, in draw order. Accent last: it sits on top."""
    bottom_tab_y = BOTTOM_BAR_Y + BOTTOM_BAR_H

    def rect(x: int, y: int, w: int, h: int) -> str:
        return f'{indent}<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{RADIUS}"/>'

    def poly(points: tuple[tuple[int, int], ...], fill: str | None = None) -> str:
        pts = " ".join(f"{x},{y}" for x, y in points)
        attr = f' fill="{fill}"' if fill else ""
        return f'{indent}<polygon points="{pts}"{attr}/>'

    # Tabs are drawn overlapping the bar they attach to by RADIUS, so the join
    # is square where they meet and rounded only at the free end.
    return "\n".join(
        [
            f'{indent}<g fill="{ink}">',
            rect(TAB_X_LEFT, 0, TAB_W, TOP_TAB_H + RADIUS),
            rect(TAB_X_RIGHT, 0, TAB_W, TOP_TAB_H + RADIUS),
            rect(TAB_X_RIGHT, MID_TAB_Y, TAB_W, BOTTOM_BAR_Y - MID_TAB_Y + RADIUS),
            rect(0, TOP_BAR_Y, W, TOP_BAR_H),
            poly(DIAGONAL_UPPER),
            poly(DIAGONAL_LOWER),
            rect(0, BOTTOM_BAR_Y, W, BOTTOM_BAR_H),
            rect(TAB_X_LEFT, bottom_tab_y - RADIUS, TAB_W, BOTTOM_TAB_H + RADIUS),
            rect(TAB_X_RIGHT, bottom_tab_y - RADIUS, TAB_W, BOTTOM_TAB_H + RADIUS),
            f"{indent}</g>",
            poly(ACCENT, accent),
        ]
    )


def mark(ink: str, accent: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="Zence">\n'
        f"  <title>{title}</title>\n"
        f"{_shapes(ink, accent)}\n"
        f"</svg>\n"
    )


def square_icon(padding_ratio: float = 0.11) -> str:
    """A square, theme-aware icon.

    The mark is 1.44:1, so a square favicon needs the letterboxing decided here
    rather than left to whatever is rendering it. Browsers that support an SVG
    favicon honour the media query, which is the only way a transparent icon
    stays visible in both a light and a dark browser chrome.
    """
    side = 1024
    scale = (1 - 2 * padding_ratio) * side / W
    dx = (side - W * scale) / 2
    dy = (side - H * scale) / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" '
        f'role="img" aria-label="Zence">\n'
        "  <title>Zence</title>\n"
        "  <style>\n"
        f"    .ink {{ fill: {INK_DARK}; }}\n"
        f"    .accent {{ fill: {ACCENT_ON_LIGHT}; }}\n"
        "    @media (prefers-color-scheme: dark) {\n"
        f"      .ink {{ fill: {INK_LIGHT}; }}\n"
        f"      .accent {{ fill: {ACCENT_ON_DARK}; }}\n"
        "    }\n"
        "  </style>\n"
        f'  <g transform="translate({dx:.1f} {dy:.1f}) scale({scale:.5f})">\n'
        f"{_shapes('currentColor', 'currentColor', indent='    ')}\n"
        "  </g>\n"
        "</svg>\n"
    ).replace('<g fill="currentColor">', '<g class="ink">').replace(
        ' fill="currentColor"/>', ' class="accent"/>'
    )


def on_field(bg: str, ink: str, accent: str, side: int, padding_ratio: float) -> str:
    """The mark centred on an opaque square — for Apple touch icons, which do
    not composite transparency onto anything sensible."""
    scale = (1 - 2 * padding_ratio) * side / W
    dx = (side - W * scale) / 2
    dy = (side - H * scale) / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" '
        f'role="img" aria-label="Zence">\n'
        "  <title>Zence</title>\n"
        f'  <rect width="{side}" height="{side}" fill="{bg}"/>\n'
        f'  <g transform="translate({dx:.1f} {dy:.1f}) scale({scale:.5f})">\n'
        f"{_shapes(ink, accent, indent='    ')}\n"
        "  </g>\n"
        "</svg>\n"
    )


def social_card(width: int = 1200, height: int = 630) -> str:
    """The mark on an opaque field, for link previews.

    No text. The scrapers already have `og:title` and `og:description`; setting
    the same words in a picture would only add a second place for them to go
    stale, and rendering them would mean baking a font into this script for one
    image. The mark is sized to read at the ~250px wide thumbnail a Slack unfurl
    actually shows.
    """
    scale = 0.46 * width / W
    dx = (width - W * scale) / 2
    dy = (height - H * scale) / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Zence">\n'
        "  <title>Zence</title>\n"
        f'  <rect width="{width}" height="{height}" fill="{INK_DARK}"/>\n'
        f'  <g transform="translate({dx:.1f} {dy:.1f}) scale({scale:.5f})">\n'
        f"{_shapes(INK_LIGHT, ACCENT_ON_DARK, indent='    ')}\n"
        "  </g>\n"
        "</svg>\n"
    )


TARGETS = {
    "brand/zence-mark-on-light.svg": lambda: mark(
        INK_DARK, ACCENT_ON_LIGHT, "Zence — for light backgrounds"
    ),
    "brand/zence-mark-on-dark.svg": lambda: mark(
        INK_LIGHT, ACCENT_ON_DARK, "Zence — for dark backgrounds"
    ),
    "brand/zence-icon.svg": square_icon,
    "brand/zence-icon-field.svg": lambda: on_field(
        INK_DARK, INK_LIGHT, ACCENT_ON_DARK, 512, 0.16
    ),
    "apps/web/app/icon.svg": square_icon,
    "apps/web/public/zence-mark-on-light.svg": lambda: mark(
        INK_DARK, ACCENT_ON_LIGHT, "Zence — for light backgrounds"
    ),
    "apps/web/public/zence-mark-on-dark.svg": lambda: mark(
        INK_LIGHT, ACCENT_ON_DARK, "Zence — for dark backgrounds"
    ),
    "brand/zence-social.svg": social_card,
}

#: (source vector, output raster, pixel size).
#:
#: The touch icon uses Next's `app/apple-icon.png` file convention, which emits
#: the right <link> on its own. The social card does not: the sibling
#: `opengraph-image.alt.txt` convention produced no `og:image:alt` here, so the
#: card lives in `public/` at a stable URL and `layout.tsx` declares it with the
#: alt text. A stable URL is the better property for a social image anyway —
#: scrapers cache by URL, and Next's content hash changes on every rebuild.
RASTERS = (
    ("brand/zence-icon-field.svg", "apps/web/app/apple-icon.png", "180x180"),
    ("brand/zence-social.svg", "apps/web/public/social-card.png", "1200x630"),
)


def _rasterize() -> None:
    if shutil.which("magick") is None:
        print(
            "\nskipped the two rasters: ImageMagick not found.\n"
            "  The committed PNGs are still valid; install `magick` and re-run\n"
            "  if the mark itself changed.",
            file=sys.stderr,
        )
        return

    for source, target, size in RASTERS:
        subprocess.run(
            ["magick", "-background", "none", str(REPO / source),
             "-resize", size, "-depth", "8", "-strip", str(REPO / target)],
            check=True,
        )
        print(f"wrote {target}")


def main(argv: list[str]) -> None:
    for relative, render in TARGETS.items():
        path = REPO / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(), encoding="utf-8")
        print(f"wrote {relative}")

    # CI regenerates and diffs, to catch an SVG edited by hand instead of here.
    # It checks the vectors only: PNG encoding is not byte-reproducible across
    # ImageMagick versions, so diffing the rasters would fail on the toolchain
    # rather than on the artwork.
    if "--vectors-only" not in argv:
        _rasterize()


if __name__ == "__main__":
    main(sys.argv[1:])
