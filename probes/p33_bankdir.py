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

`list_bank()` itself now lives on `MidiBridge` (promoted 2026-08-25 for
`k2kmon tui`'s object browser, same reasoning as `read_object_bytes`/
`patch_object_bytes`) -- kept here as a thin re-export so this probe's own
CLI usage above still works unchanged.
"""
import sys
import time

sys.path.insert(0, ".")

from probes.hw import connect
from k2000.definitions import ObjectType


def list_bank(bridge, bank: int, obj_type=ObjectType.Program, ram_only=True,
              quiet_for=2.0):
    """Every object INFO the K2000 reports for one bank. See
    `MidiBridge.list_bank` -- this is that method, kept importable as a
    plain function here for this probe's own CLI and any script already
    importing it from this module."""
    return bridge.list_bank(obj_type, bank, ram_only=ram_only, quiet_for=quiet_for)


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
