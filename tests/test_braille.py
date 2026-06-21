# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

import numpy as np
import pytest

from k2kremote import braille


def test_dimensions_blank_screen():
    blank = np.zeros((braille.SCREEN_H, braille.SCREEN_W), dtype=bool)
    lines = braille.render_lines(blank)
    assert len(lines) == braille.BRAILLE_ROWS == 16
    assert all(len(line) == braille.BRAILLE_COLS == 120 for line in lines)
    # Every cell is the empty braille pattern U+2800.
    assert set("".join(lines)) == {chr(braille.BRAILLE_BASE)}


@pytest.mark.parametrize(
    "row, col, expected_bit",
    [
        (0, 0, 0x01),  # dot 1
        (1, 0, 0x02),  # dot 2
        (2, 0, 0x04),  # dot 3
        (3, 0, 0x40),  # dot 7
        (0, 1, 0x08),  # dot 4
        (1, 1, 0x10),  # dot 5
        (2, 1, 0x20),  # dot 6
        (3, 1, 0x80),  # dot 8
    ],
)
def test_single_pixel_maps_to_correct_dot(row, col, expected_bit):
    frame = np.zeros((braille.SCREEN_H, braille.SCREEN_W), dtype=bool)
    frame[row, col] = True
    code = braille.to_codes(frame)[0, 0]
    assert code == braille.BRAILLE_BASE + expected_bit


def test_full_cell_is_solid_block():
    frame = np.zeros((braille.SCREEN_H, braille.SCREEN_W), dtype=bool)
    frame[0:4, 0:2] = True  # fill the top-left braille cell entirely
    code = braille.to_codes(frame)[0, 0]
    assert code == braille.BRAILLE_BASE + 0xFF  # U+28FF — all eight dots


def test_orientation_is_normalized():
    """A (240, 64) buffer (to_pixel_array's shape) renders like its transpose."""
    wide = np.zeros((braille.SCREEN_W, braille.SCREEN_H), dtype=bool)
    wide[0, 0] = True  # width-major: column 0, row 0
    tall = wide.T
    assert braille.render(wide) == braille.render(tall)
    assert braille.to_codes(wide)[0, 0] == braille.BRAILLE_BASE + 0x01


def test_to_pixel_array_shape_round_trips():
    """The renderer accepts exactly what psobot/k2000 yields, uint8 0/255."""
    arr = np.zeros((braille.SCREEN_W, braille.SCREEN_H), dtype=np.uint8)
    arr[0, 0] = 0xFF
    lines = braille.render_lines(arr)
    assert lines[0][0] == chr(braille.BRAILLE_BASE + 0x01)


def test_partial_buffer_is_padded_not_crashing():
    small = np.ones((4, 4), dtype=bool)
    lines = braille.render_lines(small)
    assert len(lines) == 16 and len(lines[0]) == 120


def test_text_plane_is_composited_when_rows_given():
    # Graphics empty -> braille blank; but with a text row, the composited mirror
    # must show the text (Disk/Master/edit pages live in the text plane).
    blank = np.zeros((braille.SCREEN_W, braille.SCREEN_H), dtype=np.uint8)  # (240,64)
    graphics_only = braille.render(blank)
    composited = braille.render(blank, ["DISK MODE"])
    assert set(graphics_only) == {"\n", chr(braille.BRAILLE_BASE)}  # blank
    assert composited != graphics_only  # text now visible
    assert any(c != chr(braille.BRAILLE_BASE) for c in composited.split("\n")[0])


def test_quadrant_dimensions_and_solid_block():
    frame = np.zeros((braille.SCREEN_H, braille.SCREEN_W), dtype=bool)
    lines = braille.render_quadrant(frame).split("\n")
    assert len(lines) == braille.QUAD_ROWS == 32
    assert all(len(line) == braille.QUAD_COLS == 120 for line in lines)
    assert set("".join(lines)) == {" "}  # blank -> all spaces
    # A full 2x2 cell becomes a solid block.
    frame[0:2, 0:2] = True
    assert braille.render_quadrant(frame).split("\n")[0][0] == "█"


def test_halfblock_dimensions_and_aspect():
    frame = np.zeros((braille.SCREEN_H, braille.SCREEN_W), dtype=bool)
    lines = braille.render_halfblock(frame).split("\n")
    assert len(lines) == braille.HALF_ROWS == 32
    assert all(len(line) == braille.HALF_COLS == 240 for line in lines)
    # 240 cols x 32 rows -> ~3.75:1 with 1:2 cells, matching the LCD.
    frame[0:2, 0] = True  # top+bottom of one column -> full block
    assert braille.render_halfblock(frame).split("\n")[0][0] == "█"
    frame[:] = False
    frame[0, 0] = True    # top pixel only -> upper half block
    assert braille.render_halfblock(frame).split("\n")[0][0] == "▀"


def test_width_hint():
    assert braille.width_hint(200) is None
    assert braille.width_hint(braille.BRAILLE_COLS) is None
    assert braille.width_hint(None) is None
    assert "widen" in braille.width_hint(80)


def test_demo_renders():
    out = braille._demo()
    assert out.count("\n") == braille.BRAILLE_ROWS - 1
