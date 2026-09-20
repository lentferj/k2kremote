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
`system:capture_17/18`, hold a note, fire panic mid-sustain, compare RMS.

**Correction (2026-08-17):** the claim that the K2000 is not routed to those ports
was wrong — measured, it is there at -28.7 / -31.3 dBFS with notes playing, some
45 dB above any other pair. `p13`'s `CAPTURE` constant needs no change. The probe
stays closed on its own merits (a person at the desk gets the same answer in ten
seconds by holding a note and pressing panic), but it is no longer blocked, and
the audio path it needed is available for measurement work. It could never run unattended in CI either, since it needs a physical
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

## `k2kmon learn` — the one inspector mode not verified on hardware

**Status:** implemented; `watch`, `ask`, `read`, `compare` and `types` were all
exercised against the K2000R on 2026-08-17 (ALLTEXT round trip 127.3 ms, `read`
538 ms for a 722-byte object). `learn` ran cleanly and reported **0 events**,
which is the correct output for this rig rather than a pass: `XMIT Bttns` is
**Off** on the MIDI TRANSMIT page, so the instrument transmits no panel events.
**Blocked on:** enabling `XMIT Bttns` — a change to the owner's instrument
configuration, so not done unasked — then pressing a few buttons and the wheel and
confirming each is named, including that a wheel turn reads as `wheel +n` and not
as its filler button field. **Why it matters:** `learn` exists precisely so panel
behaviour is read from the device instead of inferred from keypress counts, which
is how this project got a soft-key cycle one short and a cursor two fields off.

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

## Never overwrite a macro on disk — RENAME the existing file first

**Status:** open, requested 2026-08-18. Before writing a macro to disk, rename
whatever is already there (`BOOT.MAC` → `BOOT.BAK`, then `.BK2`, `.BK3`, … if that
is taken), so a save can never destroy the previous version. Applies to both the
online and the offline path.

**Rename, not copy** — and that distinction is what makes it cheap. A rename edits
only the **name field of the directory entry**: no cluster is allocated, no
directory entry is created, and the FAT is never written. That is the same class of
operation `k2write` already performs when it updates the 4-byte size field in that
record, so it fits its safety model instead of breaking it. (An earlier note here
claimed this needed FAT writes; that was about *copying* to a new file, which is a
different and riskier thing nobody asked for.)

**The instrument can do it itself** — verified 2026-08-18: Disk mode's **third**
soft-key page is `<more  Rename  Move  Util  NewDir  more>`. So the online flow is
entirely device-side, with no host filesystem access at all:

1. `k2kmacli push` the new table into RAM (done, verified);
2. Disk → `Rename` → pick `BOOT.MAC` → new name `BOOT.BAK`;
3. Disk → `Save` → the macro → name it `BOOT.MAC`.

Steps 2 and 3 need panel automation, and both involve the **naming dialog** — which
means the multi-tap alphanumeric entry this project already has machinery for
(feedback-driven name entry, `NameCursor`). That is the real work here, not the
renaming.

**Decided 2026-08-18: generations go in a `\BACKUP\` directory, named
`BOOT.BAK`, `BOOT.BK2`, `BOOT.BK3`, …** — first free name in the series wins, so one
operation per save and older generations keep stable names. A directory also keeps
the root uncluttered and makes the set obvious to a human at the panel.

Naming must stay **8.3**: `BOOT.MAC.BAK` is not a valid FAT16 short name (one
extension, three characters), and reading it back would need VFAT long-name entries
`k2image` does not implement. `BOOT.BAK` and friends fit.

Implementation notes for whoever builds it:

* `NewDir` is on the same soft-key page as `Rename`, so creating `\BACKUP\` when it
  is absent needs no extra route — but it must be **checked for** first, since
  creating it twice is an error path nobody wants mid-save.
* `Rename` and `Move` are **separate** soft keys. Getting a file into
  `\BACKUP\BOOT.BAK` is therefore two operations (rename in place, then move), and
  the order matters: rename first, so a half-finished sequence leaves the old macro
  under a distinct name rather than two files claiming to be `BOOT.MAC`.
* Because a `.BAK` is not a `.MAC`, the K2000's Load page filters it out of the
  macro list. That is fine for storage, but a **restore** means renaming it back
  first — worth saying in whatever UI offers this, so a backup does not look
  unusable at the moment someone needs it.

## Online save: honour a typed path, or show the target directory

**Status:** open, raised 2026-08-18. `k2kremote`'s macro save takes a bare 8.3
stem and writes into **whatever directory the instrument is currently in**. A
typed path is refused rather than trimmed — `\BOOT` plainly means "BOOT.MAC in
the root", and silently dropping the backslash would save it wherever the current
directory happened to be, which browsing moves.

Refusing is honest but unhelpful. Two ways to do better, in order of effort:

1. **Show the destination.** The Disk page carries `Path = \…`, so the save
   prompt could read it and say "will write `BOOT.MAC` into `\-EPIANOS\`" before
   anything is typed. Cheap, and removes the surprise without new panel driving.
2. **Honour the path.** `\BOOT` would navigate to the root first. The pieces
   exist — `disk_browse.root()` / `enter()` set the current directory as a side
   effect, and the save's own directory prompt has a `Change` soft key that has
   not been mapped. Needs the same closed-loop verification as everything else
   here: assert the directory *before* committing, never infer it.

Until then the save reports where the file landed rather than only its name, so
a surprise is at least visible afterwards.

## Name entry — cursor homing added; alpha dialling is NOT the general answer

**Status:** the immediate bug is **fixed and verified on hardware** (2026-08-18).
`text_entry.home_cursor()` drives the cursor to offset 0 with `CursorLeft`, which
clamps at the field start, so `type_name` can be called with a truthful
`start_col=0` on any dialog. Typing `TESTMAC` over a pre-filled `ORG_E1` now
produces exactly `TESTMAC`.

`type_name` itself was **not** wrong. Both the object Name dialog and the Disk save
dialog use the same model it implements — each number key selects a 3-letter group,
the letter replaces the character under the cursor, the cursor does not advance.
The earlier `WSDSS` came from passing `start_col=0` when `Delete` presses had parked
the cursor at offset 1, so every character was written one column right of where it
was verified. See RESOLUTION_NOTES §25.

**Researched: alpha dialling is not how naming should normally be done.**

* **Objects — do not dial at all.** `Change` (0x08) sets a name over SysEx in one
  message; the `Ctrl+o` tool already does this. Third-party tools take the same
  route (Kurzweil Kruiser types object names from a computer keyboard over MIDI),
  so this is the established approach rather than ours alone.
* **Files — dialling is unavoidable for a genuinely new name.** The protocol has no
  filesystem messages at all, so nothing can pass a filename. But it is often
  avoidable in practice: `Choose` picks an **existing** filename from a browser with
  no typing, and the field arrives pre-filled with a content-derived default.
* **Most of the time no filename is needed.** `push` + `LoadMacro` executes a macro
  straight from RAM — Kurzweil's own documented technique for sequencer-driven macro
  loading. Saving is only for persistence across power-off.

**Still open:**

* Wire `home_cursor` into the callers that type into dialogs, and decide whether
  `type_name` should home by default (it cannot always: some callers legitimately
  continue from a known offset, which is why `start_col` exists).
* A `save_macro_as(name)` helper for `k2kmaced`, which must **read `CurrentDisk`
  first** — a browser excursion silently repoints it and the save prompt does not
  show the drive (§25). This is what makes the `\BACKUP\` scheme buildable.
* `Delete`'s browser does not respond to the alpha wheel; use `CursorDown`.

## A SysEx disk/object tool instead of screen-scraping (browse, load, rename, delete)

**Status:** open idea, recorded 2026-08-18. Attractive because everything driven
through the panel today is press-counting against a screen, and `k2kmon`/§24 showed
how many ways that misreads. But the protocol splits the request in two, and only
one half is available.

**Chapter 30's message set addresses the OBJECT DATABASE, not the filesystem.**
The complete set is `Dump Load DACK DNAK Dir Info New Del Change Write Read
ReadBank DirBank EndOfBank DelBank MoveBank LoadMacro MacroDone Panel AllText
ParameterValue ParameterName GetGraphics ScreenReply`. Note `Dir` and `DirBank`
list **objects by type and id**, not files — there is **no** message to list a
directory, rename a file, delete a file, or load one by name.

### What IS possible over SysEx today (no screen, no press-counting)

| Want | Message | Notes |
|---|---|---|
| browse what is resident | `DirBank` 0x0C | bank 0–9, or **127 for all banks** in one sweep |
| one object's metadata | `Dir` 0x04 → `Info` | type, id, name, size, RAM/ROM |
| rename | `Change` 0x08 | already shipped as the `Ctrl+o` tool |
| relocate / renumber | `Change` 0x08 (new id) | untested for repaint behaviour |
| delete | `Del` 0x07 | and `DelBank` 0x0E for whole banks |
| move a bank | `MoveBank` 0x0F | |
| read / replace an object | `Read` 0x0A / `Write` 0x09 | ~0.5 s per object |

That is a complete **object manager** with no panel involvement — worth building,
and it subsumes the F11 "master functions" item above.

### Loading a FILE over SysEx — possible, indirectly, and now cheap

There is no "load file X" message, but there is a two-step route that tonight's
work makes practical:

1. `k2kmacli push` a **one-entry macro** naming the drive, path, file, bank and
   mode (verified working, and read-back checked);
2. send `LoadMacro` (0x10), which replays *the macro currently in RAM*.

The earlier objection to `LoadMacro` — that RAM might hold something unexpected,
making it a wipe followed by an unknown load — is exactly what `push` removes: you
write the macro you want first and verify it came back. **And `MacroDone` (0x11)
acknowledges completion with a status code**, which the panel route does not: the
2026-08-17 load had to be waited out blind for five minutes and then inspected. A
load with a completion signal is strictly better.

Care: a macro entry with bank *Everything* + *Overwrite* is the documented
memory-clearing trick. A single `Fill` entry loads without wiping.

### What still needs the panel

Browsing, renaming and deleting **files** — the protocol simply has no messages for
them. Options, none free:

* **Panel automation with screen reads.** Works (the 2026-08-17 disk browse and
  load did exactly this), but it is press-counting; and note the *Disk → Macro →
  Modify* page cannot be verified at all, because 0x17 reports `CurrentDisk` for
  every cursor position there (§24).
* **Read the image offline** via `k2kmaced.k2image`, which needs the card out of
  the instrument — the very thing the online route exists to avoid.

So a realistic tool is: **object operations over SysEx, file loading via
push + LoadMacro, and file browsing left to the offline image reader** — rather
than one uniform SysEx disk tool, which the protocol does not permit.

## "Delete object with dependents" (F11) — not planned

**Status:** open, **low priority / high effort / low gain / error-prone.** `Del`
(0x07) has no recurse flag (only `type`+`idno`), and `Info` exposes no dependent
list, so a "delete a Program and the keymaps/samples it uses" option would mean
RE'ing the object structures (`Dump`/`Read` a Program, parse referenced Keymap IDs,
then each Keymap's Sample IDs — dependents usually live in other banks). That is a
lot of fragile reverse-engineering for a case the front-panel menu already covers,
so it is deliberately **not** built. Revisit only if a real need appears.

## k2kmaced (macro editor) — VERIFIED ON HARDWARE; only the MIDI half is left

**Status:** **verified on real hardware 2026-08-17** with Jan at the machine, on
his own 2 GB image and K2000R. Requested 2026-08-02; shipped as its own program
(`k2kmaced` / `k2kmacli`), rebased onto `main` 2026-08-17.

**What was exercised on hardware**, so the claim is auditable rather than a
blanket tick:

* **read** — the real `\BOOT.MAC` off the card: 19 entries, 868 bytes, OS v3.87,
  and all 19 referenced files confirmed present on that disk;
* **browse (`f`)** — against the real disk: 390 loadable files across 36
  directories, walked by directory, and an entry repointed by picking a file
  from `\-AFRICA\`;
* **edit + save** — a 20th entry added and written to a new `.MAC` (908 bytes);
* **write back into the image** — twice. First a round-trip of the unmodified
  macro, which left the image **byte-identical** across all four regions the code
  can reach (boot sector, FAT, directory record, target cluster). Then a
  one-field change (`--rebank 2=900`), after which only the target cluster moved;
* **the instrument** — the K2000 recognised the disk, found `BOOT.MAC`, and
  loaded it to completion. DIRBANK then reported bank 300 empty and its 75
  programs in 900, which is exactly the edit, since entry 2 was 300's only
  source. Restored to bank 300 afterwards, verified byte-identical (md5
  `9202448d…`).

Two risks, cleared separately — Jan's distinction and the sharper one: a bad
macro is a bad boot, but a **corrupted volume means the disk is not recognised at
all**, and nothing host-side can tell them apart. The K2000's own FAT
implementation shares no code with our writer, which is what makes "the disk was
still recognisable" the first non-circular check of this write path (the
in-process verification reads back through `k2image`, the same code that decided
where to write).

* **install from the TUI** (`w` -> `i` -> arm -> fire) — done by Jan on the same
  card: it wrote his 20-entry edit (908 bytes) into the image, and the image
  booted. Both write routes, CLI and TUI, are therefore hardware-verified.

Nothing about the disk route is left open.

A `.MAC` is the K2000's macro — a list of "load this file, into that bank, in
this mode". `BOOT.MAC` on the startup drive is what the machine replays at
power-on, so it is the file that decides what is resident. Editing it today
means the front panel or a hex editor.

**Done (offline, no K2000 touched):** the format is reverse-engineered and
documented in [`docs/MAC_FORMAT.md`](docs/MAC_FORMAT.md); `k2kmaced/macfile.py`
reads/edits/writes macros (the real `BOOT.MAC` round-trips byte-exactly),
`k2kmaced/k2image.py` reads K2000 FAT16 disk images (raw and `.lzo`)
read-only, `k2kmaced/k2write.py` is the one write direction (in-place, existing
file, never the FAT), `k2kmacli` lists / checks / edits / builds / installs
macros from either source, and **`k2kmaced`** is the standalone TUI editor —
its own program and its own console script, shipped with k2kremote but never
opening a MIDI port. `k2kmaced/mpc2emu_link.py` picks up the sibling mpc2emu
checkout when present.

**Why two programs rather than one (2026-08-17):** the K2000's disk *is* its
SD/CF card on a modern setup, so editing `BOOT.MAC` means the instrument is off
with its disk in the computer, while the mirror needs it on and answering. A
macro pane inside the mirror would be unreachable exactly when it is wanted. Same
repo, though: a future *online* macro editor (read/write the live Macro Table over
MIDI) needs both halves at once.

**Still blocked — the MIDI half only.** The disk route above is done; what
remains needs the instrument *on*, which is the opposite configuration:

1. **Live macro table.** `MidiBridge.read_macro_table()` dumps object type
   100 / id 35, but `DUMP` returns the K2000's *RAM* layout, which for programs
   and keymaps differs from the disk layout — unknown whether the Macro Table's
   two layouts coincide. **No longer blocked on permission** (ports were used
   freely on 2026-08-17); blocked on a session with the instrument on *and* a
   populated Macro Table — Macro Record has to have been on for the table to hold
   anything, so it needs setting up at the panel first. `probes/p30_macro_dump.py`
   is written and ready.
2. **Drive and mode codes.** Decoded as 0-based indices into the manual's value
   lists; three offline checks agree, but only one real `.MAC` exists to check
   against. Blocked on: saving a `.MAC` per drive/mode from the front panel.
3. **Object lists.** An entry that loads *selected* objects from a file is
   longer than the modelled layout; the surplus is preserved verbatim but not
   decoded. Blocked on: recording one such entry.

**Still to build:** editing an entry's *path/filename* (the editor cycles
drive/bank/mode and reorders, but a new file has to come from `k2kmacli new`),
and writing a macro back to the device.

A bad edit is a bad boot, so writes stay conservative. Nothing is ever sent to
the K2000. **One** command writes into a disk image — `k2kmacli install`
(2026-08-17) — and it is deliberately the narrowest operation that completes the
workflow (**verified on real hardware 2026-08-17** — see RESOLUTION_NOTES: the disk stayed recognisable to the K2000 and an edited macro loaded to the bank it named): it overwrites a file that already exists, only within the clusters that
file already owns, so **the FAT is never written to** and no directory record is
ever added. It refuses to grow a file, refuses a non-macro, refuses a `.lzo`
(k2image reads those via a temp copy, so the write would be silently discarded),
demands a typed `overwrite`, and reads the file back to confirm. It makes no
backup — that is on the user, and the README says so loudly.

Still open: writing a macro back to the **device** over MIDI. Worth more than it
first appeared, and for a reason only visible from using the disk route
(2026-08-17): on a modern setup the K2000's disk *is* an SD/CF card, so editing
`BOOT.MAC` means **powering the instrument down and taking its disk out**. The
whole edit happens with no K2000 to check against, and the card shuffle is the
slow, error-prone part — not the editing.

The MIDI route would avoid all of it: send the Macro Table object into RAM with
the machine running and the card in place, then let the K2000 save its own
`BOOT.MAC` through Disk → `Macro`. No filesystem writing, no power cycle, and the
instrument itself does the formatting.

**The layout question is now ANSWERED (2026-08-17/18), and favourably.** The live
object at **type 100, id 35** reads back as `name='Macro'`, 814 bytes, and is
**byte-for-byte the `.MAC` file's object block** at offset 48;
`macfile.MacroTable.parse` reads it and `serialize()` returns it unchanged. So RAM
and disk layouts coincide for the Macro Table, and no separate parser is needed
for either direction. Both transports agree too (`Read`/Nibblized and
`DUMP`/BitStream returned identical bytes) after the bit-alignment fix in
RESOLUTION_NOTES §23.

Two traps found while establishing that:

* **Type 100 is the *Table* type, not "the macro type".** id 16 is `Master`
  (524 B), other ids hold further tables. Every one returns a plausible-looking
  object, so a wrong id gives you data, not an error — reading id 1 produced 964
  bytes that were briefly taken as evidence the macro table was unreadable.
* `Func:MACRO` showing `[ Off ]` does **not** prevent the read. Off disables
  *recording*, not the object.

**Staged plan (2026-08-18).** Full rationale and the panel measurements behind it
in RESOLUTION_NOTES §24.

| Stage | What | Risk | Status |
|---|---|---|---|
| 1 | Read the live table; diff it against a `.MAC` | none — read-only | **done**: `k2kmacli live` / `k2kmacli diff` |
| 3 | Write the table over MIDI; the K2000 saves it itself | moderate | **done and hardware-verified**: `k2kmacli push` |
| 2 | Trigger a macro load from the computer | destructive | **proven manually**, not implemented — now only a convenience |

Stage 3 removes the card shuffle entirely, and is **done**: pushed a one-field
change, read it back byte-identical, confirmed it on the instrument's own Macro
page, then restored the original byte-exactly. It required fixing the data-field
**encoder** first — `client.write` transmits bit-stream, which was mis-packed, so
writing *any* object would have corrupted it (RESOLUTION_NOTES §24).

**Also: the instrument can save the macro under any filename**, so the persist step
never needs to overwrite a working `BOOT.MAC` — push, save as `TEST.MAC`, try it
with Disk → Load, promote it when it works.

**Do not** drive the `Disk → Macro → Modify` page with counted presses: SysEx 0x17
returns `'CurrentDisk'` for every cursor position on that page, so the cursor is
**not readable** there and the check that makes `p39` safe is unavailable. The
object route avoids the question.

Note the same observation makes *reading* the live Macro Table a **different use
case** rather than part of this workflow: when you want to edit `BOOT.MAC` the
machine is off, so a live read cannot help you there. It is for inspecting what a
running machine has loaded.

Procedures and evidence: RESOLUTION_NOTES §21.

### Next session — pick up here

Branch `mac-editor`, 9 commits, rebased onto `main` 2026-08-17, **not
pushed**, not merged. `.venv/bin/python -m pytest` = 321 passing (one skip,
`test_k2image.py`, when the sibling `../mpc2emu` checkout is absent).

The three probes were **renumbered** in the rebase: `p24`/`p25`/`p26` on this
branch collided with unrelated probes of the same numbers added to `main`
since the fork, and are now `p30_macro_dump.py`, `p31_macro_codes.py` and
`p32_macro_objlist.py`. The MAC notes moved from RESOLUTION_NOTES §13 (taken
by the snappier-mirror section) to §21.

Offline, can be done any time:

- [x] **Write the three probe scripts** — done 2026-08-02:
      `probes/p30_macro_dump.py` (the only one that opens a MIDI port, and only
      to read), `p31_macro_codes.py` and `p32_macro_objlist.py` (pure file
      analysis; the K2000 work for those two is front-panel only). Each script's
      docstring is the step-by-step for the device.
- [x] **Edit an entry's path/filename in the editor** — done 2026-08-02:
      `e` opens a path overlay (host-style `/` and a missing leading `\` are
      accepted; anything the K2000 could not load is refused and the overlay
      stays open), `f` picks from the image's loadable files when `--image` was
      given, `a` adds an entry inheriting its neighbour's bank/mode/drive.
- [ ] **Decide whether to push/merge** `mac-editor`, or keep it out of `main`
      until the hardware checks land.

Needs the K2000 (ask first — the 2026-08-02 session was explicitly told not to
touch it):

- [ ] **Run p24** — does `DUMP` of type 100 / id 35 return the same layout as
      the disk file? Settles whether the app can read the live macro list. Pause
      the mirror first (§9).
- [ ] **Run p25** — confirm or replace the drive/mode code table in
      MAC_FORMAT.md §5. Until this passes, every `.MAC` this project writes is
      unverified.
- [ ] **Run p26** — decode a macro entry carrying a selected-object list, the
      one part of the format still opaque.
- [ ] **Then**: fold the results into `docs/MAC_FORMAT.md` (drop the §5 hedge),
      and only afterwards consider a write-to-device path, gated like the F11
      tool.

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

## Name-entry failures now raise — verified live, not noisy — RESOLVED

**Status:** **verified on hardware 2026-08-17** with Jan at the panel. Both
multi-tap branches in `type_name` used to give up quietly and leave a garbled
name on the device while reporting success; they now raise `NameEntryFailed`, and
the `Ctrl+O` rename tool keeps its dialog open when the INFO reply carries a name
different from the one asked for.

Both questions are answered:

* ~~Does a real multi-tap ever need more presses than the ring plus one reset?~~
  **No** (`probes/p29_multitap_budget.py`): 23 characters, ~97 pad presses,
  **nothing over budget and nothing raised**. Digit *n* costs exactly *n*+1
  presses; the worst cases are `'9'` at 10 of 11 and the third-position letters
  at 3 of 4, so the tight margin is **one spare press**. A single dropped press
  is therefore absorbed silently; two within one character would raise. No drop
  was observed at all, so the raise is a genuine last resort rather than a
  routine event, and the retry does *not* need to move inside `_type_char`.
* ~~Does the K2000 pad a stored name with trailing blanks?~~ **Answered
  2026-08-17** (`probes/p28_name_padding.py`, read-only): **it does not pad.**
  INFO returns the name exactly as stored, verified across lengths 3, 4 and a
  full 16 (`'VZ1'`, `'FGTH'`, `'Cymb.SoftMallet1'`). The comparison's `rstrip` is
  a no-op, so the check is exact and cannot false-alarm on short names.

See RESOLUTION_NOTES §20.
## README screenshots: one of five still predates the August UI work

**Status:** open, cosmetic. `braille`, `blocks/quad`, `blocks/half` and `text`
were regenerated 2026-08-17 from real captured frames and show the current chrome
(aligned soft keys, grouped legend). Two fixtures are checked in:
`docs/fixtures/frame.json` (Program Mode, for the pixel modes) and
`frame-text.json` (Master object database — eight dense rows, which is what text
mode is for). Regenerate with:

    .venv/bin/python docs/make_mirror_screenshots.py

One is still from the initial release, 2026-06-21:

* **`mirror-image.png`** — cannot be automated at all: image mode hands pixels to
  the terminal's graphics protocol, so nothing lands in the character grid to
  export as SVG. It has to be a photograph of a real kitty window; the recipe is
  in `docs/make_mirror_screenshots.py --image-help`.

And one file is not regenerable:

* **`rename-tool.svg`** — the last SVG in the README, from the initial release,
  with no generator and needing a live rename dialog. Lower risk than the mirror
  shots (box-drawing and ASCII rather than braille), but it is the one remaining
  image whose glyphs depend on the viewer's fonts. Worth folding into a generator
  next time the rename tool is touched.

**On the content of `frame-text.json`:** it shows object names from a commercial
bank the author owns and has licensed, published in this repository with his
explicit authorisation. Note the deliberate asymmetry with the k2kmaced
screenshots, which are built from a *synthetic* image with invented names — those
would have shown a whole disk's directory structure, which is a different
exposure from one screen of one owned bank. If that distinction ever stops feeling
right, the fix is to recapture from a factory-object range, which needs no code
change.

The lesson worth keeping: these went two months stale because they were shot by
hand and nothing tied them to the code. Three of the five are now regenerable by
one command from a checked-in frame, which is why they were the ones fixed first.

## ALLTEXT can confidently report blank on a populated field

**Status:** open, not root-caused. Blocked on: reproducing it — it appeared
once, mid-session, correlated with (not demonstrated to be caused by) a Gotek
disk-image reload, and was not retested afterward.

`get_screen_text()` (ALLTEXT, `0x15`) returned the `ProgramMode` header and the
soft-key row correctly, but the `<id> <name>` field between them came back as
spaces while the physical LCD showed `Program 300 CUT 000` — confirmed by a
human at the panel. Everything else on the same screen read fine, both before
and after, so this is not "ALLTEXT is broken", it is one field silently wrong.

Nothing in the shipped app was affected this time only because the code paths
in use (`select_program`'s button presses, `confirm_selection`'s `0x16`/`0x17`
read) don't touch ALLTEXT — but `refresh.py`'s live mirror, the disk browser,
and the macro editor all *do* depend on it, and none of them currently
cross-check against a second read path. A wrong-but-well-formed screen read is
worse than a crash: nothing about it announces itself. See RESOLUTION_NOTES §29.

## Does a short-release envelope re-cycle under sustain?

**Status:** open, designed, not run. Blocked on: the K2000 answering at all —
it has been silent on every ESI sub-port since the 2026-09-11 reboot, with the
host side proved good (§ in RESOLUTION_NOTES; universal identity request out
and back on the same interface via the E4XT), so this is a bench check on the
instrument's power or cables.

mpc2emu's KRZ writer emits a release shape with Rel2 and Rel3 both zero in time
*and* level whenever the source release is under about 27 ms — the point where
the time quantiser stops distinguishing it from zero. Their own comment argues
that shape is unreachable, and the argument is sound in seconds and wrong in
bytes: it reasons about a float while the machine sees a quantised byte. It
affects **20.3 % of Jan's MPC corpus** (1,387 of 6,847 XPM keygroups carry
`VolumeRelease` = 0, which their law maps to 1.005 ms).

That shape is the documented trigger for their `§KRZDBLZERO`, whose symptom is
the envelope looping back to Att1 **while the key is held**.

**The test, two programs differing only in release — 5 ms and 50 ms, both held
long — and whether the short one re-cycles under sustain.** It is decisive for
a question we cannot currently separate: §64/§65 measured a full re-articulation
**1.15 s after note-off**, which is a different timing, so these may be one
mechanism or two. The test tells us which.

Does not need a card crossing; the programs can be built in RAM.

## Is the 41.7 ms re-cycle overhead per-stage or a timer?

**Status:** open, designed, not run. Blocked on the same bench check as the
short-release test above, and sits behind it — that one is about a live defect,
this is about a fixed bug's mechanism.

`period = decay + ~41.7 ms` was measured well (three points over a 25x decay
range, 0.1-1.7 %, alternatives excluded) but it characterises the seg3F loop
the old KRZ writer set by accident, which is fixed. The open question is what
the fixed overhead *is*.

mpc2emu's hypothesis: the 0.058 s subject carried **six of its seven envelope
stages at zero time**, so 41.7 ms is 6.95 ms per zero-length stage traversed
(5.96 ms if all seven cost it) — fixed regardless of decay, which is exactly
what was measured.

**The test: vary the loop flag, not the envelope.** A first design varied the
attack instead, and it could not work: "every stage costs" and "it is a timer"
both predict an unchanged 41.7 ms, so that capture could only have excluded the
middle case. The writer always emits seven `(level, time)` pairs, so the stage
*count* cannot be varied that way either.

Byte 0 of the ENV segment selects `seg1F / seg2F / seg3F` and the bidirectional
`seg1B / seg2B / seg3B`. **Those traverse different numbers of stages per cycle
by construction**, and the bidirectional settings roughly double whichever
count applies. Six subjects, identical but for that one byte:

    per-stage, all stages   period scales with the traversed count
    per-stage, zero only    scales, with a different slope
    a timer                 FLAT across all six

Flat kills the per-stage family outright; not flat, and the slope separates the
two variants — **without having to pin down what `segN` means first**, which is
the property that makes this better than the attack version.

**Those six files deliberately set the byte the old writer set by accident.
They are the bug on purpose.** Name them so they cannot be mistaken for
conversion output, and keep them out of any real path.

**Update, 2026-09-14 — the overhead is not a constant across envelope shapes.**
A `seg1F` program from mpc2emu's writer (`LOOPPOS`, off the Gotek) traverses
`Att1 0.02 + Att2 0.01 + Att3 0.01 + Dec1 0.30` = 0.34 s and re-cycles at
**2.378 Hz = 0.4205 s**, measured at 0.054 Hz bins against a peak-to-median of
6066. That is an overhead of **~80 ms**, twice the 39.8-41.7 ms measured on the
panel subject, and the difference is far outside the 0.054 Hz resolution.

Both subjects traverse four non-zero-length stages, so **the count of stages
traversed does not explain it either** — that was already refuted from the
other direction. The formula still matches to a millisecond *within* one
envelope shape (§68's sweep), so it is not simply wrong; it does not transfer.
Whatever the overhead tracks, it is neither a fixed timer nor the stage count.

The six-subject loop-flag sweep above is still the right instrument and is
still unrun — but it should now be run **on two different envelope shapes**, or
it will only re-measure one shape's constant.


## The field registry cannot hold two meanings for one offset

**Status:** open, with a concrete case in hand (§69).

Offset `210 + 16k` is the first parameter of DSP slot `k`, and what it means is
selected by the block-type byte at `209 + 16k`: on program 42 offset 242 is the
PANNER's `Adjust` in percent, and on a program whose F3 is a filter the same
offset is `Coarse` in Hz. Both are verified against the panel. `KNOWN_FIELDS`
is `Dict[(ObjectType, offset), Field]`, so it can carry exactly one of them,
and F3 already carries the panner.

§69 added a `gate` to `Field`, which is enough to stop a wrong decode but not
enough to offer the right one — a gated entry whose gate fails says "not
decoded", where it could say "this is a PANNER, here is its Adjust".

**What it needs:** the value side becomes a list of gated interpretations,
first matching gate wins, with an ungated entry allowed last as the default.
`describe_field()` picks; `monitor_tui`'s field pane and its patch modal both
key off `KNOWN_FIELDS[(type, offset)]` and would follow. Then F2/F3/F4 Coarse
can be registered beside the panner without either displacing the other.

Not urgent: the gate already prevents the confident-wrong reading, which was
the defect. This is about coverage.

## Pitch measurements below ~100 cents need a harmonic source

**Status:** open, bounded, not needed by anything current.

§73 withdrew an apparent threshold in the Src2 pitch wire because `RELREAL`'s
sample is not one harmonic series — its strongest low partials are 93 and 112
cents apart — and every pitch estimator tried assumes a single pitched source.
Three of them disagree with each other inside their own validity ranges below
about 100 cents.

**What it needs:** a program built on a genuinely harmonic source (a sine, or a
single-cycle sample) rather than a pad, then the same sweep. Nothing in the
conversion work depends on it: the byte-to-cents curve is panel-confirmed
across the full range with no audio at all, and every audio result that stands
was taken at 100 cents or more.

Do not reuse the existing captures — the problem is in the material, not the
analysis, so no amount of re-analysis will settle it.

## A positional segment helper, so a value search cannot find a tag again

**Status:** open, small, and it has already cost real data once.

Program-object segments are addressed by walking to a known position, never by
searching for a tag byte's value. A value search for `0x21` matched program
303's Rel1 **level** byte — 33 % is 0x21 — invented a second layer there, and a
write landed inside the ENV2 segment that follows (§75, §77, and the 2026-09-18
repair). mpc2emu hit the identical error read-only on the same file format
within the same hour, getting 67 hits in PCM data.

**The rule was already written down twice and broken inside a day. A rule in a
notes file protects the next reader; only an assertion in the code protects the
next run.**

**What it needs:** one helper, next to the field registry, that takes an object
type and its size and returns the segment map — for a Program, AMPENV at
`128 + 224*k` with the layer count from the size, ENV2 at `+16`, ENV3 at `+32`,
CAL at `size-96`, HOB `0x50..0x53` at `size-64` stepping 16 — **and asserts the
tag byte at every position it returns**. Every probe and script that currently
walks an object by hand uses it instead.

Two properties it must have, both from how the failure actually happened:
* it asserts rather than returns, so a wrong layout stops the run instead of
  producing a plausible offset;
* the layer count comes from the object size, not from counting matches, since
  counting matches is the bug.

## External code review (GLM-5.3-Flash) — full-repo findings

**Status:** in progress — recorded 2026-09-20. **Six findings verified by
hand and closed on 2026-09-20; one REFUTED.** Each verified finding carries a
verdict inline below. Nothing here is actioned on the review's say-so: every
claim is reproduced first, because the one refuted finding was stated with the
same confidence as the five that were real.

    R-01  CONFIRMED  fixed  --port routed to standard(); bare --rig standard refused
    R-05  CONFIRMED  fixed  short .MAC block -> MacError, not raw struct.error
    R-11  CONFIRMED  fixed  timing help interpolated from the constants
    R-12  REFUTED           the ROM table is byte-for-byte correct; see below
    R-13  CONFIRMED  fixed  type/bank inputs now validate and refresh
    R-28  CONFIRMED  fixed  (type-drift half) decode annotation widened
    R-14  CONFIRMED  fixed  one decompression per image, and off the event loop
    R-15  CONFIRMED  fixed  every host-side write goes through os.replace
    R-16  CONFIRMED  fixed  the throttle serialises its senders
    R-17  CONFIRMED  fixed  explicit timeout=0 honoured; the rest documented
    R-18  CONFIRMED  fixed  only INFO/ENDOFBANK extend the listing's quiet window
    R-19  CONFIRMED  fixed  undecodable traffic reads as a timeout, not a crash
    R-20  CONFIRMED  fixed  MoveBank type 0 + type-0 encode + truncation; 2 documented
    R-21  CONFIRMED  fixed  every port opened by name on its own client
    R-22  CONFIRMED  fixed  both workers join, and stay silent once stopping
    R-23  CONFIRMED  fixed  a write in flight refuses both Escape and a 2nd Enter
    R-24  CONFIRMED  fixed  a failed save backs out of the dialog (Cancel/Exit)
    R-25  CONFIRMED  fixed  a short listing reports complete=False
    R-26  CONFIRMED  fixed  `ask` waits for a SCREENREPLY, not for any traffic
    R-27  PART        fixed  five of six confirmed; the resume-on-cancel half REFUTED
    R-28  CONFIRMED  fixed  state read under the lock; _Command widened; `is` -> `==

Each fix has a regression test, and all three new tests were run against the
**unfixed** source as a negative control: three failures there, 536 passing
here. A test that passes against the bug it was written for tests nothing.

A complete external review of the whole tree (`k2kremote/`, `k2kmaced/`, the
vendored `k2000/`, the test suite, CI and packaging) by GLM-5.3-Flash
(Z.ai), 2026-09-20, on `main` @ `1176e8f`. Method: four parallel deep passes
over the source plus static analysis (ruff bug-rule set) and a full test run.
Baseline: **533/533 tests pass**; no `eval`/`exec`/`pickle`/`shell=True`
anywhere; repo hygiene and the CI workflow clean; static analysis finds only
21 non-test issues, all minor. Findings are numbered R-01 … R-29 for
reference. Severity is the reviewer's assessment; every claim is to be
re-verified before acting, since this review had no hardware.

### Reachable crashes / broken features

**R-01 (major) `k2kmon --port` calls methods that do not exist.**
`monitor.py:244` calls `MidiBridge.open(port)` / `MidiBridge.open_first()` —
neither exists in `midi_bridge.py` (checked repo-wide), so
`k2kmon --rig standard --port "K2000"` dies with `AttributeError` before any
cleanup. Compounding it: under the default `rig="auto"` an explicit `--port`
is silently ignored (autodetect runs anyway).
*What it needs:* route through `MidiBridge.standard(port)` / the first
bidirectional port, and make `--port` imply `standard` or error out.

**R-02 (major) two threads drain the same MIDI input queue.**
`monitor_tui.py:189-198` (`WatchScreen._poll`) calls
`bridge.client.midi_in.get_message()` on its own thread while `_DeviceWorker`
executes ops that also consume `midi_in` (`list_bank`, every
`_send_and_receive`). The invariant at `midi_bridge.py:623-625` says all input
consumption is serialized on one thread; the watch thread violates it.
Reachable from the UI (the watch modal does not suppress the `r`/`p`
bindings). Consequences: `get_message()` from two native threads on one
rtmidi port; the watcher **steals solicited replies** — a verify-read can fail
with `PatchUnverified` for a write that actually landed; replies show up
misattributed as unsolicited traffic.
*What it needs:* serialize input consumption (worker holds a lock across an
op, `_poll` skips while held), or route watch reads through
`_DeviceWorker.submit`.

**R-03 (major) write/read paths serve stale replies as this request's answer.**
`midi_bridge.py:751, 882, 922-931, 955, 963, 984` — `rename`,
`read_object_bytes`, `patch_object_bytes` (both the LOAD and the verify DUMP),
`delete_object`, `move_object`, `delete_bank` call `_send_and_receive`
without draining stale input first, although `monitor.ask`, `_read_raw` and
`list_bank` all drain, with docstrings explaining why. A late reply from an
earlier timed-out request can be consumed as this request's answer; the
vendored client also never checks that a reply's echo fields match the
request, which undermines `patch_object_bytes`' verified-read-back guarantee.
*What it needs:* a `_drain()` before every `_send_and_receive` in the bridge,
and echo validation on reads (`reply.idno == idno`, `reply.offset == offset`),
refusing rather than verifying on mismatch.

**R-04 (major) ALSA client leak on every reopen.**
`midi_bridge.py:1004-1014` — `close()` calls `_delete_quiet(raw)` only when
the port has a `_port` attribute; `ThrottledOut` (wrapped) has one, the plain
`rtmidi.MidiIn` used by the `standard`/`_connect_split` rigs does not, so its
sequencer client is never freed — every reconnect cycle leaks one
"RtMidiIn Client" (the hazard documented at lines 168-174). Same pattern on
error paths at `midi_bridge.py:369-375, 403-410, 299-309` (probe ports
abandoned on raise).
*What it needs:* `_delete_quiet` any raw rtmidi object that is not a
`MultiIn`/`ThrottledOut`; try/except around probe opens.

**R-05 (major) k2kmaced: malformed `.MAC` block size crashes with raw
`struct.error`.** `macfile.py:434-448` — the guard rejects only positive
sizes; a negative size in `[-5, -1]` yields a <6-byte block and
`struct.unpack_from(">HHH", …)` raises `struct.error`, which is in no catch
list (`cli.py:565`, `app.py:1087, 1203`). A corrupt/truncated `.MAC` gives a
traceback in the CLI and a TUI crash with unsaved work instead of the
"cannot open" status path.
*What it needs:* require `pos + 4 + 6 <= pos - blocksize`, or wrap the unpack
in `try/except struct.error → MacError`.

**R-06 (major) k2kmaced: non-latin-1 path passes validation, crashes at
save.** `app.py:351` measures the *filename* with
`encode("latin-1", errors="replace")` and never checks the *path*;
`macfile.py:281, 287` later encode strictly. A path like `\日本\FILE.KRZ` is
accepted, then `UnicodeEncodeError` escapes `action_save` (`app.py:1030`
catches only `MacError, OSError`) and escapes `action_install` entirely —
Ctrl+S crashes the TUI with unsaved work.
*What it needs:* strict-encode `directory + filename` in `set_full_path` →
`MacError`; wrap `UnicodeEncodeError` in `MacroEntry.serialize` so the
documented error type is what every caller sees.

**R-07 (major) three bridge methods still on the 1.0 s timeout the project
deliberately abandoned.** `midi_bridge.py:757, 833, 849` — `object_name`,
`read_macro_table`, `write_macro_table` use the vendored `client.dir/dump/
write`, which default to the vendored 1.0 s; `DEFAULT_TIMEOUT = 2.5` was
raised precisely because 1.0 s is too short, and `read_object_bytes`/
`patch_object_bytes` were rerouted through `_send_and_receive` for that
reason — these three were left behind. The `k2kmaced` online push path can
flake on slow interfaces.
*What it needs:* route them through
`self.client._send_and_receive(..., timeout or self.timeout)` like their
siblings.

**R-08 (major) short-but-valid ALLTEXT replies are not retried, then
`IndexError`.** `disk_browse.py:97-105`, `macro_save.py:87-101` — `_rows()`
retries only on exception, but the manual (quoted in macro_save's own
docstring) says a short reply means the screen was mid-redraw and should be
re-requested. A successful short decode then hits blind indexing (`[7]`,
`[3]`, `[0]`) and raises `IndexError` mid-panel-flow.
*What it needs:* treat `len(rows) < 8` as failure and retry inside the loop;
raise only after the tries are exhausted.

**R-09 (major) `rename()` sends unbounded, unvalidated names.**
`midi_bridge.py:748-753` — only non-ASCII is rejected; control characters
(`\n`, `\x1b`, `\x00` are all ASCII) and arbitrary lengths go to the wire
(the >16-char truncation behaviour is itself marked "Unverified on
hardware"), and the returned `info.name` is presented as device-confirmed
with no check that it matches or plausibly truncates the request — and per
R-03 it may even be stale.
*What it needs:* clamp to 16 chars, restrict to printable `0x20-0x7E`,
verify the round-tripped name.

### Major design / correctness

**R-10 process-global monkeypatch of the vendored library.**
`midi_bridge.py:133-164` — `_install_device_id_tolerance` permanently
rewrites `SysexMessage.decode`/`has_valid_k2_headers` for the whole process,
and `_normalize` rewrites byte 2 of *any* packet starting `0xF0`, mangling
non-Kurzweil `F0 7E …` universal replies before validation. The bridge
already owns the receive path (`MultiIn`), so the normalization can live
there and leave the vendored class untouched.

**R-11 help text defaults contradict the shipped constants.**
`app.py:2744-2776`, `refresh.py:104-116` — `--sysex-interval` documents
"default 150" (actual `SEND_GAP = 0.5`), `--settle` says 150 (actual 0.35 s),
`--heartbeat` says 1200 (actual 2.5 s); two help strings recommend raising
*to* values already exceeded. Comments repeat the stale numbers
(`refresh.py:107-108`, the duty-cycle prose at lines 72-75). Anyone tuning
wire timing against the lock-up risk reads wrong numbers.
*What it needs:* regenerate help/comment text from the constants and re-run
the duty-cycle measurement.

**R-12 the LFO rate prose and the ROM table disagree by ~12 bytes.**
`k2kfields.py:96-104, 213-219` vs `k2kromtables.py:94-116` — the prose says
the wheel stops at byte 184 (24.00 Hz) with 25.00 saturating from 186;
indexing the table gives `[184] = 19.20`, `[196] = 24.00`, `[197] = 24.50`,
saturation from 198. Since decoding comes from the table, either the table is
mis-transcribed (every rate in 184-197 displays wrong) or all three prose
claims are wrong. Every *other* table in the file spot-checked byte-for-byte
correct, which is why this one looks like a genuine error.
**VERDICT: REFUTED, and no hardware was needed.** The committed table is
byte-for-byte identical to the ROM at **all 256 entries** — `[184] = 24.00`,
`[185] = 24.50`, `[186] = 25.00`, saturating from 186 — which is exactly what
the prose says and exactly what §70 measured on the panel.

The reviewer's numbers are the table read **one row late**. The literal in
`k2kromtables.py` is formatted 12 values per row, and every claimed value is
the actual value 12 indices earlier:

    claimed[184] = 19.20   actual[172] = 19.20
    claimed[196] = 24.00   actual[184] = 24.00
    claimed[197] = 24.50   actual[185] = 24.50

Worth keeping for what it says about the review as a whole: this finding was
argued *from* the other tables being correct — "every other table spot-checked
byte-for-byte correct, which is why this one looks like a genuine error" — and
that reasoning made a miscount look like evidence. **A confident claim in an
audit is a claim, not a finding.**

**R-13 dead controls in the monitor TUI.** `monitor_tui.py:241-244` — the
`typeinput`/`bankinput` widgets have no submit handler anywhere; typing a new
type/bank does nothing and refresh silently keeps browsing the old type.
*What it needs:* an `on_input_submitted` handler (validate + update +
refresh) or removal.

**R-14 multi-GB `.lzo` decompression runs synchronously on the Textual event
loop — up to three times per open.** `k2kmaced/app.py:1060-1099, 425-440`,
`k2image.py:149-173` — `_open_path`, `build_editor → load_macro`, and
`scan_image` each decompress the full image; a 2 GB backup freezes the UI for
tens of seconds, recurs in `cli._cmd_check` (cli.py:378-382), and
`plan_replacement`/`replace_file_in_image` open the image again too.
*What it needs:* cache the decompressed temp path (keyed by source
path/mtime) and move the load onto a worker with an "opening…" status.

**R-15 non-atomic host-side writes.** `k2kmaced/macfile.py:505-507`
(`write_mac` truncates before serializing — exported, currently unused, the
trap is armed), `cli.py:426-427, 456-457, 250-251`, `app.py:396-402`; `-o`
with `--force` at the source path destroys the only copy on a mid-write
failure.
*What it needs:* write to `path + ".tmp"`, fsync, `os.replace` — in
`write_mac` and the CLI's `_cmd_edit`/`_cmd_new`/`_cmd_extract`.

### Minor findings (hardware/protocol)

**R-16** `ThrottledOut.send_message` (`midi_bridge.py:264-283`) has no lock;
two concurrent senders compute `wait` from the same stale `_last` and can
violate `SYSEX_FLOOR` — latent until R-02 is fixed.
**R-17** `delete_bank` (`midi_bridge.py:984`) — `timeout or 0.5` treats an
explicit `0` as missing, and treating *any* timeout as "the wipe still
happened" is unverifiable for a bank-wide delete; document or enforce a
follow-up DIRBANK check.
**R-18** `list_bank`'s quiet window (`midi_bridge.py:788-807`) resets on any
decoded message including PANEL — a finger resting on a button extends the
loop past `quiet_for`. Reset only on `Info`/`EndOfBank`.
**R-19** vendored `client.py:99-119` — corrupt replies surface as `ValueError`
at timeout instead of `TimeoutError`; `MidiBridge.is_connected`
(`midi_bridge.py:685-691`) catches only `TimeoutError`, so a
corrupt-replying device reads as a crash, not a disconnect.
**R-20** vendored gaps: `MoveBank._decode_body` (`k2000/messages.py:707`)
still raises on type 0 where `EndOfBank`/`DelBank` were patched;
`decode_data_field` (`k2000/encoding.py:134-139`) silently returns short data
on truncated replies; `Button.SoftYes/SoftNo` (`k2000/definitions.py:70-71`)
alias `SoftE/SoftF` (duplicate enum values — `client.yes()/.no()` send the
A–F codes); `EndOfBank._response_classes = [Info]` (`k2000/messages.py:639`)
makes `client._send_and_receive(DirBank…)` structurally unable to return the
terminator (worked around correctly in `list_bank` today).
**R-21** ports opened by index from a *different* object's enumeration
(`midi_bridge.py:301-307`, `:546-547`) — TOCTOU on hotplug; the name-lookup
pattern already exists in `_open_in`/`_open_out`.

### Minor findings (app/TUI)

**R-22** shutdown races on both apps: `worker.stop()` never joins
(`app.py:1949-1954` + `app.py:2825-2829`; `monitor.py:636-639`), so
`bridge.close()` in `finally` can run mid-op and callbacks target a dead
loop. Join with a short timeout; guard callbacks with a closing flag.
**R-23** Escape during an in-flight patch → double `pop_screen` and side
effects after cancel; Enter queues duplicate writes
(`monitor_tui.py:122-146`).
**R-24** `macro_save.py:268-301` — failure paths leave a modal dialog
unanswered on the instrument's screen; back out (Cancel/Exit only) before
raising, and use the `more>` label search for the overwrite prompt.
**R-25** `disk_browse.py:311-314` — a listing *shorter* than the device's own
count is returned silently (only over-long is truncated), unlike
`list_bank`'s honest `done=False`; the promised trace is never emitted.
**R-26** `monitor.ask` (`monitor.py:326-334`) accepts the first inbound
message of any type as the reply — a PANEL press during the wait is printed
as the round-trip result.
**R-27** k2kremote app: cancelling the macro-save leaves the mirror paused
with no hint (`app.py:1534-1556`, cancel branches skip `resume_mirror`),
while `_loaded` (`app.py:1086-1116`) blindly un-pauses a user's manual pause;
`MasterFunctionScreen` fires a device round-trip on *every keystroke* of the
id field (`app.py:1656-1659`), regressing the Enter/blur discipline of
`RenameObjectScreen`; `text_entry.py:285-286` raises raw `IndexError` instead
of `NameEntryFailed` on a short ALLTEXT row; `DiskBrowserScreen._done`
(`app.py:782-793`) guards falsy but not wrong-shape results (the comment
records that this class of bug took the app down once); `remembered_size`
(`app.py:262`) — `max(rows, min(least_rows, rows))` is algebraically `rows`,
a dead clamp; `entry.remove()` un-awaited (`app.py:2063`, fine on current
Textual, a coroutine on some `textual>=0.80` versions — pin or await).
**R-28** `refresh.py:521-527, 724` — the worker reads `_paused`/`_danger`/
`_commands` outside the condition lock (benign under the GIL today; one
refactor from a stale-read bug). Type drift: `k2kfields.py:58` declares
`Optional[int]` but `_lfo1_mnrate_hz` returns `Optional[str]`;
`refresh.py:239-241` `_Command` covers 2 of ~8 actual command kinds;
`is` vs `==` on string constants (`refresh.py:771` vs `:763`).

### Minor findings (k2kmaced)

**R-29** `k2kmacli edit`: out-of-range index → `IndexError` traceback and a
*negative* index silently deletes the last entry (`cli.py:399-413`); `new`
accepts an empty filename (an entry that can never load, cli.py:439-451);
`extract` overwrites without the `--force` guard its siblings have
(cli.py:250-252); the fixed default `push` backup path is clobbered on every
push (cli.py:358-360, online.py:183-186) — the recovery copy dies exactly
while iterating; `macfile.py:456` silently drops the payload on a corrupt
`osize`; `k2image.py:104-136` — no image-size/geometry validation (truncated
FAT surfaces as `struct.error`), `dd` is not `which`-checked alongside
`lzop`, decompression stderr is discarded; `is_disk_image`
(k2image.py:96-98) advertises `.iso` (never readable) but not `backup.lzo`
(readable); latent pad-byte asymmetry in the PRAM object codec for odd-length
bodies (`macfile.py:398-405` vs `:445-448`) — unreachable via the macro path
today, but the container is documented as the general `.KRZ` format.

### Static-analysis nits

21 non-test findings: 15 unused imports, 7× `zip()` without `strict=`, 2
`global` statements (`midi_bridge.py:217`), 1 `B904`
(`monitor.py:412`). Two F821s are deferred-annotation false positives
(`app.py:239`, `midi_bridge.py:760` — the latter's `Info` should live under
`TYPE_CHECKING`).

### Test-suite gaps

1. Malformed/corrupt SysEx through the *real* receive path — only one test
   touches the genuine `_send_and_receive` loop and it feeds a valid packet
   (which is why R-03's behaviour is unbested).
2. Real `poll_panel` and `ports_present` — zero direct coverage of the
   RX-drain loop and the substring matching that underpins the
   busy-vs-disconnected distinction.
3. `main()`/teardown paths — `app.main()`, unmount, and `-sysex-interval`
   clamping in `_build_bridge` are untested (the R-22 races live here).
4. The vendored client as a unit — `_send_and_receive`'s semantics
   (wrong-class replies silently discarded) only incidentally covered.
5. Monkeypatch isolation — `_install_device_id_tolerance` is never undone
   between tests; nothing asserts a non-Kurzweil packet survives
   `_normalize`.

Also: the throttle test (`tests/test_midi_bridge.py:79-84`) names a 50 ms gap
but actually tests the 120 ms floor (`SYSEX_FLOOR` clamps it), and the
refresh-burst tests retain a timing-shaped flaky edge (sleep-based negative
assertions at `tests/test_refresh.py:226-227, 305-306, 501`).

### Noted as done well (reviewer's words)

The single-owner worker with marshalled `call_from_thread` callbacks and the
ALLTEXT-as-change-detector design; every write path verifying with exact
read-back, DNAK decoding, typed confirmations and `newid=0`; tests asserting
on wire bytes with a real `BOOT.MAC` fixture round-tripped bit-exactly;
`SYSEX_FLOOR` clamped in code so no config can violate the lock-up threshold;
`k2write`'s refuse-to-grow + FAT-untouched proof + mandatory read-back; and
the measured, documented timing constants. The findings above are
concentrated in the seams — thread boundaries, error paths, and prose that
drifted from data — not in the core architecture.

### Suggested fix order (reviewer's)

1. Reachable crashes: R-01, R-05, R-06, R-08.
2. Wire data-integrity: R-03, R-07, R-09, R-02.
3. Resource lifecycle: R-04 + R-22 joins.
4. Truth-in-documentation: R-11, and R-12 after a hardware check.
5. The rest, opportunistically — plus one targeted test file for the receive
   loop to lock in the step-2 fixes.
