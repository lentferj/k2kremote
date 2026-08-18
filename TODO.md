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
