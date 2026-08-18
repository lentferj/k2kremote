# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. Message decoding uses the vendored k2000 library
# (psobot/k2000, MIT, Peter Sobot); the K2000 SysEx layout is documented in the
# sibling mpc2emu project's docs/k2000r_midi_comms.md.
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

"""``k2kmon`` — a SysEx inspector for the K2000, mostly a passive one.

Built after a session in which three separate faults would have been obvious on
the wire and were instead diagnosed the long way round:

* a reply left in the input buffer was served to the *next* request, surfacing as
  ``ScreenReply contains image data and cannot be converted to str`` — a stale
  buffer wearing the costume of a protocol fault;
* presses that reached the device but landed on a different parameter than
  intended, because nothing showed what the instrument thought was selected;
* requests whose answers were assumed rather than read.

So the default mode sends **nothing** and simply narrates the wire. That matters
on this instrument: the RE'd SysEx floor is ~120 ms and sustained traffic at
100 ms stalls it, so a tool that chatters while you are trying to understand a
fault becomes part of the fault. Only ``ask`` transmits, one request at a time.

    k2kmon watch                 # decode everything inbound, timestamped
    k2kmon watch --panel         # only front-panel events
    k2kmon learn                 # press buttons; it names each one
    k2kmon ask alltext           # send one request, show the decoded reply
    k2kmon ask paramname         # what does the K2000 say is selected?
    k2kmon read Program 206      # dump an object -- ~20x faster than the panel
    k2kmon compare Program 206   # read it BOTH ways and diff the encodings
    k2kmon types                 # the message table, for reading before guessing

``read`` is worth knowing about before reaching for the editor: driving the panel
for one filter page costs about ten seconds and yields one page of one layer,
while ``Read`` returns the whole object, every layer, in about half a second.

``compare`` is a decoder self-check. ``form`` selects only the transmission
packing — 4 bits per MIDI byte or 7 — so both forms carry the same object and
**must** decode identically; a difference means a bug in this software. It is a
command because ours did differ for a while, and the difference was mistaken for a
property of the protocol. It reports non-zero agreement separately too, since two
readings of one object share long runs of zeros.

``learn`` exists because mapping panel behaviour by pressing keys and counting is
how this project got a soft-key cycle one short and a cursor two fields off. With
``XMIT Bttns`` on, the panel reports what a human actually pressed, which is a
better authority than a keypress count.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Iterator, List, Optional, Tuple

from k2000 import messages as _messages
from k2000.messages import SysexMessage

__all__ = ["describe", "hexdump", "message_table", "decode", "main"]

#: Byte 2 of the header carries the device id. Ours answers on 0, not the
#: broadcast 127 the manual implies — worth printing, since a wrong id looks
#: exactly like a dead instrument.
DEVICE_ID_INDEX = 2
#: The header is four bytes — f0 07 00 78 — so the message type is byte 4, not 3.
#: Byte 3 is the product id (0x78) and is the same for every message, which is
#: exactly why getting this wrong is not obvious: every line renders, and every
#: line says 0x78.
TYPE_INDEX = 4


def message_table() -> List[Tuple[int, str, str]]:
    """``(type, class name, first docstring line)`` for every decodable message."""
    import inspect as _inspect
    rows = []
    for name, obj in vars(_messages).items():
        if not _inspect.isclass(obj):
            continue
        code = getattr(obj, "_msg_type_int", None)
        if code is None:
            continue
        doc = (_inspect.getdoc(obj) or "").strip().split("\n")[0]
        rows.append((code, name, doc))
    # A type can map to more than one class in the vendored library; keep both
    # rather than silently dropping one, since which name you get back matters.
    return sorted(set(rows))


def hexdump(data: bytes, limit: int = 32) -> str:
    """Hex, truncated with an honest marker rather than a silent cut."""
    body = " ".join(f"{b:02x}" for b in data[:limit])
    return body if len(data) <= limit else f"{body} … (+{len(data) - limit} bytes)"


def decode(data: bytes):
    """The decoded message, or None when it is not K2000 SysEx we understand."""
    if not SysexMessage.has_valid_k2_headers(bytes(data)):
        return None
    try:
        return SysexMessage.decode(bytes(data))
    except Exception:
        return None


def _panel_detail(message) -> str:
    parts = []
    for event in getattr(message, "button_events", []) or []:
        button = getattr(getattr(event, "button", None), "name", "?")
        kind = getattr(getattr(event, "event_type", None), "name", "?")
        clicks = getattr(event, "alpha_wheel_clicks", 0)
        # On an inbound PANEL the irrelevant field is filler, not data: button
        # events carry wheel=+63 and wheel events carry button=ChanBankDec.
        # Printing both unqualified is how that filler gets read as a reading.
        if clicks:
            parts.append(f"wheel {clicks:+d}")
        else:
            parts.append(f"{button} {kind}")
    return ", ".join(parts) or "(no events)"


def _screen_detail(message) -> str:
    """ScreenReply carries either text or a graphics plane; str() raises on the
    latter, which is exactly the exception that masqueraded as a protocol fault."""
    try:
        text = str(message)
    except Exception:
        blob = getattr(message, "data", b"") or b""
        return f"graphics plane, {len(blob)} bytes"
    rows_ = [r.rstrip() for r in text.split("\n")]
    # A ParameterName / ParameterValue reply is a ONE-ROW screen reply, and its
    # single row is the whole answer. Reporting that as "first row" buries the
    # thing you asked for, and reports an empty answer identically to a screen
    # whose top line happens to be blank.
    if len(rows_) == 1:
        return f"text {rows_[0]!r}"
    return f"text, {len(rows_)} rows, first {rows_[0]!r}"


def _info_detail(message) -> str:
    where = "RAM" if getattr(message, "in_ram", False) else "ROM"
    return (f"{getattr(message.type, 'name', message.type)} "
            f"id {message.idno} {message.name!r} {message.size}B {where}")


def describe(data: bytes, direction: str = "") -> str:
    """One line for one message: what it is, and what it says.

    Pure, so the whole rendering layer is testable without a MIDI port — which is
    the only way it gets tested at all, since every test in this project is
    synthetic.
    """
    raw = bytes(data)
    arrow = {"in": "<-", "out": "->"}.get(direction, "  ")
    if not raw:
        return f"{arrow} (empty)"
    if raw[0] != 0xF0:
        return f"{arrow} non-SysEx  {hexdump(raw)}"
    if len(raw) <= TYPE_INDEX:
        return f"{arrow} truncated SysEx, {len(raw)} bytes  {hexdump(raw)}"

    device = raw[DEVICE_ID_INDEX]
    code = raw[TYPE_INDEX]
    message = decode(raw)
    if message is None:
        known = {c for c, _, _ in message_table()}
        note = "undecodable" if code in known else "unknown type"
        return (f"{arrow} dev {device} type 0x{code:02X} {note}, "
                f"{len(raw)} bytes  {hexdump(raw)}")

    name = type(message).__name__
    if name == "Panel":
        detail = _panel_detail(message)
    elif name == "ScreenReply":
        detail = _screen_detail(message)
    elif name == "Info":
        detail = _info_detail(message)
    elif name == "DataNotAcknowledged":
        # The vendored library decodes this to an ErrorCode enum, whose name is
        # more use than any gloss I could write — so print the name when there is
        # one and fall back to the number with an explanation when there is not.
        # Named `reason`, not `code`: `code` is already the message TYPE byte used
        # by the line below, and shadowing it made every DNAK line raise
        # "Unknown format code 'X' for object of type 'str'" — a decode-looking
        # error produced entirely by a variable name.
        reason = getattr(message, "code", None)
        named = getattr(reason, "name", None)
        detail = (f"DNAK {named}" if named else
                  f"DNAK code {reason} (1 = object open for editing)")
    else:
        # Skip privates: `__annotations__` on these message classes includes
        # class-level machinery (`_msg_type_int`, `_response_classes`), so an
        # empty-bodied request like AllText rendered as
        # "_msg_type_int=21, _response_classes=[]" -- implementation detail
        # presented in the position where the payload should be.
        fields = {k: getattr(message, k, None)
                  for k in getattr(message, "__annotations__", {})
                  if not k.startswith("_")}
        detail = ", ".join(f"{k}={v!r}" for k, v in fields.items()) or "(no body)"
    return f"{arrow} dev {device} 0x{code:02X} {name:<20} {detail}"


# --- live modes --------------------------------------------------------------

def _open_bridge(port: Optional[str], rig: str):
    from k2kremote.midi_bridge import MidiBridge
    if rig == "auto":
        return MidiBridge.autodetect()
    return MidiBridge.open(port) if port else MidiBridge.open_first()


def watch(bridge, *, only_panel: bool = False, seconds: Optional[float] = None,
          quiet_after: Optional[float] = None) -> int:
    """Print every inbound message. Sends nothing at all.

    Passive by design: see the module docstring. A monitor that polls would be
    adding traffic to the situation it is meant to explain.
    """
    print("watching (nothing is transmitted); ctrl-c to stop")
    started = last = time.monotonic()
    seen = 0
    try:
        while True:
            now = time.monotonic()
            if seconds is not None and now - started >= seconds:
                break
            if quiet_after is not None and now - last >= quiet_after:
                print(f"[{time.strftime('%H:%M:%S')}] quiet for {quiet_after:.0f}s")
                last = now
            got = bridge.client.midi_in.get_message()
            if got is None:
                time.sleep(0.002)
                continue
            data, _delta = got
            line = describe(data, "in")
            if only_panel and "Panel" not in line:
                continue
            seen += 1
            print(f"[{time.strftime('%H:%M:%S')}] {line}", flush=True)
            last = time.monotonic()
    except KeyboardInterrupt:
        pass
    print(f"\n{seen} message(s)")
    return 0


def learn(bridge, *, seconds: float = 120.0) -> int:
    """Name each front-panel press as it happens.

    Needs ``XMIT Bttns`` = On on the MIDI TRANSMIT page — it is `Bttns`, not
    `Buttons`, and it was Off on this unit, which is why physical-press mirroring
    looked broken for a day.
    """
    print("press panel buttons and turn the wheel; nothing is transmitted")
    print("(if nothing appears: MIDI TRANSMIT page, 'Bttns' must be On)")
    return watch(bridge, only_panel=True, seconds=seconds, quiet_after=15.0)


#: The one-shot requests `ask` can send, by the name you type.
REQUESTS = {
    "alltext": ("AllText", "the 8x40 text plane"),
    "graphics": ("GetGraphics", "the 240x64 pixel plane (~963 ms)"),
    "paramname": ("ParameterName", "which parameter is selected"),
    "paramvalue": ("ParameterValue", "the selected parameter's value"),
}


def ask(bridge, what: str) -> int:
    """Send one request and show the decoded reply, with its round-trip time.

    Drains the input first. Without that, a reply left over from an earlier
    request is handed to this one — the vendored client returns the first inbound
    message matching the expected class, so the mismatch surfaces as a decode
    error rather than as the staleness it is.
    """
    if what not in REQUESTS:
        print(f"unknown request {what!r}; try: {', '.join(sorted(REQUESTS))}")
        return 2
    class_name, _blurb = REQUESTS[what]
    dropped = 0
    while bridge.client.midi_in.get_message() is not None:
        dropped += 1
    if dropped:
        print(f"drained {dropped} stale inbound message(s) before asking")

    request = getattr(_messages, class_name)()
    print(describe(request.encode(), "out"))
    started = time.monotonic()
    bridge.client.midi_out.send_message(request.encode())
    deadline = started + 3.0
    while time.monotonic() < deadline:
        got = bridge.client.midi_in.get_message()
        if got is None:
            time.sleep(0.002)
            continue
        elapsed = (time.monotonic() - started) * 1000
        print(describe(got[0], "in"))
        print(f"   round trip {elapsed:.1f} ms")
        return 0
    print("   no reply within 3 s")
    return 1


def _read_raw(bridge, kind, idno: int, encoding):
    """One `Read`, returning `(reply, milliseconds)`.

    Drains the input first: a reply left over from a previous request gets served
    to this one, and the symptom is a decode error that looks like a protocol
    fault rather than a stale buffer.
    """
    from k2000.messages import Read
    while bridge.client.midi_in.get_message() is not None:
        pass
    started = time.monotonic()
    reply = bridge.client._send_and_receive(Read(kind, idno, encoding), 5.0)
    return reply, (time.monotonic() - started) * 1000


def compare_encodings(bridge, type_name: str, idno: int) -> int:
    """Read one object BOTH ways; they MUST agree, so this is a decoder check.

    `form` selects only how the data field is packed for transmission — 4 bits per
    MIDI byte (nibblized) or 7 (bit-stream), per ch. 30 "Data Formats". Both carry
    the same underlying bytes, so **identical output is the correct result** and any
    difference is a bug in this software, not a fact about the protocol.

    It is worth having as a command because that is not how it looked. A dump was
    taken in `BitStream` without the encoding ever being a decision, its bytes
    would not reconcile with the same objects read from a disk image, and two
    elaborate explanations were argued — a bad decode, or the loader transforming
    objects into a RAM form — before anyone read the spec, which settles it in a
    sentence. The real cause was `decode_n` front-padding a left-aligned bit
    stream (see `k2000.encoding.decode_data_field`).

    Non-zero agreement is reported separately because of how the near-miss was
    read: `Nibblized` and the file agreed on their first sixteen bytes, that was
    called a match, and ten of the sixteen were zeros on both sides.
    """
    from k2000.definitions import EncodingFormat
    out = {}
    for encoding in (EncodingFormat.Nibblized, EncodingFormat.BitStream):
        reply, ms = _read_raw(bridge, _object_type(type_name), idno, encoding)
        data = getattr(reply, "data", b"") or b""
        out[encoding.name] = data
        print(f"{encoding.name:<10} {len(data):>5} bytes  ({ms:.0f} ms)  "
              f"{hexdump(data, 16)}")

    a, b = out["Nibblized"], out["BitStream"]
    if a == b:
        print("\nbyte-identical — correct: `form` changes only the transmission "
              "packing, so both forms must decode to the same bytes")
        return 0
    print("\n!! THE TWO FORMS DISAGREE, WHICH MEANS A DECODER BUG HERE.")
    print("   `form` selects packing only (4 bits vs 7 bits per MIDI byte); both "
          "carry the same object, so this can never be a protocol difference.")

    pairs = list(zip(a, b))
    same = [i for i, (x, y) in enumerate(pairs) if x == y]
    # Both zero at the same index is the weakest possible evidence of agreement,
    # and on these objects it is most of it.
    signal = [i for i in same if a[i]]
    print(f"\ndiffer: {len(pairs) - len(same)} of {len(pairs)} positions"
          f"{'' if len(a) == len(b) else f'  (lengths {len(a)} vs {len(b)})'}")
    print(f"  equal at {len(same)} positions, but only {len(signal)} of those "
          f"are non-zero — agreement on zeros is not agreement")
    high = sum(1 for x in b if x & 0x80)
    print(f"  high-bit bytes: Nibblized {sum(1 for x in a if x & 0x80)}, "
          f"BitStream {high}")
    return 0


def _object_type(type_name: str):
    from k2000.definitions import ObjectType
    try:
        return getattr(ObjectType, type_name)
    except AttributeError:
        raise SystemExit(f"unknown object type {type_name!r}; try one of: "
                         f"{', '.join(t.name for t in ObjectType)}")


def read_object(bridge, type_name: str, idno: int, encoding_name: str) -> int:
    """Dump one object's raw bytes off the device.

    This is the fast path, and it is worth knowing it exists before reaching for
    the editor: reading a program's filter page by driving the panel costs about
    ten seconds and yields one page of one layer, while `Read` returns the whole
    object in about half a second. A hundred programs is fifty seconds against
    fifteen minutes, and the dump carries every layer rather than the first.

    The encoding is named in the CLI and printed on every line because a dump
    that does not record it cannot be checked later — but note that the two forms
    are only different *packings* of the same bytes and must decode identically.
    See `compare`, which asserts exactly that.
    """
    from k2000.definitions import EncodingFormat
    encoding = getattr(EncodingFormat, encoding_name)
    try:
        reply, ms = _read_raw(bridge, _object_type(type_name), idno, encoding)
    except Exception as exc:
        print(f"no object {type_name} {idno}: {type(exc).__name__}: {exc}")
        return 1
    data = getattr(reply, "data", b"") or b""
    print(f"{type_name} {idno}  {getattr(reply, 'name', '')!r}  "
          f"{len(data)} bytes  {encoding.name}  ({ms:.0f} ms)")
    print(hexdump(data, 64))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="k2kmon",
        description="Inspect K2000 SysEx. Passive unless you ask it to send.")
    parser.add_argument("--port", help="exact MIDI port name")
    parser.add_argument("--rig", choices=("standard", "auto"), default="auto")
    sub = parser.add_subparsers(dest="mode", required=True)

    p = sub.add_parser("watch", help="decode everything inbound; sends nothing")
    p.add_argument("--panel", action="store_true", help="front-panel events only")
    p.add_argument("--seconds", type=float, help="stop after this long")

    p = sub.add_parser("learn", help="press panel buttons; it names them")
    p.add_argument("--seconds", type=float, default=120.0,
                   help="stop after this long (default 120)")

    p = sub.add_parser("ask", help="send one request and decode the reply")
    p.add_argument("request", choices=sorted(REQUESTS))

    p = sub.add_parser("read", help="dump one object's raw bytes (the fast path)")
    p.add_argument("type", help="object type, e.g. Program")
    p.add_argument("idno", type=int)
    # Nibblized by default because it is the form whose decoding was verified
    # against the manual's worked example first; both must agree, and `compare`
    # is what proves it on a given build.
    p.add_argument("--encoding", choices=("Nibblized", "BitStream"),
                   default="Nibblized",
                   help="wire format (they differ; the dump header records it)")

    p = sub.add_parser("compare", help="read an object BOTH ways and diff them")
    p.add_argument("type", help="object type, e.g. Program")
    p.add_argument("idno", type=int)

    sub.add_parser("types", help="the message table; read before guessing")

    args = parser.parse_args(argv)

    if args.mode == "types":
        print(f"{'type':>5}  {'class':<22} description")
        for code, name, doc in message_table():
            print(f" 0x{code:02X}  {name:<22} {doc[:52]}")
        return 0

    bridge = _open_bridge(args.port, args.rig)
    try:
        if args.mode == "watch":
            return watch(bridge, only_panel=args.panel, seconds=args.seconds)
        if args.mode == "learn":
            return learn(bridge, seconds=args.seconds)
        if args.mode == "read":
            return read_object(bridge, args.type, args.idno, args.encoding)
        if args.mode == "compare":
            return compare_encodings(bridge, args.type, args.idno)
        return ask(bridge, args.request)
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
