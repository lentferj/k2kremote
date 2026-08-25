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
