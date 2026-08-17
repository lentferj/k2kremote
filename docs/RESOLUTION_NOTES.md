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
either side. It captured only noise: the K2000's outputs are not routed there.

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
