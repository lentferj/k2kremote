<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# The keymap zone layout the importer needs (GLM-5.3-Flash, 2026-09-21)

> ## Checked 2026-09-21 — usable, with six corrections
>
> Verified here against the ROM and this project's `.KRZ` corpus, and
> independently by `mpc2emu` against their parser. **The citations are real,
> the header decode is right, and the level-table arithmetic is right** — all
> eight level words do resolve to body `+28`, which is a good check and it
> holds. The corrections, worst first:
>
> 1. **"a per-entry level adjustment … which `mpc2emu` never writes" is false
>    twice over.** `mpc2emu` writes `KEYMAP_METHOD_VOL = 0x0017` with a 6-byte
>    entry (`krz_writer.py:179`, under §KRZSHAREDGAIN) — and its calibration is
>    *this project's* panel measurement, 0.5 dB per click, rails ±63.5 dB.
>    **And the K2000's own importer writes 6-byte entries too**: its address
>    arithmetic is `base + 6 × index`, which is method `0x17` including
>    `volumeAdjust`. So the field is not merely available — on the evidence of
>    `IMPORT_CONVERSION.md` §3 it is what the importer actually uses. The
>    sentence came from a stale line in `mpc2emu`'s `KRZ_FORMAT.md`, since
>    struck through there.
> 2. **"That is what the ROM's 'New Keymap' template (`0x1888E4`) is filled
>    with" is false**, and only the firmware can say so. That template carries
>    `method = 1`, `entrySize = 1`, and **its entry area is all zeros**. The
>    rising values the document is explaining — 282, 291, 301 … 373 — come from
>    a multisampled keymap (`SOLDANO 12 A` in `AKAICORNERS.KRZ`), and every one
>    is a genuine sample object in that bank, with per-zone tunings of
>    −17 … 0 cents beside them. **`mpc2emu` confirmed the same eleven values
>    independently and supplied the provenance that sharpens it**: that bank is
>    *their converter's own output* from an AKAI conversion, so those ids are
>    generated content whose origin is fully known. *The reading is right: they
>    are sample ids. The attribution to the prototype is wrong*, and the
>    inference built on it inverts — an importer author told to discard them as
>    template values would be discarding a converted instrument.
> 3. **"the corpus contains no compacted keymaps" is true of those 103 and
>    false of the corpus.** Methods `0x05` and `0x11` — both with `0x02` clear —
>    appear in `PADS__PADS_ROM.KRZ` here; `mpc2emu` counts `0x01` on 11 keymaps
>    and `0x03` on 25 in real third-party banks. The caution the document raises
>    is therefore **measured, not prudent**, which makes it stronger.
> 4. **"seven big-endian words" is six** (`+0` … `+11`). Its own table is right;
>    the prose disagrees with it.
> 5. **"each selected bit adds its field"** — `mpc2emu`'s parser treats `0x10`
>    and `0x08` as *mutually exclusive* (`if … elif`), not additive. No observed
>    method sets both, so nothing distinguishes the readings today.
> 6. **"The K2000 itself writes `0x0013` on save"** is carried from
>    `KRZ_FORMAT.md` and is about *saving*. It is not evidence about the
>    **importer**, whose write path is the 6-byte one in correction 1.
>
> ### Provenance of the bank used above
>
> `AKAICORNERS.KRZ` is `mpc2emu`'s converter output, not a third-party bank.
> Three claims in `IMPORT_CONVERSION.md` were measured on it — the
> `DUMP = file + 24` constant (eleven tags), the layer keymap-id offset (10 of
> 10 programs at file 164, and `+224`/`+448` in the three-layer ones), and the
> keymap geometry. **Each survives, because each was cross-checked against an
> artefact that writer had no hand in**: the tag positions against this
> project's own live-DUMP offsets and against `mpc2emu`'s 18-segment template
> summing to 224, and the keymap-id offset against where the ROM writes it.
> Recorded because the origin belongs in the record whether or not it changes
> the conclusion — which is the rule this project adopted last night and this
> is the first application of it to its own work.
>
> The pattern is last night's with the roles reversed: **the findings that read
> code held up; the one that read prose carried another project's stale
> sentence forward with a second name on it.** It surfaced only because it was
> checked against the code, on Jan's instruction.
>
> Chasing correction 1 flushed out a fourth instance in `mpc2emu`'s repo: their
> parser carried `zone_volume += v / 2.0  # unit unverified` while their writer
> carried this project's panel measurement of that same unit. **The value was
> right; the caveat about it was three weeks stale.** So the count of shapes is
> now four — a number without its corpus, a sentence without its source, an
> inference without the bytes, and a caveat that outlived its measurement — and
> none of the four was found by the project that owned the claim.

External session file. `IMPORT_CONVERSION.md` §6a ends on the dependency this
closes: the keymap builder needs the Kurzweil *keymap zone* layout, owned and
validated by `mpc2emu`'s parser over thousands of real banks. Here is that
layout, and — more useful — the check that the two projects' frames agree
numerically before any code uses it.

Source: `mpc2emu/parsers/krz_parser.py::_parse_keymap_object`, which decodes
not just mpc2emu's own write form but the full method bitfield and the
native Level[8] multi-velocity-table mechanism, cross-checked against real
soundsets. This file adds nothing to the format; it carries it across with the
frame arithmetic done, which is the part `IMPORT_CONVERSION.md` §6a was
waiting on.

## The record: `IMPORT_CONVERSION.md`'s 668 bytes, decoded

The measurement there — 103 real keymaps, **all 668 bytes**, opening

```
0000 0013 0000 0064 007f 0005 0010 000e 000c 000a 0008 0006 0004 0002
```

— is exactly mpc2emu's keymap header, read as **seven big-endian words plus
the level table**:

| file offset | word | meaning |
|---:|---:|---|
| `+0` | `0x0000` | header sample ID (used only by *compacted* keymaps — see below) |
| `+2` | `0x0013` | the **method bitfield** |
| `+4` | `0x0000` | base pitch |
| `+6` | `0x0064` | cents per entry = **100** |
| `+8` | `0x007f` | entries per velocity level → `num_keys = 127 + 1 = 128` |
| `+10` | `0x0005` | entry size = **5 bytes** |
| `+12…27` | `0x0010 0x000e … 0x0002` | the **velocity-level table**: eight words |

The method bitfield decides the per-entry field widths (the *order* is fixed,
each selected bit adds its field):

| bit | field | width |
|---|---|---|
| `0x10` | tuning, i16 (cents) | 2 |
| `0x08` | tuning, i8 | 1 |
| `0x04` | volume adjust, u8 | 1 |
| `0x02` | sample ID, u16 | 2 |
| `0x01` | sub-sample, u8 | 1 |

**Method `0x0013` = `0x10 | 0x02 | 0x01` → per entry `[i16 tuning BE | u16
sample ID BE | u8 sub-sample]` — five bytes, which is the measured record.**
The K2000 itself writes `0x0013` on save. So the example record there decodes
as:

```
00 00 01 1a 01   ->  tuning 0 cents · sample ID 0x011a (282) · sub-sample 1
```

and the observed "rising ~9 per distinct record" is the **sample ID** rising
through the prototype's default entries, not a pointer or an offset. That is
what the ROM's "New Keymap" template (`0x1888E4`) is filled with — which is
itself informative for the importer: the prototype hands each zone a *sample
ID* and the importer overwrites it, so the prototype's IDs can be recognized
as template values rather than content.

## The level table — and why `+28` was measured and not guessed

The level table is **eight words at body `+12`**, one per velocity level 0-7.
Each level's entry array address is:

```
table_addr[level] = body + 12 + 2·level + level_table[level]
```

In the measured header every level points to the *same* address: `12 + 2j +
(0x10, 0x0e, 0x0c, 0x0a, 0x08, 0x06, 0x04, 0x02)` = body + **28** for all
eight — one shared entry table covering the full velocity range, exactly the
"one per note" reading §6a proposed. A keymap where the eight level words
*disagree* has per-velocity tables; the same address repeated is the
single-table case. **The importer's clone writes a single-table prototype, so
it needs only one table** — but the level-table mechanism is the reason the
record array is not simply at a fixed offset in *every* keymap: real saved
keymaps can carry up to eight tables, and §6a's fixed 668-byte size says the
*prototype* is single-table, not that the format is.

The frame relation checks out on the measured bytes, which is the second
thing §6a needed:

* ROM computes the zone array base as `keymap_body + 12 + keymap_body[12]`
  — body `+12` is the level table, `keymap_body[12]` is level[0] = `0x0010`,
  so the ROM's base is body `+28`.
* Measured on real banks: records start at **28**. The two frames agree with
  the DUMP = file + 24 constant already established: level table at file `+12`
  = DUMP `+36`, level[0] = 16, `12 + 24 + 16 = 52` DUMP = `28` file. All three
  readings land on the same first record.

**Entry `i` sounds MIDI key `i + 12`** — hardware-confirmed in mpc2emu
(`KEYMAP_ENTRY_NOTE_OFFSET`), so the importer's 128 entries cover MIDI keys
12..139 clamped at both ends, and a Roland key range that reaches C-1 must be
clamped, not shifted.

## What the importer should write per zone

From the same parser, the fields a Roland zone-fill can carry into a record:

* `tuning` (i16, cents) — the Roland fine-tune number, if the K2000 trace
  shows it is read;
* `sampleID` (u16) — the Kurzweil object id built from
  `src[5]*100 + src[6] + bank_base` in `IMPORT_CONVERSION.md` §5;
* `subSample` (u8) — the ROM-sample selector; **1 = the sample's own data**,
  and a value the importer should write as 1 unless it means to name a
  sub-sample;
* with method `0x0013` there is **no per-entry volume field** — a keymap can
  only carry per-entry level adjustment if the method adds `0x04`, which
  mpc2emu never writes and the K2000's template does not use.

## One caveat carried over from the measurement itself

`IMPORT_CONVERSION.md` measured **103 keymaps, every one 668 bytes**. Under
this layout 668 = 12 + 16 + 128×5 exactly — but note what that implies: the
corpus contains *no compacted keymaps* (`method & 0x02` clear → entries carry
no sample ID and fall back to the header's), and no multi-table (per-velocity)
keymaps. That is plausible for ROM-prototype-derived content but should not be
assumed of *imported* keymaps — the importer writes what it writes, and if a
future trace shows it writing a different method word, entry size changes with
it. The parser handles all of it; the corpus just hasn't seen it.

## One correction to expect

`IMPORT_CONVERSION.md` §6a says the zone array "begins at `keymap_body + 12 +
keymap_body[12]` — a variable-length header". It is variable-length in
*format* (the level table is 8 words but each level points to its own table;
multiple distinct tables = more arrays), and the prototype is the single-table
case. The 28-byte prefix is the invariant for the prototype; the format is
more general, and mpc2emu's parser is the reference for the general case.
