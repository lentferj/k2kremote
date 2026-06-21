# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 23: why does auto-mode pick braille for this page?  (read-only)

Navigate the K2000 to the page in question FIRST (e.g. Disk mode), then run this.
It reads the same ALLTEXT + GETGRAPHICS + high-bit mask the app uses and dumps
every blank, non-reverse cell that has graphics pixels — so we can see exactly
what is being counted as "graphics". Self-contained (no Textual import).

    .venv/bin/python probes/p23_text_page.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from k2kremote import braille  # noqa: E402
from probes.hw import connect  # noqa: E402

# Mirror of the app's heuristic constants / grid (kept inline so this probe does
# not import k2kremote.app, which pulls in Textual/textual-image).
_TEXT_ROWS, _TEXT_COLS, _CELL_W, _CELL_H = 8, 40, 6, 8
_GRAPHICS_PAGE_PIXELS = 64
_SOLID_CELL_PIXELS = 44
_RULE_ROW_FRACTION = 0.8
_GRAPHICS_PER_TEXT_CELL = 10


def text_grid(rows):
    rows = (list(rows or []) + [""] * _TEXT_ROWS)[:_TEXT_ROWS]
    return [row.ljust(_TEXT_COLS)[:_TEXT_COLS] for row in rows]


b = connect()
print("connected:", b.description)
pixels = b.get_graphics()
text, reverse = b.get_screen_text_attrs()
text_rows = text.split("\n")

print("\n=== ALLTEXT (text rows) ===")
for r, line in enumerate(text_rows):
    print(f"{r}: {line!r}")
print("=== reverse high-bit mask (per row) ===")
for r, rv in enumerate(reverse):
    print(f"{r}: {rv}")

import numpy as np  # noqa: E402

arr = np.array(braille._fit(braille._normalize(pixels)))  # (64, 240) bool
rules = arr.sum(axis=1) >= int(_RULE_ROW_FRACTION * arr.shape[1])
print(f"\nfull-width rule pixel-rows dropped: {[int(y) for y in np.where(rules)[0]]}")
arr[rules] = False
grid = text_grid(text_rows)
partial_sum = 0
text_cells = 0
print("=== blank, non-reverse cells with graphics (rows 1..6, after rule removal) ===")
for r in range(1, _TEXT_ROWS - 1):
    line = grid[r] if r < len(grid) else ""
    rev = reverse[r] if r < len(reverse) else ""
    band = arr[r * _CELL_H:(r + 1) * _CELL_H]
    hits = []
    for c in range(_TEXT_COLS):
        if (line[c] if c < len(line) else " ") != " ":
            text_cells += 1
            continue
        if c < len(rev) and rev[c] == "1":
            continue
        fill = int(band[:, c * _CELL_W:(c + 1) * _CELL_W].sum())
        if fill == 0:
            continue
        tag = "SOLID(skip)" if fill >= _SOLID_CELL_PIXELS else "partial"
        hits.append(f"c{c}={fill}/48:{tag}")
        if fill < _SOLID_CELL_PIXELS:
            partial_sum += fill
    if hits:
        print(f"row {r}: " + "  ".join(hits))

print(f"\ngraphics pixels = {partial_sum}   text cells = {text_cells}   "
      f"(dominance: graphics-page needs >= {_GRAPHICS_PER_TEXT_CELL} px/text-cell)")
if partial_sum < _GRAPHICS_PAGE_PIXELS:
    verdict = "TEXT (barely any graphics)"
elif partial_sum < _GRAPHICS_PER_TEXT_CELL * text_cells:
    verdict = "TEXT (graphics do not dominate the text)"
else:
    verdict = "BRAILLE (graphics dominate)"
print(f"-> auto picks {verdict}")

Image.fromarray((arr * 255).astype("uint8")).resize((720, 192), Image.NEAREST).save("/tmp/page_graphics.png")
print("saved the GETGRAPHICS plane to /tmp/page_graphics.png")
