<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# How the K2000 turns an Akai or Roland object into a Kurzweil Program

Read out of the v3.87J ROM, offline, with every offset that could be checked
checked against real `.KRZ` banks. Companion to
[`ROLAND_IMPORT.md`](ROLAND_IMPORT.md), which covers the disk side.

**The headline: an imported Program is a *clone of Program 199* with a short
list of fields written into it.** Everything not in the list below keeps
Program 199's value. That is what makes the drop list decidable — and it is
also why two importers can agree on a corpus while differing: both inherit the
same template.

## 1. Two frames, and the constant between them

Offsets in this project come from two places and they differ by a constant:

| Frame | What it is | Program, 1 layer |
|---|---|---|
| **DUMP** | what `read_object_bytes` / a SysEx DUMP returns, and what `k2kfields` offsets use | 272 bytes |
| **file** | `PramObject.data` inside a `.KRZ` | 250 bytes |

**DUMP offset = file offset + 24.** Verified on all eleven segment tags of a
real 1-layer program (`AKAICORNERS.KRZ`, `DIGI-PAD  29`):

```
tag        0x1a 0x1b 0x20 0x21 0x22 0x23 0x40 0x50 0x51 0x52 0x53
file         80   84   88  104  120  136  152  184  200  216  232
DUMP        104  108  112  128  144  160  176  208  224  240  256
```

The ROM's own object pointer (`0x10B90A`, "body of object") is in the **DUMP**
frame — established independently, see §3. Everything below is DUMP.

## 2. The template mechanism

Both importers do the same three things:

1. **Create** a Program: `create_object(type=132, id, name, size=0x112)`.
2. **Clone the template**: `find_object(type=132, id=199)` then
   `memcpy(new_body, program199_body, 0x110)` — **272 bytes, a whole 1-layer
   program**.
3. **Per extra layer**: grow by `0xE0` (**224** bytes) and
   `memcpy(new_body + 48 + 224·k, program199_body + 48, 224)` — each layer is
   a copy of **Program 199's layer 1**.

The manual says "these layers have the same settings as Layer 1 of Program
199" (15-31). This is that sentence, in code, with the numbers: layer 1 starts
at DUMP offset **48** and is **224** bytes long.

Keymaps are built from a **ROM prototype** instead: a "New Keymap" template
object at `0x1888E4`, referenced nine times across the importer.

## 3. The write list

Layer `k` (0-based) starts at DUMP offset **`48 + 224·k`**. Everything the two
importers write into the cloned program:

| DUMP offset | Size | Written by Akai | Written by Roland | What we know it is |
|---|---|---|---|---|
| `188 + 224k` | word | keymap id | keymap id | **the layer's Keymap** — verified |
| `184 + 224k` | word | keymap id | keymap id | the layer's second keymap (stereo) |
| `178 + 224k` | byte | a source-derived value | **always 0** | unidentified |
| `186 + 224k` | byte | 0 | 0 | unidentified |
| `54 + 224k` | byte | computed (`0x164C66`) | **not written** | unidentified |
| `57 + 224k` | bit 5 | set | set | a flag |
| `57 + 224k` | bit 7 | set, conditional | **not written** | a flag |
| `270 + 224k` | word | bits 4-7 ← pan | same | see *Stereo* below |
| `259 + 224k` | byte | high nibble ← −pan | same | see *Stereo* below |
| `286 + 224k` | word | copy of `270 + 224k` | same | the next 16-byte block |
| `275 + 224k` | byte | copy of `259 + 224k` | same | the next 16-byte block |
| `2` | byte | source-derived | source-derived | program-level |
| `30 + 224n` | word | cleared | cleared | terminates the layer list |

**The keymap offset is verified, not read.** Scanning ten real programs in
`AKAICORNERS.KRZ` for 16-bit values that equal a keymap id present in the same
bank gives file offset **164** — in 10 of 10 programs for layer 0, and at
388 / 612 for layers 1 / 2 in the three-layer ones, i.e. `164 + 224k`. In the
DUMP frame that is `188 + 224k`, exactly where the ROM writes. That is also
what fixes the frame constant in §1 for the ROM's own pointer.

### Stereo

Both importers write a pan of **±7** into the pair of fields at
`259 / 270 + 224k`, and give the partner layer the opposite sign — the
manual's "the K2vx will also create stereo keymaps to preserve the separation
of stereo samples" (15-31). The two offsets are 16 bytes apart from their
copies at `275 / 286`, which is the stride of the trailing tagged blocks
(`0x50`…`0x53` at `size−64 … size−16`), so these writes land in the program's
trailing block area. **Which block, and which field inside it, is not yet
confirmed** — that needs one read-back of an imported program, so it is
recorded as unfinished rather than guessed.

### Derived from the source, or constant?

Asked by `mpc2emu`, who are implementing against this — the distinction
decides whether a field can be computed at all:

| Field | |
|---|---|
| `270`/`259 + 224k` (the ±7 pair) | **constant.** Literally `+7` / `−7`, the sign chosen by which member of a stereo pair the layer is. Nothing from the source reaches it |
| `57 + 224k` bit 5 | **constant**, set on every layer by both importers |
| `57 + 224k` bit 7 | **constant**, Akai only, conditional on a per-zone flag mask |
| `54 + 224k` = `lyr[5]` | **derived** — the velocity mark, see below |

### Named, via `mpc2emu`'s segment template

`mpc2emu` could not answer "what is at file offset 30 + 224k?" because their
program layout is not flat: a program is a chain of **tagged segments**, and
every field they write is named `(tag, index within that segment's body)`.
They sent the layer template — eighteen segments, `0x09`(15) `0x10`(7)
`0x11`(7) `0x18`(3) `0x19`(3) `0x14`(7) `0x15`(7) `0x1a`(3) `0x1b`(3)
`0x20`(15) `0x21`(15) `0x22`(15) `0x23`(15) `0x40`(31) `0x50`(15) `0x51`(15)
`0x52`(15) `0x53`(15) — and that is enough to do the naming from this end.

Each segment is one tag byte plus its body, so the layer is
`sum(1 + size)` = **224 bytes, the stride**. Laying the eighteen out in order
and comparing with the eleven tag positions this project had observed
independently:

**Eleven of eleven land exactly** — `0x1a` at 104, `0x1b` 108, `0x20` 112,
`0x21` 128, `0x22` 144, `0x23` 160, `0x40` 176, `0x50` 208, `0x51` 224,
`0x52` 240, `0x53` 256. Two templates derived from different directions, no
mismatch anywhere.

So the write list, in their addressing:

| DUMP | Segment | Their name | What the importer puts there |
|---|---|---|---|
| `54 + 224k` | `0x09` body[5] | `lyr[5]` | the derived 0…7 byte (Akai only) |
| `57 + 224k` | `0x09` body[8] | `lyr[8]` | flag bits 5 and 7 |
| `178 + 224k` | `0x40` body[1] | `cal[1]` | source-derived (Akai) / 0 (Roland) |
| `184 + 224k` | `0x40` body[7] | `cal[7]` | the second keymap id |
| `186 + 224k` | `0x40` body[9] | `cal[9]` | cleared |
| `188 + 224k` | `0x40` body[11] | **`cal[11]`** | **the keymap id** |
| `259 + 224k` | `0x53` body[2] | — | high nibble ← ∓7 |
| `270 + 224k` | `0x53` body[13] | — | bits 4-7 ← ±7 |

**`cal[11]` is `mpc2emu`'s own name for the keymap id**, arrived at from their
side without reference to any of this — and it is exactly where the ROM writes
it. That is the cross-confirmation the flat-offset framing could never have
given.

### `lyr[5]` is the velocity mark, and the ROM states `mpc2emu`'s formula

`mpc2emu` identified `lyr[5]` as the byte their writer builds with
`_vel_byte(lo_vel, hi_vel)` — **LoVel in bits 3–5, HiVel in bits 0–2 stored
inverted as `7 − mark`** — which they confirmed on hardware in June by diffing
a bank saved on the K2000R with known LoVel/HiVel.

The K2000's own importer computes exactly that. `0x164C66`, in full:

```
lo = src[88] >> 4                       ; 92-byte Akai staging record
if lo != 0:
    if src[89] & 0x0F: lo += 1          ; round UP on any remainder
    if lo > 7: lo = 7
    if lo > hi: lo = hi
hi = src[90] >> 4                       ; with src[90] == 127 -> 7, else clamp <= 6
return (lo << 3) | (7 - hi)             ; 0x164CE6..0x164CF0
```

The final three instructions are `negb` / `addqb #7` on the high mark and
`lslb #3` on the low one — **`(lo << 3) | (7 − hi)`**, their field description
arrived at from a panel diff, now read out of the firmware that produced the
convention. Neither derivation saw the other.

So the AKAI keygroup's velocity range becomes the K2000's eight dynamic
marks, with `127 → 7` meaning "the top of the AKAI range is fff" and the
`≤ 6` clamp keeping a non-top value off the top mark.

**And the rounding direction is a real difference, with hardware evidence
against the K2000.** `mpc2emu` rounds the low mark **down, never to nearest**,
because rounding it *onto* a mark's defining velocity made a layer play
**silent at that velocity** on the real K2000R — confirmed surgically in this
project by nudging a live layer's mark down. The firmware above rounds **up**
on any remainder. If that moves a boundary onto a defining value, **the
K2000's own AKAI importer has that dropout built in.**

That is the "reference implementation, not specification" point in its
sharpest form: the machine's own behaviour is the thing to match only until
you know why it does it.

### `lyr[8]` bit 5: the divergence is ours, and the corpus decides against me

The ROM sets bit 5 on **every** layer, both importers, unconditionally.
`mpc2emu`'s writer sets it **only for stereo sources**, and their corpus of
7,608 real layers has it on 86.4% of all-stereo layers against 0.7% of
all-mono ones. Unconditional would show as ~100% of everything, and it does
not — so their reading stands.

The likely resolution: the K2000's *importer* sets it unconditionally and
hand-authored programs do not, which makes it an importer fingerprint after
all. My own corpus check found bit 5 "common across third-party and factory
banks" and concluded nothing — because it never split by stereo, which is the
one split that makes the field speak. Another instance of the same rule.

Bit 7 is set by the Akai importer only, conditionally, and is unknown on both
sides.

### The ±7 copies cross into the next layer

With the segments laid out, the two copies resolve and they are **not**
partner-layer writes. `0x53` is the *last* segment of a layer, so copying 16
bytes on from `0x53 body[2]` and `body[13]` lands at `layer + 227` and
`layer + 238` — i.e. `lyr[2]` and `lyr[13]` of the **following layer**, a
different parameter entirely.

Either the firmware means "same index, next segment", or this is an
off-by-one-segment bug in the K2000's own importer. **Anyone reimplementing
this should not copy the ±7 into a partner layer's fields on the strength of
it.** It is stated precisely here so it can be checked rather than inherited.

### Why the corpus could not name them

**None of the four was identified from the data**, and the attempt failed in a
way worth recording. Looking for
the importer's fingerprint — bit 5 at file `33`, `0x70` at file `235` — finds
both **common across third-party and factory banks** (`SYNTHS__OBERHEIM.KRZ`,
`PADS__PADS_ROM.KRZ`, dozens more). They are ordinary fields with ordinary
values, so diffing cannot isolate them. File `246` has exactly **one** distinct
value across 29 programs, which by `eosed`'s rule means nothing downstream of
it can be validated against this corpus at all.

Reading the `moveq #7` / `moveq #-7` pair as **pan** is inference from the
magnitude and the mirroring. It is the one worth a hardware check: import a
stereo program, save, read those two nibbles in the two layers.

## 4. Where the two importers differ

Structurally they are the same routine twice — the sibling `eosed` session
found the identical parallel-code pattern in the EOS ROM the same night:

| | Akai (`0x16368A` … `0x164A86`) | Roland (`0x16AC30` … `0x16AEF0`) |
|---|---|---|
| zones per object | **8** (`cmpiw #8`) | **4** (`cmpiw #4`) |
| `178 + 224k` | source-derived | forced to 0 |
| `54 + 224k` | computed | not written |
| `57 + 224k` bit 7 | set conditionally | not written |
| everything else | identical sequence, identical constants |

## 5. The Roland source side

`0x16A2CC` seeks with `index << 7` — Roland patch data is **128 bytes** — and
fills a four-zone intermediate, per zone `i`:

```
zone[i].objid = src[5] * 100 + src[6] + bank_base
zone[i].w12   = src[2]     (word)
zone[i].b1A   = src[7]
zone[i].b1E   = src[9]
zone[i].b22   = src[4]
```

`src[5] * 100 + src[6]` is a Roland bank/number pair becoming a Kurzweil object
id, offset by the bank chosen in the load dialog.

## 6. What this is not

**This is not a parameter conversion table yet.** It says how the object is
assembled and which fields are touched; it does not yet say how a source
envelope, filter setting, key range or velocity switch becomes a Kurzweil
value. Those are the numbers worth having and they are still to be traced.

What it *does* give, immediately:

* **the drop list, by construction** — any Program field not in §3 is
  Program 199's value, not the source's. For anyone comparing an importer's
  output against the K2000's, that distinction is invisible in the bytes: both
  sides can write the same constant and agree perfectly while meaning
  different things;
* the frame constant (**+24**), which lets DUMP-frame and `.KRZ`-frame offsets
  be compared at all;
* the layer geometry (**48 + 224k**), verified against real banks;
* the keymap offset, verified against real banks.

## 6a. The keymap builder — where the parameter mapping actually lives

Each importer clones the ROM keymap prototype (`0x10B8B2`/`0x10B608`/`memcpy`),
picks a free id by scanning `find_object(133, id)` up to a ceiling of **999**,
and then fills a **zone array** that begins at `keymap_body + 12 +
keymap_body[12]` — a variable-length header, then the zones.

The Roland zone fill (`0x16A7DC`…) reads its source as **42-byte records**
(`mulsw #42`) and takes byte pairs out of them:

```
src[2 + 2z] >> 8, src[3 + 2z]     -> two bytes staged for the zone
src[10 + 2z] >> 8, src[11 + 2z]   -> two more
src[18 + 2z]  tested against 0xFF00
```

which is the shape of key-range and velocity-range pairs (high byte, low
byte), and they are written into the zone at its offsets 3 and 4 and onward.

### The entry write, with `mpc2emu`'s layout applied

`mpc2emu` supplied the keymap layout (their `docs/KRZ_FORMAT.md` §3.2, verified
by content against this same bank). A K2000 keymap has **no zone records and no
key-range fields**: it is one entry per key, the array index *is* the key, and
a "zone" spanning keys 40–52 is simply thirteen consecutive entries carrying
the same sample id. Velocity splits are several entry tables in one keymap,
selected by the eight `Level[j]` offsets at `12 + 2j`. And **entry `i` sounds
at key `i + 12`**.

With that, the Roland importer's per-entry write resolves completely
(`0x16A8DA`…`0x16A962`), in address order:

| Entry byte | Written from | Meaning |
|---|---|---|
| `+0`, `+1` | the cents word, high then low | **tuning**, i16 |
| `+2`, `+3` | high then low | **sample id**, i16 |
| `+4` | staged byte | **SSNr** |
| `+5` | constant **1** | *not in the 5-byte production layout* |

and the cents word is computed at `0x16A8B8` as

```
tuning = (A − 12 − I) × 100        ; muluw #100, after addiw #-12
```

where `A` is a staged byte and `I` the index the entry is written at. The
`× 100` is cents-per-semitone and the `− 12` is very likely `mpc2emu`'s
entry→key offset showing up in the firmware's own arithmetic — but **`I` is
not a MIDI key**, see below, so what the formula means is not settled and the
obvious reading of it is withheld.

### Resolved: the importer writes method `0x17`, six bytes per entry

The stride really is **6** (`d0 = i; d0 += d0; d0 += i; d0 += d0`, checked in
the raw bytes `2007 d080 d087 d080`), and `mpc2emu` found why: the keymap entry
layout is a **bitfield**, `0x10` tuning i16 · `0x08` tuning i8 · `0x04`
volumeAdjust i8 · `0x02` sampleID i16 · `0x01` subSample u8, with `entrySize`
equal to the sum of the selected widths. Method `0x13` (5 bytes) is the common
one; **method `0x17` is 6 bytes**, adding the per-entry `volumeAdjust`.

**Provenance, corrected.** `mpc2emu` first reported "1514 keymaps, 1514 of
1514" and then corrected it themselves: ~1140 of those files are their own
writer's output, so that headline was largely a writer agreeing with itself.
What survives is better evidence than a big number — the methods their writer
*cannot* emit appear only in banks it did not write.

Independently scanned here, over this project's own `.KRZ` collection, with
the bitfield implemented from their description rather than their code:

| Method | `entrySize` | `Method2Size` | Keymaps |
|---|---|---|---|
| `0x03` | 3 | 3 | 9 |
| `0x05` | 2 | 2 | 2 |
| `0x0b` | 4 | 4 | 6 |
| `0x0f` | 5 | 5 | 8 |
| `0x11` | 3 | 3 | 2 |
| `0x13` | 5 | 5 | 1386 |
| `0x17` | 6 | 6 | 60 |

**Zero mismatches across seven methods** — but only five of those rows carry
any weight. `0x13` and `0x17` are the two methods `mpc2emu`'s writer emits, so
those 1386 and 60 are mostly converter output on this side too, and counting
them is the same mistake in a second corpus.

The load-bearing observations are the **27 keymaps in the five methods neither
writer can produce**:

```
0x03  9     0x05  2     0x0b  6     0x0f  8     0x11  2
```

from `OBERHEIM.KRZ`, `PADS__PADS_ROM.KRZ`, `PADS__SYNSTR1.KRZ`,
`SYNTHS__OBERHEIM.KRZ` and `MXKR.KRZ`. Twenty-seven keymaps, seven methods
checked, two implementations, two partly disjoint corpora, no mismatch.

Method `0x17` specifically is attested **in one third-party bank** —
`PADS__PADS_ROM.KRZ`, which carries `0x05`, `0x11` and `0x17` together, found
independently on both sides. If the six-byte-entry claim ever needs defending,
that file is the evidence; the 60 is not.

Under `0x17` the field order predicts this importer's six writes exactly:

| Entry byte | Written from | Method `0x17` field |
|---|---|---|
| `+0`, `+1` | the cents word, high then low | **tuning** i16 |
| `+2` | a staged byte | **volumeAdjust** i8 |
| `+3`, `+4` | staged, high then low | **sampleID** i16 |
| `+5` | constant **1** | **subSample** u8 |

Three more constants that do not vary in any keymap either project has
looked at — **including the third-party banks**, which is the claim that
carries weight: `centsPerEntry = 100`, `basePitch = 0`, `entriesPerVel = 127`.

Six fields, six writes, in order, with the cents word landing in the only
i16 that takes cents and the constant `1` in the slot `mpc2emu`'s own writer
fills with `SSNr = 1` on every entry it emits. That is a relation a wrong
layout cannot satisfy, which is what makes it a finding rather than a
coincidence — a single field matching would have been worth nothing.

**Still loose, and now searched for four ways.** The prototype at `0x1888E4`
carries `method = 1`, `entrySize = 1` (a real variant — 11 keymaps use it), so
something must rewrite the header and grow the object between the clone and
the fill. A method-`0x17` keymap is **820 bytes**, so it cannot be skipped.
Searched, all negative:

* the constants `0x0017` at `body+2` and `6` at `body+10` — absent from the
  Roland module (the one `#23` is `jsr 0x149450(17, 3, 23, 1)`, screen
  coordinates in a `sprintf` loop);
* `mpc2emu`'s suggested **second ROM prototype** already carrying
  `method = 0x0017, entrySize = 0x0006` — its 28-byte signature does not occur
  anywhere in the image, nor does any shorter form of it;
* a **second keymap prototype does** exist, at `0x18862A`, named
  `"New Sample"` — and it is `method = 1, entrySize = 1` as well, so both ROM
  prototypes are the 1-byte form;
* the type-dispatched object fixup (`0x10A99C` → `0x10AD7C` for type 133)
  writes neither constant.

`entriesPerVel` is 127 in every keymap either project has looked at, so there
is no "compact keymap" escape either: a 6-byte-record keymap must be a full
128-entry, 820-byte object.

So the state is two prototypes' worth of evidence and **no mechanism found**.
Not-found is weak evidence here — a value held in a register or passed to a
helper does not appear in a constant search — but it has been looked for in
the four places it would most plausibly be, and the hunt is stopped rather
than continued until something turns up.

### And this is why the tuning formula is the *correct* form

`mpc2emu` flagged `tuning = (A − 12 − I) × 100` as the shape of a bug they had
fixed: written per key, it double-counts the transposition the K2000 already
applies through `centsPerEntry`, drives high keys to −72 semitones and silences
them — so if the importer did that, it would have been noticed in 1994.

It does not. `I` is `9 + zone_counter`, not a key, so the cents value is
**constant across every entry of a zone** — the per-zone fine offset a pitched
keymap wants, not the per-key ramp that breaks one. The index being something
other than a key, which cost a finding above, is the same fact that makes this
one come out right.

**The cheap discriminator stays worth running** when hardware is free: import
one Roland patch, save the bank, read the `tuning` words. Constant across a
zone's entries confirms the reading; ramping by 100 per entry refutes it.

## 6b. What a second importer's agreement is worth — less than it looks

`eosed` is tracing the same two formats out of the E-mu EOS ROM, and retracted
a framing that this document would otherwise have inherited. They had called a
charset "confirmed from EOS's ROM rather than from a document". It is not:
whoever wrote EOS's importer learned AKAI's layout from **Akai's published
format documents**, so EOS-agrees-with-the-document is two readings of one
source wearing different clothes.

**The same applies to this project.** Kurzweil's engineers read Roland's and
Akai's published layouts too. So where the K2000's ROM agrees with a format
note, that is not two machines agreeing — it may be two transcriptions of one
specification. The genuinely independent witness for a foreign format is the
**originating machine's own firmware**: the Akai's for AKAI (sibling project
`s3ked` has it, and found the field positions in an actual `repz cmpsb`
against `PRNAME`), and a Roland S-7xx's for Roland, which nobody here has.

Two consequences worth keeping:

* **Bank the mismatches, not the matches.** If EOS places a field where the
  K2000 trace does not, one of the two has misread a real machine and that is
  worth chasing. Agreement is weak evidence; disagreement is strong.
* **What a trace establishes independently is the importer's own choices** —
  its arithmetic, its constants, its clamps and its drop list — because those
  have no counterpart in anybody's specification and cannot have been
  transcribed. That is precisely the content of §3 and §4, which is a piece of
  luck: the part of this document that is worth most is also the part the
  circularity cannot touch.

**What is untouched by any of it:** everything in
[`ROLAND_IMPORT.md`](ROLAND_IMPORT.md) that came from the discs. Three real
CD-ROMs, fifteen directories, counts matching their own headers — no document
was involved on either side of that comparison.

## 6c. Five questions for one rig session

Everything in this document was done offline. Five things it cannot settle are
each about five minutes on the instrument, and together they need one session
with a Roland or Akai disc on the SCSI bus. **The hardware rule applies: one
session drives the K2000R, and this needs Jan's say-so.**

1. **The `tuning` reading.** Import a Roland patch, save the bank, read the
   `tuning` words of its keymap. **Constant across a zone's entries** confirms
   the per-zone-offset reading; **a ramp of 100 per entry** refutes it and
   means the importer cancels key tracking.
2. **The ±7 pan.** Import a stereo program, save, read `0x53 body[2]` and
   `body[13]` in both layers of the pair. `+7` / `−7` confirms reading the
   `moveq` pair as pan; anything else and that inference was wrong.
3. **The bit-5 fingerprint.** Is `lyr[8]` bit 5 set on a **mono** layer of a
   K2000-imported Akai program? The ROM writes it unconditionally;
   `mpc2emu`'s 7,608-layer corpus says only 0.7% of all-mono layers in the
   wild carry it. If an imported mono layer has it, the field marks an import.
4. **The segment diff.** A K2000-imported program against one `mpc2emu`
   wrote, compared **segment by segment** rather than byte by byte — same
   tags, different contents, and the tag names the field. One pass would name
   everything still unnamed in §3.
5. **The velocity dropout** (`mpc2emu`'s, and the cheapest). Import an Akai
   program whose velocity split's low bound lands on a mark's defining
   velocity, then play that velocity. The firmware rounds the low mark **up**,
   which is where this project measured a **silent layer** in June. If it is
   audible, the K2000's own importer ships the dropout.

## 7. Method

Every offset above is either an instruction in the ROM or a measurement on a
real `.KRZ`, and where both exist they agree. Two rules were applied
throughout, both learned the hard way on the Roland disk walk:

* identify by a **relation** several values must satisfy at once, never by one
  plausible position — the keymap offset holds in 10 of 10 programs *and* at
  `+224` and `+448` in the multi-layer ones;
* a field that barely varies cannot validate anything downstream of it.

**And one rule that is not about care.** Three times in one night a check here
was sound and its conclusion empty because the *split* was missing — by origin
(whose writer produced the file), by distinct value, and by stereo. None of the
three was findable by being more careful: knowing which split makes a field
speak requires the semantics, and the semantics were in another project.
`mpc2emu`'s way of putting it is the lesson — **they are findable by asking
someone who holds the other half.**
