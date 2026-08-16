# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Wraps (as a runtime dependency, not copied) the psobot/k2000 SysEx library:
#   Copyright (C) 2022-2023  Peter Sobot — MIT — https://github.com/psobot/k2000
# The throttled-output, MultiIn and split send/receive connection logic is
# ported from mpc2emu's tests/re_banks/krz_sysex_live.py:
#   Copyright (C) 2025-2026  mpc2emu contributors — GPL-2.0-or-later
# RE'd MIDI quirks (SysEx flood floor, split rig, device id 0 — broadcast 127
# not honoured) are documented in mpc2emu/docs/k2000r_midi_comms.md and verified
# on Jan's K2000R (2026-06-19; see k2kremote probes/ + TODO.md).
#
# k2kremote is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# k2kremote is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Portable MIDI transport for the Kurzweil K2000 / K2000R.

This wraps ``psobot/k2000``'s :class:`K2000Client` (the full SysEx protocol —
we never reimplement it) behind two connection strategies:

* :meth:`MidiBridge.standard` — one user-selected **bidirectional** port
  (the normal case on Linux / macOS / Windows).
* :meth:`MidiBridge.autodetect` — probe every port for a K2000 that answers
  SysEx, including interfaces (like some USB hubs) whose **send** and **receive**
  appear as different/dynamically-reassigned sub-ports, which are listened to on
  *all* of them merged via :class:`MultiIn`.

Two hardware facts shape everything (RE'd in the sibling mpc2emu project):

* The K2000's old CPU **crashes / garbles the LCD under a MIDI flood**, with a
  hard ~120 ms floor between SysEx messages. So every byte leaves through
  :class:`ThrottledOut`, which never lets two messages go out closer than
  ``gap`` seconds.
* A round-trip over a slow interface can take a while, so real calls use
  **1.5-2 s** timeouts (the library's 0.1 s ``is_connected`` default is too short).

SysEx is independent of MIDI channel; it is addressed by **SysX Device ID**.
We default to **0** for outgoing requests — the K2000R's factory default and
the value verified to work on the hardware (broadcast 127 is *not* honoured by
the tested unit, despite the MIDI spec). Replies are accepted from any device
id via a tolerance shim, so a device on a non-zero id still mirrors; set
``device_id`` to match if it doesn't answer 0.
"""

from __future__ import annotations

import sys
import time
from typing import Callable, Iterable, List, Optional, Tuple

import rtmidi  # noqa: E402

from k2000.client import K2000Client  # noqa: E402
from k2000.definitions import Button, ButtonEventType, ObjectType  # noqa: E402
from k2000.messages import ButtonEvent, Change, Del, DelBank, Panel  # noqa: E402

# --- defaults (RE'd values; see module docstring) ---------------------------
# The RE'd hard floor is ~120 ms. We sit just above it.
#
# This gap is the dominant cost of feeling remote rather than immediate, because
# it is charged on exactly the messages a user is waiting on: the gap is measured
# from the last *send*, so a request whose reply took a while (GETGRAPHICS, ~0.8 s
# of wire) has already paid it, while a PANEL button press — which the device
# answers with nothing at all — pays it in full. At the old 500 ms, a keypress
# followed by the settle read spent ~1 s idling on the throttle alone, and it was
# charged again between ALLTEXT and GETGRAPHICS.
#
# 150 ms keeps a 30 ms margin over the RE'd floor and cuts that idling by 70%.
# Anything below SYSEX_FLOOR risks the LCD garbling the K2000's CPU is known to
# suffer under a flood, so `--sysex-interval` is clamped there. Unattended
# overnight hardware runs that want the old belt-and-braces spacing can still
# pass `-i 500`.
#
# Measured on the K2000R (2026-08-15): **reads space themselves**. Back-to-back
# ALLTEXT with the throttle switched off still came 131.6 ms apart, because that
# is how long the reply takes — already past the 120 ms floor. So the gap does
# nothing for screen reads and everything for PANEL button presses, which the
# device answers with nothing at all. Verified clean at 150 ms: 40 reads, 8 full
# frames and 16 presses each left the panel byte-identical to a reference
# capture. The gap has NOT been swept below the floor; that needs a human
# watching the LCD, since a garbled panel appears in no reply.
SYSEX_FLOOR = 0.12         # RE'd hard floor; never send faster than this
# 500 ms, restored 2026-08-16 after 150 ms locked the unit up in ordinary use.
# The margin the sweep suggested was an illusion: it stalled the K2000 at 100 ms
# with *presses alone*, and real navigation layers a heartbeat, a settle read and
# a 963 ms GETGRAPHICS on top of those presses. 1.5x over a pure-press failure
# point is not 1.5x over the real traffic. Lower it with `-i` if you want to
# experiment, but do it with the panel in view.
SEND_GAP = 0.5             # min seconds between outgoing SysEx (default)
DEFAULT_TIMEOUT = 2.5      # a slow interface round-trip; allow margin
# SysX Device ID for OUTGOING requests. Hardware finding (2026-06-18 on a real
# K2000R): the unit answers device id 0 (its factory default) but does NOT
# reply to broadcast 127, despite the MIDI spec — so 0 is the working default.
# Replies are accepted from any device id (see _install_device_id_tolerance).
DEFAULT_DEVICE_ID = 0
BROADCAST_DEVICE_ID = 127  # MIDI broadcast; not honoured by the tested K2000R

# Defaults for a split send/receive interface (separate IN and OUT, with
# dynamically reassigned sub-ports listened to merged via MultiIn). Used by
# autodetect as a fallback; overridable in the config file.
SPLIT_SEND_PORT = "k2000r"
SPLIT_RECV_IFACE = "MIDI"

# Header layout of every K2 SysEx packet: F0 07 <dev> 78 ...
_DEVICE_ID_INDEX = 2


def _install_device_id_tolerance() -> None:
    """Make inbound SysEx decode regardless of the reply's device-id byte.

    With broadcast sends, a K2000 replies using *its* configured device ID, not
    ours. The psobot library validates the header byte-for-byte (device id
    included) and would reject those replies. We normalise the device-id byte
    before the library's own validation/decoding runs. Idempotent.
    """
    from k2000 import messages

    if getattr(messages, "_k2kremote_devid_tolerant", False):
        return

    canonical = messages.K2_HEADER[_DEVICE_ID_INDEX]

    def _normalize(data: bytes) -> bytes:
        if len(data) > _DEVICE_ID_INDEX and data[0] == 0xF0:
            buf = bytearray(data)
            buf[_DEVICE_ID_INDEX] = canonical
            return bytes(buf)
        return data

    _orig_decode = messages.SysexMessage.decode
    _orig_valid = messages.SysexMessage.has_valid_k2_headers

    messages.SysexMessage.decode = classmethod(
        lambda cls, data: _orig_decode(_normalize(data))
    )
    messages.SysexMessage.has_valid_k2_headers = classmethod(
        lambda cls, data: _orig_valid(_normalize(data))
    )
    messages._k2kremote_devid_tolerant = True


# --- leak-free rtmidi port helpers ------------------------------------------
# python-rtmidi creates a backend ALSA sequencer *client* in the MidiIn/MidiOut
# constructor; ``close_port()`` does NOT tear that client down, and relying on
# ``del``/GC delays it "for an arbitrary amount of time" (python-rtmidi docs).
# So every transient MidiIn/MidiOut — even one built only to call get_ports() —
# orphans a "RtMidiIn Client" until the process exits. On a host with dozens of
# MIDI ports, a single autodetect scan could exhaust the ALSA sequencer's client
# slots (open /dev/snd/seq → ENOMEM). We call ``delete()`` to free clients now.

def _delete_quiet(port) -> None:
    """Immediately free an rtmidi port's backend client; never raise."""
    try:
        port.delete()
    except Exception:
        pass


def _enum_in() -> List[str]:
    """List input port names without orphaning an ALSA sequencer client."""
    probe = rtmidi.MidiIn()
    try:
        return probe.get_ports()
    finally:
        _delete_quiet(probe)


def _enum_out() -> List[str]:
    """List output port names without orphaning an ALSA sequencer client."""
    probe = rtmidi.MidiOut()
    try:
        return probe.get_ports()
    finally:
        _delete_quiet(probe)


class ThrottledOut:
    """Wrap an ``rtmidi.MidiOut`` so SysEx never floods the K2000's CPU.

    No two messages leave less than ``gap`` seconds apart. If ``device_id`` is
    set, the SysX Device ID byte of every K2 packet (``F0 07 <dev> 78 ...``) is
    rewritten on the way out, so one shim handles broadcast addressing too.
    """

    def __init__(self, port: rtmidi.MidiOut, gap: float = SEND_GAP,
                 device_id: Optional[int] = None):
        self._port = port
        # Clamped, not trusted: the floor is a hardware property, so no caller —
        # config file, CLI flag or API user — gets to send below it.
        self._gap = max(gap, SYSEX_FLOOR)
        self._device_id = device_id
        self._last = 0.0
        # Cumulative seconds spent asleep on the gap. Makes the throttle
        # observable so instrumentation can tell "the device was slow" from
        # "we were waiting on ourselves" — without it, a timed call at a 500 ms
        # gap reads ~631 ms and the device's own 131 ms is invisible inside it.
        self.throttled_seconds = 0.0

    def send_message(self, message) -> None:
        # Only SysEx (F0 …) stresses the K2000's LCD CPU and needs the gap;
        # ordinary MIDI (notes, CC, e.g. an all-notes-off panic) passes straight
        # through so it stays real-time.
        is_sysex = len(message) > 0 and message[0] == 0xF0
        if not is_sysex:
            self._port.send_message(message)
            return

        if self._device_id is not None and len(message) > _DEVICE_ID_INDEX \
                and message[1] == 0x07:
            message = list(message)
            message[_DEVICE_ID_INDEX] = self._device_id

        wait = self._gap - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
            self.throttled_seconds += wait
        self._port.send_message(message)
        self._last = time.time()

    def __getattr__(self, name):
        return getattr(self._port, name)


class MultiIn:
    """An ``rtmidi.MidiIn``-compatible facade polling one or more ports, merged.

    With ``exact=False`` (the config-driven ``split`` rig) every input whose name
    *contains* ``name`` is opened and polled in turn — for multi-port interfaces
    that may reassign which IN sub-port carries a device's replies. With
    ``exact=True`` (used by autodetect, where the cabling to the device is fixed)
    only the single input whose name *equals* ``name`` is opened.
    """

    def __init__(self, name: str, *, exact: bool = False):
        self.ports: List[rtmidi.MidiIn] = []
        for index, port_name in enumerate(_enum_in()):
            matches = (port_name == name) if exact else (name.lower() in port_name.lower())
            if matches:
                port = rtmidi.MidiIn(queue_size_limit=8192)
                port.open_port(index)
                port.ignore_types(sysex=False)
                self.ports.append(port)
        if not self.ports:
            raise RuntimeError(f"no input port matching {name!r}")

    def ignore_types(self, **kwargs) -> None:
        for port in self.ports:
            port.ignore_types(**kwargs)

    def get_message(self):
        for port in self.ports:
            message = port.get_message()
            if message is not None:
                return message
        return None

    def get_ports(self) -> List[str]:
        return _enum_in()

    def close_port(self) -> None:
        for port in self.ports:
            port.close_port()
            _delete_quiet(port)  # free the backend ALSA client, not just the port
        self.ports = []


def _to_ascii7(text: str) -> str:
    """Mask each character to 7 bits (ALLTEXT high bit = reverse video).

    Newlines are preserved; a byte that masks to NUL (a bare 0x80) becomes a
    space so it never truncates or corrupts a rendered row.
    """
    masked = "".join(chr(ord(ch) & 0x7F) for ch in text)
    return masked.replace("\x00", " ")


def _high_bit_rows(text: str) -> List[str]:
    """Per-row reverse-video mask from raw ALLTEXT: "1" where bit 7 is set.

    The K2000 sets the high bit on reverse-video cells — the soft-label row and,
    crucially, the **cursored cell** (the name-edit underscore). Aligned 1:1 with
    the masked text rows from :func:`_to_ascii7` (both split the same string on
    newlines), so a renderer can mark exactly those cells.
    """
    return [
        "".join("1" if (ord(ch) & 0x80) else "0" for ch in line)
        for line in text.split("\n")
    ]


def list_ports() -> Tuple[List[str], List[str]]:
    """Return ``(input_port_names, output_port_names)`` available on this host."""
    return _enum_in(), _enum_out()


def bidirectional_ports() -> List[str]:
    """Names present as both an input and an output (candidate standard ports)."""
    ins, outs = list_ports()
    # Preserve output order; a stable list is friendlier for "pick a number" UIs.
    in_set = set(ins)
    return [name for name in outs if name in in_set]


def _open_out(port_name: str) -> rtmidi.MidiOut:
    out = rtmidi.MidiOut()
    names = out.get_ports()
    if port_name not in names:
        raise RuntimeError(f"no output port named {port_name!r}; have {names}")
    out.open_port(names.index(port_name))
    return out


def _looks_like_k2(name: str) -> bool:
    """Heuristic: does a port name suggest a Kurzweil K2-series device?"""
    n = name.lower()
    return any(k in n for k in ("k2000", "k2vx", "k2500", "k2600", "kurzweil", "krz"))


def _await_screen_reply(listeners, timeout, is_screen_reply):
    """Poll the merged scan listeners for a K2 screen reply within ``timeout``.

    Returns the exact port name of the input it arrived on, or None. Autodetect
    binds the receive side to that one sub-port (the K2's cabling is fixed), not
    the whole interface.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for name, port in listeners:
            message = port.get_message()
            while message is not None:
                if is_screen_reply(message[0]):
                    return name  # the exact answering sub-port
                message = port.get_message()
        time.sleep(0.005)
    return None


def _open_in(port_name: str) -> rtmidi.MidiIn:
    in_port = rtmidi.MidiIn(queue_size_limit=8192)
    names = in_port.get_ports()
    if port_name not in names:
        raise RuntimeError(f"no input port named {port_name!r}; have {names}")
    in_port.open_port(names.index(port_name))
    in_port.ignore_types(sysex=False)
    return in_port


class MidiBridge:
    """A K2000 connection: a wired :class:`K2000Client` plus convenience I/O.

    Build one with :meth:`standard`, :meth:`split_rig`, or :meth:`from_config`.
    All outbound traffic is throttled; all calls take a generous default
    timeout. Button helpers map onto the library's ``Panel``/``ButtonEvent``.
    """

    def __init__(self, client: K2000Client, description: str,
                 timeout: float = DEFAULT_TIMEOUT):
        self.client = client
        self.description = description
        self.timeout = timeout

    # -- constructors --------------------------------------------------------
    @classmethod
    def standard(cls, port_name: str, *, gap: float = SEND_GAP,
                 device_id: Optional[int] = DEFAULT_DEVICE_ID,
                 timeout: float = DEFAULT_TIMEOUT) -> "MidiBridge":
        """Connect over a single bidirectional port (the portable default)."""
        _install_device_id_tolerance()
        out = ThrottledOut(_open_out(port_name), gap=gap, device_id=device_id)
        in_port = _open_in(port_name)

        client = K2000Client.__new__(K2000Client)  # bypass bidirectional auto-detect
        client.midi_out = out
        client.midi_in = in_port
        client.port_name = port_name
        return cls(client, f"standard:{port_name}", timeout=timeout)

    @classmethod
    def split_rig(cls, *, send_port: str = SPLIT_SEND_PORT,
                  recv_iface: str = SPLIT_RECV_IFACE, gap: float = SEND_GAP,
                  device_id: Optional[int] = DEFAULT_DEVICE_ID,
                  timeout: float = DEFAULT_TIMEOUT) -> "MidiBridge":
        """Connect over a split send/receive interface (separate IN and OUT).

        Advanced/API use: send on the port matching ``send_port`` and receive on
        all sub-ports of the ``recv_iface`` interface, merged. Configure it in the
        config file with ``rig = "split"``."""
        _install_device_id_tolerance()
        out_names = _enum_out()
        match = next((n for n in out_names if send_port.lower() in n.lower()), None)
        if match is None:
            raise RuntimeError(f"no output port matching {send_port!r}; have {out_names}")
        out = ThrottledOut(_open_out(match), gap=gap, device_id=device_id)

        client = K2000Client.__new__(K2000Client)
        client.midi_out = out
        client.midi_in = MultiIn(recv_iface)
        client.port_name = f"{send_port} -> {recv_iface}"
        return cls(client, f"split:{send_port}->{recv_iface}", timeout=timeout)

    @classmethod
    def from_config(cls, config: "BridgeConfig", *, gap: float = SEND_GAP) -> "MidiBridge":
        """Build a bridge from a loaded :class:`BridgeConfig` (SysEx gap in seconds)."""
        if config.rig == "auto":
            return cls.autodetect(gap=gap, device_id=config.device_id)
        if config.rig == "split":
            return cls.split_rig(send_port=config.send_port,
                                 recv_iface=config.recv_iface,
                                 gap=gap, device_id=config.device_id)
        if not config.port:
            raise RuntimeError("config has no 'port' set for standard rig mode")
        return cls.standard(config.port, gap=gap, device_id=config.device_id)

    @classmethod
    def autodetect(cls, *, gap: float = SEND_GAP, device_id: int = DEFAULT_DEVICE_ID,
                   scan_timeout: float = 1.0, timeout: float = DEFAULT_TIMEOUT,
                   on_try: Optional[Callable[[str], None]] = None) -> "MidiBridge":
        """Find a K2000 on any accessible MIDI ports — fully general.

        Sends an ALLTEXT request out **each output port** while listening on
        **every input port**, and keeps the first output whose request comes
        back as a real K2 screen reply (type 0x19 — distinct from our 0x15
        request, so a MIDI-Thru loopback isn't mistaken for the device). That
        covers single bidirectional ports, split send/receive rigs, and
        multi-port interfaces with no hardcoded names. The receive side is bound
        to the *interface* the reply arrived on (so interfaces with dynamically-
        reassigning sub-ports still work). ``on_try`` reports each port.

        ``scan_timeout`` is how long to wait for a *probe* reply per port: short,
        because it is paid once per silent candidate. ``timeout`` is what the
        returned bridge uses for real calls. Confusing the two is not cosmetic —
        the scan value used to be handed straight to the bridge, so ``--rig auto``
        ran with a **1.0 s** operational timeout against a GETGRAPHICS that takes
        962.7 ms. Twenty-six milliseconds of headroom. Any jitter turned a healthy
        read into a TimeoutError, which the refresh worker reads as the device
        having gone away: it marks the mirror disconnected and backs off, doubling
        up to 20 s. A frozen, "constantly hanging" mirror, manufactured entirely
        by us, with the K2000 answering normally throughout.
        """
        from k2000.messages import AllText, ScreenReply, K2_HEADER

        _install_device_id_tolerance()
        type_index = len(K2_HEADER)
        request = bytearray(AllText().encode())  # F0 07 00 78 15 F7
        if device_id is not None:
            request[_DEVICE_ID_INDEX] = device_id
        request = bytes(request)

        out_names = _enum_out()
        in_names = _enum_in()
        # Try K2000-ish named ports first so a labelled rig is found fast.
        order = sorted(range(len(out_names)),
                       key=lambda i: 0 if _looks_like_k2(out_names[i]) else 1)

        # Open every input once as a merged scan listener.
        listeners: List[Tuple[str, "rtmidi.MidiIn"]] = []
        for index, name in enumerate(in_names):
            port = None
            try:
                port = rtmidi.MidiIn(queue_size_limit=8192)
                port.open_port(index)
                port.ignore_types(sysex=False)
                listeners.append((name, port))
            except Exception:
                if port is not None:
                    _delete_quiet(port)  # don't orphan a half-opened listener

        def is_screen_reply(data) -> bool:
            from k2000.messages import SysexMessage
            return (SysexMessage.has_valid_k2_headers(data)
                    and len(data) > type_index
                    and data[type_index] == ScreenReply._msg_type_int)

        try:
            for i in order:
                out_name = out_names[i]
                if on_try is not None:
                    on_try(out_name)
                out = None
                try:
                    out = rtmidi.MidiOut()
                    out.open_port(i)
                except Exception:
                    if out is not None:
                        _delete_quiet(out)  # free the client even on open failure
                    continue
                try:
                    for _, port in listeners:  # flush stale input
                        while port.get_message() is not None:
                            pass
                    out.send_message(request)
                    reply_port = _await_screen_reply(listeners, scan_timeout,
                                                     is_screen_reply)
                finally:
                    out.close_port()
                    _delete_quiet(out)  # don't orphan a probe client per output port
                if reply_port is not None:
                    return cls._connect_split(out_name, reply_port,
                                              gap=gap, device_id=device_id, timeout=timeout)
        finally:
            for _, port in listeners:
                port.close_port()
                _delete_quiet(port)  # free the backend ALSA client, not just the port

        raise RuntimeError(
            f"auto-probe: no K2000 answered on any of {len(out_names)} output ports "
            f"(listened on {len(listeners)})."
        )

    @classmethod
    def _connect_split(cls, send_name: str, recv_port: str, *, gap: float,
                       device_id: Optional[int], timeout: float) -> "MidiBridge":
        """Build a bridge: send via the exact ``send_name`` port, receive on the
        single ``recv_port`` the device answered on (its cabling is fixed)."""
        _install_device_id_tolerance()
        out = ThrottledOut(_open_out(send_name), gap=gap, device_id=device_id)
        client = K2000Client.__new__(K2000Client)
        client.midi_out = out
        client.midi_in = MultiIn(recv_port, exact=True)
        client.port_name = f"{send_name} -> {recv_port}"
        return cls(client, f"auto:{send_name} -> {recv_port}", timeout=timeout)

    # -- screen --------------------------------------------------------------
    def get_graphics(self, timeout: Optional[float] = None):
        """Fetch the LCD pixel layer as a numpy array (feed to ``braille``)."""
        return self.client.get_graphics(timeout or self.timeout)

    def get_screen_text(self, timeout: Optional[float] = None) -> str:
        """Fetch the LCD text layer (handy for soft-key labels).

        ALLTEXT bytes must be masked to 7 bits: the K2000 sets the high bit on
        reverse-video characters (the soft-label row and the cursored cell), and
        psobot's decoder does not strip it — without masking those cells render
        as garbage (e.g. ``chr(0xC4)`` instead of ``'D'``). Per the protocol
        notes (mpc2emu/docs/k2000r_midi_comms.md §6: "mask each byte &0x7F").
        """
        return _to_ascii7(self.client.get_screen_text(timeout or self.timeout))

    def get_screen_text_attrs(self, timeout: Optional[float] = None) -> Tuple[str, List[str]]:
        """Fetch ALLTEXT as ``(masked_text, reverse_mask)``.

        Same masked text as :meth:`get_screen_text`, plus the per-row high-bit
        mask (:func:`_high_bit_rows`) so callers can render the reverse-video
        cursor — notably the name-edit underscore, which the GETGRAPHICS plane
        can lag or omit on a busy page.
        """
        raw = self.client.get_screen_text(timeout or self.timeout)
        return _to_ascii7(raw), _high_bit_rows(raw)

    def poll_panel(self) -> bool:
        """Drain unsolicited inbound MIDI; return True if a PANEL message was seen.

        The K2000 emits PANEL (0x14) for its own front-panel presses when the
        XMIT buttons parameter is On — spelled **``Bttns``** on the MIDI TRANSMIT
        page, which is easy to miss, and Off by factory default. So an inbound
        PANEL means the hardware was physically touched and the mirror should
        refresh. This is a local read of the RX buffer — it sends nothing — and
        should only be called when no solicited reply is in flight (the refresh
        worker guarantees this by serializing all MIDI on one thread).

        Verified on hardware 2026-08-15: physical presses do arrive and decode,
        and our own injected presses are **not** echoed back even with ``Bttns``
        On, so there is no refresh feedback loop.

        We deliberately look at the message *type* only. On an inbound PANEL the
        field that doesn't apply is **filler, not data**: button Down/Up events
        carry ``alpha_wheel_clicks == +63`` (the device sends ``0x7F``, and the
        decoder subtracts 64), and AlphaWheel events carry a meaningless
        ``button`` (``ChanBankDec``). Anything that starts reading those fields —
        e.g. mirroring a physical press into the software name cursor — must
        ignore the irrelevant one, or it will apply a phantom 63-click turn on
        every button press. See RESOLUTION_NOTES §3.
        """
        from k2000.messages import K2_HEADER, Panel, SysexMessage

        type_index = len(K2_HEADER)  # F0 07 dev 78 <type> ...
        seen = False
        while True:
            message = self.client.midi_in.get_message()
            if message is None:
                break
            data = message[0]
            if (SysexMessage.has_valid_k2_headers(data)
                    and len(data) > type_index
                    and data[type_index] == Panel._msg_type_int):
                seen = True
        return seen

    def ports_present(self) -> bool:
        """Are the MIDI ports we opened still enumerated by the system?

        The one signal that separates "the device is busy" from "the device is
        gone", and the only one that works when the device has stopped talking
        to us — which is exactly when we need to tell those apart.

        Verified live 2026-08-16: a K2000 disk load silences the unit completely
        for **minutes**. It answers nothing, so no screen text reaches us and no
        elapsed-time rule can distinguish it from an unplug. The ports, though,
        stay enumerated throughout.

        Note what this can and cannot see. Our ports belong to the MIDI
        *interface*, so this catches the interface being unplugged; a K2000
        switched off behind a still-present interface looks the same as one that
        is merely busy. That is the right way round: the cost of calling a busy
        device "gone" is a mirror that cries wolf during every disk operation,
        while the cost of calling a powered-off device "not answering" is a
        slightly coy status line. This is a local enumeration — it sends nothing.
        """
        try:
            names = getattr(self.client.midi_in, "get_ports", _enum_in)()
            outs = _enum_out()
        except Exception:
            return True   # can't tell: assume present rather than declare a loss
        wanted = [p for p in (self.client.port_name or "").split(" -> ") if p]
        if not wanted:
            return True
        haystack = set(names) | set(outs)
        return all(any(w == n or w in n for n in haystack) for w in wanted)

    def is_connected(self, timeout: float = DEFAULT_TIMEOUT) -> bool:
        """True if the K2000 answers a screen request within ``timeout``."""
        try:
            self.client.get_screen_text(timeout)
            return True
        except TimeoutError:
            return False

    # -- input ---------------------------------------------------------------
    def press_button(self, button: Button) -> None:
        """Send a single down+up for ``button``."""
        self.client.press_button(button)

    def press_buttons(self, buttons: Iterable[Button]) -> None:
        """Send a sequence of presses (repeats collapse to down*n + one up)."""
        self.client.press_buttons(list(buttons))

    def panic(self) -> None:
        """All-Sound-Off (CC 120) + All-Notes-Off (CC 123) on all 16 channels.

        Context-independent (unlike the K2000's soft-button combos, which only
        mean "panic" on editor pages). These are ordinary MIDI CCs, so they are
        not throttled and fire immediately.
        """
        out = self.client.midi_out
        for channel in range(16):
            out.send_message([0xB0 | channel, 120, 0])
            out.send_message([0xB0 | channel, 123, 0])

    def alpha_wheel(self, clicks: int) -> None:
        """Turn the alpha wheel by ``clicks`` (negative = left).

        A single PANEL alpha-wheel event encodes at most ±63 clicks, so larger
        turns are split into several throttled messages (the throttle spaces
        them like successive physical turns). Small turns (the usual ±1 / ±5)
        stay a single message.
        """
        from k2kremote.text_entry import chunk_wheel

        for chunk in chunk_wheel(clicks):
            self.client.midi_out.send_message(
                Panel([ButtonEvent(ButtonEventType.AlphaWheel, Button.Number0, chunk)]).encode()
            )

    # -- object rename (whole-name SysEx, no multi-tap) ----------------------
    def rename(self, obj_type: ObjectType, idno: int, name: str,
               timeout: Optional[float] = None) -> str:
        """Rename an existing object in one CHANGE (0x08) — the whole name at once.

        Sets the object's name directly, **leaving its id untouched** (``newid=0``,
        which the protocol defines as "id not changed") so CHANGE can never
        relocate the object or overwrite whatever sits at another id — the only
        safe form for a remote. The name is sent as raw ASCII (the message
        null-terminates it), so any printable ASCII goes through without the
        alpha-wheel charset detour that :func:`~k2kremote.text_entry.type_name`
        needs. Returns the device-confirmed name from the INFO reply.

        This bypasses the name dialog entirely; it targets the stored object by
        ``(obj_type, idno)``. The K2000 rejects writes to an object that is open
        for editing, so the object must not be locked. **Unverified on hardware:**
        whether CHANGE is accepted while a rename dialog is on screen, and how
        the firmware truncates names longer than the 16-char display field.
        """
        if not name.isascii():
            bad = next(ch for ch in name if not ch.isascii())
            raise ValueError(f"name contains non-ASCII character {bad!r}")
        info = self.client._send_and_receive(
            Change(obj_type, idno, 0, name), timeout or self.timeout)
        return info.name

    def object_name(self, obj_type: ObjectType, idno: int) -> str:
        """Current name of an object (DIR → INFO) — the rename tool's preview."""
        return self.client.dir(obj_type, idno).name

    # DELBANK's "all object types" selector: the protocol's type field = 0. No
    # ObjectType enum member has value 0, so a tiny stand-in supplies `.value`
    # (the message only reads `type.value` when encoding).
    _ALL_OBJECT_TYPES = type("_AllObjectTypes", (), {"value": 0})()

    # -- Master object utilities (single SysEx, bypassing the LCD menu) -------
    # These rewrite the object database directly, so the K2000 menu flow that can
    # lock the unit up is bypassed entirely. They are destructive; callers must
    # pause the mirror around them (the worker is single-threaded, so no heartbeat
    # can interleave the blocking send, and the app stays paused afterwards). Each
    # returns the device's INFO reply describing the affected object.
    def delete_object(self, obj_type: ObjectType, idno: int,
                      timeout: Optional[float] = None):
        """Delete one object — DEL (0x07). Returns the INFO reply (the deleted
        object, or the ROM object it uncovers; a ROM object cannot be deleted)."""
        return self.client._send_and_receive(Del(obj_type, idno),
                                             timeout or self.timeout)

    def move_object(self, obj_type: ObjectType, idno: int, newid: int,
                    timeout: Optional[float] = None):
        """Relocate one object to ``newid`` — CHANGE (0x08) with an empty name (the
        name is left unchanged). **Destructive at the destination:** the protocol
        deletes whatever object already sits at ``newid``. Returns the INFO reply."""
        return self.client._send_and_receive(Change(obj_type, idno, newid, ""),
                                             timeout or self.timeout)

    def delete_bank(self, obj_type: Optional[ObjectType], bank: int,
                    timeout: Optional[float] = None):
        """Delete a whole 100-id bank — DELBANK (0x0E). ``obj_type=None`` sets the
        DELBANK ``type`` field to 0 = **all object types** in the bank (what a
        front-panel range delete does); ``bank=127`` with ``obj_type=None`` wipes
        **every** RAM object. Pass a type to wipe only that type's bank.

        The K2000 sends no INFO for DELBANK: a one-type bank delete is silent, and
        the all-types / "everything" nuke (type 0) replies only with an ENDOFBANK
        (itself carrying type 0 = all types). Neither is an INFO, so the short grace
        wait below always times out — we treat that as **success** and return
        ``None``. (The ENDOFBANK reply must still *decode*; ``_decode_object_type``
        in ``k2000/messages.py`` maps its type-0 field to ``None`` so it does not
        raise — verified live 2026-06-25.)
        """
        msg = DelBank(obj_type if obj_type is not None else self._ALL_OBJECT_TYPES,
                      bank)
        try:
            return self.client._send_and_receive(msg, timeout or 0.5)
        except TimeoutError:
            return None   # no ACK is expected; the wipe still happened

    # str -> the matching Number button, for re-entering a program id.
    _DIGIT_BUTTONS = {str(d): getattr(Button, f"Number{d}") for d in range(10)}

    def reselect_program(self, idno: int) -> None:
        """Re-enter a program number (its digits + ``Enter``) to force a repaint.

        A SysEx CHANGE renames the stored object, but the K2000 keeps showing the
        old name on its LCD until the program is re-selected (verified 2026-06-21,
        ``probes/p22_change_rename.py``). Re-typing the same id reselects it and
        makes the panel — and so our mirror — re-read the new name.
        """
        for ch in str(int(idno)):
            self.press_button(self._DIGIT_BUTTONS[ch])
        self.press_button(Button.Enter)

    # -- lifecycle -----------------------------------------------------------
    def close(self) -> None:
        for port in (self.client.midi_out, self.client.midi_in):
            try:
                port.close_port()
            except Exception:
                pass
            # Free the backend ALSA client, not just the port. MultiIn.close_port
            # already deletes its sub-ports; ThrottledOut wraps one rtmidi.MidiOut.
            raw = getattr(port, "_port", None)
            if raw is not None:
                _delete_quiet(raw)

    def __repr__(self) -> str:
        return f"<MidiBridge {self.description!r}>"


# --- config -----------------------------------------------------------------
class BridgeConfig:
    """The saved port selection and rig mode, persisted to ``config.toml``.

    Hand-written TOML I/O: ``tomllib`` (3.11+) reads but cannot write, and we
    only have a handful of flat keys.
    """

    def __init__(self, *, rig: str = "standard", port: Optional[str] = None,
                 send_port: str = SPLIT_SEND_PORT, recv_iface: str = SPLIT_RECV_IFACE,
                 device_id: int = DEFAULT_DEVICE_ID):
        self.rig = rig
        self.port = port
        self.send_port = send_port
        self.recv_iface = recv_iface
        self.device_id = device_id

    @classmethod
    def load(cls, path: str) -> "BridgeConfig":
        import tomllib

        with open(path, "rb") as handle:
            data = tomllib.load(handle)
        return cls(
            rig=data.get("rig", "standard"),
            port=data.get("port"),
            send_port=data.get("send_port", SPLIT_SEND_PORT),
            recv_iface=data.get("recv_iface", SPLIT_RECV_IFACE),
            device_id=int(data.get("device_id", DEFAULT_DEVICE_ID)),
        )

    def save(self, path: str) -> None:
        lines = [
            "# k2kremote MIDI bridge configuration",
            f'rig = "{self.rig}"',
        ]
        if self.port is not None:
            lines.append(f'port = "{self.port}"')
        lines.append(f'send_port = "{self.send_port}"')
        lines.append(f'recv_iface = "{self.recv_iface}"')
        lines.append(f"device_id = {self.device_id}")
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")


def _main(argv: List[str]) -> None:
    """Standalone smoke test: list ports, or read the live screen as braille."""
    if not argv or argv[0] == "ports":
        ins, outs = list_ports()
        print("MIDI inputs:")
        for name in ins:
            print(f"  {name}")
        print("MIDI outputs:")
        for name in outs:
            print(f"  {name}")
        print("\nBidirectional (standard-rig candidates):")
        for name in bidirectional_ports():
            print(f"  {name}")
        return

    if argv[0] == "probe":
        try:
            bridge = MidiBridge.autodetect(on_try=lambda d: print(f"  trying {d} …"))
        except RuntimeError as exc:
            sys.exit(str(exc))
        print(f"\nfound the K2000 on: {bridge.description}")
        print("first screen line:", bridge.get_screen_text().split("\n")[0].rstrip())
        bridge.close()
        return

    if argv[0] == "screen":
        from k2kremote import braille

        if len(argv) > 1:
            bridge = MidiBridge.standard(argv[1])
        else:
            candidates = bidirectional_ports()
            if not candidates:
                sys.exit("no bidirectional MIDI port found; pass a port name")
            bridge = MidiBridge.standard(candidates[0])
        try:
            print(braille.render(bridge.get_graphics()))
        finally:
            bridge.close()
        return

    print(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
