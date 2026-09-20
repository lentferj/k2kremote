# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# These tests use fake MIDI ports — no hardware required.

import time
from types import SimpleNamespace

import pytest

from k2kremote import midi_bridge
from k2kremote.midi_bridge import (ThrottledOut, MultiIn, BridgeConfig, MidiBridge,
                                   SEND_GAP, SYSEX_FLOOR)


class FakeOut:
    def __init__(self):
        self.sent = []

    def send_message(self, message):
        self.sent.append(list(message))


class FakePort:
    """A fake rtmidi MidiIn/MidiOut sharing one port list, for construction tests."""

    PORTS = ["k2000r in", "USB MIDI 1", "USB MIDI 2", "My Synth"]

    def __init__(self, queue_size_limit=None):
        self.opened = None

    def get_ports(self):
        return list(self.PORTS)

    def open_port(self, index):
        self.opened = index

    def ignore_types(self, **kwargs):
        pass

    def send_message(self, message):
        pass

    def get_message(self):
        return None

    def close_port(self):
        pass


class FakeRtmidi:
    MidiOut = FakePort
    MidiIn = FakePort


def test_to_ascii7_masks_high_bit():
    # A reverse-video 'D' (0xC4) masks back to 'D'; a bare 0x80 -> space.
    assert midi_bridge._to_ascii7("\xc4" + "\x80") == "D "


def test_high_bit_rows_marks_reverse_cells():
    from k2kremote.midi_bridge import _high_bit_rows
    # "AB" with B reverse-video (high bit), newline, then plain "Cd".
    rows = _high_bit_rows("A\xc2\nCd")
    assert rows == ["01", "00"]


def test_get_screen_text_attrs_returns_text_and_mask():
    bridge = MidiBridge.__new__(MidiBridge)
    bridge.timeout = 0.1
    bridge.client = SimpleNamespace(get_screen_text=lambda timeout: "A\xc2\nCd")
    text, mask = bridge.get_screen_text_attrs()
    assert text == "AB\nCd"        # high bit stripped from 0xC2 -> 'B'
    assert mask == ["01", "00"]    # and recorded as reverse-video


def test_throttle_enforces_gap_for_sysex():
    out = ThrottledOut(FakeOut(), gap=0.05)
    start = time.time()
    out.send_message([0xF0, 0x07, 0x00, 0x78, 0x18, 0xF7])
    out.send_message([0xF0, 0x07, 0x00, 0x78, 0x18, 0xF7])
    assert time.time() - start >= 0.05  # second SysEx waited for the gap


def test_gap_is_clamped_to_the_hardware_floor():
    """The 120 ms floor is a property of the K2000's CPU, not a preference.

    A too-small gap garbles the LCD, and that failure shows up on the panel
    rather than in any reply — so no caller (config file, --sysex-interval, API
    user) is trusted to go under it.
    """
    assert ThrottledOut(FakeOut(), gap=0.0)._gap == SYSEX_FLOOR
    assert ThrottledOut(FakeOut(), gap=-1)._gap == SYSEX_FLOOR
    assert ThrottledOut(FakeOut(), gap=0.5)._gap == 0.5  # slower is always allowed
    assert SEND_GAP >= SYSEX_FLOOR                       # ...including the default


def test_non_sysex_is_not_throttled():
    # Notes/CC must stay real-time — only SysEx floods the LCD CPU.
    out = ThrottledOut(FakeOut(), gap=1.0)
    start = time.time()
    out.send_message([0x90, 0x40, 0x7F])
    out.send_message([0x80, 0x40, 0x00])
    assert time.time() - start < 0.5


def test_panic_sends_all_notes_off_on_all_channels():
    fake = FakeOut()
    bridge = MidiBridge(SimpleNamespace(midi_out=fake, midi_in=None), "stub")
    bridge.panic()
    assert len(fake.sent) == 32  # 16 channels x (CC120 All-Sound-Off + CC123 All-Notes-Off)
    assert [0xB0, 120, 0] in fake.sent and [0xB0, 123, 0] in fake.sent  # ch 0
    assert [0xBF, 120, 0] in fake.sent and [0xBF, 123, 0] in fake.sent  # ch 15


def test_device_id_rewrite_on_k2_sysex():
    fake = FakeOut()
    out = ThrottledOut(fake, gap=0.0, device_id=127)
    # K2 packet: F0 07 <dev> 78 ... — dev byte must become 127.
    out.send_message([0xF0, 0x07, 0x00, 0x78, 0x18, 0xF7])
    assert fake.sent[0][2] == 127


def test_device_id_not_touched_for_non_k2_messages():
    fake = FakeOut()
    out = ThrottledOut(fake, gap=0.0, device_id=127)
    out.send_message([0x90, 0x40, 0x7F])  # a note-on, not SysEx
    assert fake.sent[0] == [0x90, 0x40, 0x7F]


def test_device_id_tolerance_decodes_foreign_reply():
    midi_bridge._install_device_id_tolerance()
    from k2000.messages import SysexMessage, ScreenReply

    # A text screen reply, re-stamped with a non-zero device id (as a broadcast
    # K2000 would answer).  It must still validate and decode.
    encoded = bytearray(ScreenReply.from_text("HELLO").encode())
    encoded[2] = 42
    encoded = bytes(encoded)

    assert SysexMessage.has_valid_k2_headers(encoded)
    decoded = SysexMessage.decode(encoded)
    assert str(decoded) == "HELLO"


def test_device_id_tolerance_is_idempotent():
    midi_bridge._install_device_id_tolerance()
    midi_bridge._install_device_id_tolerance()
    from k2000 import messages

    assert messages._k2kremote_devid_tolerant is True


class FakeMidiIn:
    """Minimal rtmidi.MidiIn stand-in for MultiIn tests."""

    _registry = {}

    def __init__(self, queue_size_limit=None):
        self._opened = None

    def get_ports(self):
        return ["USB MIDI 1", "USB MIDI 2", "Other Device"]

    def open_port(self, index):
        self._opened = index
        self.queue = list(FakeMidiIn._registry.get(index, []))

    def ignore_types(self, **kwargs):
        pass

    def get_message(self):
        if getattr(self, "queue", None):
            return self.queue.pop(0)
        return None


def test_multi_in_merges_matching_ports(monkeypatch):
    # Port index 1 (second sub-port) holds the reply.
    FakeMidiIn._registry = {1: [([0xF0, 0x07, 0x00, 0x78, 0xF7], 0.0)]}
    monkeypatch.setattr(midi_bridge.rtmidi, "MidiIn", FakeMidiIn)

    multi = MultiIn("USB MIDI")
    assert len(multi.ports) == 2  # both USB sub-ports, not "Other Device"
    assert multi.get_message() is not None
    assert multi.get_message() is None


def test_multi_in_requires_a_match(monkeypatch):
    FakeMidiIn._registry = {}
    monkeypatch.setattr(midi_bridge.rtmidi, "MidiIn", FakeMidiIn)
    with pytest.raises(RuntimeError):
        MultiIn("No Such Port")


def test_bridge_config_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    cfg = BridgeConfig(rig="standard", port="My MIDI Port", device_id=127)
    cfg.save(str(path))

    loaded = BridgeConfig.load(str(path))
    assert loaded.rig == "standard"
    assert loaded.port == "My MIDI Port"
    assert loaded.device_id == 127


def test_bridge_config_split_rig_defaults(tmp_path):
    path = tmp_path / "config.toml"
    BridgeConfig(rig="split").save(str(path))
    loaded = BridgeConfig.load(str(path))
    assert loaded.rig == "split"
    assert loaded.send_port == midi_bridge.SPLIT_SEND_PORT
    assert loaded.recv_iface == midi_bridge.SPLIT_RECV_IFACE


def _stub_bridge():
    """A MidiBridge whose client only needs a recording midi_out."""
    return MidiBridge(SimpleNamespace(midi_out=FakeOut(), midi_in=None), "stub")


def test_alpha_wheel_small_turn_is_one_message():
    bridge = _stub_bridge()
    bridge.alpha_wheel(5)
    assert len(bridge.client.midi_out.sent) == 1
    bridge.alpha_wheel(0)  # no-op
    assert len(bridge.client.midi_out.sent) == 1


def test_alpha_wheel_chunks_large_turns():
    from k2000.messages import SysexMessage

    bridge = _stub_bridge()
    bridge.alpha_wheel(70)  # > one event's ±63 capacity
    sent = bridge.client.midi_out.sent
    assert len(sent) == 2
    total = 0
    for raw in sent:
        event = SysexMessage.decode(bytes(raw)).button_events[0]
        assert -63 <= event.alpha_wheel_clicks <= 63
        total += event.alpha_wheel_clicks
    assert total == 70


def test_rename_sends_one_change_with_whole_name_and_safe_newid():
    from k2000.definitions import ObjectType
    from k2000.messages import Change, Info, SysexMessage

    captured = {}

    def fake_send_and_receive(message, timeout):
        # Round-trip the wire bytes to prove the bridge emits a well-formed CHANGE.
        decoded = SysexMessage.decode(bytes(message.encode()))
        captured["msg"] = decoded
        return Info(decoded.type, decoded.idno, 0, True, decoded.name)

    bridge = MidiBridge(SimpleNamespace(_send_and_receive=fake_send_and_receive),
                        "stub", timeout=0.5)
    result = bridge.rename(ObjectType.Program, 300, "Wave Of Mutil")

    msg = captured["msg"]
    assert isinstance(msg, Change)
    assert msg.type is ObjectType.Program
    assert msg.idno == 300
    assert msg.newid == 0                      # never relocates / overwrites another id
    assert msg.name == "Wave Of Mutil"         # the whole string, in one message
    assert result == "Wave Of Mutil"           # device-confirmed name echoed back


def test_rename_rejects_non_ascii():
    from k2000.definitions import ObjectType

    bridge = MidiBridge(SimpleNamespace(), "stub")
    with pytest.raises(ValueError):
        bridge.rename(ObjectType.Program, 300, "Café")


def _capturing_bridge(captured, *, name="OBJ", idno_from="idno", timeout=0.5):
    """A MidiBridge whose _send_and_receive round-trips the wire bytes and returns
    a plausible INFO, recording the decoded message + the timeout it was sent with."""
    from k2000.messages import Info, SysexMessage

    def fake_send_and_receive(message, timeout):
        decoded = SysexMessage.decode(bytes(message.encode()))
        captured["msg"] = decoded
        captured["timeout"] = timeout
        idno = getattr(decoded, idno_from, 0)
        return Info(decoded.type, idno, 0, True, name)

    return MidiBridge(SimpleNamespace(_send_and_receive=fake_send_and_receive),
                      "stub", timeout=timeout)


def test_delete_object_sends_del():
    from k2000.definitions import ObjectType
    from k2000.messages import Del

    captured = {}
    bridge = _capturing_bridge(captured, name="DOOMED")
    info = bridge.delete_object(ObjectType.Program, 201)

    msg = captured["msg"]
    assert isinstance(msg, Del)
    assert msg.type is ObjectType.Program and msg.idno == 201
    assert info.name == "DOOMED"          # device-confirmed deleted object


def test_move_object_sends_change_with_newid_and_empty_name():
    from k2000.definitions import ObjectType
    from k2000.messages import Change

    captured = {}
    bridge = _capturing_bridge(captured, idno_from="newid", name="MOVED")
    bridge.move_object(ObjectType.Program, 201, 305)

    msg = captured["msg"]
    assert isinstance(msg, Change)
    assert msg.idno == 201 and msg.newid == 305   # relocates to the new id
    assert msg.name == ""                          # name left unchanged


def test_delete_bank_sends_delbank_for_one_type():
    from k2000.definitions import ObjectType
    from k2000.messages import DelBank

    captured = {}
    bridge = _capturing_bridge(captured, timeout=0.5)
    bridge.delete_bank(ObjectType.Program, 2)   # wipe one type's bank

    msg = captured["msg"]
    assert isinstance(msg, DelBank)
    assert msg.type is ObjectType.Program and msg.bank == 2


def test_delete_bank_treats_missing_ack_as_success():
    # The K2000 does not acknowledge DELBANK (verified live): a timeout must be
    # swallowed and reported as success, not surfaced as "no response".
    def fake(message, timeout):
        raise TimeoutError("no reply")

    bridge = MidiBridge(SimpleNamespace(_send_and_receive=fake), "stub", timeout=0.5)
    assert bridge.delete_bank(None, 2) is None        # no exception, returns None


def test_delete_everything_uses_type_zero_bank_127():
    from k2000.messages import DelBank, Info
    from k2000.definitions import ObjectType

    captured = {}

    def fake(message, timeout):
        captured["msg"] = message
        return Info(ObjectType.Program, 0, 0, True, "")

    bridge = MidiBridge(SimpleNamespace(_send_and_receive=fake), "stub", timeout=0.5)
    bridge.delete_bank(None, 127)   # the "Everything" nuke

    msg = captured["msg"]
    assert isinstance(msg, DelBank)
    assert msg.type.value == 0 and msg.bank == 127


def test_delete_everything_endofbank_reply_is_not_a_crash():
    # The K2000 *does* acknowledge the "Delete all objects" nuke (type 0, bank 127)
    # — with an ENDOFBANK whose type field is 0 ("all object types"). Decoding 0 as
    # ObjectType(0) used to raise and surface as "Failed to decode 9-byte packet as
    # 'EndOfBank' message"; the reply must now decode and the op report success.
    from k2000.client import K2BaseClient
    from k2000.encoding import encode
    from k2000.messages import EndOfBank, K2_HEADER, K2_FOOTER, SysexMessage

    # The on-the-wire ENDOFBANK the device sends back: type 0, bank 0.
    reply = K2_HEADER + bytes([EndOfBank._msg_type_int]) \
        + encode[7](0, 2) + encode[7](0, 1) + K2_FOOTER
    decoded = SysexMessage.decode(reply)
    assert isinstance(decoded, EndOfBank) and decoded.type is None  # no longer raises

    stub = SimpleNamespace(midi_out=FakeOut(), midi_in=SimpleNamespace(
        get_message=lambda: (list(reply), 0.0)))
    client = SimpleNamespace(
        _send_and_receive=lambda msg, timeout: K2BaseClient._send_and_receive(
            stub, msg, timeout))

    bridge = MidiBridge(client, "stub", timeout=0.5)
    assert bridge.delete_bank(None, 127) is None        # success, not an exception


def test_delete_bank_all_types_sends_type_zero():
    from k2000.definitions import ObjectType
    from k2000.messages import DelBank, Info

    captured = {}

    def fake(message, timeout):
        captured["msg"] = message      # an all-types DELBANK encodes type 0; on
        captured["timeout"] = timeout  # decode that maps back to type=None.
        return Info(ObjectType.Program, 0, 0, True, "")

    bridge = MidiBridge(SimpleNamespace(_send_and_receive=fake), "stub", timeout=0.5)
    bridge.delete_bank(None, 2)   # obj_type=None -> all object types in the bank

    msg = captured["msg"]
    assert isinstance(msg, DelBank)
    assert msg.type.value == 0    # the protocol's "all object types" selector
    assert msg.bank == 2


def test_object_name_reads_dir():
    from k2000.definitions import ObjectType

    # Goes through `_send_and_receive` with the BRIDGE's timeout, not the
    # vendored `client.dir()` whose hardcoded 1.0 s is the value
    # DEFAULT_TIMEOUT = 2.5 exists to replace.
    seen = {}

    def fake(message, timeout):
        seen["msg"], seen["timeout"] = message, timeout
        return SimpleNamespace(name="CMI VOICES")

    client = SimpleNamespace(_send_and_receive=fake)
    bridge = MidiBridge(client, "stub")
    assert bridge.object_name(ObjectType.Program, 201) == "CMI VOICES"
    assert seen["timeout"] == bridge.timeout != 1.0
    assert type(seen["msg"]).__name__ == "Dir"


class _QueuedMidiIn:
    """Feeds pre-encoded raw messages back, gated behind a companion
    `_RecordingMidiOut.send_message` having been called.

    Matches the real port's timing, which `list_bank`'s own drain-before-send
    step depends on: replies to THIS request only arrive after it is sent, so
    a fake that returns them regardless of timing would let the pre-send
    drain loop eat them before `list_bank` ever gets to the collection loop
    -- every test using this fixture would silently see an empty result
    without the gate, not just the one that means to test the drain.

    `pre_send`: messages that ARE already sitting in the buffer before
    `send_message` fires -- the stale backlog the drain step exists to
    discard.
    """

    def __init__(self, messages, *, pre_send=()):
        self._post = [(list(m.encode()), 0.0) for m in messages]
        self._pre = [(list(m.encode()), 0.0) for m in pre_send]
        self.sent = False

    def get_message(self):
        if not self.sent:
            return self._pre.pop(0) if self._pre else None
        return self._post.pop(0) if self._post else None


class _RecordingMidiOut:
    """Records outgoing SysEx and flips a paired `_QueuedMidiIn`'s gate."""

    def __init__(self, midi_in=None):
        self.sent = []
        self._midi_in = midi_in

    def send_message(self, data):
        self.sent.append(data)
        if self._midi_in is not None:
            self._midi_in.sent = True


def test_list_bank_collects_info_until_endofbank():
    from k2000.definitions import ObjectType
    from k2000.messages import DirBank, EndOfBank, Info, SysexMessage

    replies = [
        Info(ObjectType.Program, 300, 264, True, "CUT 000"),
        Info(ObjectType.Program, 301, 264, True, "CUT 010"),
        EndOfBank(ObjectType.Program, 3),
    ]
    midi_in = _QueuedMidiIn(replies)
    midi_out = _RecordingMidiOut(midi_in)
    bridge = MidiBridge(SimpleNamespace(midi_in=midi_in, midi_out=midi_out),
                        "stub")

    found, done = bridge.list_bank(ObjectType.Program, 3)

    assert done is True
    assert [info.idno for info in found] == [300, 301]
    assert [info.name for info in found] == ["CUT 000", "CUT 010"]

    sent = SysexMessage.decode(bytes(midi_out.sent[0]))
    assert isinstance(sent, DirBank)
    assert sent.type is ObjectType.Program and sent.bank == 3


def test_list_bank_reports_incomplete_without_endofbank():
    from k2000.definitions import ObjectType
    from k2000.messages import Info

    replies = [Info(ObjectType.Program, 300, 264, True, "CUT 000")]
    midi_in = _QueuedMidiIn(replies)
    midi_out = _RecordingMidiOut(midi_in)
    bridge = MidiBridge(SimpleNamespace(midi_in=midi_in, midi_out=midi_out),
                        "stub")

    found, done = bridge.list_bank(ObjectType.Program, 3, quiet_for=0.05)

    assert done is False          # no EndOfBank seen -- an unconfirmed listing
    assert len(found) == 1


def test_list_bank_drains_stale_messages_before_sending():
    from k2000.definitions import ObjectType
    from k2000.messages import EndOfBank, Info

    midi_in = _QueuedMidiIn(
        [Info(ObjectType.Program, 300, 264, True, "CUT 000"),
         EndOfBank(ObjectType.Program, 3)],
        pre_send=[Info(ObjectType.Program, 999, 1, True, "STALE")])
    midi_out = _RecordingMidiOut(midi_in)
    bridge = MidiBridge(SimpleNamespace(midi_in=midi_in, midi_out=midi_out),
                        "stub")

    found, done = bridge.list_bank(ObjectType.Program, 3)

    # the stale reply (buffered before the request was even sent) must not
    # appear in the result -- it is drained, not collected.
    assert [info.idno for info in found] == [300]
    assert done is True


def test_read_object_bytes_sends_dump_with_offset_and_size():
    from k2000.definitions import ObjectType
    from k2000.messages import Dump, Load, SysexMessage

    captured = {}

    def fake_send_and_receive(message, timeout):
        decoded = SysexMessage.decode(bytes(message.encode()))
        captured["msg"] = decoded
        captured["timeout"] = timeout
        return Load(decoded.type, decoded.idno, decoded.offset, decoded.form,
                   b"\x2a\x03")

    bridge = MidiBridge(SimpleNamespace(_send_and_receive=fake_send_and_receive),
                        "stub", timeout=1.7)
    result = bridge.read_object_bytes(ObjectType.Program, 906, 215, 2)

    msg = captured["msg"]
    assert isinstance(msg, Dump)
    assert (msg.type, msg.idno, msg.offset, msg.size) == \
        (ObjectType.Program, 906, 215, 2)
    assert captured["timeout"] == 1.7   # the bridge's own configured timeout,
                                        # not the vendored client.dump()'s
                                        # hardcoded (and too-short) 1.0s
    assert result == b"\x2a\x03"


def test_patch_object_bytes_verifies_and_returns_on_match():
    from k2000.definitions import ObjectType
    from k2000.messages import DataAcknowledged, Load, SysexMessage

    captured = {"sent": []}

    def fake_send_and_receive(message, timeout):
        decoded = SysexMessage.decode(bytes(message.encode()))
        captured["sent"].append(decoded)
        if isinstance(decoded, Load):
            return DataAcknowledged(decoded.type, decoded.idno,
                                    decoded.offset, len(decoded.data))
        # the verifying read-back (a Dump) -- answer with what was written
        return Load(decoded.type, decoded.idno, decoded.offset, decoded.form,
                   b"\x28")

    bridge = MidiBridge(SimpleNamespace(_send_and_receive=fake_send_and_receive),
                        "stub")
    result = bridge.patch_object_bytes(ObjectType.Program, 906, 215, b"\x28")

    load_msg, dump_msg = captured["sent"]
    assert load_msg.data == b"\x28" and load_msg.offset == 215
    assert dump_msg.offset == 215 and dump_msg.size == 1
    assert result == b"\x28"


def test_patch_object_bytes_raises_on_dnak_without_reading_back():
    from k2000.definitions import ObjectType
    from k2000.messages import DataNotAcknowledged, Load, SysexMessage
    from k2kremote.midi_bridge import PatchUnverified

    def fake_send_and_receive(message, timeout):
        decoded = SysexMessage.decode(bytes(message.encode()))
        assert isinstance(decoded, Load), "must not read back after a DNAK"
        return DataNotAcknowledged(
            decoded.type, decoded.idno, decoded.offset, len(decoded.data),
            DataNotAcknowledged.ErrorCode.ObjectCurrentlyBeingEdited)

    bridge = MidiBridge(SimpleNamespace(_send_and_receive=fake_send_and_receive),
                        "stub")

    with pytest.raises(PatchUnverified, match="ObjectCurrentlyBeingEdited"):
        bridge.patch_object_bytes(ObjectType.Program, 906, 215, b"\x28")


def test_patch_object_bytes_raises_on_readback_mismatch():
    from k2000.definitions import ObjectType
    from k2000.messages import DataAcknowledged, Load, SysexMessage
    from k2kremote.midi_bridge import PatchUnverified

    def fake_send_and_receive(message, timeout):
        decoded = SysexMessage.decode(bytes(message.encode()))
        if isinstance(decoded, Load):
            return DataAcknowledged(decoded.type, decoded.idno,
                                    decoded.offset, len(decoded.data))
        return Load(decoded.type, decoded.idno, decoded.offset, decoded.form,
                   b"\xff")  # wrong -- not what was written

    bridge = MidiBridge(SimpleNamespace(_send_and_receive=fake_send_and_receive),
                        "stub")

    with pytest.raises(PatchUnverified, match="UNKNOWN state"):
        bridge.patch_object_bytes(ObjectType.Program, 906, 215, b"\x28")


def test_reselect_program_types_digits_then_enter():
    from k2000.definitions import Button

    pressed = []
    bridge = MidiBridge(SimpleNamespace(press_button=pressed.append), "stub")
    bridge.reselect_program(201)
    assert pressed == [Button.Number2, Button.Number0, Button.Number1, Button.Enter]


def test_standard_construction(monkeypatch):
    monkeypatch.setattr(midi_bridge, "rtmidi", FakeRtmidi)
    bridge = MidiBridge.standard("My Synth")
    assert "My Synth" in bridge.description
    assert bridge.client.port_name == "My Synth"


def test_split_rig_construction(monkeypatch):
    monkeypatch.setattr(midi_bridge, "rtmidi", FakeRtmidi)
    bridge = MidiBridge.split_rig()
    # MultiIn opened both USB sub-ports, not the send port or the other synth.
    assert len(bridge.client.midi_in.ports) == 2


def test_from_config_builds_standard(monkeypatch):
    monkeypatch.setattr(midi_bridge, "rtmidi", FakeRtmidi)
    bridge = MidiBridge.from_config(BridgeConfig(rig="standard", port="My Synth"))
    assert bridge.client.port_name == "My Synth"


def test_from_config_builds_split(monkeypatch):
    monkeypatch.setattr(midi_bridge, "rtmidi", FakeRtmidi)
    bridge = MidiBridge.from_config(BridgeConfig(rig="split"))
    assert len(bridge.client.midi_in.ports) == 2


def test_to_ascii7_masks_reverse_video():
    assert midi_bridge._to_ascii7("AB") == "AB"
    # Reverse-video 'OK' (high bit set) must mask back to plain ASCII.
    assert midi_bridge._to_ascii7(chr(ord("O") | 0x80) + chr(ord("K") | 0x80)) == "OK"
    # A bare 0x80 -> NUL -> space; newlines preserved.
    assert midi_bridge._to_ascii7("A" + chr(0x80) + "B\nC") == "A B\nC"


def test_get_screen_text_masks_high_bit():
    raw = chr(ord("O") | 0x80) + chr(ord("K") | 0x80) + "\nNormal"
    client = SimpleNamespace(get_screen_text=lambda timeout=None: raw)
    bridge = MidiBridge(client, "stub")
    assert bridge.get_screen_text() == "OK\nNormal"




class ScanRtmidi:
    """Fake rtmidi for the general autodetect scan: sending an ALLTEXT request out
    the 'K2000' output makes a K2 screen reply appear on the 'K2000 In' input."""

    OUT_NAMES = ["Synth A", "K2000 Out"]
    IN_NAMES = ["Synth A In", "K2000 In:K2000 In MIDI 1"]
    K2_OUT = 1
    K2_IN = 1
    pending = {}  # in_index -> [ (data, ts) ]
    respond = True
    live_out = set()  # constructed-but-not-deleted MidiOut instances
    live_in = set()   # constructed-but-not-deleted MidiIn instances

    class MidiOut:
        def __init__(self):
            self.idx = None
            ScanRtmidi.live_out.add(id(self))

        def get_ports(self):
            return list(ScanRtmidi.OUT_NAMES)

        def open_port(self, i):
            self.idx = i

        def send_message(self, msg):
            from k2000.messages import ScreenReply
            if ScanRtmidi.respond and self.idx == ScanRtmidi.K2_OUT:
                reply = list(ScreenReply.from_screen_contents("ProgramMode").encode())
                ScanRtmidi.pending.setdefault(ScanRtmidi.K2_IN, []).append((reply, 0.0))

        def close_port(self):
            pass

        def delete(self):
            ScanRtmidi.live_out.discard(id(self))

    class MidiIn:
        def __init__(self, queue_size_limit=None):
            self.idx = None
            ScanRtmidi.live_in.add(id(self))

        def get_ports(self):
            return list(ScanRtmidi.IN_NAMES)

        def open_port(self, i):
            self.idx = i

        def ignore_types(self, **kw):
            pass

        def get_message(self):
            q = ScanRtmidi.pending.get(self.idx)
            return q.pop(0) if q else None

        def close_port(self):
            pass

        def delete(self):
            ScanRtmidi.live_in.discard(id(self))


def test_autodetect_general_scan_finds_device(monkeypatch):
    ScanRtmidi.pending = {}
    ScanRtmidi.respond = True
    monkeypatch.setattr(midi_bridge, "rtmidi", ScanRtmidi)
    bridge = MidiBridge.autodetect(scan_timeout=0.3)
    # Sends on each out, listens on all ins; binds recv to the reply's interface.
    assert "K2000 Out" in bridge.description
    assert "K2000 In" in bridge.description
    assert len(bridge.client.midi_in.ports) == 1  # the matched interface


def test_autodetect_raises_when_nothing_answers(monkeypatch):
    ScanRtmidi.pending = {}
    ScanRtmidi.respond = False  # no port replies
    monkeypatch.setattr(midi_bridge, "rtmidi", ScanRtmidi)
    with pytest.raises(RuntimeError, match="no K2000 answered"):
        MidiBridge.autodetect(scan_timeout=0.1)


def test_autodetect_success_frees_all_scan_clients(monkeypatch):
    # Regression: the scan opened a listener on every input and a probe out per
    # output, but only close_port()'d them — leaving the backend ALSA clients
    # alive until the process exits (open /dev/snd/seq → ENOMEM). Only the ports
    # of the connected rig may remain live after a successful autodetect.
    ScanRtmidi.pending = {}
    ScanRtmidi.respond = True
    ScanRtmidi.live_in = set()
    ScanRtmidi.live_out = set()
    monkeypatch.setattr(midi_bridge, "rtmidi", ScanRtmidi)
    bridge = MidiBridge.autodetect(scan_timeout=0.3)
    assert len(bridge.client.midi_in.ports) == 1
    assert len(ScanRtmidi.live_in) == 1   # only the merged recv sub-port
    assert len(ScanRtmidi.live_out) == 1  # only the chosen send port


def test_autodetect_failure_frees_all_scan_clients(monkeypatch):
    ScanRtmidi.pending = {}
    ScanRtmidi.respond = False
    ScanRtmidi.live_in = set()
    ScanRtmidi.live_out = set()
    monkeypatch.setattr(midi_bridge, "rtmidi", ScanRtmidi)
    with pytest.raises(RuntimeError, match="no K2000 answered"):
        MidiBridge.autodetect(scan_timeout=0.1)
    assert ScanRtmidi.live_in == set()   # every scan listener freed
    assert ScanRtmidi.live_out == set()  # every probe out freed


def test_bridge_close_frees_backend_clients(monkeypatch):
    ScanRtmidi.pending = {}
    ScanRtmidi.respond = True
    ScanRtmidi.live_in = set()
    ScanRtmidi.live_out = set()
    monkeypatch.setattr(midi_bridge, "rtmidi", ScanRtmidi)
    bridge = MidiBridge.autodetect(scan_timeout=0.3)
    bridge.close()
    assert ScanRtmidi.live_in == set()   # merged recv sub-ports deleted
    assert ScanRtmidi.live_out == set()  # send port deleted


def test_autodetect_binds_only_the_answering_subport(monkeypatch):
    # ESI-style: one physical interface exposes several IN sub-ports, but the
    # K2000 is cabled to exactly one, so its reply always lands on that sub-port.
    # Autodetect must bind the receive side to just that port — not open all four.
    monkeypatch.setattr(ScanRtmidi, "IN_NAMES",
                        ["ESI M4U eX:ESI M4U eX MIDI 1 48:0",
                         "ESI M4U eX:ESI M4U eX MIDI 2 48:1",
                         "ESI M4U eX:ESI M4U eX MIDI 3 48:2",
                         "ESI M4U eX:ESI M4U eX MIDI 4 48:3"])
    monkeypatch.setattr(ScanRtmidi, "K2_IN", 2)  # answers on the 3rd sub-port
    ScanRtmidi.pending = {}
    ScanRtmidi.respond = True
    ScanRtmidi.live_in = set()
    ScanRtmidi.live_out = set()
    monkeypatch.setattr(midi_bridge, "rtmidi", ScanRtmidi)

    bridge = MidiBridge.autodetect(scan_timeout=0.3)

    assert len(bridge.client.midi_in.ports) == 1     # only the answering sub-port
    assert "MIDI 3" in bridge.description            # bound to sub-port 3, not "MIDI 1"
    assert len(ScanRtmidi.live_in) == 1              # the other three scanners freed


def test_autodetect_does_not_hand_the_scan_timeout_to_the_bridge(monkeypatch):
    """A scan timeout is not an operational timeout, and mixing them froze the app.

    GETGRAPHICS takes 962.7 ms on real hardware. With the scan's 1.0 s reused as
    the bridge timeout, every full refresh had 26 ms of headroom, and any jitter
    raised TimeoutError — which the refresh worker treats as the device being
    gone: mirror marked disconnected, exponential backoff to 20 s. A hang we
    manufactured ourselves.
    """
    from k2kremote.midi_bridge import DEFAULT_TIMEOUT, MidiBridge

    built = {}

    def fake_connect_split(cls, send, recv, *, gap, device_id, timeout):
        built["timeout"] = timeout
        return "bridge"

    monkeypatch.setattr(MidiBridge, "_connect_split", classmethod(fake_connect_split))
    monkeypatch.setattr("k2kremote.midi_bridge._enum_out", lambda: ["k2000 out"])
    monkeypatch.setattr("k2kremote.midi_bridge._enum_in", lambda: [])
    monkeypatch.setattr("k2kremote.midi_bridge._await_screen_reply",
                        lambda listeners, timeout, is_reply: "k2000 in")

    class _Out:
        def open_port(self, i): pass
        def send_message(self, m): pass
        def close_port(self): pass
        def delete(self): pass

    monkeypatch.setattr("rtmidi.MidiOut", _Out)

    MidiBridge.autodetect(scan_timeout=0.05)
    assert built["timeout"] == DEFAULT_TIMEOUT, (
        "the bridge inherited the scan timeout again")
    # And whatever it is, it must clear a GETGRAPHICS with real margin.
    assert built["timeout"] > 2 * 0.9627


# --- a host with no MIDI backend is a legitimate state, not a crash ---------

def _no_backend(monkeypatch):
    """Make rtmidi behave as it does with no ALSA sequencer / CoreMIDI / WinMM."""
    class NoBackend:
        def __init__(self, *a, **k):
            raise SystemError(
                "MidiInAlsa::initialize: error creating ALSA sequencer client object")

    monkeypatch.setattr("rtmidi.MidiIn", NoBackend)
    monkeypatch.setattr("rtmidi.MidiOut", NoBackend)


def test_enumeration_degrades_instead_of_raising(monkeypatch):
    """rtmidi raises from the *constructor* on a headless host, and every entry
    point starts by enumerating — so an unguarded probe made `ports` and the
    port-picking path traceback on any container, CI runner or box without a
    sequencer."""
    from k2kremote import midi_bridge

    _no_backend(monkeypatch)
    assert midi_bridge.list_ports() == ([], [])
    assert midi_bridge.bidirectional_ports() == []
    assert "ALSA sequencer" in (midi_bridge.midi_backend_error() or "")


def test_ports_command_explains_itself_rather_than_raising(monkeypatch, capsys):
    from k2kremote import midi_bridge

    _no_backend(monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        midi_bridge._main(["ports"])
    message = str(excinfo.value.code)
    assert "no MIDI backend" in message
    assert "snd-seq" in message          # and says what to do about it


def test_backend_error_clears_once_enumeration_works(monkeypatch):
    """A stale reason must not outlive the failure that set it."""
    from k2kremote import midi_bridge

    _no_backend(monkeypatch)
    midi_bridge.list_ports()
    assert midi_bridge.midi_backend_error() is not None

    class Fine:
        def __init__(self, *a, **k): pass
        def get_ports(self): return ["Some Port 1"]
        def delete(self): pass

    monkeypatch.setattr("rtmidi.MidiIn", Fine)
    monkeypatch.setattr("rtmidi.MidiOut", Fine)
    assert midi_bridge.list_ports() == (["Some Port 1"], ["Some Port 1"])
    assert midi_bridge.midi_backend_error() is None


def test_rename_refuses_control_characters_over_long_names_and_a_wrong_echo():
    """`isascii()` alone was the whole guard.

    Control characters are ASCII — `\n`, `\x1b` and `\x00` all passed — and
    any length went to the wire while the docstring recorded the firmware's
    truncation of over-long names as unverified. Real DIRBANK names come back
    cut at exactly 16 ('Synth-PRO5 Sangr', 'Pad-PRO5 Lunar D'), so the field
    is 16 and the device does truncate: refusing is honest where guessing what
    would be stored is not.

    And the INFO reply is presented to the caller as device-confirmed, so it
    must actually match what was asked for.
    """
    from types import SimpleNamespace

    from k2000.definitions import ObjectType

    bridge = MidiBridge(SimpleNamespace(), "stub")
    for bad in ("with\nnewline", "esc\x1bhere", "nul\x00byte"):
        with pytest.raises(ValueError):
            bridge.rename(ObjectType.Program, 300, bad)
    with pytest.raises(ValueError):
        bridge.rename(ObjectType.Program, 300, "A" * 17)

    # a reply naming something else is not a confirmation
    from k2000.messages import Info
    client = SimpleNamespace(
        _send_and_receive=lambda m, t: Info(ObjectType.Program, 300, 0, True,
                                            "SOMETHING ELSE"))
    with pytest.raises(ValueError):
        MidiBridge(client, "stub").rename(ObjectType.Program, 300, "Good Name")
