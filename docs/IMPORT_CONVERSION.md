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
| `57 + 224k` | bit 5 | set *(stereo only — see §6b)* | set *(stereo only)* | the **stereo marker** |
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
| `57 + 224k` bit 5 | ~~**constant**, set on every layer by both importers~~ **REFUTED on hardware — it is a stereo marker, set in the stereo branch only. See §6b and §6b-ter.** |
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

> **This section is superseded.** Its premise — "unconditional" — was refuted
> on the instrument; see **§6b (REFUTED)** and **§6b-ter**, where bit 5 reads
> `0x24` on four stereo imports and `0x04` on three mono ones. `mpc2emu`'s
> corpus reading was right and mine was wrong. The section is kept because the
> *reasoning* below is what the measurement later confirmed, and because the
> way I got it wrong is the point.

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

~~`src[5] * 100 + src[6]` is a Roland bank/number pair becoming a Kurzweil
object id, offset by the bank chosen in the load dialog.~~ **WRONG, retracted
2026-09-21.** It is `coarse × 100 + fine` — a **tuning in cents** — added to
`record[+38]`, and the field is `record[+10 + 2z]`. The object id lives at
`+2 + 2z`. The `× 100` was read as a bank multiplier when it is the cents
scale; see the resolution in §6a. That unverified gloss then supplied the
premise for two further wrong readings before it was checked.

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

### RETRACTED: `I` is a key after all, and the formula is per-key

**This section said the opposite and was wrong.** It claimed `I` was
`9 + zone_counter`, so the cents value was constant across a zone — the safe
per-zone offset — and that this was what saved the formula from `mpc2emu`'s
objection. **That was checked wrongly and the conclusion was relayed to them
as a resolution of their concern.**

`sp@(22)` is assigned once **per iteration**, not once. The loop is at
`0x16AB28`:

```
16ab28:  addqw #1,%sp@(250)
16ab2c:  cmpiw #88,%sp@(250)
16ab32:  bltw  0x16A7A4          <- back to `moveq #9 / addw sp@(250)`
```

`sp@(250)` runs **0…87** and re-enters the fill at the very instruction that
computes `I`. So `I = 9 + key`, running 9…96 — **a per-key index over an
88-key range.** Found by GLM-5.3-Flash and confirmed here at the address
above; the earlier reading noted this possibility and then discarded it.

**So `mpc2emu`'s objection stands and is not resolved.** The formula carries a
−100-per-key term by construction, which is the shape of the bug they fixed.

### What `A` actually is — and it is not a record byte

The same document corrected the other half, verified here at `0x16A874`:

```
a0   = record + 2 + 2z                 ; the sample reference word
      movew #134,-(sp) ; jsr 0x1032EA  ; find_object(type 134, that id)
      jsr 0x10B90A                     ; body of the object
A    = obj_body[12]                    ; 0x16A89E
tuning = record_word[10 + 2z] + (A − 12 − I) × 100
```

`A` is **byte 12 of the body of the type-134 object the record names** — the
already-imported Kurzweil object, fetched by id — not a staged byte of the
Roland record. Our vendored enum calls type 134 `Soundblock`; whether that is
`mpc2emu`'s Sample object, and whether `body[12]` is its root key, is for them
to say. If it is the root key, `(root − 12 − key) × 100` against
`centsPerEntry = 100` cancels the keymap's own per-key transposition and flattens
every key to its sample's own pitch.

### The discriminator is blocked on an unresolved field conflict

`mpc2emu` confirmed both halves against real objects: type **134** is their
Sample (their file-type codes are ours **−96**: 36/37/38 ↔ 132/133/134), and
`body[12]` **is** the root key — sample ids 200/202/204 in `AKAICORNERS.KRZ`
read 48/60/72, C3/C4/C5 of a three-way multisample, with `body[13] = 0x70`,
the documented flags value for a playable RAM sample. So the 12-byte fixed
header ends at `body+12`, `Soundfilehead` begins there, and its first byte is
`rootkey`.

With `I = key − 12` the arithmetic cancels **exactly**:

```
tuning = (root − 12 − I) × 100 = (root − key) × 100
```

against the K2000's own `(key − root) × 100` per-key transposition — sum zero,
every key sounding its sample at the sample's own pitch. `mpc2emu` has
hardware evidence for the *mechanism*: their writer once emitted
`100 × (root − 12 − key)`, the same expression an octave out, and it drove
high keys to −72 semitones and silenced them.

**But the discriminator cannot be run yet, and neither reading should be
acted on.** The 42-byte records are not disc bytes — they are built in memory
— and the two traces of that buffer disagree about what its fields hold:

| Field | The converter (`0x16A42A`…) writes | The fill (`0x16A884`…) reads |
|---|---|---|
| `+10 + 2z` | `src[5]×100 + src[6] + record[+38]` — ~~a Kurzweil object id~~ **a tuning in cents** | the **tuning base**, to which the cents term is added — *consistent, once the gloss is corrected* |
| `+2 + 2z` | *(not seen written here)* | the **sample id**, passed to `find_object(134, ·)` |
| `+18 + 2z` | `a1@(2)`, a word | a **flag**: high byte set ⇒ use the tuning word raw |

Both sides of that table are read off the ROM. They cannot both describe the
same field *at the same moment*: if `+10 + 2z` holds an object id, the fill
adds a cents term to an id and stores it as tuning.

### RESOLVED — and the object-id reading in §5 was the error

The converter's destination pointer, never checked directly until now
(`0x16A352`): `lea %sp@(4),%a3` · `movel %a5@(23696),%d0` ·
`movew %fp@,%d1 ; mulsw #42` · `addl %d1,%d0` · `movel %d0,%a3@`. So `*a3`
**is** the record address, and both traces do address the same field. **The
mistake was not in the addressing — it was in §5's gloss of the value.**

§5 called `src[5]*100 + src[6]` "a Roland bank/number pair turned into a
Kurzweil object id", inferred from the `× 100` and never checked.
**`coarse × 100 + fine` is the canonical cents encoding**, and it is this
format's own scale — `centsPerEntry = 100`. Four reasons it is a tuning, the
last decisive:

1. it is *consumed* as a tuning base — the cents term is added and the sum
   stored in the entry's `tuning` i16;
2. an id plus thousands of cents is nonsense in both units (`mpc2emu`'s
   argument, which stands even though the inference they drew from it did not);
3. `semitones × 100 + cents` is this format's convention;
4. **the sample id already has its own field.** The fill reads
   `record[+2 + 2z]` into `find_object(134, ·)`, and the disc-walk region tests
   that same word for negative at `0x16BECE`. `+10 + 2z` need not be an id
   because `+2 + 2z` is one.

```
+2  + 2z   the Kurzweil Sample object id   (written in the disc-walk region)
+10 + 2z   a tuning in cents = coarse*100 + fine + record[+38]
+38        a per-record cents base
```

**So there is no firmware bug and the write-order question never needed
answering**: `+10 + 2z` has one writer and it writes a tuning. The
contradiction was mine twice over — an unverified gloss, then a conflict built
on top of it.

### The construction is CONDITIONAL — gated on a byte from the disc

`0x16A85C`…`0x16A872`:

```
d0 = 0xFF00
a0 = record + 18 + 2z
d0 &= *a0
bne 0x16A8DA            ; high byte set -> SKIP the root lookup and the ×100 term
```

and the gate's source is traced — `0x16A44A` writes
`record[+18 + 2z] ← src[2]`, a word out of the **Roland partial data**. So the
K2000 does **not** cancel key-tracking unconditionally: a byte the disc
supplies decides, per partial, whether the `(A − 12 − I) × 100` term is applied
at all.

That answers the question `mpc2emu` posed as "unconditional, or only where the
source says fixed pitch?" — **conditional**.

### Measured on three discs: the flag is used exactly as you would hope

The gate's source resolves through one more pointer. `0x16A3A0`:
`*a2 = buffer + 16 + 16·z` — so the 128-byte Roland patch record is **16 bytes
of name followed by four 16-byte zone sub-records**, and the gate byte is
`sub[2]`, not byte 2 of the record. The partial data area itself is at disc
offset **`0x1D5600`**, 128 bytes per record (`addil #1922560` at `0x16A320`,
`pea 0x80` at `0x16A338`).

| Disc | zones | gate `sub[2] == 0` → cancel tracking | distinct values |
|---|---|---|---|
| Gigapack I CD 1 | 16016 | **49 %** | 3 (`0`, `8`, `0xFF`) |
| Gigapack I CD 2 | 11520 | **1 %** | 6 |
| L-CDP-05 Solo Strings | 4676 | **0 %** | 2 (`8`, `0xFF`) |

**A near-binary field** — 3 distinct values across 16,016 zones on CD 1, and 2
across 4676 on Solo Strings. That much is solid.

**Re-measured with the confound removed — the original direction holds and the
numbers are better.** Filtering to zones that actually carry a sample (bytes
0–1 ≠ `0xFFFF`) and correcting the data base to `0x1D5600 + 0x800`:

| Disc | used zones | gate `0` → cancel tracking | volumes drum-named |
|---|---|---|---|
| Gigapack I CD 1 | 6037 | **99.6 %** | **46 %** (`*Bass-Drums*`, `BD:`, `SD:`, `HH:`) |
| Gigapack I CD 2 | 5157 | **2 %** | **0 %** (`*CLASSICAL*`, `** CHOIR **`, `CHO:`) |
| L-CDP-05 Solo Strings | 1327 | **0 %** | 0 % |

**The two Gigapack discs are a natural A/B**: CD 1 is the percussion disc and
asks for fixed pitch on essentially every used zone; CD 2 is the melodic disc
and almost never does. The flag tracks the material, measured on the volume
names independently of the flag itself.

And CD 2's ninety exceptions are coherent: they are `CHO:Women-Comb`,
`CHO:Glissando`, `CHO:Glis up+do`, `CHO:Voiceless` — glissandi and vocal
effects, which are exactly the melodic-disc material that should not track the
keyboard.

*(Two readings were discarded getting here, both by measurement rather than
argument: "49 % of all zones" counted empty slots, and "gate 8 marks an unused
zone" was refuted by CD 2 and Solo Strings, where used zones are overwhelmingly
gate 8.)*

**The superseded paragraph, kept visible:**
Correcting them the same day they were measured: a partial carries four zone
slots and **an unused slot also reads `0`**, so an unknown share of CD 1's 49 %
is empty slots rather than fixed-pitch requests. Separating them needs the
importer's own used/unused test, which is not a byte in the disc record — it
is the sign of a value returned by a call at `0x16A3D8` (negative ⇒ the zone is
skipped and `record[+2+2z]` is set to −1), and that call is not yet traced.

Two things survive the confound and are worth keeping:

* **the flag is real and near-binary**, which is what the ROM said;
* **the first non-blank partial record on CD 1 — index 16, `" BD:BD Dance 1AI"`,
  a bass drum — has gate `0` on zone 0**, which is the value that cancels
  key-tracking. A fixed-pitch instrument asking for fixed pitch is the
  single cleanest observation in the set.

Also corrected: the data area's first **16 records are `0xFF` blanks**, so
partial data begins at `0x1D5600 + 0x800`. The earlier scan included those and
missed sixteen real records at the far end — which is exactly where the
`0xFF` gate values in the table came from.

So the K2000's importer applies the key-track cancellation **only where the
Roland source asks for it**, and real discs set that flag the way a sampler
library would. `sub[5]`, the coarse-tuning byte feeding `coarse × 100 + fine`,
is `0` in 99 % of zones, which is what a tuning offset should look like.

**The polarity is the opposite of the prior.** `mpc2emu` offered one from their
side — MPC's `<KeyTrack>` is "set = do not track" — and said to measure rather
than take the analogy. Measured: Roland's byte is **set = DO track** (`8` skips
the cancellation). Two formats, opposite conventions, and the analogy would
have inverted the meaning. They were right to refuse it.

*How the measurement was got right:* the first attempt read byte 2 of the
128-byte record and produced values like `32, 46, 48, 53, 68, 72` — which are
`' '`, `'.'`, `'0'`, `'5'`, `'D'`, `'H'`. **ASCII is what exposed a bad pointer
assumption**; a flag byte does not look like a name. Checking the pointer chain
then gave the sub-record layout.

### The construction itself: correct for fixed pitch, a defect when misapplied

**Correction, 14:45.** These two files were first described as a before/after
pair showing a fixed bug. They are not: same size, same timestamp, same run,
both written by code that already had the fix, and one source is a **drum
kit**. `mpc2emu` checked the provenance after this project pointed out that the
"after" file still carried the construction, and retracted the framing while
keeping the numbers. **The construction is deliberate and correct for
fixed-pitch material** — cancelling key-tracking is the right rendering of a
pad that does not transpose, and the idiom appears in real third-party
soundsets.

The numbers, reproduced here independently, reading each entry's sample root
from the type-38 object's `body[12]`:

```
PSCOLD_01.KRZ  keymap 200   tuning −9200 … +2300   (root−key)×100 holds 108/128
               worst: entry 115 (key 127), sample 201 root 35 → −9200 = −92 semitones
```

`(35 − 12 − 0) × 100 = +2300` at entry 0 and `(35 − 127) × 100 = −9200` at
entry 115 — **the firmware's `(A − 12 − I) × 100`, byte for byte, in a file.**

**Misapplied to pitched material it does not flatten; it goes silent.** Their
hardware measurement was of their own *old* bug, which applied the construction
to **every** entry including pitched multisamples, and that drove high keys to
−72 semitones and they stopped sounding. The reason is visible in the numbers rather than in
the algebra — the *sum* is zero, but to reach zero the engine has to deliver a
**−92-semitone per-entry tuning**, and it does not. **The cancellation is exact
on paper and unreachable on hardware past some distance from the root.**

So:

* **near the root it works** — a drum kit (one sample per key, `root == key`,
  tuning ≈ 0) is unaffected;
* **far from the root the entry stops sounding** — and an 88-key Roland
  multisample import is exactly the far case, with roots spread across the
  keyboard.

*Caveats, theirs and kept:* the measurement was their own bank on a K2000R,
not a Roland import through the machine's own importer; the construction is
identical but the sample roots are not. And whether the firmware clamps the
value before storing it is unknown — theirs did not.

**This re-specifies rig question 1.** Do not only listen for pitch: listen for
**silence at the keys furthest from each zone's root**, and read the stored
`tuning` back. `−9200` with a silent key means the K2000's importer ships the
same defect; a railed value means the firmware guards what their writer did
not, and that rail is worth knowing.

**The buffer identity, for the record, is the same memory.** The fill's
base register is set at `0x16A5B6` — `movew #23696,%d5`, i.e. `a5@(0x5C90)` —
which is the same global the converter indexes at `0x16A356`, both with
`mulsw #42`. `mpc2emu` had reasoned the other way (that the nonsensical sum
implied two different structs) and offered it as a bet rather than a finding;
the bet loses.

**What the conflict reduces to is write order, and there is a second writer.**
`a5@(0x5C90)` is *set* at `0x16BC38`, and the region `0x16BCFC`…`0x16BF4E`
contains eight more `mulsw #42` sites — a whole second body of code indexing
these records, in the disc-walk/browser area, which this trace had not seen.
So the value the fill reads at `+10 + 2z` depends on which writer ran last,
and only one of the two has been traced.

That is a bounded piece of work and it is the next step, but it is **not**
done, so neither reading is adopted and the value test below stays unrun.

Until that is settled there is no way to know which word the discriminator
should read, so it is not run. Guessing here would be the third wrong reading
of this one function in a day.

**Once it is settled, the test needs no rig:**
if `record_word[10 + 2z]` rises ~100 per key across consecutive keys, the sum
is constant and the import is pitch-flat; if it is constant, the −100/key ramp
survives into the keymap. That is a measurement on an S-7xx ISO, and it
supersedes §6c question 1's framing.

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

## 6b-bis. MEASURED ON THE MACHINE, 2026-09-21

Jan loaded two Gigapack CD 1 drum-machine kits through the K2000R's own Roland
importer (`DMa:K-Dr.Rhy55 2` → 200, `DMa:K-Rhythm 33` → 300) and the objects
were read back over SysEx. **Everything below is the instrument's own bytes.**

### The `0x17` question, closed

```
keymap header (DUMP):  0x0000 0x0017 0x0000 0x0064 0x007f 0x0006 0x0010
                       sampleId method basePitch cents entriesPerVel entrySize Level[0]
```

**`method = 0x0017`, `entrySize = 6`**, object size 796 = 28 + 128 × 6. So the
importer *does* write six-byte entries, as the `base + 6 × index` arithmetic
said and as `mpc2emu` predicted on the record beforehand. **Where the header
gets written is still not found in the firmware** — four searches failed — but
that is now a curiosity, not a blocker.

### The tuning construction, confirmed exactly

Every imported sample came in rooted at **60**, so the roots do not track the
keys and `mpc2emu`'s void-check does not apply. Program 200's keymap is the
pure ramp:

```
entry 24 key 36   tuning +2400   sample 200 root 60   (60−36)×100 = 2400
entry 25 key 37   tuning +2300   sample 201 root 60              = 2300
entry 26 key 38   tuning +2200   sample 202 root 60              = 2200
entry 30 key 42   tuning +1800   sample 204 root 60              = 1800
entry 34 key 46   tuning +1400   sample 205 root 60              = 1400
```

Exact on every entry. **Program 300 confirms the other half**: its entries
deviate from the pure ramp by multiples of 100 (+300, +600, −200, +200, +500)
— the per-zone `coarse × 100 + fine` term. So
`tuning = record[+10+2z] + (root − 12 − I) × 100`, both halves visible at once.

### REFUTED by the machine: `lyr[8]` bit 5 is not unconditional

```
lyr[8] = 0x04    bit 5 CLEAR    bit 7 clear      (both programs)
cal[7] = 0       no second keymap → mono
```

§3 said both importers set bit 5 **unconditionally on every layer**. They do
not. Going back to the ROM after the dump: the `bset #5` at `0x16ADAA` sits
immediately after `movew %a1@,%a0@(136)`, the **second-keymap** assignment —
**inside the stereo branch**. The instruction was read without checking which
branch contained it.

So bit 5 is a stereo marker, which is what `mpc2emu`'s 86.4 % / 0.7 % split
said from their corpus. Three independent confirmations now: their corpus, the
ROM's branch structure, and a mono import that leaves it clear.

### Confirmed, and not exercised

* **all eleven segment tags** at the predicted offsets;
* **`cal[11]` = 200 and 300** — `mpc2emu`'s field name, this project's ROM
  offset, the machine's bytes;
* `lyr[5]` = 0 → velocity marks lo 0 / hi 7, full range, right for a kit;
* the **±7 pan** was *not exercised*: `cal[7] = 0`, no stereo pair, so
  `0x53 body[2]` and `body[13]` are both 0. Not tested rather than refuted.

### An oddity worth chasing

**Entries 0–8 of both keymaps hold `tuning +4352, vol −44, sample 16582`** —
an invalid sample id (the importer caps ids at 999, so this is junk rather
than a mis-pointer), identical across all nine, in the region GLM's fill
document predicted would be a boundary copy of entry 9. Entry 9 is zeros, so
it is not that.

**And they are reachable.** The layer's key range is `lyr[3] = 12`,
`lyr[4] = 108` in both programs, and entry `i` sounds at key `i + 12` — so
entries 0–8 are keys **12–20**, inside the layer's own span. An imported kit
has nine playable keys pointing at a sample that does not exist.

`mpc2emu`'s writer will not emit this state: `_build_keymap_entries` ends with
a two-pass hole fill (forward, then backward for leading holes) so that no
entry ever names a dead object. **So the K2000's own importer produces a state
a sibling project deliberately avoids.**

**Tested on the instrument, 2026-09-21, with Jan's authorisation.** A control
note at key 36 (entry 24, sample 200 — a real object) followed by keys 12…20
one at a time, each with an ALLTEXT liveness read between:

```
note 36  CONTROL            alive: 'ProgramMode  Xpose:0ST  <>Channel:9'
note 12  entry 0  dangling  alive
…                           alive
note 20  entry 8  dangling  alive
```

**No hang, no loss of response, on any of the nine.** The instrument answered
normally after every note and after the panic.

Two things about the design, both `mpc2emu`'s:

* the liveness poll is the **same family of probe** that was root-caused as
  the cause of a K2000 lockup during deletes (§9), so had it hung, the cause
  would have been ambiguous between the dangling entry and the poll. The right
  design is two passes — notes alone first, notes-plus-poll second. **It did
  not bite here because nothing failed**, and the poll being present makes the
  negative *stronger* rather than weaker;
* the audible result is Jan's to report, not this session's: **no hang is not
  the same as no defect**, and a wrong sample or a stuck voice would still be
  a finding.

**The audible result: keys 12–20 silent, key 36 plays.** First from the
scripted run — one sound across the whole sequence, which the ordering made
the control — and then **confirmed by Jan playing the keys manually**, which
is the reading that counts: it depends on neither the channel this session
guessed, nor the note timing, nor the sequence order. The control at key 36
maps to sample 200, a real object, and sounds; the nine dangling keys do not.

So the complete answer is the benign one, and every part of it is measured:

```
control key 36   -> sounds         confirmed twice: scripted and by hand
keys 12..20      -> silent         confirmed twice; the engine ignores a dead id
all nine         -> no hang        with the 2-3 s-class poll running against it
```

**The K2000 ignores a keymap entry pointing at a nonexistent object.** The
importer's dangling entries are a cosmetic defect, not a hazard — nine dead
keys at the bottom of every imported kit rather than a crash. `mpc2emu`'s
hole-fill guard still buys something the K2000 does not: a hole that inherits
its neighbour's sample plays *something musical* where this plays nothing.

## 6b-ter. BOTH OPEN QUESTIONS ANSWERED, 2026-09-21

Jan imported five more patches, each to its own bank. Every claim below is
read off the instrument.

### The gate: confirmed on both arms

| Program | material | gate | keymap tuning |
|---|---|---|---|
| 200 `DMa:K-Dr.Rhy55 2` | kit | `0` | `+0 … +4352`, many distinct — **the ramp** |
| 300 `DMa:K-Rhythm 33` | kit | `0` | `+0 … +4352` — the ramp |
| 400 `TOM:K-Tom 4 st` | kit | `0` | `+0 … +4352` — the ramp |
| **500 `BA1:Hot-st-Bass`** | **pitched** | `8` | **`+0`, one distinct value, 0 steps of −100** |
| **600 `BA1:Stereo-Bass`** | **pitched** | `8` | **`+0`, one distinct** |
| **700 `SYN:StereoSound`** | **pitched** | `8` | **`+0`, one distinct** |
| **800 `BA1:MC-202`** | **pitched** | `8` | **`−134`, one distinct** |

**The cancellation is withheld on pitched material.** And `BA1:MC-202` is the
best single data point in the whole investigation: a **constant −134 cents**
across all 64 entries. Non-zero, so the per-zone **tuning base
`record[+10 + 2z]`** is demonstrably present; constant, so the per-key
`(root − 12 − I) × 100` term is demonstrably absent. **The two halves of the
formula, independently controlled, in one object.**

#### Corrected, and then settled on the disc itself

This first read *"non-zero, so the per-zone `coarse × 100 + fine` term is
demonstrably present"*. **That was wrong, and the disc says so.** The base has
three summands, `coarse × 100 + fine + record[+38]`, and a measured total of
−134 identifies none of them on its own.

So the source record was read — `BA1:MC-202` is on **CD 2** at `0x1E1600`,
partial index 368 (`(0x1E1600 − (0x1D5600 + 0x800)) / 128`), the only patch of
that name on either disc:

```
name: "BA1:MC-202    AA"
zone 0: 3a 02 08 7f 00 00 00 01 00 7f 00 00 00 7f 7f ff
        sub[2] gate   = 8     -> pitched, matching the import
        sub[5] coarse = 0
        sub[6] fine   = 0
zones 1-3: sub[0..1] = ffff -> unused
```

**`coarse × 100 + fine = 0`.** The −134 therefore comes *entirely* from
`record[+38]`, and the sentence above had attributed it to the one term that
provably contributes nothing here. `+38` is a real, independent summand
carrying a non-zero value on real material — not a term that could be dropped
as always-zero, which is exactly how it got lost downstream (see
`RESOLUTION_NOTES` §"sixth shape").

Note what this does **not** establish: where `+38` is filled from. It is a
field of the staging structure the disc walk builds, and −134 (`0xFF7A`
signed) appears nowhere in this 128-byte record, so it is computed or fetched
from elsewhere. That is an open item, now with a known worked example to test
any answer against.

The surviving claim from Program 300 — deviations from the pure ramp in
multiples of 100 — is consistent with a non-zero `coarse` there, since `fine`
would contribute the non-multiples. It is not proof of which summand moved,
and is not read as such.

### The ±7 pan: confirmed

```
stereo imports (400, 500, 600, 700):  0x53 body[2] high nibble = 7
                                      0x53 body[13] bits 4-7   = 9   (= −7 signed)
mono imports   (200, 300, 800):       both 0
```

**+7 and −7, in the same layer** — which also settles the framing: the pair is
*within* one layer, not spread across a partner layer, as §3's corrected
reading said.

### `lyr[8]` bit 5: the stereo marker, both arms measured

```
stereo: 0x24  bit 5 SET    (400, 500, 600, 700)
mono:   0x04  bit 5 clear  (200, 300, 800)
```

Perfect correlation across seven imports. `mpc2emu`'s corpus split, the ROM's
branch structure, and now both arms on hardware.

### The header does not describe the body — and that is not the machine's bug

Every imported keymap header says `entriesPerVel = 127` — 128 entries — and
`entrySize = 6`, implying **796 bytes**. The objects are not that size:

```
km 200/300/400   796 B   OK
km 401/402/403   668 B   header implies 796
km 600/601/800   412 B   header implies 796
km 500/501/700/701  156 B   header implies 796
```

**Nine of thirteen are short.** Reading entry 127 of a 156-byte keymap runs
640 bytes past the end of the object.

**This was first written up here as a defect of the K2000's importer. It is
not, and `mpc2emu` corrected the framing:** a declared count that does not
describe the object is normal for a format whose **object size is
authoritative**, and the machine plainly walks its own objects by size. The
header field declares a *layout*, not an extent. What is wrong is a reader
trusting the wrong one of the two — and the reader that did was theirs, not
the instrument.

They found it in `_decode_table`: the entry loop ran `entriesPerVel + 1` with
no bound against the object, and the `table_size` it was handed was computed
and never used — so a 156-byte keymap declaring 796 built zones out of the
*next object's* bytes, silently, because `unpack_from` raises at the end of
the file and not at the end of an object. Now bounded by
`min(declared, (object_end − table_addr) // entry_size)`, with a warning that
names the declared size against the real one. Three tests, two of which fail
against the unbounded version.

**And the prevalence is the point: zero of their 1156 corpus keymaps do this.**
No amount of reading saved banks could have found it. It needed the
instrument, on exactly the path a user takes — import a Roland disc on a
K2000, save, convert.

It does *not* contradict their corpus finding that `entriesPerVel` is always
127. It is 127 here too. **The entry count varies anyway**, with no field
describing it.

## 6c-bis. Named objects for what is still open

The two remaining questions need *material*, not more rig time, and both are
satisfied by **one 54 K import**:

| Object | Disc | Size | Why |
|---|---|---|---|
| **`BA1:Hot-st-Bass`** | **CD 2** | **54 K** | one partial, **two used zones, both gate `8`** — pitched, so the cancellation must be *withheld*; and stereo-named, so the pair should make the K2000 write a second keymap and the ±7 pan |
| `BA1:Stereo-Bass` | CD 2 | 198 K | same shape, 2 partials × 2 zones — the backup |
| `SYN:StereoSound` | CD 2 | 108 K | second backup |
| `BA1:MC-202` | CD 2 | 27 K | minimal **pitched-only** fallback: one zone, gate `8` |
| `TOM:K-Tom 4 st` | CD 1 | 234 K | stereo **fixed-pitch**, if the two arms ever want separating |

**What `BA1:Hot-st-Bass` predicts**, so the result is falsifiable either way:

* **tuning words roughly constant, not ramping −100/key.** Both its zones
  carry gate `8`, which skips the root-key term. A ramp here refutes the gate
  reading measured across 32,000 zones;
* **`cal[7]` non-zero** — a second keymap — and **±7 in `0x53 body[2]` /
  `body[13]`** of the two layers, with opposite signs. The mono kits left
  those at 0, so this is the first chance to exercise them at all.

*Stated as a caveat, not smuggled:* "stereo" in the name plus two used zones is
**suggestive, not proof**. The two zones could be a velocity split or a plain
layer pair. `cal[7]` coming back non-zero is what would confirm a stereo
import, and that is an outcome of the test rather than a precondition for it.

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
