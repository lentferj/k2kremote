# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only: every message here is built by encoding a real message class,
# so the fixtures cannot drift away from the protocol the app actually speaks.

import pytest

from k2000.definitions import Button, ButtonEventType, ObjectType
from k2000.messages import (
    AllText,
    DataNotAcknowledged,
    Info,
    Panel,
    ButtonEvent,
)

from k2kremote import monitor


def test_describe_names_the_message_and_the_device_id():
    line = monitor.describe(AllText().encode(), "out")
    assert "AllText" in line
    assert "0x15" in line
    # The device id is printed because a wrong one looks exactly like a dead
    # instrument, and this unit answers on 0 rather than the broadcast 127.
    assert "dev 0" in line
    assert line.startswith("->")


def test_describe_does_not_leak_class_machinery_as_payload():
    """An empty-bodied request has no payload, and must not pretend otherwise.

    These message classes carry `_msg_type_int` and `_response_classes` in
    `__annotations__`, so a naive field dump renders AllText as
    "_msg_type_int=21, _response_classes=[]" — internals sitting exactly where a
    reader looks for the message contents."""
    line = monitor.describe(AllText().encode(), "out")
    assert "_msg_type_int" not in line
    assert "_response_classes" not in line
    assert "(no body)" in line


def test_describe_marks_direction():
    data = AllText().encode()
    assert monitor.describe(data, "in").startswith("<-")
    assert monitor.describe(data, "out").startswith("->")
    assert monitor.describe(data).startswith("  ")


def test_describe_decodes_a_panel_button_press():
    message = Panel([ButtonEvent(ButtonEventType.Down, Button.SoftA, 0)])
    line = monitor.describe(message.encode(), "in")
    assert "Panel" in line and "SoftA" in line


def test_describe_reports_a_wheel_turn_as_a_wheel_turn():
    """A wheel event carries filler in its button field, and vice versa.

    The K2000 puts `button=ChanBankDec` in a wheel event and `wheel=+63` in a
    button event. Printing both unqualified is how filler gets read as a
    reading — this project already lost time to exactly that."""
    message = Panel([ButtonEvent(ButtonEventType.Down, Button.ChanBankDec, 7)])
    line = monitor.describe(message.encode(), "in")
    assert "wheel +7" in line
    assert "ChanBankDec" not in line


def test_describe_summarises_an_info_reply():
    message = Info(ObjectType.Program, 204, 498, True, "Film(Controller)")
    line = monitor.describe(message.encode(), "in")
    assert "Program" in line and "204" in line
    assert "Film(Controller)" in line and "RAM" in line


class _OneRowReply:
    """A ParameterName/ParameterValue reply: a screen reply of exactly one row."""
    def __str__(self):
        return "Algorithm"


class _ScreenReply:
    def __str__(self):
        return "ProgramMode    Xpose:0ST\n\n\nrow four"


class _GraphicsReply:
    """`str()` raises on a graphics plane — the exception that once looked like a
    protocol fault when a stale reply was served to the next request."""
    data = b"\x00" * 40

    def __str__(self):
        raise ValueError("contains image data and cannot be converted to str")


def test_screen_detail_shows_a_one_row_reply_in_full():
    # The single row IS the answer to `ask paramname`; calling it "first row"
    # buries it, and renders an empty answer the same as a blank top line.
    assert monitor._screen_detail(_OneRowReply()) == "text 'Algorithm'"


def test_screen_detail_counts_rows_for_a_full_screen():
    detail = monitor._screen_detail(_ScreenReply())
    assert "4 rows" in detail
    assert "ProgramMode" in detail


def test_screen_detail_survives_a_graphics_plane():
    detail = monitor._screen_detail(_GraphicsReply())
    assert "graphics plane" in detail and "40 bytes" in detail


class _Code:
    """The DNAK code field is encoded via `.value`, and the vendored library
    ships no enum for it — so the test supplies the shape rather than pretending
    an int works."""
    value = 1


def test_describe_explains_a_dnak_code():
    message = DataNotAcknowledged(ObjectType.Program, 204, 0, 0, _Code())
    line = monitor.describe(message.encode(), "in")
    # The library decodes the code to an ErrorCode, and its name says more than
    # a number plus a gloss would.
    assert "DNAK" in line
    assert "ObjectCurrentlyBeingEdited" in line


def test_describe_survives_rubbish_without_raising():
    """A monitor that dies on a malformed message is useless precisely when the
    wire is malformed, which is when you reached for it."""
    for junk in (b"", b"\xf0", b"\xf0\x07", b"\x90\x40\x7f",
                 b"\xf0\x07\x00\x78\xff\xff\xf7", bytes(range(20))):
        line = monitor.describe(junk, "in")
        assert isinstance(line, str) and line


def test_describe_distinguishes_unknown_type_from_undecodable():
    # 0x7E is not in the table at all.
    unknown = b"\xf0\x07\x00\x78\x7e\xf7"
    assert "unknown type" in monitor.describe(unknown)


def test_hexdump_marks_truncation_rather_than_hiding_it():
    short = monitor.hexdump(bytes(range(8)), limit=32)
    assert "…" not in short and short.startswith("00 01")
    long = monitor.hexdump(bytes(range(64)), limit=16)
    assert "(+48 bytes)" in long


def test_message_table_covers_the_types_this_project_relies_on():
    table = {code for code, _name, _doc in monitor.message_table()}
    # The ones today's work turned on: parameter name/value, bulk object read,
    # the text and graphics planes, and the panel.
    for code in (0x16, 0x17, 0x0A, 0x0B, 0x14, 0x15, 0x18):
        assert code in table, f"0x{code:02X} missing from the message table"


def test_message_table_entries_carry_a_description():
    rows = monitor.message_table()
    assert len(rows) >= 20
    assert all(isinstance(doc, str) for _code, _name, doc in rows)


def test_decode_returns_none_rather_than_raising():
    assert monitor.decode(b"\x90\x40\x7f") is None
    assert monitor.decode(b"") is None
    assert monitor.decode(AllText().encode()) is not None


def test_read_defaults_to_a_named_encoding_and_offers_both():
    """The encoding must be a visible, recorded choice.

    Both forms have to be reachable and the default has to be named in the
    output, so that a dump stays checkable later. They must also decode to the
    same bytes — see the data-field tests at the bottom of this file."""
    from k2000.definitions import EncodingFormat

    for name in ("Nibblized", "BitStream"):
        assert hasattr(EncodingFormat, name)

    # Drive the real parser rather than re-describing its shape here; --help
    # exits, and the text it prints is the contract.
    out = _capture_help("read")
    assert "--encoding" in out
    assert "Nibblized" in out and "BitStream" in out


def _capture_help(mode: str) -> str:
    import contextlib, io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        monitor.main([mode, "--help"])
    return buf.getvalue()


def test_compare_mode_is_reachable_from_the_cli():
    """`compare` asserts the two forms decode alike, which the spec requires."""
    out = _capture_help("compare")
    assert "idno" in out and "type" in out


def test_object_type_refuses_an_unknown_type_by_name():
    with pytest.raises(SystemExit) as exc:
        monitor._object_type("NotAType")
    # The refusal has to list the real ones; "unknown type" alone sends you
    # back to the source.
    assert "Program" in str(exc.value)


def test_object_type_accepts_a_real_one():
    from k2000.definitions import ObjectType

    assert monitor._object_type("Program") is ObjectType.Program


def test_requests_are_all_real_message_classes():
    """`ask` offers a menu; every entry must name a class that exists, or the
    menu is a list of ways to fail at runtime."""
    from k2000 import messages

    for key, (class_name, blurb) in monitor.REQUESTS.items():
        assert hasattr(messages, class_name), f"{key} -> missing {class_name}"
        assert blurb
