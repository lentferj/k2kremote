# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# The naming model is from the Kurzweil K2vx manual ("The Alphanumeric Pad" /
# "Saving and Naming") AND verified on real K2000R hardware on 2026-06-19
# (see probes/, TODO.md, docs/RESOLUTION_NOTES.md). Button codes come from the
# vendored k2000.definitions.Button (psobot/k2000, MIT, Peter Sobot).
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

"""Phase 2: smart alphanumeric entry, verified on hardware.

The K2000 names objects with its **alphanumeric pad**, multi-tap style. The
hardware-verified behaviour (2026-06-19) of a name dialog is:

* Pressing a pad button **resets** the character under the cursor to that
  button's first letter, in the current case; pressing the **same** button again
  **cycles** within the group (``K → A → B → C`` for button 1). Different button
  or a cursor move starts fresh.
* ``0`` resets to ``0`` then cycles ``0 1 2 … 9``.
* ``+/-`` (``Button.PlusMinus``) toggles the cursored character's case and flips
  a **sticky global case** — whose state at dialog-open is *not* reliable.
* ``CursorRight`` advances the cursor. **``Clear`` also just advances** (it does
  *not* blank the character on the tested unit), so it is not used here.
* There is no pad key for space or punctuation: reset to a known character
  (a digit) and nudge the **alpha wheel** along the ring (:data:`CHARSET`).

Because the global case is stateful, **fully offline entry can't guarantee
case** — so the robust path is :func:`type_name`, which reads each position back
over MIDI and self-corrects letter, case, and (for space/punctuation) wheel
position. :func:`plan_name` is the offline reference plan (used in tests and for
documentation), correct given a known ``start_case`` and fresh positions.
"""

from __future__ import annotations

import string
import time
from typing import Callable, List, Optional, Tuple

from k2000.definitions import Button

# The alpha-wheel character ring (K2vx manual "Saving and Naming"): ASCII
# 0x21..0x7A ('!'..'z') followed by space. Space is LAST; '{ | } ~' excluded.
CHARSET: str = "".join(chr(code) for code in range(0x21, 0x7B)) + " "

# A single PANEL alpha-wheel event encodes clicks in -64..63; cap at 63.
MAX_CLICKS_PER_EVENT = 63

# Alphanumeric-pad letter groups (manual keypad legend, verified).
PAD_GROUPS = {
    Button.Number1: "ABC", Button.Number2: "DEF", Button.Number3: "GHI",
    Button.Number4: "JKL", Button.Number5: "MNO", Button.Number6: "PQR",
    Button.Number7: "STU", Button.Number8: "VWX", Button.Number9: "YZ",
}
_DIGITS = "0123456789"
# letter -> (button, taps); e.g. "C" -> (Number1, 3).
_LETTER_TAPS = {
    letter: (button, index + 1)
    for button, group in PAD_GROUPS.items()
    for index, letter in enumerate(group)
}
# Directly-typeable anchors used to reach punctuation via the wheel.
_ANCHORS = _DIGITS + string.ascii_uppercase + string.ascii_lowercase + " "

CASE_UPPER = "upper"
CASE_LOWER = "lower"

# A worker command: ("wheel", clicks) or ("press", Button).
Command = Tuple[str, object]


class UnsupportedCharacter(ValueError):
    """Raised when a target character is not in :data:`CHARSET`."""


class NameEntryFailed(RuntimeError):
    """Raised when a cell never showed the wanted character.

    :func:`type_name` reads every position back, so it *knows* when a cell is
    wrong — and until now it returned quietly anyway, leaving a garbled name on
    the device and reporting success. A name that is silently wrong is worse
    than one that failed loudly: the caller has already moved on to Save."""


# --- pure helpers -----------------------------------------------------------
def is_supported(text: str) -> bool:
    """True if every character of ``text`` can be entered on the K2000."""
    return all(ch in CHARSET for ch in text)


def char_index(ch: str) -> int:
    """Position of ``ch`` in the alpha-wheel character ring."""
    pos = CHARSET.find(ch)
    if pos < 0:
        raise UnsupportedCharacter(f"character {ch!r} is not in the K2000 charset")
    return pos


def clicks_between(current: str, target: str) -> int:
    """Signed wheel clicks to turn from ``current`` to ``target`` (no wrap)."""
    return char_index(target) - char_index(current)


def chunk_wheel(clicks: int) -> List[int]:
    """Split a click count into per-event chunks within the PANEL range."""
    chunks: List[int] = []
    while clicks != 0:
        step = max(-MAX_CLICKS_PER_EVENT, min(MAX_CLICKS_PER_EVENT, clicks))
        chunks.append(step)
        clicks -= step
    return chunks


def _passes(cycle: int, override: Optional[int]) -> int:
    """How many presses may be needed to land a character on a multi-tap pad.

    ``cycle`` is the length of that pad's ring, and the bound must be derived
    from it rather than picked: the first press may be a *reset* to the ring's
    first entry (the pad only advances when it was also the previous button), so
    the worst case is one reset plus a full lap. Hence ``cycle + 1``.

    The digit branch used a flat 12 against a ring of 10. That happened to be
    enough, which is the problem — nothing tied the number to the ring, so
    tuning it down to 8 for speed would have broken 8 and 9 only, silently, and
    only on names containing them."""
    return cycle + 1 if override is None else override


def _nearest_anchor(target: str) -> str:
    """The directly-typeable character closest to ``target`` in the ring."""
    target_index = char_index(target)
    return min(_ANCHORS, key=lambda anchor: abs(char_index(anchor) - target_index))


# --- offline plan (reference / tests) ---------------------------------------
def _letter_presses(ch: str, case: str) -> Tuple[List[Command], str]:
    button, taps = _LETTER_TAPS[ch.upper()]
    commands: List[Command] = []
    need = CASE_LOWER if ch.islower() else CASE_UPPER
    if need != case:
        commands.append(("press", Button.PlusMinus))
        case = need
    commands.extend([("press", button)] * taps)
    return commands, case


def _wheel_to(anchor: str, target: str) -> List[Command]:
    return [("wheel", c) for c in chunk_wheel(clicks_between(anchor, target))]


def plan_name(target: str, *, start_case: str = CASE_LOWER) -> List[Command]:
    """Offline command plan to type ``target`` into a fresh name field.

    No ``Clear`` (it advances, not blanks); multi-tap resets then cycles. Space
    and punctuation reach the wheel from a digit anchor. Correct given a known
    ``start_case`` and reset-on-fresh positions — the hardware path
    (:func:`type_name`) instead verifies each position and needs no such
    assumption.
    """
    if not is_supported(target):
        bad = next(ch for ch in target if ch not in CHARSET)
        raise UnsupportedCharacter(f"cannot type {bad!r}: not in the K2000 charset")

    case = start_case
    commands: List[Command] = []
    for i, ch in enumerate(target):
        if ch == " ":
            commands.append(("press", Button.Number0))
            commands.extend(_wheel_to("0", " "))
        elif ch in _DIGITS:
            commands.extend([("press", Button.Number0)] * (int(ch) + 1))
        elif ch.isalpha():
            presses, case = _letter_presses(ch, case)
            commands.extend(presses)
        else:  # punctuation: nearest pad anchor, then wheel
            anchor = _nearest_anchor(ch)
            if anchor.isalpha():
                presses, case = _letter_presses(anchor, case)
                commands.extend(presses)
            else:
                commands.extend([("press", Button.Number0)] * (int(anchor) + 1))
            commands.extend(_wheel_to(anchor, ch))
        if i < len(target) - 1:
            commands.append(("press", Button.CursorRight))
    return commands


# --- hardware feedback-driven typer -----------------------------------------
def _find_name_field(rows: List[str]) -> Tuple[int, int]:
    """Locate (row, col) of the editable name from a screen, by its "Name:" label."""
    for r, row in enumerate(rows):
        idx = row.find("Name:")
        if idx >= 0:
            col = idx + len("Name:")
            while col < len(row) and row[col] == " ":
                col += 1
            return r, col
    return 3, 16  # observed default (Program rename dialog)


def home_cursor(bridge, width: int = 16, *, settle: float = 0.28) -> None:
    """Drive the name cursor to offset 0, so ``start_col=0`` is actually true.

    ``type_name`` verifies each character at ``name_col + start_col + col``, so a
    caller that does not know the cursor's real offset garbles the name: the letter
    lands at one column while the check reads another, the correction loop never
    matches, and every character is left on its group's *first* letter. Typing
    ``TEST`` into a field whose cursor sat one place right produced ``SDSS`` —
    S, D, S, S being the first letters of the groups for T, E, S, T.

    ``CursorLeft`` **clamps** at the field start rather than wrapping, so pressing
    it ``width`` times is both sufficient and idempotent, and needs no knowledge of
    where the cursor actually was. That matters because the K2000 does not report
    the name cursor over MIDI at all (RESOLUTION_NOTES §6): it cannot be read, only
    driven to a known place.

    Call this before :func:`type_name` on any dialog you did not just open — in
    particular after ``Delete`` presses, which move it.
    """
    for _ in range(max(1, width)):
        bridge.press_button(Button.CursorLeft)
        time.sleep(settle)


def type_name(bridge, target: str, *, settle: float = 0.55,
              name_row: Optional[int] = None, name_col: Optional[int] = None,
              start_col: int = 0, max_passes: Optional[int] = None) -> None:
    """Type ``target`` into the K2000's *open* name dialog, with feedback.

    Reads each position back over MIDI and corrects the letter, its case, and
    (for space/punctuation) the wheel position — so it is robust to the unknown
    global case state and to whatever the field already contained. ``bridge``
    must expose ``press_button``, ``alpha_wheel`` and ``get_screen_text`` and is
    driven synchronously, so call this from the MIDI worker thread.

    ``start_col`` is the field offset (0-based) the device cursor is parked on
    when entry begins; typing proceeds from there and each position is read back
    at ``name_col + start_col + i``. The caller must pass the cursor's real
    offset (the app threads :class:`~k2kremote.name_cursor.NameCursor`'s tracked
    position) — otherwise the feedback reads land on the wrong cells and the
    multi-tap correction garbles the name. Defaults to ``0`` (cursor at the
    field's first cell).

    ``max_passes`` overrides the per-pad press budget, which by default is
    derived from the pad's own ring (see :func:`_passes`); leave it alone unless
    a device is observed needing more.

    Raises :class:`NameEntryFailed` if a cell never shows what was asked for.
    Since every position is read back, "wrong" is always *known* here — the only
    question is whether the caller hears about it, and a half-typed name that
    reports success gets saved to the device under that name.
    """
    if not is_supported(target):
        bad = next(ch for ch in target if ch not in CHARSET)
        raise UnsupportedCharacter(f"cannot type {bad!r}: not in the K2000 charset")

    if name_row is None or name_col is None:
        rows = bridge.get_screen_text().split("\n")
        dr, dc = _find_name_field(rows)
        name_row = dr if name_row is None else name_row
        name_col = dc if name_col is None else name_col

    def press(button: Button) -> None:
        bridge.press_button(button)
        time.sleep(settle)

    def wheel(clicks: int) -> None:
        bridge.alpha_wheel(clicks)
        time.sleep(settle)

    def shown(col: int) -> str:
        return bridge.get_screen_text().split("\n")[name_row][name_col + start_col + col]

    for i, ch in enumerate(target):
        _type_char(press, wheel, shown, i, ch, max_passes)
        if i < len(target) - 1:
            press(Button.CursorRight)


def _type_char(press: Callable, wheel: Callable, shown: Callable,
               col: int, ch: str, max_passes: int) -> None:
    if ch == " ":
        press(Button.Number0)                       # known '0'
        for c in chunk_wheel(clicks_between("0", " ")):
            wheel(c)
        return
    if ch in _DIGITS:
        # Number0 cycles 0..9, so the bound is the ring, not a round number.
        for _ in range(_passes(len(_DIGITS), max_passes)):
            press(Button.Number0)                   # reset to 0, then cycle
            if shown(col) == ch:
                return
        raise NameEntryFailed(
            f"cell {col} still shows {shown(col)!r} after cycling the digit pad "
            f"for {ch!r}")
    if ch.isalpha():
        button, _ = _LETTER_TAPS[ch.upper()]
        for _ in range(_passes(len(PAD_GROUPS[button]), max_passes)):
            press(button)                           # reset, then cycle to it
            if shown(col).upper() == ch.upper():
                break
        else:
            raise NameEntryFailed(
                f"cell {col} still shows {shown(col)!r} after cycling "
                f"{button.name} for {ch!r}")
        if shown(col) != ch:                         # fix case (sticky toggle)
            press(Button.PlusMinus)
        if shown(col) != ch:
            raise NameEntryFailed(
                f"cell {col} shows {shown(col)!r}, not {ch!r}: the case toggle "
                f"did not take")
        return
    # punctuation: type the nearest pad char, then wheel to it
    anchor = _nearest_anchor(ch)
    _type_char(press, wheel, shown, col, anchor, max_passes)
    for c in chunk_wheel(clicks_between(anchor, ch)):
        wheel(c)
