# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# Button codes come from psobot/k2000's definitions.Button (MIT, Peter Sobot),
# a runtime dependency. The terminal-key -> K2000-button mapping is ours and
# follows the table in DESIGN.md.
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

"""Map Textual key events onto K2000 front-panel actions.

A terminal keypress resolves to a :class:`KeyAction`, which is either a single
front-panel **button** press or an **alpha-wheel** turn (signed click count).
The table follows DESIGN.md; Textual's portable key model (real ``f1``..``f8``,
``alt+p`` and ``ctrl+up`` chords) is the reason that spec is achievable across
Linux / macOS / Windows terminals.

The dangerous object commands (DEL / DELBANK / MOVEBANK) are deliberately
**absent** from this table — they must never be reachable from a keystroke.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from attrs import frozen

from k2000.definitions import Button


@frozen
class KeyAction:
    """A resolved keypress: press ``button`` or turn the wheel ``wheel`` clicks."""

    label: str
    button: Optional[Button] = None
    wheel: int = 0

    @property
    def is_wheel(self) -> bool:
        return self.button is None


def _button(label: str, button: Button) -> KeyAction:
    return KeyAction(label=label, button=button)


def _wheel(label: str, clicks: int) -> KeyAction:
    return KeyAction(label=label, wheel=clicks)


# Terminal key (Textual `event.key`) -> action. Keys are Textual's normalized
# names; a few have aliases (e.g. "+"/"plus") so both spellings resolve.
KEYMAP: Dict[str, KeyAction] = {
    # Soft keys (the live F1-F6 label bar comes from the bottom screen row).
    "f1": _button("SoftA", Button.SoftA),
    "f2": _button("SoftB", Button.SoftB),
    "f3": _button("SoftC", Button.SoftC),
    "f4": _button("SoftD", Button.SoftD),
    "f5": _button("SoftE", Button.SoftE),
    "f6": _button("SoftF", Button.SoftF),
    "f7": _button("Edit", Button.Edit),
    "f8": _button("Exit", Button.Exit),
    # Terminal-safe alternates for the F-keys (some terminals, e.g. LXTerminal,
    # intercept F1/F10/F11…). The home-row run a s d f g h mirrors soft A-F
    # (contiguous on both QWERTY and QWERTZ); Ctrl+E/Ctrl+X = Edit/Exit.
    "a": _button("SoftA", Button.SoftA),
    "s": _button("SoftB", Button.SoftB),
    "d": _button("SoftC", Button.SoftC),
    "f": _button("SoftD", Button.SoftD),
    "g": _button("SoftE", Button.SoftE),
    "h": _button("SoftF", Button.SoftF),
    "ctrl+e": _button("Edit", Button.Edit),
    "ctrl+x": _button("Exit", Button.Exit),
    # Cursor.
    "up": _button("Cursor↑", Button.CursorUp),
    "down": _button("Cursor↓", Button.CursorDown),
    "left": _button("Cursor←", Button.CursorLeft),
    "right": _button("Cursor→", Button.CursorRight),
    # Editing / entry.
    "enter": _button("Enter", Button.Enter),
    "escape": _button("Exit", Button.Exit),      # Esc backs out (like the EXIT button)
    "delete": _button("Cancel", Button.Cancel),  # Cancel moved off Esc
    "backspace": _button("Clear", Button.Clear),
    # Digits.
    "0": _button("0", Button.Number0),
    "1": _button("1", Button.Number1),
    "2": _button("2", Button.Number2),
    "3": _button("3", Button.Number3),
    "4": _button("4", Button.Number4),
    "5": _button("5", Button.Number5),
    "6": _button("6", Button.Number6),
    "7": _button("7", Button.Number7),
    "8": _button("8", Button.Number8),
    "9": _button("9", Button.Number9),
    # Value +/- (the panel's Plus/Minus, not numeric sign entry). PageUp/PageDown
    # are equivalents of +/-.
    "plus": _button("Plus", Button.Plus),
    "+": _button("Plus", Button.Plus),
    "pageup": _button("Plus", Button.Plus),
    "minus": _button("Minus", Button.Minus),
    "-": _button("Minus", Button.Minus),
    "pagedown": _button("Minus", Button.Minus),
    # The alphanumeric pad's dedicated +/- key (Button.PlusMinus) is a separate
    # physical button from Plus/Minus above — per the K2vx manual ("The
    # Plus/Minus Buttons"), it's "used primarily for entering negative numeric
    # values and switching from uppercase to lowercase letters". Bound on
    # Shift+- since plain "-" is already Minus/decrement: type "_", "5",
    # Enter to get -5.
    "underscore": _button("+/-", Button.PlusMinus),
    "_": _button("+/-", Button.PlusMinus),
    # Chan / Bank -/+ (the panel's CHAN/BANK pair, doubling as Layer/Zone in the
    # editors). The both-at-once combo (jump bank / Guitar-Wind / select-all) is
    # the K2000's dedicated single code, not two buttons together; it sits on the
    # bracket-adjacent backslash.
    "left_square_bracket": _button("Chan/Bank−", Button.ChanBankDec),
    "[": _button("Chan/Bank−", Button.ChanBankDec),
    "right_square_bracket": _button("Chan/Bank+", Button.ChanBankInc),
    "]": _button("Chan/Bank+", Button.ChanBankInc),
    "backslash": _button("Chan/Bank±", Button.ChanBankIncDec),
    "\\": _button("Chan/Bank±", Button.ChanBankIncDec),
    # Alpha wheel (PageUp/Down are now +/-, so the wheel lives on Ctrl+arrows).
    "ctrl+up": _wheel("Wheel +1", +1),
    "ctrl+down": _wheel("Wheel −1", -1),
    "ctrl+pageup": _wheel("Wheel +5", +5),
    "ctrl+pagedown": _wheel("Wheel −5", -5),
    # Mode buttons (Alt-chords — portable in Textual).
    "alt+p": _button("Program", Button.Program),
    "alt+s": _button("Setup", Button.Setup),
    "alt+q": _button("Quick-Access", Button.QuickAccess),
    "alt+m": _button("Master", Button.Master),
    "alt+i": _button("MIDI", Button.MIDI),
    "alt+d": _button("Disk", Button.Disk),
    "alt+g": _button("Song", Button.Song),
    "alt+e": _button("Effects", Button.Effects),
    # Combo (double-button) functions are triggered by the K2000's dedicated
    # single codes, not by sending two buttons together (verified on hardware
    # 2026-06-19). In a naming dialog, CursorLeftRight (0x1A) jumps to the end
    # of the name. (Panic is an app binding — a real MIDI all-notes-off.)
    "alt+end": _button("Name → end", Button.CursorLeftRight),
}


def resolve(key: str) -> Optional[KeyAction]:
    """Return the :class:`KeyAction` for a Textual key string, or ``None``."""
    return KEYMAP.get(key)


# Labels for the mode bar in the TUI: (chord, short name).
MODE_BAR: List[Tuple[str, str]] = [
    ("Alt+p", "Prog"),
    ("Alt+s", "Setup"),
    ("Alt+q", "QA"),
    ("Alt+m", "Mstr"),
    ("Alt+i", "MIDI"),
    ("Alt+d", "Disk"),
    ("Alt+g", "Song"),
    ("Alt+e", "FX"),
]

# --- mode leader (for terminals that grab Alt-chords) -----------------------
# GTK terminals (e.g. LXTerminal) capture Alt+letter for menu mnemonics, so the
# Alt+p/s/… mode chords never reach the app. Under --super-alt-keys the modes are
# instead reached with a **leader key**: press MODE_LEADER, then the mode's
# letter — plain keystrokes that no terminal intercepts. Letters match the
# Alt-chords (p s q m i d g e).
MODE_LEADER = "m"
MODE_KEYS: Dict[str, KeyAction] = {
    "p": _button("Program", Button.Program),
    "s": _button("Setup", Button.Setup),
    "q": _button("Quick-Access", Button.QuickAccess),
    "m": _button("Master", Button.Master),
    "i": _button("MIDI", Button.MIDI),
    "d": _button("Disk", Button.Disk),
    "g": _button("Song", Button.Song),
    "e": _button("Effects", Button.Effects),
}
# Mode bar shown under --super-alt-keys: "m <letter>" leader hints instead of the
# Alt-chords. Lowercase letters — no Shift is involved.
MODE_BAR_ALT: List[Tuple[str, str]] = [
    (f"{MODE_LEADER},{letter}", name)
    for (_, name), letter in zip(MODE_BAR, ("p", "s", "q", "m", "i", "d", "g", "e"))
]

# Key legend for the status row, as discrete blocks. The TUI folds these to the
# window width (k2kremote.app.wrap_blocks), breaking only between blocks — never
# inside one — so a label like "Alt+X panic" is never split across a line.
# Grouped so a fold never orphans one member of a run. The function keys in
# particular read as a block: when a greedy wrap put "F7 Edit" at the end of the
# navigation line and started the next with "F8 Exit", F7 was reported missing.
LEGEND_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("↑↓←→ cursor", "+/- or PgUp/Dn value", "_ sign/case", "Enter", "Esc=Exit",
     "Del=Cancel", "Ctrl+↑/↓ wheel", "[ ] Chan/Bank", "\\ both"),
    ("F1-F6 soft", "F7 Edit", "F8 Exit", "F9 name", "F10 view", "F11 master",
     "F12 png"),
    ("Alt+x panic", "p pause", "Ctrl+r refresh", "Ctrl+o rename"),
)
LEGEND_BLOCKS: Tuple[str, ...] = tuple(b for g in LEGEND_GROUPS for b in g)
LEGEND = " · ".join(LEGEND_BLOCKS)

# Same legend with the **terminal-safe alternates** for terminals that swallow
# the F-keys (shown by the app's --alt-keys option). Only the F-key blocks change.
LEGEND_GROUPS_ALT: Tuple[Tuple[str, ...], ...] = (
    LEGEND_GROUPS[0],
    ("a-h soft", "Ctrl+e Edit", "Ctrl+x Exit", "Ctrl+n name", "Ctrl+v view",
     "Ctrl+u master", "Ctrl+g png"),
    LEGEND_GROUPS[2],
)
LEGEND_BLOCKS_ALT: Tuple[str, ...] = tuple(b for g in LEGEND_GROUPS_ALT for b in g)

# Soft-key prefixes for the live F1-F6 label bar: the F-keys by default, or the
# home-row alternates (a s d f g h) under --alt-keys.
SOFT_KEY_LABELS: Tuple[str, ...] = ("F1", "F2", "F3", "F4", "F5", "F6")
SOFT_KEY_LABELS_ALT: Tuple[str, ...] = ("a", "s", "d", "f", "g", "h")
