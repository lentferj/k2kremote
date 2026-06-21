# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic: renders frames to PNG in a temp dir, no hardware.

import numpy as np
import pytest

from k2kremote import screenshot
from k2kremote.refresh import Frame

PIL = pytest.importorskip("PIL", reason="Pillow not installed")
from PIL import Image  # noqa: E402


def _frame():
    pixels = np.zeros((240, 64), dtype=np.uint8)
    pixels[0, :] = pixels[-1, :] = 0xFF  # a border so it's not blank
    return Frame(pixels=pixels, text_rows=["Program", "", "", "", "", "", "", "ABCDEF"])


def test_render_image_dimensions_scale():
    image = screenshot.render_image(_frame(), scale=4)
    assert image.size == (240 * 4, 64 * 4)


def test_save_png_writes_a_valid_file(tmp_path):
    out = tmp_path / "shot.png"
    returned = screenshot.save_png(_frame(), str(out), scale=2)
    assert returned == str(out)
    assert out.exists() and out.stat().st_size > 0
    with Image.open(out) as img:
        assert img.format == "PNG"
        assert img.size == (240 * 2, 64 * 2)


def test_text_only_frame_renders_over_blank(tmp_path):
    out = tmp_path / "text.png"
    screenshot.save_png(Frame(pixels=None, text_rows=["Hello"]), str(out), scale=1)
    assert out.exists()


def test_overlong_rows_are_clipped_not_crashing(tmp_path):
    # >40-char rows and >8 rows would index off generate_image's canvas.
    frame = Frame(pixels=np.zeros((240, 64), dtype=np.uint8),
                  text_rows=["X" * 60] * 10)
    out = tmp_path / "wide.png"
    screenshot.save_png(frame, str(out), scale=1)
    assert out.exists()


def test_default_filename_pattern():
    name = screenshot.default_filename()
    assert name.startswith("k2kremote-") and name.endswith(".png")
