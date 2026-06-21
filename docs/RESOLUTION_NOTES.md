<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# k2kremote — resolution notes

Companion to [TODO.md](../TODO.md): *how* each item was resolved or will be.
Hardware findings are from Jan's K2000R, 2026-06-19; the probe scripts that
produced them live in `probes/`.

> One session drives the K2000R at a time; all output is throttled (SysEx only —
> notes/CC pass through). Device id **0** works; broadcast **127** does not.

---

## 1. Naming model — RESOLVED (verified on hardware)

The K2000 name dialog behaves as follows (probes/p09–p12):

* A pad button **resets** the cursored character to the group's first letter,
  then the **same** button **cycles** within the group. A different button or a
  cursor move starts fresh. `0` resets/cycles `0…9`.
* `+/-` (`Button.PlusMinus`) toggles the character's case and a **sticky global
  case** whose value at dialog-open is **not reliable**.
* `CursorRight` advances; **`Clear` also advances without blanking** (contrary to
  the manual) — so it must not be used to "reset" a position.
* Space/punctuation: reset to a known digit, then nudge the **alpha wheel** along
  the ring `! … z ` (space last).

Because the case is stateful, `text_entry.type_name` reads each position back
over MIDI and corrects the letter, case and wheel — verified typing
"K2K Hello-1" and "k2kremote demo". `plan_name` is the offline reference plan
(no `Clear`, reset+cycle, assumes a `start_case`).

## 2. Feedback entry done; trailing characters open

`type_name` is the feedback-driven typer (§1). Still open: when the new name is
shorter than the old, the tail is left (since `Clear` doesn't blank). Options:
type a full-width name (what the app does), or add a `Delete`-soft-button pass to
the end of the field. The name field is found by its "Name:" label
(`_find_name_field`); the Program rename dialog is row 3, col 16.

## 3. Inbound-PANEL physical mirroring — needs a human press

Confirmed our injected presses are **not** echoed back (probes/p16), so there is
no refresh feedback loop. To finish: set MIDI-mode XMIT `Buttons` = On, then have
someone press a front-panel button and confirm `poll_panel()` returns True and
the mirror refreshes within ~`INBOUND_POLL`. If injected presses ever *do* echo
on another unit, filter PANELs whose events we just sent. `mirror_panel=False`
disables the feature.

## 4. Audio routing for acoustic checks

`probes/p13_panic_audio.py` records JACK `system:capture_17/18` (the ports
mpc2emu used) but captured only noise — the K2000 output isn't routed there now.
To verify panic/notes acoustically, connect the K2000's audio outs to those JACK
capture ports (or update `CAPTURE` to the live ports), then re-run: a held note
should show high RMS before `bridge.panic()` and near-silence after.

## 5. Combo functions use dedicated codes, not chords — RESOLVED

Sending two buttons' Down/Up events together does **not** trigger the K2000's
"double-button" functions (probes/p14); the dedicated single codes do
(`CursorLeftRight` 0x1A jumps to end of name — probes/p15). So combos are bound
as ordinary single-code presses, and a generic "chord" API was removed. Panic is
a real MIDI all-notes-off (CC 120/123 on all channels), not the editor-only
soft-button combo.

## 6. Name-edit cursor — track in software, not from any device reply — RESOLVED

**The earlier "render it from the ALLTEXT high bit" theory was wrong** (corrected
2026-06-20, `probes/p21_name_cursor.py`). Probing a live rename dialog with the
cursor visibly under a character showed the cursor is in **neither** device reply:

* ALLTEXT bit 7 is **never set** on the name row (the bridge docstring's "cursored
  cell has the high bit" claim does not hold for the name editor); and
* GETGRAPHICS does **not** contain it either — in the name dialog that plane held
  *only* the divider line (pixel-row 55) and the soft-label reverse bar (rows
  56–63); the name text and the cursor underline are absent from it. (Side note:
  GETGRAPHICS is an **overlay plane, not a screenshot** — the text comes from
  ALLTEXT and must be composited in, which `braille._composite` already does.)

So the underline is a firmware overlay the device never exposes. The cursor also
**does not blink** (5 reads ~3 s apart were byte-identical).

Fix: model the cursor in software (`k2kremote/name_cursor.py`, `NameCursor`).
It mirrors the device's own cursor model — `CursorRight`/`Clear`/`>>>` advance,
`CursorLeft`/`<<<` retreat, `CursorLeftRight` (0x1A) jumps to the name's end,
pad/wheel edits don't move it — clamped to the 16-cell field, opening on cell 0
(the assumption `type_name` already makes). The app advances it whenever it sends
a cursor button (`on_key`) and after `type_name` (`set_typed`), and renders it by
emitting a one-cell `reverse_mask` that is OR'd (`merge_reverse`) into
`Frame.reverse` and fed through the **existing** `apply_cursor_underline` /
`render_text_overlay` path — so the underline shows in braille / blocks / image /
text with no new render code. `set_prioritize_graphics(True)` is still set while
naming, now only to keep the surrounding chrome fresh (the cursor no longer needs
it). **Limitation:** purely software, so it assumes app-driven editing; a cursor
moved by a *physical* front-panel press isn't reflected (we can't read the real
position back). **To verify on hardware:** open a Program rename, move with
`<<<`/`>>>` from the app — the underline should track the active cell live.

**Typing-from-a-moved-cursor bug — fixed 2026-06-21.** Reported live: park the
cursor on the *V* of "VOICES", press F9 and type "abc" → garbage ("CMI DmMCES");
from the first cell it was fine. Cause: `type_name` typed forward from wherever
the hardware cursor sat but always read each position **back at field column 0**
(`shown(col)` = `name_row[name_col + col]`), implicitly assuming the cursor was
parked on the first cell. With the cursor mid-field the pad presses land on cells
*k, k+1, …* while the read-back inspects cells *0,1,2*, so the "press until the
screen matches" loop never sees its own edit, runs to its cap, and the case
toggle fires on an unrelated cell → mangled name. Fix: `type_name` takes a
`start_col` (the field offset the cursor is on) and reads back at
`name_col + start_col + col`; the app passes `NameCursor.pos` (its tracked,
app-driven offset), so typing begins **at the cursor cell** — "abc" onto the *V*
now overwrites VOI→abc. `NameCursor.set_typed` advances **relative** to the
cursor (rests `len-1` cells on from where typing began). Still software-only: a
cursor moved by a *physical* press isn't tracked, so the offset is only correct
for app-driven moves. Covered by synthetic tests
(`test_type_name_starts_at_cursor_offset`, `test_set_typed_is_relative_to_current_cursor`,
`test_name_entry_types_from_tracked_cursor_offset`); **live hardware check still
pending.**

## 7. Soft-label split + bottom-bar wrapping — RESOLVED

`soft_labels` split the bottom row on fixed rounded column boundaries, which chopped
labels straddling a seam ("Format" → "Forma" + "t"). Now each whole word is assigned
to the soft key under its **centre column** (`int(centre * 6 / 40)`), so a label is
never cut. Separately, the legend/mode/soft bars relied on NBSP to keep `[blocks]`
intact when wrapping, but Rich treats `\xa0` as a break opportunity, so blocks still
split at the width boundary ("Alt+X panic" across two lines). Replaced with
`wrap_blocks`, which folds blocks to the window width itself (breaking only between
blocks) and renders with `Text(no_wrap=True)`; re-folds on resize.

## 8. Whole-name SysEx rename — CHANGE (0x08), an alternative to multi-tap

Names need **not** be dialled in letter-by-letter. The Kurzweil protocol's
**CHANGE (msg type 0x08)** carries `type · idno · newid · name` and sets the
object's name from a **null-terminated ASCII string in a single message** (see
the mpc2emu project's `docs/k2000r_midi_comms.md` §3; the vendored `k2000` lib
already models it as `messages.Change`). Wired up as
`MidiBridge.rename(obj_type, idno, name)`:
it sends `Change(obj_type, idno, newid=0, name)` and returns the device-confirmed
name from the INFO reply. **`newid` is always 0** — the protocol defines `newid`
in (`0`, `idno`) as "id unchanged", whereas a *different* legal `newid` would
relocate the object and **delete whatever sat at that id**; CHANGE is for that
reason deliberately *not* on the doc's "safe for a remote" list, so we never
expose the relocate form. Name is sent as raw 7-bit ASCII (rejected if
non-ASCII), so punctuation/space need no alpha-wheel detour.

This **bypasses the name dialog**: it targets the stored object by `(type, idno)`,
so it does not need the screen cursor at all — sidestepping §6 entirely for the
common "rename program N" case. Trade-offs / **still open** (see TODO):

* The app must learn the current object's `(type, idno)` to target it — read the
  Save dialog's `ID#nnn`, or query `DIR`/`INFO`. Not wired yet.
* **Hardware-unverified:** the K2000 DNAKs writes to an object **locked for
  editing** (DNAK code 1); whether a rename dialog being open counts as "editing"
  (and thus blocks CHANGE) is untested — it may be a *send-instead-of-dialog*
  path, not a *drive-the-dialog* one. Name truncation past 16 chars also untested.
* Keep `type_name` (§1–2) as the drive-the-open-dialog fallback for when the id
  is unknown or CHANGE is refused.

Synthetic coverage: `test_rename_sends_one_change_with_whole_name_and_safe_newid`
(round-trips the wire bytes, asserts `newid=0` and the whole name) and
`test_rename_rejects_non_ascii`.

**Hardware-verified 2026-06-21** (`probes/p22_change_rename.py`, on Program 201):

* **From Program mode (NOT in the editor): CHANGE works** — `'CMI VOICES   pst'`
  → `'Wave Of Mutilation'`, confirmed by the INFO reply *and* a follow-up `DIR`
  read-back. So this is the supported path.
* **But the K2000 does not redraw its LCD** after the SysEx rename — the panel
  kept showing the old name until the program was re-selected (dialling the value
  away and back). So our mirror would show the stale name too. **Fix on apply:**
  re-select the program (type its number + `Enter`) to force the device to
  re-read and repaint, then refresh our mirror.
* **In the editor / in the in-editor "Program Name:" dialog: does NOT stick.**
  The probe printed "accepted", but the editor runs off its own **edit buffer**,
  which overrode the database change (a later read had reverted to the
  pre-edit name). Confirms the editing-lock reasoning: CHANGE is a
  *send-instead-of-a-dialog* path used **from Program mode**, never while the
  object is open in EditProg.

**Design decision (2026-06-21):** CHANGE is *not* wired into the screen-mirror
dialogs at all — those keep the in-dialog multi-tap `type_name` (§1–2), since the
editor's edit buffer owns the name there. Instead CHANGE backs a **standalone
"rename object" tool** that is *not* a screen mirror: the user picks an object
**type** (Program/Sample/Keymap/Setup/Effect/…), enters the **id**, the tool shows
the **current name** (`DIR` → INFO.name), prompts for the **new name**, sends
CHANGE, and forces a device repaint. This sidesteps id auto-discovery (the user
supplies it) and the editing-lock (it is used outside the editor). For a Program
the repaint is forced by **re-selecting the id** (type its digits + `Enter`),
which also leaves the device showing the just-renamed program. The worker then
schedules a **settle refresh** (delayed, not immediate): if the app's mirror is
sitting on the renamed object it must re-read the screen *after* the device has
switched program and repainted — an instant read catches the pre-repaint screen
and the mirror stays stale (observed live 2026-06-21: the panel updated, the
mirror did not).

**Long names — the stored name is NOT truncated (verified live 2026-06-21).** A
CHANGE with a name longer than the 16-char display is stored in full: #201 was
set to the 26-char lowercase alphabet and `DIR`/INFO read back the complete
`…xyz`. Only the **LCD view** is clipped to the field width (~16 chars); the rest
of the stored string is simply off the right edge — there is **no** truncation
indicator or boundary marker. (An earlier note here claimed the boundary char was
case-flipped to a capital `P`; that was a **misread** — on this display lowercase
`p` and uppercase `P` are visually indistinguishable, so `…mnop` looked like
`…mnoP`. `DIR` confirms the stored char is lowercase `p`.) The rename tool's
"current name" preview uses `DIR`,
so it always shows the full, un-clipped name. (Implication: the tool can set
names the front panel can't display in full — fine for the database, just not
fully visible on the panel.) To make that visible, the tool colours any
characters past the `NAME_MAX_LEN` (16) display field in **bold orange**
(`_name_preview` / `_OVERFLOW_STYLE`) — both in the current-name preview and live
in the hint as a new name is typed.
