# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# The naming/cursor model is from the Kurzweil K2vx manual ("Saving and Naming")
# AND verified on real K2000R hardware: the name-edit
# cursor is exposed in neither the ALLTEXT nor the GETGRAPHICS query
# (2026-06-20, probes/p21_name_cursor.py), so it is tracked in software here.
# Button codes come from psobot/k2000's definitions.Button (MIT, Peter Sobot).
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

"""Software model of the K2000 name-edit cursor position.

The K2000R draws the name-editor cursor as a firmware underline exposed in
**neither** the ALLTEXT query (no underscore character, no high-bit attribute)
**nor** the GETGRAPHICS overlay plane — verified live on 2026-06-20
(``probes/p21_name_cursor.py``: the physical underline under a character never
appears in either reply). So its position can't be read back; we mirror the
device's own cursor model in software, advancing it exactly as the front-panel
buttons we send would on the hardware, and draw the underline ourselves.

Movement (hardware-verified naming model — see :mod:`k2kremote.text_entry`):

* ``CursorRight``, ``Clear`` and the dialog's ``>>>`` soft key (SoftD) **advance**
  one cell (``Clear`` advances rather than blanks on this unit);
* ``CursorLeft`` and the ``<<<`` soft key (SoftC) **retreat** one cell;
* ``CursorLeftRight`` (the ``0x1A`` combo code) **jumps to the end** of the name;
* typing a pad character or turning the alpha wheel changes the cell *under* the
  cursor and does **not** move it — you advance explicitly.

A fresh dialog opens with the cursor on the first cell. While a dialog is open
this model tracks every app-driven cursor move, and the app feeds the tracked
offset to :func:`k2kremote.text_entry.type_name` (its ``start_col``) so typing
begins at the cursor cell rather than always at the field's start. (A cursor
moved by a *physical* front-panel press still isn't reflected — the real
position can't be read back.) The cursor is clamped to a :data:`NAME_MAX_LEN`-cell
field.
"""

from __future__ import annotations

from typing import List

from attrs import define

from k2000.definitions import Button

# K2000 object names are up to 16 characters.
NAME_MAX_LEN = 16

# Soft keys (SoftC/SoftD) are the name dialog's <<< / >>> cursor keys; they only
# move the cursor while a name dialog is open, which is exactly when this model
# is active, so mapping them here is safe.
_ADVANCE = frozenset({Button.CursorRight, Button.Clear, Button.SoftD})
_RETREAT = frozenset({Button.CursorLeft, Button.SoftC})
_TO_END = frozenset({Button.CursorLeftRight})


def _clamp(pos: int) -> int:
    return max(0, min(pos, NAME_MAX_LEN - 1))


@define
class NameCursor:
    """Tracks the column of the name-edit cursor while a name dialog is open."""

    active: bool = False
    row: int = 3       # screen text row of the name field
    origin: int = 16   # screen column of the field's first cell
    pos: int = 0       # cursor offset within the field (0-based)

    def open(self, row: int, origin: int, pos: int = 0) -> None:
        """Begin tracking a freshly opened name dialog (cursor on cell ``pos``)."""
        self.active = True
        self.row = row
        self.origin = origin
        self.pos = _clamp(pos)

    def close(self) -> None:
        """Stop tracking once the dialog is gone."""
        self.active = False
        self.pos = 0

    def screen_col(self) -> int:
        """Absolute screen column of the cursor cell."""
        return self.origin + self.pos

    def move(self, button: Button, name_len: int = 0) -> bool:
        """Advance/retreat the cursor for a button we are about to send.

        ``name_len`` (the current name's length) is used only by the
        jump-to-end combo. Returns ``True`` if the position actually changed, so
        the caller can re-render immediately without waiting for a device frame.
        """
        if not self.active:
            return False
        before = self.pos
        if button in _ADVANCE:
            self.pos = _clamp(self.pos + 1)
        elif button in _RETREAT:
            self.pos = _clamp(self.pos - 1)
        elif button in _TO_END:
            self.pos = _clamp(max(0, name_len - 1))
        return self.pos != before

    def set_typed(self, length: int) -> None:
        """Place the cursor where :func:`type_name` leaves it: the last typed cell.

        ``type_name`` starts at the current cursor cell and advances one cell per
        character, so after typing ``length`` characters the cursor rests
        ``length - 1`` cells further along — relative to where it began, not from
        the field's start.
        """
        if self.active:
            self.pos = _clamp(self.pos + max(0, length - 1))

    def reverse_mask(self, rows: int = 8, cols: int = 40) -> List[str]:
        """A reverse-video mask (the shape the app's renderers already consume)
        with a single ``"1"`` at the cursor cell, or ``[]`` when inactive or the
        cell is off-screen."""
        if not self.active:
            return []
        r, c = self.row, self.screen_col()
        if not (0 <= r < rows and 0 <= c < cols):
            return []
        mask = ["0" * cols for _ in range(rows)]
        mask[r] = "0" * c + "1" + "0" * (cols - c - 1)
        return mask


def merge_reverse(base: List[str], overlay: List[str], cols: int = 40) -> List[str]:
    """OR two per-row reverse masks cell-by-cell (either may be empty or ragged).

    Lets the software cursor mask be layered onto whatever reverse-video cells
    the device itself reported, without either clobbering the other.
    """
    if not overlay:
        return base
    if not base:
        return overlay
    rows = max(len(base), len(overlay))
    out: List[str] = []
    for r in range(rows):
        a = base[r] if r < len(base) else ""
        b = overlay[r] if r < len(overlay) else ""
        width = max(len(a), len(b), cols)
        a, b = a.ljust(width, "0"), b.ljust(width, "0")
        out.append("".join("1" if (a[i] == "1" or b[i] == "1") else "0"
                           for i in range(width)))
    return out
