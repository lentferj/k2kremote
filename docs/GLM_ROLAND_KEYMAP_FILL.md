<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# The Roland keymap fill, decoded (GLM-5.3-Flash, 2026-09-21)

> ## Checked 2026-09-21 — the two load-bearing claims hold, and one of them
> ## overturns a finding of ours
>
> Verified at the cited addresses in the v3.87J ROM:
>
> * **The 88-key loop is real.** `0x16AB28`: `addqw #1,%sp@(250)` /
>   `cmpiw #88,%sp@(250)` / `bltw 0x16A7A4` — and `0x16A7A4` is exactly where
>   `moveq #9 / addw %sp@(250)` computes the entry index. So `I = 9 + key`
>   over 0…87, **not** `9 + zone_counter`. `IMPORT_CONVERSION.md` said the
>   latter and has been corrected; the error had already been relayed to
>   `mpc2emu` as a resolution of their tuning objection, and that has been
>   withdrawn.
> * **The type-134 lookup is real.** `0x16A874`…`0x16A89E`: the record's
>   sample-reference word goes to `find_object(134, id)`, then `0x10B90A`
>   for the body, then `moveb %a0@(12)` — `A` is byte 12 of *that object's*
>   body, not a staged record byte, exactly as claimed.
>
> **What is verified versus inferred.** The address arithmetic, the loop
> bound, the fetch and the byte offset are all confirmed instruction by
> instruction. Calling type 134 "the Sample" is an interpretation — our
> vendored enum names it `Soundblock` — and "`A` is the root key" is an
> inference from the arithmetic's shape, not a reading of the object. Both
> are for `mpc2emu` to confirm against their Sample-object layout.
>
> Unchecked here, and flagged as such rather than endorsed: the boundary-copy
> claim (entries 0–8 and 96–127) and the `0x16C5B8`/`0x15390C` volume chain.
> The `cmpiw #127` loop at `0x16AB20` is consistent with the boundary copies,
> which is corroboration and not confirmation.
>
> ### Re-checked 14:45 — two upgrades and one refutation
>
> **§5's record map is now CONFIRMED, and it was right where we were wrong.**
> It lists `+2 + 2z` as the sample id and `+10 + 2z` as the tuning source.
> `IMPORT_CONVERSION.md` §5 had called `+10 + 2z` "a Kurzweil object id"
> — an unverified gloss of `src[5]*100 + src[6]`, which is `coarse × 100 +
> fine`, cents. That gloss then supplied the premise for two further wrong
> readings here before it was checked. **This document had the field right
> from the start.**
>
> **§2's conditional is confirmed and matters more than it was given credit
> for.** At `0x16A870`/`0x16A872`: `andw record[+18+2z],#0xFF00` / `bne
> 0x16A8DA` — if the high byte is non-zero the whole root-key lookup and the
> `(A − 12 − I) × 100` term are **skipped**. And the gate's source is traced:
> `0x16A44A` writes `record[+18 + 2z] ← src[2]`, a word from the **Roland
> partial data**. So the K2000 does **not** cancel key-tracking
> unconditionally — it is gated on a byte the disc supplies.
>
> **§3's musical conclusion is REFUTED by hardware.** It argues the ramp
> "*flattens* each key to its own sample's pitch rather than silencing high
> keys, because the keymap's own per-key transposition and the tuning offset
> then cancel". `mpc2emu` measured the identical construction on a K2000R:
> applied to pitched material it drove high keys to −72 semitones and they
> **went silent**. The sum is zero in arithmetic, but reaching it needs the
> engine to deliver a −92-semitone per-entry tuning and it does not — the
> cancellation is exact on paper and unreachable on hardware far from the
> root. Near the root (a fixed-pitch drum map, `root == key`) the construction
> is correct and appears in real third-party banks.
>
> That is the reasoning-that-fits shape once more, and it is instructive that
> it appears in the document that got everything it read off the code right:
> **the refuted paragraph is the one that left the disassembly and reasoned
> about music.**
>
> **This document read the code and the code held.** That is now the second
> external file to correct this project on a point where our own reading had
> stopped one instruction short — and the first where the correction reversed
> a conclusion we had already passed to a sibling project.

External session file, offline — no hardware. This completes the
`IMPORT_CONVERSION.md` §6a zone fill (`0x16A7DC…`) the way the document was
heading: every entry byte now has a source, the boundaries of the fill are
established, and the tuning formula's shape resolves the §6c question 1
reading from the ROM side. All addresses are v3.87J load addresses
(file offset = address − `0x100000`).

## 1. The fill is per-key, 88 keys wide, with copied boundaries

`IMPORT_CONVERSION.md` described the source as "42-byte records" taken by
pairs. The structure around it decides what those pairs are:

* A **word table of 88 entries** at the caller's frame (`sp@(68)…`, walked as
  `0..88`) maps each key to a **42-byte record index**; `-1` means no record.
* The outer loop walks the table (`addqw #1,%sp@(250); cmpiw #88` at
  `0x16AB28`), re-entering the fill at `0x16A7A4`; the inner staging counter
  is `sp@(248)`.
* **If no key of the 88 has a record, the patch's zone slot is written `-1`
  and the zone is empty** (`0x16A62A: movew #-1,%a0@`) — that is the
  no-zone representation, not a zero-filled zone.
* The entry index written is `I = 9 + key` (`0x16A7A4: moveq #9; addw
  %sp@(250)`) — **the fill covers entries 9–95 only, the 88-key piano
  range, at keys 21–107.**
* When the running index reaches 9, the same staged values are written to
  **entries 0–8** (`0x16A9F6`: `cmpiw #9` → writes with `%a2@` counting 0…8,
  then stops at 9); when it reaches 95, `a2@` is loaded with **96** and
  entries **96–127** are written with the last record's values
  (`0x16AA8E`/`0x16AA98`). So the keyboard's bottom 9 and top 32 entries are
  boundary copies of the outermost keys' records — which is how an 88-key
  source becomes a 128-entry keymap.

This settles the prototype-size question from a different direction than the
header search: a full 88-key import touches entries 0–127 — 128 six-byte
entries plus the 28-byte header, consistent with the 820-byte method-`0x17`
object — and the fill itself, not a second prototype, decides the content.

## 2. The entry write, in `0x17` field order — complete

Every write is `body + 6·I` (the stride confirmed: `d0=2i; d0+=i; d0+=d0`),
and the six writes in address order are:

| entry offset | staged from | meaning (`0x17` field) |
|---:|---|---|
| `+3`, `+4` | record word `+2 + 2z`, high then low | **sampleID** i16 |
| `+2` | the `0x16C5B8` converter | **volumeAdjust** i8 |
| `+0`, `+1` | record word `+10 + 2z`, adjusted | **tuning** i16 |
| `+5` | constant `1` | **subSample** u8 |

with one branch: when `record[+18 + 2z] & 0xFF00` is **non-zero**, the
tuning fetch is skipped and `+10 + 2z` is written raw (`0x16A85C`…
`0x16A872`; the `bnes` jumps past the fetch to `0x16A8DA`). So the high byte
of the flag word at `+18 + 2z` means **"this word is already final"** — a
per-(record, zone) flag on the tuning source.

## 3. The sample reference is a type-134 lookup, and the pitch comes from its body

When the adjustment branch runs (`0x16A874`):

```
word  = record[+2 + 2z]              ; the SAMPLE reference
obj   = find_object(134, word)       ; 0x1032ea — type 134, the Sample
A     = obj_body[12]                 ; one byte at body +12
tuning = record_word[+10 + 2z] + (A − 12 − I) · 100
```

Two corrections to the current text, both verifiable at the cited addresses:

* **`A` is not "a staged byte" of the record — it is byte `+12` of the body of
  the Kurzweil Sample object whose id is `record[+2 + 2z]`** (type 134, not
  133; `0x1032ea(134, id)` then `0x10B90A` "body of object"). The Roland
  patch's partial sample reference is resolved to the *already-imported K2000
  sample* before its byte is read. What `body+12` is — mpc2emu's Sample-object
  layout names it — decides what the adjustment is keyed on.
* **`I` is `9 + key`, so it varies per key.** The current §6a text says
  "`I` is `9 + zone_counter`, not a key" and concludes the cents value is
  "constant across every entry of a zone". The loop counter feeding `I`
  (`sp@(250)`) is the 0…88 key counter — the same one that selects the
  record. So the arithmetic carries a **−100-per-key term by construction**,
  and whether the final tuning is constant depends entirely on the record's
  `+10 + 2z` word rising by ~100 per key in step.

That reframes §6c question 1, and it is checkable **without hardware**: the
discriminator is no longer "read the keymap's tuning words" but "read the
42-byte records' `+10+2z` words across consecutive keys". If those rise
~100/key (a per-key pitch, as an 88-note multisample's records would), the
sum is constant and the imported keymap is pitch-flat. If they are constant,
the K2000 ships the −100/key ramp — which under `centsPerEntry = 100`
*flattens* each key to its own sample's pitch rather than silencing high
keys, because the keymap's own per-key transposition and the tuning offset
then cancel. The ramp that mpc2emu flagged as the shape of a bug they fixed
is, read against an 88-key multisample import, the arithmetic that makes one
sound per key play at one pitch — the two uses differ, and the disc decides
which one this is.

## 4. The volumeAdjust chain

```
key      = (record[+12 + 2z] & 255) + 1
selector = record[+40] + 1
word     = 0x1835B0(key, selector) · 4     ; multiply helper
volAdj   = 0x16C5B8(word)
```

`0x16C5B8` in full (it is the last piece of the chain and it closes cleanly):
`src < 2 → −96`; otherwise it walks a counter from −96 upward, at each step
calling **`0x15390C(step)`** (the K2000's own level-step → value law),
returning the first step whose law value is `>= src`, capped at 96. So the
per-entry volume adjust is **the K2000's own dB-step scale applied to a
Roland-derived level** — not a formula fitted to the source, but a bracket
search on the destination's law. `0x15390C` is one function away from being
the same law `mpc2emu` models as `krz_db_to_level_pct` — tracing it is one
dump and would pin the exact step scale both projects are imitating.

## 5. The 42-byte record, as far as the reads establish it

| record offset | read as | use |
|---:|---|---|
| `+2 + 2z` (word) | a **K2000 Sample object id** (type 134 fetch) | entry sampleID |
| `+10 + 2z` (word) | tuning source | entry tuning, unless adjusted |
| `+12 + 2z` (byte) | lookup key | volumeAdjust chain |
| `+18 + 2z` (word) | flag | high byte set → tuning word used raw |
| `+40` (word) | selector | volumeAdjust chain |

with `z` the **partial/zone index 0–3** (`d6 = 2·fp@`, `fp@` the four-zone
patch loop). Four zone slots of three words each, plus a selector — 42 bytes
holds that with room for a name at `+26`, which the disc will confirm or
refute. The records are reached through the 88-entry per-key table, so the
next question is where that table's base comes from in the loader — the
records may be a staging array built during the disc walk rather than disc
bytes, which is exactly the distinction `ENSONIQ_ROLAND_IMPORT.md` learned to
test.

## 6. What this closes, offline

* **Question 1 is decidable from a disc**, not the rig: dump
  `record[+10+2z]` for consecutive keys on a real S-7xx ISO and see whether
  it rises ~100/key. The corpus is already mounted in `ROLAND_IMPORT.md`'s
  walk.
* The method-`0x17` header mystery gains a structural answer in the same
  register as the field order: the clone is created via `0x103310` (type 133)
  and the prototype copied — but the fill writes **six bytes per entry**, so
  whatever sets `method/entrySize` happens between clone and fill. If the
  header template is pushed as a *block* rather than written as constants —
  the `pea 0x190BF3` argument in the copy call at `0x16A726` is worth one
  look — the constant search that came up empty was looking in the wrong
  encoding for exactly that reason.
* The five hardware questions in §6c lose none of their value — but
  question 1's premise ("constant confirms, ramp refutes") should be restated
  as **two readings of the same ramp**: constant-final-tuning if the disc's
  per-key word tracks, ramping if it does not. The formula above is what the
  rig measurement will be compared against either way.
