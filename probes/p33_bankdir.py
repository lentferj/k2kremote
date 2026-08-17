# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 33: what is actually resident, per bank?  (READ-ONLY)

Written to answer "did the macro load what it was supposed to?" without reading
the panel: after installing an edited BOOT.MAC, the question is which banks got
populated, and DIRBANK answers it directly.

DIRBANK (0x0C) asks the K2000 to return one INFO per matching object, then an
ENDOFBANK (0x0D). The vendored client's `_send_and_receive` returns the *first*
matching reply, so a multi-response request needs its own loop — that is all this
does. It sends one request per bank and reads until ENDOFBANK or silence.

Sends nothing but DIRBANK. No writes, no button presses, no editor navigation.

    .venv/bin/python probes/p33_bankdir.py            # banks 2,3,4,5,6,9
    .venv/bin/python probes/p33_bankdir.py 3 9        # just those two

Bank numbers are the K2000's 1-byte bank field (the hundreds digit): 3 is
300-399. Note this is *not* the macro file's encoding, where the same bank is
stored as 300 -- worth keeping straight when comparing a macro against what
actually loaded.
"""
import sys
import time

sys.path.insert(0, ".")

from probes.hw import connect
from k2000.definitions import ObjectType
from k2000.messages import DirBank, EndOfBank, Info, SysexMessage


def list_bank(bridge, bank: int, obj_type=ObjectType.Program, ram_only=True,
              quiet_for=2.0):
    """Every object INFO the K2000 reports for one bank."""
    client = bridge.client
    while client.midi_in.get_message() is not None:
        pass                                  # drain anything stale
    client.midi_out.send_message(DirBank(obj_type, bank, ram_only).encode())

    found, last_seen, done = [], time.monotonic(), False
    while not done and time.monotonic() - last_seen < quiet_for:
        message = client.midi_in.get_message()
        if message is None:
            time.sleep(0.005)
            continue
        data, _ = message
        if not SysexMessage.has_valid_k2_headers(data):
            continue
        try:
            decoded = SysexMessage.decode(data)
        except Exception:
            continue
        last_seen = time.monotonic()
        if isinstance(decoded, Info):
            found.append(decoded)
        elif isinstance(decoded, EndOfBank):
            done = True
    return found, done


def main():
    banks = [int(a) for a in sys.argv[1:]] or [2, 3, 4, 5, 6, 9]
    bridge = connect()
    try:
        print(f"connected: {bridge.description}\n")
        for bank in banks:
            objects, clean = list_bank(bridge, bank)
            label = f"bank {bank}00-{bank}99"
            end = "" if clean else "   (no ENDOFBANK — timed out)"
            print(f"{label}: {len(objects)} program(s){end}")
            for info in objects:
                ram = "RAM" if info.in_ram else "ROM"
                print(f"    {info.idno:>4}  {info.name:<18} {info.size:>7} B  {ram}")
            if not objects:
                print("    (empty)")
            print()
            time.sleep(0.5)               # stay well clear of the SysEx floor
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
