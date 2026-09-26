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

Within :data:`KNOWN_FIELDS`, the byte<->value conversions have an honesty
boundary worth keeping visible, and **it moved on 2026-09-14** — the
paragraph that used to stand here said the dense point-by-point tables
"exist only in a chat transcript with a sibling project, not in this
repository". They are in this repository: :mod:`k2kremote.k2kromtables`,
read out of the firmware in RESOLUTION_NOTES §70, with their ROM addresses
recorded — and *this file imports them twenty-six lines below*. The caveat
outlived its measurement by six days while sitting above the import that
refutes it.

What is true now, per field:

* **Table-backed, exact over the whole byte range** — the decoders that index
  :data:`~k2kremote.k2kromtables.LFO_RATE_CHZ`,
  :data:`~k2kremote.k2kromtables.FILTER_COARSE_HZ`,
  :data:`~k2kremote.k2kromtables.ENV2_FILFREQ_CT` and
  :data:`~k2kremote.k2kromtables.LFO_PITCH_CT`. These are the firmware's own
  display tables, not a fit to them.
* **Formula-backed, proven over part of the range** — the rest, e.g.
  :func:`_amp_veltrk_db`, which still returns ``None`` outside the range that
  was actually verified rather than extrapolating.

So :func:`decode` returns ``None`` for a byte a *formula* cannot vouch for,
and a real value everywhere a *table* covers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple, Union

from k2000.definitions import ObjectType
from k2kremote.k2kromtables import (ENV2_FILFREQ_CT, FILTER_COARSE_HZ,
                                     LFO_PITCH_CT, LFO_RATE_CHZ,
                                     ROLAND_RATE_HZ)


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



# --- Soundblock / Keymap -----------------------------------------------
#
# These four were not found by DUMP-diffing panel edits, which is how every
# Program entry above was found. They come from tracing the import paths in
# the OS ROM and were then checked against objects the K2000 itself wrote
# during the Roland and AKAI imports (docs/IMPORT_CONVERSION.md). That is a
# different provenance, not a weaker one -- the check is still the machine.

#: A Soundfilehead sits at Soundblock body+12, so its own field offsets are
#: 12 higher here. Named so the arithmetic is visible rather than folded in.
_SFH = 12


def _sample_rate_hz(raw: bytes) -> Optional[int]:
    """Soundblock offset 40 (`Soundfilehead.samplePeriod`) -> the sample rate.

    The firmware writes `1e9 / rate` **truncated**, not rounded: the divide
    at ROM 0x18352C is a restoring division that discards the remainder.
    Confirmed on device output at the one rate where the two differ --
    an AKAI import at 44100 wrote 22675, where rounding gives 22676.

        20833 ns -> 48000 Hz      (Roland kit imports, 2026-09-21)
        22675 ns -> 44100 Hz      (AKAI Voice Spectral imports, 2026-09-22)

    **Inverting the truncation does not recover the rate.** `1e9/22675` is
    44101.4, so rounding gives 44101 -- close, tidy and not a rate the
    machine can produce. So this does not invert: it asks which of the six
    rates the ROM's own table holds (0x169D90) truncates back to this
    period, which is exact.

    A period no table rate produces decodes to None. That is the common
    case for anything not imported -- a sampled or ROM sample may sit at a
    rate the import path never writes -- and None is the right answer there
    rather than a plausible number.
    """
    period = int.from_bytes(raw[:4], "big")
    if period == 0:
        return None
    for rate in ROLAND_RATE_HZ:
        if int(1e9 / rate) == period:
            return rate
    return None


def _sample_loop_state(raw: bytes) -> Optional[str]:
    """Soundblock offset 13 (`Soundfilehead.flags`) -> looped or one-shot.

    **Bit 0x80 is inverted**: CLEAR means looped, SET means one-shot. That
    reading was confirmed by contrast rather than by assertion -- two
    imports of different material, the same field, differing in exactly that
    bit and matching the source both times:

        Roland percussion kits   flags 0xB0   bit set    one-shot
        AKAI sax multisample     flags 0x30   bit clear  looped

    The rest of the byte is not decoded here. The corpus holds 0x00, 0x04,
    0x70, 0x72, 0xB0 and 0xF0, and no reading of the remaining bits survives
    all six, so this returns only what bit 7 says.
    """
    return "one-shot" if raw[0] & 0x80 else "looped"


def _sample_root_note(raw: bytes) -> Optional[str]:
    """Soundblock offset 12 (`Soundfilehead.rootkey`) -> the note name.

    A standard MIDI note number: an AKAI sample whose header said D#6 (87)
    imported as 87 while its *name* said `D 5`, which is how the header was
    shown to be the source rather than the name (2026-09-22).

    Octave numbering is **C4 = 60**, the standard convention, and it is the
    panel's own: the CUTCAL readings recorded for `_f1_coarse_hz` above show
    the device displaying `A 4 440Hz` and `C 6 1047Hz`, which puts middle C
    at C4. It also matches the AKAI side, where header root 87 is D#6.

    A first draft of this said `C0 = 0` and rendered 60 as `C5`. That was
    asserted without evidence, and the evidence refuting it was already in
    this file.
    """
    n = raw[0]
    if not 0 <= n <= 127:
        return None
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    return f"{names[n % 12]}{n // 12 - 1} ({n})"


def _keymap_entry_layout(raw: bytes) -> Optional[str]:
    """Keymap offset 2 (`method`) -> what one entry in the table contains.

    The method is a bitfield selecting which fields each entry carries, and
    `entrySize` at offset 10 is their total width. The order is the bit
    order, which is how a 6-byte `0x17` entry decodes:

        0x10  tuning i16      0x08  tuning i8     0x04  volumeAdjust i8
        0x02  sampleID i16    0x01  subSample u8

    Checked against imported keymaps whose first entries were known
    independently: `0x17` gave `tuning +4352, vol -44, sample 16582, sub 1`,
    matching the values recorded for those objects.
    """
    method = int.from_bytes(raw[:2], "big")
    parts, width = [], 0
    if method & 0x10:
        parts.append("tuning i16"); width += 2
    elif method & 0x08:
        parts.append("tuning i8"); width += 1
    if method & 0x04:
        parts.append("volumeAdjust i8"); width += 1
    if method & 0x02:
        parts.append("sampleID i16"); width += 2
    if method & 0x01:
        parts.append("subSample u8"); width += 1
    if not parts:
        return None
    return f"{' + '.join(parts)} = {width} B/entry"


#: Only offsets independently confirmed by DUMP-diffing two panel-driven
#: states go here -- see the module docstring for why this list is short.
def _keytrk_ct_per_key(raw: bytes) -> Optional[str]:
    """PITCH / KEYMAP KeyTrk: one three-region ladder shared by both fields.

    Measured 2026-09-25 over 89 points -- a full wheel sweep in both
    directions, reading the display and DUMPing the byte at every step -- and
    then confirmed independently on the KEYMAP page's own KeyTrk, which lands
    on the same ladder. The boundaries at 8 and 33 are where a two-point fit
    goes wrong: a line through (1, 5) and (43, 100) reproduces both endpoints
    and is wrong everywhere between. See RESOLUTION_NOTES §90.
    """
    b = raw[0]
    s = b - 256 if b > 127 else b
    n = abs(s)
    if n <= 8:
        ct = 5 * n
    elif n <= 33:
        ct = 40 + 2 * (n - 8)
    else:
        ct = 90 + (n - 33)
    return f"{-ct if s < 0 else ct} ct/key"


def _res_depth_db(raw: bytes) -> Optional[str]:
    """F2 RES Depth as the PANEL displays it -- 0.5 dB per unit, linear.

    **This is the display's law, not an acoustic measurement.** F2 RES is
    under a standing decision to be measured acoustically before anything
    writes it, after three prior catches on a plausible reading of a displayed
    unit. Shown here because a browser should say what the machine says; do
    not derive a conversion from it.
    """
    b = raw[0]
    s = b - 256 if b > 127 else b
    return f"{s * 0.5:+.1f} dB (displayed)"


def _percent_0_100(raw: bytes) -> Optional[str]:
    """A plain 0..100 percentage; the byte IS the number. Rails driven."""
    b = raw[0]
    return f"{b}%" if 0 <= b <= 100 else None


KNOWN_FIELDS: Dict[Tuple[ObjectType, int], Field] = {
    (ObjectType.Program, 196): Field(
        name="PITCH KeyTrk", size=1, unit=None,
        notes="RESOLUTION_NOTES §90; three-region ladder, 89 points. A "
              "DEVIATION added to the KEYMAP page's KeyTrk, so 0 = normal "
              "1:1 and byte 43 (+100) is DOUBLE tracking, not fixed pitch. "
              "Fixed pitch here is byte 213 (-100) and occurs once in 16,649 "
              "corpus layers -- the KEYMAP page is how it is normally done.",
        decode=_keytrk_ct_per_key,
    ),
    (ObjectType.Program, 180): Field(
        name="KEYMAP KeyTrk", size=1, unit=None,
        notes="RESOLUTION_NOTES §90; same ladder as offset 196. Default is "
              "byte 43 = 100 ct/key (normal). Byte 0 = 0 ct/key = fixed "
              "pitch, and that is where drum programs sit: 9.7x enriched "
              "over non-drums across 4,280 corpus programs.",
        decode=_keytrk_ct_per_key,
    ),
    (ObjectType.Program, 43): Field(
        name="FX Wet/Dry Mix Adjust", size=1, unit=None,
        notes="RESOLUTION_NOTES §90; the byte IS the percentage, rails 0 and "
              "100 both driven. EffectPreset sits at offset 42.",
        decode=_percent_0_100,
    ),
    (ObjectType.Program, 231): Field(
        name="F2 RES Depth", size=1, unit=None,
        notes="RESOLUTION_NOTES §90; offset confirmed three ways (corpus, "
              "generic empty block, and with 2P LOPASS loaded). The 0.5 dB "
              "per unit is the DISPLAY's law and is deliberately not treated "
              "as the acoustic one -- see the decoder's docstring.",
        decode=_res_depth_db,
    ),
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

    (ObjectType.Soundblock, _SFH + 0): Field(
        name="Sample Root", size=1, unit="",
        notes="IMPORT_CONVERSION.md; Soundfilehead.rootkey, MIDI note. "
              "Shown the K2000's way (C0 = 0), so 60 reads C5 not C4.",
        decode=_sample_root_note,
    ),
    (ObjectType.Soundblock, _SFH + 1): Field(
        name="Sample Loop", size=1, unit="",
        notes="IMPORT_CONVERSION.md; Soundfilehead.flags bit 0x80, and it "
              "is INVERTED -- clear = looped. Confirmed by contrast: "
              "0xB0 one-shot kits against 0x30 looped multisamples. "
              "The other bits are not decoded; no reading survives all six "
              "values the corpus holds.",
        decode=_sample_loop_state,
    ),
    (ObjectType.Soundblock, _SFH + 28): Field(
        name="Sample Rate", size=4, unit="Hz",
        notes="IMPORT_CONVERSION.md; Soundfilehead.samplePeriod, "
              "TRUNC(1e9/rate) -- the ROM divide at 0x18352C discards the "
              "remainder. Device wrote 22675 at 44100, where rounding "
              "would give 22676.",
        decode=_sample_rate_hz,
    ),
    (ObjectType.Keymap, 2): Field(
        name="Keymap Method", size=2, unit="",
        notes="IMPORT_CONVERSION.md; bitfield selecting the per-entry "
              "fields, in bit order. entrySize at offset 10 is their total "
              "width -- 0x17 gives 6 bytes.",
        decode=_keymap_entry_layout,
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
    # A unitless field -- a note name, a loop state -- would otherwise print
    # a trailing space inside the parens.
    suffix = f" {field.unit}" if field.unit else ""
    return f"{hexed} ({field.name}: {value}{suffix})"


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
