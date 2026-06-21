# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

from k2000.definitions import Button

from k2kremote import keymap


def test_soft_keys_and_function_row():
    assert keymap.resolve("f1").button == Button.SoftA
    assert keymap.resolve("f6").button == Button.SoftF
    assert keymap.resolve("f7").button == Button.Edit
    assert keymap.resolve("f8").button == Button.Exit


def test_terminal_safe_alternates_for_fkeys():
    # Home-row run a s d f g h mirrors soft A-F (same on QWERTY/QWERTZ);
    # Ctrl+E/Ctrl+X mirror Edit/Exit — for terminals that intercept F-keys.
    for letter, fkey in zip("asdfgh", ["f1", "f2", "f3", "f4", "f5", "f6"]):
        assert keymap.resolve(letter).button == keymap.resolve(fkey).button
    assert keymap.resolve("ctrl+e").button == Button.Edit
    assert keymap.resolve("ctrl+x").button == Button.Exit


def test_cursor_keys():
    assert keymap.resolve("up").button == Button.CursorUp
    assert keymap.resolve("down").button == Button.CursorDown
    assert keymap.resolve("left").button == Button.CursorLeft
    assert keymap.resolve("right").button == Button.CursorRight


def test_digits():
    for n in range(10):
        action = keymap.resolve(str(n))
        assert action.button == getattr(Button, f"Number{n}")


def test_value_and_chanbank_aliases():
    assert keymap.resolve("plus").button == Button.Plus
    assert keymap.resolve("+").button == Button.Plus
    assert keymap.resolve("minus").button == Button.Minus
    assert keymap.resolve("-").button == Button.Minus
    assert keymap.resolve("[").button == Button.ChanBankDec
    assert keymap.resolve("left_square_bracket").button == Button.ChanBankDec
    assert keymap.resolve("]").button == Button.ChanBankInc


def test_edit_keys():
    assert keymap.resolve("enter").button == Button.Enter
    assert keymap.resolve("escape").button == Button.Exit    # Esc backs out
    assert keymap.resolve("delete").button == Button.Cancel  # Cancel on Delete
    assert keymap.resolve("backspace").button == Button.Clear


def test_pageupdown_are_value_plus_minus():
    # PageUp = Plus (value up), PageDown = Minus (value down).
    assert keymap.resolve("pageup").button == Button.Plus
    assert keymap.resolve("pagedown").button == Button.Minus


def test_alpha_wheel_on_ctrl_arrows():
    up1 = keymap.resolve("ctrl+up")
    assert up1.is_wheel and up1.wheel == +1 and up1.button is None
    assert keymap.resolve("ctrl+down").wheel == -1
    assert keymap.resolve("ctrl+pageup").wheel == +5
    assert keymap.resolve("ctrl+pagedown").wheel == -5


def test_mode_chords():
    assert keymap.resolve("alt+p").button == Button.Program
    assert keymap.resolve("alt+e").button == Button.Effects
    assert keymap.resolve("alt+i").button == Button.MIDI


def test_unknown_key_returns_none():
    assert keymap.resolve("ctrl+z") is None
    assert keymap.resolve("tab") is None


def test_panic_is_not_a_keymap_press():
    # Panic is an app binding (a real MIDI all-notes-off), not a button/chord —
    # the soft-button "panic" combo is editor-only and context-dependent.
    assert keymap.resolve("alt+x") is None


def test_name_end_combo_uses_dedicated_code():
    # The K2000 combo "left+right cursor = jump to end of name" is its own
    # single button code (CursorLeftRight 0x1A), verified on hardware.
    action = keymap.resolve("alt+end")
    assert action.button == Button.CursorLeftRight


def test_dangerous_commands_are_unreachable():
    """DEL / DELBANK / MOVEBANK must never be bound to a key."""
    bound = {a.button for a in keymap.KEYMAP.values() if a.button is not None}
    forbidden_names = {"Delete", "Del", "DelBank", "MoveBank"}
    assert not any(b.name in forbidden_names for b in bound)
