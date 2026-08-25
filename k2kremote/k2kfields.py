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
from typing import Callable, Dict, Optional, Tuple

from k2000.definitions import ObjectType


@dataclass(frozen=True)
class Field:
    """One offset-addressed field this project has independently mapped."""

    name: str
    size: int
    unit: str
    notes: str
    #: raw bytes -> decoded value, or None if out of the formula's proven
    #: range (see module docstring).
    decode: Callable[[bytes], Optional[int]]


def _env2_filfreq_depth_ct(raw: bytes) -> Optional[int]:
    """`hob_f1[6]`, Program RAM offset 215. `ct = (byte-28)*100` holds
    exactly for byte 34-124 (RESOLUTION_NOTES §30); byte 127 = 10800ct
    (9.000 octaves) confirmed by single-clicking there directly. Bytes
    0-33 and 125-126 are known to exist and be monotonic but their exact
    values were only ever recorded in a chat transcript, not committed
    here -- return None rather than interpolate a number nobody verified."""
    b = raw[0]
    if b == 127:
        return 10800
    if 34 <= b <= 124:
        return (b - 28) * 100
    return None


def _lfo1_pitch_depth_ct(raw: bytes) -> Optional[int]:
    """`cal[22]`, Program RAM offset 199. `ct = byte` holds exactly for
    byte 0-20 (RESOLUTION_NOTES §30, "1:1 up to byte 20"); byte 79 = 1200ct
    and byte 123 = 7200ct (6.000 octaves, the ceiling) are individually
    confirmed spot values. Bytes 21-78 and 80-122 are known to be
    monotonic but not by an exact recorded formula -- None, same reasoning
    as the filter depth field above."""
    b = raw[0]
    if b == 79:
        return 1200
    if b == 123:
        return 7200
    if 0 <= b <= 20:
        return b
    return None


#: Only offsets independently confirmed by DUMP-diffing two panel-driven
#: states go here -- see the module docstring for why this list is short.
KNOWN_FIELDS: Dict[Tuple[ObjectType, int], Field] = {
    (ObjectType.Program, 215): Field(
        name="ENV2->FilFreq Depth", size=1, unit="cents",
        notes="RESOLUTION_NOTES §30; exact for byte 34-124 and byte 127",
        decode=_env2_filfreq_depth_ct,
    ),
    (ObjectType.Program, 199): Field(
        name="LFO1->Pitch Depth", size=1, unit="cents",
        notes="RESOLUTION_NOTES §30; exact for byte 0-20, 79, 123",
        decode=_lfo1_pitch_depth_ct,
    ),
}


def describe_field(obj_type: ObjectType, offset: int, raw: bytes) -> str:
    """``"58"`` normally, ``"58 (ENV2->FilFreq Depth: 3000 cents)"`` when the
    offset is in :data:`KNOWN_FIELDS` and its formula covers this byte."""
    hexed = raw.hex()
    field = KNOWN_FIELDS.get((obj_type, offset))
    if field is None:
        return hexed
    value = field.decode(raw)
    if value is None:
        return f"{hexed} ({field.name}: unmapped for this byte)"
    return f"{hexed} ({field.name}: {value} {field.unit})"


def filter_cutoff_byte_to_hz(b: int) -> float:
    """K2000 filter cutoff byte -> Hz. ``Hz = 440 * 2**((s-9)/12)``, `s` the
    signed semitone value of `b` (two's-complement over a signed byte).

    Verified to 0.08% against the device's own panel `Coarse:` field across
    11 presets during the CUTCAL session (RESOLUTION_NOTES, 2026-08-22) --
    the *law* is solid. **The RAM offset holding this byte within a live
    Program object was never mapped**: CUTCAL set and read it entirely via
    the panel's F1 FRQ page, never via DUMP. Apply this only to a byte
    whose location you already know (e.g. by reading the panel yourself,
    the way CUTCAL did) -- there is deliberately no `KNOWN_FIELDS` entry
    that would auto-apply this to some offset while browsing, because that
    offset has never been confirmed.
    """
    s = b - 256 if b >= 128 else b
    return 440.0 * (2.0 ** ((s - 9) / 12.0))
