# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

from k2000.definitions import ObjectType

from k2kremote import k2kfields


def test_describe_field_bare_hex_for_an_unknown_offset():
    assert k2kfields.describe_field(ObjectType.Program, 0, b"\x2a") == "2a"


def test_describe_field_decodes_env2_filfreq_depth_in_the_exact_range():
    # ct = (byte-28)*100, verified for byte 34-124 (RESOLUTION_NOTES §30).
    out = k2kfields.describe_field(ObjectType.Program, 215, b"\x28")  # 40
    assert out == "28 (ENV2->FilFreq Depth: 1200 cents)"


def test_describe_field_env2_filfreq_depth_ceiling():
    out = k2kfields.describe_field(ObjectType.Program, 215, b"\x7f")  # 127
    assert out == "7f (ENV2->FilFreq Depth: 10800 cents)"


def test_describe_field_env2_filfreq_depth_unmapped_below_the_formula_range():
    # byte < 34 is known to exist and be monotonic, but the exact value was
    # only ever recorded in a chat transcript -- must not fabricate one.
    out = k2kfields.describe_field(ObjectType.Program, 215, b"\x05")
    assert out == "05 (ENV2->FilFreq Depth: unmapped for this byte)"


def test_describe_field_decodes_lfo1_pitch_depth_in_the_exact_range():
    out = k2kfields.describe_field(ObjectType.Program, 199, b"\x0a")  # 10
    assert out == "0a (LFO1->Pitch Depth: 10 cents)"


def test_describe_field_lfo1_pitch_depth_spot_values():
    assert k2kfields.describe_field(ObjectType.Program, 199, bytes([79])) \
        == "4f (LFO1->Pitch Depth: 1200 cents)"
    assert k2kfields.describe_field(ObjectType.Program, 199, bytes([123])) \
        == "7b (LFO1->Pitch Depth: 7200 cents)"


def test_describe_field_lfo1_pitch_depth_unmapped_between_spot_values():
    out = k2kfields.describe_field(ObjectType.Program, 199, bytes([50]))
    assert out == "32 (LFO1->Pitch Depth: unmapped for this byte)"


def test_describe_field_only_applies_to_the_right_object_type():
    # The offsets are only confirmed for Program objects; a Keymap at the
    # same offset must not be silently decoded as if it meant the same
    # thing.
    out = k2kfields.describe_field(ObjectType.Keymap, 215, b"\x28")
    assert out == "28"


def test_filter_cutoff_byte_to_hz_matches_the_hardware_verified_table():
    # RESOLUTION_NOTES: byte -26 -> ~58Hz, byte 75 -> ~19912Hz (CUTCAL,
    # verified to 0.08% against the device's own panel Coarse: field).
    assert abs(k2kfields.filter_cutoff_byte_to_hz(256 - 26) - 58.0) < 1.0
    assert abs(k2kfields.filter_cutoff_byte_to_hz(75) - 19912.0) < 100.0


def test_filter_cutoff_byte_to_hz_middle_c_reference():
    # byte 9 is s=9 -> 440*2**0 = 440Hz exactly, the formula's own anchor.
    assert k2kfields.filter_cutoff_byte_to_hz(9) == 440.0


def test_describe_field_decodes_amp_veltrk_as_the_measured_bank_read():
    # RESOLUTION_NOTES §47: the four VELCHECK presets carried 0/5/15/36 at
    # offset 261 and the panel showed VelTrk:0dB/5dB/15dB/36dB. These are the
    # bytes actually read off the instrument, not a constructed example.
    for byte, shown in ((0, 0), (5, 5), (15, 15), (36, 36)):
        out = k2kfields.describe_field(ObjectType.Program, 261, bytes([byte]))
        assert out == f"{byte:02x} (F4 AMP VelTrk: {shown} dB)"


def test_describe_field_decodes_negative_amp_veltrk():
    # RESOLUTION_NOTES §62: measured on the device by typing the value and
    # reading the byte back. The first version of this decoder returned the
    # raw byte, so -32 dB rendered as "224 dB" -- a figure the parameter
    # cannot hold, printed with no hedge.
    for byte, shown in ((224, -32), (160, -96), (96, 96), (36, 36)):
        out = k2kfields.describe_field(ObjectType.Program, 261, bytes([byte]))
        assert out == f"{byte:02x} (F4 AMP VelTrk: {shown} dB)"


def test_amp_veltrk_outside_the_devices_range_is_unmapped():
    # The manual's range is +-96 dB and the device confirms it, so bytes 97
    # to 159 correspond to no setting the field can hold. Say so rather than
    # print a plausible number.
    for byte in (97, 127, 128, 159):
        out = k2kfields.describe_field(ObjectType.Program, 261, bytes([byte]))
        assert "unmapped" in out


def test_amp_veltrk_neighbours_are_deliberately_not_decoded():
    # F4 AMP Src1 (262) and Depth (263) are mapped in §47/§43 but stay out of
    # KNOWN_FIELDS: Src1 is a control-source code whose table this project has
    # never enumerated. Decoding them would be inventing meaning.
    assert k2kfields.describe_field(ObjectType.Program, 262, b"\x72") == "72"
    assert k2kfields.describe_field(ObjectType.Program, 263, b"\x00") == "00"


def test_panner_adjust_is_signed_and_clamps_at_100():
    # §62: +100 % -> byte 100, -100 % -> byte 156, and typing 127 leaves the
    # field at 100 -- so bytes 101..155 are unreachable from the panel.
    for byte, shown in ((100, 100), (156, -100), (224, -32)):
        out = k2kfields.describe_field(ObjectType.Program, 242, bytes([byte]))
        assert out == f"{byte:02x} (F3 POS Adjust: {shown} %)"
    for byte in (101, 127, 128, 155):
        out = k2kfields.describe_field(ObjectType.Program, 242, bytes([byte]))
        assert "unmapped" in out


def test_describe_field_decodes_panner_adjust():
    # RESOLUTION_NOTES §56/§57: six programs read 0, 0, +7, +7, -11, -32 % off
    # the panel and mapped straight onto this byte; a DUMP-diff then set it to
    # 37 and read 37 back. Negative values are two's complement.
    for byte, pct in ((0, 0), (7, 7), (37, 37), (256 - 11, -11), (256 - 32, -32)):
        out = k2kfields.describe_field(ObjectType.Program, 242, bytes([byte]))
        assert out == f"{byte:02x} (F3 POS Adjust: {pct} %)"


def test_panner_neighbours_are_deliberately_not_decoded():
    # KeyTrk 244, VelTrk 245, Depth 247, MinDpt 249, MaxDpt 250, Pad 252 each
    # rest on one measured value plus a zero baseline -- a slope with nothing
    # tested in between. Offsets recorded in the notes, not decoded here.
    for off in (244, 245, 247, 249, 250, 252):
        assert k2kfields.describe_field(ObjectType.Program, off, b"\x0a") == "0a"
