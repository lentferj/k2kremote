# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# Consumes the 240x64 pixel array produced at runtime by psobot/k2000's
# ScreenReply.to_pixel_array (MIT, Peter Sobot) — a dependency, not copied.
#
# k2kremote is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# k2kremote is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Render the K2000's 240x64 LCD pixel buffer as Unicode braille.

The K2000 ``GETGRAPHICS`` reply decodes (via ``psobot/k2000``'s
``ScreenReply.to_pixel_array``) into a 240x64 array of on/off pixels. Braille
cells pack a 2x4 grid of dots, so the whole screen maps 1:1 onto a **120x16**
character mirror — every cursor box and envelope curve the hardware draws.

Braille dot numbering inside one cell (Unicode block U+2800)::

    1 4      bit 0x01  0x08
    2 5      bit 0x02  0x10
    3 6      bit 0x04  0x20
    7 8      bit 0x40  0x80

So a cell covers pixel rows ``r..r+3`` and columns ``c..c+1``; the code point is
``0x2800 + OR(dot bits for every lit pixel)``.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Union

import numpy as np

# Native LCD geometry.
SCREEN_W = 240
SCREEN_H = 64

# A braille cell is 2 dots wide, 4 dots tall.
CELL_W = 2
CELL_H = 4

# 1:1 mirror dimensions.
BRAILLE_COLS = SCREEN_W // CELL_W  # 120
BRAILLE_ROWS = SCREEN_H // CELL_H  # 16

BRAILLE_BASE = 0x2800

# Quadrant-block alternative: 2x2 px per cell (solid blocks, no dot gaps) -> a
# 120x32 mirror. Indexed by (TL<<3 | TR<<2 | BL<<1 | BR).
QUAD_COLS = SCREEN_W // 2  # 120
QUAD_ROWS = SCREEN_H // 2  # 32
_QUADRANTS = " ▗▖▄▝▐▞▟▘▚▌▙▀▜▛█"

# Half-block alternative: 1 px wide x 2 px tall per cell -> a 240x32 mirror.
# Solid blocks AND the correct wide 3.75:1 aspect (matches the hardware LCD);
# needs a 240-column terminal. Indexed by (top<<1 | bottom).
HALF_COLS = SCREEN_W       # 240
HALF_ROWS = SCREEN_H // 2  # 32
_HALFBLOCKS = " ▄▀█"

# Dot-bit weight for each (row-in-cell, col-in-cell) position. Indexed [dy][dx].
_DOT_WEIGHTS = np.array(
    [
        [0x01, 0x08],
        [0x02, 0x10],
        [0x04, 0x20],
        [0x40, 0x80],
    ],
    dtype=np.uint16,
)

PixelInput = Union[np.ndarray, Sequence[Sequence[int]]]


def _normalize(pixels: PixelInput) -> np.ndarray:
    """Coerce an LCD pixel buffer to a boolean ``(SCREEN_H, SCREEN_W)`` array.

    Accepts either orientation: ``to_pixel_array`` yields ``(240, 64)`` (width
    major), while the on-screen layout is ``(64, 240)`` (rows x cols). We pick
    the row-major orientation — the taller axis becomes columns — matching the
    same heuristic ``psobot/k2000``'s ``image.generate_image`` uses.
    """
    arr = np.asarray(pixels)
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D pixel buffer, got shape {arr.shape}")

    # Orient to (rows, cols) = (height, width): width is the longer axis.
    if arr.shape[0] > arr.shape[1]:
        arr = arr.T

    return arr.astype(bool)


def _fit(arr: np.ndarray) -> np.ndarray:
    """Crop/pad a boolean array to exactly ``(SCREEN_H, SCREEN_W)``.

    Real devices always return the full 240x64; this only guards synthetic or
    partial buffers so the renderer never raises mid-refresh.
    """
    h, w = arr.shape
    if (h, w) == (SCREEN_H, SCREEN_W):
        return arr
    fitted = np.zeros((SCREEN_H, SCREEN_W), dtype=bool)
    fitted[: min(h, SCREEN_H), : min(w, SCREEN_W)] = arr[:SCREEN_H, :SCREEN_W]
    return fitted


def _composite(pixels: PixelInput, text_rows: Sequence[str]) -> np.ndarray:
    """Overlay the ALLTEXT plane onto the GETGRAPHICS plane → ``(64, 240)`` bool.

    The K2000 LCD shows two planes at once: graphics (GETGRAPHICS) and text
    (ALLTEXT). GETGRAPHICS alone misses everything drawn in the text plane —
    most of Disk/Master/edit pages, the status bar and soft-key labels. We reuse
    psobot/k2000's ``image.generate_image`` (the same compositor the PNG
    screenshots use, with correct reverse-video inversion) and threshold it back
    to 1 bit. Falls back to graphics-only if anything goes wrong.
    """
    try:
        from k2000.image import generate_image, WHITE

        rows = [(row or "")[:SCREEN_W // 6] for row in list(text_rows)[:SCREEN_H // 8]]
        image = generate_image(np.asarray(pixels), rows)
        rgb = np.asarray(image)  # (64, 240, 3); lit pixels are WHITE
        return _fit(np.all(rgb[..., :3] == np.array(WHITE[:3]), axis=-1))
    except Exception:
        return _fit(_normalize(pixels))


def to_codes(pixels: PixelInput,
             text_rows: Optional[Sequence[str]] = None) -> np.ndarray:
    """Return the ``(16, 120)`` braille code points for a buffer.

    If ``text_rows`` is given, the text plane is composited on first so the
    mirror shows everything the hardware does (see :func:`_composite`).
    """
    arr = _composite(pixels, text_rows) if text_rows else _fit(_normalize(pixels))

    # (16, 4, 120, 2): block-row, dot-row, block-col, dot-col.
    cells = arr.reshape(BRAILLE_ROWS, CELL_H, BRAILLE_COLS, CELL_W)

    # Weight each lit dot and OR them together per cell. Summation is equivalent
    # to bitwise-OR here because every (dy, dx) slot owns a distinct bit.
    weighted = cells * _DOT_WEIGHTS[np.newaxis, :, np.newaxis, :]
    codes = weighted.sum(axis=(1, 3)).astype(np.uint16)
    return codes + BRAILLE_BASE


def render(pixels: PixelInput,
           text_rows: Optional[Sequence[str]] = None) -> str:
    """Render a 240x64 buffer as a 120x16 braille string (text plane composited
    in when ``text_rows`` is supplied)."""
    codes = to_codes(pixels, text_rows)
    return "\n".join("".join(chr(c) for c in row) for row in codes)


def render_lines(pixels: PixelInput,
                 text_rows: Optional[Sequence[str]] = None) -> List[str]:
    """Like :func:`render` but return the 16 rows as a list of strings."""
    codes = to_codes(pixels, text_rows)
    return ["".join(chr(c) for c in row) for row in codes]


def render_quadrant(pixels: PixelInput,
                    text_rows: Optional[Sequence[str]] = None) -> str:
    """Render a 240x64 buffer as a 120x32 **quadrant-block** string.

    Solid 2x2 cells (no braille dot-gaps), so it reads cleaner — at the cost of
    twice the rows. The text plane is composited in when ``text_rows`` given.
    """
    arr = _composite(pixels, text_rows) if text_rows else _fit(_normalize(pixels))
    cells = arr.reshape(QUAD_ROWS, 2, QUAD_COLS, 2).astype(int)
    idx = (cells[:, 0, :, 0] * 8 + cells[:, 0, :, 1] * 4
           + cells[:, 1, :, 0] * 2 + cells[:, 1, :, 1])
    return "\n".join("".join(_QUADRANTS[i] for i in row) for row in idx)


def render_halfblock(pixels: PixelInput,
                     text_rows: Optional[Sequence[str]] = None) -> str:
    """Render a 240x64 buffer as a 240x32 **half-block** string.

    Solid cells like quadrant, but 1 px wide each, so the mirror keeps the
    hardware LCD's wide 3.75:1 aspect ratio. Needs a 240-column terminal.
    """
    arr = _composite(pixels, text_rows) if text_rows else _fit(_normalize(pixels))
    cells = arr.reshape(HALF_ROWS, 2, HALF_COLS).astype(int)
    idx = cells[:, 0, :] * 2 + cells[:, 1, :]
    return "\n".join("".join(_HALFBLOCKS[i] for i in row) for row in idx)


def width_hint(terminal_width: Optional[int]) -> Optional[str]:
    """Return a 'widen your terminal' hint, or ``None`` if there's room.

    1:1 braille needs at least :data:`BRAILLE_COLS` columns. ``None`` width
    (e.g. output not a TTY) is treated as wide enough.
    """
    if terminal_width is None or terminal_width >= BRAILLE_COLS:
        return None
    return (
        f"terminal is {terminal_width} cols; need {BRAILLE_COLS} for a "
        f"pixel-accurate mirror — widen the window"
    )


def _demo() -> str:
    """A standalone smoke test: render a frame with a border and an X."""
    frame = np.zeros((SCREEN_H, SCREEN_W), dtype=bool)
    frame[0, :] = frame[-1, :] = True
    frame[:, 0] = frame[:, -1] = True
    for i in range(min(SCREEN_H, SCREEN_W)):
        frame[i, int(i * SCREEN_W / SCREEN_H)] = True
        frame[i, SCREEN_W - 1 - int(i * SCREEN_W / SCREEN_H)] = True
    return render(frame)


if __name__ == "__main__":
    print(_demo())
