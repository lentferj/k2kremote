# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Models the hardware-verified K2000 name dialog (probes/, 2026-06-19):
# a pad press resets to the group's first letter then cycles; +/- toggles a
# sticky case; CursorRight/Clear advance; space/punctuation via the alpha wheel.

import pytest

from k2000.definitions import Button

from k2kremote import text_entry as te

PM = ("press", Button.PlusMinus)
RIGHT = ("press", Button.CursorRight)


def n(d):
    return ("press", getattr(Button, f"Number{d}"))


# -- character ring ----------------------------------------------------------
def test_charset_ring():
    assert te.CHARSET[0] == "!" and te.CHARSET[-1] == " "
    assert "z" in te.CHARSET and "{" not in te.CHARSET and "~" not in te.CHARSET
    assert te.char_index(" ") == len(te.CHARSET) - 1


@pytest.mark.parametrize("clicks, expected",
                         [(0, []), (63, [63]), (64, [63, 1]), (-70, [-63, -7])])
def test_chunk_wheel(clicks, expected):
    assert te.chunk_wheel(clicks) == expected and sum(te.chunk_wheel(clicks)) == clicks


# -- offline plan_name (no Clear; reset+cycle; default case lower) -----------
def test_plan_default_case_is_lower():
    assert te.plan_name("a") == [n(1)]            # lowercase: no toggle
    assert te.plan_name("A") == [PM, n(1)]        # uppercase: toggle first


def test_plan_letters_cycle_within_group():
    assert te.plan_name("c") == [n(1), n(1), n(1)]   # a,b,c
    assert te.plan_name("d") == [n(2)]
    assert te.plan_name("z") == [n(9), n(9)]


def test_plan_case_is_sticky():
    # 'a' (lower, no toggle), advance, 'B' (toggle to upper, then b->B = 2 taps)
    assert te.plan_name("aB") == [n(1), RIGHT, PM, n(1), n(1)]


def test_plan_digits_from_zero_button():
    assert te.plan_name("0") == [n(0)]
    assert te.plan_name("5") == [n(0)] * 6


def test_plan_space_via_wheel_from_zero():
    plan = te.plan_name(" ")
    assert plan[0] == n(0)
    assert all(c[0] == "wheel" for c in plan[1:])
    assert sum(c[1] for c in plan[1:]) == te.clicks_between("0", " ")


def test_plan_no_clear_anywhere():
    # Clear advances the cursor on hardware, so it must never appear in a plan.
    plan = te.plan_name("Ab 7c-x")
    assert ("press", Button.Clear) not in plan


def test_plan_punctuation_anchor_then_wheel():
    plan = te.plan_name("-")           # '-' nearest digit anchor is '0'
    assert plan[0] == n(0)
    assert sum(c[1] for c in plan if c[0] == "wheel") == te.clicks_between("0", "-")


def test_unsupported_raises():
    with pytest.raises(te.UnsupportedCharacter):
        te.plan_name("é")


# -- feedback typer against a faithful fake K2000 name dialog -----------------
class FakeK2000Field:
    """Models the hardware-verified name-dialog behaviour for type_name()."""

    def __init__(self, initial="Keys-UC Timeless", case="lower"):
        self.field = list(initial)
        self.cursor = 0
        self.case = case
        self.last = None

    def _set(self, ch):
        while self.cursor >= len(self.field):
            self.field.append(" ")
        self.field[self.cursor] = ch

    def press_button(self, btn):
        if btn in te.PAD_GROUPS:
            group = te.PAD_GROUPS[btn]
            cur = self.field[self.cursor].upper() if self.cursor < len(self.field) else ""
            nxt = group[(group.index(cur) + 1) % len(group)] if (self.last == btn and cur in group) else group[0]
            self._set(nxt.lower() if self.case == "lower" else nxt)
            self.last = btn
        elif btn == Button.Number0:
            cur = self.field[self.cursor] if self.cursor < len(self.field) else ""
            nxt = "0123456789"[("0123456789".index(cur) + 1) % 10] if (self.last == btn and cur in "0123456789") else "0"
            self._set(nxt)
            self.last = btn
        elif btn == Button.PlusMinus:
            c = self.field[self.cursor]
            self.field[self.cursor] = c.lower() if c.isupper() else c.upper()
            self.case = "upper" if self.case == "lower" else "lower"
        elif btn in (Button.CursorRight, Button.Clear):  # both just advance
            self.cursor += 1
            self.last = None

    def alpha_wheel(self, clicks):
        idx = te.CHARSET.find(self.field[self.cursor])
        if idx < 0:
            idx = 0
        self._set(te.CHARSET[max(0, min(len(te.CHARSET) - 1, idx + clicks))])
        self.last = None

    def get_screen_text(self):
        return "\n".join([""] * 3 + ["Program Name:   " + "".join(self.field)] + [""] * 4)

    def typed(self, length):
        return "".join(self.field[:length])


@pytest.mark.parametrize("initial_case", ["lower", "upper"])
@pytest.mark.parametrize("target", ["Ab 7c", "Cab", "K2 Bass", "x-y.z", "ZZ9"])
def test_type_name_lands_target_regardless_of_state(target, initial_case):
    fake = FakeK2000Field(initial="Keys-UC Timeless RAM", case=initial_case)
    te.type_name(fake, target, settle=0)
    assert fake.typed(len(target)) == target


def test_type_name_starts_at_cursor_offset():
    # User parked the cursor mid-name (on the 4th cell) and typed; the new text
    # must land at the cursor, leaving the cells before it untouched. Without the
    # start_col plumbing the feedback reads cell 0 and the name is garbled.
    fake = FakeK2000Field(initial="VOICES", case="upper")
    fake.cursor = 3                       # cursor on the 'C' of VOICES
    te.type_name(fake, "abc", settle=0, start_col=3)
    assert "".join(fake.field[3:6]) == "abc"   # typed at the cursor
    assert "".join(fake.field[:3]) == "VOI"    # prefix left intact


def test_type_name_finds_field_by_name_label():
    assert te._find_name_field(["", "Program Name:   Foo"]) == (1, 16)
    assert te._find_name_field(["no label here"]) == (3, 16)  # fallback
