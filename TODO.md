<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# k2kremote — open issues / TODO

Issue-tracking mirrors the mpc2emu convention: *what* is open lives here;
*how* lives in [docs/RESOLUTION_NOTES.md](docs/RESOLUTION_NOTES.md). Hardware
verification was done on Jan's K2000R on **2026-06-19** (probe scripts in
`probes/`).

> **Verified on hardware** (no longer open): screen read (ALLTEXT) + braille
> mirror (GETGRAPHICS) + PNG screenshot; all eight mode menus; digit/program
> selection and every button press; **device id 0** (the unit ignores broadcast
> 127 — default corrected); the **alphanumeric-pad multi-tap** naming model and
> the feedback-driven `text_entry.type_name` (typed "k2kremote demo" correctly);
> the combo **code** `CursorLeftRight` (0x1A = jump to end of name); the **Save**
> flow (created + renamed program **300**); and that injected presses are **not**
> echoed back (no refresh feedback loop).

---

## Physical-panel mirroring needs a human press to fully confirm

**Status:** partially verified. **Blocked on:** a person physically pressing a
front-panel button while `k2kremote` is connected.

`refresh.py` refreshes when an inbound PANEL (0x14) arrives. Confirmed: our own
injected presses are **not** echoed (so no feedback loop), and `poll_panel`
drains cleanly. Not yet confirmed: that the K2000 emits PANEL for a *physical*
press (needs MIDI-mode XMIT `Buttons` = On and a human at the panel). The code
is sound and won't misfire; `mirror_panel=False` disables it. See
RESOLUTION_NOTES §3.

## Audio verification of the rig is unrouted

**Status:** inconclusive. **Blocked on:** JACK audio routing.

`probes/p13_panic_audio.py` captured only noise on `system:capture_17/18`, so the
K2000 output isn't on those ports right now. The panic itself (MIDI CC 120/123 on
all channels) is verified to send correctly (unit test); only the *acoustic*
confirmation is pending a working capture route. See RESOLUTION_NOTES §4.

## Name-edit cursor: software tracking needs live hardware verification

**Status:** implemented, **blocked on** a hardware check. **Done 2026-06-20** (in a
second session running in kitty): the name-edit cursor is exposed in *neither*
device reply (ALLTEXT bit 7 is never set on the name row; GETGRAPHICS is an overlay
plane that omits the name text and the underline) — verified with
`probes/p21_name_cursor.py` against a live rename dialog. So it is now tracked in
software (`k2kremote/name_cursor.py`, `NameCursor`) and drawn via the existing
reverse-mask path. **2026-06-21:** also fixed a typing bug found live — typing
onto a mid-name cursor (the *V* of "VOICES") garbled the name ("CMI DmMCES")
because `type_name` read its feedback at field column 0 regardless of the cursor;
it now takes the tracked `start_col` so typing starts **at** the cursor. Full
suite 149 pass. **Not yet confirmed on hardware:** open a Program rename, move
with `<<<`/`>>>` from the app, then type — the underline should track the active
cell live (image/braille/blocks/text) and the name should land at the cursor.
Software-only, so a *physical* front-panel cursor move won't be reflected. See
RESOLUTION_NOTES §6.

## Whole-name SysEx rename (CHANGE 0x08) — standalone tool, works live

**Status:** implemented and **verified live** via the `Ctrl+O` rename tool
(2026-06-21: lookup → rename → repaint confirmed on the panel *and* the mirror).
Only edge case still open: how the firmware truncates names > 16 chars.
The name can be set as a **full ASCII string in one
SysEx CHANGE (0x08)** instead of multi-tapping — verified live on Program 201
(`probes/p22_change_rename.py`): CHANGE works **from Program mode** (confirmed by
INFO + a `DIR` read-back) but **not** while the object is open in the editor
(the editor's edit buffer overrides it), and the panel **doesn't repaint** until
the program is re-selected. So it is *not* wired into the screen-mirror dialogs
(those keep `type_name`); instead it backs a **standalone "rename object" tool**
(`Ctrl+O`, `RenameObjectScreen`): pick type (Program/Sample/Keymap/Setup/FX/…),
enter id, see the current name (`DIR`), type a new name → `MidiBridge.rename`
(always `newid=0`) → for a Program, re-select the id to force a repaint. Stack:
`MidiBridge.rename`/`object_name`/`reselect_program` + worker `rename`/
`lookup_name`. Synthetic tests across bridge/worker/app; suite 157 pass. A
post-rename **settle refresh** updates the mirror even when it is sitting on the
renamed object (an immediate refresh caught the pre-repaint screen — fixed
2026-06-21). Long-name behaviour also settled (2026-06-21): the **stored name is
not truncated** (a 26-char alphabet round-tripped via `DIR`); the LCD just clips
the view and case-flips the boundary char as a "more" indicator, which the mirror
reproduces verbatim. The tool's preview uses `DIR`, so it shows the full name.
Nothing open. See RESOLUTION_NOTES §8.

## Trailing characters when a new name is shorter (enhancement)

**Status:** open (low priority). `type_name` overwrites position-by-position;
since `Clear` advances rather than blanks on this unit, a new name shorter than
the old one leaves the tail intact. The app types a full-width name to avoid it;
a `Delete`-to-end pass would be tidier. See RESOLUTION_NOTES §2.
