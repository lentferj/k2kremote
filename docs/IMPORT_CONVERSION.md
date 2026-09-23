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

**This is where a real parameter table has to come from**, and finishing it
needs the Kurzweil *keymap zone* layout — which sibling project `mpc2emu` owns
and has validated over thousands of programs. That is the one dependency this
document is waiting on; everything above it was derivable here.

## 7. Method

Every offset above is either an instruction in the ROM or a measurement on a
real `.KRZ`, and where both exist they agree. Two rules were applied
throughout, both learned the hard way on the Roland disk walk:

* identify by a **relation** several values must satisfy at once, never by one
  plausible position — the keymap offset holds in 10 of 10 programs *and* at
  `+224` and `+448` in the multi-layer ones;
* a field that barely varies cannot validate anything downstream of it.
