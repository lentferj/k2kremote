<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# Kurzweil K2000 `.MAC` Macro File — Reverse-Engineered Reference

A **macro** is the K2000's list of "load this file, into that bank, in this
mode". The list lives in battery-backed RAM as a *Macro Table* object, and can
be saved to disk as a `.MAC` file. `BOOT.MAC` in the root directory of the
startup drive is the one the machine replays at power-on, so it is the file
that decides what is resident after boot ("Creating a Startup File", manual
13-63).

Sources for this document:

* the **Kurzweil K2vx manual**, chapter 13 — *Macros* (13-38 … 13-54),
  *Creating a Startup File* (13-63);
* the real **`BOOT.MAC`** off this project's K2000R, recovered from the
  `HD0_K2X_HD2G-*.img.lzo` backups (300 bytes, 6 entries, written by OS v3.54;
  byte-identical in the 2025-05 and 2026-02 backups). It is checked in as
  `tests/fixtures/BOOT.MAC`;
* the sibling **mpc2emu** project's [`docs/KRZ_FORMAT.md`](../../mpc2emu/docs/KRZ_FORMAT.md)
  §2 for the `PRAM` container framing, and `docs/k2000r_midi_comms.md` §4 for
  the object-type numbering.

> **Implementation:** [`k2kmaced/macfile.py`](../k2kmaced/macfile.py). Where
> this document and the code disagree, trust the code — it round-trips the real
> file byte-for-byte, which is the regression test
> (`tests/test_macfile.py::test_hardware_written_file_round_trips_byte_exactly`).

**Endianness: big-endian throughout** (68000 platform), the opposite of the
FAT16 volume the file sits on.

---

## 1. Container

A `.MAC` is a `PRAM` object-database dump — the *same* container as a `.KRZ`
bank, just with one object in it and no PCM region:

```
PRAM <osize> <rest[24]>      32-byte file header
  object block               the Macro Table (type 100, id 35, name "Macro")
  int32 = 0                  object-section end marker
                             (a .KRZ has its PCM region here; a .MAC does not)
```

`osize` is the absolute offset where the sample region would start; in a `.MAC`
that equals the file length. `rest` carries free-RAM figures and, at offset
16, the OS version ×100 (`354` = v3.54 in our file).

The object block framing is mpc2emu's `KRZ_FORMAT.md` §2.2 unchanged:
`int32` negative block size, `u16` hash, `u16` size, `u16` ofs, NUL-terminated
name padded to even, then the object body.

### Object identity

The hash is `0x6423`. Bit `0x8000` is clear, so the split is 8/8 (mpc2emu's
`_gtype`/`_gid`): **type 100, id 35**. Type 100 is the K2000's *Table* type —
the Master parameters are 100/16 — and `Table  35  Macro` is exactly the line
the manual shows for a macro in the Save-Object list (13-40). The same
type/id pair addresses the live table over MIDI.

---

## 2. Macro Table body

A run of variable-length entries, then a `u16 = 0` terminator:

```
entry[0] entry[1] … entry[n-1]  0x0000
```

The manual notes an empty table is 14 bytes and each entry adds "approximately
40 to 100 bytes" — consistent with the 34–44 byte entries below (plus the
object framing).

## 3. Macro entry

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0:2` | 2 | `length` | total bytes of this entry, **including** this field |
| `2:4` | 2 | `drive` | drive-ID code — §5 |
| `4:6` | 2 | — | `0` in every observed entry; meaning unknown |
| `6:8` | 2 | `bank` | `0`, `100` … `900`, or `0xFFFF` = **Everything** |
| `8:10` | 2 | `mode` | load-mode code — §5 |
| `10:12` | 2 | — | **uninitialised**: `0x000E`, `0x88A4`, `0x0000`, `0x0008` across six entries of one file |
| `12:14` | 2 | — | `0` in every observed entry; meaning unknown |
| `14:30` | 16 | `filename` | NUL-terminated, NUL/garbage-padded — up to 15 chars |
| `30:…` | var | `path` | NUL-terminated directory path (`\`, `\--FAVS\`), padded to an **even** length |
| … | 2 | `trailer` | also uninitialised (`0x2D46`, `0x0000`, `0x4F57`, `0x5256`, `0x0024`, `0x5A00`) |

So `length = 32 + even(len(path) + 1)` — 34 for a root-directory entry, 42 for
`\--FAVS\`, 44 for `\-RLNDCD2\`. All six entries of the real file match.

The fields marked uninitialised are firmware leftovers, not data: they differ
between entries that are otherwise identical in kind. `macfile.py` keeps them
so an untouched entry re-serialises byte-for-byte, and zeroes them on any entry
you actually edit.

### Annotated first entry

```
0030  00 22        length = 34
      00 01        drive  = 1  → SCSI 0
      00 00        (unknown, always 0)
      ff ff        bank   = Everything
      00 03        mode   = 3  → Overwrite
      00 0e        (uninitialised)
      00 00        (unknown, always 0)
003e  4e 55 4c 4c 2e 4b 52 5a 00 52 5a 00 8d 90 00 00
                   filename = "NULL.KRZ", then 7 bytes of leftovers
004e  5c 00        path = "\"
0050  2d 46        (uninitialised trailer)
```

which the K2000's own Macro page would draw as

```
0:\NULL.KRZ                   E:O:
```

— the manual's documented boot trick for clearing memory at startup: an empty
bank loaded as *Everything* in *Overwrite* mode (13-64).

---

## 4. The whole real file

```
  #  entry                                bank   mode        length
  0  0:\NULL.KRZ                          E      Overwrite   34
  1  0:\--FAVS\KPOWFAV.KRZ                200    Overwrite   42
  2  0:\--FAVS\LFOALFAV.KRZ               300    Overwrite   42
  3  0:\--FAVS\SOARCFAV.KRZ               400    Overwrite   42
  4  0:\--FAVS\TCNOAFAV.KRZ               500    Overwrite   42
  5  0:\-RLNDCD2\WAVSTFAV.KRZ             600    Overwrite   44
```

All six paths resolve to files that exist on the same image, at exactly those
paths — which is what makes the path/filename split and the drive reading
trustworthy rather than merely plausible.

---

## 5. Drive and mode codes — the one soft spot

The manual prints the value lists for the *Modify Macro Entries* page (13-52)
but not their numeric codes. Decoding them as 0-based indices into those lists
gives:

| Code | Drive | | Code | Mode | Letter |
|---|---|---|---|---|---|
| 0 | Floppy | | 0 | Append | `A` |
| 1 | SCSI 0 | | 1 | Merge | `M` |
| 2 | SCSI 1 | | 2 | Fill | `F` |
| … | … | | 3 | Overwrite | `O` |
| 8 | SCSI 7 | | 4 | OvFill | `V` |
| 9 | Unspecified | | | | |
| 10 | Library | | | | |

Three independent checks agree on the real file:

1. **`mode = 3` → Overwrite.** Entry 0 is `NULL.KRZ` loaded as *Everything* —
   the manual's memory-clearing boot trick, which only works in *Overwrite*
   mode (13-64). The list-index reading is the one that produces it.
2. **`drive = 1` → SCSI 0.** The backups are named `HD0_…`; the disk is SCSI
   ID 0.
3. Every referenced path exists on that disk (§4).

### Codes 2 and 3 are now confirmed against the instrument (2026-08-17)

Driving the panel to *Disk → Macro* makes the K2000 render its own macro table,
one line per entry, with the mode as a letter in exactly the position this
decoder predicts. On a 19-entry macro the device printed `O` on every entry we
decode as `mode = 3` and `F` on every entry we decode as `mode = 2`:

```
 0:\NULL.KRZ                       E:O:      mode 3  ->  device shows O
 0:\<path>\<bank>.KRZ            200:O:      mode 3  ->  device shows O
 0:\<path>\<bank>.KRZ            200:F:      mode 2  ->  device shows F
```

So **`3` → Overwrite and `2` → Fill are measured, not inferred**, and the
list-index reading is right where it has been exercised. This also rules out the
displayed-value alternative for the mode field: were `3` stored as the displayed
value it would not land on Overwrite, and the `NULL.KRZ` entry would not work.

Codes `0` (Append), `1` (Merge) and `4` (OvFill) remain **unconfirmed**, as does
the entire drive column — the observed macro uses drive `1` throughout, which is
consistent with SCSI 0 but does not discriminate it from the alternative. The
table is therefore *partly* measured, and §7's probe is still the way to finish
it.

Treat modes `0`, `1`, `4` and every drive code as unverified when writing a
macro.

---

## 6. Object lists — not covered

A macro entry can carry a list of individual objects to load from the file
instead of the whole file; the K2000 flags those with `Obj` on the Macro page
and shows them as `Program 210`-style type/id pairs (13-46). **No such entry
was available**, so the layout of the appended list is unknown.

`macfile.py` handles this without guessing: bytes beyond the modelled layout
are captured verbatim in `MacroEntry.extra`, reported through
`has_object_list`, and written back unchanged.

---

## 7. Open questions for a hardware session

Nothing here has touched the K2000. When a session is authorised:

* **Does the RAM layout match the disk layout?** `DUMP` returns the K2000's
  in-RAM structure, which for programs and keymaps is known to differ from the
  disk serialization (mpc2emu, `k2000r_midi_comms.md` §4). Dump object type
  100 / id 35 with Macro Record on and compare against the `.MAC` the same
  table saves to disk.
* **Drive and mode codes** (§5): set one entry to each of the eleven drives and
  five modes from the front panel, save a `.MAC` each time, and read the code
  back. *Partly done* — modes `2` and `3` were confirmed by reading the device's
  own Macro page (§5). What remains is modes `0`, `1`, `4` and the drive column,
  none of which the observed macro exercises.
* **Object lists** (§6): record one macro entry with a selected-object list and
  diff it against the same entry without one.

The procedures are written up in
[`RESOLUTION_NOTES.md`](RESOLUTION_NOTES.md) — see *MAC editor*.
