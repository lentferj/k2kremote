# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only. The fixtures are built with the real MacroEntry/MacroTable
# classes and serialized the way the instrument would, so they cannot drift from
# the format the code actually parses — and no capture from the owner's disk is
# committed, so no third-party library names end up in the repository.

import pytest

from k2kmaced import online
from k2kmaced.macfile import MacError, MacroEntry, MacroTable, PramFile

#: Overwrite and Fill, per MAC_FORMAT §5. Codes 2 and 3 are the two confirmed
#: against the instrument's own Macro page.
FILL, OVERWRITE = 2, 3
SCSI0 = 1


def entry(filename, bank, mode=OVERWRITE, path="\\"):
    return MacroEntry(drive=SCSI0, bank=bank, mode=mode, path=path,
                      filename=filename)


def table(*entries):
    return MacroTable(list(entries))


def serialized(*entries):
    """The object-block bytes, as the K2000 returns them from a live read.

    The RAM layout and the `.MAC` file's object block are byte-identical
    (verified on hardware), so serializing the table is a faithful stand-in for
    what comes back over MIDI.
    """
    return table(*entries).serialize()


class FakeBridge:
    """Just enough bridge to satisfy `read_live`."""

    description = "fake:in -> fake:out"

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def read_macro_table(self, timeout=None):
        self.calls += 1
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def close(self):
        pass


# --- read_live ---------------------------------------------------------------

def test_read_live_parses_the_object_the_device_returns():
    data = serialized(entry("BOOT1.KRZ", 200), entry("BOOT2.KRZ", 300, FILL))
    live = online.read_live(FakeBridge(data))
    assert len(live) == 2
    assert "BOOT1.KRZ" in live.entries[0].display()
    assert live.entries[1].mode_letter == "F"


def test_read_live_says_so_when_nothing_is_recorded():
    """An empty object means "no macro recorded", which is a real state and not
    a parse failure — so it must not surface as a struct error."""
    with pytest.raises(MacError) as exc:
        online.read_live(FakeBridge(b""))
    assert "nothing has been recorded" in str(exc.value)


def test_read_live_blames_the_id_rather_than_the_parser():
    """Type 100 is the *Table* type and holds unrelated objects — id 16 is
    `Master`. Reading the wrong id returns a few hundred plausible-looking bytes,
    so the error has to point at the id, which is the actual mistake."""
    with pytest.raises(MacError) as exc:
        online.read_live(FakeBridge(b"\x00\x01\x02not a macro at all" * 8))
    message = str(exc.value)
    assert "did not parse" in message
    assert "35" in message and "100" in message


def test_read_live_reports_the_byte_count_it_could_not_parse():
    junk = bytes(range(64))
    with pytest.raises(MacError) as exc:
        online.read_live(FakeBridge(junk))
    assert "64 bytes" in str(exc.value)


# --- diff --------------------------------------------------------------------

def test_diff_reports_identical_tables_as_identical():
    a = table(entry("A.KRZ", 200), entry("B.KRZ", 300))
    b = table(entry("A.KRZ", 200), entry("B.KRZ", 300))
    rows = online.diff(list(a), list(b))
    assert all(r.same for r in rows)
    assert "identical" in online.summarise(rows)


def test_diff_spots_a_changed_bank():
    a = table(entry("A.KRZ", 200))
    b = table(entry("A.KRZ", 900))
    rows = online.diff(list(a), list(b))
    assert not rows[0].same
    assert "1 of 1" in online.summarise(rows)


def test_diff_spots_a_changed_mode():
    """Overwrite versus Fill decides whether a load lands at the bank base or
    after whatever is already resident — a difference worth catching."""
    rows = online.diff(list(table(entry("A.KRZ", 200, OVERWRITE))),
                       list(table(entry("A.KRZ", 200, FILL))))
    assert not rows[0].same


def test_diff_does_not_drop_the_tail_when_lengths_differ():
    """The appended entry is exactly what you are looking for, and zip() would
    silently discard it."""
    short = table(entry("A.KRZ", 200))
    long_ = table(entry("A.KRZ", 200), entry("B.KRZ", 300), entry("C.KRZ", 400))
    rows = online.diff(list(short), list(long_))
    assert len(rows) == 3
    assert rows[0].same
    assert rows[1].live is None and rows[1].other is not None
    assert not rows[1].same and not rows[2].same


def test_diff_is_symmetric_about_which_side_is_missing():
    short, long_ = table(entry("A.KRZ", 200)), table(entry("A.KRZ", 200),
                                                     entry("B.KRZ", 300))
    forward = online.diff(list(short), list(long_))
    backward = online.diff(list(long_), list(short))
    assert len(forward) == len(backward) == 2
    assert forward[1].live is None and backward[1].other is None


def test_diff_row_renders_a_missing_side_visibly():
    row = online.DiffRow(3, "0:\\A.KRZ  200:O:", None)
    text = row.format()
    assert text.startswith("!!")
    assert "—" in text


def test_summarise_names_the_first_differing_index():
    a = table(entry("A.KRZ", 200), entry("B.KRZ", 300), entry("C.KRZ", 400))
    b = table(entry("A.KRZ", 200), entry("B.KRZ", 300), entry("C.KRZ", 900))
    assert "index 2" in online.summarise(online.diff(list(a), list(b)))


def test_diff_reports_a_selected_object_list_as_a_difference():
    """`extra` is not cosmetic: it is where a selected-object list lives.

    An entry with one loads only the objects named in it, not the whole file, so
    two entries pointing at the same file with and without a list do NOT load the
    same thing. `display()` marks it `Obj` and the diff must show it. This test
    was originally written the other way round, asserting that `extra` could be
    ignored, and it failed — which is how the distinction was found."""
    plain = entry("A.KRZ", 200)
    with_list = MacroEntry(drive=SCSI0, bank=200, mode=OVERWRITE, path="\\",
                           filename="A.KRZ", extra=b"\x01\x02\x03\x04")
    assert with_list.has_object_list
    rows = online.diff([plain], [with_list])
    assert not rows[0].same
    assert "Obj" in rows[0].other and "Obj" not in rows[0].live


# --- the object identity -----------------------------------------------------

def test_object_identity_matches_the_offline_parser():
    """One definition of type/id, not two that can drift apart."""
    from k2kmaced import macfile

    assert online.MACRO_TYPE == macfile.MACRO_TYPE == 100
    assert online.MACRO_ID == macfile.MACRO_ID == 35


def test_the_ram_layout_assumption_is_stated_by_a_round_trip():
    """`read_live` relies on the RAM object being the file's object block.

    Verified on hardware; asserted here as a round-trip so a change to the
    serializer that would break the live path fails in CI rather than on a
    K2000."""
    data = serialized(entry("A.KRZ", 200), entry("B.KRZ", 300, FILL))
    assert MacroTable.parse(data).serialize() == data
    # And the same bytes must sit inside a .MAC container unchanged.
    pram = PramFile.for_macro(MacroTable.parse(data))
    assert data in pram.serialize()


# --- push --------------------------------------------------------------------

class FakeWriteBridge:
    """A bridge that stores what it is written and serves it back.

    `echo=False` models the case that matters: the write is accepted but the
    object that comes back is not the one that went out.
    """

    description = "fake:in -> fake:out"

    def __init__(self, initial=b"", *, echo=True, dnak=None):
        self.stored = initial
        self.echo = echo
        self.dnak = dnak
        self.writes = []

    def read_macro_table(self, timeout=None):
        return self.stored

    def write_macro_table(self, data, name="Macro"):
        self.writes.append(data)
        if self.dnak is not None:
            return self.dnak
        if self.echo:
            self.stored = data
        return object()          # a DACK carries no `code`

    def close(self):
        pass


class _Dnak:
    class code:
        name = "RAMIsFull"


def test_push_writes_and_returns_the_read_back_table():
    wanted = table(entry("A.KRZ", 200), entry("B.KRZ", 300, FILL))
    bridge = FakeWriteBridge(serialized(entry("OLD.KRZ", 100)))
    got = online.push(bridge, wanted)
    assert len(bridge.writes) == 1
    assert bridge.writes[0] == wanted.serialize()
    assert [e.display() for e in got] == [e.display() for e in wanted]


def test_push_saves_the_previous_table_first(tmp_path):
    """The backup is taken BEFORE the write, so it holds the old contents."""
    old = serialized(entry("OLD.KRZ", 100))
    bridge = FakeWriteBridge(old)
    backup = tmp_path / "before.bin"
    online.push(bridge, table(entry("NEW.KRZ", 200)), backup_path=str(backup))
    assert backup.read_bytes() == old


def test_push_refuses_an_empty_table_without_sending_anything():
    """An empty table is indistinguishable from a bug that produced no entries,
    and the result looks like the instrument forgot its configuration."""
    bridge = FakeWriteBridge(serialized(entry("A.KRZ", 200)))
    with pytest.raises(online.PushRefused):
        online.push(bridge, table())
    assert bridge.writes == []


def test_push_allows_an_empty_table_when_asked_explicitly():
    bridge = FakeWriteBridge(serialized(entry("A.KRZ", 200)))
    online.push(bridge, table(), allow_empty=True)
    assert len(bridge.writes) == 1


def test_push_reports_a_dnak_with_its_reason():
    bridge = FakeWriteBridge(serialized(entry("A.KRZ", 200)), dnak=_Dnak())
    with pytest.raises(online.PushUnverified) as exc:
        online.push(bridge, table(entry("B.KRZ", 300)))
    assert "RAMIsFull" in str(exc.value)


def test_push_fails_loudly_when_the_read_back_differs():
    """A DACK says the message was accepted, not that the bytes are right.

    If the object that comes back is not the one sent, the live table is in an
    unknown state and must not be saved to disk — so this must raise rather than
    report success."""
    bridge = FakeWriteBridge(serialized(entry("A.KRZ", 200)), echo=False)
    with pytest.raises(online.PushUnverified) as exc:
        online.push(bridge, table(entry("B.KRZ", 300)))
    message = str(exc.value)
    assert "UNKNOWN" in message
    assert "must not be saved" in message


def test_push_points_at_the_backup_when_verification_fails(tmp_path):
    backup = tmp_path / "before.bin"
    bridge = FakeWriteBridge(serialized(entry("A.KRZ", 200)), echo=False)
    with pytest.raises(online.PushUnverified) as exc:
        online.push(bridge, table(entry("B.KRZ", 300)), backup_path=str(backup))
    assert str(backup) in str(exc.value)


# --- the selected marker -----------------------------------------------------

def test_a_selected_entry_parses_and_round_trips():
    """The K2000 stores its `*` selection marker in the entry's length word.

    The Save page's `All` soft key sets it on every entry, so a table read back
    afterwards carried 0x8000 on each length — which parsed as a 32802-byte
    entry and failed with "runs past the object data". It is a flag, not
    corruption, and the table behind it was perfectly intact."""
    from k2kmaced.macfile import ENTRY_SELECTED

    plain = serialized(entry("A.KRZ", 200), entry("B.KRZ", 300, FILL))
    marked = bytearray(plain)
    marked[0] |= ENTRY_SELECTED >> 8          # mark the first entry

    table = MacroTable.parse(bytes(marked))
    assert len(table.entries) == 2
    assert table.entries[0].selected is True
    assert table.entries[1].selected is False
    assert table.serialize() == bytes(marked), "the marker must survive a round trip"


def test_every_entry_marked_still_parses():
    """`All` marks the lot, which is the case that actually failed."""
    from k2kmaced.macfile import ENTRY_SELECTED

    data = bytearray(serialized(entry("A.KRZ", 200), entry("B.KRZ", 300),
                                entry("C.KRZ", 400)))
    pos = 0
    for _ in range(3):
        length = ((data[pos] << 8) | data[pos + 1]) & ~ENTRY_SELECTED
        data[pos] |= ENTRY_SELECTED >> 8
        pos += length
    table = MacroTable.parse(bytes(data))
    assert len(table.entries) == 3
    assert all(e.selected for e in table.entries)
    assert table.serialize() == bytes(data)


def test_clearing_the_marker_shortens_nothing():
    """Length and flag share a word; clearing the flag must not change the size."""
    table = MacroTable.parse(serialized(entry("A.KRZ", 200)))
    before = len(table.serialize())
    table.entries[0].selected = True
    assert len(table.serialize()) == before
