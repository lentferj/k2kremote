# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only: no MIDI hardware is ever opened.

from k2000.definitions import Button

from k2kremote.name_cursor import NAME_MAX_LEN, NameCursor, merge_reverse


def test_open_starts_on_first_cell():
    cur = NameCursor()
    cur.open(row=3, origin=16)
    assert cur.active and cur.pos == 0 and cur.screen_col() == 16


def test_advance_and_retreat():
    cur = NameCursor()
    cur.open(3, 16)
    for button in (Button.CursorRight, Button.Clear, Button.SoftD):  # >>> soft key
        assert cur.move(button) is True
    assert cur.pos == 3 and cur.screen_col() == 19
    for button in (Button.CursorLeft, Button.SoftC):  # <<< soft key
        assert cur.move(button) is True
    assert cur.pos == 1


def test_clamped_to_field():
    cur = NameCursor()
    cur.open(3, 16)
    for _ in range(NAME_MAX_LEN + 5):
        cur.move(Button.CursorRight)
    assert cur.pos == NAME_MAX_LEN - 1          # never past the field
    moved = cur.move(Button.CursorRight)
    assert moved is False                        # already at the end
    for _ in range(NAME_MAX_LEN + 5):
        cur.move(Button.CursorLeft)
    assert cur.pos == 0
    assert cur.move(Button.CursorLeft) is False  # already at the start


def test_jump_to_end_uses_name_length():
    cur = NameCursor()
    cur.open(3, 16)
    cur.move(Button.CursorLeftRight, name_len=10)  # "CMI VOICES"
    assert cur.pos == 9                            # last character
    cur.move(Button.CursorLeftRight, name_len=0)   # empty name
    assert cur.pos == 0


def test_typing_and_wheel_do_not_move():
    cur = NameCursor()
    cur.open(3, 16)
    cur.move(Button.CursorRight)
    assert cur.move(Button.Number1) is False  # pad press changes the cell, not pos
    assert cur.pos == 1


def test_set_typed_lands_on_last_cell():
    cur = NameCursor()
    cur.open(3, 16)
    cur.set_typed(len("k2kremote demo"))  # 14 chars
    assert cur.pos == 13


def test_set_typed_is_relative_to_current_cursor():
    cur = NameCursor()
    cur.open(3, 16)
    cur.move(Button.CursorRight)
    cur.move(Button.CursorRight)
    cur.move(Button.CursorRight)  # cursor moved onto cell 3 before typing
    cur.set_typed(len("abc"))     # types abc at cells 3,4,5 -> rests on cell 5
    assert cur.pos == 5


def test_inactive_cursor_is_inert():
    cur = NameCursor()
    assert cur.move(Button.CursorRight) is False
    assert cur.reverse_mask() == []
    cur.open(3, 16)
    cur.close()
    assert not cur.active and cur.move(Button.CursorRight) is False


def test_reverse_mask_marks_only_the_cursor_cell():
    cur = NameCursor()
    cur.open(3, 16)
    cur.move(Button.CursorRight)  # screen col 17
    mask = cur.reverse_mask()
    assert len(mask) == 8 and all(len(row) == 40 for row in mask)
    assert mask[3][17] == "1"
    assert mask[3].count("1") == 1
    assert all("1" not in row for r, row in enumerate(mask) if r != 3)


def test_reverse_mask_empty_when_off_screen():
    cur = NameCursor()
    cur.open(row=3, origin=39)  # last column; advancing leaves the 40-col grid
    cur.move(Button.CursorRight)
    assert cur.reverse_mask() == []


def test_merge_reverse_ors_masks():
    base = ["0010", "0000"]
    overlay = ["1000", "0001"]
    merged = merge_reverse(base, overlay, cols=4)
    assert merged[0] == "1010" and merged[1] == "0001"
    # An empty side is a no-op either way.
    assert merge_reverse([], overlay) is overlay
    assert merge_reverse(base, []) is base
