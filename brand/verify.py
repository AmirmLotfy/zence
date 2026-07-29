#!/usr/bin/env python3
"""Diff the generated vector mark against the artwork it was traced from.

`build.py` reproduces the logo from measurements, which is a claim — this is
what checks it. The mark is rasterized at the source PNG's own scale and
compared pixel by pixel, separately for the ink and the accent, so an error in
one cannot be hidden by the other.

The first run of this caught two real mistakes: a missing tab, and a diagonal
edge 7px out of true. Both were invisible in a side-by-side look at the two
images and obvious the moment they were subtracted.

Writes brand/.verify-diff.png — red is artwork the vector missed, blue is
vector that is not in the artwork.

Needs Pillow and ImageMagick. Neither is a dependency of Zence; this is a
one-off check for when the mark changes, not part of the build.

Exit code 0 if the mark matches within tolerance, 1 otherwise.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent

#: The artwork's tight ink bounding box, per file: (left, top, right, bottom).
#:
#: The two exports are not the same drawing at two sizes. Normalized to a common
#: width, the dark-background one has a top bar ~3px thinner and a bottom bar
#: ~3px lower — under 0.5% of the mark's height, but spread along two 945px
#: edges, which is most of why the light export scores worse below.
#:
#: The vector follows the dark-background export: it is the larger of the two,
#: and the more internally consistent (its bars agree with its tabs, the other's
#: do not). So that file is checked strictly and the other is reported.
SOURCES = {
    "source/zence-mark-on-dark.png": ((29, 171, 974, 827), 0.020),
    "source/zence-mark-on-light.png": ((41, 186, 960, 825), 0.055),
}

#: The strict bound is 2%. The mark's outline is roughly 8,450px long at this
#: scale, so 2% of its 253,000px area is an average edge error of 0.6px — below
#: what thresholding an antialiased PNG can resolve, and therefore about as
#: close as a trace can get. Anything structural — a missing element, an edge at
#: the wrong angle — lands far above it: the first run of this scored 3.8% and
#: was missing a whole tab.


def is_green(r: int, g: int, b: int) -> bool:
    return g > r and g > b + 25


def compare(source: pathlib.Path, box: tuple[int, int, int, int], vector: pathlib.Path):
    art = Image.open(source).convert("RGBA").crop(box)
    width, height = art.size

    with tempfile.TemporaryDirectory() as tmp:
        rendered = pathlib.Path(tmp) / "vector.png"
        subprocess.run(
            [
                "magick",
                "-background",
                "none",
                str(vector),
                "-resize",
                f"{width}x{height}!",
                str(rendered),
            ],
            check=True,
        )
        vec = Image.open(rendered).convert("RGBA")

    art_px, vec_px = art.load(), vec.load()
    diff_image = Image.new("RGB", (width, height), (255, 255, 255))
    out = diff_image.load()

    counts = {"union": 0, "shape": 0, "accent": 0}
    for y in range(height):
        for x in range(width):
            ar, ag, ab, aa = art_px[x, y]
            vr, vg, vb, va = vec_px[x, y]
            art_ink, vec_ink = aa >= 128, va >= 128
            if not (art_ink or vec_ink):
                continue
            counts["union"] += 1

            if art_ink != vec_ink:
                counts["shape"] += 1
                out[x, y] = (220, 40, 40) if art_ink else (40, 90, 220)
                continue

            if is_green(ar, ag, ab) != is_green(vr, vg, vb):
                counts["accent"] += 1
                out[x, y] = (240, 170, 40)
            else:
                out[x, y] = (218, 218, 218)

    return counts, diff_image


def main() -> int:
    failures = []
    tiles = []
    for relative, (box, tolerance) in SOURCES.items():
        source = ROOT / relative
        vector = ROOT / (
            "zence-mark-on-dark.svg" if "on-dark" in relative else "zence-mark-on-light.svg"
        )
        counts, image = compare(source, box, vector)
        tiles.append(image)

        union = counts["union"]
        shape = counts["shape"] / union
        accent = counts["accent"] / union
        ok = shape <= tolerance and accent <= 0.01
        if not ok:
            failures.append(relative)
        print(
            f"{'ok  ' if ok else 'FAIL'} {relative}   (bound {tolerance:.1%})\n"
            f"       silhouette differs on {counts['shape']:>6} px ({shape:6.2%})\n"
            f"       accent     differs on {counts['accent']:>6} px ({accent:6.2%})"
        )

    combined = Image.new(
        "RGB",
        (max(t.width for t in tiles), sum(t.height for t in tiles) + 20),
        (255, 255, 255),
    )
    offset = 0
    for tile in tiles:
        combined.paste(tile, (0, offset))
        offset += tile.height + 20
    combined.save(ROOT / ".verify-diff.png")
    print(f"\nwrote {(ROOT / '.verify-diff.png').relative_to(ROOT.parent)}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
