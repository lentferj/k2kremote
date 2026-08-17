# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only: no MIDI hardware is ever opened. The one binary fixture,
# tests/fixtures/BOOT.MAC, is the real startup macro recovered from this
# project's K2000R disk-image backup — the ground truth the format was
# reverse-engineered from (docs/MAC_FORMAT.md).

from pathlib import Path

import pytest

from k2kmaced.macfile import (
    BANK_EVERYTHING,
    MACRO_ID,
    MACRO_TYPE,
    MacError,
    MacroEntry,
    MacroTable,
    PramFile,
)

FIXTURE = Path(__file__).parent / "fixtures" / "BOOT.MAC"


@pytest.fixture
def boot_bytes() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture
def boot(boot_bytes) -> PramFile:
    return PramFile.parse(boot_bytes)


# --- container -------------------------------------------------------------


def test_pram_container_holds_one_macro_table(boot):
    assert len(boot.objects) == 1
    obj = boot.objects[0]
    assert (obj.type, obj.idno, obj.name) == (MACRO_TYPE, MACRO_ID, "Macro")
    assert boot.software_version == 354  # K2000 OS v3.54 wrote this file
    assert boot.payload == b""           # a .MAC carries no PCM region


def test_hardware_written_file_round_trips_byte_exactly(boot, boot_bytes):
    assert boot.serialize() == boot_bytes


def test_rejects_foreign_data():
    with pytest.raises(MacError):
        PramFile.parse(b"RIFF" + bytes(64))
    with pytest.raises(MacError):
        PramFile.parse(b"PRAM")  # truncated header


def test_pram_without_a_macro_table_is_reported():
    pram = PramFile()
    with pytest.raises(MacError, match="no Macro Table"):
        pram.macro_table()


# --- the real boot macro ---------------------------------------------------


def test_decodes_the_real_boot_macro(boot):
    table = boot.macro_table()
    assert len(table) == 6

    first = table[0]
    # The manual's documented "clear everything at boot" trick, 13-64: load an
    # empty bank as Everything in Overwrite mode.
    assert first.filename == "NULL.KRZ"
    assert first.path == "\\"
    assert first.full_path == "\\NULL.KRZ"
    assert first.bank == BANK_EVERYTHING and first.bank_label == "E"
    assert first.mode_label == "Overwrite" and first.mode_letter == "O"
    assert first.drive_label == "SCSI 0"
    assert not first.has_object_list

    assert [e.bank for e in table][1:] == [200, 300, 400, 500, 600]
    assert [e.filename for e in table][1:] == [
        "KPOWFAV.KRZ", "LFOALFAV.KRZ", "SOARCFAV.KRZ",
        "TCNOAFAV.KRZ", "WAVSTFAV.KRZ",
    ]
    assert table[5].path == "\\-RLNDCD2\\"


def test_display_matches_the_k2000_macro_page(boot):
    # 13-45: "<drive>:<path>  <bank>:<mode>:<Obj>"
    assert boot.macro_table()[0].display().rstrip() == "0:\\NULL.KRZ" + " " * 19 + "E:O:"


# --- editing ---------------------------------------------------------------


def test_editing_an_entry_drops_the_verbatim_source(boot):
    table = boot.macro_table()
    entry = table[1]
    assert entry._source is not None
    entry.bank = 700
    assert entry._source is None          # rebuilt canonically from now on
    assert table[0]._source is not None   # untouched entries keep their bytes


def test_edited_entry_keeps_its_length_and_reparses(boot):
    table = boot.macro_table()
    before = len(table[1].serialize())
    table[1].bank = 700
    after = table[1].serialize()
    assert len(after) == before
    reparsed = MacroEntry.parse(after, 0)
    assert reparsed.bank == 700
    assert reparsed.filename == "KPOWFAV.KRZ" and reparsed.path == "\\--FAVS\\"
    # Canonical rebuild zeroes the padding the firmware left uninitialised.
    assert reparsed.trailer == 0


def test_write_back_into_the_container(boot):
    table = boot.macro_table()
    table.rebank(700, mode=2)
    boot.set_macro_table(table)
    again = PramFile.parse(boot.serialize()).macro_table()
    assert [e.bank for e in again] == [700] * 6
    assert {e.mode_label for e in again} == {"Fill"}


def test_move_reorders_and_clamps(boot):
    table = boot.macro_table()
    names = [e.filename for e in table]
    assert table.move(0, 5) == 5
    assert [e.filename for e in table] == names[1:] + names[:1]
    assert table.move(5, 99) == 5  # clamped at the end, no exception


def test_delete_and_reserialize(boot):
    table = boot.macro_table()
    table.entries.pop(0)
    boot.set_macro_table(table)
    again = PramFile.parse(boot.serialize()).macro_table()
    assert len(again) == 5 and again[0].filename == "KPOWFAV.KRZ"


# --- building from scratch -------------------------------------------------


def test_build_a_macro_from_scratch():
    entries = [
        MacroEntry(drive=1, bank=BANK_EVERYTHING, mode=3,
                   path="\\", filename="NULL.KRZ"),
        MacroEntry(drive=1, bank=200, mode=2,
                   path="\\ANALOG\\", filename="SYNAPSE.KRZ"),
    ]
    pram = PramFile.for_macro(MacroTable(entries))
    blob = pram.serialize()

    table = PramFile.parse(blob).macro_table()
    assert [e.full_path for e in table] == ["\\NULL.KRZ", "\\ANALOG\\SYNAPSE.KRZ"]
    assert [e.bank_label for e in table] == ["E", "200"]
    assert [e.mode_letter for e in table] == ["O", "F"]
    assert PramFile.parse(blob).serialize() == blob  # stable


def test_entry_lengths_follow_the_documented_formula():
    # 14-byte header + 16-byte name field + NUL-terminated path padded to even
    # + a 2-byte trailer.
    for path, expected in (("\\", 34), ("\\--FAVS\\", 42), ("\\-RLNDCD2\\", 44)):
        entry = MacroEntry(drive=1, bank=0, mode=2, path=path, filename="A.KRZ")
        assert len(entry.serialize()) == expected


def test_file_name_longer_than_the_field_is_refused():
    entry = MacroEntry(drive=1, bank=0, mode=2, path="\\",
                       filename="WAYTOOLONGNAME.KRZ")
    with pytest.raises(MacError, match="does not fit"):
        entry.serialize()


def test_empty_table_still_terminates():
    blob = PramFile.for_macro(MacroTable()).serialize()
    assert len(PramFile.parse(blob).macro_table()) == 0


# --- malformed input -------------------------------------------------------


def test_unterminated_table_is_rejected():
    entry = MacroEntry(drive=1, bank=0, mode=2, path="\\", filename="A.KRZ")
    with pytest.raises(MacError, match="not terminated"):
        MacroTable.parse(entry.serialize())


def test_entry_running_past_the_object_is_rejected():
    entry = MacroEntry(drive=1, bank=0, mode=2, path="\\", filename="A.KRZ")
    with pytest.raises(MacError, match="past the object"):
        MacroTable.parse(entry.serialize()[:-4])


def test_absurdly_short_entry_is_rejected():
    with pytest.raises(MacError, match="too short"):
        MacroTable.parse(b"\x00\x08" + bytes(6))


def test_unknown_codes_degrade_to_labels_not_crashes():
    entry = MacroEntry(drive=99, bank=250, mode=88, path="\\", filename="A.KRZ")
    assert entry.drive_label == "drive 99"
    assert entry.mode_label == "mode 88"
    assert entry.mode_letter == "?"
    assert entry.display().startswith("?:")
