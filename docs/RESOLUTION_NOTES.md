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

**Update, same evening:** recurred with no disk reload anywhere nearby —
during the ENV2/LFO1 depth work below, a plain `select_program()` (digit
presses + Enter) on an already-loaded program produced the identical blank
`ProgramMode` field, confirmed via `0x16` that the selection had genuinely
worked (`'305*CUT 050'`) while `rows()` still showed nothing. So the earlier
"correlated with the Gotek reload" framing was too narrow — correlation with
*that one instance* was real, but the trigger is broader than disk activity.
Still not root-caused.

The shape of the catch is the same one running through the whole CUTCAL
session (§28's sibling capture and the filter-uniformity misdiagnosis this
afternoon): a reader that returns a confident, well-formed answer disagreeing
with the device is not "known-broken", it is *worse* — it looks exactly like
data until something outside the read path (a human at the panel, a second
SysEx query) contradicts it.

## 30. Two more unverified `krz_writer` constants, measured on hardware (2026-08-22)

mpc2emu's converter carried two more self-flagged `approx` byte-to-real-unit
mappings — `hob_f1[6]` (ENV2->FilFreq depth) and `cal[22]` (LFO1->Pitch
depth) — never checked against a real K2000, same shape as the CUTCAL
cutoff-byte bug in §28/29's sibling session. Both needed a program with a
real modulation routing wired up; none existed, so this session built one:
**program 250**, a ROM `Sawtooth` keymap (id 151) through algorithm 1's
4-pole lowpass (base cutoff 1047Hz), `F1 FRQ` `Src1=ENV2` and `PITCH`
`Src1=LFO1` both wired at Depth 0. Built by editing ROM object **199**
("Default Program", the K2000's own scratch template) and Save-As-ing to
250 — 199 itself was never saved over.

### The panel does not show a live envelope-modulated value

Tested directly before trusting anything: held a note for the full 3s hold
at max `ENV2->FilFreq` depth (10800ct = 9 octaves) and read `Coarse` on the
filter page throughout SysEx `0x16`/`0x17` — never moved off the static
1047Hz setting. So unlike CUTCAL's `Coarse`-is-the-parameter check, both
depth measurements had to be audio-only (see the WAV analysis below) or
correlated against the raw object bytes (see the tables below) — never
against a live panel readout, because there isn't one.

### The wheel accelerates non-linearly, and a naive step-size guess crashes

First attempt at a closed-loop `Depth` setter clamped each wheel turn to
+/-8 clicks, on the assumption of ~2ct/click measured from a handful of
isolated single clicks. Real behaviour: 63 clicks in *one* message went
0->3500ct, and the *next* 63-click message (same direction, no pause) went
3500->10400ct — not a fixed rate, and history-dependent. The +/-8 version
oscillated and never converged on a target, hitting its iteration cap with
nothing corrupted (parameters are freely re-editable) but nothing swept
either. Fixed by dropping to **exactly one click per step**, always,
verified against the actual screen/`0x16` value before deciding the next
direction — slower, but every single-click sequence tested was linear with
no drift, because the acceleration is a property of *turning fast*, not of
*being told to turn far*.

Separately confirmed (Jan's own observation, not derived): the *displayed*
cents-per-click size is genuinely non-uniform and native to each parameter
— 2ct/click near zero on `ENV2->FilFreq` Depth, growing to 5ct/click by the
15th consecutive click, `ct = (byte-28)*100` exactly from byte 34 onward.
This is the real mechanism; "wheel acceleration" in the paragraph above was
this session's misreading of the same underlying curve as a *message-timing*
artifact rather than the *field's own* per-step design.

### A sawtooth's own 1/k spectral rolloff defeated the corner detector once, cleanly

First pass at measuring `ENV2->FilFreq`'s corner shift reused CUTCAL's
Welch-PSD + threshold detector unmodified. Result: an **identical** ~1046Hz
corner at all seven tested depths from 0 to 4800ct — a monotonic parameter
sweep producing a flat result, the exact signature (per mpc2emu, independently
naming the same tell from `PITCH NONE AMP` and the 126Hz latch in §28/29)
of "the measurement cannot move regardless of the parameter." Cause: a
sawtooth's own spectral envelope falls ~1/k regardless of any filtering, so
raw harmonic-4 magnitude was already below a flat threshold from source
rolloff alone, identically at every depth. Fixed by multiplying each
harmonic's magnitude by its index `k` before thresholding (flattens the
passband so a crossing only trips on the filter's *own* rolloff). Analysis
kept as a **separate pass** over already-captured WAVs from then on — once
bitten twice, capture is now decoupled from analysis on principle, so a bad
detector never requires re-touching the hardware to fix.

### Filter depth: valid to ~2.25 octaves, then the source itself runs out

Once corrected, `ENV2->FilFreq` depth measured cleanly from 0 to 2400ct
(0 to 2.248 octaves, not a straight line: exact at 1200ct, under at 600ct,
over above that — but each point sub-one-harmonic-bin at the low end, so
only the 2400ct deviation is likely real). 3600ct and 4800ct both measured
an *identical* 6537Hz "corner" — not the filter: raw harmonic data shows a
>25x cliff between harmonic 24 (6275Hz) and 28 (7321Hz), flat near-noise-
floor to 22kHz regardless of depth. The ROM `Sawtooth` sample is itself
bandlimited around 7kHz (ordinary anti-aliasing for a wavetable played
across octaves), so nothing above that is measurable with this source
regardless of how far the filter opens.

Byte<->cents for `hob_f1[6]`, correlated by diffing `DUMP` reads of program
250 at known panel Depth values (RAM offset 215; **unverified against the
on-disk `.KRZ` layout** — programs are known to differ between RAM and disk
per §21/§25, and mpc2emu confirmed afterward that the offset didn't matter
to them, since the byte<->cents *mapping* is a property of the parameter,
not of where either side stores it): dense 0-49 (2100ct), sparse to 124
(9600ct) fitting `ct = (byte-28)*100` exactly throughout, coarsening again
for the last three bytes to the true ceiling — **byte 127 = 10800ct =
exactly 9.000 octaves**, confirmed by single-clicking there directly rather
than trusting an earlier big-jump-to-max test. That number is what let
mpc2emu find their own bug: their writer's `round(amount*127)` assumed 127
was cents-linear full scale, when the real curve is compressed near zero —
subtle filter envelopes (`amount` 0.05-0.25) were written **3x-26x too
shallow**, while `amount=1.0` was **1.75x too deep** against their own E4XT
reference (5.14 octaves). Both directions wrong, from one wrong assumption
about one byte's meaning.

### Pitch depth: a different curve, audio-confirmed at both ends

`LFO1->Pitch` Depth (RAM offset 199, same disk-offset caveat) mapped fully
dense, byte 0 to its own ceiling at byte 123 = 7200ct = 6 octaves — a
*different* law from the filter's: 1:1 (byte N = N cents) up to byte 20,
not compressed the way `hob_f1[6]` is near zero. mpc2emu's writer maximum,
byte 79, lands at exactly **1200ct = 1.000 octave**.

Audio cross-check (autocorrelation pitch-tracking over a held note, LFO1's
own 2Hz giving ~6 cycles across a 3s hold) confirmed the panel's Depth is a
**+/- half-swing, not full peak-to-peak**: byte 79 measured 2404.7ct
peak-to-peak against an expected 2400ct (2x1200), byte 41 (80ct) measured
161.4ct against an expected 160ct — both within 0.5%, once a first pass's
`fmax=500Hz` search-window clipping (caught because the reported peak
landed *exactly* on the window's own boundary) was widened and re-run on
the same already-captured WAV. Byte 4 (the value mpc2emu's *old* buggy
writer actually wrote for a "half amount" request) measured 9.5ct
peak-to-peak, but that number is **below the tracker's own resolution
floor** — at ~262Hz, adjacent whole-sample lags in the autocorrelation are
already ~9-10ct apart, so a true 4ct swing cannot be resolved by this
method at all. A parabolic sub-lag interpolation attempt made the same
measurement *worse* (25.5ct on the identical file) rather than better, and
was reported as a failed refinement rather than presented as an improved
number. What stands: byte 4's measured swing is ~17x smaller than byte 41's
clearly-resolved one, consistent with (not proof of) mpc2emu's "no audible
vibrato" characterisation of the old bug.

mpc2emu independently confirmed the LFO1 full-scale question the same way:
their own E4XT reference constant (`LFO_PITCH_FULL_CENTS = 1593`, ±16
semitones) already carried a comment reading, verbatim, *"NOT the ±1 octave
previously assumed"* — the disproof of their writer's own assumption was
sitting in the same source file as the bug.

## 31. `patch_object_bytes` / `read_object_bytes` — DUMP/LOAD instead of the panel (2026-08-25)

Direct motivation: `probes/p44_release_rate_test.py` (§30's AMPENV release-
rate session, mpc2emu's rate-vs-duration question) spent an entire evening
editing three AMPENV fields via cursor-ring navigation and closed-loop wheel
turns — one field edit took anywhere from 20 seconds to several minutes
depending on the field's own (nonlinear, per-field) step curve, and a single
off-by-one in the cursor-ring offset silently drove the wrong field for nine
minutes before anyone checked. Every value this project has ever set on the
device (ENV2/LFO1 depth, filter cutoff, the whole AMPENV sweep) went through
the panel, because nothing shorter existed.

**The K2000 manual documents a shorter path that was never used.** Chapter
30, "System Exclusive Protocol," describes `DUMP` (0x00) / `LOAD` (0x01) with
explicit `offs`/`size` fields — a genuine **partial-object** read/write, not
the whole-object replace `WRITE` (0x09) already used for the macro table.
The manual says outright this is meant to "build a simple object librarian
software program" — almost certainly what a commercial editor like MIDI
Quest uses. The vendored `psobot/k2000` library already implements both
messages correctly, checksum included (`k2000/messages.py`'s `Dump`/`Load`
classes) — nobody had wired a convenience layer on top with this project's
own verify-after-write discipline.

Added `MidiBridge.read_object_bytes()` / `.patch_object_bytes()`
(`k2kremote/midi_bridge.py`). The pairing mirrors `read_macro_table()`/
`write_macro_table()`, but `patch_object_bytes` verifies internally rather
than leaving that to the caller (unlike `write_macro_table`, whose caller —
`k2kmaced.online.push` — does the read-back-and-compare itself): a DNAK is
raised immediately, and a successful write is always followed by a read-back
that must match exactly before the call returns, raising `PatchUnverified`
otherwise. Built this way on purpose — a primitive meant to *replace* ad hoc
verify-it-yourself RE code should not have a way to skip the check.

**Two things only found by testing against real hardware, not the synthetic
suite:**

* `client.dump()`/`client.load()` (the vendored library's own convenience
  methods) hardcode a 1.0 s timeout with no override. `read_object_bytes`/
  `patch_object_bytes` go through `_send_and_receive` directly instead, using
  the bridge's own configured timeout (1.5–2 s) for consistency with every
  other call this project makes.
* **DUMPing an object that doesn't exist gets no reply at all** — not a
  DNAK, silence, regardless of timeout length. Found by accident: the first
  live test targeted program 250 (the ENV2/LFO1 depth scratch program from
  §30), not knowing a `Master -> Delete -> Everything` hours earlier had
  wiped it and it was never reloaded. Both a 1.0 s and a 5.0 s timeout failed
  identically against the missing object; the identical call against a
  program confirmed present (via `object_name`/DIR, which *does* document a
  "not found" reply — size 0, name null) answered normally. The manual
  documents DUMP's reply only as "a LOAD message" and says nothing about a
  missing object — this is a real protocol fact, not a timeout tuning
  problem, and cost a false lead (an incorrect draft docstring claiming
  1.0 s was "measured too tight," corrected before commit once the real
  cause was found — the exact write-a-claim-then-verify-it pattern this
  project has tried to hold to all night).

Verified end-to-end on hardware against program 906 (`ObSt lowp kl.lay`,
still resident from §30): read byte 215, then a true no-op patch (write back
the same byte, verify), then confirmed via the panel's own AMPENV page that
nothing had moved. 488 synthetic tests pass, four of them new
(`tests/test_midi_bridge.py`), built on the same `_send_and_receive` round-
trip-through-`SysexMessage.decode()` pattern already used for `rename()`/
`delete_object()` rather than mocking `client.dump()`/`.load()` directly —
proves the wire format, not just the call.

**Update, same evening: now reachable from `k2kmon patch` / `k2kmon read
--offset/--size`.** Investigated first whether it belonged as a new TUI
screen in `k2kremote.app` (the user's original framing — integrate SysEx
capability the way eosed did, in the opposite direction from how this
project grew). It doesn't: `k2kmon` (`k2kremote/monitor.py`) already does
`read`/`compare` for exactly this class of job — "roughly twenty times
faster than the panel," per its own README section — and the project's own
convention splits tools into separate binaries by mutual-exclusivity-with-
the-mirror or hardware-safety character (see `pyproject.toml`'s comments on
why `k2kmaced` and `k2kmon` are separate from `k2kremote`), not by feature
size. A new modal screen would have duplicated a job an already-separate
tool already owns — so `patch_object_bytes`/`read_object_bytes` were wired
into `k2kmon` instead: `k2kmon patch <type> <idno> <offset> <hex>` (typed
`write` confirmation unless `--yes`, mirroring `k2kmaced push`'s reasoning
that a live-object write deserves the same weight as a live-macro-table
write) and `k2kmon read <type> <idno> --offset N --size N` for a partial
read via the same primitive. Verified end-to-end on hardware the same way
as the primitive itself: `read --offset 215 --size 1` against program 906
returned `58` (matching the value already confirmed via the Python API),
and `patch ... 215 58` (a true no-op write-back) reported success and left
the byte unchanged. 7 new tests, 495 total pass.

## 32. `k2kfields.py`, `MidiBridge.list_bank()`, and `k2kmon tui` (2026-08-25)

Follow-on to §31: the user asked for `k2kmon` to reach parity with the
sibling project eosed's TUI, specifically an interactive browser that shows
a raw byte's known meaning alongside it (eosed does this for algorithm
names, Hz values, etc., wherever it knows them).

**The registry keeps two different kinds of field knowledge distinct, on
purpose.** `ENV2->FilFreq Depth` (Program RAM offset 215) and `LFO1->Pitch
Depth` (offset 199) were found by DUMP-diffing two panel-driven states
(§30) — both the **offset** and the **decode law** are known, so
`k2kremote/k2kfields.py`'s `KNOWN_FIELDS` registry auto-decorates them
wherever an offset is read. The filter-cutoff-to-Hz law
(`Hz = 440 * 2**((s-9)/12)`, verified to 0.08% against the panel's own
`Coarse:` field, CUTCAL) is exposed too, as a bare function
(`filter_cutoff_byte_to_hz`) — but its RAM offset inside a live Program
object was **never mapped**; CUTCAL set/read it entirely through the
panel's F1 FRQ page, never via DUMP. `KNOWN_FIELDS` deliberately does not
carry an entry for it, so nothing in the TUI or CLI implies an offset that
was never verified — only a manual caller who already knows where the byte
lives can apply the conversion.

The dense byte-by-byte tables for both known offsets were, before this
session, only ever sent to mpc2emu in chat — never committed anywhere in
this repository. `k2kfields.py`'s `decode()` functions return `None`
("unmapped for this byte") outside the exact ranges/spot-values §30
actually records in prose, rather than reconstructing the missing interior
values from memory.

`MidiBridge.list_bank()` — object enumeration via `DIRBANK` (0x0C), an
INFO×N + `ENDOFBANK` reply that doesn't fit `_send_and_receive`'s
one-reply-per-request model — was promoted the same way `read_object_bytes`/
`patch_object_bytes` were in §31: out of hand-rolled probe code
(`probes/p33_bankdir.py`, unchanged in behaviour, now a one-line wrapper)
and onto `MidiBridge` itself, so `k2kmon tui`'s object-list pane and any
future caller share one implementation instead of two.

`k2kmon tui` (`k2kremote/monitor_tui.py`) is a Textual app, kept in its own
module so `import textual` stays optional for every other `k2kmon` mode.
Three panes plus a modal: object list (`list_bank`), field pane
(`read_object_bytes` for every `KNOWN_FIELDS` entry matching the selected
object's type, decoded via `k2kfields.describe_field`), a patch modal
reusing `patch`'s own typed-confirmation/read-back-verify discipline
(`patch_object_bytes`), and a toggle-able watch pane sharing `watch`'s own
`describe()` decoder — so the TUI and the one-shot CLI commands can never
decode the same bytes two different ways. Threading follows this project's
own convention (`refresh.py`'s `RefreshWorker`: a plain `threading.Thread`
marshaling results back via `call_from_thread`), not eosed's `@work`
decorator — different codebase, its own established pattern already fit.

One eosed trap deliberately avoided: eosed has Hz-conversion functions that
are defined and unit-tested but never called from its live display path —
dead code from the UI's perspective. `k2kfields.describe_field()` is the
one function both the TUI's field pane and any future script would call, so
a field added to `KNOWN_FIELDS` is either exercised by the display or the
test suite that already covers `describe_field` directly — no
built-but-never-wired path here.

13 new tests (`tests/test_k2kfields.py`, `tests/test_midi_bridge.py`'s
`list_bank` tests, `tests/test_monitor_tui.py` against a synthetic
`FakeK2000Bridge` and Textual's own `run_test()`/`Pilot` harness — no
hardware touched), 513 total pass.

**Live hardware smoke test, 2026-08-25: passed.** Driven the same way as the
synthetic tests — `MonitorTuiApp` through `run_test()`/`Pilot`, headless, no
TTY needed — but against a real `MidiBridge.autodetect()`. Browsed to bank 9
(`901`-`910`, `906` present), selected `906`: the field pane showed offset
199 (LFO1->Pitch Depth) as `00` -> `0 cents`, and offset 215 (ENV2->FilFreq
Depth) as `58` -> `6000 cents`, matching §31's own recorded byte for that
offset on that object exactly. (Predicted `3000 cents` beforehand from
misreading §31's "returned 58" as decimal rather than the hex string
`read`/`patch` actually print/accept — `0x58` = 88 decimal,
`(88-28)*100 = 6000`, which is what came back. Own arithmetic error, not a
decode or hardware finding — worth recording since this offset's byte
`58` reads two different ways depending on which base you assume, and nothing
in §31's prose said "hex" outright.) The watch pane opened against the real
`midi_in` and read cleanly for a quiet 2 s window (0 lines — device idle,
nothing unexpected; no traffic was deliberately generated to check this
further).

## 33. AMPENV Loop field, live — and a self-inflicted audio-analysis bug (2026-08-27)

mpc2emu brought a cross-session question: their KRZ writer's `ENV` segment
byte 14 (§4.4 of their `KRZ_FORMAT.md`, "loop flag (template default)",
always written 0) was suspected of making an instant-decay envelope
retrigger from peak while a note was still held, well before note-off.
Investigated live against program 906 with Jan's explicit sign-off at each
hardware step (per this file's own hardware-exclusivity rule — mpc2emu never
drove the device directly; two sessions with open MIDI ports on the same
K2000 at once is exactly what that rule exists to prevent).

**The AMPENV Loop field is real and reachable, but not documented anywhere
in this repo before tonight.** `probes/p44_release_rate_test.py`'s own
docstring already recorded "Loop Off/Inf" on program 906 months ago, unread
until now. Live navigation confirmed it: a 16-field cursor ring (Att1/2/3,
Dec1, Rel1/2/3 time and %, plus `Loop-state` and `Loop-Inf`, cursor opening
on Rel3-%), with `Loop-state` reading named modes, not a binary flag — one
wheel click from `Off` produced `seg1F` ("segment 1, forward", per the K2000
manual mpc2emu found at `~/temp/k2000_manual.txt` lines ~3690-3810: Loop
types only ever cycle the attack/decay portion; release is documented as
strictly gated on Note Off, regardless of loop state). One indexing bug
surfaced and was caught by the probe's own sanity check before it could
touch anything: the ring returned by `read_ring()` is ordered by **steps
from the opening cursor position**, not by canonical field index — indexing
it with a canonical index instead of `(canonical - OPEN_INDEX) % 16`
compared the wrong two values and aborted safely rather than editing blind.

**A real, separate anomaly was confirmed live, independent of Loop-state.**
A matched A/B (`Loop-state=Off` vs `Loop-state=seg1F`, identical note/hold)
showed the *same* unexplained envelope swell recurring ~10.3-10.7s after the
initial attack in *both* conditions — proving Loop-Type is a coincidental
correlate, not the cause, of mpc2emu's bug. (`seg1F` did add one further,
distinct recurrence beyond that shared anomaly, consistent with the manual's
attack/decay-loop description — Loop does something real, just not the
thing being chased.) mpc2emu independently confirmed the same swell shape at
full resolution on their own fixed build (907): decay to the floor,
unexplained rise back toward peak, second full decay — a real K2000 firmware
behaviour that contradicts the manual's own release-only-on-Note-Off
description. Settled as *not* a MIDI-routing artifact by subscribing
`aseqdump` directly to `mididings_k2000r`'s output port during a fresh held
note: the wire carried exactly the one Note On and one Note Off sent, for
the entire hold, nothing else. Root cause remains open on mpc2emu's side
(their TODO.md `§KRZENVLOOP`) — three plausible causes (Loop-Type, a
too-quiet sustain level, mididings) ruled out with hardware captures rather
than assumption, not yet a fourth found.

**Bug worth recording so it isn't repeated:** every "silent capture"
encountered while chasing this (three in a row, blamed in the moment on MIDI
channel, port index, and per-layer key range) was actually a **units bug in
this session's own analysis code**, not a hardware or routing problem. The
mono-downmix line was copied from `p44_release_rate_test.py`'s
`completion_time()` — `(L + R) / 2 / 32767.0` — which is correct *there*
because that function's own comparisons (a floor reference computed the same
way) are self-consistent even though the absolute units are wrong. Reused in
a new script against an *absolute* noise-floor constant, the extra `/32767`
shrank an already-normalized (-1..1 float, straight from JACK)
signal down another factor of 32767, past a hard-coded `0.001` floor — so
every genuinely successful capture printed `peak=0.0000` and read as total
silence. Caught only by reading the already-written WAV file's raw int16
samples directly (`max abs sample 6070/32767`) after three rounds of
chasing MIDI-plumbing red herrings. **Only divide by 32767 when the source
is actually int16 PCM (e.g. read back from a WAV file already written by
`write_wav`) — raw JACK capture arrays are already -1..1 float and need no
such scaling.** Switched to mpc2emu's own proven `krz_audio_measure.py`
(`record()` / `_midi_out()`, thread-first-then-note-on, name-substring port
matching, no numeric port index) for the corrected reruns.

## 34. `soft_index()` pressed OvFill instead of Fill — a real destructive miss (2026-08-30)

While loading a fresh AKAI S3000->KRZ conversion (`FROM_S3.KRZ`, cross-session
work for mpc2emu) via live panel automation, a helper used to find a soft
key by its on-screen label pressed the wrong button: asked for "Fill" on the
Load dialog's mode row (`OvFill Overwrt Merge Append Fill  Cancel`), it
pressed **OvFill** instead — soft key A, not E. OvFill's own manual
definition: "First deletes all RAM objects in the selected bank, and then
loads in objects using consecutive numbering." An actually-destructive
button, reached by a probe's own untested helper, not a read/patch call
this project has otherwise been careful to verify before trusting.

**Root cause:** `soft_index(row, label)` (three independent copies —
`probes/p36_filter_fields.py`, `k2kremote/disk_browse.py`,
`k2kremote/macro_save.py` — all with the identical flaw) found the soft key
by `row.find(label)`, then mapped that character index to one of six zones.
"Fill" is a literal substring of "OvFill" at index 2, well before the real
"Fill" button's own text at index 28, so the substring search silently
returned OvFill's zone. Confirmed by hand-tracing the actual row string,
not assumed.

**First fix attempt was also wrong, worth recording as its own lesson.**
Tried requiring an EXACT match against a fixed 40/6-character zone slice
instead of a bare substring — plausible, and wrong: the K2000's soft-key
zones do not align to a uniform 6.67-character grid. Slicing "OvFill
Overwrt Merge Append Fill  Cancel" that way put "Append"'s trailing `d`
into the same zone as "Fill", so neither "Fill" nor "OvFill" landed on a
zone whose *stripped* text equalled the label, and the code silently fell
through to the same buggy substring search it was meant to replace. Caught
by actually running the new test against the real string, not by reasoning
about the zone math — the same "test it, don't just reason about it"
discipline eosed's own cmp_route.py fix (§32-adjacent, same night) already
demonstrated elsewhere in this session.

**Actual fix:** walk every occurrence of `label` in the row via
`str.find(label, start)`, and accept the first one that is not fused to a
letter or digit on either side (`row[idx-1]` and `row[idx+len(label)]`,
where present, must not be alphanumeric). This finds "Fill" at index 28
(preceded by a space) and correctly skips the index-2 occurrence fused
inside "OvFill" (preceded by `v`), without assuming anything about zone
width or button alignment. Verified against the real collision string and
against every existing call site's expectations (`Root`/`Open`/`Cancel`,
`Yes`/`No`, `Macro`/`Util`, `more>`, `F1 FRQ`) — 515 tests pass, two of them
new (`tests/test_disk_browse.py`, `tests/test_macro_save.py`), reproducing
the OvFill/Fill collision directly rather than only the fixed behaviour.

**Blast radius, confirmed rather than assumed:** the load itself completed
using OvFill on bank 800-899 — 6 Programs, 18 Keymaps, 16 Soundblocks now
resident there, consistent with `FROM_S3.KRZ` loading successfully via
consecutive numbering. Programs 400s and 900s (this session's own
measurement data) were verified untouched immediately after, since OvFill
only ever touches the bank it is pointed at. Bank 800-899's *prior* RAM
contents were never snapshotted for non-Program object types before the
load, so the delete step's actual cost was unknown at the time this was
first written up — Jan confirmed directly afterward that nothing of
significance was there; what's now on 800 is this session's own recent
scratch content. Reported immediately and in full to mpc2emu and to Jan
before doing anything else, including before writing this note.

**Standing lesson for any future live panel automation on a destructive
path:** `k2kremote/disk_browse.py` already existed, already had this exact
bug latently, and its own module docstring already states outright *why*
its browser "never presses `OK`" — loading is slow and, into a populated
bank, destructive. That module was the right place to look before
hand-rolling a one-off script against the Load dialog's bank/mode-selection
screens, which it deliberately does not implement. It wasn't checked for
first. Building an actual safe, tested load flow (bank select + mode
select, reusing this fixed `soft_index`) is future work, not done here.

## 35. `current_field()` never actually matched padded labels like "Depth" (2026-08-31)

`probes/p36_filter_fields.py`'s `current_field()` — the SysEx 0x17/0x16
"ask the device what's selected" helper `goto_field()` is built on — returned
`"Depth "` and `"Src1  "` (trailing spaces intact) instead of `"Depth"` and
`"Src1"`, so `goto_field(bridge, "Depth")` silently returned `None` on any
page where that field exists. Found live, mid-session, chasing a real
`AssertionError` trying to reach Layer 2/3 of the reference preset for a cross-session
measurement request.

**Root cause:** the K2000 pads short field labels with spaces before the
colon to align the value column across a page — the device answers
`"Depth :"`, `"Src1  :"`, not `"Depth:"`, `"Src1:"`. The old code did
`.strip().rstrip(":")` — `.strip()` only touches the string's true outer
ends, and the colon (not whitespace) is what's actually at the end, so it
strips nothing; `.rstrip(":")` then removes the colon but leaves the
padding spaces that were sitting *before* it. Confirmed by reading the raw
device reply directly (`bridge.client.get_current_parameter_name()`) rather
than trusting the already-processed helper. Labels with no padding needed
(`"Coarse:"`, `"FineHz:"`) were unaffected, which is why this went unnoticed
through `goto_field(bridge, "Depth")` calls that quietly worked in some
contexts and not others.

**Fix:** strip after removing the colon, not before —
`name.replace(":", "").strip()`. Verified against both padded and unpadded
labels in `tests/test_p36_filter_fields.py`; full suite (517 tests) passes.

**Not fixed here:** `k2kremote/macro_save.py:161`'s `current_disk()` has the
identical `.strip().rstrip(":")` pattern, currently harmless only because
`"CurrentDisk"` has no internal padding. Worth the same fix if that function
is ever pointed at a padded label.

## 36. The v1 "knee", panel-edit persistence, and mpc2emu's fold branch (2026-09-01)

Measured for the mpc2emu ↔ s3ked cross-machine preset comparison. Two
results worth keeping, one of them a correction of a claim this session had
already sent to a peer.

### The v1 "knee" was the velocity->filter route, NOT an amp limit

**Superseded finding, kept because the wrong version was circulated.** On
the reference preset v13 the whole-signal velocity curve looked like the amp was failing to
deliver its `VelTrk` setting: v1..v127 swing of 30.01 dB where 35 dB was
written, with a flat plateau below v4. It is not the amp. Measured with the
Program Editor held **open** (see below), three conditions in one session:

```
                                slope(v>=32)  full-range  v1..v127 swing
  A  VelTrk 35, filter 7500/8200    0.26534     0.23984      30.01 dB
  B  F1 FRQ VelTrk 0/0              0.27141     0.27416      34.59 dB
  C  AMP VelTrk 24/24               0.17662     0.15249      19.16 dB
  the amp's own law, measured separately:       0.27618
```

**B**: zeroing the velocity->cutoff route gives 34.59 dB of a 35 dB setting and
the plateau disappears rather than shrinking -- the curve is monotonic to v1
(-34.59 / -34.29 / -33.80 / -32.56 / -30.42 at v1/2/4/8/16, against
-30.01 / -30.77 / -30.46 / -27.40 / -27.52 with the route live).

**C**: v1's *absolute* level moved **+10.94 dB** when AMP VelTrk went 35 -> 24,
against +11.0 predicted for full delivery and +0.0 for a fixed floor. **The amp
delivers its VelTrk setting in full.** The shortfall is constant, not
proportional -- 4.99 dB at VelTrk 35, 4.84 dB at VelTrk 24 -- i.e. a fixed
filter-route contribution.

**Consequence:** `VelTrk 24` (the value the reference preset's source wants) can be written
as-is; no compensation is needed and none should be applied. A converted patch
will still measure ~5 dB less whole-signal swing than its VelTrk setting
whenever a velocity->cutoff route is present, and that is the patch working,
not a defect.

### Panel edits are live ONLY while the editor is open

**The bug that produced the wrong version above, and it invalidated two runs.**
`probes/p36_filter_fields.leave_editor()` exits the Program Editor answering
the save prompt with **"No"** -- which its own docstring states in its first
line, correctly, because it exists to guarantee a read-only probe never leaves
the box modified. The prompt is:

```
  Save <program name>.P before exiting?
                Rename Cancel Yes    No
```

Reusing it inside a script that *made* edits meant every sequence ran as:

```
  1. enter editor, set the field, read it back      <- edit applied, verified
  2. leave_editor()  -> "No"  -> program REVERTS    <- edit discarded
  3. capture                                        <- UNMODIFIED program
```

**An immediate read-back cannot catch this** -- the value really was set. Two
runs were lost to it: a filter-neutralisation test reported as a *failed
prediction* (it was never tested) and a `VelTrk 24` sweep that was a second
`VelTrk 35` sweep.

**The fix is to capture with the editor still open.** Closing the SysEx bridge
does not exit the editor, so the working pattern is: enter editor, edit, close
the bridge, capture, reopen the bridge for the next edit, and `leave_editor()`
at the very end to discard. Proven by setting AMP `VelTrk 0` (which should
collapse the velocity response entirely): v1..v127 spread went 30.17 dB ->
**-3.49 dB** in-editor, and back to 35/35 after exiting.

**The general rule, from s3ked, worth more than the specific bug:** *if a
neutralisation is real, the measurement must move; if it does not move, you
have not established a null result, you have established nothing.* The invalid
run moved the slope by 0.010 dB/unit and was reported as a null result
refuting a hypothesis. The valid one moved it by 3.4 percentage points. Treat
"nothing changed" as a broken experiment until the mechanism is shown live.

**A methodological trap this session walked into.** A single-capture fit over
the *full* range gave 0.22927 dB/unit at r² 0.984 with 2.1 dB residuals, and
that was reported to a peer as a velocity-dependent *shape* artefact. Two
checks were needed, both cheap and both skipped the first time:

- **Repeatability.** Six captures per velocity: sd 0.24–0.57 dB, spread
  ≤1.46 dB. That established the ~2.4 dB deviation as real (not noise) *and*
  gave the resolution needed to see it was confined to one point.
- **A falsifiable prediction, run.** "Zero `F1 FRQ VelTrk` on both layers and
  the slope snaps to 0.276 ± 0.005, r² > 0.999." It did not: 7500→0 and
  8200→0 moved the slope by **0.010 dB/unit** (0.22927 → 0.23965). The
  hypothesis was wrong and the retraction went out within the hour.

Every other velocity route was then eliminated by reading the box:
`LAYER LoVel ppp / HiVel fff` (no velocity switching), `ENVCTL Att/Dec/Rel
VelTrk 1.000x` (no velocity→envelope rate), `F4 AMP Src1 OFF / Depth 0dB`,
`KEYMAP VelTrk 0ct`. This is [[k2000-ampenv-panel-automation]]'s "unretested
plausible inference" failure mode again — see it there for the pattern.

### mpc2emu's zero-coverage fold branch is correct on hardware

`writers/krz_writer.py:1666`, the `if _vel_ct and _vel_min_ct:` floored-sweep
branch, whose own comment says *"ZERO of 1383 velocity routings in the corpus
take this branch"* and *"untested until the reference preset"*. The reference preset v13 is the first
patch to exercise it. Source bytes from s3ked, written values read off the
box, and mpc2emu's own parser+writer run forward:

```
  kg0  MODVFILT1 35  FILFRQ 35 -> cutoff  96.05 Hz  -> writer 16.35 Hz / 7455 ct
       K2000 actual: Coarse C 0 16 Hz, VelTrk 7500 ct           (-45 ct)
  kg1  MODVFILT1 35  FILFRQ 65 -> cutoff 844.18 Hz  -> writer 84.03 Hz / 7989 ct
       K2000 actual: Coarse D 2 73 Hz, VelTrk 8200 ct          (-211 ct)

  top of sweep   kg0  source 1212.73 Hz  vs box 1244.51 Hz   +44.8 ct
                 kg1  source 8479.36 Hz  vs box 8372.02 Hz   -22.1 ct
```

The §AKAICHOKEFILTER compensation works: the comment feared kg0's sweep top
landing near 2.6 kHz against a ~1.2 kHz source ceiling, and it lands at
1244 Hz. **Identical `MODVFILT1 = 35` on both keygroups producing 7500 and
8200 is the source's own asymmetry**, not the branch inventing one — the
parser's room clamp `min(_half, _room_down, _room_up)` binds on a different
side for each (kg0 down to the AKAI's 7.607 Hz floor → 4390 ct; kg1 up to the
8481 Hz ceiling → 3994 ct).

**The −200 ct gap above was this session's own error, and it is instructive.**
The forward run computed kg1 *alone*. Since §AKAILAYERGAP (mpc2emu,
2026-08-31) the writer does not write a keygroup to a layer: `_fit_layers`
fuses three source voices into one K2000 layer and `_fuse_voices` **key-span
weighted averages** the continuous filter fields on the way:

```
  before fusion   kg1 keys 24-59    844.18 Hz  3994.3 ct   <- what was calculated
                  kg3 keys 60-71   1212.71 Hz  3367.2 ct
                  kg5 keys 72-127   679.26 Hz  4370.6 ct
  after  fusion   L2  keys 24-127   797.90 Hz  4124.6 ct   <- what the writer folds
```

mpc2emu's current build writes `hob_f1[1] = -22 / hob_f1[4] = 110` — byte for
byte what is on the box. **702 is current, not stale.** The discrepancy was
two calculations of different objects.

**Carry this into any future source↔device comparison: since v13, a K2000
layer is not any single AKAI keygroup.** L1 is the three choke-losers fused,
L2 the three survivors, with cutoff, resonance, filter-env depth, keytrack
and both velocity-filter fields averaged by key span. A per-keygroup source
value will not equal a per-layer device value for any of those fields, by
design — and there is therefore no per-keygroup counterpart to give a layer
an asymmetric `AMP Adjust` from.

### ROM #199 has no filter

`_TPL_LAYER` is byte-identical to ROM #199, and #199's EditProg reads
`F1 OFF  F2 OFF  F3 OFF` with one layer. **Every filter value on a converted
program is written by the converter — never template residue.** This was
checked precisely because "inherited from the template" was the first and
wrong assumption about where 7500/8200 ct came from.

## 37. The K2000 keymap has a per-key-range `VolumeAdjust`, and nothing writes it (2026-09-01)

Found while checking whether mpc2emu's §KRZSHAREDGAIN (per-sample gain
averaged across every zone in the bank that references a sample) had a
lossless home on the device. It does.

`EditKeyMap` on keymap 707 (the reference preset layer 2), walking every range with the
`Key Range` selector — which the manual documents as a *view* selector, so
this is a read, and the selector was stepped back afterwards:

```
   Key Range              Sample                VolumeAdjust
   C 0 - B 3   (..59)     703*KK DXE-C 3          0.0 dB
   C 4 - B 4   (60-71)    704*KK DXE1-C 4         0.0 dB
   C 5 - G 10  (72..)     705*KK DXE2-C 5         0.0 dB
                          (wraps — exactly 3 ranges)
```

Manual, §"The Keymap Editor Parameters":

> **Volume Adjust** — "Here you can adjust the volume of the notes in the
> *current key range*. This enables you to make each key range play at the
> same volume even if the samples in the various ranges were recorded at
> different volumes."

**Three fields are easy to confuse and only one of them is per-key-range:**

| field | scope | who writes it |
|---|---|---|
| Soundfilehead `volumeAdjust` | per **sample** | mpc2emu `krz_writer` (bank-wide mean over referencing zones) |
| F4 AMP `Adjust` | per **layer** | mpc2emu (from the source's layer gain) |
| Keymap range `VolumeAdjust` | per **key range** | **nobody** |

The per-sample byte is shared across presets — the reference preset shares samples with
CRYSTAL E and VELSTACK E, which is what makes the mean lossy — and the
per-layer `Adjust` can only hold one value for all ranges. **The keymap
object is private to its preset and its `VolumeAdjust` is per range**, so it
is the only one of the three that structurally matches the model's per-zone
`volume`. Suggested to mpc2emu as `zone.volume − sample_gain_db[sample]`,
which is identically 0 wherever a sample is not shared (so no regression on
byte-identical unity banks).

**Measured on the panel, 2026-09-01** (all edits discarded via the exit
prompt; field verified back at `0.0dB` on every range afterwards):

```
  STEP    +1 click -> 0.5dB   +2 -> 1.0dB   +3 -> 1.5dB   +4 -> 2.0dB
          -1 click -> -0.5dB  -2 -> -1.0dB  -3 -> -1.5dB
  RANGE   both rails driven:  upper +63.5dB   lower -63.5dB
  SCOPE   range C 0-B 3 set to 63.5dB; C 4-B 4 and C 5-G 10 stayed 0.0dB;
          returning to C 0-B 3 still read 63.5dB
```

**The low rail is −63.5 dB, NOT −64.0.** The *sample* editor's equivalent
reaches −64.0 (signed i8, byte 0x80), but the keymap field uses **bytes
−127..+127 and never 0x80** — so a writer must clamp to ±127. This is the one
value the panel cannot produce.

Per-key-range scoping is now established **by experiment** rather than from
the manual's wording.

**Byte layout** (from mpc2emu's `docs/KRZ_FORMAT.md`, not measured here): the
keymap `method` word is a bitfield, `0x04` selects a per-entry `volumeAdjust`
i8 sitting **+2 into the entry**, between the i16 tuning and the i16 sampleID.
mpc2emu writes `0x13` (entry size 5); adding volume means `0x17` (size 6).
Their *reader* (`krz_parser._decode_table`) already decodes the full bitfield
including `0x04` — this is a write-side-only gap.

**Navigation note:** in `EditKeyMap`, `ChanBankInc/Dec` steps the *velocity*
level (`<>VelocityRange:` on the top line), **not** the key range — the K2000
supports 1–3 velocity levels per keymap and they cannot be added to an
existing keymap. Key ranges are stepped with the `Key Range` field itself.
Walking ranges with ChanBank silently shows the same range every time.

## 38. §KRZSHAREDGAIN verified on hardware; v14 at bank 800 (2026-09-01)

mpc2emu's fix for per-sample gain averaged across every zone in the bank (the
bug §37's keymap `VolumeAdjust` finding was chased down for) shipped as v14.
Loaded `FROM_S3.KRZ` (709K, byte-size-matched against
`out_MXS3toKRZ_v14/MXS3TOKRZ_01.KRZ` = 726414) into **bank 800**, verified
empty first, mode **Fill**. The reference preset is at **802**; **702 keeps v13** as the
reference artefact.

### The two fields sum to the source gain

```
  C 0-B 3   KK DXE    keymap -5.5 + sample -6.5 = -12.00   source -12.115   +0.12
  C 4-B 4   KK DXE1   keymap -4.0 + sample -1.0 =  -5.00   source  -4.846   -0.15
  C 5-G 10  KK DXE2   keymap -8.0 + sample -4.0 = -12.00   source -12.115   +0.12
```

Max |error| **0.154 dB** against the field's own 0.5 dB quantisation. Layer 1's
ranges are all `0.0dB`, consistent with the writer emitting `method 0x17` only
on the keymaps that need a residual and `0x13` elsewhere.

### Audio A/B, paired — both versions resident at once

Because v13 (702) and v14 (802) are in RAM simultaneously, each pair was
captured back to back through the same chain, the same Volume knob and the same
minute. **Chain and gain cancel exactly, so no reference design is needed** —
this is a much stronger design than the cross-machine comparison of §36 and it
is available whenever two versions can be resident together.

Whole patch (mean of v127/v64, 3 reps): note 48 **-1.55**, note 63 **-2.57**,
note 80 **-5.33** dB. All negative, as required if v13 was too loud — but the
*ordering* contradicted the zone errors (+5.65 / +3.88 / +8.08 predicts
80 > 48 > 63; observed 80 > 63 > 48).

**Tested rather than explained away.** Layer 1 is untouched by the fix, so it
is pure dilution; muting it on both programs isolates the change:

```
  L2 ONLY    v13 -> v14   predicted    err
    note 48    -5.55        -5.65     +0.11
    note 63    -4.02        -3.88     -0.14
    note 80    -8.07        -8.08     +0.01      ordering restored to [80,48,63]
```

Max error **0.14 dB**. The anomaly was layer 1's *note-dependent* share: at
note 48 the whole-patch delta is only 27% of the L2 change, at notes 63 and 80
it is 66%. **A whole-patch measurement dilutes a per-layer change by an amount
that varies with note**, so per-layer claims need the other layer muted — which
is cheap, since the mute is an in-editor edit discarded on exit (§36).

### Loading into a verified-empty bank cannot go destructively wrong

The K2000 offers only `Append / Fill / Cancel` when the target bank is empty —
`OvFill`, `Overwrt` and `Merge` are not presented at all. Useful given that
`soft_index` once matched "Fill" inside "OvFill" and pressed the destructive
one for real (§34). Verifying the bank is empty first is therefore a stronger
guard than getting the soft key right.

## 39. v15 verified: the resonance change is symmetric, not top-only (2026-09-01)

Jan loaded v15 to program **902**; mpc2emu asked for parameter-level
verification. Banks 200-499 had been cleared, but 500/600/700/800/900 remain,
so **702 (v13), 802 (v14) and 902 (v15) are all resident** and comparable back
to back.

### Confirmed as v15

```
  LAYER COUNT      3          (v13/v14 have 2 -- checked, not assumed)
  F2 RES           L1 5.0dB   L2 19.0dB   L3 14.0dB
  F1 FRQ Coarse    L1 16Hz    L2 104Hz    L3 55Hz
  keymap ranges    L1 3       L2 2        L3 1
```

**Two entries in the supplied expectation table were wrong, and both were
expectation errors, not build errors** — worth knowing because as written they
would fail a correct build:

- `AMPENV Dec1` is **not** 7/3/3. It is `0.02s/37%` and `5.10s/21%`, **identical
  across v13, v14 and v15**, with L3 inheriting L2's envelope exactly. v15
  changed no amp envelope, which is what a resonance/fusion fix should do.
- The keymap ranges are **wider** than described (L2's second range runs
  `C 4-G 10`, L3's single range spans `C 0-G 10`). Coverage is still correct
  because the **LAYER bounds** do the gating: `L2 C1-B4`, `L3 C5-G9` —
  contiguous, no gap, no overlap. v14 achieved the same coverage the opposite
  way, with full-range layers and three bounded keymap ranges; the splits have
  to live *somewhere*, and which of the two carries them depends on whether the
  keygroups share a keymap.

### The change is symmetric — the "control" note moved more than the effect

Set up note 48 as a control on the claim that the builds are near-identical
below key 60. It moved **+9.4%** in centroid, three times the effect being
looked for. Reading the resonances rather than reporting the number:

```
  keys <=71   16.5 -> 19.0  =  +2.5 dB  MORE resonant
  keys >=72   16.5 -> 14.0  =  -2.5 dB  LESS resonant
```

**Fusing two keygroups instead of three does not merely release the third — it
re-averages what remains**, and kg1+kg3 average higher than kg1+kg3+kg5 did.
(The fused value on the box is **16.5 dB**, not the 17.5 that was quoted.)

Audio, all three builds paired back to back, centroid over 0.10-0.60 s, v127:

```
  v14 -> v15     d_rms      d_centroid
    note 48     -0.22 dB   +265.0 Hz (+9.4%)    L2, now more resonant
    note 72     +0.07 dB    -67.8 Hz (-2.5%)    L3, now less resonant
    note 80     +0.07 dB   -136.6 Hz (-3.2%)
    note 88     -0.09 dB   -107.2 Hz (-2.3%)
```

RMS flat to ±0.22 dB throughout, so §KRZSHAREDGAIN's level fix survives v15 —
the change is purely spectral, as intended.

### Scored against the source, and where the error now lives

```
  keys        source   v13/v14        v15
   24-59      18.7      16.5 (-2.2)   19.0 (+0.3)
   60-71      25.5      16.5 (-9.0)   19.0 (-6.5)   <-- remaining error
   72-127     14.9      16.5 (+1.6)   14.0 (-0.9)
```

All three ranges improve. **The residual is now concentrated in keys 60-71 at
-6.5 dB**, because kg1 and kg3 remain fused and differ by 6.8 dB — the same key
range where §KRZSHAREDGAIN's residual was largest. Unlike that bug there is
**no per-key-range escape**: K2000 resonance is a per-LAYER DSP parameter and
the program already uses three layers, so splitting kg1/kg3 is not available.
Treat it as a hard limit rather than an open defect.

**Method note:** a resonance change is a peakiness change, and RMS cannot
distinguish "quieter" from "less resonant". Spectral centroid is gain-invariant
and does — and with two builds resident simultaneously the comparison is paired
against the same chain and knob (§38).

## 40. `F2 RES KeyTrk`: pivot 60, literal dB/key, linear both ways (2026-09-01)

Measured because it is the only lever that could relax §39's "keys 60-71 are
6.5 dB under source and there is nothing to be done" — K2000 resonance is a
per-LAYER DSP parameter, but the `F2 RES` page carries its own `KeyTrk`, which
mpc2emu's writer has never emitted.

```
  resonance(key) = Adjust + KeyTrk * (key - 60)

  KeyTrk 0.04:  d = -1.44 -0.96 -0.39  0.00 +0.54 +0.97 +1.49   (keys 24..96)
       gradient 1.010 dB/key per unit set   pivot 59.2   r2 0.9989
  KeyTrk 0.10:  d = -3.60 -2.41 -1.21  0.00 +1.23 +2.45 +3.65
       gradient 1.009 dB/key per unit set   pivot 59.8   r2 1.0000
```

**Pivot is key 60** — middle C, agreed independently by both settings, and
**not** the endpoint pivot the amp's `VelTrk` uses (§36). Linear in key and in
the setting; the displayed dB/key is literal to within 1%; `0` is genuinely
neutral (the KeyTrk 0 row is flat to 0.00 dB across six octaves).

### The rig, and why the first one was thrown away

**Built on ROM #199's edit buffer**: one layer, ALG 5, keymap 163 Sine Wave
with **both** KEYMAP and PITCH `KeyTrk` at 0 so the pitch is frozen at 262 Hz,
the corner parked on it at `C 4`, `F1 FRQ` KeyTrk/Depth/VelTrk 0, `F4 AMP`
VelTrk 0. Control: 0.00 dB level spread across keys 24-96 at crest 3.03.
Nothing saved.

**CORRECTION (2026-09-01, later): F3 was NOT switched off.** This note and §42
both claimed it was; §40's own transcript prints the chain as
`PITCH 2POLE LOWPASS BAND2 AMP` throughout. Pressing the `F3` soft key
*navigates to* that block's page — it does not change the block's type, which
lives on the ALG page. **#199 defaults its F3 block to BAND2 under algorithm
5** and it stayed in circuit for every §40/§42 capture.

**Harmless for the KeyTrk law, fatal for anything absolute — and the reason
matters more than the conclusion.** The tempting argument is "a fixed stage in
series divides out of a difference". True, but it assumes the premise that
actually needed checking: **was BAND2 fixed?** A bandpass has its own block
parameters, and `F3 SEP` on the 4-pole turned out to carry its own
`KeyTrk`/`VelTrk` (§42). BAND2's were never touched. Had its centre tracked the
key, the series gain would have varied with key and the measurement would be
corrupted — invisibly, because it would look exactly like resonance
keytracking.

**The control settles it empirically:** §40's KeyTrk-0 run measured **0.00 dB
level spread across keys 24-96**. A key-dependent BAND2 could not produce that.
So the stage was key-independent on that rig, whatever its settings were — and
the calibration curve was measured through BAND2 as well, so its constant gain
cancels in the level→resonance inversion before any difference is taken.

**State it that way round.** "The control was flat, therefore the stage was
key-independent" is the check; "a fixed stage divides out" is an argument from
an unchecked premise. §40/§42's results stand — pivot 60, 1.009-1.010 dB/key
per unit, offset 228, rails ±100 — but they stand *with BAND2 in circuit*, not
because it was removed.

Any measurement of the transfer function *itself* (a corner frequency, a
rolloff slope) does have BAND2 in series with the filter under test and is
invalid. Found while measuring filter corners (§45), where the same rig
produced fits railing at the search limit.

**A sine parked exactly on the corner turns RMS into a direct readout of the
resonant peak**, which is what makes this measurable at all — resonance is a
peak, not a broadband gain, so RMS on any other source barely moves.

The first attempt was built on **program 902** because it already had a working
2-pole lowpass, so the rig was ~8 edits away instead of built from scratch.
That reasoning was about edit count, not validity, and it was wrong: 902 is the
v15 reference artefact and carries seven confounds (three layers, a choke
click, ENV2->corner at 7600/4000 ct, velocity->corner at 7500/8200 ct, layer
key spans that differ so sweeping the key changes which layer sounds, musical
samples, pitch keytracking). All were neutralised and the control did come back
flat — but each took a run to find, and two more runs were lost to state left
behind in the rig. **The clean rig beat it in one run.** Build the rig from a
known state; do not subtract confounds from an unknown one.

### Resonance -> level SATURATES, and that broke the first measurement

```
  Adjust  0->6 dB : level tracks at 1.00 dB/dB
          6->12   : 1.4 dB total
         12->24   : almost nothing
```

The first attempt used the reference preset's own 19 dB base, so KeyTrk's whole +-7 dB
excursion sat in the flat region and produced 0.4 dB where 14.4 was expected —
**a false null that read as "KeyTrk does nothing"**. Choose an operating point
in the 0-6 dB region, and invert measured level back through a calibration
curve rather than treating level as proportional to resonance.

Practical corollary: **the reference preset's layers sit at 19 and 14 dB, already saturated**,
so a resonance change up there moves the output far less than its dB value
suggests. Do not predict audibility from a resonance delta alone.

### What it buys, and what it does not

```
  L2 (keys 24-71)                      RMS err   worst
    v15 today: flat 19.0 dB             3.26      6.5 dB
    best ramp: 22.4 dB, KeyTrk 0.159    1.95      3.5 dB
```

KeyTrk **halves** the error on a fused layer but does not eliminate it:
**KeyTrk is a linear ramp and the source is piecewise-constant**, so matching
kg3 costs accuracy inside kg1 where v15 is currently almost exact. And it only
helps when the source resonances are **monotonic in key** — the reference preset's run
18.7 -> 25.5 -> 14.9, up then down, and one ramp across all three keygroups is
*worse* than the three-layer split (RMS 2.81 dB, worst 7.8 dB). Use KeyTrk for
a fused layer whose members trend one way; keep separate layers where they do
not.

## 41. `F2 RES KeyTrk` byte: offset 228, and `ram_only=True` is not "is this ID free" (2026-09-01)

§40 measured the law; mpc2emu needed the byte to write it. Found by DUMP-diff
(§30's method) across four scratch programs identical in everything but
`F2 RES KeyTrk`:

```
  KeyTrk    byte@228   signed   dB/key per unit
   +0.00        0        +0         -
   +0.10        5        +5       0.0200
   -0.10      251        -5       0.0200
   +1.00       50       +50       0.0200      <- 10x check
```

**Offset 228 was the only byte that differed across the set.** Signed i8 at
**0.02 dB/key per unit**, which matches the alpha-wheel step measured
independently. The ±0.10 pair alone could not distinguish a linear scale from a
curve through those two points, hence the 1.00 confirmation.

**Panel rails are −2.00 .. +2.00 dB/key = bytes −100 .. +100 — NOT the signed
i8 range.** −128/+127 would reach −2.56/+2.54, values the panel cannot produce.

```python
# F2 RES KeyTrk, Program object offset 228
byte = max(-100, min(100, round(db_per_key / 0.02))) & 0xFF
```

This is the second rail in two days that is narrower than its container (§37's
keymap `VolumeAdjust` is ±63.5, not −64.0). **Measure the rails; do not infer
them from the byte width.**

### `list_bank(..., ram_only=True)` hides ROM, and is not a free-ID test

The scratch copies were first aimed at "empty bank 100" — empty per this
project's own census. The K2000 refused: the save dialog came back
`(Replace Cheeze)` with its soft key changed from `Save` to **`Replace`**.
**Bank 100 holds 100 ROM programs**; `ram_only=True` had hidden all of them and
reported the bank empty.

**Guard, now in the probe: refuse to save if the dialog offers `Replace`.**
The device's own dialog is the authority on whether an ID is free — a census
with `ram_only=True` answers a different question ("what is in RAM here"), and
0-199 is ROM territory on this machine. Worth the same guard anywhere an ID is
chosen programmatically.

**Save-dialog flow** (Program Editor → `Save`): the ID must be typed **and
committed with Enter** — typing alone leaves it mid-entry (`as:100...`) and the
screen still reads the old ID. Then the soft row is
`Object | Rename | Save | Cancel` for a free ID, and
`Object | Rename | Replace | Cancel` for an occupied one.

**Left resident:** scratch programs **200-203** (`Default Program` copies at
KeyTrk 0.00 / +0.10 / −0.10 / +1.00), RAM-only, ROM keymap 163 so no sample RAM
involved. Not deleted: a delete flow this project has not exercised, on a box
with a known delete-time lockup ([[lockup-heartbeat-during-deletes]]), run for
tidiness alone, is a poor risk trade — flagged for Jan's next bank clear
instead.

## 42. The 4-pole `F2 RES KeyTrk` law is the same law — read the manual first (2026-09-01)

Jan pointed out that the algorithms are described in the manual. Consulting it
before designing the probe **prevented a real error and revealed a confound no
amount of probing the F2 page would have surfaced.**

Manual, "Four-pole Lowpass Filter with Separation (4POLE LOPASS W/ SEP)":

> "This combines 2POLE LOWPASS and LOPAS2 in one **three-stage** function. The
> parameters on the F1 FRQ page affect the cutoff frequencies of **both**
> filters. The parameters on the **F2 RES** page affect the resonance of
> **2POLE LOWPASS**. The parameters on the **F3 SEP** page shift the cutoff
> frequency of LOPAS2."

**F3 is not a spare slot on a 4-pole — it is the filter's own SEP stage.** The
plan of record before reading this was to "check F3 and switch it off", which
would have dismantled the filter being measured. And **`F3 SEP` carries its own
`KeyTrk`/`VelTrk`/`Depth`**: a non-zero SEP KeyTrk moves LOPAS2's corner with
key — exactly the confound the rig exists to exclude — and nothing on the
`F2 RES` page would show it. (On #199 it defaults to all zeros, so the run
would have survived; that is luck, not method.)

### Result: identical, and structurally so

```
                 dB/key per unit set    pivot     r2
  4-pole  KeyTrk 0.04       1.052        59.0    0.9993
          KeyTrk 0.10       1.020        59.5    0.9998
  2-pole  (§40 reference) 1.009-1.010  59.2-59.8

  byte@228:  4-pole  0.00 -> 0,  1.00 -> 50    identical to 2-pole (§41)
```

Control spread at KeyTrk 0: **0.00 dB** across keys 24-96. The prediction was
stated before measuring. It holds *because* `F2 RES` on a 4-pole is literally
the same 2POLE LOWPASS resonance stage with a second lowpass cascaded after —
structural, not two numbers happening to agree.

**One rule covers both filter types:**

```python
# F2 RES KeyTrk -- Program object offset 228, 2-pole AND 4-pole
byte = max(-100, min(100, round(db_per_key / 0.02))) & 0xFF
# resonance(key) = Adjust + KeyTrk * (key - 60)
```

**Saturation knee moved**: 4-pole flattens at Adjust ~8 dB against 2-pole's ~6.
Found before sweeping, operating point set at 4.0; crest stayed 3.15-3.26
against a pure sine's 3.01, so nothing clipped.

### Scope, and one manual caveat

Measured for `2POLE LOWPASS` and `4POLE LOPASS W/SEP` only. Algorithm 1's
centre block also offers HIFREQ STIMULATOR, PARAMETRIC EQ, STEEP RESONANT BASS,
4POLE HIPASS W/SEP, TWIN PEAKS BANDPASS and DOUBLE NOTCH W/SEP — **none
measured**, and the 4-pole result transfers only because the manual states the
resonance stage is shared. Do not assume the highpass or bandpass match.

**The manual is authoritative on structure but not always on field labels**: it
renders the F3 SEP first field as `Adjust:0ct`; the device says `Coarse:0ct`.
That difference broke the first run.

**Scratch programs 200-205** remain resident in bank 200 (200-203 from §41,
204-205 from this note's byte check) — RAM-only, ROM keymap 163, no sample RAM.

## 43. F4 AMP `Src1` / `Depth` bytes: 262 / 263, 1 dB per unit (2026-09-01)

mpc2emu's tremolo path (`lfo1_to_volume`) is read by no hardware reader and
written by no writer, so LFO→amplitude is absent from every hardware path. They
could infer `Src1`/`Depth` adjacency from the F1 FRQ block but not the absolute
offsets or the scale.

DUMP-diff, no audio needed — set the field, save, dump:

```
  state                @262      @263
  Src1 OFF,  Dep   0     0         0     (baseline, id 206)
  Src1 LFO1, Dep   0   114         0
  Src1 LFO1, Dep +12   114        12
  Src1 LFO1, Dep -12   114       244  (-12)
  Src1 LFO1, Dep +24   114        24
  Src1 LFO1, Dep  +6   114         6
```

**Offset 262 = `Src1`**, holding the control-source code directly
(`OFF` = 0, `LFO1` = **114**). **Offset 263 = `Depth`**, signed i8,
**1.0 dB per unit** — the byte equals the displayed dB.

**Panel rails −96 .. +96 dB = bytes −96..+96.** Third rail in two days narrower
than its container (§37 `VolumeAdjust` ±63.5; §41 `F2 RES KeyTrk` ±100; this
±96). The habit stands: **measure the rail, never infer it from byte width.**

```python
src1_byte  = control_source_code                          # offset 262
depth_byte = max(-96, min(96, round(depth_db))) & 0xFF    # offset 263
```

Note the scale is **1 dB/unit here against 0.02 dB/unit for `F2 RES KeyTrk`**
(§41) — there is **no shared scaling convention across the F-blocks**, so each
depth field needs its own measurement.

**Selecting a control source: type the code, do not wheel.** The `Src1` list is
long; wheeling 60 clicks overshot to `FX Depth` without reaching LFO1. The
manual's Main Control Source List gives the numbers (LFO1 = 114, LFO2 = 116,
ENV2 = 121, Data = 6).

**A self-inflicted analysis bug worth remembering:** the script's automatic
"which byte varies with Depth" step printed `[]`. It intersected the
changed-byte sets across states, and the Depth-0 state has no change at 263, so
263 fell out of the intersection. The raw per-state diffs were unambiguous —
but a reader skimming for the summary line would have concluded that no byte
encodes Depth. **A derived summary can fail while its inputs are fine.**

**Not measured:** `Src2`, `DptCtl`, `MinDpt`, `MaxDpt`. Probably 264+ by the
same adjacency; that is an inference, not a result.

## 44. F4 AMP tremolo swings ±Depth about nominal (2026-09-01)

mpc2emu's model asserted, unmeasured, that LFO→volume is "always positive: a
tremolo swings symmetrically down from the zone's own volume" — self-
contradictory as written. It decides whether writing depth D costs headroom
above nominal.

```
  Depth   peak vs nominal   trough vs nominal   total swing   2xDepth
   12.0        +12.08            -11.51            23.58        24.0
   24.0        +23.85            -22.52            46.37        48.0
  peak/Depth 1.007, 0.994    swing/(2*Depth) 0.982, 0.966
```

**`Depth` is the one-sided amplitude in dB, applied bipolar about the
un-modulated level.** Peak-to-peak is 2×Depth. **Writing depth D costs the full
D dB of headroom above nominal** — so a zone within D dB of full scale clips on
every tremolo peak. Both halves of the model's claim were wrong: it is not
one-sided, and it does not stay at or below nominal.

**The residual asymmetry is REAL — it is the device, not the floor. My first
reading of it was wrong and I disproved it myself.** §44 first recorded the
shallow trough as "probably my noise floor, not proven". Measuring the same
Depth 24 at two gains 8 dB apart settles it:

```
  Adjust   peak-nom   trough-nom   centre offset   half-swing   trough hdr
   -24.0    +24.46      -21.53         +1.46          23.00       9.68 dB
   -16.0    +24.48      -21.05         +1.72          22.77      18.17 dB
```

**The trough moved 0.48 dB while its headroom over the floor nearly doubled**
(9.68 → 18.17 dB), and floor-correcting the power leaves −22.0 / −21.1 — still
~2.5 dB short of −24. Floor-limited would have closed the gap. It did not.

Meanwhile **the peak is identical at both gains to 0.01 dB** (+24.46 / +24.48),
which also rules out compression at the top: the louder run had only 5.21 dB of
peak headroom and read the same as the quiet one with 13.12 dB.

So the swing is **not** exactly ±D. Measured:

```
  Depth 12   +12.08 / -11.51    centre +0.29   half-swing 11.80
  Depth 24   +24.47 / -21.53    centre +1.47   half-swing 23.00
```

The modulation centre sits slightly **above** the un-modulated level, by an
amount that grows with depth, and the half-swing is ~0.96-0.98 × D. The
mechanism is not established and is not worth guessing at from two depths.

**The practical consequence is unchanged and if anything firmer**: the headroom
cost is the *peak*, which is **≥ D** (+12.08 at D=12, +24.47 at D=24). Budget
the full Depth above nominal.

**Rig:** ROM #199 at its **default algorithm** — `PITCH / NONE / AMP`, F1/F2/F3
all OFF, so no filter anywhere can colour an amplitude measurement. Sine keymap
163, LFO1 (control source 114) into `F4 AMP Src1`, LFO1 at its default 2.00 Hz
sine giving ~4.5 cycles in the window. **Linearity verified before capturing**
(Adjust −18→−24 gave −5.95 dB against −6.0) — a clipped peak would have read as
"down only" regardless of the truth.

### The verdict line in the script was wrong while its numbers were right

It printed **"UP ONLY (peak +D above nominal)"**. The classifier tested only the
peak against `D`; `peak ≈ +D` matched a branch *defined* by the trough staying
at nominal, and the trough had moved to −D too. **Second instance the same day**
of a derived summary failing over sound inputs (§43's byte-detector printing
`[]` was the first). Both were caught by reading the raw rows. **Do not report a
classifier's label without checking it against the numbers it classified** —
and prefer printing the numbers next to the verdict, as these scripts do, so
the discrepancy is visible at all.

## 45. Filter corner measured with audio — the displayed Hz IS the corner (2026-09-02)

§KRZCUTCAL confirmed `440*2**((s-9)/12)` against the K2000's **own displayed
`Coarse:` label**, never against a measurement. AKAI/E4XT/MPC all have measured
−3 dB corners, so AKAI→KRZ was mapping a measured corner onto a display
convention with an unknown offset. Prediction stated before running: they are
the same. **They are.**

```
  2POLE LOWPASS, F3=NONE verified by DUMP
   displayed   fitted   resid(n=2)   ratio   source
      261.6    235.7      0.7        0.901   saw  note 24
      523.3    491.2      0.9        0.939   saw
     1046.5   1059.8      0.9        1.013   saw
     2093.0   1965.7      2.2        0.939   hihat note 60
     4186.0   3840.0      1.4        0.917   hihat
     8372.0   8539.3      1.0        1.020   hihat

  mean 0.9548  sd 0.0498  n=6  95% CI 0.915-0.995  -- no resolvable offset
```

**Pole count confirmed independently of the panel:** n=2 beats n=1 and n=4 by
~7 dB of residual at every low-band point.

**4-pole NOT established** — one trustworthy point (8372 Hz, ratio 0.884). A
24 dB/oct rolloff buries its stopband in the floor far faster; at 3.36% of real
layers it is not worth a flat-source rig.

### Redone with the real noise source — and the honest bound is ±10%

Jan loaded the §KRZCUTCAL bank (`CUTCAL.KRZ`) to **300ff**: eleven programs
`CUT 000`-`CUT 100` plus the **`CalNoise`** soundblock. Verified before use and
it is the right source — **sustained** (AMPENV loops; flat to 0.2 dB over 3 s,
so window placement cannot bias anything) and **flat to about 1 dB per octave**
across 63 Hz-16 kHz, comparable to mpc2emu's ±0.7 dB MPC benchmark. Reference
SNR 62 dB median, 100% of the band clear.

**The answer still moves with the ANALYSIS, not the instrument:**

```
  run                              n    mean     sd     range
  saw+hihat, fixed band 63-16k     6   0.955   0.050  0.901-1.020
  CalNoise,  fixed band 63-16k     5   0.912   0.063  0.868-1.022
  CalNoise,  adaptive band (2P)    8   0.856   0.212  0.363-1.051
  CalNoise,  adaptive band (4P)    5   0.965   0.079  0.877-1.043

  spread of the MEANS across analysis choices: 0.856 .. 0.965  (11 points)
```

**The fit-band policy shifts the result by as much as the effect being sought.**
A real corner offset would not move when the analysis band changes; this does.
So the 0.87-0.91 clustering that looked like a systematic ~10% offset in the
mid-band is **a method artefact, not a device property** — and that sensitivity
is itself the diagnostic.

Pooling every CalNoise point that passed both gates (n=10): **mean 0.939,
sd 0.073, 95% CI 0.893-0.984**.

**Conclusion, stated at the precision actually achieved: the displayed cutoff
and the measured corner agree to within ±10%, and no offset is resolvable.**
That is weaker than the ~1% the AKAI/E4XT/MPC corners carry, but it does rule
out a gross mismatch, which was the conversion risk. Tightening it needs a
different method (swept sine, or a proper analyser) rather than more runs of
this one — five attempts converged on the bound, not past it.

**Also learned: a low residual is not a quality gate.** The 65 Hz 2-pole point
fitted 23.6 Hz — ratio 0.363, plainly wrong — with residual **2.9 dB**, passing
a `resid<3` filter. A truncated curve is easy to fit well. Gate on usable
bandwidth *and* plausibility, not on residual alone.

### RESOLVED — the swept sine works, and it supersedes the ±10 % bound

**Cause of the earlier failure: the CUT programs sound on ONE KEY.**
`LoKey C 4, HiKey C 4` — they were built for a fixed-pitch noise calibration.
Swapping the keymap does not widen the layer, so 48 of 49 sweep notes were
silent and "pitch not tracking" was 48 noise-floor captures averaged with one
real tone. Purity 0.64 and 56 dB of reference spread were both that.
**Identical to the reference preset's layer bound in §36 — written up in this same file and
not applied.**

Found by Jan's one-note test, which settled it in a single capture where three
sweep runs had not:

```
  note   expect    FFTpeak   zero-x   autocorr   purity     rms
    48    130.8     150.0    6489.0      50.0    0.617   0.00003   NOISE FLOOR
    60    261.6     261.8     282.3     262.3    0.999   0.00050   perfect sine
    72    523.3     150.0    6537.1      50.0    0.615   0.00003   NOISE FLOOR
```

**Check the thing every later step assumes, on ONE sample, before scaling up.**

### The measurement

Rig: program 300 → keymap 163 Sine Wave, **layer widened C 1–G 9**, both
KEYMAP and PITCH `KeyTrk` at 100 ct/key, F2 RES 0, all modulation zeroed,
F3 asserted `NONE` by DUMP. Reference pass filter-open; per-note ratio is
|H(f)| directly — **no model, no fit band**.

```
  purity   median 1.000, min 0.999      span 12.2 octaves (4 .. 19188 Hz)
  flatness 5.4 dB p-p, sd 1.1 dB        plateau +0.0 dB

  2POLE   -3 dB at  1.259 / 1.265 / 1.203 x displayed   mean 1.242  sd 0.034
  4POLE   -3 dB at  0.783 / 0.775 / 0.722 x displayed   mean 0.760  sd 0.034
```

Three cutoffs four octaves apart agreeing to **3.4 %** each. **The offset is
constant with frequency and differs by filter type by a factor of 1.63.**

**The 4-pole has a structural explanation that nearly lands.** Two identical
cascaded 2-pole sections are −6 dB at the section corner, so the cascade's
−3 dB sits at **0.802 × corner**; measured 0.760, 5.3 % off. So the label
plausibly means the *section* corner and the 4-pole's offset is mostly the
cascade rather than a calibration error. **The 2-pole's 1.242 is unexplained** —
a Butterworth 2-pole should read 1.000.

**This supersedes the ±10 % bound above**, which came from a method with a
demonstrated ±11-point fit-band sensitivity and was simply too coarse to
resolve a 24 % offset.

### RESOLVED: the label is honest — it is f0, not a −3 dB corner

The Q question was tested by measuring the gain **at** the displayed corner,
rather than inferring Q from the −3 dB point (which would be circular):

```
  2-POLE   gain at displayed corner  -0.10 dB  ->  |H(f0)| = Q = 0.989
           -3 dB crossing at 1.264 f0          ->        Q = 0.986
           two independent readings of one curve, agreeing to 0.2 %

  4-POLE   gain at displayed corner  -6.11 dB  ->  |H(f0)| = 0.495
           as two cascaded sections =>  each 0.703  (Butterworth 0.7071, -0.5 %)
           that cascade predicts -3 dB at 0.802 f0; measured 0.774  (-3.5 %)
```

**There is no calibration error. The displayed cutoff is f0 — the section's
natural frequency — in both filters.** They differ in Q, and both values are
sensible:

- **2-pole runs Q ≈ 0.99: unity gain at the labelled frequency.** A deliberate
  design choice, not an accident — at zero resonance the response passes
  through 0 dB at the corner.
- **4-pole is two Butterworth (0.707) sections at the same f0.** Its −6.11 dB
  at f0 is 0.707², and its −3 dB necessarily falls below f0.

`SEP` was read back off the panel after writing (`Coarse 0ct, Fine 0ct,
KeyTrk 0ct/key, Depth 0ct`), so the sections really were co-located and the
cascade arithmetic applies — which is why 0.703 lands on 0.7071.

**The conversion still needs a correction, but not an error-correction.** The
label is honest f0; AKAI/E4XT/MPC corners are measured −3 dB points. Mapping
one onto the other:

```
  if the source number is a measured -3 dB corner:
    2-pole:  cutoff_byte_Hz = source_3dB / 1.264    (-406 cents)
    4-pole:  cutoff_byte_Hz = source_3dB / 0.774    (+444 cents)
```

**Opposite directions**, and the 2-pole case is 77 % of real layers — setting
the byte to the source's −3 dB frequency directly puts f0 about 4 semitones
high on the common case. **That is what the writer does today.** Held for Jan
rather than wired: one rig, one day, and a four-semitone change on the
dominant path deserves a listen first.

**Root cause, fixed on mpc2emu's side:** `VoiceLayer.filter_cutoff` was
documented as `#: Hz` and nothing else. **That is a unit, not a definition** —
two machines can both report "cutoff in Hz" and mean different frequencies,
which is exactly what happened. It now reads "the −3 dB corner, in Hz" with
each format's convention spelled out and the K2000's f0 flagged as the
exception. Same species as this project's earlier "physical quantity in one
machine's parameter scale" defects, but subtler: this one *was* in physical
units, just not the same physical quantity.

### Confirmed against an independent instrument (2026-09-02)

The f0 result was internally consistent but had never been checked against a
machine that measures corners the same way. The MPC does. Jan set it static
(`Cutoff 70`, envelope depth 0 → −3 dB corner **808 Hz**); K2000 program 403
(same converted bass samples, `2POLE LOWPASS`) was captured at two cutoff bytes,
note 48 velocity 100, identical window (0.3–2.0 s) and band (40 Hz–14 kHz).

**403 carried `F1 FRQ Depth 10800ct` from ENV2** — a nine-octave sweep that
hides a 406-cent change in the resting corner completely. Zeroed first; that
error had already produced one inconclusive run on mpc2emu's side.

```
    band     MPC       A(831)    B(622)     A-MPC     B-MPC
     630     -22.6      -7.8      -6.5     +14.8     +16.1
     800     -26.0      -8.1     -12.8     +17.9     +13.2
    1000     -32.6     -18.5     -26.4     +14.1      +6.2
    1250     -39.8     -31.5     -38.7      +8.3      +1.1
    1600     -50.2     -43.1     -49.6      +7.1      +0.6
    2000     -62.0     -59.7     -62.8      +2.3      -0.8
  mean |error| 1000-2000 Hz:   A 7.9 dB    B 2.2 dB
  crossing -40 dB:  MPC 1256   A 1498 (+305 c)   B 1287 (+43 c)
```

**B — the f0-corrected byte — tracks the MPC to within ~1 dB from 1250 Hz up;
A, which is what the writer ships today, is 7–8 dB brighter.** Three
independent lines now agree the label is f0: gain at the corner (Q 0.989), the
−3 dB crossing (Q 0.986), and an external instrument.

**The metric nearly inverted the conclusion.** The requested statistic was
spectral centroid. Over the same captures:

```
  centroid    A 585 Hz   B 547 Hz    (+115 cents -- right sign, far too small)
  rolloff85   A 391 Hz   B 458 Hz    (-272 cents -- WRONG SIGN)
```

Two summaries of one capture set **disagreeing in sign**. Both are dominated by
the bass fundamental far below either corner; rolloff85 asks where 85 % of the
energy sits and so reports the source, not the filter. Reported as asked, the
centroid would have read "115 cents where 406 was predicted — under-powered,
inconclusive", which is wrong. **On a pitched source, measure the filter where
the filter is acting** — the 1/3-octave slope above the corner — not with a
whole-spectrum statistic.

The cross-machine caveat shows up exactly where predicted: at 630/800 Hz both
K2000 versions sit 13–18 dB above the MPC, which is the converted sample's own
spectrum near the fundamental. Hence comparing **slopes above the corner**,
where the source difference has died away.

**Still not established:**
- **repeatability** — 1047 Hz measured twice per filter (2-pole 1.265/1.264,
  4-pole 0.775/0.774), but same rig, same day;
- ~~whether the source formats' numbers really are −3 dB points~~ —
  **ANSWERED by mpc2emu: all three are.** `akai_filfrq_to_hz` documents
  "FILFRQ -> the −3 dB corner in Hz"; §E4BFILTCAL read the E4XT's off a noise
  spectrum in 1/6-octave bands; §MPCCUTOFF fitted a 2-pole whose fc *is* the
  −3 dB point, and the MPC's resonance-0 response measures +0.15 dB, near
  enough to Butterworth that fc and −3 dB coincide. **So the K2000 is the odd
  one out and the correction is real, not a no-op.**
- the 4-pole's residual −3.5 % against the ideal cascade — small, possibly
  non-identical sections, not chased.

### Superseded: swept-sine attempt, rig verified, sweep did not sweep

Jan's idea, and the reasoning is right: a chromatic scale on keymap 163 (Sine
Wave) with pitch keytracking ON is a swept sine, which would remove all three
limits at once — SNR (all energy at one frequency, so a point 60 dB into the
stopband still measures), the topology assumption (read −3 dB off the curve,
no model), and the fit band (no such knob). It is the method that would take
the ±10 % bound to something tight enough to be a constant.

**It is not working, and the failure is well characterised rather than
mysterious.** Rig verified correct by DUMP and by reading it back:

```
  ALG 5, PITCH / 2POLE LOWPASS / NONE / AMP     F3 byte@241 = 60 (NONE) OK
  KeyMap 163 Sine Wave
  KEYMAP KeyTrk 100ct/key   AND   PITCH KeyTrk 100ct/key
  F2 RES 0, F1 Depth/VelTrk/KeyTrk 0, AMP VelTrk 0, Adjust -12 dB
```

and yet, across 49 notes spanning MIDI 24–120 (**eight octaves**):

```
  measured f range   148 .. 260 Hz     SWEEP SPAN 0.8 octaves
  purity             median 0.64       (a clean sine should be >0.95)
  reference flatness 56 dB p-p across notes
```

**The pitch is pinned and the tone is not clean.** Setting *both* KeyTrk fields
to 100 changed nothing — which rules out the obvious cause and is the inverse
of mpc2emu's original "set both to 0 to freeze pitch" warning. Purity 0.64 says
whatever is being measured is not a clean fundamental either, so the pinned
frequency may itself be an analysis artefact rather than the instrument's
output.

**Three gates refused to emit numbers, correctly**, on three successive runs:
the purity gate, the pitch/tuning gate, and finally a hard sweep-span gate that
skipped the cutoff passes outright. Earlier versions of this rig would have
produced ratios (0.301, 1.522, 0.217, 0.348...) that look like measurements.
**None of those are reported anywhere** — that is the gates working.

**Next step if resumed** (not attempted, ~9 attempts is where this stopped):
capture one long note at one pitch and inspect the waveform and spectrum
directly, before any sweep logic — establish that a single note produces a
clean sine at the expected frequency, which is the assumption every later step
rests on and the one thing never independently checked.

### This ROM has no noise, and no single source covers the band

All 192 ROM keymaps listed: nothing noise/white/pink. **Open Hihat (44)** gives
100% bin coverage of 63 Hz-16 kHz (sawtooth: 2.9%) and is spectrally a noise
substitute — its non-flatness divides out with the wide-open reference.

But **coverage and SNR trade off**: a cymbal spreads its energy over ~20000
bins where a saw concentrates it into ~400, so a closed filter drops the
hihat's stopband under the capture floor. The hihat starves below ~2 kHz; the
saw runs out of band above ~2.8 kHz. **Use each where it has signal.** Their
overlap at 2093 Hz is also where they disagree most (1.161 saw vs 0.939 hihat),
an edge effect on the saw side — the ratio drifts monotonically with where the
corner sits inside the source's band, which is how edge effects announce
themselves.

### Pressing the `F3` soft key does not switch F3 off

It **navigates to** that block's page. The block's **type** lives on the ALG
page. #199 defaults F3 to **BAND2** under algorithm 5, so a bandpass sat in
series with the filter under test in every earlier run — including §40 and §42,
whose claim to have switched it off is corrected there.

**Verify by SysEx, not by reading the screen** (Jan's suggestion, and it is the
general lesson). DUMP-diff of two saved copies:

```
  F3 block type = Program object offset 241     BAND2 = 35,  NONE = 60
```

Exactly one byte differed, and **NONE = 60 matches mpc2emu's `f3_byte` writer
constant**, derived independently. Runs now assert `byte@241 == 60` before
capturing.

### Two self-inflicted failures worth keeping

- **A clipped REFERENCE flattens everything.** One run railed every fit because
  the reference peaked at 0.418 against a ~0.10 ceiling — an AMP Adjust copied
  from a previous rig instead of chosen. Clipping flattens a spectrum, so the
  divided response looks open at every setting. Both sources now search the
  level down until the peak clears, and assert it.
- **A starved fit returns the search limit, not an error.** Fits that ran out
  of stopband returned exactly 20000.0 Hz — the top of the grid — with *low*
  residual, because a truncated curve is easy to fit. The SNR gate (% of fit
  band above the floor) is what makes that visible; without it the number looks
  like a result.

## 46. Six failures in one day, all the same shape (2026-09-02)

Across three sessions on 2026-09-01, six results were wrong. Not one was a bad
measurement — **every one was a sentence, label or assumption written on top of
sound data**, and every one looked plausible on the way out:

| | what was sound | what was wrong |
|---|---|---|
| §43 | the per-state byte diffs | the auto-detector printed `[]` (its set-intersection dropped the byte whose value happened to match the baseline) |
| §44 | peak/trough numbers | the verdict label said "UP ONLY" — it tested only the peak against a branch *defined* by the trough |
| §44 | the asymmetry itself | "probably my noise floor" — a hedge that turned out to be the device |
| §45 | the fitted corners | "F3 switched off" — the soft key navigates, it does not change the block type |
| §45 | the capture chain | an AMP Adjust copied from another rig, clipping the reference at 0.418 into a 0.10 ceiling |
| (mpc2emu) | the audio | an envelope indexed by schedule times, reading −240 dB from a capture peaking at −11 |

**The measurements were being checked adversarially and the layer on top was
not.** That layer is what reaches a constants file.

**Taxonomy (mpc2emu's, and it is the useful cut):**

```
  wrong label over sound data        a classifier verdict, a units ambiguity
  wrong hypothesis over sound data   "probably my noise floor"
  wrong index over sound data        an envelope indexed by schedule times
  wrong state assumed                F3/BAND2, bank-of-100, a copied AMP Adjust
  wrong statistic, computed right    spectral centroid on a bass note
```

The first four are all catchable by a better check — something is broken and a
gate can be made to see it. **The last is not**: nothing is broken anywhere,
every gate passes, the number is real, and it simply does not answer the
question asked. The only defence found for it is redundancy — **compute two
statistics of the same thing, and if they disagree, neither is the answer
yet.** On the §45 cross-machine capture, centroid said +115 cents and
`rolloff85` said −272 cents over identical data; the disagreement, not
judgement, is what prompted looking further.

**What actually caught each one was something independent disagreeing** — the
manual (F3 is part of the 4-pole, not a spare block), a prior measurement
(mpc2emu's `corner_frequency` reading 25% low), a control run built for a
different purpose (§40's flat KeyTrk-0 sweep, which turned out to be the only
proof that a rogue BAND2 was key-independent), a peer's corpus census, a second
gain setting. **Worth engineering deliberately rather than waiting for it.**

Practices that earned their place, all used above:

- **Print the numbers beside the verdict**, so a wrong label is visible against
  its own inputs rather than replacing them.
- **State a falsifiable prediction before the run** and report it failing. §40's
  filter-route prediction failed and the failure was the finding; §42's 4-pole
  prediction held and meant more for having been stated first.
- **Assert the rig, don't inherit it.** Levels, corner settings, block types —
  measured or asserted each run. Prefer a SysEx DUMP to a screen read (§45).
  **Including the audio path**: every capture script in this session wrapped
  its JACK `connect()` in `except Exception: pass`. A failed connect then
  yields a silent capture that analyses cleanly — the same silent-capture
  failure mpc2emu hit from a stale cached recorder, reached by a different
  route. Assert the connection, or at minimum assert the reference capture is
  above the noise floor before trusting anything downstream of it.

  **This was live, not latent.** mpc2emu's shared
  `tests/re_banks/krz_audio_measure.py::record()` printed the failure to
  stderr and recorded anyway; its caller is
  **`krz_stereo_measure.py:46`** — the KRZ stereo rig, which is *queued* for
  the next K2000R session (the channel-order question). So the hazard sat in a
  script waiting to be run fresh by someone trusting a helper that had worked
  before. Fixed there with a connection read-back, which also separates the two
  cases the old `except` conflated: **"already connected" is harmless,
  "missing port" is fatal**, and printing both then recording treats them
  alike. **Pull that read-back before running the stereo rig.**
- **Gate on both ends.** A starved fit returns the search limit with a *low*
  residual; a clipped reference flattens every spectrum. Neither announces
  itself.
- **A hedge is cheap; an assertion is not.** "Probably my floor" survived into a
  peer's notes marked unproven and cost one run to close. Asserted, it would
  have become a constant.
- **A confound that mimics the signal cannot be caught by looking at the
  signal** — it needs a control that varies something the confound does not.
- **"We never swallowed it" is a claim about the code; "the port is connected"
  is a claim about the world.** Only the second is what a measurement depends
  on. Every state bug this session had that shape: `byte@241` versus the panel
  read, bank-of-100 versus the MIDI spec, the layer key range versus what the
  program was built for. In each the code did exactly what it said and the
  world was arranged differently. **Read the world back.**

## 47. AMP `VelTrk` is Program offset 261, and the K2000 delivers it (2026-09-04)

The last leg of mpc2emu's `§KRZAMPVEL`: for years every K2000 voice their
converter wrote inherited ROM #199's `AMP VelTrk 35`, whether the source asked
for velocity response or not. They built a four-preset bank to test the fix on
the three machines at once — one shared 1 kHz sine at −6 dBFS on key 60, root
60, four presets identical in every respect *except* `AMP VelTrk`:

    program 800  'VT00 NULL'   VelTrk  0     <- the NULL is the point, not a warm-up
    program 801  'VT05 SOFT'   VelTrk  5
    program 802  'VT15 FULL'   VelTrk 15
    program 803  'VT36 AKAI'   VelTrk 36

**The byte: Program object offset 261, unsigned, 1 dB per unit.** Found by
reading all four objects whole (272 bytes) and printing *every* offset that
differs across the four — **no target byte in mind**. Exactly two varied:

    offset  800  801  802  803
       189   66   67   68   69     keymap pointer, low byte (834/835/836/837)
       261    0    5   15   36     AMP VelTrk

That method is worth more than the answer. A read of a named byte cannot fail
to confirm the byte you named; a differential dump can only report what
actually varies, and the second varying offset (the keymap pointer) is itself
the check that the four objects were otherwise identical. Confirmed
independently on the panel — `F4 AMP (FINAL AMP)`, Layer 1/1, algorithm 1,
chain `PITCH NONE ... AMP` — reading `VelTrk:0dB / 5dB / 15dB / 36dB`. Either
reading alone would have been a guess about the other.

261 sits directly beside §43's `Src1` at 262 and `Depth` at 263, which is the
same page. mpc2emu addresses all three as segment `0x53`, indices 4/5/6, and
**all three differ from these offsets by a constant 257** — two address spaces
over the same bytes, cross-checked from a direction that knew nothing about
this dump.

**Delivered in full, measured.** Ladder at key 60, velocities
1/16/32/48/64/80/96/112/127, peak level per note:

    program  byte   v127 dBFS   v1 dBFS   swing     error
    800       0      -14.16     -14.16     0.00 dB  +0.00
    801       5      -14.16     -19.43     5.27 dB  +0.27
    802      15      -14.16     -29.65    15.49 dB  +0.49
    803      36      -14.08     -50.21    36.13 dB  +0.13

The NULL preset reads flat across all nine velocities — peak-to-peak spread
0.097 dB, sd 0.036, max deviation from mean 0.072 dB. **A voice that asks for
no velocity response has none.** Note this is the same machine that in §36
measured a *constant ~5 dB shortfall* against its `VelTrk` setting on a
whole-signal RMS statistic; on peak level, with one flat sine and no filter
modulation anywhere in the program, the shortfall is gone. §36's shortfall was
never the amp — it was the statistic and the source material.

**The compression trap, checked rather than assumed.** mpc2emu had just lost an
E4XT leg to analogue compression ahead of the converter: staged by ear on one
loud note, the nine-point ladder came back 15.6 dB short at v127 with v112
measuring *quieter* than v96. Fitting 803's lower half (v1..v64) and
extrapolating:

    v  1  resid -0.03    v 48  resid +0.03    v 96  resid +0.28
    v 16  resid -0.30    v 64  resid -0.19    v112  resid -0.33
    v 32  resid +0.48    v 80  resid -0.66    v127  resid -0.41

The line through the bottom four points predicts v127 to within 0.41 dB — no
bend, no inversion, linear in velocity to ~0.5 dB across the whole 36 dB.
Loudest peak of the run was 0.198, ~14 dB below full scale. **Two endpoints
would not have shown this**: the E4XT looked fine at v1 and v127 and was
bending from v64 up. The inversion only appears if you have a middle.

**One imperfection, recorded rather than smoothed.** Normalising each preset to
its own v127 and dividing by its `VelTrk` should collapse all three onto one
curve. It nearly does — worst disagreement 0.109 of the 0..−1 range, at v48,
where 801 sits higher than the other two. In absolute terms that is 0.5 dB on a
5 dB preset. So the velocity *curve* is mildly `VelTrk`-dependent: endpoints
agree to well under a dB, the middle does not. Fitting an endpoint swing is
safe; fitting a curve *shape* is not, and would need measuring per setting.

**Two rig disciplines that earned their keep, both from prior failures here.**

- **One JACK client for all 36 captures**, not one per note — per-capture client
  create/destroy is what wedged jackd before (`[[jack-client-churn-wedges-jackd]]`),
  and the capture connection is **read back from the JACK graph** before
  recording rather than inferred from whether `connect()` raised. "Already
  connected" and "port missing" raise the same exception; only the graph tells
  them apart, and the second records silence that analyses perfectly.
- **Program selection verified, not assumed.** Program Mode draws the program
  number in the **graphics plane**, so ALLTEXT reads rows 1-6 as blank and
  cannot see which program is current. Each preset's identity was confirmed by
  opening the editor and reading its `VelTrk` off the panel before any note was
  played. This is not paranoia: §36 lost a run to a ladder captured against a
  program that had never changed.

### The load flow, staged (the OvFill path, done deliberately)

§34 left "a safe, tested load flow (bank select + mode select)" as future work.
This is it, and it was driven one screen at a time rather than as one script:

1. Browser at `\BANKS\`, select the file, press `OK` — **stop and read**. The
   K2000 answers with `Load this file as:200...299*` and a scrolling bank list.
2. The list scrolls **with the selection fixed on the label row** (row 3), one
   bank per alpha-wheel click. Wheel until row 3 reads `800...899`, verify it,
   then `OK` — **stop and read**.
3. The mode row appears, verbatim `OvFill Overwrt Merge Append Fill  Cancel`
   — the same string as 2026-08-30.
4. Before pressing anything, assert `soft_index(row, "Fill") == 4` **and**
   `soft_index(row, "OvFill") == 0` against the real row string, and refuse to
   press if either disagrees. Both held; `Fill` pressed.

The guard is the point. §34's bug pressed OvFill — which deletes the target
bank's RAM objects — while asking for Fill, and a remembered key position would
have hidden it again. Asserting *both* labels resolves correctly is cheap and
fails loudly. Load completed in ~3 s for a 158K bank; free sample RAM went
1305K → 1196K, program memory 409K → 405K. Programs landed at 800-803 as
predicted; **keymaps landed at 834-837**, appended after the 34 already
resident, and nothing resident was touched.

Corollary worth carrying: *"bank 800 is free"* was true for Programs and false
for Keymaps and Soundblocks. The DIRBANK survey said so plainly and it was
still nearly read as "the bank is empty". **A bank is empty per object type.**

## 48. LISTEN3 verified — and a 20.75 dB error that was never the amp (2026-09-04)

The real bank, after §47's synthetic one. Four presets, one per source, loaded
from `\BANKS\LISTEN3.KRZ` (23843K) into an empty bank 800. mpc2emu supplied
expected values **and named the trap in advance**, which is what made the read
falsifiable rather than a nod.

### Layer stride: 224 bytes

Object sizes came back 272 / 496 / 720 for 1 / 2 / 3 layers, so layer *n*'s
`AMP VelTrk` should be at `261 + 224*(n-1)`. That is a prediction from three
sizes, not a measurement, so it was printed with its neighbours and checked
against an independent panel walk of every layer. Both agree:

    program        panel                       dump
    800 MPC MIXED  2 layers  [0dB, 0dB]        261=0   485=0
    801 MPC SOFT   1 layer   [5dB]             261=5
    802 MPC FULL   1 layer   [15dB]            261=15
    803 AKAI VEL   3 layers  [36,36,36]        261=36  485=36  709=36

**800 is not a null and must not be read as one.** Its MPC source has four
voices asking for 0.0, 17.2 and 19.0 dB; the K2000's 3-layer cap forces a
reduction and the survivors come out at 0. At the *byte* that is
indistinguishable from a correct `VelTrk 0` — so the discriminator is the
**layer count**, not the value. Two layers both at 0 is the known loss; three
or four with differing values would have meant the reduction preserved them.
The honest statement is that the K2000 cannot hold that preset's velocity
structure at all.

### The 20.75 dB error, and why it was not the writer

Ladder at key 60, nine velocities, peak per note:

    program  byte   v127      v1        swing      error
    801       5    -20.78   -46.53    25.75 dB   +20.75
    802      15     -9.30   -24.35    15.05 dB    +0.05
    803      36    -10.40   -47.12    36.73 dB    +0.73

802 is exact — and it is the **only preset in the bank with no filter**
(algorithm 1, `PITCH NONE ... AMP`). Every layer's filter page had been read
**before** the ladder ran, precisely so the explanation could not be
retrofitted:

    800  F1 FRQ 4P LOPASS  VelTrk 7900ct  Src1 ENV2 Depth 10800ct
    801  F1 FRQ 2P LOPASS  VelTrk 5900ct  Src1 OFF
    802  no filter page at all
    803  F1 FRQ 2P LOPASS  VelTrk 3200/2700/3400ct  Src1 ENV2 Depth 9600ct

801 carries **5900 cents of velocity-to-cutoff with no envelope on the filter
at all**, so velocity alone opens it — and its ladder visibly saturates above
v64 (−22.79, −21.96, −21.77, −21.42, −20.78) as the corner passes the top of
the sample's own spectrum. Zeroing that one field and re-capturing:

    v1 -46.93   v16 -46.05   v32 -45.82   v48 -44.71   v64 -44.26
    v80 -43.64  v96 -42.92   v112 -42.37  v127 -41.78

    swing 5.14 dB against a byte of 5.  Error +0.14 dB.

**25.75 → 5.14.** The excess was entirely the source's own velocity→cutoff
routing. §47 had already shown the amp delivers `VelTrk` 1:1 on a flat sine
with no filter; this shows what a *peak* statistic does the moment a filter
route exists. **Peak level tracks velocity→filter as faithfully as it tracks
velocity→volume, and cannot tell them apart.** s3ked found the same thing on
the AKAI within the hour (one preset 14.42 dB over, excess vanished when its
filter route was zeroed), and mpc2emu predicted it here before the ladder ran.

Two disciplines this depended on, both from failures already in this file:

- The edit was made **with the editor open** and captured before exiting —
  a panel edit is live only while the editor is up, and `leave_editor()`
  answers the save prompt "No" (§36).
- The object was **DUMP-diffed before and after** rather than trusting that
  the edit took. "Nothing changed" is a broken experiment, not a null result
  (§40). Exactly one byte moved. 801 was then restored by exiting with No,
  and offset 213 verified back at 87 by a further dump.

**Cross-machine postscript, and the reason 20.75 was worth reporting as a
number rather than as "the filter".** The E4XT and the AKAI had both measured a
filter excess of **14.43 and 14.42 dB** from this same source — agreeing to
0.01 dB. mpc2emu wrote that up as two points, explicitly declined to call it a
shared constant, and said a third machine would separate the readings:

    E4XT    5958 ct   210 Hz resting corner            14.43 dB
    AKAI   ~5900 ct   FILFRQ 70, 12 dB/oct             14.42 dB
    K2000   5900 ct   2-pole LOPASS, no filter env     20.75 dB

The K2000 separated them. The agreement was a coincidence of resting corners,
not a law: **the level change from opening a filter depends on where the corner
starts and on the source's spectrum, not on the depth in cents alone.** Claimed
on two points it would have entered the notes as a fact and been wrong within
the hour. What survives, and is now confirmed on three machines with three
filter designs, is the weaker and actually-tested claim: the velocity→filter
depth converts faithfully, verified each time by removing it and watching the
excess vanish.

### New byte: `F1 FRQ VelTrk` is Program offset 213

Free from that diff. `5900ct` read as byte **87**, and `(87−28)×100 = 5900` —
the same cents encoding as §30's `ENV2->FilFreq Depth` at 215. But `0ct` read
as byte **0**, which that formula does not produce (it would give −2800), so
the bottom of the range is a different mapping.

**Deliberately NOT added to `k2kfields.KNOWN_FIELDS`.** Two verified points is
an offset, not a law: asserting §30's closed form over a different field on the
strength of one agreeing sample is exactly the overclaim that module's docstring
exists to prevent. The offset is solid and recorded here; the decode is a
candidate for the next session that can afford a proper sweep.

### The load-mode row has two shapes

Into a **populated** bank the K2000 offers
`OvFill Overwrt Merge Append Fill  Cancel`; into an **empty** one it offers only
`Append Fill  Cancel` — with nothing to overwrite, it does not offer to. §47's
guard asserted the six-label row and correctly **refused to press anything**
when the three-label row appeared. That is the guard working, not failing: it
was written to accept one known shape and it met an unknown one.

The fix was to teach it both shapes explicitly — full row requires `Fill`→E
*and* `OvFill`→A; empty-bank row requires exactly `["Append", "Fill", "Cancel"]`
and `Fill`→E — rather than to loosen it until it passed. **A guard relaxed to
make a run proceed is not a guard.**

Related, and the reason the earlier survey read oddly: the trailing `*` in
`800...899*` on the bank dialog **marks a bank that is not empty**. After
`Master → Delete → Everything` the same row reads `800...899` with no asterisk.
Every bank carried one in the earlier listings because every bank had something
in it.

### `Master → Delete → Everything` takes ~45 s of total silence

Run on Jan's direct instruction to free sample RAM. Free memory went
`Samples:1196K / Memory:405K` → `Samples:65536K / Memory:752K`, and every
object type read back empty.

**During the operation the K2000 answers nothing at all** — ALLTEXT returns a
blank screen and then times out for roughly 45 seconds before the device comes
back cleanly. This is normal for the operation and not a hang. Worth having
written down: this project already has a K2000 lockup on record from a
heartbeat arriving during a destructive object op, and a machine that looks
dead for 45 s is a machine somebody power-cycles mid-delete.

The confirmation prompt is a bare **`Are you sure?`** with `Yes / No` — it does
not restate the verb. A guard requiring the word "delete" in the prompt text
will refuse it, which is the right way round: read the prompt, then answer it.

## 49. What the audio rig does when nothing changes (2026-09-04)

Every measurement in §45, §47 and §48 was reported to two decimals without
anyone having measured how much this rig moves **when nothing moves**. That is
the same gap mpc2emu's `§MATRIXV4` diagnosed in their old confidence score:
three metrics combined into a number with no threshold below which a
difference was not a finding.

Program 802 (`MPC FULL`, the only preset in LISTEN3 with no filter page), key
60, velocities 1/32/64/96/127, peak per note. Two runs back to back with
nothing touched between, then a third after 45 minutes idle. `tilt` is the
slope of the 1/3-octave band differences at v127 against log frequency;
`shape` is the RMS of what remains after that slope is removed.

    NOISE  (back to back)     swing -0.004 dB   tilt +0.0091 dB/oct   shape 0.0816 dB
    DRIFT  (after 2700 s)     swing +0.081 dB   tilt +0.0170 dB/oct   shape 0.0579 dB

Alongside the sibling projects' own rigs, same source material:

    E4XT    swing 0.062   tilt 0.020   shape 0.145
    MPC     swing 0.000   tilt 0.001   shape 0.013
    K2000   swing 0.004   tilt 0.009   shape 0.082

**The drift swing figure is not uniform gain creep — it is one note.**
Per-velocity deltas across the 45 minutes:

    v1 +0.009    v32 +0.019    v64 +0.016    v96 +0.008    v127 +0.089

Four of five sit inside the back-to-back noise band; v127 moved +0.089 and
dragged the swing with it, because swing is `v127 − v1` and inherits whatever
happens at either end.

**Most likely the statistic, not the rig** — stated as a reading, not a
measurement. `peak` takes a single sample, the highest excursion in the attack,
so it is the least averaged number in the ladder, and the loudest note is where
the transient has most room to vary. The supporting observation is that
`shape` went *down* over 45 minutes (0.0579) versus back to back (0.0816): a
drifting box would show band energies diverging with time, and they did not.
Whatever moves is not accumulating.

Two limits worth keeping attached to these constants:

- **One 45-minute interval, measured once.** A single sample of a drift process
  is a data point, not a bound. Whether 0.089 is a ceiling or the middle of a
  distribution is unmeasured.
- **The box was idle throughout.** This bounds thermal and gain creep on a
  machine sitting still. It says nothing about the failure actually worth
  fearing — an xrun partway through real work — which needs a session with load
  in it.

**Practical consequence for every earlier section:** differences below about
0.1 dB in a peak-derived swing on real multisampled material are not findings
on this rig. §47's residuals (0.00 / 0.27 / 0.49 / 0.13 dB) and §48's 802
result (0.05 dB) sit above or near that floor and survive; §48's 803 residual
of 0.73 dB is comfortably real. Anything a future session reports below 0.1 dB
as a *difference* needs either a tighter statistic (an RMS or sustain-window
average, both far better averaged than peak) or a repeatability pair of its own
run alongside it.

## 50. A bank load that silently drops a third of itself (2026-09-04)

mpc2emu's matrix bank, `MX_mpc_to_krz.KRZ` (`MXMPCTOK.KRZ` on SCSI 5 — the
K2000's filesystem is 8.3 and mangles the name, which is worth knowing before
anyone searches the card for the original), loaded into bank 900 with `Fill`.
It reported success. **A third of it was not there.**

### 100 objects per bank, per type — and `Fill` stops silently

    file: 11 programs (ids 200-210), 22 keymaps (200-221), 149 samples (200-348)

    loaded at bank 900:  Soundblock bank 9: 100, ids 900..999   <- exactly 100
    loaded at Everything: Soundblock bank 2: 100, ids 200..299
                          Soundblock bank 3:  49, ids 300..348   <- all 149

A K2000 bank holds **100 objects of each type**. Loading into a *specific*
bank re-banks every id into it ("the bank digit is ignored, and the remainder
is used" — manual, Disk Mode / Load Function Dialog), so 149 samples were
asked to fit in 100 slots and **49 were discarded with no error, no warning
and a normal-looking return to Disk mode**.

Free sample RAM was **21,661K at the moment it stopped** — it did not run out
of memory, it ran out of ids. A limit that bites with a third of memory free
is a count, not a capacity.

**The manual documents the way out, and it is a destination, not a mode:**

> "For loading as 'Everything', the ID number for an object stored in a file
> is taken literally, and not re-banked (except if Fill or OvFill mode is
> chosen, in which case the K2vx will use ID numbers starting from 200.)"

`Everything` + `Fill` numbered from 200 and spanned banks 2 **and** 3.
Verified by control: same file, same mode, only the destination changed, and
`Soundblock TOTAL` went 100 → 149 with sample RAM consumption 20,044K →
25,553K against the 24.8 MB of PCM the file carries.

Also documented and separately useful: **`Overwrt` "will individually
overwrite objects in the bank following the just filled bank"**, and `OvFill`
"skips over object IDs that are in use". So a specific-bank load is not
inherently capped — **`Fill` is the one mode that simply stops.** And a load
into bank 9 cannot work in *any* mode, because there is no bank 10 to spill
into.

**No writer change was needed.** The converter's `_MAX_OBJ_ID = 999` against
`base_id = 200` describes exactly what the K2000 did when asked properly. The
fault was the load destination.

### Truncation does not merely lose objects — it repoints zones at wrong ones

The nastier half, found by walking keymap zones on the panel. On the
truncated load, the top zone of every layer of `Lead-PRO5 Lollipop` read:

    keys B 4-G 10   smp 999*elodic-PD46 Syn4-D#3

`999` is the saturation boundary and `…elodic-PD46 Syn4` is the **drum
program's** material. A zone that referenced a sample past the ceiling did not
end up dangling or silent: it ended up pointing at whatever object occupied
the clamped id. **A wrong-object reference is worse than a missing one,
because it plays.**

And it is not confined to the top. The same program measured **7 dB louder at
key 36** and **16 dB different at key 60** after the clean reload — same
program, same notes, only the destination changed. **The truncated bank was
wrong in the middle as well as missing at the top**, which is why the first
530-note grid was rerun rather than annotated.

### The high keys were never the truncation — nor the rate ceiling

The obvious story — high keys silent because the high-rooted samples were the
ones dropped — was wrong, and only a control showed it. `Bass-Dark-The Poker`,
v127, same rig, only the load destination changed:

    bank 900    k36 -9.87  k48 -3.03  k60 -14.86  k72 -4.96  k84 -52.84  k96 -75.37
    Everything  k36 -3.92  k48 -4.37  k60 -30.54  k72 -7.79  k84 -61.98  k96 -76.48

**k84 and k96 are silent with all 149 samples resident.**

The *second* story was also wrong, and this one had numbers behind it. The
top keymap zone points at a sample stored at **24000 Hz** where its neighbours
are at 42762 — exactly the converter's own `_KRZ_RATE_FLOOR` — and the panel
reports that zone running to the top of the keyboard, so playing key 84 would
need 50,854 Hz and key 96 would need 101,708 Hz. Silence above roughly +12
semitones fitted a playback ceiling near 48 kHz, and the arithmetic, the file's
rate field and the measurements all agreed.

**The actual mechanism is the LAYER bound, and the panel says so plainly:**

    program 205 'Bass-Dark-The Poker'   all three layers   HiKey: B 5   (= MIDI 83)
    program 200 'LD Vintage Acid'       layer 1/1          HiKey: G 9   (= MIDI 127)

205 stops at **83**. Keys 84 and up are outside every layer of the program, so
nothing sounds because **nothing covers them** — no zone is being asked to
stretch past any ceiling. 200 runs to 127 and sounds at k84 normally, which is
the control.

Both readings of the keymap were correct and were about different objects: the
keymap *zone* really does run to the top, and the *layer* selects which part of
it applies. Conflating the two is what produced a rate-ceiling explanation that
fitted every number and named the wrong cause. mpc2emu's parser had the mirror
image of the same fault — indexing a full 128-key table without applying each
voice's key range.

The rate floor is probably still what *sets* the limit: the writer's stretch
window ends +12 semitones above the top sample's root (71 + 12 = 83), which is
exactly where `HiKey` sits. **The bug is that it then does not extend the outer
zones to the keyboard edges.** Coverage:

    MPC source    keys 0-127
    KRZ output    keys 12-83        56 of 128 keys lost, at both ends

**Two independent measurements agreeing is not evidence when both can inherit
the same class of fault.** The drum "collapse" was reported from two sides —
a hardware level ramp and a file-side keymap read — and *both were wrong*: the
ramp came from a truncated bank playing clamped references, the parse from a
mis-indexed table, and they matched because a repeated wrong sample and a
mis-indexed table produce the same signature. The E4B control stood outside
both and said sixteen distinct samples; it was cited as corroboration when it
was the only real evidence, and it was disagreeing. **There was never a drum
collapse.**

### How wrong the truncated grid was — measured, not estimated

Both 530-note grids were captured with the same rig, same windows, same
bands, so the truncated load can be compared against the clean one directly.
v127 peak level, per program and key:

    66 cells   median delta +2.44 dB   mean |delta| 4.72 dB   35 cells over 3 dB

    LD Casiopaya 9   k36   -50.11 -> -24.21   +25.90
    LD Vintage Acid  k48   -29.53 -> -13.07   +16.46
    Bass-MS20 Antima k84   -24.40 -> -10.02   +14.38
    LD Tube Pipe     k36   -23.38 -> -12.16   +11.22

**Over half the grid moved by more than 3 dB.** A load that reported success
and returned normally to Disk mode produced a data set that was wrong almost
everywhere, and nothing in the capture path could have detected it — every
note sounded, every measure computed, every row looked plausible.

Two specific consequences worth keeping:

- **A withdrawn finding.** On the truncated load the drum probe showed keys
  36-45 marching in a smooth 0.02 dB/key ramp — the signature of one sample
  transposed — which was reported to mpc2emu as evidence for a keymap
  collapse in their writer. On the clean load the same sixteen keys give
  scattered levels. **The ramp was the truncated bank playing clamped
  references.** The caveat given at the time ("level cannot prove sample
  identity; this is a pointer, not a verdict") turned out to be the entire
  load-bearing part of the claim.
- **A false positive that would have been believed.** `Bass-MS20 Antimatter`
  has `AMP VelTrk 0` and on the clean load delivers 0.03-0.70 dB of velocity
  swing — correct. On the truncated load it showed **15.44 dB**. Scored, that
  reads as a converter inventing velocity sensitivity the source never asked
  for: a plausible, specific, entirely fabricated defect.

**"Missed onsets" were a symptom of it, not a separate bug.** `LD Casiopaya
9` fell back on 17 of 45 notes for want of a detectable onset, which looked
like slow-attack material defeating the search window. On the clean load it
is 0 of 45 — the program had simply been 26 dB too quiet to trigger
detection. A measurement artifact can masquerade as a limitation of the
measuring method.

### What made the difference, methodologically

- **The variable neither session varied was the destination.** Both had built
  a confident account of a writer bug from one load into one bank. Jan asked
  "did you reload at a lower bank and re-measure?" from outside both chains of
  reasoning, and the answer took an hour of analysis with it.
- **`exactly 100` had appeared three times earlier in the night** — banks
  600/700/800/900 each reporting exactly 100 Soundblocks — and was read as
  "this is what a full bank looks like". It was the ceiling, unremarked.
- **A fingerprint that collides is not an identity check.** The first attempt
  at verifying which program was selected used the F4 AMP fields and collided
  on six of eleven programs, because the converter writes the same amp
  settings to most voices. The keymap pointer (bytes 188-189, cross-checked
  against the KEYMAP page) is unique. Program Mode draws the program number in
  the **graphics** plane, so ALLTEXT cannot read it and something else has to.

## 51. Rig faults found while driving it hard for six hours (2026-09-04)

Five things that each looked like a result and were not. Recorded because
every one of them produced a clean, confident, wrong number rather than an
error.

**"No K2000 answered on any of 38 output ports" was a leaked file
descriptor.** A peer session's capture script was creating an
`rtmidi.MidiOut` per capture without `delete()`, and had accumulated 22 ALSA
sequencer clients, then 48, then 51. `MidiBridge.autodetect()` opens ~70 at
once (one per output port to probe, plus every input to listen on), so it hit
`snd_seq_hw_open: Cannot allocate memory` and reported the instrument dead.
**The instrument was fine and answering.** Two lessons: *"no device answered"
is a claim about your ability to ask, not about the device*; and autodetect's
client burst makes it the first thing to fail on a busy machine, so a rig that
knows its ports should say so — `MidiBridge.split_rig(send_port="ESI M4U eX
MIDI 8", recv_iface="ESI M4U eX")` needs 9 clients, and a single named
bidirectional port needs 2. (The same leak is on record here from 2026-07-12:
`close_port()` does not free the backend client; `delete()` must be called.)

**Windows placed on the commanded note-on, not the audible one.** The rig
sends the note, so the commanded instant is exact — and it is not when the
sound arrives. Measured MIDI-to-audio lag on this machine: **24-78 ms**
(rtmidi → mididings → USB → K2000 → converters → JACK) against an attack
window that opened at 20 ms. Every attack window was landing **before the
note**. The data said so on its own: a decaying note read *quieter* at its
attack than 100 ms later, which is impossible, and that column had been read
twice without noticing.

Fixed by anchoring each note's windows to its **detected onset** — threshold
relative to that note's own peak (velocity-invariant), searched near the
commanded instant. A single measured constant would have been wrong: the
78 ms figure is a quiet note crossing a fixed threshold late, not transport.

**A search window is a prior, and a prior that excludes the truth produces a
confident fallback rather than an error.** The first onset search looked
250 ms past the commanded on. Slow-attack material lands later, so four
programs fell back on 9-25 notes each — and a fallback places the windows
before the note, the exact artifact the anchoring existed to prevent. Widened
to 600 ms. Some notes still fall back, and `peak_time_s` (added for exactly
this) shows why: they peak at **1.7-2.1 s**, *after* note-off. Those are not
slow attacks a wider window can catch; a note loudest two seconds in is not
described by attack/early/mid windows at all. Flagged, not chased. (Worth
noting they have the same shape as §33's unrooted envelope swell.)

**A fallback is two different things and counting them together hides both.**
A row with no detected onset is either a **silent note** (correct — there is
nothing to find) or a **detector miss** (wrong — windows before the note), and
they are identical in the file unless the level is checked. Separated: one
program showed `45 = 45 silent + 0 missed` (a genuinely silent program,
correctly handled) and another `17 = 0 silent + 17 missed` (a real fault). One
number would have concealed both.

**Never pipe a long-running hardware script into `head`.** SIGPIPE killed one
mid-run and left the panel inside `EditKeyMap` — whose soft row carries
`Delete` and `Save`. Backing out safely means pressing **only** `Exit`, and
answering the save prompt (`Rename | Cancel | Yes | No`) with `No`. Redirect
to a file and read the file.

**A window artefact produces a plausible number on a healthy note, and no
flag can catch it.** Three keys of a drum kit measured 2.96 / 3.84 / 4.49 dB of
velocity swing where the other thirteen gave 8.75-15.64, and were reported as
possibly degenerate. They are not: those three samples are 55-80 ms long and
the `early` window opens at 100 ms, so the sample had finished before the
window started. The same captures, read on other statistics:

    key    PEAK swing   attack sw   early sw   v127 over floor
     37      15.06        17.98       2.96          78.7 dB
     41      15.48        15.53       3.84          77.1 dB
     45      15.89        16.70       4.49          78.2 dB
     all 16  13.58-15.89                            72.3-87.6 dB

**This is invisible to the silent-versus-missed separation above**, which only
inspects rows where onset detection *failed*. Here detection succeeded, the
note was 78 dB over the floor, and the number was simply a measure of something
else. The only defence is more than one statistic over the same capture —
which is why the grid records peak plus four RMS windows rather than the one
window originally asked for. **The question was answered from stored data in
seconds; a single-window grid would have needed a reload and a re-run**, by
which time the wrong claim would have been in a table.

The same fault crossed three sessions in a different costume the same day: a
peer reported keys as "silent" meaning "silent in the window I scored", the
qualifier was lost in the summary, and this session then matched that against a
*different* window and manufactured a conflict between two true statements.
**A summary crossing a session boundary loses the condition that makes it
true.** State the condition, or state a raw number.

**A screen read can come back as something that is not a screen.** A script
asserting on `rows(b)[0]` failed with:

    AssertionError: Panel(button_events=[ButtonEvent(event_type=Down,
                    button=Button.Edit, alpha_wheel_clicks=63)])

`get_screen_text()` had returned a **panel-event message** — the K2000
reporting button activity, most likely a physical press at the panel — where
every script in this project assumes a string. It failed loudly and before
touching anything, which is what the assertion was for, but the assumption is
worth naming: **the reply to a screen request is not guaranteed to be a screen
reply**, and a script that indexes it without checking will fail somewhere
less obvious than an assert. It is also a concrete reason not to drive the box
while someone is at the front panel.

**Measured rig characteristics, for anyone setting a threshold against them.**

    noise floor        -90.7 dBFS typical, worst silent window -83.7
    inter-capture bleed none: a v127 note followed by a capture with no note
                       played reads at or below the silent floor
    repeatability      back-to-back  swing 0.004 dB, tilt 0.009 dB/oct, shape 0.082 dB
                       after 2700 s  swing 0.081 dB, tilt 0.017 dB/oct, shape 0.058 dB

The drift swing is one note: v127 moved +0.089 dB while the other four
velocities sat at 0.008-0.019, and `shape` went *down* over the interval,
which is not what a drifting box looks like. Peak takes a single sample and is
the least averaged statistic in the ladder — see §49.

## 52. A program with >3 split layers only sounds on the drum channel (2026-09-05)

`Lead-PRO5 Lollipop` measured **silent on every key from 0 to 96** across two
different bank builds and two different loads — 8 enabled layers covering the
whole keyboard, all velocities, `Adjust 6dB`, every zone with a sample
assigned, samples present in RAM with real PCM. §50 recorded it as unexplained
after truncation was excluded by experiment.

It was never silent. **A K2000 program with more than three *split* layers is
a drum program, and a drum program sounds only when the played channel matches
`DrumChan` on the Master page.** Lead-PRO5 has 8 layers; everything else in
the bank has 1 to 3.

    202 'Lead-PRO5 Lollip' v127, played on channel 9   (DrumChan 8):
        every key -76 .. -71 dBFS, no onset          silent

    same program, DrumChan moved to 10, played on channel 10:
        k36 -14.38  k48 -12.63  k60 -11.21  k72 -8.96  k84 -11.14
        onsets detected on all five                   normal

The converter had said so in its own build log, in as many words, including
why it declined to fuse the layers down to three: *"a faithful four-layer
electric piano is SILENT on a normal channel, which is not a subtler rendering
of the preset, it is no rendering at all."* **Three sessions spent hours
reverse-engineering a fact the tool that produced the file had already
printed.** Nobody asked whether the generator had anything to say about the
artefact before measuring it.

**The drum channel is not otherwise special, and an inference that it was cost
a wrong explanation.** A one-layer program sounds on the drum channel exactly
as it does anywhere else — `LD Vintage Acid` gave −13.57 dBFS on channel 10
with `DrumChan` set to 10, against −13.56 when 10 was an ordinary channel. So
"is this the drum channel?" explains a drum program's silence and nothing
else. This session had claimed the opposite from a single failed control.

**A separate fact about this rig, unexplained and worth knowing: channel 8
does not reach the instrument.** Normal and drum programs alike are silent
there, both through `mididings_k2000r` and by sending straight at
`ESI M4U eX MIDI 8`, while channels 9 and 10 sound normally over the same
paths. `~/mididings_k2000r.py` does run `ChannelFilter(9,10,11,12,13,16)`,
which explains the mididings route but not the direct one. Not chased —
nothing depends on it — but a test that needs channel 8 will fail for reasons
that have nothing to do with the instrument's programs.

**Measured properly, the program converts correctly.** Full grid row on the
drum channel — 45 notes, 0 onset fallbacks:

    key   peak v1..v127        peak swing   attack-RMS swing
     36   -30.01 .. -14.29       15.73          10.71
     48   -32.36 .. -12.65       19.71          20.69
     60   -25.78 .. -11.31       14.46          19.02
     72   -25.28 ..  -9.22       16.07          15.92
     84   -27.92 .. -11.25       16.68          23.89

Note that **`mid` sits at the floor (−89.6 to −90.0 dB) on every one of those
notes** while `attack` and `full` carry real signal: the samples are short
enough to be over before 0.4 s. Scored on `early` or `mid` this program would
read as near-silent *again*, for the third time in one bank and the second
distinct cause — see §51's window artefact. **A statistic that reads a healthy
note as silent has now produced a false defect on this material three times.**

**Consequence for measurement data:** a grid captured on channel 9 records
*valid observations of the wrong experiment* for any drum program in the bank.
The rows are not wrong; they are not a measure of the conversion either, and a
scoring pass that reads them as 0.000 is scoring the channel assignment.

## 53. Two RAM edits that tested two fixes — one confirmed, one refuted (2026-09-05)

Both run separately, both restored and verified, nothing on the card touched.

### Keymap object layout, and the wrong-sample fix

**Keymap entries are 6 bytes, with the sample id at `31 + 6i` as a 16-bit
big-endian value.** Found by dumping the object and listing every offset
holding a plausible sample id: the result reads as a run-length structure and
the runs line up with the zones the panel shows.

    keymap 215 (Bass-Dark, 668 bytes), entries 0..53:
      312 x17, 313 x5, 314 x5, 315 x5, 316 x5, 317 x5, 318 x5,
      311 x5, 320 x5, 321 x49

**`311` sits exactly where `319` belongs** — the ascending run breaks for five
entries and resumes. That is the noise sample in a bass keymap, and 319
(`nderhand-061 Db3`) is the bank's one unreferenced sample: the same defect
seen from both ends. Patching those five low bytes (311 = `0x0137`,
319 = `0x013F`, so one byte each) across all three layer keymaps:

    k 48   -3.75 ->  -4.22    -0.47 dB   (control)
    k 60  -32.58 ->  -2.62   +29.96 dB   <-- target
    k 72   -7.09 ->  -4.39    +2.70 dB   (control)

Key 60 moves from 28 dB below its neighbours to level with them. **The
control that moved 2.70 dB is not an effect**: that note has read between
−4.4 and −7.8 dBFS across six runs today, so both controls are inside their
own spread. Worth stating rather than quietly reporting only the target.

### The up-pitch ceiling is far higher than the writer assumes

§50 recorded the top of `Bass-Dark` as unreachable because the layer stops at
`HiKey 83`, and the working theory — held by both sessions — was that the
writer stopped there because the zone's sample (root 71, stored at 24000 Hz)
could not be pitched higher. Prediction: extending the bound would give
silence or a mistuned note.

**Program offset `53 + 224n` is the layer `HiKey`** (the only byte reading 83
on all three layers; neighbourhood `[0,0,0,83,0,127,0]`). Patched to 127 and
**verified on the panel before measuring** — `HiKey` read `G 9` on all three
layers, so the byte is what it was taken for.

    k 83  -2.34 ->  -2.50    -0.16 dB   (control -- did not move)
    k 84 -75.75 ->  -2.44   +73.31 dB
    k 96 -75.76 ->   0.00   +75.76 dB

**Level alone would have been the wrong evidence** — the prediction allowed a
mistuned note, which is loud. So: strongest partial per key, v96 (v127 clips
the capture above k91), across the whole range:

    key  +st   partial     key  +st   partial
     83   12    492.2       90   19    369.1  (= 738.2 / 2)
     84   13    521.5       91   20    389.6
     85   14    550.8       92   21    413.1
     86   15    585.9       93   22    436.5
     87   16    621.1       94   23    928.7
     88   17    659.2       95   24    984.4
     89   18    697.3       96   25    984.4   <-- identical to key 95

A clean semitone ladder from +12 to +24 (492.2 × 1.0595 = 521.4, and every
step tracks to within a bin), then key 96 returns **exactly** key 95's
partials. **The rate caps at +25 and nowhere below.** Keys 84-95 play at the
correct pitch and full level, and are silent in the shipped bank for no
reason — twelve semitones of usable range discarded.

For this sample +24 is a playback rate of 96 kHz and +25 is 101.7 kHz, so the
limit looks like an absolute rate ceiling near 96-102 kHz rather than a fixed
transposition. **Measured on one sample at one stored rate** — a 44.1 kHz
sample would presumably hit the same wall around +12, and +24 must not become
a constant until a second rate has been checked against it.

### It is an absolute rate ceiling of 96 kHz, on two samples an octave apart

One sample at one stored rate cannot separate an absolute rate ceiling from a
fixed transposition, so the +24 above is not on its own a law. The
discriminator needs no second stored rate to be *known*, only to be
*different*: repoint the top run at a neighbouring sample and see whether the
cap lands on the same semitone offset.

Repointed keymap entries 57-105 in all three layer keymaps from sample 321
(root 71) to sample **320** (root 66) and swept. Exact stored rates, read out
of the file afterwards from integer-nanosecond periods:

    smp 321  root 71  23999.808 Hz    +24 -> 95,999.2 Hz  plays   +25 -> 101,707.6 Hz  caps
    smp 320  root 66  42762.455 Hz    +14 -> 95,998.5 Hz  plays   +15 -> 101,706.8 Hz  caps

**Both last-playing rates are 95,998-95,999 Hz; both first-capped are
101,707 Hz.** Different samples, different semitone caps (+24 against +14),
same absolute rate — so the limit is a playback rate and a fixed transposition
is dead. It matches a `96000` already present in mpc2emu's
`_compute_base_pitch()`, twenty lines from the `48000` its
`_compute_max_pitch()` clamps with.

Their corpus evidence for 48000 (sr=30k → +814, sr=15k → +2014) is not a
contradiction: those are values authors *stored* in a maxPitch field, an
authoring convention, and **the machine plays an octave past it.** Two true
observations about different things, which is why this stayed hidden.

**Two samples could only bracket it, and the reason is arithmetic rather than
effort.** Their rates are 23999.808 and 42762.455 Hz — a ratio of 1.78177,
which is 9.98 semitones. **They sit on the same semitone grid**, so their step
ladders land in the same places and bracket the ceiling identically: four
points, one constraint. The bracket was `(95,999 , 101,707) Hz` — one semitone
wide, excluding 48000 outright but admitting 100 kHz as readily as 96000.

Narrowing needed a rate that is *not* a semitone multiple of 24 kHz. Of the
six stored rates in this bank, five sit on that grid to within 0.0004 of a
semitone; only a 44.1 kHz group is off it, and it reaches **99,000 Hz at +14**
— inside the bracket.

### The capped pitch measures the ceiling

Sample **220** (`elodic-PD46 Syn4`, root 51, 44099.488 Hz), pitched rather
than one of the twelve drums at the same rate — a partial ladder cannot be
read off a kick:

    key  +st     f0 Hz    commanded playback
     64   13    196.32          93,444 Hz     last playing
     65   14    201.87          99,000 Hz     CAPPED
     66+  15+   plateau at 201.78 +- 0.37 Hz through key 72

**99,000 Hz does not play, so the ceiling is below it and 96000 survives.**

But the plateau is not merely "capped" — **it is the ceiling expressed as
pitch**, and that turns a bracket into a measurement. Key 64 plays at a known
93,443.6 Hz and reads 196.32; the plateau reads 201.78, **+0.475 semitones**
above it:

    ceiling = 93,443.6 x 2^(0.475/12) = 96,044 Hz     (plateau mean)
            = 93,443.6 x 2^(0.483/12) = 96,085 Hz     (key 65 alone)

**0.8 cents from 96,000 (+0.05%)**, and consistent with all six observations
across the three samples. A capped note does not need a bracket around it: the
frozen pitch *is* the limit, referred to a key whose rate is known.

**Caveats, the first being the one that matters.** The f0 estimator (harmonic
product spectrum) **jumps harmonic rank on several keys** — steps of +4.00,
−1.95 and −10.90 semitones appear between rows that are certainly one semitone
apart, so the low rows are not a pitch measurement. The boundary rows are
trustworthy for a narrower reason: key 64, key 65 and the whole plateau lie in
the same rank (196-202 Hz), so the *ratio* between them holds whatever the
rank is, and the plateau is flat to 6.3 cents over seven keys.

And **the first attempt clipped at 0.00 dBFS on every note.** This program has
almost no velocity response, so a lower velocity does not help — attenuating
the instrument with **CC7 = 40** (restored to 127 afterwards) fixed it. The
clipped run put the boundary in the same place but its middle rows were worse.
A clipped capture is exactly the input that makes a harmonic estimator
confident and wrong.

**Outcome of the fix on the peer's side**, recorded because it is what the
measurement was for: `_compute_max_pitch()` had two callers doing different
jobs, and the 48000 was the right constant for the wrong one. The stored
`maxPitch` field keeps 48000 (an authoring convention that matches every real
soundset and does not gate playback); how far a zone may *extend* moved to a
new ceiling at 96000. Over 69 banks / 2160 zones: **zones lost entirely
78 (3.6%) → 0**, zones clipped at the top **899 (41.6%) → 380 (17.6%)**. A
"lost" zone was never silence — hole-filling extended a neighbour across those
keys, so they sounded the wrong sample.

**An off-by-one in reading this sweep cost the peer session an hour.** The
first report said sample 320 "tracks to +13, caps at +14". It tracks to +14
and caps at +15: key 80's partials happen to equal the frozen value, because
the frozen value *is* the +14 rate that everything above clamps to, and the
first frozen row was read as the first *distinct* one. That one-row shift made
the two samples disagree by a semitone, which produced a 0.17 ns anomaly, two
incompatible framings that each fitted three of four points, and a
frame-offset hypothesis — none of which existed. **Computing the ratios
between consecutive rows takes one line and would have caught it; looking at
the column and deciding where it changes did not.**

    k78 -> k79   1.0555  = +0.94 st   tracking
    k79 -> k80   1.0603  = +1.01 st   tracking     <-- misread as the cap
    k80 -> k81   1.0000  = +0.00 st   capped

**The failure mode above the cap is the dangerous kind.** The note does not go
silent: it plays at −5 to −6 dBFS, cleanly, at a frozen wrong pitch, for
seventeen consecutive keys. **A peak or RMS measurement scores every one of
those keys as a success.** Only the partials show it.

That is the third distinct mechanism in one day with the same signature — a
plausible number measuring the wrong thing. The others: §51's window artefact
reading a healthy note as silent, and §50's truncated bank manufacturing
15.44 dB of velocity response on a program whose `AMP VelTrk` byte is 0. **A
number being reasonable is not evidence that it is a measurement of what it is
named after** — and the transcription slip above is a fourth, cheaper variant:
a number that measured the right thing and was read wrong.

**Limitation of the sweep, stated because the correction above depends on
knowing it:** the partial ladder is only cleanly readable from key 78 upward.
Below that the top-three-partials picker latches onto different harmonics
between keys (k75→k76 reads +5.82 semitones, an artefact). The
tracking/capping boundary is unambiguous because it lies in the readable
region and the frozen rows are bit-identical, but the low rows are not a pitch
measurement.

### Method notes

- **A byte found by value search is a candidate, not a field.** Both offsets
  here were confirmed against the instrument's own display before anything was
  measured — the keymap by its run structure matching the panel's zones, the
  `HiKey` by reading `G 9` back off the LAYER page after patching. §51's list
  of confident wrong numbers is what that habit exists to avoid.
- **`patch_object_bytes` made the keymap edit possible at all.** A panel edit
  would not survive: three layers use three keymaps, only one editor can be
  open at a time, and §36's rule is that panel edits die when the editor
  closes. A SysEx patch persists in RAM, so all three could be changed and
  then measured together.

## 54. Measuring two converter fixes, and a mean that lied (2026-09-06)

`MX9MPCKR` (MATRIX6) against `MX8V501` (MATRIX5) — same eleven MPC source
programs, same `convert.py` invocation, differing by mpc2emu's 96 kHz ceiling
fix and a headroom-downsampler fix. Both grids captured with the same rig, the
same four windows and the same 25 bands, matched **by program name**: the slot
order differs between builds, so an index match would compare one program
against another.

    ceiling fix        WORKS, and correctly    k84 -75.74 -> -2.99 dBFS, right pitch
                                               layer HiKey 83 -> 95
    drum-program flag  WORKS                   Lead-PRO5 plays on ch9, 45/45 onsets
    headroom fix       NO measurable effect    +0.17 dB level = rig offset; the
                                               apparent +7 dB spectral tilt was retracted
    wrong sample       NOT FIXED, MOVED        noise run keys 59-63 -> keys 70-74
    key 85 artefact    invisible to this rig   right pitch, right level, wrong sample
    k88 and two others  NOT REAL                single-capture flukes; do not
                                               trust an unrepeated single cell

### "Audible" is a weaker claim than the fix predicts

`Bass-Dark` k84 went from 1/9 audible to 5/9 and +72.75 dB — but a key playing
the wrong sample at the wrong pitch is also not dead. The partial ladder
settles it:

    k80 208.01   k81 219.73   k84 260.74   k85 275.39   k86 292.97 ... k91 389.65
    every step +1.00 semitone (two estimator rank-jumps at 82/83 aside)

k84 sits mid-ladder at the right pitch and a level in line with its
neighbours. **That is "correct", not "not dead".** The distinction was
mpc2emu's ask and it was the right one.

Coverage now stops at key 95, and that is **physics rather than a clamp**: the
topmost sample is root 71 at 24 kHz, and +24 semitones is exactly key 95 under
the 96 kHz ceiling measured in §53. The writer's bound and the hardware limit
now coincide.

### A defect this rig cannot see, by construction

The build log records a dropped zone at key 85. **In audio, key 85 is clean —
right pitch, level in line with its neighbours.** The hole-fill covers it with
the neighbouring sample, so it is *wrong sample at the right pitch*, and a
level-and-pitch check passes it. Catching it needs a timbre comparison against
the source.

**This is a permanent limitation of the measurement, not a gap in one run**, and
"k85 clean" must never be quoted as evidence the zone-drop is harmless.

### The wrong sample did not get fixed; it moved

Read out of the keymap objects rather than inferred from the level change:

    MX8V501    entries 47..51  -> keys 59..63   sample 311 (noise)
    MX9MPCKR   entries 58..62  -> keys 70..74   sample 311 (noise)

Same five-entry run, same broken sequence `316, 317, 318, 311, 320, 321`,
sample 319 still the missing member and still unreferenced. **k60 improving by
+28.24 dB and k72 regressing by −27.64 dB are the same defect moving one zone
up with the coverage remap** — not a fix and a regression. Reading the object
is what distinguished those; the levels alone would have supported either
story.

### The mean said +1.33 dB. The median said +0.01. Both were wrong.

mpc2emu predicted the headroom fix (11% → 90% of samples retained at 44.1 kHz)
would show as programs getting louder. It did not: +0.17 dB median across 66
cells, which is this rig's own inter-session offset (§49) and nothing else.
**Retaining sample rate buys bandwidth, not level, and a level grid cannot see
it** — but the grid stores 25 bands per note, so the right measurement was
captured alongside the wrong one and cost no hardware to run.

Per matched cell at v127: `band_v9 − band_v501`, each cell's **median band
delta subtracted** so the level offset is removed by construction, then
tilt = mean(≥5 kHz) − mean(<1 kHz). The set-wide mean came out **+1.33 dB,
t = 2.5** — and it is an artefact: the median over the same 56 cells is
**+0.01 dB**, only 28 of 56 positive. Broken down per program, two appeared to
gain ~7 dB and seven were flat.

**That per-program breakdown was also an artefact, and catching the first one
did not stop me publishing the second.** One more level down:

    LD Retro Powder   k36 +21.86   k48 +0.04   k60 +0.03   k72 +0.02   k84 +13.75
    PD Tapemaker      k36  +1.08   k48 +6.80   k60 +10.77  k72 +9.45   k84  +8.20

`LD Retro Powder` is **+0.02 to +0.04 dB on three of five keys** — its +7.14 is
two outlier keys averaged with three nulls. `PD Tapemaker` is the ~18 dB quiet
program and its raw band deltas at k60 run **−52.9, +33.2, −24.6, +32.1**: not
spectral changes, but third-octave bands close enough to the floor that the
value depends on which noise realisation landed in the window.

Two independent predictions had already failed against the "two gainers" —
mpc2emu's own file-side spectral check said −2 dB for both, and a zone-width
test on the loaded keymaps found **four programs with byte-identical zone
geometry, two "gaining" and two not**, with the single most heavily pitched
program in the bank (one zone, 106 keys) gaining nothing. **Two failed
predictions in a row are usually the measurement.**

For contrast, a real null — `LD Retro Powder` at k60, all 25 bands:

    +0.2 +0.2 +0.2 +0.2 +0.2 +0.2 +0.2 +0.2 +0.2 +0.2 +0.2 +0.2 +0.2
    +0.1 +0.1 +0.1 +0.1 +0.1 +0.0 +0.1 +0.2 +0.4 +0.4 -0.1 -0.0

**Corrected finding: no measurable spectral effect of the headroom fix in this
data**, and the file-side check agrees. A mechanism (playback interpolation)
had been proposed to reconcile +7 against −2; there is no +7 to reconcile.

**The lesson is not "compute a second statistic" — I did that, at one level,
and stopped.** A mean over five keys hides bimodality exactly as well as a
mean over nine programs. **Every level of aggregation needs the same
treatment, and the one you stop at is the one that will be wrong.** This is the
fourth member of the week's family: §51's window artefact, §53's frozen-pitch
plateau, §54's set-wide mean, and now §54's per-program mean — each a number
that is arithmetically correct and is not a measurement of what it is named
after.

### The three odd keys were flukes, and that is the more useful result

`LD Retro Powder` k36 (+21.86) and k84 (+13.75), and `Bass-Dark` k88 (8 dB
low) all looked like single keys misbehaving inside a zone with no file-side
cause. Re-measured with their neighbours, three repeats each, **under the same
CC7=60 attenuation the original pass used** so the comparison was not across a
gain change:

    Bass-Dark        k86 -21.37  k87 -22.28  k88 -21.91  k89 -23.27  k90 -23.91
      original pass: k87 -21.32  k88 -30.22  k89 -23.24

    LD Retro Powder  k35 -35.80  k36 -36.00  k37 -35.90
                     k83 -36.20  k84 -35.93  k85 -35.96

**None of the three reproduce.** k88 reads −21.91 where it read −30.22; the
two `LD Retro Powder` keys sit within 0.2 dB of their neighbours, sd 0.03-0.11
across three repeats.

**The bound this corrects matters more than the keys did.** §49 put this rig's
repeatability at **0.004 dB back-to-back** — but that was a *sustained sine on
one program*. On real multisampled material a single note occasionally
deviates by several dB: k88 was **8 dB** off once and identical to its
neighbours three times running. Typical repeatability is still fine (sd
0.03-0.78 dB across fifteen re-measures); **the excursions are rare and large,
which is the worst combination for a grid that measures each cell once.**

**So a single-cell difference on this material is not a finding until it
repeats.** That retroactively accounts for the +2.70 dB "control move" on
Bass-Dark k72 flagged the previous day — noted then as inside that note's own
spread across six runs, now with a mechanism — and, more importantly, for
`LD Retro Powder`'s +7.14 itself: two outlier keys out of five, **each
measured once**. The retraction above said those outliers were unexplained;
they were flukes, and the whole +7.14 is now accounted for rather than merely
withdrawn.

**Practical consequence for future grids: measure each cell twice and keep
both, or re-measure any cell that stands out before reporting it.** The cost is
one extra pass. The alternative is what happened here — three single cells
consumed an afternoon across two sessions, and two of them reached a peer's
notes as findings before anyone asked whether they repeated.

## 55. The KRZ column, and a bound that is wrong in both directions (2026-09-06)

Three banks — `MX9E4KR` (E4B source), `MX9S3KR` (S3000), `MX9S1KR` (S1000) —
22 programs, **1980 notes with every cell captured twice** on Jan's
instruction. `mxgrid_krzcol.json`.

### Two measurements are a detector, not insurance

The reason for capturing twice was §54's flukes. What the pairs actually show
is more useful than a safety margin. Across 990 paired cells:

    median |r0-r1|  0.011 dB      over 1 dB   6.16 %
    95th pct        1.212 dB      over 2 dB   2.53 %
    max             6.199 dB      over 3 dB   0.91 %

**But it is not spread evenly — it is almost entirely five programs.**

    E4B    (10 programs)   median 0.001-0.010 dB    3 cells over 1 dB of 450
    S1000  (6 programs)    median 0.004-0.014 dB    2 cells over 1 dB of 270
    S3000  (6 programs)    NEWAGE 10/45, SPACE 16/45, VELSTACK 15/45,
                           COSMIC 10/45, CRYSTAL 5/45 (max 6.20 dB)
                           -- and BASIC E.P is clean at 0/45

**Sixteen of twenty-two programs repeat to about a hundredth of a decibel.**
All the instability is in five of six S3000 electric pianos, and the sixth — in
the same bank, same load, same session — is perfectly stable. So it is not the
rig, the bank or the load: **repeat disagreement is a property of the
program.** `CRYSTAL E.P` at key 72 alone supplies five of the ten worst cells
in the grid.

That refines §54 rather than confirming it. The rule is not "measure
everything twice because material is noisy" but **"measure twice to find out
which material is noisy"** — a program agreeing to 0.01 dB needs no repeats;
one scattering by 6 dB cannot be quoted from a single capture at all and wants
more than two.

### One constant, wrong in both directions at once

Every `MX9E4KR` program is one layer over a **single-zone keymap covering keys
12-117** — one sample stretched across 105 keys — with `LoKey 21 / HiKey 79`,
identical on all ten. Key 84 measured silent on all ten and only those (0 of 18
cells each; every S3000 and S1000 program is 18/18 everywhere).

The obvious reading — the bound is too low and the top of the keyboard is being
thrown away — **was wrong, and only a pitch sweep could tell.** Patching
`HiKey` to 127 on `Super Sub 2`:

    k72 131.84   k73 137.70   k74 146.48   k75..k95 all 146.48, -14.8 dBFS

**The pitch stops tracking at 75 and the layer runs to 79.** Extending the
bound gains nothing; keys 75-79 were already sounding at a frozen pitch, at
full level, a semitone and a half flat by k79. **A level check passes every one
of them** — the third appearance this week of the same shape.

mpc2emu then computed the per-sample ceiling key from the file
(`rate x 2^((k-root)/12) <= 96000`) and predicted four programs before they
were measured:

    program          predicted        measured
    Synth Bass 23    tracks to 74     tracks to 74, frozen 75-79     exact
    DX Bass 1        tracks to 79     tracks to 79, no frozen keys   exact
    Moog Bass        tracks past 79   tracks to 79, no frozen keys   exact
    JP4 Bass         tracks to 79     tracks to 77, k78/79 SILENT    no

**So one written constant of 79 is simultaneously too high for six programs
(which sound wrong keys) and too low for one (`Moog Bass`, which would track to
84 and is cut at 79).** The fix is neither raising nor lowering it but
computing it per sample. That is a stronger argument than either failure alone,
and neither failure alone would have produced it.

**`JP4 Bass` is unexplained and fails differently in kind.** Its program,
layer, keymap and zone are identical to `DX Bass 1`'s, and the file gives both
the same rate and root — yet they track identically to k77, to the FFT bin, and
then one continues while the other drops to the noise floor. `Super Sub 2`
*clamps* at the ceiling (frozen pitch, full level); `JP4 Bass` *stops*. If both
are the same limit, **the machine does not respond to it uniformly**, and a fix
derived from one behaviour will not predict the other.

### A detector fault worth recording

The freeze test marked `JP4 Bass` k79 as frozen. It is not — k78 and k79 are
both at the noise floor, so the "identical f0" is the same noise peak read
twice. **A pitch-equality test is meaningless below the floor and must be gated
on level.** It did not mislead here because the levels are unmissable; in a
quieter case it would have manufactured a ceiling that was not there.


## 56. "The audio moved" was a broken MIDI cable (2026-09-06)

A capture that had read −13 dBFS all day started reading the noise floor. A
scan of all twenty physical inputs found the instrument on `capture_15/16`
with a 65 dB note-versus-silence margin, and later on `capture_13/14`, and
then nowhere at all. The rig's capture constant was changed twice to follow
it.

**The audio never moved. It was on `capture_17/18` the whole time.**

`mididings_k2000r`'s `out_1` had been disconnected from the ESI port that
feeds the K2000's MIDI IN. No note reached the instrument, so every capture of
it was silence — and the scan, which asks *where does a note land*, found
whatever else was answering a mis-wired MIDI path. One `aconnect 135:1 64:7`
restored the morning's documented state and the instrument came straight back
at −12.8 dBFS, inside the range the same program measured in that morning's
grid.

**Why the diagnosis went wrong.** SysEx and notes take different routes on
this rig: the bridge talks *directly* to `ESI M4U eX MIDI 8`, while notes go
through `mididings_k2000r`. So the panel stayed fully responsive — programs
selected, pages read, edits applied — while nothing could be played. **Every
check that the instrument was alive passed, because the instrument was
alive.**

**A port scan finds where a NOTE lands, which is the instrument you meant only
if the MIDI path is intact.** Verify the MIDI connection before believing a
scan that appears to move the audio; the scan cannot tell "the audio is
elsewhere" from "the note went elsewhere".

The guard added afterwards, `Rig.prove_audio()`, plays one note and refuses to
run unless the capture hears it 20 dB over the measured floor. It would have
caught this in one note rather than in an hour — but note what it does *not*
do: it says the path is broken, not which half. That is still the right guard,
because refusing to record is the important part.

**Chain of consequences worth counting**, since each step looked reasonable:
a sweep read silence; the silence was attributed to the program under test
(`JP4 Bass`); a control was run and also read silence, correctly moving
suspicion to the rig; a port scan appeared to locate the instrument elsewhere;
the constant was changed to match; the next scan moved it again; and only then
was the MIDI graph inspected. **The control did its job — it stopped a wrong
claim about JP4 Bass — and the scan that followed then produced a second wrong
claim of its own.** A diagnostic tool needs its own precondition as much as a
measurement does.

## 57. The PANNER block, mapped by DUMP-diff (2026-09-06)

§56's pan finding left the question of *where* the panner's fields live. The
peer session proposed setting every field to a distinct value, **saving the
bank** and diffing the files. Saving writes to the K2000's disk, which is one
of Jan's three reserved actions, so it was done over SysEx instead — dump the
object, make the panel edits with the editor still open, dump again, exit
discarding. Same answer, nothing on disk, and the object verified byte-
identical afterwards.

**Subject: program 244 `Proteus 12String`, whose panner fields all read zero**,
so every field moves from 0 to a distinct non-zero value and no byte can stay
put by coincidence. Identity confirmed from its keymap id before anything was
touched.

    field    typed    panel read    offset   signed   scale
    Adjust     37        37%          242       37    1 %/unit
    KeyTrk   -9.0      -9.0%/key      244      -45    0.2 %/key per unit
    VelTrk    115       114%          245       57    2 %/unit
    Depth     -73       -72%          247      -36    2 %/unit
    MinDpt     21        20%          249       10    2 %/unit
    MaxDpt   -137      -136%          250      -68    2 %/unit
    Pad        12        12dB         252        2    6 dB/unit (0/6/12/18)
    ?           -         -           268        2    UNEXPLAINED

**The scales are self-consistent and self-confirming.** Every `±200%` field is
2 %/unit, which is exactly what fits ±200 into a signed byte — and the
quantisation shows in the read-backs: 115, 21, −73 and −137 came back as 114,
20, −72 and −136, every odd value snapping to the nearest even one. `Adjust`
is 1 %/unit over ±100, which independently matches six panel values read in
§56 mapping directly to the same byte as percent.

**Confirmed from the other side.** The peer session aligned these program
offsets against the F3 HOB segment in a real bank and found
`segment index = program offset − 241`, with `seg[0]` the block type and
**PANNER = 40** — which extends the offset-241 block-type table this file
already had (`BAND2 = 35`, `NONE = 60`). Checked against `St. Phantasia`,
whose panel reads `Adjust −32` and whose segment is literally
`[0x52, 40, −32, …]`. **Two independent addressings of the same bytes, one
from the panel and one from the file, agreeing exactly** — which is the check
worth having before writing into a block that had only ever been read.

**Two gaps left open rather than filled in.** Offset **268** also changed,
0 → 2, and cannot be attributed: it is outside the panner block, inside the
F4 AMP region, and nothing on that page was edited. It happens to have taken
the same value as `Pad`. And **`Src1`, `Src2` and `DptCtl` are not located** —
they are enumerations chosen with the wheel rather than typed, so a
digit-entry pass cannot reach them and no source byte appears in the diff.

### The source enumerations, and why spread beat adjacency

`Src1`, `Src2` and `DptCtl` are wheel-selected and unreachable by digit entry,
so they needed a second pass: step the wheel, dump after **every** step, and
read the name the panel reports at each.

    Src1      offset 246
    Src2      offset 251        <-- LFO2 = 116, the auto-pan route
    DptCtl    offset 248
    all three share one encoding (verified on four common values)

**Stepping to well-separated entries rather than adjacent ones is what made
the encoding readable, and it was mpc2emu's design point rather than this
session's.** Positions 1, 8, 24 and 60 gave bytes 127, 7, 23, 91 — and
positions 8 and 24 both look exactly like `byte = position − 1`. **Any three
adjacent points in that stretch would have said "dense index" with complete
confidence.** Position 60 breaking it is the only reason the real scheme
appeared.

**The byte is the K2000's control-source code, and for controller sources it
is the MIDI CC number**: `MWheel` 1, `Breath` 2, `Volume` 7, `Pan` 10,
`Sustain` 64, `FX Depth` 91, with `OFF` 0 and `ON` 127. Internal sources form
a block from 96 up:

    Note St  96   AttVel  100   VTRIG1 106   ASR1 110   LFO1   114
    Key St   97   InvAVel 101   VTRIG2 107   ASR2 111   LFO1ph 115
    KeyNum   98   PPress  102   RandV1 108   FUN1 112   LFO2   116
    BKeyNum  99   BPPress 103   RandV2 109   FUN2 113

A 112-position walk is saved as `lfo2_code.json` with ~70 named sources.

So the bank's two auto-panning programs read completely as
`Src2 = 116 (LFO2)`, `MinDpt 4 %`, `MaxDpt 56 %`, `DptCtl = 1 (MWheel)`,
`Adjust +7 %`, `KeyTrk −1.0 %/key` — a routable description rather than
orphaned depths.

**Offset 268 did not move** in the wheel pass or across 112 source positions.
It changed only in the digit pass, alongside `Pad`. Still unassigned, but now
bounded: it is not a panner source field.

**The experimental design deserves recording, because it is what made the diff
decisive rather than suggestive.** Every value distinct, none zero, none
repeating, both signs represented. Three of the seven bytes landed on 57, −36
and −68 — unremarkable numbers that would have been ambiguous under a tidier
set of inputs, and two fields sharing a value could not have been separated
from the diff at all.

**The control was the load-bearing part.** `Adjust` was already placed at that
offset from panel readings alone; setting it to 37 and requiring the byte to
become 37 tested the anchor before anything else in the diff was believed. A
diff with no control is a list of bytes that changed, not a mapping.

## 58. The PANNER that panned nothing: it is a two-wire block (2026-09-06)

§57 mapped the `F3 POS (PANNER)` block byte by byte, and mpc2emu's converter
then emitted a program using it — 263, algorithm 2, `Src1 = LFO1`, `Depth 52 %`,
LFO1 free-running at 8.70 Hz. Every field read back correctly on the panel and
in RAM. The program produced **no stereo movement at all**: balance sd
0.015 dB, with nothing at 8.70 Hz anywhere in the spectrum, and the control
program 208 (block `NONE`) measured *less* steady at 0.034 dB.

The answer is in the Musician's Guide, p284, and it is not a bug in anything:

> "This single-stage function converts a single wire at its input into a double
> wire at its output, splitting the signal between an 'upper' and 'lower' wire.
> ... **By itself the PANNER doesn't change the pan position of the sound.** It
> just defines what percentage of the currently selected layer's sound goes to
> each wire. ... So when you use the PANNER function, you'll also want to adjust
> the Pan parameters on the OUTPUT page, setting the upper wire's pan fully
> right, and the lower wire's pan fully left."

`PANNER` is **one wire in, two wires out**. It positions nothing. The `OUTPUT`
page's `U` and `L` rows are those two wires, and if both sit at centre — which
is the inherited default — the wires sum and the block is inaudible no matter
how hard it is driven. All of §57's fields were doing exactly what they claim;
their output was being re-summed one stage later.

The manual passage also states independently that `PANNER` exists only in
**algorithms 2, 13, 24 and 26**, matching `_ALG_WITH_PANNER` in the KRZ parser,
which was derived months earlier by a different route.

### The measurements (mpc2emu's, on 263)

    Adjust +50 %, wires centred            0.01 dB     static, still nothing
    Src1 LFO1, Depth 52 %, centred      sd 0.015 dB
    Src2 RandV2, MaxDpt 100 %, MW 127   sd 0.045 dB
    wires SPREAD hard L/R               sd 10.118 dB, peak 8.70 Hz / 13.29 dB

The peak lands on LFO1's own rate. The modulation was present throughout and
never reached the outputs.

**Program 246 (`MXKRSRC`) was the contrast that gave it away**, though not for
the reason it was offered. §57 recorded that the bank's own working panners
drive from `Src2`/`GLFO2` with `MinDpt 4 % / MaxDpt 56 %` rather than
`Src1`/`Depth`, and that was passed across as a hypothesis about the *route*.
The route was never the variable. What actually distinguished 246 is that **its
two wires are panned hard left and hard right on the OUTPUT page** — the one
field neither side had looked at.

### The check that made the null interpretable

Before concluding the block was dead, mpc2emu pushed the panner's own `Pad`
from 0 dB to 18 dB and measured −18.08 dB. `Pad` is a `PANNER` field, so one
edit proved the block was in the audio path *and* that its gain stage worked
while its pan did nothing — which is what narrowed the fault to the output
stage rather than to the block or its source.

The first attempt at that check pressed `Pad` **downward**, where the range
floors at 0, and nothing moved. **A control that cannot move is not evidence
that nothing responds.** That near-miss is the same failure family as §36's
rule about panel edits dying with the editor: an experiment that cannot produce
a signal reads identically to one that produces none.

### For the converter

Emitting a `PANNER` block without also writing the layer's `OUTPUT` wire pans
is a no-op. The fix is two more fields, not a rewiring — filed on the mpc2emu
side as `§K2PANWIRES`.

### The offset map

mpc2emu's RAM dump of 263 read `@241 = 0` with none of `40 / 114 / 26` present,
and they initially concluded the §57 offsets did not index RAM. They do. The
values read by `read_object_bytes` at 241 / 246 / 247 are rendered by the
device's own panel as `(PANNER)` / `Src1:LFO1` / `Depth:52 %` — two independent
routes agreeing on three values, which a RAM-vs-file encoding difference could
not produce. Their dump was the odd one out; the cause was not chased down.
**When two maps disagree, the one that agrees with the device's own decode
wins.**

### The pattern this makes five of

s3ked's observation from earlier today — a route wired with something on it left
at zero — now has five instances across three machines and three writers:
`MODVPAN1` zero with the source wired, `MODVFILT3` against `SUSTN2` zero, an
envelope depth multiplied by zero sustain, and now two output wires summing at
centre. The common shape is a converter carrying sources and primary depths
across while leaving the destination block's secondary fields at whatever they
happened to hold. That argues for auditing every writer for unset secondary
fields rather than patching the four sites separately.

## 59. Parameter values can be typed on the numeric pad (2026-09-06)

Panel automation in this project has driven values with `alpha_wheel()` clicks
throughout. It did not have to. Jan pointed out that the alphanumeric pad enters
**values**, not just names and program numbers — manual 3-4, "The Alphanumeric
Pad" — and `Button.Number0..Number9` (0x00-0x09), `PlusMinus` (0x0A), `Cancel`
(0x0B), `Clear` (0x0C) and `Enter` (0x0D) have been in the enum the whole time.

Typing is deterministic: no click counting, no accumulated drift, no read-back
to discover where the wheel landed. It also needs no `patch_object_bytes`, so it
is the route that still works when a byte-level object write is unavailable.

**The trap is the decimal point.** Digits fill from the rightmost decimal place,
so the field's displayed precision is a multiplier:

    Adjust:0%          integer      32 %    = 3, 2, ENTER
    KeyTrk: 0.0%/key   1 decimal    5.0     = 5, 0, ENTER
    LFO1 MnRate 8.70H  2 decimals   2.00 Hz = 2, 0, 0, ENTER

Typing `2` into that rate field gives **0.02 Hz** — a 50-second period, which
across any plausible recording window is indistinguishable from a panner that
does not move. A decimal-scale slip can therefore manufacture exactly the null
result you are investigating.

So: read the field's decimal places off the screen *before* typing, and read the
value back *after* `ENTER`. The value does not commit until `ENTER`, and an
un-committed entry looks identical on screen to a committed one — which is why
the read-back must come after. `CANCEL` before `ENTER` restores the original
value, giving a free abort.

A typed value is still a panel edit and remains subject to §36: live only
while the editor is open, and discarded when the exit prompt is answered `No`.

Demonstrated accidentally on this rig before it was known: `select_program`
typing digits while the Program Editor happened to be open edited the parameter
under the cursor instead of selecting a program — fixed by asserting Program
Mode before typing, which is now also the reason the helper is safe to reuse.

## 60. The algorithm/DSP-function table, and codes that are not global (2026-09-07)

mpc2emu asked for the comprehensive algorithm/function lookup table (their
`§K2ALGWALK`), framed as a panel walk: step every algorithm, read the block
chain off the ALG page. Most of it did not need the device at all.

### The table was already in print

The Musician's Guide does not contain it — it *points* at it: "the Reference
Guide contains a list of all 31 algorithms and the DSP functions available for
each one". The Reference Guide is on disk as the numbered chapter PDFs beside
the Musician's Guide, and chapter 26 is `26 DSP Algs.pdf`. `pdftotext -layout`
renders the block chains and the per-block function lists cleanly; only the
line-and-arrow glyphs come out as an unmapped symbol font.

Parsed to `~/temp/k2k_algs/k2000_algorithms.json` and `K2000_ALGORITHMS.md` by
`parse_algs.py`. Five minutes, no hardware. Two structural facts a converter
needs, both from the manual rather than from measurement:

- **Algorithms 26-31 have no PITCH stage.** Four stages, not five.
- **A block can span several stage slots** — algorithm 1's HIFREQ STIMULATOR
  occupies three of the five. So "which block is in F3" is not the same question
  as "which stage is third".

One parser bug worth recording because it is invisible in the output: keying the
function lists by block *name* silently merged the two blocks of algorithms 8-15,
which are both called `LOPASS`. Keyed by position instead.

### What print does not give: the codes

The Reference Guide names functions; the converter needs bytes. That is the part
worth device time, and an accident made it cheap.

**Typing a number into a block field on the ALG page selects the function by its
code.** Found by fat-fingering a program number while the cursor sat on a block
and watching `SINE` become `LOPASS`, with the display showing `1...` mid-entry.
That is also a warning for anyone driving this machine: stray numeric entry
edits whatever the cursor is on, and the ALG page's cursor does not start on the
Algorithm parameter.

Two more facts make the reading trustworthy:

- **A dump taken with the Program Editor open reflects the edit buffer.** Offset
  241 tracked every typed change. This is what allows (typed code, panel name,
  stored byte) to be captured as a triple rather than assumed to line up.
- `get_current_parameter_name()` returns `Algorithm:` on the algorithm parameter
  and empty on a block field, which gives a self-identifying anchor to navigate
  from. Ring, rightwards: `block1 -> ... -> Algorithm -> PITCH -> block1`.

### The block type offsets

    F1 = 209    F2 = 225    F3 = 241    F4 = 257

All four measured by DUMP-diff. The 32-byte spacing was deliberately not assumed
after the first two were known: assuming it would have put two blocks' worth of
codes at wrong offsets with every value still looking like a legal function.

The offset search has a property that came out of the failure mode rather than
despite it. Since an accepted code stores its own value, the offset is the
position holding the typed value for several different probes — and **a refused
probe fails to vote rather than voting wrongly.**

### The codes are per block, not global

This is the load-bearing result, and it is the opposite of what was reported to
mpc2emu first.

    NONE          60 in the LOPASS-family blocks and alg 5 F3
                  61 in alg 5 F1, alg 2 F1, alg 16/17/18 F2
                  62 in alg 1 F1
                  63 in alg 21 F2
    PARA BASS      8 in alg 2/5 F1   but  10 in alg 16 F2
    PARA TREBLE    9 in alg 2/5 F1   but  11 in alg 16 F2

A byte means something only together with the block it sits in. Full table in
`~/temp/k2k_algs/K2000_FUNCTION_CODES.md` and `function_codes_by_block.json`,
60 functions, every name in the printed table covered.

The double-output algorithms carry a surprise for anyone indexing blocks: on
algorithm 3 the last two stages are **one cursor field offering a pair**,
reading `AMP U   AMP L` (byte 38) or `BAL     AMP` (byte 39). There is no third
block to select.

### Four ways this went wrong, all the same way

Every one produced a confident, in-range, legal-looking answer.

**A refused code returns another legal function of that block.** Not an error,
not a null — a real function name, promptly, from a live device, changed from
the previous reading and causally downstream of the key pressed. The usual
defence against a bad read is to check the thing you poked responded at all, and
here it did.

**A sentinel wiped by the same fallback.** The first refusal detector set the
field to a known value before each probe and asked whether the probe left it
standing. The fallback overwrote the sentinel too, so the detector reported "0
refused" for a block that refused most of the range.

**A terminator that was not one.** The first sweep stopped at 70 because NONE
sat at 60 and that felt like an end. `LP2RES` and `SHAPE2` were at 73 and 74 —
eight codes past where the search stopped. A sentinel value that reads like a
terminator is not a terminator.

**A correct observation retracted because it did not fit.** NONE reading 61 in
algorithm 5's F1 was reported, then withdrawn as a refusal artefact, because a
global enumeration had already been committed to. The stored byte says 61. The
retraction was made in the same message that warned a peer against naming a
fallback after what they expected.

The rule that survives all four, and it is stronger than the "show the detector
can produce a non-null" form:

> **A measurement is not evidence until the apparatus has been shown able to
> produce a reading that CONTRADICTS the one you got.**

Liveness is the weak form; distinguishability is the strong one. Practically:
ask what reading would have appeared if the hypothesis were false, then check
the apparatus can produce it. If it cannot, you have built an instrument that
only says yes. What rescued this walk was not proving the panel responds — it
was reading the stored byte, a second channel that *could* disagree with the
panel, and did, on the first block.

### Two rig faults, both of which hid a failure rather than caused one

**A script whose `main()` runs at import drove the panel every time it was
imported.** Two helper modules were written without an `if __name__` guard, so
importing them from the next script silently ran a full hardware pass first.

**A waiting loop that polled `pgrep -f blockwalk.py` matched its own command
line** and therefore never noticed the child had died. A walk crashed at 23:56
and was reported as "progressing" for 35 minutes. Compounding it, the progress
check grepped the log for success patterns only, so the traceback was filtered
out of view. Check a background job by pid, and grep for failure as well as
progress.

## 61. The LFO1 rate ladder, and a law that was right in one segment (2026-09-07)

mpc2emu's KRZ writer converted an LFO rate to a byte with one undocumented
line, `byte = 26 + 10*Hz`, no anchors cited and no calibration record. Two
programs measured on the panner work disagreed with it unevenly — exact on one,
11.5 % out on the other — which is the signature of a fitted line, not a scale
error. Swept properly, the machine turns out to be piecewise.

### The table

`LFO1 MnRate` is at Program-object offset **91**. 185 rows, one per byte,
read off the panel, no interpolation:

    byte   0..20    0.01 Hz/byte      0.00 ..  0.20 Hz
    byte  20..36    0.05 Hz/byte      0.20 ..  1.00 Hz
    byte  36..126   0.10 Hz/byte      1.00 .. 10.00 Hz
    byte 126..176   0.20 Hz/byte     10.00 .. 20.00 Hz
    byte 176..184   0.50 Hz/byte     20.00 .. 24.00 Hz

**Byte 184 is the ceiling** — the wheel will not move past it. The reachable
range is 0-184, not 0-255.

In the third segment `byte = 36 + (Hz - 1.00)/0.10`, which reduces to
`26 + 10*Hz`. **The old law was correct, for 1 to 10 Hz.** Both programs that
raised the question sit either side of the 10 Hz boundary: 8.70 Hz converts
exactly, and 11.50 Hz gets byte 141, which really is 13.00 Hz.

Full map at `~/temp/k2k_algs/lfo1_rate_table.json`.

### Audio cross-check

Four bytes across three segments, two reps each, panel value asserted before
each capture:

    byte  76   panel  5.00 Hz   audio  5.00   delta 0.00
    byte 126   panel 10.00 Hz   audio 10.00   delta 0.00
    byte 156   panel 16.00 Hz   audio 16.11   delta 0.11
    byte 180   panel 22.00 Hz   audio 22.22   delta 0.22

The residuals are **FFT quantisation, not error**: a 1.8 s window at 10 ms
frames gives 0.556 Hz bins, and 16.11 is bin 29 exactly — the nearest bin to
16.00 *is* 16.11. The panel is the instrument here and the audio is the check
that it is not lying; neither confirms the other's third decimal.

### The mistake that nearly produced a table

The first sweep ran 260 steps in which the panel climbed 0 to 24 Hz **while
the byte being read never left 49**. Offset 32 is `GLFO2`'s MnRate, not
LFO1's. The discovery run had searched for a field whose parameter name
contained `MnRate`, but the LFO page's fields return an **empty** parameter
name — so nothing ever matched, every iteration pressed `CursorRight`, and the
cursor walked onto GLFO2 before anything was typed. The resulting diff was a
real byte for the wrong field, and it fit `26 + 10*Hz` beautifully, which is
exactly what made it convincing.

What caught it was the data, not foresight: **a byte that does not move while
its value does is not that value's byte.** The sweep now types a known value
at startup and requires the `LFO1` *screen row* to change before it will sweep
anything — verifying the subject against the display, since the page does not
provide a name to verify against.

Two device facts fell out of it:

- **SysEx writes are refused while the Program Editor is open** —
  `DNAK ObjectCurrentlyBeingEdited` — although reads still reflect the edit
  buffer (§60). So during an edit a byte can be read but not written from
  outside, which is why this had to be driven by the alpha wheel.
- `MxRate` stayed `0.00H` and `RateCt` `OFF` across all 185 rows and the
  reported rate tracked `MnRate` alone. Consistent with "MnRate is the rate
  when RateCt is OFF", but untested with RateCt on: unobserved, not excluded.

### Why it matters beyond one program

Above 10 Hz the old law spends one byte per 0.1 Hz where the machine spends one
per 0.2, so the excess over 10 lands roughly doubled — a 15 Hz source arrives
at 20 Hz. Above 21.4 Hz it silently clamps at the 24.00 ceiling. Below 1 Hz it
fails worse in relative terms: 0.10 Hz becomes byte 27, which is 0.55 Hz, five
and a half times too fast. **Slow LFOs are the proportionally worst affected**,
and they are the ones a listener notices.

## 62. Two decoders that were signed, and a review that caught one (2026-09-07)

A code review flagged `k2kfields._amp_veltrk_db` as decoding a signed field as
unsigned, citing the manual's F4 AMP parameter table (`VELOCITY TRACKING
+-96 dB`). It was right, and the device says so directly. Typing values on the
numeric pad and reading the byte back:

    F4 AMP VelTrk, offset 261        F3 POS Adjust, offset 242
      +36 dB -> byte  36               +37 % -> byte  37
      +96 dB -> byte  96              +100 % -> byte 100
      -32 dB -> byte 224               -32 % -> byte 224
      -96 dB -> byte 160              -100 % -> byte 156

Both are **two's complement**. `VelTrk` runs +-96 dB, `Adjust` +-100 % — and
Adjust clamps: typing 127 leaves the field at 100, so bytes 101-155 are
unreachable from the panel. Both decoders now return `None` outside their
proven range instead of a plausible figure.

The original `_amp_veltrk_db` returned `raw[0]`, so a program with
`VelTrk:-32dB` would have been rendered as **"224 dB"** — a value the parameter
cannot hold, printed with no hedge, in a module whose entire stated contract is
to say "unmapped" rather than guess.

Three things are worth separating out about how it got there.

**The measurements were all positive.** §47's four objects carried 0, 5, 15 and
36. Every one confirmed the law and none of them could have exposed the sign,
because the sign only shows up in the half of the range that was never
sampled. The docstring then claimed the field "needs no proven-range hedge" —
a claim about the whole range from evidence covering half of it.

**The file contradicted itself.** `_panner_adjust_pct`, five lines below,
two's-complements its byte on the same class of evidence. Two decoders written
in the same sitting disagreed about whether K2000 parameters are signed, and
neither docstring mentioned the other.

**The manual had the answer the whole time.** The F4 AMP parameter table gives
the range explicitly. This is the third time in two days that a page of the
Musician's Guide has settled something that was being established the
expensive way — see §58 and §60.

`normalise_param_label()` moved to `midi_bridge` in the same pass: the padded
label fix from §35 had been applied to the probe but not to `macro_save`'s copy
of the same parse, so the two had silently diverged with only one of them
tested.

## 63. Measuring the K2000 column of the conversion matrix (2026-09-07)

Four routes re-captured for mpc2emu's matrix rebuild — `E4_to_KRZ` (10),
`MPC_to_KRZ` (11, never scored before), `S3_to_KRZ` (6) and `S1_to_KRZ` (6) —
through the shared three-machine harness at `~/temp/matrix/measure.py`.
**131 of 132 notes sounded.** Five bank loads, each preceded by a verified RAM
clear.

### Device facts worth keeping

**The factory source bank uses a deliberate two-level output scheme.** All
twelve MXKRSRC programs, panel-read:

    organs (6)                OUTPUT Gain  0 dB    F4 AMP Adjust  -4..-7 dB
    12-string/Phantasia (6)   OUTPUT Gain 12 dB    F4 AMP Adjust  -2..+6 dB

No overlap in either field, and 12 dB is one of the K2000's discrete gain steps
rather than a tuned value. This settled an open question on mpc2emu's side —
their converter wrote those six patches ~30 dB *down*, and the source boosts
them ~22 dB *up*, so nothing was being carried across faithfully. Their reader
takes zone volume from the sample's own `volumeAdjust` and **never reads the
program-scope `OUTPUT Gain` or `AMP Adjust` at all**.

**A clean split in the data is not a cause.** Both sides read that as an
organ-versus-12-string split, because the twelve programs sort exactly that way
in the source *and* in the output — a 6/6 partition with no overlap in two
independent fields. The real variable is whether a preset has velocity layers;
in this bank the two partitions coincide. Twelve programs cannot separate them.
Only mpc2emu's build log could, because it names the mechanism as it fires.

**§52's drum-program rule is about the K2000's own layer count.**
`Trap-Kit-Purple` reads `Layer:1/3` — three layers, not more than three — so it
sounds on any channel, and it did, on the harness's channel 9 with Master
`DrumChan` at 8. Predicting a drum-channel null for it was wrong. Its actual
null at note 55 is the key map: layer 1 is `LoKey C 2 / HiKey C#3`, i.e. 36-49.
That patch now has **three plausible mechanisms that all present as silence** —
drum channel, key range, and a dead conversion — and only one of them fired.

### The contamination flag fails on quiet material

`measure.py` flags a note when its pre-roll sits within 40 dB of that note's
peak. `PD Tapemaker` demonstrated both failure modes an hour apart, same
program, same notes, only the note gap changed:

    gap 3.0 s   pre-roll -66.5 dB   flagged   TRUE POSITIVE, real bleed
    gap 8.0 s   pre-roll -93.6 dB   flagged   FALSE POSITIVE, bleed gone

27.1 dB of bleed removed and the flag never moved, because that program's whole
dynamic range is **40.2 dB** — peak -51.0 against a -91.2 floor. A 40 dB
peak-relative test has nowhere for a clean pre-roll to sit. It cannot pass at
any gap. The test's premise fails on quiet material, and a floor-relative
measure belongs in the post-pass where it applies to files already written.

### The sidecar was wrong three times, each time plausibly

`measure.py` averages stereo to mono before computing features, so per-channel
peaks and floor occupancy needed a companion pass over the WAVs it writes
(`chan_sidecar.py`). It produced confident wrong numbers three times:

1. **Floor from the file's first 200 ms** — caught a transient in the head and
   reported a -53.7 dB floor for a program whose own pre-rolls measure -81 to
   -94 dB.
2. **Note onsets reconstructed from the nominal PRE/HOLD/GAP constants** — the
   harness records each note's real `time.time()` and its sleeps overshoot, so
   by the fourth note the "pre-roll" window had walked inside the note and the
   floor read -38.8 dB.
3. **The gap hardcoded at 3.0** — on an 8 s re-take every window walked five
   seconds further out of place per note and landed in the silence *between*
   notes, reporting "min above floor" around 14 dB for programs 63-83 dB clear.

Every one of the three **manufactured the floor-limited reading the file exists
to detect**, and two of them reached a peer before being caught. The fix that
holds: the floor uses **no timing at all** (quietest 5 % of 250 ms windows
across the file) and is cross-checked against the harness's independently
computed `preroll_db` — agreement is printed per program and runs 0.3-1.7 dB.
Peaks take the gap from the features file rather than a default, and the
`silent` flag is carried across from `measure.py` rather than re-derived,
because a raw sample peak and a smoothed envelope peak disagree by ~14 dB on a
silent window.

### Two process-check bugs, opposite symptoms

A waiting loop polling `pgrep -f blockwalk.py` matched **its own command line**
and reported a job that had crashed 35 minutes earlier as still running (§61).
The matrix harness's new concurrency guard matched **its own `timeout`
wrapper** — whose argv contains the script name — and refused to start a run
with no conflict present.

Same bug, opposite symptoms: one claimed health that was absent, the other a
conflict that was absent. Neither is legible as a process-detection failure at
the point of impact. Check a background job **by pid**, and exclude your own
ancestors.

## 64. Run-to-run variance, a displaced capture, and the OUTPUT Gain enum (2026-09-07)

All four matrix routes captured a second time, hours apart, each behind a
verified RAM clear and bank reload. The diff is the first measurement of
run-to-run variance this rig has ever had.

### The rig's noise floor

    route   n    mean |d|   p95      max     what sits above the floor
    E4     40    0.033 dB*  0.04*    0.26*   * excluding note 55, see below
    MPC    43    0.095 dB   0.47     1.43    one note, bleed the 8 s gap removed
    S3     24    0.254 dB   1.50     2.04    five of six electric pianos
    S1     24    0.049 dB   0.05     0.84    one note on P-BASS SLAP

**~50 note-pairs at or under 0.05 dB.** Nothing benign in 131 pairs exceeded
0.3 dB, so 0.05 dB is the floor and 0.3 dB is the threshold above which a
difference means something. Three distinct phenomena sit above it, each with
an identified cause — which is a decomposition rather than a variance
estimate, and lets each row be read on its own terms.

**S3 reproduced §55's five-of-six electric-piano instability by a completely
different route**, months later, with `BASIC E.P` clean again at 0.024 dB.
Nothing about this method was chosen to look for it.

### One capture run was displaced by a whole program

On the E4 route, note 55 differed between runs by up to 6.3 dB while notes
36/43/48 in the same files agreed to 0.03 dB. Spectrally, **run 1's program N
was identical (cosine 1.000) to run 2's program N-1** — a one-program offset,
interior programs only.

Resolved by replaying the route with the note order reversed
(`--notes 55,36,43,48`):

- note 55 played **first** still matched run 1 at 1.000 for all ten programs
- note 48 played **last** matched run 1 at 1.000 for all ten

**So it is neither the note nor the slot: one capture run is simply wrong.**
Run 1 and the reordered run agree; the 8 s-gap run has its note-55 audio
displaced. The instrument is exonerated — it played the same sound with the
note in two different sequence positions.

**A correction to the measurement that found it.** The displacement was first
reported using zero-lag correlation, at 0.9982. That measure is worthless on
periodic audio: applied to note 48 — which reproduces to 0.03 dB — it returns
-0.19, -0.66, +0.58, +0.96 for four programs, because a few milliseconds of
window drift flips its sign. The control was sitting in the same files.
**Establish a similarity measure on something known to be identical before
using it as evidence that two things differ.** Redone lag-tolerantly and
spectrally the finding got stronger, not weaker.

### OUTPUT Gain: a descending 6 dB enum

    U wire gain -> Program offset 270      L wire gain -> Program offset 254

    byte = 5 - dB/6      steps 0, 6, 12, 18, 24, 30 dB      byte 5..0

The byte counts **down** as gain goes up, and 0 dB is the maximum byte value.
A converter writing dB straight in, or treating 0 as "no gain", gets the
loudest setting for the quietest request. Typing 36 clamps to 30.

Measured by sweeping each wire through all six steps with the other held
constant, on MXKRSRC program 200, restored byte-identical after every run —
edit-buffer only, discarded with `No`, the RAM object never modified.

The factory bank then decodes with no assumption: organs `5,5` = 0 dB/0 dB,
the 12-string family `3,3` = 12 dB/12 dB. With `F4 AMP Adjust` (-4..-7 dB on
organs, -2..+6 on 12-strings) that is ~22 dB of deliberate family separation
in the source, on two program-scope fields a converter had never read.

### Watching one of two candidate offsets

The Gain sweep initially showed a flat byte: U Gain moved through all six
values and offset 254 never budged. Three mechanisms were written and tested
to explain it — the edit buffer flushes on `ENTER`, no, on cursor-leave, no,
the object dump lags the panel by seconds — and each was refuted. "The dump
lags a panel edit" was minutes from being reported as a finding.

**The byte was flat because U Gain lives at 270.** One wire was being edited
and the other watched. Nothing lagged; every hypothesis was an explanation for
an artefact of reading the wrong offset. Printing **both** candidates on each
step resolved it at once: the one that moves identifies itself, and the one
that does not is the control.

This is the same failure as §61's LFO sweep — 260 steps of a moving panel
against a motionless byte that belonged to a different LFO — hit again the
same day, with the first instance already written up in this file. **A lesson
in the notes is not a check in the procedure.** The check is: when a field
does not respond, confirm you are reading the field you are writing before
theorising about why; and with two candidate offsets, watch both.

## 65. Four refuted mechanisms, and two more mapped offsets (2026-09-07)

The matrix work continued across three card crossings (MATRIX13/14/15). What
is worth keeping is mostly the negative results.

### Two more Program offsets

    OUTPUT Gain, upper wire   offset 270   byte = 5 - dB/6, six steps 0..30 dB
    OUTPUT Gain, lower wire   offset 254   (descending: 0 dB is byte 5)
    AMPENV Rel1 level         offset 138   the percentage directly, 33 -> 33

**A RAM object write outside the editor survives a program change**, where a
panel edit does not — the editor's buffer is discarded when the harness sends
its next program change. So an edit that has to survive an automated capture
must go through `patch_object_bytes` with the editor closed, not through the
panel. `DNAK ObjectCurrentlyBeingEdited` is returned if the editor is open, so
the two are mutually exclusive and the ordering is forced.

### A wire asymmetry that was real and inaudible

One build shipped every program with mismatched wire gains — upper 6 dB, lower
12 dB. Isolated against the fixed build with nothing else changing:

    n=24 notes   median -0.034 dB   mean +0.003 dB
    BASIC E.P (the one reliably reproducing program)   max |d| 0.049 dB

Zero. **The two wires do not sum for this material** — only one carries
signal. Still worth fixing: an inaudible wrong value becomes audible the
moment a program uses both wires, which is exactly what a PANNER does.

The defect had survived every check on the converter side because **its reader
reads only one of the two fields its writer writes**, so the round trip was
perfectly self-consistent while the machine had one wire 6 dB louder. **A field
written in two places and read in one cannot be caught by a round trip.** It
needed an instrument outside the loop.

### The note-swap: four mechanisms, all refuted

§64's displaced capture attracted four explanations and every one failed:

    recording overran into the next program   refuted by file length: 43.75 s
                                              against 43.85 predicted for ONE
                                              cycle at that gap
    the gap override reached one thing        refuted by two other routes
      and not another                         through the identical override
                                              with exactly four events
    a non-terminating amplitude envelope      refuted twice, and the premise
                                              was wrong -- the panel shows
                                              Rel1 33% then Rel2 0%
    the harness sent extra note-ons           refuted by the same script at the
                                              same gap on a different bank
                                              producing a clean capture

**The condition, as far as it is established: the old bank AND the long gap,
neither alone.** At the short gap the extra event would fall 2.45 s before the
next commanded note, in silence and detectable, and it is not there — so the
gap is part of the condition, not merely what reveals it. Left unexplained
rather than given a fifth story; it is a property of a superseded build and
the current one has three independent clean captures, including one through
the suspect path.

**`Rel3: User` on the AMPENV page is not distinctive.** The Musician's Guide
says of ENV2/ENV3 that "the only differences are that you can program an
amount for Rel3" — so the amp envelope's Rel3 level is not programmable and
reads `User` on every K2000 program. It was briefly treated as a converter
signature.

### An onset guard shorter than the note

A spurious-event check counted onsets with a 1.5 s guard against a 2.0 s hold,
so a single note could register twice and a clean four-note capture reported
eight events. **The check written to catch spurious events contained the
artefact it was built to detect.** Guard must exceed `HOLD`.

The same artefact had been flagged in a manual count hours earlier and the
lesson was not carried into the code it was about — the second instance in two
days of §64's rule that a lesson in the notes is not a check in the procedure.

### Card handling

A card crossing left the K2000 on **"Problem mounting disk"**, and once that
dialog is dismissed the Disk page looks normal apart from reading `Not found`
where the volume name belongs. Cycling `CurrentDisk` away and back forces a
remount. Anything that assumed the card was present would have loaded nothing
and blamed the bank.

## 66. The firmware settles the function codes — and corrects §60 (2026-09-14)

Jan supplied the K2000 v3.87J OS ROMs (two 512 KB EPROM images, `High`/`Low`).
They interleave as the even/odd bytes of the 68000's 16-bit bus into a 1 MB
image with a valid reset vector — SSP `0x00020000`, PC `0x00000012` — and
internal pointers read `0x0018xxxx` for file offsets `0x08xxxx`, so **the ROM
is mapped at address 0x100000**. That constant is needed for every address in
this section; working copy at `~/temp/k2k_fw/k2000_v387j.bin`.

### The dispatch that decides a DSP function name

At address `0x1177A4`:

    movew  sp@(8),d0                      ; the function code
    cmpiw  #127,d0
    bhiw   reject
    moveal #157,a0
    moveq  #67,d1
    loop:  addql #1,a0
           cmpb  pc@(0x1177be,a0:l),d0     ; -> the table at 0x11785C
           dbls  d1,loop
    bnew   reject                          ; exact match required
    addl   d1,d1
    movew  pc@(0x1177d4,d1:l),d1
    jmp    pc@(0x1177d4,d1:w)              ; handler: movel #<name ptr>,(a1)

`0x11785C` is an ascending list of the 67 valid codes, terminated `0x7F`. The
loop exits on the first entry `>= d0` and requires equality, so **every code
not in that list is rejected** — which is exactly the refusal behaviour §60
measured from the panel.

**The jump table is indexed by `d1`, which counts DOWN**, so it runs in reverse
order relative to the code list. Matching it forwards produces nothing, which
is what defeated the first attempt.

Decoded, the map agrees with **all 65 codes measured on the instrument, with
zero disagreements**, and adds the two the panel walk never reached. Full table
at `~/temp/k2k_algs/rom_function_codes.json`.

### §60's "the codes are not a global enumeration" was wrong

That claim was drawn from `NONE` reading 60, 61, 62 and 63 in different blocks
and `PARA BASS` reading 8 in one and 10 in another. The measurements were
right; the explanation was not.

**The byte-to-name map IS global and unambiguous. Several names simply have
more than one code:**

    NONE        0, 60, 61, 62, 63     five distinct codes, one displayed name
    PARA BASS   8, 10
    PARA TREBLE 9, 11
    LOPAS2      37, 69

Different blocks offer different members of those sets, which is what made it
look per-block. So **a reader can decode any byte with one table** — the thing
§60 said was impossible. It is the *writer* that has a choice to make, and
`NONE` in particular has five ways to say the same thing.

Codes 0 and 69 (`NONE` and `LOPAS2`) exist and were never reachable in any
block walked from the panel.

### What the ROM would not give up

The LFO rate ladder and the OUTPUT gain enum (§61, §65) are **not** stored as
constant tables — no arrangement of their breakpoints or steps appears in the
image. They are computed, so confirming those laws still needs either the
measured ladder or a reading of the formatting code.

## 67. The envelopes, and what the manual settled that the ROM would not (2026-09-14)

### The ROM gives the page, not the law

The AMPENV field records sit at file `0x096352` — seven 18-byte entries,
`Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3 Loop`, each holding the label, a screen
column stepping by 5, and a width. They are **display descriptors, not
parameter laws**. One useful detail falls out: every record has width 4 except
`Rel3`, which has 5, because that field renders `User` rather than a
percentage — which is why the amp envelope's Rel3 level is not programmable
(the Musician's Guide says of ENV2/ENV3 that "the only differences are that you
can program an amount for Rel3").

Like the LFO rate ladder (§61) and the OUTPUT gain enum (§65), the envelope
behaviour is computed rather than tabled. **Three laws sought in the image,
three not there.** Worth recording as a bound on what ROM archaeology gets you
here: the firmware yields enumerations and layouts readily and continuous laws
not at all.

### The amp-envelope Loop field, and a refuted mechanism

Manual, AMPENV: seven loop types — `Off`, `seg1F/seg2F/seg3F` forward,
`seg1B/seg2B/seg3B` bidirectional — with a count of `Inf` or 1 to 31. And:

> "Regardless of the loop type and the number of loops, each note goes into its
> release section as soon as its Note State goes off."

**So an amplitude-envelope loop cannot produce anything after Note Off.** That
refutes the leading candidate for mpc2emu's §K2000 envelope re-cycle bug as an
explanation for the re-articulation measured in §64/§65 — which began about
**1.15 s after note-off**. Refuted twice over, since the affected programs read
`Loop: Off` on the panel anyway, the `Inf` beside it being the count that `Off`
makes irrelevant.

### Five function codes settled from the manual

Asked for a panel pass on five codes whose meaning a converter needed. The
instrument has been silent since the 2026-09-11 reboot, so the panel was not
available — the Musician's Guide answered all five, and from a documented
source rather than an inference:

    35 BAND2    two-pole bandpass, width FIXED at 2.2 octaves; otherwise
                identical to BANDPASS FILTER
    36 NOTCH2   two-pole notch, width fixed at 2.2 octaves, same relation to
                NOTCH FILTER
    52 HIPAS2   two-pole highpass; HIPASS attenuates low frequencies more at
                the same cutoff
    70 LPCLIP   one-pole, "programmed just like LOPASS"; the input is
                multiplied by 4 before the filter, which is what clips
    57 LPGATE   lowpass whose "cutoff frequency is controlled by the AMPENV" --
                high at 100 %, low as the envelope decays or releases

All five take a real frequency parameter. The two that would have been easiest
to get wrong are LPCLIP and LPGATE, and both are filters for reasons that are
not the naming symmetry that suggests it.

### An entropy pre-flight for firmware work

eosed established that the E4XT OS images are compressed end to end, with the
decompressor in the sampler's boot ROM rather than the file — and a
disassembler pointed at that produces **plausible garbage rather than an
error**. Their check, run here for contrast:

    K2000 ROM   mean 5.00 bits/byte   98.7 % of 256-byte windows below 6.0
    EOS  image  mean 7.19             1.6 %

A test that fires one way is a detector; one that separates both ways is a
discriminator, and the pair is what makes either number mean anything.

**But the ordering matters: entropy first because it is cheap, and behavioural
agreement because it is the only conclusive check.** Entropy would have saved
the attempt had it failed; it could not have shown the attempt had succeeded.
What did that was §66's table reproducing 65 hardware measurements taken by a
different method over several days.

**The failure mode of all of this work is a plausible wrong answer, not an
error** — packed data disassembles, a later ISA decodes instructions the CPU
does not have, and a reverse-indexed table decoded forwards yields a complete
and entirely wrong map with nothing internal to contradict it.

## 68. The re-cycle overhead is per cycle, not per stage (2026-09-14)

The instrument came back (empty, ROM only) and the queued test ran. Seven
captures on ROM program 199, amp envelope switched to `User` and set to
`Att1 0s/100% · Att2 0s/100% · Att3 0.06s/0% · Dec1 0s/0% · Rel1-3 0s/0%`,
**identical in every capture** — only the `Loop` field differed. A 6 s held
note each, onsets by rising edge.

    Loop     onsets   period     sd
    Off           1   --         --      (control: no re-cycle)
    seg1F        61   0.0998 s   0.0013
    seg2F        61   0.0998 s   0.0020
    seg3F         1   --         --
    seg1B        25   0.2400 s   0.0029
    seg1B        25   0.2400 s   0.0025
    seg1B        25   0.2400 s   0.0000

### Per-stage traversal is refuted

`seg1F` loops back to attack segment 1 and `seg2F` to segment 2, so they
traverse a different number of stages per cycle. **Their periods are identical
to four decimal places.** The hypothesis under test predicted about 6.95 ms per
stage; the measured difference is 0.0000 s.

**Nor is it simply a timer**, because `seg1B` is not flat against the forward
settings — 0.2400 s against 0.0998 s. A bidirectional loop traverses the
envelope out and back, so the cycle is longer *because the path is longer*.

So: **the overhead is per cycle, and the cycle's length follows the envelope
path traversed, not the number of segment boundaries crossed.** Forward
overhead here is 0.0998 - 0.06 = **39.8 ms**, and against the original
subject's true `Att3` of 0.058 s it is 41.8 ms, which is the recorded 41.7 ms.

### Two incidental findings

**`seg3F` does not re-cycle audibly at all** on this envelope, and that is
correct rather than surprising: it loops to the start of attack segment 3,
which runs from 0 % to 0 %. Looping over a stage that never rises produces
nothing to hear. **A loop setting can be active and silent**, which is worth
knowing before anyone reads a null as "looping is off".

**The last three rows are the same setting captured three times** — the wheel
stopped advancing at `seg1B`, so `seg2B` and `seg3B` were not reached. The
repeat was accidental and is the run's best number: **0.2400 s three times**,
sd 0.0029 / 0.0025 / 0.0000.

### Two rig faults worth recording

A run killed mid-capture **left a note sounding**, and the next run measured a
floor of **-30.3 dBFS** and carried on. Every level in that capture would have
been referenced to a ringing note. `measure_floor()` now refuses anything above
-60 dBFS and says why.

And closing the JACK client while its process callback was still appending to
the capture buffer **segfaulted the interpreter** — a crash in the C layer, so
there is nothing to catch. The teardown now stops the callback, waits, and
calls `close()` alone rather than `deactivate()` then `close()`.

Rig at `~/temp/k2k_fw/envrig.py`, results at `~/temp/k2k_fw/looptest.json`.
Program 199 verified back at `Mode:Natural` afterwards and RAM still empty:
panel edits only, discarded on exit, nothing saved.

### The double-null release shape does nothing on its own

Same rig, same hour. Two subjects on ROM program 199 identical but for
`Rel2`'s time, `Loop: Off`, note held 4 s with the capture running 3.5 s past
note-off:

    subject           onsets   during hold   after note-off
    double-null            1             1                0
    Rel2 has time          1             1                0

One onset each, the attack. Nothing under sustain, nothing after release.

**The positive control is what makes that a result.** The same detector, same
envelope, same rig, an hour earlier, counted **61 onsets** with `Loop: seg1F`.
A re-cycle would have been seen. Without that control this is "we looked and
found nothing", which is worth very little.

**And it separates a confound that had been in every observation of the
phenomenon.** mpc2emu's re-cycle rule was drawn entirely from output of their
*old* writer, which put a floored attack-time byte into byte 0 — and 3 is
`seg3F`. So the degenerate release shape and an active loop flag were present
*together* in every capture the rule came from, and nobody had separated them
because byte 0 was not known to be the loop flag until 2026-08-31. Separated,
**the shape alone does nothing**; the loop flag is the mechanism.

Scope: one envelope, panel-built on a ROM program, `Loop: Off`, sustain 0 %.
The original subject was a converted program off a card, and a panel
reconstruction of a file's shape is not the same object — the same caution
§64/§65 needed.

### Pole counts, and a test that could only have refuted

The Guide's DSP-function contents listing enumerates the filters by pole count
directly, which settles a family of codes at once:

    TWO-POLE NOTCH                    code  4  NOTCH FILTER
    TWO-POLE NOTCH, FIXED WIDTH       code 36  NOTCH2
    DOUBLE NOTCH WITH SEPARATION      code 56
    TWO-POLE BANDPASS                 code  3  BANDPASS FILT
    TWO-POLE BANDPASS, FIXED WIDTH    code 35  BAND2
    TWIN PEAKS BANDPASS               code 55

with each entry's own heading repeating it — "Two-pole Notch Filter (NOTCH
FILTER)" — and the body reinforcing it a third time. **Every one of these is
two-pole; the only four-pole entries in the list are the `W/SEP` pair.**

**The ROM route offered for this could only have refuted, never established.**
The proposal was that if codes 4 and 36 shared a dispatch handler they would
share a pole count. They do not share one — §66's table gives each its own
entry and its own name pointer — but *separate* handlers imply nothing either
way. A shared handler would have been evidence; separate handlers are not
counter-evidence. **Worth checking which direction a cheap test can actually
run before spending on it**, especially when the alternative was a card
crossing.

### The file-path run, and a detector that manufactured its own peak

A bank built by mpc2emu's writer and loaded off the Gotek — four programs,
`NULLRUN` (double-null), `NULLPAD` (Rel3 padded one grid step), `RELREAL` (a
real 50 ms release) and `LOOPPOS` (byte-identical to `NULLRUN` except byte 0 =
`seg1F`). All sustain at 87 %, `Dec1 0.30 s`.

    prog      sustain    mod peak   x median
    LOOPPOS   -46.8 dB    2.40 Hz        437
    NULLRUN   -49.7 dB   20.00 Hz        971
    NULLPAD   -49.7 dB   20.00 Hz        722
    RELREAL   -49.7 dB   20.00 Hz        868

**The three Loop-Off programs agree to 0.00 dB and 0.00 Hz**, so the
double-null is indistinguishable from both counter-examples on the file path as
well as on the panel. The control separates by 2.9 dB and an entirely different
modulation frequency.

**The first pass reported the control as dead.** The onset detector from the
loop sweep needs the level to fall below a gap before it re-arms, and these
programs sustain at 87 % — so a `seg1F` loop modulates a held level instead of
firing bursts out of silence, and all four counted one onset. **An instrument
carried from a case where it worked into one where it cannot fire**, which is
the fourth instance of that shape in two days. What caught it was four
identical peak levels: **identical numbers are a smell.**

**And the `20.00 Hz` common to the three is an artefact of the analysis, not a
property of the audio.** Neither of the two offered explanations was right — it
is not the sample's loop (that is at 0.51 Hz) and not the search band's top
edge (the band ran to 60 Hz). Block-RMS framing samples the carrier at the
frame rate and aliases it down: **a pure 220 Hz tone with no amplitude
modulation whatsoever reproduces the effect synthetically, and the spurious
peak MOVES when the frame length changes** — 40.00 Hz at 5 ms frames, 59.83 Hz
at 4 ms and 8 ms.

That does not weaken the null, it states it in the detector's own terms: a
high-frequency carrier-derived peak is what this detector reports **when there
is no real modulation to find**. Re-run with a 20 s hold and a 0.4-10 Hz band,
at 0.054 Hz bins:

    LOOPPOS   2.378 Hz   period 0.4205 s   x6066 median
    NULLRUN   9.946 Hz                     x43   median

A factor of 140 in peak-to-median between them.

### The 41.7 ms overhead is not fixed across envelope shapes

`LOOPPOS` traverses `Att1 0.02 + Att2 0.01 + Att3 0.01 + Dec1 0.30` = 0.34 s
and re-cycles every **0.4205 s**, so its overhead is **~80 ms** — twice the
41.7 ms measured on the panel subject, whose traversal was a single 0.06 s
stage with three zero-length ones before it (overhead 39.8 ms).

§68's own sweep matched to a millisecond within one envelope shape, so the
formula is not simply wrong. **It does not transfer across shapes**, and
whatever the overhead depends on, it is not the count of stages traversed
(that was refuted) and not a constant either. Open.

### A check that cannot fail

Four separate instruments failed the same way in one day, across two projects,
and **none of the four produced a wrong value** — each produced a value that
could only ever have come out one way:

- a scan keyed on a single tag, on data where the tag varied
- a guard shorter than the note it was counting
- a 5 ms analysis window on a 33 Hz carrier
- an onset detector that re-arms below a gap, on programs sustaining at 87 %

Every one of them was an instrument carried from a case where it worked into a
case where it *could not fire*, and every one reported a clean negative. A
detector with no path to a positive result is indistinguishable from a
detector reporting a null, and the reading looks exactly as it should.

**What caught the fourth was four identical peak levels** (−41.7/−41.8 dB
across four different programs): identical numbers are a smell. The general
form of that check is cheaper than re-deriving the instrument — before
believing a negative, feed the detector something it must fire on. §68's
control programs exist for exactly that reason, and they are why the
double-null null is worth anything.

## 69. The filter cutoff's offset, and the byte next to the block type (2026-09-14)

`filter_cutoff_byte_to_hz()` carried the one law this project trusts most —
`Hz = 440 * 2**((s-9)/12)`, verified to 0.08% against the device's own
`Coarse:` display during CUTCAL — together with a docstring saying, in as many
words, that **nobody had ever mapped which byte of a live Program object holds
it**. CUTCAL set and read it entirely through the panel's F1 FRQ page, never
through DUMP, so the registry deliberately had no entry: a conversion that
cannot be pointed at a byte cannot decorate a browser.

Jan loaded the CUTCAL bank to 204ff. Eleven programs `CUT 000`-`CUT 100` that
differ in one parameter are the instrument that closes it — DUMP all eleven,
diff, and the offsets that vary are the candidates
(`probes/p45_cutoff_offset.py`, read-only).

    2 of 272 offsets vary across the set
      offset 189   MONOTONIC   [204, 205, ... 214]
      offset 210   jumbled     [230, 240, 250, 4, 14, 24, 34, 45, 55, 65, 75]

**The monotonic one was the decoy and the jumbled one was the answer.** Offset
189 tracks the program id exactly — it is the keymap pointer, and this bank
ships one keymap per program at matching ids, so the "one-parameter variants"
premise was false in a way that produced a *prettier* signal than the real
field. Checked against ROM programs: 1, 2, 3 and 199 all carry 1 there, and
program 42 carries 151. Not an id.

Offset 210 reads jumbled only because it is **signed**: −26, −16, −6, 4, 14,
24, 34, 45, 55, 65, 75, a clean ladder of ten semitones per step. §62's lesson
arriving a third time.

### Pinned against the panel, endpoints included

    typed 1     -> panel "C 0 16Hz"       byte -48   law    16.4 Hz
    CUT 000     -> panel "A#1 58Hz"       byte -26   law    58.3 Hz
    typed 440   -> panel "A 4 440Hz"      byte   9   law   440.0 Hz
    CUT 050     -> panel "C 6 1047Hz"     byte  24   law  1046.5 Hz
    CUT 100     -> panel "D#10 19912Hz"   byte  75   law 19912.1 Hz
    typed 99999 -> panel "G 10 25088Hz"   byte  79   law 25087.7 Hz

The byte is a **signed semitone index with 0 = C4**; `s = 9` is A4 = 440 Hz
exactly, which is what the `−9` in the exponent has always been. **The first
and last rows are the field's own clamps** — type an out-of-range number and
let the device refuse it, and the refusal pins the endpoint. That is why the
proven range is exactly −48..79 and not a guess with a hedge around it.

Typing into the editor and DUMPing at the same time also re-confirms that a
dump taken with the editor open reflects the edit buffer. Nothing was saved;
the editor was left with "No".

### The real structure: block type, then that block's first parameter

Offset 209 is the F1 block-type byte, and the four DSP slots stride by 16 —
209/225/241/257 — so **`210 + 16k` is the first parameter of slot `k`**, and
what it *means* depends on the type byte beside it:

    prog  1  F1 SINE(23)                 210=  0        F3 LOPAS2(37)  242= 41 -> 2794 Hz  (panel: F 7 2794Hz)
    prog  3  F1 PARA TREBLE(9)           210= 59 -> 7902 Hz  (panel: B 8 7902Hz)
    prog 42  F1 STEEP RES BASS(14)       210=-48 ->   16 Hz  (panel: C 0 16Hz)
             F3 PANNER(40)               242=-17 ->  -17 %   (§56/§57's entry)
    prog 204 F1 4POLE LOPASS W/SEP(50)   210=-26 ->   58 Hz  (panel: A#1 58Hz)

**This is why the entry is gated rather than plain.** Program 1 carries `SINE`
in F1 with byte 0 at offset 210, and the cutoff law renders that as a tidy,
confident **"261.6 Hz"** for a block that has no cutoff at all — the panel's
actual filter page reads 2794 Hz, on a different slot. Programs 6 and 199 carry
`NONE` in F1 and would have decoded just as confidently. An ungated registry
entry would have been the §51 failure exactly: in range, well-formed,
plausible, wrong.

So `Field` grew a `gate` — `(offset, predicate, why)` — and `describe_field()`
takes the gating byte. Without it the decode still renders, but **with its
condition attached**, because an unqualified number is indistinguishable from a
verified one. The TUI reads the block-type byte alongside the field rather than
passing the burden to the user.

`FREQ_BLOCK_TYPES` holds the four types whose `Coarse:` was actually checked
against the panel — 9 PARA TREBLE, 14 STEEP RESONANT BASS, 37 LOPAS2, 50 4POLE
LOPASS W/SEP. `LOPASS` and `HIPASS` are **absent on purpose**: their names say
they belong, and a name is not evidence.

### Only F1 is registered, and the reason is a real limitation

`242 + 16k` wants four entries, but offset 242 already holds `F3 POS Adjust`
for a PANNER block. **One offset, two meanings, selected by a different byte** —
and `KNOWN_FIELDS` is a dict keyed by offset, so it can hold one. F1 is
registered; F2/F3/F4 are recorded here and tracked in TODO.md.

## 70. The display tables, read out of the ROM — and what they corrected (2026-09-14)

§66 used the firmware to settle the DSP function codes. The same image answers
a whole class of open questions, because **the numbers the K2000 shows are
lookup tables, not formulas**, and the tables are in there.

The method is the one that keeps this honest: never search the ROM for
"the LFO table". Search it for **numbers this project has already measured off
the panel**, and let the match say where the table is. Then read the table out
and check it back against the instrument.

### The filter cutoff — §69's clamps were the table's own length

Searching for `440, 466, 494, 523` — four consecutive semitones from A4 — hits
once, at ROM **0x1FC276**. Walking outward, the table runs **0x1FC204 to
0x1FC303, exactly 128 entries**, and every one equals the CUTCAL law rounded
**half-up**:

    index = signed byte + 48,  byte -48 .. 79  ->  16 .. 25088 Hz

**So the clamps §69 pinned by typing out-of-range values are the table's first
and last rows.** Two independent routes, same two numbers. And the rounding is
half-up, not Python's half-even — 1046.5 Hz shows as `1047`, which §69 had
already had to special-case by hand.

### The LFO rate — §61's ceiling was the WHEEL's, not the field's

The rate ladder is at **0x1FB404**, and every one of §61's 185 panel rows
matches. The five "segments" are the table's own step changes, at exactly the
bytes the sweep found: steps of 1, 5, 10, 20 and 50 hundredths beginning at
bytes 0, 20, 36, 126 and 176.

**But the table is 256 entries, not 185.** §61 says "byte 184 is the ceiling —
the wheel will not move past it. The reachable range is 0-184, not 0-255."
Written by SysEx, which the wheel cannot do:

    byte 176 -> 20.00 Hz        byte 185 -> 24.50 Hz
    byte 184 -> 24.00 Hz        byte 186 -> 25.00 Hz
    wheel +1 from 184 -> 24.00  byte 200, 255 -> 25.00 Hz

The wheel stop is real and §61 reported it correctly. **The field is not
limited by it**: a file can carry 24.50 and 25.00 Hz, and the device displays
and uses them. Bytes 186-255 all saturate at 25.00, so the meaningful range for
a writer is 0-186.

### The two depth fields are BIPOLAR, and were half-decoded

§30 had `ENV2->FilFreq` depth as `(byte-28)*100` over bytes 34-124 plus byte
127, with everything else returning "unmapped" because the dense low region
existed only in a chat transcript. The ROM has the whole thing at **0x1F9604**:
256 entries, **symmetric about zero, ±10800 cents**, indexed by a **signed**
byte. `LFO1->Pitch` depth is the same shape at **0x1FA204**, ±7200 cents.

Fourteen bytes checked back against the panel, all exact:

    ENV2->FilFreq (215)              LFO1->Pitch (199)
      10 ->    20ct                    20 ->    20ct
     246 ->   -20ct                   236 ->   -20ct
      58 ->  3000ct                   100 ->  3300ct
     198 -> -3000ct                   156 -> -3300ct
     127 -> 10800ct                   133 -> -7200ct
     128 -> -10800ct                    0 ->     0ct
     129 -> -10800ct
       0 ->     0ct

**The old decoder called the entire negative half "unmapped for this byte".**
Not wrong — it refused rather than guessed, which is what it was built to do —
but blind to half of every one of these fields. Both now decode all 256 bytes
from `k2kremote/k2kromtables.py`.

### What this is and is not

The tables are in the repository as numbers, with their ROM addresses recorded
so anyone can go back to the bytes. **The firmware is Young Chang / Kurzweil's
and is not redistributed**; what is committed is the same fact a panel sweep
produces one row at a time, obtained in one pass instead of 256.

Also found, not yet identified: a 40-entry pointer array at **0x10897E** into a
family of 256-entry tables at 0x1F9604 + k*0x200 — among them ±6000, ±2400,
±500, ±332, 10..32000 and a 0..25000 that has 20 at index 10 and 300 at index
55, which are exactly the AMPENV times of §68's subject. Mapping parameters to
tables needs the parameter descriptors, which have not been found.

### The pattern worth keeping

Every one of these was a **partial** answer that looked complete enough to stop
at: a law with a proven sub-range, a ladder with a ceiling, a formula with the
awkward end hedged. None of them was wrong. Each was the part of the table the
panel could reach — and in the LFO's case, what the panel could reach was set
by a wheel stop that has nothing to do with what the field can hold.

### What the sign was worth downstream

mpc2emu counted their corpus against this the same evening:

    LFO1 -> Pitch routings in 669 files:   1,941
    carrying a NEGATIVE byte (>= 128):       415   = 21.4%, across 87 files

**And the failure was not "a large positive" as predicted here — it was the
maximum.** Every negative byte fell past their `min(b, 123)` clamp, returned
the table's 7200-cent ceiling, and was then taken as full one-sided depth. **A
gentle -10 cent vibrato converted to six octaves of it**, on a fifth of every
LFO-to-pitch routing they carry. Fixed in their `7bfe7da`; zero voices now read
full depth and the median came out at 0.0044.

Two things worth keeping from how that landed.

**The magnitude table is what made a sign fix safe.** Raw 156 is signed -100
and their table's entry 100 is 3300, against the -3300 ct measured here — so
the sign could be corrected knowing the magnitudes underneath it were right.
**A sign fix applied to a wrong magnitude table looks identical from the
outside**: small negatives stay small, the mirror is symmetric, the ceiling is
respected, and every number is still wrong.

**The neighbouring field was already right.** Their `ENV2->FilFreq` is
sign-extended at both call sites, with a comment recording why — an envelope
that sweeps the corner *down* read as one that sweeps it up is a different
patch. So the general warning sent over ("if your parser reads these unsigned")
was half wrong: someone had already got that one right, and the field beside it
never got the same treatment. **The gap was not knowledge, it was reach.**

### One more restore failure, and the fix

A run was killed by its own timeout with a scratch byte still written and the
editor still open. The next run read *that* byte as "the original" and
faithfully restored it. **A pre-test dump is the only trustworthy baseline** —
`cutdiff.json` from §69 had all 272 bytes of program 204, so the true value was
recoverable, and the program is now byte-for-byte identical to it. Cleanup also
has to leave the editor first: a SysEx restore is refused while editing
(`DNAK ObjectCurrentlyBeingEdited`), so the `finally` block that skips that
step reports success and changes nothing.

## 71. The release span, and two ways a beautiful fit measures the wrong thing (2026-09-14)

mpc2emu's `KRZ_RELEASE_SPAN_DB = 99.37` had never been measured — it came from
comparing this machine's *displayed* release against another machine's
displayed release, which is two conversions of an unmeasured span rather than
one measurement of a real one. Every KRZ release they write divides by it.

**Measured: 100.32 ± 0.09 dB**, or 101.5 dB if the ROM time table's
milliseconds are 1.1 % long (see `k` below). Against 99.37 that is 1-2 % high,
which is inaudible — **the value of the measurement is the model, not the
number.**

### The design, and why time-to-silence could not be used

The proposed method was `span = slew × time-to-silence`. The rig cannot do the
second half: interface floor −92.2 dBFS, note peak −37.4 dBFS, so **54.8 dB of
usable range**. Raising the program's OUTPUT gain from +6 to +30 dB recovered
the full 24 dB (peak −13.4 dBFS, **78.8 dB**) with the tail still sitting on
the *interface* floor rather than the K2000's own noise — so the instrument is
quieter than the converter and the limit is a physical input-gain knob. A floor
ADDS to a tail, so a time-to-silence reads short and a span built on it reads
small, with a known sign. Not reportable.

**Measure the span as a SLOPE instead.** If it is a fixed property then
`slew = span / T` for every release time T, so fit slew at several T and
regress against 1/T: the span is the slope, the intercept is a free diagnostic
for a fixed overhead, and **nothing ever needs to see the bottom.**

    500 ms  201.216 dB/s   span 100.61      3000 ms   33.459 dB/s   span 100.38
   1000 ms   99.669 dB/s   span  99.67      4000 ms   25.101 dB/s   span 100.40
   2000 ms   50.099 dB/s   span 100.20      5000 ms   20.060 dB/s   span 100.30

    slew = 100.550/T - 0.181     R^2 = 0.999974  (all six)
    long four: span 100.320 +- 0.092 dB, intercept +0.066 dB/s

**The intercept is zero, so there is no fixed overhead in the release** — a
real contrast with §68's re-cycle, whose overhead is large and does not even
transfer across envelope shapes.

### Two bad fits, and they failed differently

**An error in the x-axis is invisible to per-point fit quality.** Two rungs
came out as outliers (83.6 and 87.8 dB) and they had **the smallest residuals
of the six** — 0.38 and 0.33 dB. The cause was mine: bytes 128 and 153 were
labelled 2500 and 3500 ms by interpolating the table's step instead of reading
it, and the step changes from 20 ms to 40 ms per index at byte 103. The true
times are 3000 and 4000, and with them those rungs join the others.
mpc2emu's formulation is the keeper: **goodness of fit is evidence about the
model given the axes, never about the axes.**

**Selecting points by their LEVEL and then regressing level on time is
regression attenuation.** The first linearity check split the fall into 5 dB
bands and reported 19.43 dB/s at the top falling to 11.36 at the bottom, which
reads exactly like a curve. It is not. Noise decides band membership, so the
fitted slope is dragged toward zero, harder the narrower the band. Demonstrated
on a synthetic fall of **exactly** 20.00 dB/s with 0.35 dB of ripple and no
curvature whatsoever:

    select on LEVEL  -5..-10 dB: 18.75      select on TIME 0.25-0.50 s: 20.54
    select on LEVEL -25..-30 dB: 18.13      select on TIME 1.25-1.50 s: 19.01
    select on LEVEL -45..-50 dB: 18.86      select on TIME 2.25-2.50 s: 20.06

Re-done in the right coordinate — 0.4 s time slices — the same rung reads
**20.26, 20.25, 20.30, 20.30, 20.32, 20.26, 20.07 dB/s from −7 dB to −55 dB,
flat to 0.3 % over 48 dB**, then 18.7, 10.8, 1.8 as it meets the floor. So the
release is straight in dB, and the earlier "bend" was the instrument, not the
machine. The `-10..-50` ladder window was attenuated too, just mildly (20.04
against 20.3), because 40 dB is a wide net.

**The two failures are not the same.** A wrong x-axis leaves the fit pristine
and moves the answer; a selection-biased window corrupts the axis being fitted
*on*, so no amount of care about labels would have caught it.

### k: is a ROM table's millisecond a real millisecond?

Setting T from the table at `0x1FBA04` and confirming it against the panel
proves nothing — **the panel may simply be reading the table out**, and a
constant factor would leave every rung consistent and the span wrong by exactly
that factor. Nothing inside the experiment can see it.

**The attack breaks it, because an attack ENDS at full level, which is visible,
where a release ends below the floor, which is not.** Fit the amplitude ramp
between 20 % and 80 %, extrapolate to 0 and to the plateau, take the
difference: **both ends carry any fixed latency equally, so it cancels** and no
note-on timestamp is needed.

    table 1000 ms -> ramp 1.0132 s        table 4000 ms -> ramp 4.0438 s
    table 2000 ms -> ramp 2.0294 s        table 5000 ms -> ramp 5.0624 s
    duration = 1.0113 x table + 0.0033 s    R^2 = 0.999996

**k = 1.011** — the table's milliseconds are real to about 1 %. The ramp is
linear in amplitude to 1.7 % of plateau, and that residual is also what could
bias k, so it is worth 1 %, not four digits.

A first attempt at k measured "90 % of plateau" against the table and got
0.8662. That is an artefact of the criterion, not the machine: **the criterion
fires at 90 % of the way up a ramp, so its slope is k × 0.9 and nothing inside
it separates the two.**

### Sustain 0 is not a mute here

eosed found the E4XT's sustain 0 reading 22.6 dB below their own noise floor,
which points at a mute rather than an envelope bottom. On the K2000, sustain 0
with a 1 s decay falls smoothly from −17.5 dBFS to **−90.0 dBFS against a
−92.0 floor**, with no discontinuity and no cutoff. At 2 dB of margin that
cannot distinguish a true zero from something below the floor, and it should
not be read as showing one. It does show there is no cliff — so "level 0 is a
mute" is a property of that machine, not of envelope generators.

### The AMPENV level percent, and a knee that is real

Falling out of the decay work: an AMPENV level **percent is not an amplitude
ratio**. Setting 25 % puts the sustain 28 dB below full, not the 12.04 dB a
linear reading gives. mpc2emu's writer already converts through a fitted
curve rather than a ratio, so the open question was only whether the **knee at
the bottom of that curve** — ten dB per halving all the way down and then
twenty-one for the last one — was the machine or the fit.

**It is the machine.** Measured against a level-100 % capture, so the sample's
own contour, the output gain, the interface gain and the velocity all divide
out:

    pct   measured   mpc2emu's law   per halving
    50     18.06         18.07
    25     28.10         28.03           10.04
    12     38.13         37.96           10.04
     6     48.17         47.99           10.03
     3     68.80         69.01           20.64
     0     73.14           --             (floor control, 4.3 dB margin)

**Every point within 0.21 dB, including the knee.** Their curve was right and
is now measured.

Two instrument notes, because the first attempt at this measured nothing and
said so:

**3 %, 1 % and 0 % came back at −88.49, −88.40 and −88.59 dBFS** — within
0.2 dB of each other. That is not a law flattening out, it is three readings
of the noise floor, and **0 % is the control that names it**: a level of zero
cannot be 47.8 dB down *and* be the same number as 3 %. Two causes, both
mine — the OUTPUT gain had been restored to +6 dB along with the rest of the
baseline, throwing away the 24 dB that made the earlier runs work, and the
floor was not being subtracted.

**Subtract the floor in POWER, not in dB.** It adds to the signal, so an
uncorrected reading near it is high and the drop reads low. At the 3 % rung
the correction is 0.87 dB on a 7.4 dB margin, which is the difference between
20.6 and 19.8 dB for that last halving.

The 2 % rung is not reportable: it reads 67.78 dB, *less* drop than 3 %, on an
8 dB margin. Monotonicity failing is the signal that the point is noise.

### Two free known-answer tests, and one rule about preconditions

Both of tonight's saves came from the same cheap move, and neither was planned
as a check.

**The intercept recovered a quantity that was never supplied.** The decay
corner fit returned `corner = 0.9948 x table + 0.3115 s`, and the capture takes
a **300 ms pre-roll** before sending note-on. The fit handed back 311.5 ms:
0.300 that was known and 11.5 ms of real MIDI-plus-audio latency that was not.
Nothing in the model was told about the pre-roll — it tests the whole chain,
clock included, not just the fit.

**The 0 % rung named a floor that looked like a law.** Three readings within
0.2 dB of each other are indistinguishable from a curve flattening out, and
nothing *inside* the sweep can separate them. A rung whose answer is known a
priori can: a level of zero cannot be 47.8 dB down and also be the same number
as 3 %.

**So: put a quantity into the experiment whose value you already know and let
the fit or the sweep hand it back.** It costs one rung or one extra term, it
needs no extra hardware, and it catches the class of error that care does not —
the same family as §68's control programs and §70's "search the ROM for numbers
you already measured".

**And one rule, from the cause rather than the catch.** A restore-to-baseline
that was entirely *correct* left the next measurement silently running 24 dB
quieter, because that measurement depended on a non-baseline setting (the
raised OUTPUT gain) and **inherited** it rather than re-establishing it. The
good behaviour is what set the trap, and it springs on the run *after*.

> **A measurement must assert its own preconditions, not assume the previous
> run's state survived.**

Cheap to obey: every script that needs a non-default setting writes it at the
top, next to the baseline it will restore at the bottom.

## 72. The PITCH page's byte map, and why position-matching could not find it (2026-09-14)

mpc2emu needed the `CAL` segment's PITCH-page fields to carry modwheel-gated
vibrato across conversion paths. They had tried the corpus: 42,932 CAL
segments, three positions holding valid control-source codes, and a
co-occurrence test that **refuted** the obvious reading — `CAL[23] = MWheel`
appeared on 57.1 % of layers where `CAL[21]` was `OFF` and only 17.4 % where it
was set, backwards for a field gating `CAL[21]`'s depth.

Asked the machine instead. `CAL[k]` is Program offset **177+k**. Write one
distinctive byte at a time over SysEx (which the editor refuses, so it happens
outside it), read the whole PITCH page, diff against an all-zero baseline. Only
one byte moves per read, so a changed cell **names** the field rather than
suggesting it.

    offset  CAL    field          offset  CAL    field
     192     15    Coarse (-)      199     22    Depth
     194     17    Coarse (+)      200     23    DptCtl
     195     18    Fine            201     24    MinDpt
     196     19    KeyTrk          202     25    MaxDpt
     197     20    VelTrk          203     26    Src2
     198     21    Src1            207     30    FineHz

`CAL[0..14]`, `[16]`, `[27]`, `[28]`, `[29]` drive nothing on this page.

### The byte order is not the page order, and that is the whole answer

The screen reads `Src1, Depth, Src2, DptCtl, MinDpt, MaxDpt`. **Memory reads
`Src1, Depth, DptCtl, MinDpt, MaxDpt, Src2`** — `Src2` is third on screen and
*last* in the segment. Both corpus anomalies fall straight out:

* `CAL[23]` really is `DptCtl`, so their guess was right. It gates the **Src2**
  wire's depth range, not `Src1`'s depth — which is why it correlates with
  `CAL[26]` and looked backwards against `CAL[21]`.
* `CAL[27]` is zero wherever `CAL[26]` is a source because **`Src2` is not
  followed by its depth**: its depth is the `MinDpt`/`MaxDpt` pair that comes
  *before* it.

Neither is a quirk of the data. Position-based inference assumed the layout
mirrors the display, and on this page it does not.

### Coarse is the difference of two bytes

Two offsets moved `Coarse`, with opposite signs at the same probe value, so
it was worth three more writes rather than a guess:

    192=45 194= 0 -> -45ST      192= 0 194=45 -> 45ST
    192=12 194= 0 -> -12ST      192= 0 194=12 -> 12ST
    192=45 194=45 ->   0ST      192=211 194=0 -> 45ST

**`Coarse = (byte194 - byte192)` as an 8-bit subtraction read signed.** A
parser that reads only one of them gets the transposition wrong whenever the
other is non-zero — worth a corpus count on how often `CAL[15]` is set.

### Two more facts from the same pass

**Offset 208 is defended by the device.** Writing 0 to it reads back `0x50`; it
sits between the CAL segment and the F1 block-type byte at 209 and is not
`CAL`'s to write. `patch_object_bytes`'s read-back check is what caught it,
refusing rather than reporting a write that had been silently overridden.

**Two control-source codes, from the same screens:** `1 = MWheel` (the baseline
value of `DptCtl` in this bank) and `45 = Bal Ctl` (the probe value).

## 73. The keymap page's bytes, and Coarse adds to Xpose (2026-09-14)

§72 left mpc2emu with a live question: they read `cur.transpose = CAL[1]`, and
§72 had found `CAL[0..14]` driving nothing on the PITCH page. Either `CAL[1]`
is the keymap `Xpose` — in which case they read transpose correctly and simply
never read `Coarse`, an additive fix — or it is something else and everything
written back carries the error.

Same method, on the KEYMAP page:

    178  CAL[1]   Xpose          188  CAL[11]  KeyMap id, high byte
    180  CAL[3]   KeyTrk         189  CAL[12]  KeyMap id, low byte
    181  CAL[4]   VelTrk         191  CAL[14]  AltSwitch

**`CAL[1]` is `Xpose`.** Probe 7 reads `7ST`. Their transpose was always right.

Three by-products:

**The keymap pointer is two bytes, 188/189.** Probe 7 at 188 gave
`999 Not Found` and at 189 gave `7 Elec Jazz Guitar`. That also retires §69's
decoy: 189 stepping 204, 205 ... 214 across the CUTCAL bank was a keymap id's
LOW byte, and a reader taking 189 alone breaks above id 255.

**`AltSwitch` took code 7 and displayed `Volume`, the same name code 7 reads in
`Src2`** — the control-source table is shared across pages.

**The control-source codes ARE MIDI CC numbers**, at least through the first
block: `0 OFF, 1 MWheel, 2 Breath, 3 MIDI03, 4 Foot, 5 PortTim, 6 Data,
7 Volume, 8 Balance, 9 MIDI09, 10 Pan, 11 Express, 12-15 MIDI12-15, 16 Ctl A,
17 Ctl B`, plus `45 Bal Ctl`. The unnamed entries are literally `MIDInn`, and
`MWheel` is 1 because it is CC 1.

### They add

Six rungs, pitch measured against the (0,0) capture so the sample's own tuning
cancels:

    Xpose 12  Coarse  0   +11.97 st        Xpose 0  Coarse  7    +7.04 st
    Xpose  0  Coarse 12   +11.97 st        Xpose 7  Coarse  0    +6.99 st
    Xpose 12  Coarse 12   +23.98 st

**Total transposition = `Xpose` + `Coarse` = `CAL[1]` + (`CAL[17]` −
`CAL[15]`).** The two single-field rungs were the carried known: each had to
land on +12 alone, or the rig was not measuring pitch and the joint rung would
have meant nothing.

### Two estimator failures in one measurement

**A single-peak pitch estimator was the wrong instrument and it announced it
with a negative frequency.** An unclamped parabolic vertex on a flat
autocorrelation peak pushed the lag negative, and `log2(f/ref)` threw rather
than returning a plausible number — which is the lucky half. It is also wrong
in principle: a peak-picker follows whichever partial is loudest, so a change
in which harmonic dominates reads as a pitch change, and **octave errors are
exactly the size of the effect being measured**. An estimator that can confuse
+12 with 0 cannot answer a question whose hypotheses differ by 12.

Replaced with a log-frequency spectrum cross-correlation, where pitch is a pure
shift and the whole harmonic series votes.

**And that one was biased toward zero.** The (12,12) rung came back as
`-0.00 semitones` — **a suspiciously round number**, and neither hypothesis
predicted it. The correlation did have a peak at +23.98, at r = 0.386 against
lag 0's 0.528. **An unnormalised cross-correlation loses overlap as the lag
grows** — two octaves costs 27 % of a 7.32-octave grid — so the residual
same-sample similarity at lag 0 beat the true peak. Scoring each lag on its own
overlap (a proper normalised cross-correlation) puts every rung right, with
(12,12) at +23.98, r = 0.589 against 0.528.

Same family as §71's regression attenuation: **the estimator had a preferred
answer built into its geometry**, and it produced it confidently.

### DptCtl scales between MinDpt and MaxDpt, and Dpt is not in it at all

The last field question on the PITCH page, and it decides whether the MPC's
wheel-gated vibrato survives conversion or gets approximated. `Src2` was set to
`Foot` (code 4) held at a fixed CC 4 rather than a constant `ON`, which turns
the wire's contribution into a **static** pitch offset — so nothing has to
estimate a modulation depth. `Dpt` 500 ct, `MinDpt` 100 ct, `MaxDpt` 300 ct,
three distinct values off the ROM table.

    Src2=Foot CC4=0,   DptCtl OFF     +0.00 st     <- carried known
    Src2=Foot CC4=127, DptCtl OFF     +0.99 st     = MinDpt
    DptCtl=MWheel  wheel   0          +0.99 st     = MinDpt
    DptCtl=MWheel  wheel  64          +1.97 st     (predicted 2.00)
    DptCtl=MWheel  wheel 127          +3.00 st     = MaxDpt
    Dpt=0ct  DptCtl=MWheel wheel   0  +0.99 st     <- unchanged
    Dpt=0ct  DptCtl=MWheel wheel 127  +3.00 st     <- unchanged

**`DptCtl` scales the `Src2` depth linearly between `MinDpt` and `MaxDpt`, and
`Dpt` belongs to the `Src1` wire only.** The decisive rung is the last pair:
changing `Dpt` from 500 ct to 0 with everything else held moves the reading by
nothing at all. That is a difference rather than an inference across rungs, so
no clamping argument can rescue the alternative — with only endpoints to
compare, both hypotheses fit.

So the idiom converts exactly, with no approximation: `Src2 = LFO1`,
`MinDpt = D*(1-Kw)`, `MaxDpt = D`, `DptCtl = MWheel`.

**And one fact for READING the 4,770 existing layers that use this:** with
`DptCtl` **OFF**, the wire sits at **MinDpt**, not MaxDpt. A layer with
`DptCtl` off and `MinDpt != MaxDpt` sounds at its minimum, and a reader that
takes `MaxDpt` as the depth overstates every one of them.

The 64-wheel rung lands at 197 ct against a linear prediction of 200, which is
under two bins of the estimator's 4.3-cent resolution — linear within what this
measurement can see, and not evidence of a curve.

### The small-depth "threshold" — withdrawn, and what it cost

Alongside the curve confirmation, the audio read **zero pitch shift** for
declared depths below 75 cents and exactly the declared value above, with the
step reproducible at byte 40 across an interleaved re-run. It was tempting, it
was stable, and **it is not a result.**

Three estimators were applied to the same captures and two of them contradict
the third inside their own stated validity:

    byte 40, declared 75 ct
      log-spectrum correlation      75.1 ct   (matches the panel)
      low-partial tracking, +-150c   0.0 ct   (window covers 75 c easily)

A fourth and fifth had already failed earlier: a nearest-peak tracker whose
+-2.5 % window was **narrower than the shift it was chasing**, so it re-found
the same partial and reported ~0 for a known 300 cents; and an independent
harmonic-sum `f0`, which latched onto subharmonics and returned −122 ct for a
known +100.

**The material is why.** The reference capture's strongest low partials are
149.9, 158.2, 187.4, 199.9, 249.8, 281.2, 349.8 and 375.0 Hz — 149.9 and 158.2
are 93 cents apart, 187.4 and 199.9 are 112 apart. **That is not one harmonic
series.** Every one of these estimators assumes a single pitched source, and
`RELREAL`'s sample does not provide one.

So the honest position is that **pitch shifts below about 100 cents cannot be
measured on this material at all**, and the apparent threshold is an artefact
of two estimators' valid ranges meeting near there — not a property of the
machine. The claim is withdrawn.

What survives untouched, because none of it depends on the audio or on small
shifts: the panel-confirmed byte-to-cents curve (§73), the DptCtl scaling at
100/200/300 cents, and the transpose arithmetic at 7, 12 and 24 semitones.
Measuring the small end properly needs a program built on a genuinely harmonic
source — a sine, or a single-cycle sample — not this bank's pad.

**And the general lesson is not "use a better estimator".** Five failed here in
one sitting, each with a different mechanism, and the synthetic control that
vindicated one of them (a resampled copy of the reference, which it read to
within 1 cent at 10 cents) **could not see the problem, because resampling
preserves whatever inharmonicity the source already had.** A constructed signal
only tests what it varies.

**The companion rule**, from mpc2emu, and it is the sharper half: *a control
proves the estimator handles the variation you introduced, and says nothing
about the properties you copied.* Four of the five failures here were caught by
a known-good rung sitting in the same table, and the fifth only by a different
method disagreeing. **None was caught by the synthetic control.**

**And one more shape of the same disease, from their side of the same
evening:** their round trip preserved the wheel gate to `0.0000` on four
hand-picked values. Swept over 793 `(depth, Kw)` pairs the worst errors are
0.0294 and 0.0667 — the quantisation of `MinDpt` and `MaxDpt` cancels in their
*ratio* at the points that happened to be chosen. **A number that reads as
precision and is coincidence.** They put the swept figures in the docstring
rather than the flattering ones.

## 74. The HOB filter block's byte map (2026-09-15)

mpc2emu could not rank two "assumed" K2000 constants because they could not
histogram the fields, and their attempt to find `KeyTrk` by corpus position
gave "10.1 % of 43,424 blocks out of `seg[3]`" — **flagged as a guess rather
than sent as a reason to spend bench time**, because §72 had just shown the
byte order is not the page order.

Same method: one distinctive byte at a time into the F1 block, the `F1 FRQ`
page read back and diffed against an all-zero baseline. Block base is
`209 + 16k` (§69), so `seg[j]` is offset `209 + 16k + j`. **The type byte
itself is deliberately not swept** — changing it changes which page exists.

    seg[ 1]  210  Coarse       seg[ 7]  216  DptCtl
    seg[ 2]  211  Fine         seg[ 8]  217  MinDpt
    seg[ 3]  212  KeyTrk       seg[ 9]  218  MaxDpt
    seg[ 4]  213  VelTrk       seg[10]  219  Src2
    seg[ 5]  214  Src1         seg[11]  220  Pad
    seg[ 6]  215  Depth        seg[12..14] nothing on this page

**Their `seg[3]` guess was right**, and their `Src1`/`DptCtl`/`Src2` at 5/7/10
are confirmed.

### The same displacement as CAL, in a different segment

The page reads `Coarse, Fine, KeyTrk, VelTrk, Pad` down the left and
`Src1, Depth, Src2, DptCtl, MinDpt, MaxDpt` down the right. Memory reads

    Src1, Depth, DptCtl, MinDpt, MaxDpt, Src2

— `Src2` last in memory, third on screen, **exactly as in `CAL`** (§72), and
`Pad` last of all. So it is not a quirk of one segment: **the K2000 stores the
second modulation source after its own depth fields, on both pages.** Anyone
inferring either layout from the display gets `Src2` and `DptCtl` wrong in the
same way twice.

### Four different curves inside eleven bytes

Probe byte 33, decoded by what the panel showed:

    Coarse                 A 6 1760Hz   = 440*2**((33-9)/12)   (§69's law)
    Depth/MinDpt/MaxDpt        500 ct   = ENV2_FILFREQ_CT[33]   NOT the pitch curve
    VelTrk                     500 ct   = same
    KeyTrk                  66 ct/key   = 2 x the byte
    Pad                          6 dB   = ?

`LFO_PITCH_CT[33]` is **46 ct**, an order of magnitude out — so the filter
block's depth fields use the `ENV2->FilFreq` curve and the pitch page's use the
LFO-pitch one. Two curves, same field names, different segments. A converter
that picks one by field name rather than by segment is wrong by 10x on
whichever it guesses second.

### And the byte before each block type is defended

Offset **224** refused to be zeroed — the byte immediately before F2's type
byte at 225 — exactly as **208** did before F1's at 209. Twice is a pattern:
there is something at `209 + 16k - 1` that is not the block's to write, and
`patch_object_bytes`' read-back check is what caught both rather than reporting
a write the device had silently overridden.

**A note on the first attempt, which found nothing and was right to.** It ran
on program 202, whose F1 block type is **62 = `NONE`** — no filter, so no
`Fn FRQ` page at all. The sweep refused to diff a page it could not reach
instead of reporting fifteen "no change" rows, which is what an unguarded
version would have produced: fifteen confident negatives from a page that was
never open.

## 75. Offsets are not addresses — the segment stream, and what the "defended" bytes were (2026-09-15)

Every offset this project has recorded — 199, 228, 241, 262, 263, and now 117 —
is an address **inside program 204's layout**. mpc2emu went to calibrate against
one of them and found the same field at **seventeen distinct byte positions
across 6,575 corpus programs**; 204 happens to be the modal layout, which is
why "their 228 is our 204" worked exactly once. The segment stream before the
HOB blocks varies with what a program contains.

So the portable form is **(segment tag, body index)**. Walking program 204:

    0x1a @ 104   0x1b @ 108   0x20 @ 112   0x21 @ 128   0x22 @ 144
    0x23 @ 160   0x40 @ 176   0x50 @ 208   0x51 @ 224   0x52 @ 240   0x53 @ 256

Tag byte, then the body. `0x21`-`0x23` and `0x50`-`0x53` carry 15; `0x40`
carries 31. Converting what this project already had:

    199 -> 0x40[22]   LFO1->Pitch Depth      262 -> 0x53[5]   F4 AMP Src1
    228 -> 0x51[3]    F2 RES KeyTrk          263 -> 0x53[6]   F4 AMP Depth
    241 -> 0x52[0]    F3 block type          117 -> 0x20[4]   ENVCTL Att VelTrk

§72's `CAL[k]` **is** `0x40[k]`, and §74's `seg[j]` **is** `0x50[j]`, so both
maps were already structural and only the anchors were not.

### The "defended" bytes were segment tags

Offsets 208 and 224 refused writes during the CAL and HOB sweeps, and 112
refused during the ENVCTL sweep. This project recorded that twice as "the byte
before each block-type byte is defended by the device" and called it a pattern
without a mechanism. **They are the tag bytes** — `0x50`, `0x51` and `0x20`.
Not defended parameters: the structure itself, which is why the device would
not keep a zero there.

The observation was right and the model was wrong for two days, and it took a
question about address spaces to produce the explanation. `patch_object_bytes`'
read-back check is what refused each one rather than reporting a write the
device had silently overridden.

**Writing a tag has effects beyond its own byte.** The refused write at 108
(`0x1b`) also cleared `0x20`'s three `Source` bytes, which the sweep then
restored incidentally as it passed each one — visible in the run as `Source:
OFF` trailing off across successive rows. **Do not probe tag bytes**; sweep
bodies only, and take the segment map first.

### ENVCTL, in full

`0x20`, body 15 bytes. `VelTrk` exists only on the `Att` row, which matches the
manual's "velocity tracking is hard-wired to the attack sections":

    [2] Att Adjust   [3] Att KeyTrk   [4] Att VelTrk   [5] Att Source   [6] Att Depth
    [7] Dec Adjust   [8] Dec KeyTrk                    [9] Dec Source  [10] Dec Depth
   [11] Rel Adjust  [12] Rel KeyTrk                   [13] Rel Source  [14] Rel Depth

Located by setting the field from the panel and dumping with the editor open,
so nothing was saved. **`1.000x` is byte 0, and returning to it produced an
empty diff against baseline** — "is neutral really neutral" answered by
observation rather than inference.

### The multiplier is the E24 series, and the ROM had it all along

    ROM 0x1FC404, 256 entries, signed-byte index, thousandths, 0.018x .. 50.000x

    -7: 0.500    0: 1.000   +5: 1.500   +8: 2.000   +15: 4.000   +23: 8.000

    1.0 1.1 1.2 1.3 1.4 1.5 1.6 1.8 2.0 2.2 2.5 2.7 3.0 3.3 3.6 4.0 ...

**E24 preferred numbers, 24 steps per decade.** A doubling is
`24*log10(2) = 7.22` steps, which is exactly why +8 doubles and x4 lands on +15
rather than +16 — an asymmetry recorded here as "not quite the obvious one"
while a panel sweep was being set up to map it point by point.

Jan asked whether this project had a firmware image, which it does and has used
since §66. **Having the tool is not the same as reaching for it**: the ROM
answered in one search what the sweep would have spent an hour approximating.

## 76. Velocity to attack time: the law, and three machines with three anchors (2026-09-15)

`ENVCTL Att VelTrk` is `0x20`[4] (§75), and its multiplier comes from ROM
`0x1FC404`. What the byte *does* needed measuring, because "the multiplier
applies at full velocity" is an assumption about the **anchor**, and mpc2emu
had already found the AKAI anchoring at velocity 64 and the E4XT at 127.

Rig: `F4 AMP VelTrk` zeroed so velocity cannot change loudness — every capture
then has the same plateau and any difference is timing alone. AMPENV Loop
forced Off (204 and 202 ship `seg3F / Inf`, which is §68's re-cycle). A **User**
envelope, since ENVCTL does not affect a Natural envelope's attack. Attack read
as the ramp's own duration, 20-80 % fit extrapolated to both ends so fixed
latency cancels (§71).

    control (VelTrk 0)   vel   1: 2029.0 ms    vel 64: 2030.3    vel 127: 2027.7
    VelTrk +8 (2.000x)   vel   1: 2014.3       vel 32: 1697.9    vel  64: 1428.3
                         vel  96: 1204.4       vel 127: 1013.3

**`t(1)/t(127) = 1.988` against `M = 2.000`.** And the shape is exponential:

    vel             32      64      96     127
    log2(t1/tv)   0.246   0.496   0.742   0.991
    (v-1)/126     0.246   0.500   0.754   1.000

**`t(v) = t(nominal) / M**((v-1)/126)`**, anchored at velocity 1 and reaching
the full multiplier exactly at 127. Confirmed in the other direction with
`M = 0.470`: measured ratios 0.8307 / 0.6850 / 0.5656 / 0.4721 against
0.8305 / 0.6856 / 0.5659 / 0.4700. **Span = M both ways.**

So on this machine the span mpc2emu carries — `t(1)/t(127)` — **is** the
displayed multiplier, with no conversion at all.

**Three machines, three anchors:** K2000 at velocity 1, AKAI at 64, E4XT at
127. Not one pair agrees, and assuming an anchor rather than measuring it is
wrong on two of three with a silent failure — the routing still sounds like
velocity affecting attack, just with the wrong end of the keyboard pinned.

### The anchor that moved, and did not

The negative run put `t(1)` at **1681 ms** where the control had said 2029,
which would have meant the programmed time lands at a different velocity
depending on direction. It does not. **A control run at the identical hold and
identical analysis windows gives 1676.4 / 1682.4 / 1683.2 ms** — the negative
run's `t(1)` matches its own control exactly, and velocity 1 is the anchor in
both directions.

**The 17 % was my analysis geometry**, and the mechanism is worth the line: the
long-hold version estimated the plateau from `t > t[-1] - 1.4`, and on a
7.8-second capture that window **contains the release**. A plateau estimated
too low makes the extrapolated ramp too short, by the same factor on every
rung — which is exactly why the ratios stayed perfect while the absolute
numbers moved. **Take absolute attack times from the short-hold geometry
(2029 ms for a 2000 ms table entry, against §71's `k` predicting 2022); take
ratios from either.**

### Three process failures, one of them new in kind

**The subject.** The first attempt ran on program 204 — `CUT 000`, whose 4-pole
lowpass sits at **58 Hz**, so a note at key 48 is almost entirely removed. The
plateau came out 1.5 dB above the floor and the estimator reported attack times
of **592 seconds**. mpc2emu's framing is better than "check your subject":
**the property that qualified it disqualified it.** 204 is the right subject
for panel and DUMP work *because* it has a filter block, and the wrong one for
audio *because* of where that filter sits.

**The guard that was skipped, then mis-sequenced.** `Rig.prove()` exists to
catch exactly a dead audio path, and was not called. Added, it was then called
**before** the program was selected, so it tested the previous run's leftover
program and condemned a path that was fine. **A precondition check has to run
after the preconditions are established** — §71's restore-to-baseline lesson,
broken in the opposite direction inside a day. mpc2emu's general form:
*the check ran, so it felt checked* — the mechanism existing is what stops
anyone examining its position or its applicability.

**And §75's own lesson, broken within the hour**: the output-gain offsets
254/270 were blind-written into 204, where they land in the `GAIN` block's body
rather than on an output wire. An offset is only an address inside a layout.

### A correction is itself a claim

After a power-down the K2000's RAM bank 2 came back with **0 objects**, where a
verified bank had been left. This session reported "the programs did not come
back" to mpc2emu as a finding; mpc2emu propagated it into a retraction of a
documented claim within ten minutes.

**The counter-argument was already written in the note being retracted.**
It had been investigated once before, on 2026-08-31, and the conclusion
recorded then was explicit: *"don't read a post-power-cycle empty RAM state as
evidence of that without confirming whether a cleanup was done first"* — Jan
routinely runs `Master -> Delete -> Everything` after a power cycle, because
anything referencing loaded sample RAM is broken anyway. **A cleanup and a flat
battery produce an identical `DIRBANK` result**, and nothing observable from
this side distinguishes them.

So the reading had two explanations and was reported as one. Neither session
opened the file it was about to edit.

> **A correction is itself a claim and needs the same check as any other
> assertion.** "You were wrong about X" is the hardest thing to refuse, which
> is exactly why it should be the easiest thing to verify — and the cheapest
> possible check here was re-reading our own note before overwriting it.

What survives is narrower than either the finding or the retraction, and is
what both notes now carry: **an empty bank after a power cycle is unsurprising
and uninformative about the cause — ask, do not infer.** And operationally,
regardless of cause: **never stage RAM contents on one evening for a
measurement on the next.** Re-read the bank at the start of every session and
treat anything left there as gone until `DIRBANK` says otherwise. Both sessions
had planned the other way, which is what made the exchange worth having even
though the finding evaporated.

## 77. The capture path is mono — and §58 said why (2026-09-17)

mpc2emu's LFO→pan depth is written as a plain fraction of the target's rail,
a convention never measured on any machine. On the E4XT it produced **39.21 dB
of pan swing against the MPC original's 5.11**. The K2000 writer does the same
thing (`round(depth * 50)`), so a depth ladder was built here to calibrate it.

### The ladder

ROM 199 is `1 Grand Piano` on algorithm 1 — **not** the sine it was remembered
as. Built explicitly instead: **algorithm 2** (`PITCH / 2POLE LOWPASS / PANNER
/ AMP`, the panner in slot `0x52`), **keymap 163 `Sine Wave`** for a mono
sustaining source, `F1 Coarse` opened to 25088 Hz so the filter colours
nothing, **LFO1 at 0.20 Hz** (byte 20), PANNER `Src1` = LFO1. Six objects
written to RAM 200-205 by SysEx `Write` (0x09), differing only in the depth
byte: 2, 4, 6, 10, 20, 50.

Two things the build cost, both worth keeping:

**The algorithm number is the wiring, not the functions.** The ALG page's
cursor opens on a **block**, not on `Algorithm`, so typing 2/13/24/26 there
sets the block's *function* — which is why "13" came back as `PARAMETRIC EQ`,
function code 13, while the algorithm never left 1. And **a block silently
ignores a function code it does not offer**, so typing 40 for PANNER under
algorithm 1 looked exactly like the panel ignoring the keypress.

**Bank select: the K2000 obeys BOTH `CC0` and `CC32`**, bank = `id // 100`.
Two notes disagreed, each was evidence only of what its author had tried, and
the device settled it in one round — *the arbiter for a disagreement about a
machine is the machine*. A bare program change with no bank select lands on
the current bank: `PC 0` selected `100 Cheeze`.

### The full control-source table

128 codes, read off the panel one at a time, because LFO1 was not in the
30-75 window guessed from §73's "the low block is MIDI CC numbers":

    0-31     MIDI CC numbers       1 MWheel  2 Breath  4 Foot  7 Volume  10 Pan
    32-63    per-voice + clocks   33 MPress  36 Bi-Mwl  40 LFO2  47 A Clk4
    64-95    switches, more CCs   64 Sustain  65 PortSw  75 LegatoSW  91 FX Depth
    96-127   the MODULATORS      100 AttVel 110 ASR1 112 FUN1 **114 LFO1**
                                 120 AMPENV 121 ENV2 **127 ON**

**The CC block is real and it is a trap**: the modulators sit at the top,
above a second scattering of raw `MIDInn` entries. `127 = ON` is the constant
source hunted for unsuccessfully across two earlier sessions.

Duplicates repeat §66's pattern from the DSP function table: `ASR2` at 38 and
111, `FUN2` at 39 and 113, `LFO2` at 40 and 116, `LFO2ph` at 41 and 117. And
**code 40 is `LFO2` as a SOURCE and `PANNER` as a FUNCTION** — one byte, two
namespaces.

### The result: zero modulation at every depth, and why that was not the answer

All six captured cleanly — fundamental 261.6 Hz, second harmonic −76 dB, so
the sine was sounding at the right pitch — and the balance never moved:
`L/R` −0.235 dB at every depth, swing 0.00 dB across a 25x range.

**mpc2emu refused to report it, and that refusal is the result.** Six programs
failing identically is a worse story than one path carrying the same signal
twice, and **a reading in which nothing changed is indistinguishable from a
measurement that was never connected.**

The positive control, measured here with L and R read **separately** (the
rig's own `capture()` returns `(L+R)/2`, averaging the two channels in
question):

    centre   0%   L -20.30  R -20.07   L-R -0.24 dB   corr +1.0000
    hard L -100%  L -19.92  R -19.68   L-R -0.24 dB   corr +1.0000
    hard R +100%  L -21.68  R -21.45   L-R -0.24 dB   corr +1.0000

**Identical balance at hard left, hard right and centre, correlation +1.0000.**
The capture path is mono. Confirmed against the other three rigs, which show
5.74 / 45.23 / 29.90 dB of balance variation against the K2000's **0.01**.

**And the absolute level DOES move with `Adjust`** — which is what makes this a
diagnosis instead of a null. §58 established a month ago that the K2000's
PANNER is **one wire in, two wires out**, summing to inaudible at centre. What
reaches the capture is that sum: panning shifts the summed level by a dB and
can never shift the balance. The mechanism was on record; no question had yet
needed the two wires separated.

### What it costs, and the general form

**Nothing already measured is in doubt.** Every K2000 measurement this project
has ever taken — spans, envelope times, filter corners, the velocity law — is
a LEVEL measurement, which a mono path serves perfectly.

> **The rig we trust is a map of the questions we have already asked.**

The same shape as the guards being a map of the mistakes already made, one
layer down. A property nobody knew the rig had, exposed by the first question
that required two independent channels.

**One more instance of the ratio trap, from mpc2emu's side:** their first
stereo test read the K2000 as "STEREO, 15.95 dB" because it ran over the whole
capture, including onset and decay frames where both channels sit near the
floor and their ratio is noise. Restricted to the steady window: 0.01 dB. **A
ratio of two small numbers is a reading that is not there** — and it nearly
contradicted a positive control.

**And tags are positional, not searchable by value.** The first read-back of
the ladder reported `keymap=0` for all six, having found the `0x40` CAL tag by
scanning for a byte equal to 64 — which matches data. Anchored from the
object's end instead (`0x53` at size−16, CAL at size−96, asserted), all six
read keymap 163. Third time in one session that hunting a structure by its
value found something earlier and wrong.

### RETRACTED: the capture path is not mono — the wires were unspread

**§77's conclusion is withdrawn. The K2000 capture path is stereo.** The
balance moves as soon as the PANNER's two output wires are spread:

    before: 0x52 body[2]=0x00 (pan +0)  body[14]=0x00 (pan +0)
    after :           =0x70 (pan +7)            =0x90 (pan -7)

    LFO running, Adjust 0   balance mean  +5.51 dB  sd 5.164  p05..p95 15.73 dB
    static hard LEFT        balance mean +10.59 dB
    static hard RIGHT       balance mean  +1.90 dB

8.7 dB of static shift and 15.73 dB of modulation, against 0.01 dB before. The
three-path comparison was a true reading of a **program that could not pan**,
not of a path that could not carry it.

The missing bytes are in HOB segment `0x52`: **body[2] and body[14], high
nibble a 4-bit signed pan (−7..+7)**. mpc2emu's trap is worth carrying: `0x90`
and `0x94` are *both* pan −7, and two wires hard left sum exactly as two
centred wires do — indistinguishable from the original fault.

**How this went wrong, which is the part worth keeping.**

**§58 was read as corroboration when it was the alternative hypothesis.** This
project has carried "the PANNER is one wire in, two wires out, and centred
wires sum to inaudible" for a month. It explains the observation completely
*without* any mono path. Citing it in support of the wiring conclusion
converted a missing check into apparent confirmation — **worse than not having
the note at all**, because a hypothesis that arrives with a mechanism attached
stops being interrogated.

**And the positive control was not one.** A static `Adjust` sweep exercises the
panner's *input* stage; the failure was downstream of it, in the output wires.
So the control could only ever return the same answer whichever hypothesis was
true.

> **A control is only positive if the effect it induces must traverse the part
> in question.**

mpc2emu's own file had recorded the result in advance — *"Adjust +50% moved the
image 0.01 dB while centred — even the STATIC offset is inaudible unspread"* —
and neither session went looking for it.

**Jan asked "did you check the output setting page".** Two sessions held the
mechanism in their own notes, agreed with each other, and the question that
separated the explanations came from the person who had read neither.

What survives from §77: the control-source table, the CC0/CC32 finding, the
algorithm-versus-function distinction, the positional-tags rule, and the ratio
trap. What does not: every sentence about wiring.

### The result: 0.372 dB per byte, linear over a 10x range

With the wires spread, the ladder measured:

    byte  2   0.75 dB pp   resid 0.01    0.376 dB/byte
    byte  4   1.50 dB      resid 0.03    0.374
    byte  6   2.23 dB      resid 0.04    0.372
    byte 10   3.69 dB      resid 0.08    0.369
    byte 20   7.45 dB      resid 0.21    0.372
    byte 50  35.08 dB      resid 8.08    <- saturated

**0.372 dB/byte, constant to ±0.003 across a tenfold range**, with the LFO
recovered at 0.201 Hz on every point against the dialled 0.20 — which is the
sine source and the byte-20 rate setting both confirming themselves.

The K2000 is genuinely linear here where the E4XT was not (0.64 then 1.75 dB
steps at the equivalent scale), so mpc2emu's 5.11 dB target lands at **byte
14** as an interpolation the law supports rather than one it merely tolerates.
Their writer had been emitting **byte 32**, well past where the residual gives
out.

**The residual column found the unusable region before the swing did, on all
three machines** — 0.01 at the bottom rising to 8.08 where the law stops. That
column was mpc2emu's request at the start and it earned its place three times.

Their three pan scales are 0.1563 (E4XT), 0.1563 (AKAI) and **0.4377** here.
The first two matching had looked like a shared law; the K2000 shows it was two
rails needing similar reduction from the same wrong starting convention.

**And the retraction's accounting, corrected by mpc2emu:** not more mine than
theirs. This session had §58 and read it as corroboration; they had
`§K2PANWIRES` in their own writer, hardware-confirmed twelve days earlier,
carrying the literal prediction *"Adjust +50% moved the image 0.01 dB while
centred — even the STATIC offset is inaudible unspread"* — the control, its
result and the diagnosis, in a file they had edited twice that night. **Two
sessions, two copies of the answer, neither opened.**

## 78. Two contaminated spans, and a 1.43x that is not a machine constant (2026-09-18)

Jan heard `Sangre`'s release as too short on the K2000 against the MPC source
and the two other conversions. Measured on one metric — **seconds from note-off
to a 30 dB fall**, because per-capture curve fits over different windows are
not comparable:

    MPC One (source)     0.420 s
    AKAI S3000XL         0.420 s     <- matches the source exactly
    K2000 Rel1 0.840     0.225 s     <- 1.87x fast
    K2000 Rel1 1.420     0.295 s
    K2000 Rel1 2.000     0.410 s     <- 2.03 s would be exact

So the K2000 needs **1.43x** the Rel1 the arithmetic asks for
(`99.37 / rate` = 1.420 s). The question is whether that factor is a property
of the machine or of this program.

### It is not Dec1

Set Dec1 from 3.36 s to 10 s, which moves the decay state at note-off a long
way — the note-off level rose 6.3 dB, so the write demonstrably took — and the
30 dB time moved **3.7 %**, 0.410 to 0.425 s. A prediction written down before
the capture said a real contributor should move it *"large and obvious, not a
few percent"*. It did not. It also is not zero, which is the awkward outcome:
**Dec1 contributes a little and explains nothing.**

### And the machine is not the problem either — §71's intercept says so

The suspicion was that `KRZ_RELEASE_SPAN_DB` had been measured on a
purpose-built subject with no decay of its own, and so under-predicts on real
material. The subject was purpose-built. But §71 regressed slew against 1/T
over six release times and **the intercept came out at +0.066 dB/s** against
slews of 20 to 200 — and a sample contributing its own decay would add a
near-constant dB/s to every rung and appear exactly there. It did not. **On
that subject the 99.80 dB is the envelope's span, not an artefact.**

### Two contaminated numbers on opposite sides

Which leaves the material — and mpc2emu's own `MPC_RELEASE_SPAN_DB = 38.3`
**was measured on Sangre.** So the samples' decay is inside that 38.3, and
inside the K2000's apparent requirement too, in the other direction.

> **Two contaminated constants on opposite sides is how you get a factor that
> looks like a machine property and is not one.**

Fitting a shared sample-decay term reconciles them at around 23 dB/s and
predicts 2.14 s against the 2.03 measured — which mpc2emu declined to claim,
correctly: a free parameter fitted to the same three points it then predicts.

The clean fix is to re-measure the MPC's span the way §71 measured the K2000's
— decay-free subject, several release settings, regress and check the
intercept — making it the envelope's span rather than one program's. That needs
MPC bench time and is Jan's call.

### Two things worth keeping

**The K2000's envelope times are a quantised table, not a continuum**
(ROM 0x1FBA04, exported to `~/temp/k2k_tables/envelope_times_ms.json`). Any
prediction that divides by a *requested* time carries the quantisation error;
`1.420 s` happening to be an exact entry was luck. Steps run 2, 3, 5, 10, 20,
40, 100, 500, 1000, 5000 ms — **and the first four change within the first five
indices, so a table reconstructed from the step rule is right in the middle and
wrong at both ends.** A rule that describes most of a table is not the table.

**And a theoretical conversion that is more principled than an empirical one is
still worse if the empirical one was fitted to the real thing.** mpc2emu backed
out a change that would have moved the AKAI's `RELSE1` from 55 to 59 on
theoretical grounds — 55 being the value Jan had confirmed by ear that
afternoon. Same shape as §77's retraction: the better-sounding reasoning
winning over evidence already in hand.

## 79. The release law is affine, and one manipulation beat a third program (2026-09-18)

§78 left a **1.43x** between the release the arithmetic asks for and the one
the K2000 needs, with no explanation. It resolved into two separate findings,
and the route there is worth as much as either.

### The branch, and a constant used outside its scope

mpc2emu's `_fill_env` has two branches. Below the 33 % knee both release legs
aim at silence and **Rel1 carries the whole fall**; above it Rel1 only fades to
the knee and Rel2 finishes. They map Rel1 to audible fall **4.7x differently**:

    branch       sustain   Rel1 written   -30 dB fall   ratio
    below-knee      0.00      2.00 s         0.435 s     0.22
    above-knee      0.63      1.45 s         1.51  s     1.04
    above-knee      1.00      8.32 s         8.58  s     1.03

So a factor fitted on one branch is wrong on the other by a factor of five, and
the old 1.9 had been fitted on a *sustaining* program — roughly right above the
knee, badly wrong below it, which is exactly the case Jan reported.

**And §71's own span has the same defect.** It was measured with Dec1 and
sustain at 100 % — **above the knee** — so 99.80 dB is that branch's span.
Applying it below the knee was the same category error in the other direction.
The constant is not wrong; **its stated scope is.**

### A manipulation instead of a third correlated observation

Both sessions framed the next step as "we need a third program". mpc2emu was
right that this was wrong: two programs differ in release time, sustain,
samples **and** Rel2 at once, so a third is one more correlated observation.
**Rel2 is settable** — so hold everything else fixed and move the one quantity
the relation is about. Correlation across programs becomes manipulation on one.

Better still, **hold Rel1 fixed too**: the `slope x Rel1` term is then common to
every reading, so a difference between two Rel2 settings is a difference in
intercept with **no line fitted, no slope assumed, and no extrapolation into
the noise floor.** Every argument of the preceding two hours — two-point fits,
which dB depth, fitted-versus-measured — was downstream of estimating a slope
nobody needed.

    Rel1 8300 ms throughout, Rel2 swept, t(-30 dB):

    Rel2    measured   predicted    miss     role
     500     8.235      8.235        --      fit point
    1000     8.330      8.344      -0.014    out of sample
    1500     8.460      8.453      +0.007    out of sample
    2080     8.580      8.580        --      fit point
    3000     8.770      8.781      -0.011    out of sample

**Proportional across a 6x range**, three out-of-sample misses straddling zero
at max 0.014 s against an sd of 0.005.

**A saturation mechanism proposed here is refuted on the terms set for it in
advance.** The claim was that Rel2 stops contributing once −30 dB arrives
before Rel2 ends; mpc2emu worked out that this puts the crossover below 1500,
and 1500 landed +0.007 s from prediction. Written down before the last capture:
if 3000 lands on the line the mechanism is **wrong**, not "it saturates above
3000" — which would be moving the goalposts to wherever the data is not.

### The control that was never fitted

    Rel2 500 -> 3000        coefficient
      -10 dB                   -0.0121      <- flat, and never used in any fit
      -20 dB                   +0.0689
      -30 dB                   +0.2165

**Rel2's influence grows with measurement depth**, and the −10 dB row — above
the knee, where Rel2 should not reach at all — stays flat across the whole 6x
range. An out-of-sample control on a parameter no fit ever saw is worth more
than the five-point line it sits beside. It also answers, with a measurement
rather than an argument about floor guards, the standing worry that the whole
effect was −30 dB sitting in the mud.

**And it killed an earlier claim of structure.** With one depth the intercept
matched a quarter of each program's Rel2 to three digits — and across three
depths the intercept is −0.021 / +0.157 / +0.520, so **"intercept = Rel2/4" was
a statement about the depth that happened to be chosen.** The physical story
survives; the coefficient does not.

### The knee was already measured

An inference then put the knee at **−15.3 dB** against the writer's
`_REL_KNEE_PCT = 33.0` at ~−24.8 — a 9.5 dB disagreement shaping every
sustaining program written. §71's level curve settles it without touching the
instrument: 50 % → −18.06 dB, 25 % → −28.10, 12 % → −38.13, 6 % → −48.17,
**10.04 dB per halving**, so 33 % interpolates to **−24.08 dB from either
neighbour, agreeing to 0.00.**

The writer is right; the inference is broken, and it rests on dB-linearity
within a segment.

> **A fit that agrees with itself and disagrees with a direct measurement of
> one of its parameters is telling you about its form, not its inputs.**

Same shape as the Rel2/4 artefact one level up: there the coefficient was an
artefact of the depth chosen, here the knee is an artefact of the form assumed.
Both times the arithmetic was perfectly self-consistent.

### Two smaller things that cost something

**A noise figure carried across programs.** ±3 % was quoted from Sangre —
sustain 0, 3.4 s decay, so its note-off level genuinely jitters with timing —
onto a program at sustain 1.0 with a 30 s decay whose four repeats give
sd 0.005 s. **The effect is 68 sigma and a borrowed conservative figure very
nearly had it reported as unconfirmed.** Erring conservative is not
automatically safe: here it would have cost a real result rather than prevented
a wrong one.

**And a table entry asserted without checking.** "8320 is an exact table entry,
so the comparison is clean on both sides" — it is not one; above 5000 ms the
step is 100 ms. The comparison survived only because 8300 is what the program
already held. Said while pressing mpc2emu about exactly that habit.

## 80. Rig hygiene: a leaked JACK client takes the machine down (2026-09-18)

s3ked wedged this machine's jackd twice in one evening and it took the rig down
for every session. The cause is worth carrying because `~/temp/k2k_fw/envrig.py`
had the identical defect and had survived a month of use.

**A constructor that raises after `activate()` leaks the client.** The rig did

    self.client.activate()                       # registered and running
    for src, dst in zip(CAPTURE, self.ins):
        self.client.connect(src, dst)            # can raise

with nothing between them. Its two *checked* failures called `close()` first,
so it read as defended — but a `connect()` that **raises** walks out with the
client registered and activated, the half-built object discarded, and **no
reference left to close it.** To jackd, a client whose owner has died and one
that is merely busy are the same thing: it keeps writing to the socket,
`jack_lsp` times out for everyone, and **killing the owning process does not
clear it.**

Verified rather than assumed, by pointing `CAPTURE` at a port that does not
exist:

    constructor failed as intended: JackErrorCode: Error connecting ...
    ports still registered by the failed client: none -- no leak

### Catch `BaseException`, and the reason the wrong version survives

The error that path actually raises is `JackErrorCode`, which **is** an
`Exception`. So `except Exception` handles every failure anyone meets while
testing, and fails only on `KeyboardInterrupt` or `SystemExit` — a harness
timeout, a Ctrl-C, a hung probe — **which is exactly how this failure arrives.**

> **A guard that is correct against every observed failure and wrong against
> the unobserved one is indistinguishable from a correct guard** — until the
> day it isn't.

Teardown also needs `getattr` guards, because it now runs from the
constructor's own failure path where `self.out` does not exist yet: an
`AttributeError` there would abandon the client *and* mask the original error.

### Two more of the same family

**An unbounded queue.** `capture()` set the enqueue flag with no `try/finally`,
so a timeout mid-capture left the RT callback appending until memory ran out.
Now `finally`-guarded, and it sends **all-notes-off on every exit path
including the failing one** — a note left sounding reads as a noise floor on
the *next* run, which cost a whole measurement on 2026-09-04.

**No xrun detection**, and this one reaches work already reported. A dropout
silently **shortens** a capture, and §71's release span, §73's envelope-time
law and §76's velocity law are all timings that assume contiguous frames. None
is withdrawn — four repeats at identical settings gave sd 0.005 s — but the
distinction matters:

> **"the repeats agreed" is weaker evidence than "no xruns occurred".**

Repeats agreeing rules out *random* dropouts. It says nothing about a dropout
that recurs at the same point in every capture, which would be perfectly
repeatable and perfectly wrong. There is now a counter and a per-capture
warning.

### Protocol

**Say `RIG IS MINE` before touching audio or MIDI, `RIG IS FREE` when done,
including on failure.** Adopted after s3ked's three collisions in one day —
this session had been running long unattended captures all week and announcing
nothing, which is the same exposure that simply had not collided yet.

## 81. The decay has the release's bug, and the sample is in both machines (2026-09-19)

§79 fixed the release. The **decay** carries the same seconds-versus-span error,
and three separate release investigations that evening walked straight past it.

At **sustain 0** what falls during the held note is the decay, not the release.
Against the MPC source, time to fall 30 dB:

    source 1.53 s     E4XT 1.38     AKAI 1.39     K2000 0.80

The encoded value is not the problem: the bank holds Dec1 **3.36 s** against the
source's 3.3508, correct to 0.3 %. The source's decay reaches −30 dB at 1.53 s,
implying a span of **65.7 dB**; those seconds are then written to a machine
whose decay crosses **99.37 dB**.

### The exemption was stated, and that is why nobody re-checked it

eosed's note read: *"the DECAY deliberately gets no such field: it ends at the
sustain level, which both machines agree on, so its seconds are sound."* **That
is correct for sustain > 0 and wrong at sustain 0**, where the decay ends at
silence and inherits the release's problem exactly:

    sustain 0.00  ->  0.52x   WRONG
    sustain 0.63  ->  0.99x   correct
    sustain 1.00  ->  never falls 30 dB while held

> **An unstated precondition invites a check; a stated deliberate choice
> forbids one.** (mpc2emu's formulation, and the best sentence of the week.)

The word doing the damage is *deliberately* — it records that the exemption was
considered and chosen. Same family as §80's guard that is correct against every
observed failure, and §78's constants whose **scope** was wrong rather than
their value. **Three of that night's four findings were in things already
written down, all of them written carefully.**

**And the method note is the durable part:** every release protocol measures the
fall AFTER note-off, and at sustain 0 the decay falls BEFORE it — inside the
part of the capture everyone discards as "the held note". **The bug was in the
data being thrown away**, so the discard rule was where to look, not the
analysis.

### Output is sample x envelope, so the dB rates ADD

A sweep of Dec1 bent hard — slope 0.122 s per 1000 ms on the first leg, 0.065
on the second — and mpc2emu read the saturation as the sample's own contour
setting a floor, noting a contradiction: the K2000 at 1.14 s was *faster* than
the MPC's 1.55 two seconds of Dec1 past where it should have stopped mattering.

**The sign was backwards.** Output is sample x envelope, so in dB the two falls
**add**: a decaying sample makes the total fall FASTER, never slower. The
sample's own 30 dB time is an **upper bound** on t30 — the asymptote approached
as Dec1 grows and the envelope stops contributing. Both machines sitting below
it is expected, not anomalous.

That turned the next capture into a prediction: if both machines play the same
contour, the MPC's 1.55 s is itself bounded by the sample's time, so the K2000's
asymptote is **at least 1.55 and the target is reachable.** Measured at Dec1
13000: **1.40 s, still climbing.**

    Dec1(s)  t30(s)   envelope   implied SAMPLE rate
     3.36    0.81      29.57         7.46 dB/s
     5.00    1.01      19.87         9.83
     7.00    1.14      14.20        12.12
    13.00    1.40       7.64        13.78

    asymptote ~2.18 s; target 1.55 is below it, so reachable
    Dec1 needed ~17.8 s = 5.3x the source's 3.35 s

**The implied sample rate is not constant (7.5 → 13.8), which a pure product
model requires.** It converges rather than drifts, so the envelope term
`99.37/Dec1` is the approximate part rather than the sample term — and 2.18 s is
worth "about two seconds", not three digits.

### What the fix should match — and why no constant was derived

If the fixed component and the bend are both the sample, and **the sample is in
both machines**, then fitting Dec1 until the totals match is compensating an
envelope for material the other machine already has. The quantity that should
match is each machine's **envelope contribution**, `30/t30 − rate_sample`.
Testable the moment anyone varies the MPC's decay — which needs Jan at the MPC,
since that capture only ever existed at one setting.

**mpc2emu declined to write 5.3x into the converter**, on one program, one
sample, and a model whose own residual drifts 85 %. That is the release
factor's mistake in a new stage: right on its calibration program, wrong on the
next.

> **Recorded as: reachable, ~5x, method understood, constant not derived.**
> A better place to stop than a number.

## 82. Dec1 is a time-to-target, and a settle criterion that read long (2026-09-19)

§81 left the decay conversion with a method but no constant. The missing piece
was whether `Dec1` is a **time** (reach the target in Dec1 seconds, whatever the
span) or a **rate** (a fixed dB/s, so the time scales with the span). A scalar
conversion is only safe if it is a time.

### The subject had to be proven before it could be used

Jan loaded CUTCAL to 600ff, giving `CalNoise` — the material class mpc2emu had
measured the MPC on. Program 600 was **not** usable as-is:

* its F1 is a 4-pole lowpass at **58 Hz** (it is `CUT 000`, the bottom of the
  ladder), which removes essentially all of a noise source;
* its AMPENV carries **loop byte 3** — §45's "sustained" came from a **looping
  envelope**, which is exactly what a decay measurement must not have.

So `620 NOISFLAT`: a copy with the filter opened to 25088 Hz, the loop Off, and
a flat held envelope. **Then the material was checked rather than assumed**,
because if the flatness had come from the loop, turning it off would leave a
decaying subject — the contamination that produced §81's wrong 5.3x:

    held note, loop OFF, 0.6-6.0 s:  mean -24.68 dBFS, drift 0.00 dB, sd 0.098

### Fix the time, vary the target

With `Dec1` fixed at 4000 ms and only its target LEVEL varied, the two readings
do not overlap — and the spans come from §71's level curve, so they were
predicted before the captures:

    target    span      TIME predicts    RATE predicts
     50 %   18.06 dB        4.0 s           0.72 s
     25 %   28.10 dB        4.0 s           1.13 s
      0 %   99.37 dB        4.0 s           4.0 s   <- not discriminating alone

**Measured 4.38 s and 4.59 s. Time machine, decisively.**

### The residual was the criterion, not the machine

4.38 → 4.59 as the span grew looked like `t = Dec1 + 0.021·span`, which at full
span predicts 6.09 s against 4.00 — a 50 % error at exactly the sustain-0 end
where the conversion has to live. mpc2emu declared both numbers before the last
capture.

**The 0 % point is not the same experiment as the other two**: 50 % and 25 %
land on a plateau, 0 % lands on *silence*, so a settle criterion fires when the
fall reaches the noise floor rather than when the envelope arrives. That biases
the reading **long** — toward confirming the residual. Flagged before the
number, with the alternative of fitting the straight part instead.

Refitted that way, window −5 to −50 dB with its lowest point still 23.4 dB
above the floor:

    target   span     slope dB/s    span/slope
     50 %   18.18      4.504          4.036 s
     25 %   27.96      7.015          3.986 s
      0 %   99.37     25.167          3.948 s

**3.95 to 4.04 s against a nominal 4000 ms, flat across a 5.5x range of span.**
The drift was the criterion firing late as the envelope approached its plateau
asymptotically — and it had been biting at **all three** points, not only at
0 % as expected.

> Run on the settle criterion alone, 0 % would have read near 6 s and
> **confirmed the residual, with r² and a straight line behind it.**

### Three independent checks that came free

Multiplying each slope by the nominal 4.0 s recovers the span by a route
sharing nothing with how these constants were originally measured — noise
source, slope fit, different session, different analysis:

    50 %   18.02 dB   against §71's  18.06   (0.2 %)
    25 %   28.06 dB   against §71's  28.10   (0.14 %)
     0 %  100.67 dB   against §71's  99.80   (0.9 %)  and mpc2emu's 99.37 (1.3 %)

§71's AMPENV level curve is confirmed three times over, and the release span
gets its **first independent check** — the constant a conversion was about to
be written against.

### Two things about how numbers go wrong

**A table whose rows measure different quantities reads as a trend.** "Sustain
0 → 0.52x wrong, sustain 0.63 → 0.99x correct" looked like a clean gated
pattern and named the whole investigation. But at sustain 0.63 the envelope's
span is ~4 dB, so a 30 dB fall is mostly the **sample** — one row measures the
envelope and the other measures the material. Neither number is wrong. Putting
them in one table made them a trend.

**A stored figure is a snapshot of a chain that can change; one computed at the
moment of use cannot go stale.** mpc2emu twice reported program 304 sitting at
Dec1 13000 ms when a live DUMP said 3360 — traced to a **conversation
compaction** carrying it forward as a fact, true when written. A summary is the
most dangerous kind of cache because it reads as memory rather than as a cached
value. §77's reading of §58 as corroboration is the same failure with a live
instrument standing right there.
