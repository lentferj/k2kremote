# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# Renders via psobot/k2000's image.generate_image / upscale_image (MIT, Peter
# Sobot) — a runtime dependency, not copied. Pillow is imported lazily so it is
# only required when actually saving a screenshot.
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

"""Save a captured K2000 screen as a high-fidelity PNG.

The braille mirror is for the terminal; for sharing or documenting a patch a
true-to-hardware image is nicer. We reuse ``psobot/k2000``'s ``image`` module
(the same decoder DESIGN.md points at) to draw the 240x64 pixel layer with the
text overlay in the LCD's blue/amber palette, optionally upscaled.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from k2kremote.refresh import Frame

# Native LCD geometry (matches k2kremote.braille).
_SCREEN_W = 240
_SCREEN_H = 64


def render_image(frame: "Frame", *, scale: int = 4):
    """Return a PIL image of ``frame`` (graphics + text), upscaled by ``scale``.

    A text-only frame (fast ALLTEXT mode, ``pixels is None``) is rendered over a
    blank pixel layer so the text still appears.
    """
    from k2000.image import generate_image, upscale_image  # lazy: needs Pillow

    if frame.pixels is None:
        pixels = np.zeros((_SCREEN_W, _SCREEN_H), dtype=np.uint8)
    else:
        pixels = np.asarray(frame.pixels)

    # Clip to the real 8x40 text grid — generate_image indexes off the 240x64
    # canvas if a row is wider than the screen or there are more than 8 rows.
    text_rows = [row[:40] for row in list(frame.text_rows)[:8]]
    image = generate_image(pixels, text_rows)
    if scale and scale > 1:
        image = upscale_image(image, scale)
    return image


def live_image(frame: "Frame", *, scale: int = 4):
    """A fast PIL image for the live mirror: composite at native res, then a
    nearest-neighbour upscale (crisp pixels, ~1 ms vs the fancy upscaler's ~80)."""
    from PIL import Image

    image = render_image(frame, scale=1)  # native 240x64 composite
    if scale and scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
    return image


def save_png(frame: "Frame", path: str, *, scale: int = 4) -> str:
    """Render ``frame`` and write it to ``path`` as a PNG. Returns ``path``."""
    render_image(frame, scale=scale).save(path)
    return path


def default_filename(prefix: str = "k2kremote") -> str:
    """A timestamped screenshot filename, e.g. ``k2kremote-20260618-100532.png``."""
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}.png"
