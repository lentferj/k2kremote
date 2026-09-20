# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Known K2000 SysEx object fields — offset, meaning, decoded value.

The registry half of the pattern eosed's TUI uses (`eos/params.py`'s
`Parameter` dataclass + `describe_value()`), adapted for the K2000's
**offset-addressed** RAM objects rather than EOS's id-addressed parameters.
Everything here traces back to a `docs/RESOLUTION_NOTES.md` entry — this
module is that prose turned into something `k2kmon` can query, not a new
source of claims.

**Two different kinds of knowledge, kept deliberately separate — conflating
them would overclaim what this project has actually verified:**

* :data:`KNOWN_FIELDS` — fields whose byte **offset within a live object**
  was found by DUMP-diffing two panel-driven states (RESOLUTION_NOTES §30).
  These are the only entries safe to auto-decorate while browsing an
  arbitrary object, because the tool actually knows where to look.
* Standalone conversion functions below (e.g. :func:`filter_cutoff_byte_to_hz`)
  — a byte's *meaning* is verified, but its *offset* within a Program object
  was never mapped (CUTCAL set/read the filter cutoff byte via the panel's
  F1 FRQ page, never via DUMP). These are only ever applied to a byte the
  caller already knows the location of — never auto-detected.

Within :data:`KNOWN_FIELDS`, the byte<->value conversions themselves have a
further honesty boundary worth keeping visible rather than smoothing over:
the *exact* mapping was only ever established as a closed-form formula over
part of each byte's range, plus a handful of individually-verified spot
values (ceilings, mostly). The dense point-by-point tables from the RE
session that found this exist only in a chat transcript with a sibling
project, not in this repository — reconstructing them from memory here
would be exactly the kind of unverified claim this project has spent all
night catching in other people's work. :func:`decode` returns ``None``
for a byte outside a formula's *proven* range rather than guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple, Union

from k2000.definitions import ObjectType
from k2kremote.k2kromtables import (ENV2_FILFREQ_CT, FILTER_COARSE_HZ,
                                     LFO_PITCH_CT, LFO_RATE_CHZ)


@dataclass(frozen=True)
class Field:
    """One offset-addressed field this project has independently mapped."""

    name: str
    size: int
    unit: str
    notes: str
    #: raw bytes -> decoded value, or None if out of the formula's proven
    #: range (see module docstring). A decoder may return a preformatted
    #: string where the device's own display has fixed decimals that an int
    #: would lose -- `LFO1 MnRate` shows `2.00 Hz`, not `2 Hz` -- so the
    #: annotation is not `Optional[int]`, which is what it claimed while
    #: `_lfo1_mnrate_hz` had been returning `str` since the day it was added.
    decode: Callable[[bytes], Optional[Union[int, str]]]
    #: `(offset, predicate, why)` for a field whose meaning depends on
    #: ANOTHER byte -- the DSP block-type byte, in the one case that needs
    #: it. An ungated entry at such an offset is not merely imprecise, it
    #: prints a confident wrong number: Program 1 carries `SINE` in F1 and
    #: byte 0 at offset 210, which the cutoff law renders as a tidy
    #: "261.6 Hz" for a block that has no cutoff at all.
    gate: Optional[Tuple[int, Callable[[int], bool], str]] = None


def _env2_filfreq_depth_ct(raw: bytes) -> Optional[int]:
    """`hob_f1[6]`, Program RAM offset 215 -- cents, **signed**, +-10800.

    Was a formula over part of the range (`(byte-28)*100` for byte 34-124,
    plus byte 127) with everything else returning `None`, because the dense
    region and the negative half had only ever been written down in a chat
    transcript. §70 read the whole table out of the OS ROM instead
    (0x1F9604, 256 entries, symmetric) and checked eight bytes of it back
    against the panel, negatives included:

        byte  10 ->    20ct     byte 246 (-10) ->   -20ct
        byte  58 ->  3000ct     byte 198 (-58) -> -3000ct
        byte 127 -> 10800ct     byte 128 (-128) -> -10800ct

    Every byte now decodes. **The field is bipolar** -- the old decoder
    called the whole negative half unmapped."""
    return ENV2_FILFREQ_CT[raw[0]]


def _lfo1_pitch_depth_ct(raw: bytes) -> Optional[int]:
    """`cal[22]`, Program RAM offset 199 -- cents, **signed**, +-7200.

    Same story as the filter depth above: §30 had 1:1 up to byte 20 and two
    spot values, §70 has the ROM's own table (0x1FA204) with the panel
    agreeing at byte 20, -20, 100, -100 and -123 (RESOLUTION_NOTES §70)."""
    return LFO_PITCH_CT[raw[0]]


def _lfo1_mnrate_hz(raw: bytes) -> Optional[str]:
    """`LFO1 MnRate`, Program RAM offset 91 -- Hz, to two decimals.

    The ROM table (0x1FB404) is **256 entries, not the 185 rows §61's panel
    sweep could reach**: byte 184 is where the WHEEL stops (24.00 Hz), and
    bytes 185 and 186 give 24.50 and 25.00, with 186-255 all 25.00.
    Confirmed on hardware by writing the byte over SysEx, which the wheel
    cannot do -- so a FILE can carry a rate the front panel cannot dial."""
    return f"{LFO_RATE_CHZ[raw[0]] / 100:.2f}"


def _amp_veltrk_db(raw: bytes) -> Optional[int]:
    """`F4 AMP VelTrk`, Program offset 261. **Signed**, 1 dB per unit.

    Measured on the device 2026-09-07 by typing values on the numeric pad and
    reading the byte back, because the first version of this decoder returned
    `raw[0]` unsigned and would have rendered every negative setting as a
    number the parameter cannot hold:

        panel  +36 dB -> byte  36      panel  -32 dB -> byte 224
        panel  +96 dB -> byte  96      panel  -96 dB -> byte 160

    Two's complement, and the manual's range for the field is +-96 dB (F4 AMP
    parameter table). Bytes between 97 and 159 are outside it and decode to
    `None` rather than to a plausible-looking figure -- the whole point of this
    table is that an unproven byte says so.

    Its neighbours `Src1` (262) and `Depth` (263) are mapped in §43 but are
    deliberately NOT in this table: `Src1` is a control-source code whose
    table this project has not enumerated, and decoding it would mean
    inventing names for codes nobody here has read off the device."""
    b = raw[0] - 256 if raw[0] > 127 else raw[0]
    return b if -96 <= b <= 96 else None


def _panner_adjust_pct(raw: bytes) -> Optional[int]:
    """`F3 POS (PANNER)` Adjust, Program offset 242. Signed, 1 % per unit --
    the byte IS the percentage the panel shows, negative left.

    Placed twice by independent routes (RESOLUTION_NOTES §56/§57) and then
    measured directly 2026-09-07, typing values and reading the byte back:

        panel  +37 % -> byte  37       panel  -32 % -> byte 224
        panel +100 % -> byte 100       panel -100 % -> byte 156

    The field clamps at +-100 -- typing 127 leaves it at 100 -- so bytes 101
    to 155 are unreachable from the panel and decode to `None`.

    Its neighbours -- KeyTrk 244, VelTrk 245, Depth 247, MinDpt 249,
    MaxDpt 250, Pad 252 -- are deliberately NOT in this table. Each rests on
    one measured value plus a zero baseline, which fixes a slope but has
    tested nothing in between, and §51's list of confident wrong numbers is
    what that restraint exists for."""
    b = raw[0] - 256 if raw[0] > 127 else raw[0]
    return b if -100 <= b <= 100 else None


#: DSP function codes whose block's FIRST parameter is the `Coarse:`
#: frequency -- each one checked against the panel's own reading, not
#: assumed from the name (RESOLUTION_NOTES §69).
FREQ_BLOCK_TYPES: Dict[int, str] = {
    9: "PARA TREBLE",            # prog 3 F1, byte 59 -> panel "B 8 7902Hz"
    14: "STEEP RESONANT BASS",   # prog 42 F1, byte -48 -> panel "C 0 16Hz"
    37: "LOPAS2",                # prog 1 F3, byte 41 -> panel "F 7 2794Hz"
    50: "4POLE LOPASS W/SEP",    # CUTCAL bank F1, 11 programs + both clamps
}


def _f1_coarse_hz(raw: bytes) -> Optional[int]:
    """Program offset 210 -> the `Coarse:` frequency the panel displays, in Hz.

    The byte is a **signed semitone index with 0 = C4**, and the law is
    `Hz = 440 * 2**((s-9)/12)` -- `s = 9` is A4 = 440 Hz exactly, which is
    what the -9 in the exponent is. Verified against the device's own
    `Coarse:` field, 2026-09-14:

        typed 1     -> panel "C 0 16Hz"       byte -48   law    16.4 Hz
        CUT 000     -> panel "A#1 58Hz"       byte -26   law    58.3 Hz
        typed 440   -> panel "A 4 440Hz"      byte   9   law   440.0 Hz
        CUT 050     -> panel "C 6 1047Hz"     byte  24   law  1046.5 Hz
        CUT 100     -> panel "D#10 19912Hz"   byte  75   law 19912.1 Hz
        typed 99999 -> panel "G 10 25088Hz"   byte  79   law 25087.7 Hz

    The first and last are the field's own **clamps** -- typing an
    out-of-range number and letting the device refuse it is what pins the
    endpoints -- so the proven range is exactly -48..79 and anything
    outside it decodes to `None`.

    The panel rounds to whole Hz (1046.5 shows as `1047`), so this rounds
    half-up to match what the user is looking at, not Python's half-even.
    """
    b = raw[0] - 256 if raw[0] > 127 else raw[0]
    if not -48 <= b <= 79:
        return None
    return FILTER_COARSE_HZ[b + 48]


#: Only offsets independently confirmed by DUMP-diffing two panel-driven
#: states go here -- see the module docstring for why this list is short.
KNOWN_FIELDS: Dict[Tuple[ObjectType, int], Field] = {
    (ObjectType.Program, 215): Field(
        name="ENV2->FilFreq Depth", size=1, unit="cents",
        notes="RESOLUTION_NOTES §30/§70; ROM table 0x1F9604, signed, "
              "all 256 bytes, +-10800 cents",
        decode=_env2_filfreq_depth_ct,
    ),
    (ObjectType.Program, 199): Field(
        name="LFO1->Pitch Depth", size=1, unit="cents",
        notes="RESOLUTION_NOTES §30/§70; ROM table 0x1FA204, signed, "
              "all 256 bytes, +-7200 cents",
        decode=_lfo1_pitch_depth_ct,
    ),
    (ObjectType.Program, 261): Field(
        name="F4 AMP VelTrk", size=1, unit="dB",
        notes="RESOLUTION_NOTES §47/§62; signed, 1 dB per unit, +-96 dB",
        decode=_amp_veltrk_db,
    ),
    (ObjectType.Program, 91): Field(
        name="LFO1 MnRate", size=1, unit="Hz",
        notes="RESOLUTION_NOTES §61/§70; ROM table 0x1FB404, all 256 bytes, "
              "0.00-25.00 Hz. The wheel stops at byte 184 (24.00); SysEx "
              "and files reach 185 (24.50) and 186+ (25.00).",
        decode=_lfo1_mnrate_hz,
    ),
    (ObjectType.Program, 210): Field(
        name="F1 Coarse", size=1, unit="Hz",
        notes="RESOLUTION_NOTES §69; signed semitones, 0 = C4, "
              "proven -48..79 (both are the field's own clamps). "
              "Only a frequency when the F1 block type at 209 is one.",
        decode=_f1_coarse_hz,
        gate=(209, lambda t: t in FREQ_BLOCK_TYPES,
              "the F1 block type at offset 209 is a frequency function"),
    ),
    (ObjectType.Program, 242): Field(
        name="F3 POS Adjust", size=1, unit="%",
        notes="RESOLUTION_NOTES §56/§57/§62; signed, 1 % per unit, +-100 %",
        decode=_panner_adjust_pct,
    ),
}


def describe_field(obj_type: ObjectType, offset: int, raw: bytes,
                   gate_byte: Optional[int] = None) -> str:
    """``"28"`` normally, ``"28 (ENV2->FilFreq Depth: 1200 cents)"`` when the
    offset is in :data:`KNOWN_FIELDS` and its formula covers this byte. Note
    ``raw.hex()`` prints the byte in hex, not decimal -- byte ``0x58`` (88
    decimal) is a different, larger cent value than a naive decimal-58
    reading would give; this ambiguity is exactly what tripped up the
    RESOLUTION_NOTES §32 hardware smoke test's own pre-test prediction."""
    hexed = raw.hex()
    field = KNOWN_FIELDS.get((obj_type, offset))
    if field is None:
        return hexed
    if field.gate is not None:
        _, allows, why = field.gate
        if gate_byte is None:
            # Say the condition out loud rather than decode on the hope that
            # it holds -- an unqualified number here is indistinguishable
            # from a verified one, which is the whole failure this gate
            # exists to prevent.
            value = field.decode(raw)
            shown = ("unmapped for this byte" if value is None
                     else f"{value} {field.unit}")
            return f"{hexed} ({field.name}: {shown} -- only if {why})"
        if not allows(gate_byte):
            return (f"{hexed} ({field.name}: not decoded -- "
                    f"{why} does not hold, byte {gate_byte})")
    value = field.decode(raw)
    if value is None:
        return f"{hexed} ({field.name}: unmapped for this byte)"
    return f"{hexed} ({field.name}: {value} {field.unit})"


def filter_cutoff_byte_to_hz(b: int) -> float:
    """K2000 filter cutoff byte -> Hz. ``Hz = 440 * 2**((s-9)/12)``, `s` the
    signed semitone value of `b` (two's-complement over a signed byte).

    Verified to 0.08% against the device's own panel `Coarse:` field across
    11 presets during the CUTCAL session (RESOLUTION_NOTES, 2026-08-22).

    **The offset was mapped 2026-09-14** (RESOLUTION_NOTES §69): the
    block's first parameter byte, `210 + 16*k` for DSP slot `k`, sitting
    immediately after that block's type byte at `209 + 16*k`. `F1` is in
    :data:`KNOWN_FIELDS` as a gated entry; the other three slots are not,
    because offset 242 already holds `F3 POS Adjust` for a PANNER block and
    one offset cannot carry two unconditional meanings -- see TODO.md.

    This bare function stays, for a byte whose slot you know but whose
    block type you have not checked. **The law is only a frequency when
    the block is a frequency function** (:data:`FREQ_BLOCK_TYPES`); applied
    blind it returns a tidy, wrong number, as it does for Program 1's
    `SINE` in F1.
    """
    s = b - 256 if b >= 128 else b
    return 440.0 * (2.0 ** ((s - 9) / 12.0))
