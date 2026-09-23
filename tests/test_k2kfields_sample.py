# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# The Soundblock/Keymap decoders, checked against objects the K2000 ITSELF
# wrote during the Roland and AKAI imports of 2026-09-21/22. No hardware:
# the dumps are saved under ~/temp and the tests skip without them.

import json
import pathlib

import pytest

from k2000.definitions import ObjectType
from k2kremote.k2kfields import describe_field

DUMPS = pathlib.Path.home() / "temp"


def _load(name):
    path = DUMPS / name
    if not path.exists():
        pytest.skip(f"device dump {name} not present")
    return json.loads(path.read_text())


def test_sample_rate_across_a_whole_imported_volume():
    """SOPRANO SAX2, 19 sample objects the K2000 wrote, every one 44100 Hz.

    (Written first as "Roland kit imports, 48000 Hz" from memory. The bytes
    say 0x5893 = 22675 on all 19, which is the AKAI import at rate code 1 --
    the dump is named for what it holds and the label was wrong.)
    """
    d = _load("akai_sopranosax2_readback.json")
    bodies = [bytes.fromhex(h) for h in d["samples"].values()]
    assert len(bodies) == 19
    for body in bodies:
        assert describe_field(ObjectType.Soundblock, 40, body[40:44]) \
            == "00005893 (Sample Rate: 44100 Hz)"


def test_the_truncated_arm_is_what_makes_44100_reachable():
    """The rate that discriminates: 1e9/44100 truncates to 22675 and rounds
    to 22676, and the device wrote 22675 (AKAI import, 2026-09-22).

    Inverting the truncation answers 44101 -- tidy, and not a rate the
    machine can produce. Snapping to the ROM's own table answers 44100.
    """
    assert describe_field(ObjectType.Soundblock, 40, bytes.fromhex("00005893")) \
        == "00005893 (Sample Rate: 44100 Hz)"
    assert round(1e9 / 22675) == 44101      # what inverting would have said
    assert int(1e9 / 44100) == 22675        # what the device actually wrote


def test_loop_state_is_read_from_the_inverted_bit():
    """0x80 CLEAR = looped. Confirmed by contrast on two real imports."""
    assert describe_field(ObjectType.Soundblock, 13, bytes([0x30])) \
        == "30 (Sample Loop: looped)"
    assert describe_field(ObjectType.Soundblock, 13, bytes([0xB0])) \
        == "b0 (Sample Loop: one-shot)"


def test_root_note_matches_the_akai_header_that_pinned_it():
    """Header root 87 is D#6 -- the value that showed the K2000 reads the
    AKAI header and not the sample's name (which said `D 5`)."""
    assert describe_field(ObjectType.Soundblock, 12, bytes([87])) \
        == "57 (Sample Root: D#6 (87))"
    assert describe_field(ObjectType.Soundblock, 12, bytes([60])) \
        == "3c (Sample Root: C4 (60))"


def test_roland_import_roots_decode_across_the_whole_set():
    d = _load("akai_sopranosax2_readback.json")
    for hexs in d["samples"].values():
        out = describe_field(ObjectType.Soundblock, 12,
                             bytes.fromhex(hexs)[12:13])
        assert "Sample Root" in out and "unmapped" not in out


def test_keymap_method_layout_from_a_real_imported_keymap():
    """0x17 is the 6-byte form, and the layout is what decoded the entries."""
    d = _load("akai_accordion_cymbals_readback.json")
    body = bytes.fromhex(d["objs"]["Keymap_300"])[:540]   # the DIRBANK size
    assert describe_field(ObjectType.Keymap, 2, body[2:4]) == (
        "0017 (Keymap Method: tuning i16 + volumeAdjust i8 + sampleID i16 "
        "+ subSample u8 = 6 B/entry)")


def test_a_period_no_table_rate_produces_decodes_to_none():
    """Better an honest gap than a tidy wrong number -- 1e9/41704 is 23978,
    which is not a rate the K2000's import path can write."""
    out = describe_field(ObjectType.Soundblock, 40, bytes.fromhex("0000A2E8"))
    assert out == "0000a2e8 (Sample Rate: unmapped for this byte)"
