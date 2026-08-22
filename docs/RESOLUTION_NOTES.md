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

## 3. Inbound-PANEL physical mirroring — RESOLVED (verified on hardware)

Verified live 2026-08-15 with a human at the panel. **The K2000R does emit PANEL
(0x14) for physical front-panel presses**, and every one decoded correctly: all
eight mode keys, ChanBank±, the four cursors, Clear, Enter, SoftA–D. The alpha
wheel echoes too, as signed deltas (+1, +2, +4, +16, −9 …) in bursts as tight as
0–30 ms apart — which is the device itself confirming that wheel motion is
summable, the assumption the outgoing coalescing in §13 rests on.

### The setting is `Bttns`, not `Buttons`, and it was Off all along

On the MIDI **TRANSMIT** page it is abbreviated `Bttns` (row 4, middle column),
which is why searching the screen dump for "Button" finds nothing. It was `Off`
on this unit, which is the entire reason this item sat unconfirmed for so long —
the device was never emitting anything to detect. It **survives a power cycle**
(battery-backed), so it only needs setting once.

### No feedback loop — now actually tested

The previous "injected presses are not echoed" result was recorded while `Bttns`
was `Off`, where *nothing* is echoed, so it demonstrated nothing. Re-run with
`Bttns:On`: four injected cursor presses, 1.5 s listening window each, **zero
inbound PANEL**. The K2000's OS really does distinguish internal (front-panel)
from external MIDI, as the `Panel` docstring in `k2000/messages.py` claims. The
claim now rests on a test that could have failed.

### The third byte is filler and decodes as garbage

Every button Down/Up arrived with `alpha_wheel_clicks == +63`: the device sends
`0x7F` in the wheel slot, and `ButtonEvent.decode` computes `byte - 64`.
Symmetrically, every AlphaWheel event decoded with `button == ChanBankDec`
(value 21) — filler in the button slot. Our own encoder puts `0x40` / `Number0`
in those slots, so this is the device's convention, not ours.

Harmless today: `poll_panel()` inspects only the message *type*. But **any code
that reads those fields off an inbound PANEL must ignore the irrelevant one** —
the button field on an AlphaWheel event, the wheel field on a Down/Up. A future
"mirror the physical press into the software name cursor" would otherwise apply
a phantom +63-click turn on every button press.

### How it was captured

`probes/` has no committed script for this; it was a throwaway passive listener
(connect, then read `client.midi_in` in a loop and decode 0x14, sending nothing
at all so a human can navigate freely). Worth noting the hazard that surfaced:
asking someone to "press a few different buttons" walked the unit onto the
**Disk** page, where the soft keys are live disk operations, and SoftA started a
floppy load that hung the machine (recovered by power cycle, no data lost). Any
future ask-a-human-to-press protocol should name the safe buttons explicitly.

## 4. Panic acoustic verification — CLOSED (2026-08-16)

`probes/p13_panic_audio.py` records JACK `system:capture_17/18` (the ports
mpc2emu used), holds a note, fires `bridge.panic()` mid-sustain and compares RMS
either side. It captured only noise, and that was written up as "the K2000's
outputs are not routed there".

**That conclusion was wrong, and was corrected 2026-08-17 by measuring.** With
notes playing at velocity 115, four seconds of capture reads:

    system:capture_17   rms 0.0369  (-28.7 dBFS)   peak 0.152
    system:capture_18   rms 0.0271  (-31.3 dBFS)   peak 0.134
    system:capture_19/20       (-90.8 / -89.5 dBFS)  silence
    system:capture_1/2         (-74.5 / -71.7 dBFS)  NOT an input - see below

Some 60 dB above a genuinely idle input pair, so the instrument is on 17/18 and
`p13`'s hardcoded ports were right all along.

**`system:capture_1/2` is not a hardware input on this rig** — it is a stereo sum
of everything playing on the computer. It read -74 dBFS here because the machine
happened to be quiet, not because it is an idle input, and it would show signal
for any application audio. So it is useless as a control pair and actively
misleading for "is there signal anywhere" sweeps: a measurement that accidentally
captured it would be recording the computer, including any monitoring of the
instrument, which is a feedback path rather than a measurement. Use **19/20** as
the idle reference. Whatever the original run captured, the
fault was not the port numbers — and "captured only noise" became a claim about
the routing rather than about that attempt, which then justified closing the
probe. A negative result got promoted to a property of the rig.

**Closed rather than fixed.** The routing existed only to *automate* the
listening. `panic()` sends CC 120 + CC 123 on all 16 channels and that is
unit-tested; the open question was whether the K2000 honours them, and those are
the standard All Sound Off / All Notes Off messages it documents responding to.
Anyone sitting at the instrument can settle it in ten seconds — hold a note,
press panic, listen — and the automated version could never run unattended
anyway, because it needs a physical audio path that a CI machine does not have.

The probe is kept as a record of the method. To use it, point `CAPTURE` at
whatever JACK ports the K2000 is actually on and re-run: a held note should show
high RMS before the panic and near-silence after.

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

## 9. Heartbeat locks up the K2000 during deletes — context-aware gating + manual mode

**Root cause (verified live 2026-06-25, firmware 3.87J).** The ~2.5 s GETGRAPHICS
**heartbeat** in `refresh.py` crashes the K2000 when it lands while the unit is
inside a destructive critical section (delete / save rewriting its object table).
Reproduces even when the operator drives the *front panel* directly — the
background poll alone is enough; recovery needs ~2 factory-reset cycles. With
k2kremote **not** running, every delete succeeds. This was the long-standing
mpc2emu "delete lockup" wrongly blamed on the KRZ converter / bank corruption;
the converter is exonerated. **Confirmation experiment:** launching paused
(`p` → no outbound SysEx, ports still open) made both targeted deletes **and**
*Delete Everything* clean, isolating the periodic poll (not the cable) as cause.
See project memory `lockup-heartbeat-during-deletes`.

**First attempt FAILED live 2026-06-25.** A v1 gate keyed on body-text markers
RE'd from the *manual* (`Func:DELETE`, `Select database function:`, …) and merely
deferred reads 1.5 s. Doing **Master → Delete → Bank 200…299** locked the unit up
anyway: the badge never appeared because the real K2000 screens didn't match the
guessed strings, and a poll fired into the rewrite. The actual flow is
**"Delete Selection: 200…299 | … | Everything"** → OK → **"Are You sure? Yes | No"**
→ rewrite. Lesson: guessed body strings are unreliable, and a *timed* deferral can
still clip a long (bank / Everything) rewrite.

**v2 (auto-pause on *every* destructive-context screen) was too aggressive.** It
also froze the idle **"Delete Selection:"** range list — and since the list is
~10–12 lines, navigating it cost a manual `Ctrl+r` per line (Jan: "up to 12
refreshes"). Idle screens (the range list, object menus) are SAFE to poll — the
K2000 isn't rewriting anything there — so freezing them buys no safety and wrecks
usability.

**Fix — current design (gate ONLY the commit prompt; synthetic, live verify
pending):**

1. **Auto-pause only on the confirmation prompt (always on).**
   `is_destructive_screen()` flags **just the final commit step** — the screen
   whose next press (Yes) starts the rewrite — via two signals: body text
   `are you sure`, or a **structural bare Yes/No soft-key pair**. The mirror stays
   **fully live everywhere else**, including the selection/range list and object
   menus, so navigation is normal. OK/Cancel is *not* a trigger (it is the accept
   button on the safe selection screen; only destructive commits use Yes/No).
   On the confirm prompt the worker goes **fully quiescent (no heartbeat, no
   settle, no inbound-PANEL read)**, exactly like a manual `p`; the press that
   follows (Yes) and the rewrite then happen with zero outbound MIDI. It does
   **not** time-resume — the user presses **`p`** or **`Ctrl+r`** once the K2000
   has finished (both trigger a `force_refresh`, which reads even while paused and
   lifts the hold only if the screen is now safe). **Unified pause UI:** manual
   pause, the heavy-disk-op auto-pause, and this confirm auto-pause all show one
   `⏸ PAUSED · <reason>` badge (manual / disk op / confirm) and all resume with
   `p` — `action_pause` routes to `force_refresh` when `worker.danger` so it
   doesn't stack a manual pause on top of the content-driven hold.
2. **`--manual-refresh` (opt-in).** Passes `heartbeat=None` → no periodic poll at
   all; the mirror updates only on front-panel events and explicit `Ctrl+r`.

**Residual risk / limits.** The confirm prompt must be *read* before the operator
presses Yes (the OK press that summons it normally triggers that read via the
panel echo, beating human reaction; but with XMIT Buttons off it relies on the
heartbeat, so a very fast Yes could still slip through). A destructive op that
commits with **no Yes/No confirm** wouldn't be caught either. So **`p` pause
before panel surgery remains the only guaranteed safety** (zero dependence on
screen content); the auto-pause is best-effort. A planned follow-up (§ TODO) is
**default-deny polling** — only poll on a recognised *safe* screen. Synthetic
coverage in `tests/test_refresh.py`
(`test_is_destructive_screen_flags_only_the_confirm_prompt`,
`test_heartbeat_gated_off_on_destructive_screen`,
`test_destructive_screen_auto_pauses_then_resumes_on_force_refresh`,
`test_force_refresh_reads_while_auto_paused_but_request_refresh_does_not`,
`test_manual_refresh_mode_skips_heartbeat_but_honours_events`).

## 10. Master object utilities via SysEx — the F11 tool (bypasses the LCD)

A standalone alternative to driving the K2000's Master → Object menu flow (the
flow that can lock the unit up, see §9): fire the destructive op as **one SysEx**
straight at the object database, no front-panel navigation. Modelled on the §8
rename tool. Three functions (the ones that map to a single K2000 SysEx):

* **Delete object** → `Del` (0x07) — `MidiBridge.delete_object`.
* **Move/relocate object** → `Change` (0x08) with an **empty name** (name
  unchanged) and a non-zero `newid` — `MidiBridge.move_object`. **Destructive at
  the destination:** the protocol deletes whatever already sits at `newid`.
* **Delete bank — one type** → `DelBank` (0x0E), **type-scoped** — wipes only the
  chosen type's 100-id bank. Verified live 2026-06-25: `DelBank(Program, 3)` deleted
  only programs in the 300s (keymaps/samples intact), same for `DelBank(Sample, 3)`.
  Type dropdown applies — `MidiBridge.delete_bank(obj_type, bank)`.
* **Delete bank — all types** → `DelBank` with `type` = 0 and a specific bank =
  every object type whose ID is in that 100-id range — `delete_bank(None, bank)`.
  (This is by ID range, NOT a dependency walk; "delete program + dependents" is a
  different, non-bank-scoped operation with no single SysEx.)
* **Delete all objects** (labelled "Delete all objects (Program RAM)") → `DelBank`
  with `type` = 0 **and bank = 127** = every object of every type, all banks
  — `delete_bank(None, 127)`. No type/bank field; double-confirm only. **Does NOT
  reclaim sample RAM** — see the sample-RAM caveat below.

`DelBank` returns **no INFO** (verified live 2026-06-25 — the bank is wiped but no
INFO comes back), so `delete_bank` uses a short grace wait and **treats the timeout
as success** (returns `None`); otherwise it surfaced a misleading "no response"
error. The "Everything" `type` = 0 has no `ObjectType` enum member, so a tiny
`.value == 0` stand-in (`_ALL_OBJECT_TYPES`) supplies it for encoding.

**ENDOFBANK decode crash on "Delete all objects" — FIXED (verified live 2026-06-26).**
The all-types/Everything delete (`type` 0) is in fact *acknowledged*: the K2000
replies with an **ENDOFBANK** (0x0D) whose `type` field is **0** ("all object
types"). Decoding that as `ObjectType(0)` raised (`0 is not a valid ObjectType`),
which `_send_and_receive` re-raised after the grace loop — surfacing as
`Failed to decode 9-byte packet as 'EndOfBank' message` (a `ValueError`, not the
`TimeoutError` `delete_bank` was catching). Fix: `_decode_object_type()` in
`k2000/messages.py` maps a `type`-0 field to `None` ("all types") for `EndOfBank`,
`DelBank`, and `MoveBank`, so the reply decodes; it isn't an `Info`, so the grace
wait still times out → success. Regression:
`test_delete_everything_endofbank_reply_is_not_a_crash`.

### Sample RAM is NOT reclaimed by `DelBank` — power-cycle or a front-panel "Everything" delete (verified live 2026-06-26)

The K2000 has **two memory pools** (manual ch. 27): battery-backed **Program RAM**
(programs, keymaps, setups, and *sample objects* — type 134 "Soundblock", the
header carrying Start/Alt/Loop/End + MISC params) and volatile **Sample RAM** (the
raw audio of loaded RAM samples). The F11 "Delete all objects" `DelBank` clears
Program RAM, so the sample objects vanish from both the object DB and Master →
Sample (only ROM remains) — **but the sample-RAM allocator is not told to release
those blocks**, so free Sample RAM is unchanged ("a few KB", as before). With the
referencing objects already gone, the bytes are **orphaned** (resident but
unreachable). `DelBank` is a blunt object-table wipe; it skips the sample-RAM
reclamation that the firmware's own delete path runs.

**Recovery (no save needed):**
* A front-panel **Master → Object → Delete → Everything** afterwards **does**
  reclaim the orphaned sample RAM — free RAM is reported correctly again, and it's
  **fast** (verified live 2026-06-26). The firmware's Delete-Objects path runs the
  sample-RAM GC even when the objects are already gone.
* Or **power-cycle** the K2000 — Sample RAM is volatile, so it clears entirely.

There is **no SysEx that reclaims sample RAM** (DELBANK doesn't; no documented
alternative), so the app cannot do it over MIDI. The F11 confirm, the field
placeholder, and the help text all warn that "Delete all objects" frees Program
RAM only and leaves sample RAM for a front-panel delete or a power-cycle.

"Copy" is intentionally absent (no single SysEx for it); "Name" is the Ctrl+O tool.

**Stack.** `MidiBridge.{delete_object,move_object,delete_bank}` → a generic
`RefreshWorker.device_op(fn, on_result)` that runs `fn(bridge)` on the worker
thread (so no heartbeat can interleave the blocking send) and never schedules a
follow-up refresh → `K2KRemoteApp.master_apply`, which **pauses the mirror first**
(reason "master op", unified `⏸ PAUSED` badge) and leaves it paused so no read
lands during any rewrite; the user resumes with `p`. UI is `MasterFunctionScreen`
(F11): function + type + id (or bank), a `DIR` name preview, and a **two-step
Enter confirm** ("⚠ … press Enter again to FIRE"). Bound to **F11**, NOT Ctrl+M —
terminals deliver Ctrl+M as Enter (a device key).

Synthetic coverage: `test_delete_object_sends_del`,
`test_move_object_sends_change_with_newid_and_empty_name`,
`test_delete_bank_sends_delbank_for_one_type`,
`test_delete_bank_treats_missing_ack_as_success`,
`test_delete_everything_uses_type_zero_bank_127`,
`test_delete_everything_endofbank_reply_is_not_a_crash`,
`test_delete_bank_all_types_sends_type_zero` (bridge);
`test_device_op_runs_on_worker_thread_even_while_paused`,
`test_device_op_reports_errors_without_killing_the_worker` (worker);
`test_master_tool_two_step_confirm_and_autopause` (app).

**Verified live 2026-06-25 / -26:** a bank delete works; one-type `DelBank` returns
no INFO; the all-types/Everything delete replies with ENDOFBANK `type` 0 (decode
crash now fixed); and "Delete all objects" frees Program RAM but orphans sample RAM,
recovered by a front-panel "Everything" delete or a power-cycle. **Still
unverified:** that `Del` (single object) *does* reply as the protocol claims, and
whether a `Change`-move needs a panel reselect to repaint.

---

## 11. Autodetect leaked dozens of "RtMidiIn Client"s — free backend clients now — RESOLVED

**Symptom (Jan, 2026-07-12):** starting `k2kremote --rig auto` leaves a few dozen
disconnected **RtMidiIn Client** entries in qjackctl's ALSA-MIDI panel; only the 8
that matter (the ESI M4U eX sub-ports the merged `MultiIn` receives on) are wired
up. On a host with many ports it eventually exhausts the ALSA sequencer's client
slots — even `aconnect -l` then fails with *"open /dev/snd/seq failed: Cannot
allocate memory"* (ENOMEM), and no process can open MIDI at all until k2kremote is
killed. Observed live: **49** `RtMidiIn` clients for one running `--rig auto`.

**Cause:** `MidiBridge.autodetect` opens a listener (`rtmidi.MidiIn`) on *every*
input port and a probe `rtmidi.MidiOut` per output port, then only `close_port()`s
them. python-rtmidi creates the backend ALSA sequencer **client** in the
constructor, and its own docs are explicit: `close_port()` does **not** tear the
client down, and relying on `del`/GC "may be delayed for an arbitrary amount of
time." So every transient port — including the one-shot `rtmidi.MidiIn()` built
just to call `get_ports()` — orphans a client for the life of the process. ~40
scan listeners + the 8 kept `MultiIn` ports ≈ the dozens seen.

**Fix (`k2kremote/midi_bridge.py`):** call `port.delete()` (immediate backend
teardown) everywhere a port is transient:
- `_delete_quiet()` / `_enum_in()` / `_enum_out()` helpers; all bare
  `rtmidi.MidiIn().get_ports()` / `MidiOut().get_ports()` enumerations now route
  through the leak-free helpers.
- `autodetect`: `finally` deletes every scan listener; the per-output probe `out`
  is deleted in its own `finally` (and on open failure); half-opened listeners are
  deleted too.
- `MultiIn.close_port` and `MidiBridge.close` now `delete()` the backend client,
  not just close the port — a clean disconnect frees ALSA slots.

**Synthetic coverage:** `test_autodetect_success_frees_all_scan_clients`,
`test_autodetect_failure_frees_all_scan_clients`,
`test_bridge_close_frees_backend_clients` (the `ScanRtmidi` fake tracks
constructed-but-not-deleted clients). **Not yet verified live** — the running
session must be restarted on the patched code and the ALSA client count rechecked
(`grep -c RtMidiIn /proc/asound/seq/clients` should drop to 8).

---

## 12. Autodetect over-listened on the whole interface — bind to the answering sub-port — RESOLVED

Follow-up to §11. After autodetect found the K2000, it bound the receive side to
the *entire* matched interface via `MultiIn(recv_iface)` — all 8 ESI M4U eX IN
sub-ports, merged. That was a defensive port from mpc2emu for interfaces that
reassign which sub-port carries a device's replies. Jan's rig doesn't do that: the
ESI just lets each port be assigned IN or OUT, but the **cabling to the K2000's
fixed MIDI IN/OUT is fixed**, so the reply always lands on the same sub-port.

`_await_screen_reply` already knew the exact answering sub-port but discarded it
(`name.split(":", 1)[0]` → client name). Now it returns the full port name, and
`_connect_split` opens `MultiIn(recv_port, exact=True)` — a new exact-match mode
that opens only the single input whose name *equals* `recv_port`. The
config-driven `split` rig keeps the old substring/merge-all behaviour
(`exact=False`, the default) for anyone who genuinely needs it.

**Combined with §11, a live `--rig auto` now shows 1 `RtMidiIn` client** (the one
receive sub-port) instead of ~49. Synthetic coverage:
`test_autodetect_binds_only_the_answering_subport` (four sub-ports on one
interface, exactly one opened). **Not yet verified live** that reception stays
reliable bound to the single sub-port — expected to, since the cabling is fixed.

---

## 13. Making the mirror snappier — ALLTEXT as the change detector

**Prompted by the sibling eosed project**, which had just built LCD mirroring
for the E-mu EOS panel protocol and found a genuine delta request there: its
`51h` returns a full 2212-byte screen (716 ms measured), while `52h` returns
either a full frame when something changed or an **86-byte "nothing new"** in
70 ms. Its refresh strategy follows directly — poll the cheap one, act only
when the answer is big enough to decode (eosed `docs/RESOLUTION_NOTES.md`
§33a–§33c).

### The K2000 has no delta request — but it has a cheap plane

Every screen opcode in the K2 SysEx set was checked against `k2000/messages.py`
and the K2500 reference: `ALLTEXT` (0x15), `PARAMVALUE` (0x16), `PARAMNAME`
(0x17) and `GETGRAPHICS` (0x18) all return a `SCREENREPLY` (0x19), and **none
of them takes a body** — there is no offset, no region, no "since last time".
The device cannot be asked what changed, and it never pushes. So eosed's
mechanism does not port. What ports is its *shape*: ask something cheap, and
escalate only when the cheap answer says you must.

The cheap thing here is the text plane. Both reads are a fixed size:

| read | payload | predicted | **measured** |
|---|---|---|---|
| `ALLTEXT` (0x15) | 321 bytes | ~103 ms | **131.6 ms** |
| `GETGRAPHICS` (0x18) | 2561 bytes | ~819 ms | **962.7 ms** |

**7.3x.** Measured on the K2000R 2026-08-15 with `probes/p24_timing.py` (medians
of 7; the spread was under 2 ms either way — the device is strikingly
deterministic). Both are ~20-28% slower than the raw payload arithmetic
predicts, which is SysEx framing plus the 10 ms poll granularity in psobot's
`_send_and_receive`.

### What was actually costing the time

Measuring the *protocol* would have missed the biggest cost, which was ours.
The old defaults were `SEND_GAP` 500 ms, `SETTLE` 350 ms, `HEARTBEAT` 2.5 s,
and a refresh that unconditionally read **both** planes. Walking one keypress
through that:

    press sent                          t=0
    throttle gap before the settle read  +500 ms   <-- pure idling
    settle                               +350 ms
    ALLTEXT                              +103 ms
    throttle gap                         +397 ms   <-- pure idling
    GETGRAPHICS                          +819 ms
                                        ------
    full frame on screen                ~2.2 s

Two thirds of that is the throttle and a conservative settle, not the wire. And
an idle heartbeat spent ~0.92 s of every 2.5 s reading a screen that, most of
the time, had not changed at all — a **37% duty cycle to learn nothing**, on
the same link the user's keypresses have to get out on.

### The four changes

1. **`SEND_GAP` 500 ms → 150 ms** (`SYSEX_FLOOR` = 120 ms, clamped in
   `ThrottledOut`, so no config or flag can go under it). The gap is measured
   from the last *send*, so a request whose reply takes a while has already
   paid it — it is charged precisely on the messages a user waits for. This is
   the single largest win and the one that most needs hardware confirmation.
2. **ALLTEXT is the change detector.** A refresh reads the text plane first and
   compares it — *including the reverse-video mask*, so a cursor that inverts a
   cell without moving a character still counts as a change. Identical means
   stop: no 2561-byte read, and no frame handed to the UI at all.
3. **`HEARTBEAT` 2.5 s → 1.2 s.** Affordable only because of (2): a quiet poll
   now costs ~103 ms, so 1.2 s is a **9% duty cycle** — a quarter of the old
   load while spotting front-panel changes twice as fast.
4. **`SETTLE` 350 ms → 150 ms with one re-look** (`SETTLE_RETRY`, 250 ms).
   Rather than making every keypress wait for the worst-case redraw, read early
   and cheaply; if the screen comes back unchanged the redraw probably had not
   landed, so look once more. The second look always buys the pixel plane,
   because a press *can* change graphics only.

Measured A/B on the same unit and the same screen, heartbeat disabled in both
arms so only the press-driven refresh is timed (n=4 each):

| keypress to... | old (500/350) | new (150/150) | |
|---|---|---|---|
| text on screen | 632 ms | **282 ms** | 2.2x |
| fresh pixel plane | 1968 ms | **1267 ms** | 1.6x |

The text figure is the one that matters for feel: nearly all navigation changes
text, and 282 ms is the point where the user sees the new screen. Both numbers
match the arithmetic exactly (old: 500 gap + 132 read = 632), which is a good
sign the model of where the time goes is right.

Idle cost, 36 s window with the shipping constants: 30 text reads, 2 pixel
reads, **16% duty cycle** against 44% for the old always-both-planes heartbeat.
(It was 23% before `GRAPHICS_MAX_AGE` went from 6 s to 12 s — see below.)

### The backstop, and the one thing text cannot see

A change with no text component is possible: an envelope curve redrawing, the
algorithm page's block outlines. No text compare can ever see it. So
`GRAPHICS_MAX_AGE` (6 s) bounds how long the pixel plane may go unread while
the text keeps saying "quiet", and a `_FULL` refresh — startup, resume, inbound
PANEL, Ctrl+r — never takes the shortcut at all. eosed reached the same
conclusion from the other direction: when it cannot decode a partial frame it
escalates to the full request, "correct behaviour under uncertainty".

### Alpha-wheel coalescing

A fast spin enqueued one command per click, each its own throttled SysEx, so a
ten-click flick cost ten gaps and landed long after the user stopped turning.
Adjacent queued wheel turns are now summed into one PANEL event. This is
protocol-identical — the payload is a signed delta and `chunk_wheel` re-splits
anything past the ±63 per-event range — so it is a pure latency win.

Repeated **presses** are deliberately *not* merged. The K2500 manual endorses
"several downs, one up" for increment buttons, but that is untested here and
would corrupt the name dialog's multi-tap, which counts distinct presses. Left
open below.

Plans from `submit()` are now queued as a single opaque entry rather than
spliced into the queue, which is what makes "merge adjacent wheels" safe: a
name-entry plan is replayed exactly as written and a racing keystroke cannot
land inside it.

### The pause guards are untouched

Nothing here changes when we may talk to the device — only how much we ask for
once that decision is already made. `is_destructive_screen` still runs on every
text read *before* the shortcut is considered, so the confirm-prompt auto-pause
(§9) sees every screen it saw before; the settle re-look is not scheduled while
paused or in `danger`; manual pause and `--manual-refresh` behave exactly as
before.

### Verified on hardware (2026-08-15, unattended, read-mostly)

Run on the live K2000R sitting in Program Mode. Every phase captured a
reference screen (text + reverse mask + pixels) and re-compared it afterwards,
because **a garbled LCD does show up in what we read back** — the earlier claim
that no script can detect it was too pessimistic. What a script cannot detect is
a garble that a *later* repaint has already cleaned up, which is why the sweep
below the floor still needs eyes.

* **The change detector's core assumption holds.** 40 ALLTEXT reads over 22 s on
  a quiet screen: **0 text differences, 0 mask differences**. 6 GETGRAPHICS
  reads: 0 pixel differences. Nothing on that page blinks, flickers or counts,
  so "identical means nothing changed" is sound. Had anything blinked, the whole
  optimisation would have been inert.
* **Reads space themselves.** Back-to-back ALLTEXT with the throttle switched
  *off* still came 131.6 ms apart — the reply time alone clears the 120 ms
  floor. The gap therefore does nothing for reads and everything for PANEL
  presses, which get no reply. That confines the entire risk of lowering it to
  the press path.
* **150 ms is clean.** 40 reads, 8 full frames and 16 net-zero cursor presses,
  each followed by a full reference comparison: panel byte-identical every time,
  0 errors.
* **The redraw is faster than the settle can observe.** At every delay tried the
  screen had already redrawn by the earliest readable moment (~300 ms = gap +
  ALLTEXT), 3/3. So `SETTLE` below `SEND_GAP` buys nothing — the read cannot be
  issued sooner — and `SETTLE_RETRY` should essentially never fire in normal
  navigation.
* **The backstop was the surprise.** `GRAPHICS_MAX_AGE` at 6 s fired 3 times in
  a 25 s idle window, and those three 0.96 s pixel reads were *half* of all idle
  wire time. Raised to **12 s**, which took idle duty from 23% to **16%**. The
  exposure is small: any keypress reads the pixel plane on its settle and an
  inbound PANEL forces a full refresh, so what the backstop uniquely guards is
  only "the device changed its own graphics, no text moved, nobody touched
  anything".

### The gap sweep: 120 ms holds, 100 ms stalls the device

Two runs, 2026-08-15, both with a human watching the panel.

**Run 1 — 16 presses per step, 120 → 40 ms: all steps passed the automated
check, and the human saw the LCD flickering.** That is a direct hit on the
limitation noted when `intact()` was written: it catches damage that *survives*
to the next read and is blind to anything a repaint fixes first. The script and
the observer disagreed and the observer was right.

**Run 2 — bursts sized by duration (~4 s each), controls first:**

    gap 500 ms  (old default)   16 presses,  469 ms apart   CLEAN
    gap 150 ms  (what we ship)  26 presses,  144 ms apart   CLEAN
    gap 120 ms  (the RE'd floor) 32 presses, 116 ms apart   CLEAN
    gap 100 ms                  40 presses,   98 ms apart   *** DEVICE STOPPED
                                                                ANSWERING ***

The ALLTEXT after the 100 ms burst timed out. The unit recovered on its own
within a few seconds, with no lasting damage.

**The 120 ms floor is almost exactly right.** It was inherited from mpc2emu's RE
notes without a first-hand test; the first step below it is where this unit
stops servicing MIDI.

### Duration matters more than rate, and the presses were not cheap

Run 1 reached 40 ms with no stall; run 2 died at 100 ms. The difference is burst
*length* — 0.6 s versus 3.9 s. The hazard behaves like a flood that has to be
sustained before it bites, which is why a short sweep found nothing and reading
it as "no cliff" would have been wrong.

And the presses were doing far more than assumed. On Program Mode the cursor
keys step the program list, so **every press selected and loaded an adjacent
program** — seen live as the display alternating 996/995. So this was never the
"cheap field-cursor move on an idle page" it was documented as. That makes it
the *right* experiment for the wrong reason: sustained program loads are exactly
what a user holding an arrow key produces, and "MIDI flood while the CPU is
busy" is the regime the floor came from in the first place.

It also means the honest scope of the result is **MIDI rate plus real work**,
not MIDI rate alone. Pure request traffic may well tolerate more — but there is
no reason to find out, because reads self-space at 131.6 ms regardless.

### Why 150 ms stays

It is 1.5x the observed failure point and 1.25x the RE'd floor, and it held
clean under the harshest pattern available: back-to-back program loads for four
seconds. The upside of going lower was only 282 → 172 ms on the press path,
since the 131.6 ms ALLTEXT read now dominates. Not a trade worth making against
a device that stops answering one step further down.

This also argues against collapsing repeated presses to "several downs, one up"
(still open below): key repeat at speed is precisely the traffic that broke the
unit at 100 ms, and merging would make each message do *more* work, not less.

### The probe failed open, and now fails closed

Run 2 was launched through a wrapper where stdin is not a tty, so every
interactive prompt was skipped, the warning scrolled past, and it ran the 100 ms
step unattended — the exact outcome the prompts existed to prevent. A phase that
deliberately provokes a hardware fault and whose only real instrument is a
person looking at the panel must **refuse** to run without one, not warn and
continue. It now does (`--force-unattended` overrides, pointlessly). A stalled
device is also caught and reported as the result it is, rather than a traceback.

### Still open

* **Where the flicker starts** is still unpinned — run 2 never got a verdict out
  of a human because of the tty bug, and it stalled before reaching the steps
  where run 1's flicker was probably visible. Now answerable in one pass from a
  real terminal, since each step waits for a verdict. Low value: the hard
  failure at 100 ms already settles the shipping decision.
* Whether **pure read traffic** (no presses, no program loads) tolerates a
  smaller gap. Untested and uninteresting: reads self-space at 131.6 ms anyway.
* Whether repeated presses may be collapsed to down×n + one up (manual says yes
  for `+`/`-`; unverified on the K2000R, and it must stay off inside name-entry
  plans regardless).
* `PARAMVALUE` (0x16) / `PARAMNAME` (0x17) return a short null-terminated
  string — a handful of bytes, far cheaper even than ALLTEXT. If they track the
  cursored parameter, they would make an *even* cheaper detector while
  wheel-scrubbing a single value. Neither has been tried on the hardware.

---

## 14. SAVE → NAME "takes no keyboard input" — both suspects cleared

Captured live 2026-08-15 with `probes/p25_savename.py`, which walks
Program 205 → Edit → net-zero wheel edit → Exit → Yes → Rename and dumps the
full 8x40 text layer plus both predicates' verdicts at every step. Nothing is
committed; it backs out and the object name is re-read to prove it.

### The two documented candidates are both wrong

The Save → Name page is:

    3| Program Name:   Drum Default Prg
    7| Delete Insert  <<<    >>>    OK   Cancel

* **`is_name_dialog()` returns True.** The soft row carries both `Delete` and
  `Insert`, so the app *does* recognise the page, open the software name cursor
  and show the F9 hint. Candidate 1 is out.
* **`_find_name_field()` returns (3, 16) from the literal label**, not the
  fallback — `"Program Name:"` contains `"Name:"`, and the value starts at
  column 16. Correct, and identical to the editor rename dialog. Candidate 2 is
  out.

### Input reaches the device on that page, and the cursor starts at 0

On a freshly opened Save → Name page, one `Number2` press changed field offset
**0** (`Drum Default Prg` → `drum Default Prg`). So multi-tap works there, and
the device parks its cursor at offset 0 — exactly what `NameCursor` assumes.

One misleading intermediate result is worth recording. An earlier pass pressed
`CursorRight` first and *then* typed, and `type_name(… start_col=0)` wrote at
offsets 1-2 instead of 0-1 (`Ddum` → `DAam`). That looked like an off-by-one
bug; it was the probe's own cursor move, with `start_col` then lying about where
the device cursor was. The same class of failure as the mid-name garbling fixed
in §6, and a reminder that any test of this page must not move the cursor first.

### What is actually left: the heavy-op auto-pause

The remaining explanation is not on the device at all. `_HEAVY_OPS` in `app.py`
includes `"save"`, and `_heavy_op_for` matches it against the *live label* of
whichever soft key was pressed. Pressing a soft key labelled **Save** therefore
auto-pauses the mirror before sending the press (§9's SCSI guard).

A paused worker still **delivers** presses — the pause check in `run()` only
applies when no command is queued — but it schedules **no settle refresh**. So
every keystroke reaches the K2000 while the mirror stays frozen on the last
frame. From the outside that is indistinguishable from "keyboard input does not
reach the K2000", which is exactly how it was reported.

`tests/test_app.py::test_save_soft_key_pauses_the_mirror_but_still_sends_presses`
pins the mechanism synthetically: press a `Save` soft key, confirm the pause and
that the press still went out, then confirm three further keystrokes are all
delivered while the worker stays paused forever.

Crucially this depends on **how the name page was reached**:

* **Editor route** (Exit → Yes → Rename), the one captured above: none of the
  three soft rows contains a heavy-op word, so the mirror stays live and the
  flow works. `test_save_page_soft_rows_do_not_themselves_trigger_the_guard`
  pins the captured rows so a future `_HEAVY_OPS` edit cannot silently break it.
* **Disk route** (Disk mode → `Save` soft key → filename page): trips the guard,
  freezes the mirror, and matches the report.

### Open

Which route was taken has not been confirmed with the reporter — it decides
whether the above is the cause or merely a real but unrelated bug. If it is the
Disk route, the fix is not to weaken the guard (it exists because polling during
a SCSI write can lock the unit up) but to notice that a *name dialog* means the
device is waiting for input rather than working, and to say so, or resume.

Worth fixing regardless: pressing keys while paused gives no feedback at all.
A status line along the lines of "sent — mirror paused, press p to see it"
would have made this self-diagnosing.

---

## 15. The snappy defaults locked the K2000 up in real use — reverted (2026-08-16)

Reported within minutes of running §13's build for actual work: "the device
constantly hangs, reacts slow", ending in a power cycle. The defaults are
reverted; the traffic *reductions* are kept.

### Why the measurements did not catch it

Everything in §13 was measured on traffic that does not resemble using the
thing. The round-trips were isolated. The 16% duty figure came from a **25-36 s
idle window**. The keypress A/B fired **single presses** with 1-2.5 s of quiet
between trials. Nothing put sustained, overlapping traffic on the wire.

The sweep had already said this and it was read too generously. It stalled the
unit at 100 ms **with presses alone**. Shipping 150 ms was described as "1.5x
the failure point" — but real navigation layers a 1.2 s heartbeat, a settle
read, a settle re-look and a periodic 963 ms GETGRAPHICS *on top of* the
presses. 1.5x over a pure-press failure point is not 1.5x over that.

There is also a change §13 never accounted for, made the same day in §3:
**XMIT `Bttns` went from Off to On.** Before that, `poll_panel` never saw
anything and the inbound-PANEL path was dead code in practice. With it On, every
physical touch of the panel called `request_refresh()` — a `_FULL` refresh,
both planes, ~1.1 s of wire — while the K2000 was still busy doing whatever the
press had asked for. Working at the hardware and the mirror at the same time is
exactly the reported scenario.

### What changed back, and what did not

| | §13 | now |
|---|---|---|
| `SEND_GAP` | 150 ms | **500 ms** |
| `HEARTBEAT` | 1.2 s | **2.5 s** |
| `SETTLE` | 150 ms | **350 ms** |
| `SETTLE_RETRY` | 250 ms | **disabled** |
| ALLTEXT change detector | on | **on** — strictly less traffic |
| wheel coalescing | on | **on** — strictly fewer messages |
| `GRAPHICS_MAX_AGE` | 12 s | **12 s** — still fewer pixel reads than always fetching |

The split is the point: three of §13's changes raise traffic *density*, and
three lower total traffic. Only the density ones are implicated, so only they go
back. The result should be lighter at idle than the build that predates §13
entirely — a quiet heartbeat costs one 132 ms ALLTEXT rather than 1.1 s of both
planes, so idle duty is ~5% against the old 44%, at the old cadence.

**Inbound PANEL no longer forces a full refresh.** `note_panel_event()` puts a
physical press through the settle, exactly like one of our own: the change
detector can then skip the pixel plane when nothing moved, and a flurry of
presses collapses into one read. `--no-panel-mirror` switches the path off
without having to go and set `Bttns` back to Off on the device.

### The lesson worth keeping

A latency benchmark on isolated operations says nothing about a device whose
failure mode is *sustained* load. The number that mattered — how dense the
traffic gets while somebody is actually navigating — was never measured, and the
one experiment that probed sustained load was read as reassurance rather than as
the warning it was.

`probes/p26_sustained.py` is the instrument that was missing. It drives the real
`RefreshWorker` (the actual mix of presses, settle reads, heartbeats and
periodic GETGRAPHICS) with a synthetic user navigating for minutes, and watches
two script-visible signals:

* **stalls** — a request the device never answers, which is what a lock-up looks
  like from here;
* **latency drift** — healthy ALLTEXT is 131.6 ms with under 2 ms of spread, so
  a median that climbs between the start and end of a run is the device falling
  behind. That turns "reacts slow" into a number *before* it becomes a hang, and
  it is only possible because the K2000 is so consistent when it is happy.

Flicker still needs eyes. Everything else here does not.

**No timing profile goes back to a faster default without a clean run of this**,
at both profiles, for minutes rather than seconds. The bar is: never stalled,
and the median barely moved.

### What p26 found — after its own stall detector was fixed (2026-08-16)

The first two runs are **void**. Both were measured through a 1.0 s operational
timeout against a 962.7 ms GETGRAPHICS — 26 ms of headroom — so "stalled"
frequently meant "was 30 ms slower than usual". That ceiling came from
`autodetect` handing its *scan* timeout to the bridge, which is a real app bug
in its own right (§16) and is very likely most of what "constantly hangs, reacts
slow" actually was. It surfaced only because p26 accused the *conservative*
profile of stalling in 8 seconds, which contradicts weeks of real use: a
detector that fails the shipping build is more likely broken than right.

Re-run with a 5 s operational timeout, so a stall means the device really did
not answer:

    conservative  5 min clean   131.6 ms, +0.0 drift, worst 132.2 ms   0 panel events
    fast          *** STALLED after 98 s ***  worst 161.7 ms          39 panel events

**The fast profile genuinely stalls.** Ninety-eight seconds, on GETGRAPHICS,
with a human working the front panel throughout and five seconds of grace before
the call was called dead. Its worst-case ALLTEXT also drifted up to 161.7 ms
against the conservative profile's 132.2 — the device visibly working harder
even when it was answering. So the revert in §15 was right, and is now backed by
a measurement rather than by a field report.

**What this run still does not show** is that the conservative profile is safe
*under the same load*: it recorded **0 panel events** during that phase, so
nobody was touching the panel while it ran. The probe says so in its own output
rather than letting a quiet run read as a pass — which is the one piece of
instrumentation today that behaved exactly as intended. Conservative-with-presses
remains untested; real use is the only evidence for it.

Both surviving comparisons still share a confound worth naming: presses were
happening during `fast` and not during `conservative`, so "fast timings" and
"someone at the panel" are not fully separated. What *is* separated is the
earlier pair — fast without the panel path survived five minutes clean, fast
with it stalled twice — which points at the interaction rather than at the
timings alone.

---

## 16. `--rig auto` ran with a 1.0 s operational timeout (2026-08-16)

`MidiBridge.autodetect` took a single ``timeout`` and used it for two unrelated
jobs: how long to wait for a probe reply from each candidate port during the
scan, and what the returned bridge uses for every real call afterwards. A scan
wants a small number, so it was 1.0 s. **A GETGRAPHICS takes 962.7 ms.**

Twenty-six milliseconds of headroom on every full refresh. Any jitter raised
`TimeoutError`, and `RefreshWorker._on_refresh_error` reads that as the device
having gone away: it flips the mirror to disconnected and backs off, doubling to
a 20 s cap. The result is a mirror frozen for up to twenty seconds, announcing
that the K2000 is missing, while the K2000 answers normally throughout.

This is almost certainly a large part of what §15 recorded as "constantly hangs,
reacts slow", and it is independent of the timing constants — which means the
revert there may have been fixing the wrong thing. It applies to anyone starting
with `--rig auto`, i.e. the normal way.

`scan_timeout` (1.0 s) is now separate from `timeout` (`DEFAULT_TIMEOUT`, 2.5 s).
`probes/hw.connect()` asks for 5 s so a probe can distinguish slow from dead. A
regression test asserts the bridge never inherits the scan value and that
whatever it does get clears a GETGRAPHICS with real margin.

**How it was found is the point.** Not by reading the code, and not from the
field report — by a probe producing a result that could not be true (the
shipping profile stalling in 8 seconds) and taking that seriously instead of
recording it. Two earlier conclusions had already been drawn through the same
ceiling.

---

## 17. "Disconnected" during a disk load — the device goes completely silent

Reported live 2026-08-16: starting a disk load makes the mirror announce a
disconnection. Harmless, since it reconnects, but wrong, and inconsistent with
every other disk operation.

It took four attempts, and the first three all failed the same way: each tried
to *recognise* the situation from something the device tells us, and during a
load the K2000 tells us nothing at all.

### The measurement that ended it

With a load in progress, an autodetect scan across **all 40 output ports found
no K2000**. Not a slow reply — no reply, from anywhere, for the whole multi-
minute operation.

That single fact kills three approaches at once:

1. **Matching progress screens** (`Opening file`, `Reading file`). Those appear
   on the LCD, not over MIDI. We never read them, so the marker list could never
   fire. Adding `Please wait` — the wording actually in use — changed nothing,
   because the problem was never the wording.
2. **A grace window before declaring a disconnection.** 12 s of tolerance does
   not cover a silence of minutes. No fixed number does.
3. **Reading the screen to learn the device is busy.** The detection depended on
   the very read that was failing. This is the one worth remembering: a signal
   that requires the cooperation of a device that has stopped cooperating is not
   a signal.

### What actually works

Once the device is silent, one thing still knows the difference between "busy"
and "gone", and it is not on the wire: **whether the ports we opened are still
enumerated**. Checked while a load was running — all present.

`MidiBridge.ports_present()` asks the system, sends nothing, and needs no help
from the K2000. The worker reports a distinct `waiting` state, and the title bar
says **`busy — not answering`** in yellow instead of `disconnected` in red,
clearing itself when the device replies. Confirmed on hardware.

**Verified:** the busy path, on hardware — a real load shows yellow
`busy — not answering` and clears itself when it finishes. **Not verified:** the
ports-gone path, which is synthetic-only. Exercising it means unplugging the
interface's USB, and replugging renumbers the ALSA clients (`56:x` -> `64:x`
happened twice on its own today), so it costs a rewire of the routing for one
boolean. Judged not worth it 2026-08-16; if the red `disconnected` state ever
looks wrong, this is the untested branch.

Deliberate limit: our ports belong to the MIDI *interface*, so a K2000 switched
off behind a live interface reads as busy rather than gone. That is the right
way round — calling a busy device "gone" cries wolf during every disk operation,
while calling a powered-off one "not answering" is merely coy. The elapsed-time
rule still applies when the ports genuinely vanish, or when a bridge cannot
answer the question.

### Still inconsistent, deliberately

Starting a load **from the app** trips the heavy-op guard (a soft key labelled
`Load`/`Save`/`Macro`/`Delete`) and pauses the mirror outright, needing a manual
`p` to resume. Starting the same load **at the front panel** now gets the busy
handling, which recovers by itself. Two paths to the same situation with
different behaviour. Left alone for now because the pause is the more
conservative of the two and nobody has complained, but it is a wart.

### The marker work is now mostly decorative

`is_busy_screen` only fires when we happen to read the screen, which during a
real load we do not. It is kept because it costs nothing and may catch shorter
operations, but it is not what fixed this, and it should not be mistaken for the
mechanism.

---

## 18. Driving the editor from the mirror — things learned doing it (2026-08-16)

A sibling project needed DSP parameters read off the K2000's own display. Doing
that end to end — disk browse, bank load, editor navigation, parameter sweep —
turned up several things worth keeping. No library, vendor or preset names here
by request; none of what follows depends on them.

### The editor's DSP pages are F1..F4, and their layout is fixed

The program editor's second soft-key page reads e.g.

    <more   F1 FRQ   F2 RES   F3 POS   F4 AMP   more>

F1..F4 are the four DSP function slots of the current algorithm, and the soft
label names what each slot *does* in this program (FRQ, RES, DRV, AMP, PCH,
WID, POS…). Each opens a page with the same eleven control parameters the manual
describes, laid out in two 20-column halves:

    Coarse / Adjust      Src1
    Fine                 Depth
    (FineHz, PITCH only) Src2
    KeyTrk               DptCtl
    VelTrk               MinDpt
    Pad                  MaxDpt

`soft_labels` finds them, and splitting each row at column 20 parses both halves
cleanly — the two columns are independent `label:value` fields.

### The parameter cursor is not in ALLTEXT either

§6 established that the *name-edit* cursor appears in neither device reply. The
same is true of the editor's parameter cursor: `get_screen_text_attrs` returns an
all-zero reverse mask on a DSP page. It is drawn in the graphics plane only.

Consequence for anything driving the editor: you cannot see where the cursor is,
so **locate it by acting** — nudge the wheel one click and see which field
changed. Cursor position after opening a page was consistently the top-left
parameter, with CursorRight moving to the right column.

### Reading a parameter's whole range without writing anything

The useful technique from this job. To learn a parameter's value scale, put the
cursor on it, turn the alpha wheel one click at a time reading the display after
each, then leave with **Exit → No**. The edit buffer is discarded and the stored
object is untouched — verified by re-reading afterwards.

This gets the entire curve from a single program, which is far better than
hunting for programs that happen to hold different values, and it costs nothing
because nothing is saved. It revealed that one K2000 depth parameter is
*piecewise*: coarse steps at the top of its range, a long linear middle, heavy
compression near zero, and a mirrored negative branch. Two sample points had
suggested a straight line and would have been badly wrong at the ends.

Generalisable: any "what does this byte mean" question about a program parameter
can be answered this way, as long as you exit without saving.

### Disk operations, measured

Confirms §17 with numbers:

* pressing **Load** — 27 s of total silence while the SCSI volume is scanned;
* a **15.8 MB bank load** — about 3 minutes of silence;
* a **56 KB programs-only load** — under 10 s;
* ordinary browsing (directory open, cursor moves, Cancel) — about 1 s.

Throughout, the ALSA ports stay enumerated, which is what `ports_present()`
relies on. A programs-only bank whose samples are all ROM references loads
without complaint and does not touch sample RAM.

### Master → Delete → Everything really does reclaim sample RAM

The counterpart to the DELBANK finding in §10, now confirmed from the other
side: the **front-panel** wipe took free sample memory from 1135K to 65536K,
i.e. it released everything. Our own F11 helper goes through DELBANK, which
frees program RAM but leaves sample RAM allocated. When sample memory is the
resource that is short — which is exactly when a large load has just refused —
the front panel is the route that works and the SysEx helper is not.

Worth remembering as a general shape rather than a K2000 quirk: a protocol-level
"delete all" and the panel's own are not guaranteed to free the same resources,
and the difference only shows up when you are short of the one that leaks.

---

## 19. Driving the program editor: layers, parameter entry, and two traps

§18 covered a first pass at reading DSP parameters off the display. A much longer
session against the same machine turned up the things §18 got wrong or missed.
Generic K2000 behaviour throughout; nothing here depends on the material.

### The algorithm and the DSP functions are PER LAYER

A program has up to seven layers, and **each layer has its own algorithm and its
own DSP chain**. One program observed with layers 1-2 on algorithm 21 and layer 3
on algorithm 13. Another with four layers running three different functions in
the F1 slot.

So "the algorithm of program X" is not well defined, and neither is "the filter
of program X". Anything reading program parameters has to iterate layers, and
anything correlating against stored bytes has to pair each byte with its own
layer's algorithm rather than the program's first.

This invalidated a whole afternoon of readings that were all silently layer 1 of
N — they were not wrong, but they described a slice, and the slice turned out to
differ from the rest.

### Layer selection: the Chan/Bank buttons

`<>Layer:1/7` in a page header marks it as steppable by **ChanBankInc /
ChanBankDec** — the same `<>` convention as `<>Channel:9` in Program Mode.
Stepping stays on the current page, so a reader can hold F1 open and walk every
layer without re-navigating.

### F1..F4 are control INPUTS, not chain positions

The soft row reads `F1 FRQ  F2 RES  F3 POS  F4 AMP`, and it is tempting to map
F*n* to the *n*th block. It does not. The PITCH block has its own dedicated soft
button, F1..F4 are the remaining **control inputs in order**, and a DSP function
with several inputs consumes several slots:

    alg  2   PITCH  2POLE LOWPASS  PANNER  AMP     F1 FRQ  F2 RES  F3 POS  F4 AMP
    alg 19   PITCH  LOPAS2  SHAPE MOD OSC  AMP     F1 FRQ  F2 PCH  F3 DEP  F4 AMP
    alg 28          SYNC M  SYNC S  LP2RES  AMP    F1 PCH  F2 PCH  F3 FRQ  F4 AMP

The two-input lowpass spans F1+F2; algorithms 26-31 have no PITCH block so F1
starts at the first block; a `NONE` block still occupies a slot and reads `OFF`.

### Type a value, do not step to it

Stepping a parameter with the alpha wheel **carries state**. Sweeping the
algorithm 1..31 with the wheel produced chains that disagreed with the same
algorithms reached directly, on more than half of them — changing the algorithm
preserves each block's function where the new chain permits it, so what you see
depends on where you came from.

Typing the number on the alphanumeric pad jumps straight there. For any
"enumerate a parameter's values" sweep: **type, re-entering the editor fresh each
time**, or the readings describe your path rather than the parameter.

Two related traps, both silent:

* **Parameter lists wrap.** Wheeling up from algorithm 31 lands on 1 with no
  indication, which silently ended a sweep early.
* **Program 199 is the factory default program** and makes a clean baseline for
  "what does this parameter look like untouched".

### Reading a parameter's full range, non-destructively

Put the cursor on it, step the wheel one click at a time reading the display, and
leave with **Exit → No**. The edit buffer is discarded; the stored object is
untouched. One program yields the whole curve, which beats hunting for programs
that happen to hold different values.

This is how the depth scale was found to be piecewise rather than linear. Two
sample points had implied a straight line.

### The parameter cursor is invisible to us

As with the name-edit cursor (§6), `get_screen_text_attrs` returns an all-zero
reverse mask on a DSP page — the cursor is drawn in the graphics plane only. So
a driver cannot see where the cursor is and must **locate it by acting**: nudge a
control, diff the screen, see what moved. On opening a page the cursor sits on
the first parameter, and CursorRight moves to the right-hand column.

### The display truncates at 40 columns

A long function name loses its tail: `F1 FRQ(PARA TREBLE` with the closing
bracket cut. The ALG page's chain line carries the untruncated name, so read
types from there.

### The left column is not a fixed parameter set

    FRQ  Coarse / Fine / -      / KeyTrk / VelTrk / Pad
    PCH  Coarse / Fine / FineHz / KeyTrk / VelTrk / Pad
    AMP  Adjust / -    / -      / KeyTrk / VelTrk / Pad
    AMT  Adjust / -    / KStart / KeyTrk / VelTrk / Pad

The first field is `Coarse` on frequency and pitch functions and `Adjust` on the
others; non-linear functions carry `KStart` where PITCH carries `FineHz`. Parse
by position within the 20-column half and read the label, rather than assuming a
key set.

### Units are per function, not per unit name

Worth stating because it caught us: a `dB` on one page is not the same encoding
as a `dB` on another. Amplitude and shaper depths read 1:1 with the stored byte;
filter resonance reads at half a dB per unit. Frequency depths are neither — they
follow a piecewise cents curve. **The unit has to be keyed off the function, and
the scale off the function too.**

### Overnight jobs do not belong in the session scratchpad

The scratchpad lives under `/tmp`, which on this host is a separate 4.7 GB volume
and does not survive a reboot. A long capture writing there lost everything to a
host power-cycle, despite flushing every row — guarding against the job stalling
does nothing about the file being deleted underneath it. Long-running artefacts
go under `~/temp`, detached with `nohup`, resumable, and `fsync` per record
rather than `flush`: after a power loss those are genuinely different states.

## 20. Bounds fitted to the tested case, and telling "not yet" from "lost" (2026-08-17)

An overnight capture run for the sibling project produced three findings that
are about *method* rather than the K2000, and all three cost real hours.

### A loop bound must come from the structure, not from the case that worked

The capture navigates the program editor by cycling the soft-key row until it
finds the page it wants. It allowed **four** presses. The editor has **six**
soft pages. Layers 1 and 2 happened to start from a page where four sufficed,
so the run looked healthy; **every layer-3 read failed**, 22 of them, and since
a failure broke out of the layer loop those programs silently lost layers 4+ as
well. The row count rose the whole time. It was the log, not the count, that
showed it.

Auditing the repo for the same shape found it in `text_entry._type_char`: a
flat budget of 12 presses against a digit ring of 10, with the letter branch
directly below deriving its bound correctly from `len(PAD_GROUPS[button]) + 1`.
Twelve is enough, so nothing was broken — which is what makes it worth fixing.
Nothing tied the number to the ring, so tuning it down for speed would have
broken 8 and 9 only, in names containing them only, on hardware only. Both
branches now go through `_passes()`: one reset plus a full lap, derived.

Same shape as the depth curve fitted across sampled points and read outside the
sampled range, and the same shape as the timing constants of §15, measured on
isolated operations and shipped for sustained ones. Three times in one night,
and in each case the narrowness was invisible from inside the fix.

### Reading a position back and then not acting on it

`type_name` reads every cell back — that is its entire advantage over
`plan_name`. Both multi-tap branches nevertheless *returned quietly* when the
cell never showed the wanted character, leaving a garbled name on the device
and reporting success. The caller's next move is Save. Where a function already
knows the answer is wrong, the only question left is whether the caller hears
about it; both paths now raise `NameEntryFailed`.

### A progress signal must distinguish "not yet" from "lost"

The consumer of the capture compared a denominator that was complete from the
first row against a numerator that filled in over hours, so every unfinished
layer read as MISSING. Two obvious fixes both have the same hole:

* **a `DONE` line in the log** — never written by a run that is killed, wedges,
  or dies to a power-cycle (which this one did, at 23:15). The consumer then
  waits forever and silently never flags anything.
* **a row-count threshold** — cannot tell a finished run from one that stopped
  one row short.

`status_watch.py` (with the capture under `~/temp/k2k_correlation`, not in this
repo — it is cross-project scratch) emits `state: running | complete | stalled` plus
`gaps_are_meaningful`, rewritten atomically (temp + rename, so a reader never
sees half a file). `stalled` fires after 300 s without the file growing, and it
is the state neither option above can express: **dead, not slow.** Waiting
silently on a marker that will never arrive is a worse failure than a false
alarm, because nothing surfaces it.

### Two wrong denominators is a cheaper diagnosis than one

Our expected row totals disagreed (184 vs 116 at layer 2) while agreeing exactly
at layers 3, 4 and 5 — which killed the obvious "you are missing a bank"
explanation and said the gap was scattered individual programs. Emitting a
per-program table turned a total-vs-total argument into a join, and the join
found the other side's number was stale, cached across the very fix that
invalidated it. Both now read 581.

What is left is better than the disagreement never happening: the layer count of
all 255 programs now has two independent derivations — read off the device here,
counted from `0x50` segments in the files there — that agree per program. Values
that outlive their evidence look exactly like values that are still true; the
only cheap defence is a second derivation from a different source.

### INFO does not pad a stored name — verified read-only

`probes/p28_name_padding.py` (2026-08-17, DIR → INFO, no writes) read names of
length 3, 4 and a full 16 off the device: `'VZ1'`, `'FGTH'`, `'Cymb.SoftMallet1'`.
**None came back padded.** INFO returns the name exactly as stored, so the
rename tool's trailing-blank strip is a no-op and the comparison against what
the user asked for is exact.

Worth having tested rather than assumed in either direction. Had the firmware
padded with blanks, the strip would have been the only thing preventing a
mismatch report on every rename of a short name; had it padded with anything
else, the strip would not have helped and the tool would have false-alarmed
every time. The check cost one read.

### The derived multi-tap budget holds on hardware, with one press of slack

`probes/p29_multitap_budget.py` (2026-08-17, Jan at the panel) drove the real
`type_name` into an open name dialog and counted the presses it actually spent
per character. 23 characters, ~97 pad presses: **nothing over budget, nothing
raised, not one dropped press.**

    digit n            n+1 presses      worst '9'  10 of 11
    3rd-in-group A-Z   3 presses        worst      3 of 4
    'Z' (ring of 2)    2 presses                   2 of 3

So the tight margin is **exactly one spare press**. A single dropped press is
absorbed silently; two within one character would raise `NameEntryFailed`. That
is the right shape — the raise is a last resort, not a routine event, so the
retry does not need to move inside `_type_char`.

Two things worth knowing for anyone re-running it:

* **`'0'` costs 9 presses, not 1, in that output** — and it is the probe's own
  fault, not the device's. Locating the cursor presses `Number0` twice, leaving
  the cell showing `'1'`, so reaching `'0'` cycles the long way round. It doubles
  as confirmation that the ring is ten long and wraps.
* **The cursor is measured, not assumed.** It cannot be read over MIDI, and every
  read-back in `type_name` is offset from it — one cell out and each character is
  verified against its *neighbour*, which is indistinguishable from the device
  dropping presses. The probe writes one character, diffs the field to see which
  column changed, walks the cursor to the first cell, and re-measures to confirm.

The first version of this probe gated itself on `stdin.isatty()` to enforce "a
human is watching". That is a proxy for the property, not the property: an idle
terminal has a tty and an attended run through a wrapper has none. It locked out
the very person it was written for. The gate is now an explicit `--attended`
flag — passing it *is* the human act.
## 21. MAC editor — the `.MAC` format, RE'd offline

Everything below was done **with no K2000 attached**, from the backup images in
`~/Dokumente/SYNTHS/K2000R/Backups/`. The byte-level layout has its own
document — [`MAC_FORMAT.md`](MAC_FORMAT.md); this section is the procedure and
what is still open.

### How the sample was obtained

`HD0_K2X_HD2G-*.img.lzo` is a **bare FAT16 volume, OEM `KMSI`** — no MBR,
512 B/sector, 32 KB clusters, 2 FATs. `mtools` refuses it (the BPB leaves
heads/sectors zero), so read the BPB and FAT directly; that reader is now
`k2kmaced/k2image.py`. Streaming `lzop -dc … | dd conv=sparse` keeps the
decompressed 2 GB image off the disk where it is all zeros.

The 2026-02 and 2025-05 images hold the **same** `BOOT.MAC` (300 bytes, 6
entries, OS v3.54); the 2025-01 image has none. That is the only real `.MAC`
available anywhere on the machine — no soundset on disk ships one — which is
why §5 of the format doc is hedged. It is checked in as
`tests/fixtures/BOOT.MAC` so the round-trip stays a regression test.

### What the first read got wrong

The 2026-08-02 note in TODO.md read the per-entry `u16` at offset 6 as a "load
id" and called `0x2A 00 01` an entry prefix. It is neither: `0x002A` is the
entry **length**, `0x0001` the **drive**, and the id-looking field is the
target **bank** (`0xFFFF` = Everything). The entry stride is therefore
`32 + even(len(path) + 1)`, fully determined, not a guess.

mpc2emu's `parsers/krz_parser._read_objects` was expected to read the container
as-is, and it does — it walks `BOOT.MAC` and reports `type 100, id 35, name
"Macro"` correctly, its conditional hash decode handling the >42 type. But it
is a private helper that returns *offsets* into the buffer, there is no write
direction, and a `.MAC` needs both. So `macfile.PramFile` implements the
framing directly (~60 lines), and mpc2emu is used for what it is uniquely good
at: parsing the `.KRZ` banks a macro *references*
(`k2kremote/mpc2emu_link.py`).

### Probes to run when hardware is authorised

Written 2026-08-02 as `probes/p24`–`p26`, following the house pattern; none has
been run. Only run them with a full backup present.

* **`p30_macro_dump.py` — RAM vs disk layout.** With Macro Record on and a
  known macro in memory, `DUMP` type 100 / id 35 (`MidiBridge.read_macro_table`)
  and feed the bytes to `MacroTable.parse`. If it parses and the entries match
  the front-panel display, RAM and disk layouts coincide and the app can read
  the live table directly; if it raises, diff the dump against the `.MAC` the
  same table saves to disk. This is a **read-only** SysEx op, but it still needs
  the mirror paused (§9: the heartbeat must not interleave).
* **`p31_macro_codes.py` — drive/mode codes.** From the front panel, set one
  macro entry to each of the 11 drives and 5 modes in turn, saving a `.MAC`
  each time; then read the `drive`/`mode` words back with `macfile`. Confirms
  or replaces the table in MAC_FORMAT.md §5. Front-panel work only — no SysEx.
* **`p32_macro_objlist.py` — object lists.** Record one entry with a
  selected-object list (`Open` a `.KRZ`, select objects, press `Macro`), save,
  and diff against the same entry recorded without one. `MacroEntry.extra`
  already isolates the surplus bytes.

### Writing back — deliberately not built

The tooling only ever writes a **new** `.MAC` on the host. It does not write
into a disk image, and it does not send a macro to the K2000. A wrong
`BOOT.MAC` is a boot that loads the wrong banks or none, and §9's lesson (the
K2000 locking up during object-destructive work) applies with more force to the
object the machine reads before anything else is loaded. Any future write path
should go through the same confirm-and-pause gate as the F11 tool.

### Writing back into the image: the narrowest operation that works

`mtools` cannot touch these volumes — confirmed on the real backup, not inferred:

    mdir -i hd0.img ::/
      → The devil is in the details: zero number of heads or sectors

The K2000's BPB leaves `sectors/track` and heads at zero (OEM `KMSI`), which
mtools treats as fatal. That left the macro workflow with no way back onto the
disk, so `k2kmaced/k2write.py` adds one — and its safety comes from the *shape*
of the operation rather than from care in the code:

* the target file **must already exist**, so no directory record is created and
  no free cluster is claimed;
* the new contents must fit the clusters that file **already owns**, so **the FAT
  is never written at all** — there is no code path that touches it, which a test
  asserts by comparing the FAT region byte-for-byte across a write;
* only two regions change: bytes inside those clusters, and the 4-byte size field
  of that file's own directory record.

A macro is ~300 bytes and a K2000 cluster is 32 KB, so `BOOT.MAC` always fits the
single cluster it already has. Shrinking leaves the surplus clusters allocated to
the file as slack — reachable only through it, with the size field marking the
end. Releasing them would mean editing the FAT, which is the one thing this is
built to avoid.

Kept in a **separate module** from `k2image` on purpose: that reader is what every
other tool depends on, and its "never writes" property is worth keeping literally
true rather than "true except for one method".

Two refusals worth keeping:

* **`.lzo` images.** `k2image` reads them by decompressing to a temp file, so a
  write would edit the copy and lose it at cleanup — a silent no-op, which is
  worse than an error.
* **Anything that is not a valid macro.** Parsed before the image is opened for
  writing, because an invalid `BOOT.MAC` fails at *boot*, far from the mistake.

The write verifies by reading the file back out and comparing. A write that
reports success without landing is the failure that costs a boot, so it is
checked rather than assumed.

### The in-place image write, verified on hardware (2026-08-17)

Run on Jan's real 2 GB image (`HD0.img`, raw, OEM `KMSI`), with his backup in
hand and at his explicit instruction. Its `\BOOT.MAC` is 868 bytes, **19
entries**, written by K2000 OS v3.87, one 32 KB cluster with 31,900 bytes slack.

**Two independent risks, and they are not the same risk.** Jan's framing, and it
is sharper than the one this was documented with: a bad macro means a bad boot,
but a *corrupted volume* means the K2000 does not recognise the disk at all.
Nothing on the host side can distinguish them.

**Test 1 — round-trip the unmodified macro.** Extract, install straight back,
compare the four regions any code path here can reach:

    bootsector      unchanged
    FAT             unchanged
    dir_record      unchanged
    target_cluster  unchanged

Byte-identical, including the cluster tail — the slack past byte 868 was already
zero, so the zero-padding was a no-op.

**Test 2 — one field changed.** `--rebank 2=900` moved entry 2 from bank 300 to
900; 18 of 19 entries untouched, still 868 bytes. Footprint after the write:
`target_cluster` CHANGED, everything else unchanged (the directory record does
not move because size is the only field written there, and the size was equal).

**Test 3 — the instrument.** Disk recognised, directory walked, `BOOT.MAC` found
and loaded to completion. Then `probes/p33_bankdir.py` over DIRBANK:

    bank 200  84 programs      bank 500  100
    bank 300   0  (empty)      bank 600  100
    bank 400  42               bank 900   75

Bank 300 empty and its 75 programs in 900 is exactly the edit, since entry 2 was
300's only source.

### Why the hardware was the only reader that could settle it

The post-write verification in `k2write` reads the file back through `k2image` —
**the same code that computed where to write it.** A misunderstanding of the
geometry would have written to the wrong offset and then read the wrong offset
back, reporting a clean success. `mtools` cannot arbitrate either: it refuses
these volumes outright.

The K2000's own FAT implementation shares no code with the writer, so "the disk
was recognised and the macro loaded" is the first check of this write that is not
circular. Same shape as the layer-count cross-check: what makes a second opinion
worth having is that it comes from somewhere else.

### k2kmaced itself, exercised on the real card (2026-08-17)

Beyond the write path above, the editor was driven against Jan's actual disk with
him at the machine — worth recording separately, because "the write primitive is
correct" and "the program is usable on real data" are different claims:

* the real `\BOOT.MAC` opened out of the image: **19 entries, 868 bytes, OS
  v3.87**, all 19 referenced files present;
* the `f` browser walked a genuinely large disk — **390 loadable files across 36
  directories** — which is the case the original flat OptionList could not serve
  and the reason it was replaced;
* an entry was repointed by picking a file from `\-AFRICA\`, a 20th entry added,
  and the result saved to a new `.MAC` (908 bytes);
* the instrument then booted from the edited image and loaded to completion.

**The TUI install route is verified too**, and by accident of sequence rather than
design: after the CLI restore the card was found holding a 908-byte, 20-entry
macro — Jan's own edit, installed through `w` -> `i` -> arm -> fire, md5 matching
the `.MAC` he had saved. So the gate, the dialog and the write all did run against
a real card, and the resulting image booted.

Worth keeping the sequence visible, because it corrected a claim written minutes
earlier in this file. The first version of this note said the keystroke route was
unexercised and argued it was safe because "the code underneath is the same" —
which is an argument, not a test. The test had in fact happened; nobody had told
the notes. A doc that reasons about coverage instead of checking it is wrong in
whichever direction the facts happen to fall.

### The selected parameter IS readable over MIDI — 0x16 / 0x17

**SysEx 0x17 requests the currently-selected parameter's NAME and 0x16 its VALUE.**
The vendored client has exposed both since it was imported, as
`get_current_parameter_name()` and `get_current_parameter_value()`. On a filter
page the K2000 answers:

    start         name 'Coarse:'   value 'E 4 330Hz'
    cursor down   name 'Fine  :'   value '0ct'
    cursor down   name 'KeyTrk:'   value '0ct/key'
    cursor right  name 'DptCtl:'   value 'MWheel'

So the parameter cursor is **directly readable** and never has to be inferred.
`probes/p36_filter_fields.py` now has `goto_field(bridge, "VelTrk")`, which walks
the page asking the instrument what is selected after every move and **refuses**
rather than guessing if the field is not there.

### How this was missed for a whole evening, which is the more useful part

§6 of this file says the name-edit cursor is exposed in *neither* device reply.
That is correct, and it is a statement about the **character position inside a
name field** — the underline in `Program Name: ____`. It was generalised to "the
parameter cursor is not readable over MIDI", and that generalisation was never
tested against the message table.

The cost, all in one session:

* a render-to-PNG-and-look loop, used as the only way to locate the cursor;
* 48 wheel clicks into `Src2`, which silently changed `AttVel` to `B Clk2` — the
  routing being measured — while the script reported the field it *thought* it
  was on;
* two velocity sweeps whose flat results were nearly filed as measurements, one
  of them with the cutoff still parked at the top of the filter's range from an
  earlier experiment;
* a "cursor is NOT on Coarse — stopping rather than guessing" guard, written to
  work around a problem that did not exist.

The guard was still worth having, and it is what eventually stopped the third
wrong write. But the lesson is narrower than "verify more": **a true finding about
a specific thing had been widened into a false claim about a general one, and the
widened version was never checked.** Two lines of the message table refuted it.

Anything driving the editor should use `goto_field` and assert the name the device
reports, not count keypresses.

---

## 22. The `data` field is left-aligned — both encoder and decoder were wrong

Found 2026-08-18 by reading the K2 SysEx spec (K2vx Musician's Guide **ch. 30**,
"Data Formats"), which is on this machine alongside the algorithm chapter:
`~/Seafile/Bibliothek/Handbücher/…/Synthesizer/K2000/30 SysEx.pdf`. **Read it
before reverse-engineering anything about the protocol.**

### The bug

The spec uses **two different bit alignments** and the vendored library implemented
only one:

* **numeric fields** (`type`, `idno`, `size`, `offs`) are *right* justified —
  "The significant bits are right justified in a field";
* the **`data` field** is *left* aligned — built "starting from the left, slicing
  off groups of 7 bits", with "the trailing bits … set to zero".

`decode_n` / `encode_n` pad at the **head**, which is correct for the first and
wrong for the second. It is invisible in nibble form, where 2 bytes per data byte
always lands on a multiple of 8 — but 722 data bytes in bit-stream form is 5776
bits carried in 826 seven-bit bytes, i.e. 5782, so two zero bits are inserted at
the front and **every byte is shifted by two**.

### Why it mattered more on the way out

`client.write` transmits in **bit-stream** form. So writing *any* object — a
program, a keymap, a macro table — would have sent a mis-packed payload into the
object database. The read side merely produced bytes that would not reconcile with
the same object read from a disk image; the write side would have corrupted it.

Fixed with `encode_data_field()` / `decode_data_field()`, used by `Load` and
`Write`. Validated three ways:

1. against the manual's own worked example (`4F D8 01 29`, given in both forms);
2. **against the instrument** — re-encoding what the K2000 sent reproduces its own
   payload byte-for-byte, 1628 bytes nibblized and 931 bit-stream, checksums
   matching;
3. both forms of one 722-byte object now decode identically, as the spec requires.

`form` selects packing, never content, so **identical output is the correct
result** — a difference between the two forms can only ever be a bug here.

### A second fault it exposed: two copies of `k2000`

`k2000` was **editable-installed from a sibling checkout** (`~/git-repos/k2000`)
while this repo also *vendors* a tracked copy in `k2000/`. Which one you imported
depended on the working directory: from the repo root the vendored copy shadowed
the install, so `pytest` and the probes used it — while the installed console
scripts, run from anywhere else, used the sibling. A fix applied here appeared to
have no effect there.

`pyproject.toml` already lists `k2000` among this project's packages, so the
sibling install was redundant as well as shadowing. Removed with
`pip uninstall k2000`. **If a fix to `k2000/` seems not to take effect, check
`k2000.__file__` from the directory the failing command actually runs in.**

### `text_entry.home_cursor()`

Added alongside, because the same session showed how a name gets garbled: the
K2000 **does not report the name cursor over MIDI at all**, so `type_name` takes
the offset from its caller (`start_col`). A caller that guesses writes each letter
one column away from where it verifies it, the correction loop never matches, and
every character is left on its group's *first* letter — typing `TEST` produced
`SDSS`.

`home_cursor` drives the cursor to offset 0 with `CursorLeft`, which **clamps** at
the field start, so it is idempotent and needs no screen read. It is **additive**:
nothing calls it yet. The app threads `NameCursor`'s tracked position and is
unaffected; this is for callers that did not open the dialog themselves.

---

## 23. Validating a converter against a full machine (2026-08-17)

The instrument was filled from its boot macro — eighteen bank files, 441 programs
— specifically to check a sibling project's field map against *diverse* material
rather than one soundset. What follows is mostly about how nearly every step
produced plausible wrong answers first.

### `Fill` ignores bank boundaries — so `id - base` is not a join

The macro loads three banks in *Overwrite* and the rest in *Fill*. Measured:

```
one 108-object file            ids 500 … 607     crosses the 599/600 boundary
the next file, entry says 600  ids 608 … 619     starts after the spill, not at 600
```

So **`Fill` continues from the highest occupied id**, and the bank number in a
macro entry is a starting hint rather than a destination. Computing a file's base
from its entry would have mis-joined **403 of 441** programs — every one landing
on a real program with a real name, i.e. silently.

Joining on the object **name** instead came out **441/441 exact**. Names must be
compared *verbatim*: they carry significant leading and trailing spaces, embedded
quote characters, and `0x7f` stereo-pair markers. Any `strip()` turns exact
matches into near-matches.

### Panel `Fn` = manual slot `n + 1`

The manual numbers DSP slots counting `PITCH` as slot 1 and the amplitude stage
last. The panel's `Fn` labels count only the blocks *after* `PITCH`:

| manual slot | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| panel | *(none)* | `F1` | `F2` | `F3` | *(amp stage)* |

Confirmed on 40 layer rows across 22 algorithm/chain combinations, and
independently from the byte side by the sibling project's own code join.

This matters because a slot's option **list differs per slot**: for algorithm 10,
slot 3 offers 16 functions beginning `LOPASS HIPASS ALPASS`, while slot 4 offers 13
beginning `LPCLIP SINE+ NOISE+`. Decoding a slot-4 code through slot 3's list
yields a wrong function *and* a wrong offset.

Consequence: for algorithms 17 and 18 **`F3` does not exist** — two DSP slots and
then the amplitude stage.

### The block chain is NOT a property of the algorithm

Setting an algorithm on a borrowed edit buffer draws its *default* chain. The same
algorithm in a real program draws a different one:

```
alg 17, borrowed buffer   PITCH  LOPASS  NONE          AMP
alg 17, a real program    PITCH  SHAPER  AMP MOD OSC   AMP
```

The algorithm fixes **topology** — slot count, widths, wiring — and each slot's
**function is selected per program**. An `algorithm -> filter_slots` table is
therefore not an answer to "does this program have a filter in slot 4", and a
sweep of the algorithms cannot produce one.

### The wiring is in the graphics plane

`ALLTEXT` gives block *names* only; the lines connecting them — the signal flow,
and whether a slot is single, double or triple width — are drawn in the graphics
layer (`GETGRAPHICS`, 0x18, ~960 ms). `x AMP` / `+ AMP` / `! AMP` are the only
hints text carries. `probes/p40_algorithm_pictures.py` captures both planes.

### Reading the chain: match a vocabulary, do not split on whitespace

Block names contain spaces (`AMP MOD OSC`, `2POLE LOWPASS`, `4POLE HIPASS W/SEP`),
so splitting the chain on whitespace mis-slots them. Matching against the set of
functions each slot is *allowed* to hold, longest option first, resolved 40/40
rows with every slot filled — and cross-validated the option table at the same
time, since no name appeared that the table did not allow.

### Four probe bugs, all of which returned correct-looking rows

Each needed an external contradiction to surface; none raised:

1. **`len()` of a tuple as a count.** `list_bank()` returns `(infos, done)`; bound
   to one name it reports `2` for every bank. Two banks "had 2 programs".
2. **First-match filter page.** Taking the first `Fn FRQ` label found hides the
   second filter — `PITCH SAW LOPASS LOPASS` has one in `F2` *and* `F3`. This
   reported two programs as contradicting a correct analysis.
3. **Layer 1 only.** Layers of one program carry different algorithms and
   different cutoffs. "This program's filter is in F1" is not a property of a
   program.
4. **A globally-ordered expectation.** Concatenating files in macro order ignores
   that they load into different banks. The tell was that mismatches began at
   exactly the first file's length, and the "wrong" name was the *correct* next
   file's first name — a disagreement that resolves into the right answer to a
   different question is a bug in the question.

### Round-tripping proves self-consistency, not correctness

The sibling's filter-code table was believed good on the strength of 581/581
agreement. The anchors from this session found a code mapped to the **wrong**
filter type and two codes **refused** outright. Both survive a round-trip
perfectly: re-reading what you wrote cannot detect either. Compare a green test
suite saying nothing about a dead branch, and a corpus gate whose measured effect
was exactly zero.

---

---

## 24. The SysEx spec was on this machine all along (2026-08-17)

Chapters 29 (MIDI) and 30 (System Exclusive Protocol) of the K2vx Musician's
Guide are at
`~/Seafile/Bibliothek/Handbücher/…/Synthesizer/K2000/30 SysEx.pdf`.
**Read chapter 30 before reverse-engineering anything about the protocol.** Several
things this project measured, argued about, or got wrong are stated there plainly.

### Confirmed by the spec

* Header is `sox(1) kid(1) dev-id(1) pid(1) msg-type(1) message(n) eox(1)` — so
  the device id is byte **2** and the message type is byte **4**, with byte 3 the
  constant product id `78h`. Matches `monitor.TYPE_INDEX = 4` (which was briefly 3).
* Device id: the instrument matches its own SysEx ID, *or* anything when its ID is
  set to 127. So 127 is a wildcard on the **receiving** side.
* `DIRBANK`/`READBANK` `bank` is a single digit **0–9**, or 127 for all banks —
  not an id base. Passing 200 raises, which is how this was found.
* DNAK codes: 1 being edited, 2 bad checksum, 3 ID out of range, 4 not found,
  5 RAM full.
* `ALLTEXT` returns **320** bytes (8 × 40); **a short reply means the screen was
  mid-redraw and should be re-requested** — a documented retry condition.
* `GETGRAPHICS` returns **2560** bytes, 6 pixels per byte in the low 6 bits.
* `PANEL` wheel delta is `byte − 64`.
* `READBANK` inserts a **50 ms** delay between `WRITE` messages of its own accord.

### Not in our object-type table

Master parameters are readable as **type 100, ID 16**, and cannot be reached with
any Bank message. `MacroTable` is *not* a documented object type, which is why
reading it returns something that does not parse as a macro.

### The two faults it exposed are recorded in §22

Reading this chapter is what found the `data`-field bit-alignment bug (both
directions) and, chasing why the fix appeared to do nothing, the shadowed `k2000`
package. Both are written up in **§22**, since they are core protocol/transport
faults rather than anything to do with the survey this section describes.

---

## 25. The live macro table, and the plan for editing it online (2026-08-18)

### It reads, and the layout is the file's

`Read`/`DUMP` of **type 100, id 35** returns `name='Macro'`, 814 bytes for a
19-entry macro. Those bytes are **byte-for-byte the `.MAC` container's object
block at offset 48** — checked against the same macro extracted from a disk image:
814/814 equal. `macfile.MacroTable.parse` reads it, lists all 19 entries, and
`serialize()` returns the input unchanged.

So the long-standing question in MAC_FORMAT §7 — does the RAM layout match the
disk layout — is **yes, for the Macro Table**. Programs and keymaps still differ;
this one does not.

Both transports agree: `Read` + `Nibblized` and `bridge.read_macro_table()`
(`DUMP` + `BitStream`) returned identical bytes. That is also a second, independent
confirmation of the bit-alignment fix in §22, through a different code path.

### Two ways to look at the right object and see the wrong thing

**Type 100 is the *Table* type, not "the macro type".** Several unrelated objects
live under it:

```
type 100 id 35 -> 'Macro'           814 B   the macro table
type 100 id 16 -> 'Master'          524 B   Master parameters (ch. 30 documents this)
type 100 id  1 -> 964 B, no ASCII           some other table
```

Reading id 1 and id 16 produced hundreds of bytes of plausible-looking object, and
that was briefly written up as "the macro table is not readable over MIDI and the
object route is a dead end". It was the wrong id, twice, on a type whose other
members answer happily. `ObjectType.MacroTable = 100` is *correct* as a type code
but reads as a promise about the id, which there is none of.

`Func:MACRO` showing `[ Off ]` does **not** prevent the read — the object exists
regardless; Off disables recording.

### Why online editing is worth building

`k2kmaced` edits `BOOT.MAC` offline and is hardware-verified, but on a modern rig
the K2000's disk *is* its SD/CF card, so using it means powering the instrument
down and pulling the card. The card shuffle is the slow, error-prone part — not
the editing.

The online route removes it: write the Macro Table object into RAM with the
machine running, then let the K2000 save its own `BOOT.MAC` from Disk → `Macro`.
No filesystem writing, no power cycle, and the instrument does the formatting.

### The panel route is the one to avoid

`Disk → Macro → Modify` opens a real edit page (`Modify:Drive` selects the
attribute, applied to "*1 entry selected*"), so panel-driven editing looks
feasible. It is not, safely: **SysEx 0x17 returns `'CurrentDisk'` for every cursor
position on that page** — a stale value from Disk mode. The parameter-name read
that lets `p39` refuse to type into the wrong field is unavailable there, so any
implementation would be counting presses while mutating the boot configuration.
That combination — unverifiable *and* destructive — is the one that produced four
separate bugs on 2026-08-17, each returning correct-looking rows.

The object route sidesteps it entirely: one `Write`, then read the object back and
diff it.

### Stage 1 (done): `k2kmacli live` and `k2kmacli diff`

`k2kmaced/online.py`, read-only, and deliberately thin because the offline parser
does the work:

* `read_live(bridge) -> MacroTable`, with errors that distinguish *nothing
  recorded* (empty object) from *wrong id* (bytes that do not parse) — since the
  second is the mistake actually made.
* `diff(live, other) -> [DiffRow]`, comparing the **rendered** entry and padding
  the shorter side with `None`. `zip()` would drop the tail, which is exactly
  where an appended entry sits.
* `k2kmacli diff` exits **1** on a difference, so it works as a scripted check.

Verified live: `diff` against the matching backup reports *identical — 19 entries
match*; against an older 6-entry macro it marks each differing row and pads the
missing six.

**`MacroEntry.extra` is not cosmetic.** A test was written asserting that a diff
could ignore it, and it failed — `extra` is where a **selected-object list** lives,
which makes an entry load particular objects instead of the whole file.
`display()` marks it `Obj`. So the diff reports it, correctly: two entries naming
the same file with and without an object list do not load the same thing. A byte
compare would also flag unknown padding (noise); a field compare ignoring `extra`
would miss the object list (not noise).

### Stage 3 (done): `k2kmacli push`, verified on hardware

**The encoder had to be fixed first, and it was worse than the decode bug.**
`encode_n` right-aligns the payload in a fixed-width field; the data field is
left-aligned with trailing zeros. `client.write` transmits in **bit-stream** form,
so writing any object — a macro table, a program — would have sent a mis-packed
payload into the object database. The manual's example: 4 data bytes must pack to
`27 76 00 12 48`, and the old path produced `04 7e 60 02 29`.

`encode_data_field()` fixes both call sites, and the check is as strong as one gets
without a second implementation: **re-encoding what the instrument sent reproduces
the device's own payload byte-for-byte** — 1628 bytes nibblized, 931 bit-stream,
checksums matching. Our packing and the K2000's agree exactly, both directions,
both forms.

**Verified end to end on the instrument (2026-08-18):**

```
push a one-field change (entry 2, bank 300 -> 900)
  read back .............. byte-identical to what was sent
  device's Macro page .... shows 900:O:      <- independent of our own read
restore the original
  live vs pre-test capture ... 814/814 identical
  live vs on-disk BOOT.MAC ... identical, 19 entries match
```

The read-back is the guard, not the `DACK`: a `DACK` says the message was accepted,
not that the bytes are right, and a mis-encoded write would leave the machine
booting something nobody chose while the macro page rendered it as intended.
`push()` therefore saves the previous table first, writes, reads back, and raises
`PushUnverified` unless the object matches — naming the backup in the message. An
empty table is refused by default, being indistinguishable from a bug that produced
no entries.

**The disk is never touched.** The instrument saves the table itself, and **it can
save under any filename** — so the safe order is push, save as e.g. `TEST.MAC`, try
it with Disk → Load, and promote it only when it works. A working `BOOT.MAC` never
has to be overwritten. That reframes the whole risk profile of the online route and
was not obvious from the offline tool.

### The full round trip, proven (2026-08-18)

Built offline → pushed over SysEx → **saved to disk by the instrument** → loaded
and run from disk:

```
k2kmacli new    one entry: \-ORGANS\ORG_E1.KRZ -> bank 800, Fill
k2kmacli push   read back byte-identical
Disk -> Save -> Macro -> All -> OK -> name -> OK -> "use current directory?" OK
   (device goes SILENT during the write -- §17; ~12 s, then returns to DiskMode)
Disk -> Load -> Root -> T.MAC -> OK -> "as specified" -> OK
   result: bank 800, previously EMPTY, now holds  800 'GARAGE ORGAN'
```

Nothing was overwritten: the save created a new file (root went 25 → 26 entries),
which is the `\BACKUP\`-style discipline working in practice. The macro table was
restored afterwards, byte-identical to the pre-test capture.

### The save flow, and the naming dialog's real model

`Disk → Save` offers `Export | Macro | Object | NewDir | OK | Cancel`. Choosing
`Macro` shows the **live** table (another confirmation that `push` reached it),
then `All` → `OK` opens the filename editor:

```
Save as:        WAVSTFAV
Delete Insert >>End  Choose  OK   Cancel
```

Two things about that editor cost time and are worth knowing:

* **It pre-fills a stale name** from an earlier buffer. Pressing `OK` straight
  through saves under whatever that was — here `WAVSTFAV.MAC`, which has nothing
  to do with the macro being saved. Always set the name explicitly.
* **`Delete` removes the character to the RIGHT of the cursor**, so the first
  character can never be deleted, only changed — a loop that deletes until the
  field is empty never terminates.

**The character model is NOT multi-tap, and `text_entry.type_name` does not work
here.** Measured directly: key `8` cycles `V → W → X → V`, key `3` gives `G → H`.
So **each number key selects a 3-letter group** — key *k* covers letters
3(*k*−1)+1 … +3 (1→ABC, 2→DEF, 3→GHI, 7→STU, 8→VWX) — the chosen letter
**replaces** the character under the cursor, and **the cursor does not advance**.
Multi-tap assumes repeated presses of one key walk a group *and* that the cursor
advances on a different key; neither holds. `type_name("TEST")` produced `WSDSS`.

Whatever automates saving needs a small dialog-specific driver: position the
cursor explicitly, press the group key the right number of times for each letter,
and move with `CursorRight` between characters. That is the real work in the
"rename before saving" item, not the renaming.

### Stage 2, when picked up

Triggering a load from the computer is **proven manually** (2026-08-17) but not
implemented as a command: `Disk → Load → Root → BOOT.MAC → OK → "as specified" →
OK`, reading the screen before every press. Two cautions for whoever writes it:

* `LoadMacro` (0x10) replays *the macro currently in memory*, which is **not** the
  same as loading one from disk. Firing it when RAM holds something unexpected is a
  wipe followed by an unknown load.
* The macro page's own `Load` soft key prompts *"Load current item or all items?"* —
  and that prompt **can** be cancelled cleanly (tested), so it is a genuine confirm
  step rather than a point of no return.

With stage 3 done, stage 2 is a convenience rather than a requirement: `push` plus
the instrument's own save covers the workflow that mattered.

---

---

## 26. Two undocumented SysEx types, and why saving still needs the panel (2026-08-18)

### `0x12` / `0x13` — an undocumented memory query

Chapter 30 documents `0x00`–`0x11` and `0x14`–`0x19`. **`0x12` and `0x13` are
absent from the manual but real**, and they are a request/response pair:

```
->  f0 07 00 78 12 f7                       (no body)
<-  f0 07 00 78 13  00 03 1e  00 05 22  f7  (two 3-byte 7-bit values)
                    = 414      = 674
```

Correlated against the Disk-mode header `Samples:1349K   Memory:414K`:

| field | value | meaning |
|---|---|---|
| 1 | 414 | **program RAM free, in K** — exact match, repeatedly |
| 2 | 674 | **sample RAM free, in 2K units** — 674 × 2 = 1348 ≈ 1349K displayed |

`0x13` sent bare gets no reply, consistent with it being the *response* type.

The unit on field 2 rests on one screen comparison (674.5 exactly halves the
displayed figure), so treat "2K units" as strongly indicated rather than proven —
a load or delete large enough to move sample memory by megabytes would settle it.

Useful because it is far cheaper than `ALLTEXT` for a free-memory check: no 320-byte
screen transfer, and it works in any mode rather than only on the Disk page.

### There is NO save-to-disk message, and no message carries a filename

Worth stating flatly, because it is the natural thing to want. The full message set
addresses the **object database** (`Dir`, `Info`, `New`, `Del`, `Change`, `Read`,
`Write`, the Bank messages) plus the panel and screen. Nothing writes a file,
names a file, or triggers a Save. `LoadMacro` (0x10) loads *from RAM*, not disk.

So persisting a macro requires the panel. **But the common case does not need
persistence at all:** `push` + `LoadMacro` loads the files a macro names, straight
from RAM. That is not a workaround — it is Kurzweil's own documented technique for
automating macro loading from a sequencer: the macro object is sent as SysEx,
replacing whatever is in the Macro Recorder, then the Load Macro command makes it
execute. `MacroDone` (0x11) acknowledges completion with a status code, which is
better than the panel route, where a load must be waited out blind.

### `Choose` in the save dialog is a real browser — pointed at another drive

The filename dialog's `Choose` key opens `Choose file name:` with `Root` / `Parent`
navigation. It first appeared to list a single phantom file (`IDALL.KRZ`, 1251K)
that exists nowhere in the SCSI 0 image, and the wheel would not move.

Explanation: **it had opened the floppy drive**, where that bank is the only file —
so the listing was correct and complete, just for a different drive. It is
therefore a usable way to set a filename by picking an existing one, with no
character entry at all, provided the drive is set first. Do not conclude "phantom
entry" from a listing that does not match the drive you had in mind.

### `type_name` is not broken — the caller must supply the cursor offset

`type_name(bridge, "TEST", name_row=3, name_col=16)` produced `WSDSS` in the save
dialog, which was briefly written up as the function being wrong for that dialog.
It is not.

Both dialogs share the same character model, measured directly:

```
object Name dialog   key 8 -> v, w, x     key 3 -> g, h
Disk save dialog     key 8 -> V, W, X     key 3 -> G, H
```

Each number key selects a **3-letter group** (key *k* → letters 3(*k*−1)+1 … +3),
the letter **replaces** the character under the cursor, and **the cursor does not
advance** — which is exactly what `_LETTER_TAPS` and `_type_char` implement.

The failure was `start_col`. `shown()` reads `name_col + start_col + col`, and after
several `Delete` presses the cursor was parked at offset **1**, not 0. So each letter
was written at column *n*+1 while being verified at column *n*: the check never
matched, the loop pressed the group key to exhaustion, and each character was left
on its group's **first** letter — `S, D, S, S` for `T, E, S, T`. The docstring warns
about exactly this.

**Fix: home the cursor before typing** rather than assuming it. `CursorLeft` clamps
at the field start, so pressing it field-width times is sufficient and idempotent.
Two further quirks of these dialogs:

* `Delete` removes the character to the **right** of the cursor, so the first
  character can never be deleted, only overwritten — a "delete until empty" loop
  never terminates.
* The field arrives **pre-filled**, and the default is *derived from content* (it
  offered `WAVSTFAV` for a 19-entry macro and `ORG_E1` for a one-entry one). Pressing
  `OK` straight through therefore saves under a plausible but unintended name.

### `CurrentDisk` changes under you — and a save follows it silently

The single most dangerous thing found while automating the save flow.

Opening the filename dialog's `Choose` browser and navigating in it **changes the
Disk page's `CurrentDisk` parameter, and leaves it changed** after you cancel out.
On this rig `Choose` opened the Floppy, and `CurrentDisk` then read `Floppy`
indefinitely — so the *next* save went to the floppy, while the confirm prompt said
only `Use current directory for TESTMAC.MAC? (Path = \)`. The path is shown; **the
drive is not**. The same applies to the Delete browser, which then listed the
floppy's files and looked wrong until the drive was checked.

That means a macro save can land on an entirely different disk than intended, with
nothing in the prompt to reveal it. Anything automating a save **must read
`CurrentDisk` and set it explicitly** rather than assuming, and should re-read it
after any browser excursion.

It is readable and settable over MIDI without press-counting: the Disk page's field
reports as `('CurrentDisk', 'Floppy')` through 0x17/0x16, so a driver can walk the
cursor until the device names the field, then wheel until the device reports the
wanted drive. That is how it was restored to `SCSI 0` here — no counted presses.

This also explains the `Choose` listing that appeared to be a phantom: it was the
floppy's only bank, correctly listed, on a drive nobody had chosen deliberately.

### The save flow, end to end, as verified

```
CHECK CurrentDisk first (0x17 on the Disk page) -- do not assume
Disk -> Save -> Macro -> All            -> filename editor
home_cursor(bridge, width)              -> cursor to offset 0; do NOT assume it
type_name(bridge, "TESTMAC", ...)       -> verified: field read back as TESTMAC
OK -> "Use current directory ...?" -> OK -> written (device silent ~10 s)
```

Delete, for cleaning up afterwards, is `Disk -> Delete`, then `CursorDown` to the
file (**the alpha wheel does not scroll this browser**), `Select` to mark it — the
name gains a `*` and the header shows `Sel:1/26` — then `OK` and `Yes`. Always
assert the selected name before confirming; the browser opens on whatever drive
`CurrentDisk` points at.

---

## 27. The K2000's LCD truncates a path with `..` — and the browser was trusting it (2026-08-18)

A live macro table carried an entry with path `..\-SLAP\`, pointing at nothing.
The file is real: `\-BAESSE\-SLAP\E3_SLAPB.KRZ`, verified against the disk image.
One directory component — `-BAESSE` — was simply missing.

### The cause

`DiskBrowserScreen` read the current directory back from the device after every
navigation, via `disk_browse.current_path()`, which parses the `Dir:` field of
the panel header. Reproduced live:

```
after entering -BAESSE, raw header: 'Dir:\-BAESSE\     Sel:0/6    Index:   1'
after entering -SLAP,   raw header: 'Dir:..\-SLAP\     Sel:0/6    Index:   1'
```

**The K2000's 40-column header truncates a path that does not fit, and marks
the cut with a leading `..`.** That is the device's own ellipsis convention —
"there is more before this" — not a literal parent-directory reference. Reading
it back verbatim and storing it as a macro entry's path produced exactly the
corrupted entry found live. The device does not validate a macro entry's path
at write time, so nothing complained until the entry was loaded.

### The fix

The screen already knows, by name, every directory it has entered — it chose
each one from a listing to get there. There was never a need to ask the device
what the resulting path is. `disk_browse.descend(path, name)` and
`disk_browse.ascend(path)` are pure string operations that compose the path
from what the caller already knows, and `DiskBrowserScreen` now uses them
exclusively — a source-inspection test asserts `current_path` never appears in
its methods again.

`current_path()` itself is kept, since it remains useful for a human reading the
screen, but its docstring now states the trap explicitly rather than leaving the
next caller to rediscover it.

Verified against the real captured names: `descend(descend("\", "-BAESSE"),
"-SLAP")` gives `\-BAESSE\-SLAP\`, matching the file's actual location exactly —
where the old code gave `..\-SLAP\`.

### The general shape

This is the same class of bug as the Macro page's `0x8000` selection flag (§21)
and the `CurrentDisk` repointing (§25): **trusting a device's rendering of state
as the state itself**, when the rendering is a display convention rather than a
faithful readout. The K2000's screens are built for a human at a 40-column LCD,
not for a caller expecting a machine-readable value — the panel truncates,
abbreviates and flags things for legibility, and each of those has now cost a
silent corruption once. A caller that can track its own state should, rather
than asking the panel and trusting the answer is complete.

---

## 28. Silent notes: TRANSMIT vs RECEIVE channel, and a fault no SysEx could see (2026-08-19/22)

For a cross-project A/B capture with mpc2emu (K2000 vs their KRZ→AKAI conversion
of PMVOL124), the K2000 stopped making sound entirely — mid-session, after a
routine power cycle to clear an orphaned-sample-RAM error. What follows is the
chase, because every step eliminated a real possibility with a measurement, and
that discipline is what kept a two-day gap from costing a wasted evening at
either end.

### `Channel:9` in the panel header is the TRANSMIT channel, not RECEIVE

The single most useful fact to have written down. `ProgramMode`'s header, and
the `MIDI` button's default page, both show `Channel:9` — and it is easy to
assume that is "the channel this instrument listens on." **It is not.** Press
`MIDI`: the page opens on `MIDIMode:TRANSMIT`. The receive settings are a
separate soft key:

```
MIDIMode:RECEIVE
BasicChannel:8    SysEx ID:0
MIDI Mode:Multi   SCSI ID:6
```

`BasicChannel` reading `8` while notes are correctly received on channel 9
looks like a mismatch and is not one: with `MIDI Mode: Multi`, `BasicChannel`
does not govern local play at all. The operative setting is the **`CHANLS`**
page — a full per-channel map, one row per MIDI channel, each with its own
`Enable` / `Program` / `Volume` / `Pan` / output routing. Landing the cursor on
channel 9's row and reading it back (device-confirmed, not assumed) is what
actually answers "will a note-on on channel 9 be heard, and by which program":

```
Enable :On   Program:200*Med. RainStick 1   Volume:127   Pan:64   OutPair:Prog
```

So there are **three different "channel" readings on this instrument**, and
only one of them is what a note-on needs: the panel header (transmit), `RECV`'s
`BasicChannel` (a fallback, overridden in Multi mode), and `CHANLS`'s per-row
`Enable`/`Program` (what actually matters). SysEx proves the wire and the
device id; it says nothing about which of these three a note-on will be judged
against, because SysEx carries its own device id and is channel-independent —
a confirmed object selection proves the cable works and proves nothing about
whether note-on will be heard.

### The `A(FX)` vs `B(DRY)` output-routing test — a good hypothesis, correctly ruled out

The program editor's `OUTPUT` page shows a `Pair` field per layer (`A(FX)`,
`B(DRY)`, and others reachable by wheel). A program's output routed through the
internal effects bus rather than a dry pair is a real, previously-unconsidered
failure mode, and worth testing directly: enter the edit buffer, confirm the
field via `0x16` before touching it, change it, play a note, measure, and —
regardless of the result — **exit without saving** (`leave_editor`, which
answers any save prompt with `No`) and re-read the field fresh to confirm it
is unchanged. Both `A(FX)` and `B(DRY)` gave identical silence, which correctly
ruled the internal FX bus out rather than leaving it as a live suspect.

### The actual fault: an external unit, powered off, sitting in series

None of the above was it. An external effects unit sits physically between the
K2000's output and the audio interface's ADAT expander. It was off — probably
since the power cycle that cleared the sample-RAM error. With it in series
(not on a parallel send/return), it blocks **everything** leaving the K2000
regardless of the K2000's own internal routing, which is exactly why the
`A(FX)`/`B(DRY)` test showed no difference either way: both signals had to
pass through the same dead box.

**No SysEx read, no port scan, and no amount of panel navigation could have
found this.** It is state that exists entirely outside the K2000's own object
model — a box on a shelf with a switch. It was found by direct physical
inspection, and by nothing else, after every softwareside hypothesis had been
correctly exhausted.

### The lesson worth generalising

Every wrong hypothesis here was eliminated by a *measurement*, not by
argument: the receive channel by reading `CHANLS` rather than trusting the
panel header; the FX-bus routing by an edit-buffer test with before/after
readback; the capture ports by scanning all twenty rather than assuming 17/18
were still correct. None of those measurements cost a second pass, because
each gave a clean yes/no rather than a plausible-sounding guess. The one thing
that could not be reached this way was **what physically sits in the signal
path** — a purely SysEx-and-panel picture of "K2000 → interface" has no slot
for a third box in series, and that is worth remembering the next time
something measures correctly at both ends and is still silent in the middle.

### A stale edit session, caught by re-verifying rather than trusting a read

A minor process note, folded into the FX investigation. A diagnostic script
opened the `OUTPUT` page, printed it, and exited by closing the MIDI
connection — **without** pressing `Exit` first. A later script then called
`select_program()` (digit presses + Enter) while the device was silently still
sitting in that abandoned edit session; the digits landed as direct-entry
shortcuts into whatever field the stale cursor was on, and the next read came
back showing an unrequested value (`D(DRY)` where `A(FX)` was expected — a
field mutation nobody intended). Caught only because the practice throughout
this project is to force back to a known state and re-read fresh before
trusting anything, rather than act on the first answer. Left as unreported, it
would have looked like discovered evidence of a routing fault the read had
itself caused. **Always leave an editor via `Exit`, even when a script's job
is "just read one page."**

### `probes/p41_pmvol124_capture.py` — the two capture guards, now reusable

Written for this session and worth keeping generally: `confirm_selection()`
asks the device what is currently selected (`0x16`, `<id>*<name>`) before a
group of takes rather than trusting the command that set it, and
`lift_over_preroll()` requires each take's note region to sit measurably above
that *same take's own* pre-roll silence — not an absolute threshold, and not
"did it clip" (silence never clips). Both guards were exercised for real
during this session: the first capture attempt hit the lift gate immediately,
on the very silence this section is about, and refused to write a bad take
under a real filename. That refusal is what turned "captures failed silently"
into "captures failed loudly, with a diagnosis to follow."

## 29. ALLTEXT confidently reports blank on a populated field (2026-08-22)

While gating a recapture on mpc2emu's corrected `CUTCAL_01` bank (see §28's
sibling capture work), `probes/p36_filter_fields.py`'s panel-navigation helpers
(`select_program`, `algorithm_of`, `rows()` — all built on `get_screen_text()` /
ALLTEXT, `0x15`) suddenly returned an unreadable screen: the `ProgramMode`
header showed, and the soft-key row showed, but the field between them that
normally carries `<id> <name>` came back as **spaces**, and digit presses that
should have echoed into a program-number field did nothing visible at all.

This looked exactly like a stuck panel or a failed disk load, and — per the
project's standing rule about not blind-pressing buttons on real hardware
without a working feedback loop — work stopped rather than guessing further
(the stale-edit-session mutation in §28 is what that rule exists to prevent).
Jan was asked to look at the actual LCD. **It read `Program 300 CUT 000` —
correct, populated, unremarkable.** ALLTEXT was reporting blank for a field the
device was actively displaying.

The defect is narrower than "ALLTEXT is broken": the soft-key row (row 7) and
the rest of the header text around the gap were reading correctly throughout,
both before and after this happened — only the specific `<id> <name>` field
inside the `ProgramMode` header came back empty. The capture pipeline itself
was unaffected, because `probes/p41_pmvol124_capture.py`'s `select_program()`
(digit button presses, no screen read) and `confirm_selection()` (`0x16`/`0x17`,
"what is currently selected") never touch ALLTEXT at all — that is why the
actual CUTCAL recapture and its panel-verified `Coarse:` cross-check
(both `0x16`/`0x17`-based) worked cleanly through the same session where the
ALLTEXT read was silently wrong.

**Not root-caused.** Open questions: what triggers it (something about the
Gotek/disk-reload sequence was the only thing that had just happened, but that
is a correlation, not a demonstrated cause); whether it is transient (did not
retest after the fact, since the working `0x16`/`0x17` path was sufficient to
finish the task); and whether any other ALLTEXT-dependent code path in this
project — `refresh.py`'s mirror, the disk browser, the macro editor's on-screen
state — can hit the same blank-field failure silently, since none of them
currently cross-check against a second read path the way this session
accidentally did. Tracked in TODO.md; no probe written yet.

The shape of the catch is the same one running through the whole CUTCAL
session (§28's sibling capture and the filter-uniformity misdiagnosis this
afternoon): a reader that returns a confident, well-formed answer disagreeing
with the device is not "known-broken", it is *worse* — it looks exactly like
data until something outside the read path (a human at the panel, a second
SysEx query) contradicts it.
