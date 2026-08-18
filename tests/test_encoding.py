# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# The fixtures are the K2 SysEx spec's own worked example (K2vx Musician's Guide
# ch. 30, "Data Formats"), so these tests are checks against the protocol rather
# than against our reading of it.

import pytest

from k2000.encoding import decode_data_field, encode_data_field

#: ch. 30's example: four data bytes, given in BOTH transmission forms.
DATA = bytes([0x4F, 0xD8, 0x01, 0x29])
NIBBLE = bytes([0x04, 0x0F, 0x0D, 0x08, 0x00, 0x01, 0x02, 0x09])
BITSTREAM = bytes([0x27, 0x76, 0x00, 0x12, 0x48])


def test_decode_matches_the_specs_worked_example_in_both_forms():
    assert decode_data_field(NIBBLE, 4, len(DATA)) == DATA
    assert decode_data_field(BITSTREAM, 7, len(DATA)) == DATA


def test_encode_matches_the_specs_worked_example_in_both_forms():
    assert encode_data_field(DATA, 4) == NIBBLE
    assert encode_data_field(DATA, 7) == BITSTREAM


def test_the_two_forms_are_the_same_data():
    """`form` selects transmission packing, not content.

    Both forms must decode to identical bytes; a difference is a bug here and can
    never be a fact about the protocol. Ours *did* differ for a while, and the
    difference was briefly mistaken for one."""
    assert (decode_data_field(NIBBLE, 4, len(DATA))
            == decode_data_field(BITSTREAM, 7, len(DATA)))


def test_data_field_is_left_aligned_not_right():
    """The data field pads at the TAIL; numeric fields are right-justified.

    This is the bug. `decode_n`/`encode_n` right-justify, which is correct for
    `type`/`idno`/`size`/`offs` and wrong for `data`. It hides in nibble form,
    where 2 output bytes per input byte always divides evenly — but 722 data bytes
    in bit-stream form is 5776 bits carried in 826 seven-bit bytes, i.e. 5782, so
    front-padding inserts two leading zeros and shifts every decoded byte."""
    # one data byte 0xFF -> 11111111 -> 1111111 1000000
    assert encode_data_field(b"\xff", 7) == bytes([0x7F, 0x40])
    assert decode_data_field(bytes([0x7F, 0x40]), 7, 1) == b"\xff"


def test_round_trip_survives_a_length_that_is_not_a_multiple_of_seven():
    """The lengths that expose the alignment bug are the awkward ones."""
    for size in (1, 2, 3, 6, 7, 8, 100, 722, 814):
        payload = bytes((i * 37 + 11) & 0xFF for i in range(size))
        for bits in (4, 7):
            packed = encode_data_field(payload, bits)
            assert decode_data_field(packed, bits, size) == payload, (size, bits)


def test_encoded_length_is_what_the_protocol_predicts():
    """722 data bytes are 1444 nibble bytes and 826 bit-stream bytes — the sizes
    the instrument itself sends."""
    payload = bytes(722)
    assert len(encode_data_field(payload, 4)) == 1444
    assert len(encode_data_field(payload, 7)) == 826


def test_decode_honours_the_declared_size_and_drops_the_pad():
    """Trailing pad bits must not become an extra byte."""
    assert len(decode_data_field(bytes([0x7F] * 5), 7, 4)) == 4


def test_decode_rejects_a_byte_with_bits_above_the_field_width():
    """A byte with the high bit set is not valid 7-bit MIDI data; failing loudly
    beats silently decoding framing noise as object bytes."""
    with pytest.raises(ValueError):
        decode_data_field(bytes([0xFF, 0x00]), 7, 1)
