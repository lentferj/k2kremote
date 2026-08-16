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

## Physical-panel mirroring — RESOLVED

**Status:** **verified on hardware 2026-08-15** with a human at the panel.

The K2000R emits PANEL (0x14) for physical presses; all buttons and the alpha
wheel decoded correctly, and our own injected presses are **not** echoed back
(re-tested with the setting actually On — the earlier result was taken while it
was Off and proved nothing). The mirror refreshes on a physical touch.

The gate was a misread parameter name: it is **`Bttns`** on the MIDI TRANSMIT
page, not `Buttons`, and it was `Off` on this unit. It survives a power cycle.

One thing to respect in future code: on an inbound PANEL the *irrelevant* field
is filler, not data — button events carry `wheel=+63` (`0x7F`) and wheel events
carry `button=ChanBankDec`. See RESOLUTION_NOTES §3.

## Panic acoustic verification — CLOSED, not planned

**Status:** closed 2026-08-16. Not a gap worth a probe.

`bridge.panic()` sends CC 120 (All Sound Off) and CC 123 (All Notes Off) on all
16 channels, unthrottled, and that is unit-tested. What was never confirmed is
whether the K2000 *honours* them — but those are the standard MIDI messages for
exactly this, the K2000 documents responding to them, and the failure mode is
"the panic key doesn't help with a stuck note", which is obvious the first time
you need it.

The old blocker was **JACK routing**, and it only ever existed so
`probes/p13_panic_audio.py` could *automate* the listening: record
`system:capture_17/18`, hold a note, fire panic mid-sustain, compare RMS. The
K2000's outputs are not routed to those ports, and wiring them up buys nothing a
person at the desk cannot get in ten seconds by holding a note and pressing
panic. It could never run unattended in CI either, since it needs a physical
audio path.

The probe stays in `probes/` as a record of the method; it needs `CAPTURE`
pointed at live ports before it would do anything. See RESOLUTION_NOTES §4.

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

## SAVE → NAME takes no keyboard input — both suspects cleared, one left

**Status:** captured on hardware 2026-08-15 (`probes/p25_savename.py`). The two
suspected causes are **refuted**. **Blocked on:** confirming which route was
used to reach the name page.

The Save → Name page is `Program Name:   Drum Default Prg` over a
`Delete Insert <<< >>> OK Cancel` soft row, so `is_name_dialog()` returns True
and `_find_name_field()` returns (3, 16) from the literal label — both correct.
Input reaches the device there (one `Number2` press changed field offset 0), and
the cursor parks at offset 0, which is exactly what `NameCursor` assumes.

**Leading candidate now:** `_HEAVY_OPS` contains `"save"`, so pressing a soft key
labelled **Save** auto-pauses the mirror. A paused worker still sends presses but
schedules no refresh — input keeps working while the screen freezes, which is
indistinguishable from "input does not reach the device". Pinned synthetically by
`test_save_soft_key_pauses_the_mirror_but_still_sends_presses`.

This only bites on the **Disk route** (Disk mode → `Save`). The **editor route**
(Exit → Yes → Rename) never trips the guard — verified live, and pinned by
`test_save_page_soft_rows_do_not_themselves_trigger_the_guard`.

**Next:** confirm the route. If Disk, the fix is not to weaken the guard but to
treat "the resulting screen is a name dialog" as evidence the device is waiting
for input rather than working. Worth doing either way: pressing keys while
paused currently gives no feedback at all. See RESOLUTION_NOTES §14.

## Heartbeat lockup during deletes — gating fix needs live HW verification

**Status:** root cause **verified live 2026-06-25**; a v1 string-marker gate
**failed live** (Master → Delete → Bank 200…299 still locked up — the guessed
strings didn't match and a *timed* deferral clipped the rewrite). **v2 implemented
synthetically:** on a destructive screen the worker now **auto-pauses entirely**
(no MIDI), detecting it via real wording (`are you sure`, `delete selection`, …)
**and** a structural confirm check (bare Yes/No or OK/Cancel soft-key pair); resume
is manual via `Ctrl+r`. `--manual-refresh` drops the periodic poll entirely.
**Blocked on:** confirming on hardware that a real Master delete (bank *and*
Everything) now shows `⚠ AUTO-PAUSED` on the "Delete Selection"/"Are You sure?"
screens and stays clean. **Known limits (so `p` pause is still the only guarantee):**
detection must happen before you press Yes/OK; a delete with no on-screen confirm
wouldn't be caught.

## Heartbeat safety: switch to default-deny polling (follow-up)

**Status:** open. **Why:** the auto-pause above is a denylist of destructive
screens — a screen we fail to recognise still gets polled (that's how v1 crashed).
Safer: only fire the heartbeat when the screen matches a recognised **safe** layout
(e.g. Program/Setup play screens), so an unrecognised screen means "don't poll".
Needs RE of the safe-screen signatures. See RESOLUTION_NOTES §9.

## Master functions tool (F11) — SysEx delete/move/delete-bank, needs live verify

**Status:** implemented; **bank delete verified live 2026-06-25** (works; `DelBank`
sends no ACK — now handled by treating the timeout as success; and DELBANK is
**type-scoped** — `DelBank(Program,3)`/`DelBank(Sample,3)` each deleted only that
type in the 300s). Five functions: delete object, move/relocate, delete one type's
bank, **delete all types in one bank** (`DelBank` type 0 + bank N), and **Delete
EVERYTHING** (type 0 / bank 127). Stack: `bridge.{delete_object,move_object,delete_bank}` →
`worker.device_op` → `master_apply` (auto-pauses the mirror). **Still to verify on
hardware:** (1) does `DelBank` with **type 0** actually delete *all* types (tiers 2
& 3)? — only the type-scoped tier 1 is confirmed so far; (2) Delete object — does
`Del` reply with INFO as the protocol claims (if not, give it the same no-ACK
treatment as `DelBank`)? (3) Move — does `Change` with a new id repaint without a
panel reselect (rename needed one)? Test against scratch objects with a full backup.
See RESOLUTION_NOTES §10.

## "Delete object with dependents" (F11) — not planned

**Status:** open, **low priority / high effort / low gain / error-prone.** `Del`
(0x07) has no recurse flag (only `type`+`idno`), and `Info` exposes no dependent
list, so a "delete a Program and the keymaps/samples it uses" option would mean
RE'ing the object structures (`Dump`/`Read` a Program, parse referenced Keymap IDs,
then each Keymap's Sample IDs — dependents usually live in other banks). That is a
lot of fragile reverse-engineering for a case the front-panel menu already covers,
so it is deliberately **not** built. Revisit only if a real need appears.

## MAC editor — planned

**Status:** open, not started. Requested 2026-08-02.

A `.MAC` is the K2000's boot/setup macro — `BOOT.MAC` is what the machine
loads at startup to pull in a set of banks, so it is the file that decides
what is resident. Editing it today means the front panel or a hex editor.

k2kremote is the natural home: it already speaks the device and mirrors the
LCD, so an editor could show the macro's steps (which banks load, from where,
into which id ranges) and let them be reordered, added or removed, then written
back.

Worth knowing before starting: a MAC drives **bank loading**, so a bad edit is
a boot that loads the wrong thing or nothing. Treat writes the way the delete
work is treated — verify against scratch copies with a full backup present, and
never write a `BOOT.MAC` without the previous one saved alongside.

Reference material: `HD0_K2X_HD2G-20260202.img.lzo` in
`~/Dokumente/SYNTHS/K2000R/Backups/` is a full disk image of the current
machine state, so it contains a real `BOOT.MAC` plus the banks it references —
the format can be RE'd from it offline, with no K2000 attached.

## Faster mirror — timing REVERTED; the cheap-read work stays

**Status:** the ALLTEXT change detector and wheel coalescing are in and good.
The faster *timings* were reverted 2026-08-16 after they locked the K2000 up in
ordinary use (power cycle required).

Kept, because they lower total traffic: ALLTEXT as the change detector (a quiet
heartbeat costs one 132 ms read instead of 1.1 s of both planes — idle duty ~5%
against the old 44%), alpha-wheel coalescing, and `GRAPHICS_MAX_AGE`.

Reverted, because they raise traffic *density*: `SEND_GAP` back to 500 ms,
`HEARTBEAT` to 2.5 s, `SETTLE` to 350 ms, and the settle re-look disabled.

Also fixed: an inbound PANEL used to force a full both-planes refresh. That path
was dead until `Bttns` was switched On the same day, after which every physical
touch of the panel cost ~1.1 s of wire while the device was busy. It now goes
through the settle like any other press, and `--no-panel-mirror` disables it.

**Settled 2026-08-16 by experiment:** the fast profile stalls after **98 s** of
sustained use with someone at the front panel (`p26`, 39 panel events,
GETGRAPHICS unanswered for a full 5 s), and its worst-case ALLTEXT drifts to
161.7 ms against the conservative profile's 132.2. The conservative profile ran
five minutes clean in the same session. The fast timings are not coming back.

Two earlier p26 results (34 s and 8 s stalls) are **void** — measured through a
1.0 s operational timeout against a 963 ms read. That bug is fixed; see
RESOLUTION_NOTES §16, and note it was probably a big part of the original hang
report on its own.

Still untested: the conservative profile *with* someone pressing (that phase
recorded 0 panel events). Real use is the only evidence for it so far.

**If anyone lowers these again:** run `probes/p26_sustained.py` first — it
drives the real worker with a synthetic user for minutes and reports stalls plus
latency drift (healthy ALLTEXT is 131.6 ms with <2 ms spread, so a climbing
median is the device falling behind). The bar is a clean run at the candidate
profile: never stalled, median barely moved. The measurements that justified the
fast defaults were isolated round-trips, an idle duty-cycle window and single
keypresses — none of which resemble navigating. See RESOLUTION_NOTES §15.

## Disk-op status: app-initiated and panel-initiated loads behave differently

**Status:** open, cosmetic. The underlying "disconnected during a load" bug is
**fixed and confirmed on hardware** (RESOLUTION_NOTES §17).

Starting a disk load from the app trips the heavy-op guard — a soft key labelled
`Load`/`Save`/`Macro`/`Delete` — and pauses the mirror outright, needing `p` to
resume. Starting the same load at the front panel gets the newer `waiting`
handling, which recovers on its own. Same situation, two behaviours.

Unifying them means deciding which is right. The pause is more conservative and
predates the evidence; the busy state is nicer to use and is now known to be
safe, since a loading K2000 answers nothing at all and cannot be disturbed by a
poll it never receives. Worth doing when someone is annoyed enough by it.
