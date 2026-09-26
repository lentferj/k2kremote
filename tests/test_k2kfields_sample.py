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


# --- fields measured on the K2000R, 2026-09-25/26 --------------------------
#
# Each assertion below is a point actually read off the instrument: the panel
# display on one side, a DUMP of the byte on the other, taken in the same
# instant with the editor holding the object. They are not derived from the
# law -- the law was fitted to them.


def test_keytrk_ladder_reproduces_the_measured_points():
    """The three regions, at the boundaries and either side of them.

    A straight line through (1, 5) and (43, 100) hits both of those and is
    wrong at every point between, which is why this pins the interior.
    """
    from k2kremote.k2kfields import describe_field
    from k2000.definitions import ObjectType

    measured = {                      # byte -> displayed ct/key
        0: 0, 1: 5, 3: 15, 8: 40,     # region 1: 5*|b|
        9: 42, 13: 50, 23: 70, 33: 90,  # region 2: 40+2*(|b|-8)
        34: 91, 43: 100, 45: 102,     # region 3: 90+(|b|-33)
        255: -5, 249: -35, 213: -100, 211: -102,   # two's complement
    }
    for byte, ct in measured.items():
        out = describe_field(ObjectType.Program, 196, bytes([byte]))
        assert f"{ct} ct/key" in out, f"byte {byte}: {out}"


def test_both_keytrk_fields_share_one_ladder():
    """KEYMAP KeyTrk (180) landed on the ladder fitted to PITCH KeyTrk (196).

    Two fields agreeing is what makes the region boundaries real rather than
    an artefact of one page, so it is asserted rather than assumed.
    """
    from k2kremote.k2kfields import describe_field
    from k2000.definitions import ObjectType

    for byte in (0, 3, 13, 23, 33, 43, 249, 255):
        a = describe_field(ObjectType.Program, 196, bytes([byte])).split(":")[-1]
        b = describe_field(ObjectType.Program, 180, bytes([byte])).split(":")[-1]
        assert a == b, f"byte {byte}: PITCH {a!r} vs KEYMAP {b!r}"


def test_keymap_keytrk_default_is_the_normal_tracking_byte():
    """Byte 43 is the KEYMAP page's default and reads 100 ct/key -- the same
    byte that means +100 (doubling) on the PITCH page, because PITCH adds to
    KEYMAP. Same byte, same unit, different musical meaning per offset."""
    from k2kremote.k2kfields import describe_field
    from k2000.definitions import ObjectType

    assert "100 ct/key" in describe_field(ObjectType.Program, 180, b"\x2b")
    assert "100 ct/key" in describe_field(ObjectType.Program, 196, b"\x2b")
    assert "0 ct/key" in describe_field(ObjectType.Program, 180, b"\x00")


def test_wet_dry_byte_is_the_percentage_and_rails_at_100():
    from k2kremote.k2kfields import describe_field
    from k2000.definitions import ObjectType

    for byte, pct in ((12, 12), (37, 37), (73, 73), (0, 0), (100, 100)):
        assert f"{pct}%" in describe_field(ObjectType.Program, 43, bytes([byte]))
    # Above the driven rail the decoder declines rather than inventing a
    # reading. describe_field still names the field -- saying "there is a
    # Wet/Dry here and I cannot read this byte" is more useful than silence,
    # and it is what distinguishes an unmapped value from an absent field.
    assert "unmapped" in describe_field(ObjectType.Program, 43, bytes([101]))


def test_res_depth_is_labelled_as_the_display_not_the_law():
    """F2 RES is under a standing decision to be measured acoustically. The
    decoder must not quietly present the panel's dB as the conversion."""
    from k2kremote.k2kfields import describe_field
    from k2000.definitions import ObjectType

    out = describe_field(ObjectType.Program, 231, bytes([24]))
    assert "+12.0 dB" in out and "displayed" in out
