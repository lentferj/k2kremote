<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# The K2000's third-party importers, read out of the firmware

*Mostly Roland; the format detection covers Kurzweil, Ensoniq and Akai too.*

The K2000 loads Roland S-7xx disks — "Reading Samples", Musician's Guide 15-32.
This is that code, read out of the v3.87J ROM
(`~/temp/k2k_fw/k2000_v387j.bin`, 1 MiB, 68000, **mapped at `0x100000`**, so
file offset = address − `0x100000`).

**No hardware was used.** Every claim here is either an instruction sequence in
the ROM or a byte measured on a real Roland disc, and the two are cross-checked
against each other. The corpus is `~/Dokumente/SYNTHS/Roland Samples`: three
S-7xx CD-ROMs so far — Gigapack I CD 1 and CD 2 (`SYS-772 HardDisk Sys Ver.
1.04`) and L-CDP-05 Solo Strings Vol 1 (`Ver. 2.19`), all three `S770 MR25A`.

Tools: `m68k-linux-gnu-objdump -D -b binary -m m68k:68000 --adjust-vma=0x100000`.

## 1. How the K2000 decides what kind of disk it is looking at

`0x11C660` is the mount. It sets a format code in `a5@(0x14AA)` by running
sniffers over sector 0 in a fixed order, first match wins:

| Order | Sniffer | Format | What it tests |
|---|---|---|---|
| 1 | `0x16A234` | **4 — Roland** | sector 0 bytes 4, 5, 7 = `S`, `7`, `0` |
| 2 | `0x167C78` | **1 — Kurzweil** | sector 0 bytes 3…6 = `KMSI`, the FAT OEM field |
| 3 | `0x165130` | **3 — Ensoniq** | see below |
| 4 | `0x171AC6` | 5 — device-level | no sector test at all: `0x1866F0(drive)` |

Format `4` is Roland on two independent grounds: the sniffer's own byte tests,
and the macro entry's source field, whose format byte reads `4` for a Roland
object (`docs/MAC_FORMAT.md` §3).

The **Ensoniq** sniffer first *excludes* — `KMSI` at 3…6, or an x86 jump
(`0xE9`/`0xEB`) at byte 0, which is how every DOS boot sector starts, both
return "not mine" — and then scores a signature, differently per medium:

* SCSI: reads **sector 1** and scores `[30] == 0xFF`, `[38] == 'I'`,
  `[39] == 'D'`; two of three is enough.
* Floppy: scores six byte constants in sector 0 (`[1]=0x80`, `[2]=0x01`,
  `[5]=0x0A`, `[7]=0x02`, `[9]=0x50`, `[12]=0x02`).

**Checked on a real EPS disc** (`CDR-1 (EPS).iso`): sector 1 holds
`FF "CDRM001ID"` at offset 30, so all three SCSI tests hit — `0xFF` at 30,
`I` at 38, `D` at 39.

**Format 5 is the AKAI path** — identified 2026-09-21. It takes a drive
number, probes the device (`0x1866F0`) and never looks at a sector, which is
why it looked like a device probe rather than a signature test: **an AKAI
S1000/S3000 hard disk is selected by partition letter, not by a magic
number.** The evidence:

* `0x12A714`: `moveb %a0@(30),%d0` / `extw` / `addiw #-65` — a byte read and
  **`'A'` subtracted**, i.e. a partition letter `A`, `B`, `C`… turned into an
  index. Negative means no partition;
* that branch falls into `0x12A730`, `pea 0x18D4B1` → the string
  **`"Akai partition not found."`**;
* the other AKAI string, **`"No Akai sample files found."`**, is at
  `0x18C0AB`;
* it all sits in the same region as the format-5 tests (`0x12AADC`,
  `0x12AAE2`, `0x12B0E8`, `0x12BC3A`).

**And there is no AKAI sniffer, because there is nothing to sniff.** The mount
writes only `0`, `1`, `3`, `4` and `5` into the format code — `movew #1` at
`0x11C908`/`0x11C98A`/`0x11CA56`/`0x11CB68`, `#3` at `0x11CAF2`/`0x11CB7E`,
`#4` at `0x11CB4C`, `#5` at `0x11CB98`, `clrw` elsewhere. **Nothing anywhere
writes 2**, although two sites test for it. Format 2 remains unassigned by
this path.

### The AKAI dispatch is by file type, not by disc format

`0x16368A`, the Akai program builder, has **exactly one caller** in the image:
`0x1221AA`. It is guarded by

```
0x12218E:  cmpiw #3,%a5@(0,%d2:l)      ; a per-FILE type code, not the disc format
0x1221AA:  jsr 0x16368A
```

so an AKAI program is built when a *file* in the mounted partition carries
type 3 — a sibling of the `cmpiw #5` branch a few instructions later and the
`0x1652FC` builder above it. **The disc format selects the partition; the file
type selects the builder.** That is why the Akai arm takes a staging record
rather than reading the disc itself, and it is the entry point for the
remaining fill-path work (`O6`).

### The Roland sniffer is three byte compares, not a string

```
0x16A234:  n = 0
           if (sector0[4] == 'S') n++
           if (sector0[5] == '7') n++
           if (sector0[7] == '0') n++
           if (n != 3) return 0
```

**Byte 6 — the model digit — is deliberately not tested**, so this matches
`S770` and `S750` alike. That is why there is no `S770` string anywhere in the
ROM, and why searching for one finds nothing.

A three-byte compare that spans two models is exactly the shape that later
turns out to be per-model, so it was checked: the only `cmpib #'7'` in the
whole image is this sniffer, there is no `cmpib #'5'` anywhere, and nothing
downstream reads sector 0 byte 6. On this evidence the Roland path is one
implementation for both models — but the check is worth repeating against an
S-750 disk if one ever turns up, since absence of a compare is weaker evidence
than a compare would be.

## 2. The five counts in sector 0

Having matched, the sniffer reads five 16-bit values through the helper at
`0x1698AE`, which is a **little-endian** reader (`p[1] << 8 | p[0]`) — the
68000 is big-endian and Roland is not:

| Sector-0 offset | Global | Meaning | Measured on CD 1 |
|---|---|---|---|
| `0x114` | `a5@(0x5CA4)` | Volumes | 122 |
| `0x116` | `a5@(0x5CA6)` | Performances | 269 |
| `0x118` | `a5@(0x5CA8)` | Patches | 889 |
| `0x11A` | `a5@(0x5CAA)` | Partials | 4004 |
| `0x11C` | `a5@(0x5CAC)` | Samples | 5761 |

The object browser (`0x16BB0A`) caches four of them — Volume, Performance,
Patch, **Sample** — and re-reads its listing when they change. It never uses
Partials: the K2000 offers exactly the four types the manual names.

**Validated against the discs, not assumed** — see §3, where all five counts
are checked against the records themselves on three different discs.

## 3. The directories are at hardcoded offsets

`0x169960` is a jump table on the object type:

| Type | ROM's base | Records actually start |
|---|---|---|
| 0 Volume | `0x000A0600` | `0x000A0800` |
| 1 Performance | `0x000A1600` | `0x000A1800` |
| 2 Patch | `0x000A5600` | `0x000A5800` |
| — Partial (no table entry) | `0x000AD600` | `0x000AD800` |
| 3 Sample | `0x000CD600` | `0x000CD800` |

Each area opens with a **`0x200` header** and the records follow — uniformly,
all five. The K2000 has no jump-table entry for Partials, which is why it
offers exactly four object types; the Partial base above is measured from the
discs, not read from the ROM.

Records are **32 bytes** (`index << 5` in three separate places), and the
loader reaches them by seeking the whole disk as a pseudo-file: it opens the
name `ROLAND.S` (`0x17562E`), then seeks with `0x175418` and reads with
`0x175D86`. `ROLAND.S` is *not* a file on the Roland disk — nothing on either
CD carries that name — it is how the K2000's own file layer is asked for the
raw volume.

### Record layout, as the ROM reads it and the disk confirms

```
+0x00  16  name, ASCII, space-padded      "   :Sound&Vision", "KIT:REAL m *1-16"
+0x10   1  class tag                       0x40 Volume · 0x41 Performance
                                           0x42 Patch  · 0x43 Partial · 0x44 Sample
+0x12   2  LE16   id / forward link
+0x14   2  LE16   backward link (0xFFFF on the first record)
+0x16   2  LE16   index
+0x1E   2  LE16   size, read at 0x169A3E and scaled by 9 × 1024
```

The listing code copies the 16 name bytes verbatim (`memcpy` of 16 at
`0x169A2E`), appends a space, then formats the size — so the K2000 shows a
Roland object under its own name, untranslated.

### Checked properly, on three discs

The assertion is not "does a record here look like a record". It is: walking
exactly `count` records of 32 bytes from `base + 0x200`, **every** one carries
that class's tag, and the record just past the end is empty. A wrong base
cannot satisfy that for five classes at once.

| Disc | Sys | Volume | Performance | Patch | Partial | Sample |
|---|---|---|---|---|---|---|
| Gigapack I CD 1 | 1.04 | 122 | 269 | 889 | 4004 | 5761 |
| Gigapack I CD 2 | 1.04 | 75 | 147 | 916 | 2880 | 4128 |
| L-CDP-05 Solo Strings | 2.19 | 13 | 53 | 200 | 1169 | 890 |

Fifteen directories, all five classes on each disc: tags all match, counts
equal the header's own numbers, terminator empty. Three different media and
two different `SYS-772 HardDisk Sys` versions, so the agreement is not one
disc counted three times.

### The trap this walked into first

An earlier reading of this had the Volume, Patch and Sample bases `0x200` low
but the **Performance** base landing exactly on a record — `KIT:REAL m *1-16`
at `0x0A1600`, a real, 32-byte-aligned, properly named record. It is a
**Volume** record. Gigapack CD 1 has 122 volumes, whose run ends at
`0x0A1740`, so `0x0A1600` is still inside the volume directory: the wrong base
landed on a valid record of the wrong class, and the exception it seemed to
prove was an artefact of that one disc's size.

Checking the **class tag** is what catches it, because the tag is a relation a
wrong base cannot satisfy, where "this looks like a name" is not. The sibling
`eosed` session hit the identical failure twice the same night on the EOS ROM —
a wrong base offset yielding real field names — and caught it the same way.
One constant wrong everywhere also beats three-right-and-an-exception: an
exception was the signal that the reading was wrong, not that the format was
irregular.

## 4. Where the mapping lives

`0x16A2CC` onwards converts a Roland record into Kurzweil terms. The first
piece of arithmetic found there (`0x16A40A`):

> ### RETRACTED later the same day — this section's central gloss is wrong
>
> **`src[5] * 100 + src[6]` is not an object id. It is a tuning in cents**,
> `coarse × 100 + fine`, and the third term is not a bank base but
> `record[+38]`, a per-record cents base. The full law, hardware-confirmed on
> seven imports and disc-confirmed on one:
>
> ```
> +2  + 2z   the Kurzweil Sample object id   <- the id lives HERE
> +10 + 2z   a tuning in cents = coarse*100 + fine + record[+38]
> +38        a per-record cents base
> ```
>
> The `× 100` was read as a bank multiplier when it is cents-per-semitone.
> The id has its own field two words earlier, so `+10 + 2z` never needed to
> be one. See `IMPORT_CONVERSION.md` §5 for the retraction and §6b-ter for
> the measurement; `BA1:MC-202` (CD 2, `0x1E1600`) has `coarse = 0`,
> `fine = 0` and a measured `−134` cents, which comes entirely from `+38`.
>
> **This gloss went uncorrected here for a day after it was retracted
> elsewhere**, and it supplied the premise for two further errors. It is left
> in place below rather than deleted, because it is the mistake the rest of
> the investigation was spent unwinding.

```
dest_id = src[5] * 100 + src[6] + bank_base
```

— ~~a Roland bank/number pair turned into a Kurzweil object id, offset by the
bank the user chose in the load dialog~~ **(retracted — see the block above)**.
That is the shape the rest of the mapping will take, and it is the part worth
having: the disk walk above is re-derivable from format notes, but *what
Kurzweil decided a Roland parameter means* exists only here.

### What the converter builds, per patch

`0x16A2CC` seeks with `index << 7` — Roland patch data is **128 bytes** — and
then fills a per-patch structure four times over (`cmpiw #4` at `0x16A452`):
**four zones per patch**, which is the shape a Roland Patch's partials arrive
in. Per zone `i`:

```
dest[0x0A + 2i] = src[5] * 100 + src[6] + bank_base   ; RETRACTED: not an id,
                                                     ; a tuning in cents, and
                                                     ; the 3rd term is +38
dest[0x12 + 2i] = src[2]        (word)
dest[0x1A + i]  = src[7]
dest[0x1E + i]  = src[9]
dest[0x22 + i]  = src[4]
```

### The two templates

The program builder (`0x1641BC`…`0x164A4E`) starts by fetching a **live
Kurzweil object**: `0x1645E2` calls the object lookup with type `132`
(Program) and id `199` — the manual's "layers have the same settings as
Layer 1 of Program 199" (15-31), confirmed in code rather than taken on the
manual's word. The keymap side uses a **ROM prototype**: a "New Keymap"
template object at `0x1888E4`, referenced nine times across the importer.

**There are three ROM prototypes, not two.** The sample path clones a third at
**`0x188436`**, named **`"Abcdefghijkl"` — twelve characters**, with header
words `0058`/`0010` against `00AE`/`000E` for the other two, so it is a
differently shaped object and not just a wider name:

```
0x188436   9800  0058  0010   "Abcdefghijkl"   cloned at 0x169C20 (sample path)
0x18862A   9401  00AE  000E   "New Sample"
0x1888E4   9401  00AE  000E   "New Keymap"
```

See `IMPORT_CONVERSION.md` §"Still loose" — the third prototype makes one of
the four negative searches a claim stated over an incomplete enumeration.

So an imported object is a clone of a template with the imported values
written into it — which is exactly why the drop list matters: any field the
importer never writes keeps Program 199's value, and that is indistinguishable
from a deliberate choice unless you have read the code.

### Still unknown

The per-parameter mapping itself: envelopes, filter settings, key ranges,
velocity switching, stereo pairing. Where to look, in the order that repaid the
sibling `eosed` project doing the same job on the E-mu EOS ROM today:

1. **Lookup tables, not formulas.** EOS converts AKAI envelopes with a
   100-entry byte table and computes no time at all; weeks had gone into
   fitting a law to a quantity the firmware never computes. If the K2000 has
   tables, they are the deliverable.
2. **Hardcoded constants** written unconditionally — they explain corpus-wide
   patterns that look like properties of the source material and are not.
3. **What the importer drops.** Decidable from the code by enumerating the
   source bytes it reads and taking the complement, and invisible to any
   agreement metric, because two converters that both write a constant agree
   perfectly.
4. Exact arithmetic, including the truncation, for the few things that really
   are formulas.

## 5. Method notes

* Identify a field by a **relation** several fields must satisfy at once, never
  by a single plausible-looking position: an off-by-a-few base offset produces
  one field that fits and is wrong.
* A source byte that barely varies across the corpus cannot validate anything
  downstream of it. Count distinct values before believing an agreement.
* "My search did not find a reference" is not "the program does not read it" —
  an address kept in a register across several uses shows up once.
* A count in a header need not describe the body that follows it.

## 6. Status

Reconnaissance and the disk walk, done offline. The parameter mapping is
**not** done. `TODO.md` carries the open steps; the Akai side has its own
prerequisite, `~/git-repos/mpc2emu/docs/AKAI_S3000_FORMAT.md`, which is
validated against thousands of real library programs and should be read before
any of the K2000's Akai path is re-derived.
