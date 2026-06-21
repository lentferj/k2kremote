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
from k2kremote.midi_bridge import ThrottledOut, MultiIn, BridgeConfig, MidiBridge


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
    result = bridge.rename(ObjectType.Program, 300, "Wave Of Mutilation")

    msg = captured["msg"]
    assert isinstance(msg, Change)
    assert msg.type is ObjectType.Program
    assert msg.idno == 300
    assert msg.newid == 0                      # never relocates / overwrites another id
    assert msg.name == "Wave Of Mutilation"    # the whole string, in one message
    assert result == "Wave Of Mutilation"      # device-confirmed name echoed back


def test_rename_rejects_non_ascii():
    from k2000.definitions import ObjectType

    bridge = MidiBridge(SimpleNamespace(), "stub")
    with pytest.raises(ValueError):
        bridge.rename(ObjectType.Program, 300, "Café")


def test_object_name_reads_dir():
    from k2000.definitions import ObjectType

    client = SimpleNamespace(dir=lambda t, i: SimpleNamespace(name="CMI VOICES"))
    bridge = MidiBridge(client, "stub")
    assert bridge.object_name(ObjectType.Program, 201) == "CMI VOICES"


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

    class MidiOut:
        def __init__(self):
            self.idx = None

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

    class MidiIn:
        def __init__(self, queue_size_limit=None):
            self.idx = None

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


def test_autodetect_general_scan_finds_device(monkeypatch):
    ScanRtmidi.pending = {}
    ScanRtmidi.respond = True
    monkeypatch.setattr(midi_bridge, "rtmidi", ScanRtmidi)
    bridge = MidiBridge.autodetect(timeout=0.3)
    # Sends on each out, listens on all ins; binds recv to the reply's interface.
    assert "K2000 Out" in bridge.description
    assert "K2000 In" in bridge.description
    assert len(bridge.client.midi_in.ports) == 1  # the matched interface


def test_autodetect_raises_when_nothing_answers(monkeypatch):
    ScanRtmidi.pending = {}
    ScanRtmidi.respond = False  # no port replies
    monkeypatch.setattr(midi_bridge, "rtmidi", ScanRtmidi)
    with pytest.raises(RuntimeError, match="no K2000 answered"):
        MidiBridge.autodetect(timeout=0.1)
