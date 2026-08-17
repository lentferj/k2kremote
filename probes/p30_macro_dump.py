# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 24: does the live Macro Table dump in the same layout as a .MAC? (READ-ONLY)

Settles the first open question of RESOLUTION_NOTES §21 / MAC_FORMAT.md §7: the
K2000's ``DUMP`` returns its **RAM** structure, which for Programs and Keymaps
is known to differ from the disk serialization. If the Macro Table's two layouts
coincide, k2kremote can read the live macro list directly; if they don't, this
prints the diff needed to model the RAM form.

Sends one ``DUMP`` (0x00) of object type 100 / id 35 — a read. No presses, no
writes. Pause the app's mirror first (RESOLUTION_NOTES §9: the heartbeat must
not interleave a blocking send).

Set up the device first:

  1. Disk mode → Macro → **On** (Record), so a Macro Table object exists at all.
     With Macro mode Off there is no object and the DUMP will fail — that
     failure is itself a useful result, so it is reported, not hidden.
  2. Give it a few entries (load a couple of files with Macro on, or load an
     existing .MAC "as a macro" — press *Macro*, not *OK*, so nothing loads).
  3. Save the same table to disk (Disk → Save → Macro → All) and copy that .MAC
     to the host if you want the byte-for-byte comparison.

Usage:
    .venv/bin/python probes/p30_macro_dump.py [reference.MAC] [--save dump.bin]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from k2kmaced.macfile import MacError, MacroTable, PramFile  # noqa: E402
from probes.hw import connect  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
save_to = None
for i, a in enumerate(sys.argv):
    if a == "--save" and i + 1 < len(sys.argv):
        save_to = sys.argv[i + 1]
reference = args[0] if args else None


def hexdump(data, width=16, limit=512):
    for off in range(0, min(len(data), limit), width):
        chunk = data[off:off + width]
        hexed = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  {off:04x}  {hexed:<{width * 3}} {text}")
    if len(data) > limit:
        print(f"  … {len(data) - limit} more bytes")


b = connect()
print(f"connected: {b}\n")

print("=== DUMP type 100 (Table) / id 35 (Macro) ===")
try:
    data = b.read_macro_table()
except Exception as exc:  # noqa: BLE001
    sys.exit(
        f"DUMP failed: {type(exc).__name__}: {exc}\n"
        "If Macro mode is Off there is no Macro Table object to dump — turn it "
        "on (Disk → Macro → On) and retry. Any other failure is a finding: "
        "record it in RESOLUTION_NOTES §21."
    )

print(f"{len(data)} bytes of object data\n")
hexdump(data)

if save_to:
    with open(save_to, "wb") as fh:
        fh.write(data)
    print(f"\nraw dump written to {save_to}")

print("\n=== does the disk layout parse it? ===")
try:
    table = MacroTable.parse(data)
except MacError as exc:
    print(f"NO — {exc}")
    print("So the RAM layout differs from the disk layout. Save the same table "
          "as a .MAC, pass it as the argument here, and diff the two by hand: "
          "the entry count and the ASCII paths should line up even when the "
          "fixed fields do not.")
    table = None
else:
    print(f"YES — {len(table)} entr{'y' if len(table) == 1 else 'ies'}:")
    for i, entry in enumerate(table):
        print(f"  {i:>3}  {entry.display().rstrip()}")
    print("\nCompare these lines against the K2000's own Macro page. If they "
          "match, RAM and disk layouts coincide and MidiBridge.read_macro_table "
          "can feed the editor directly.")

if reference:
    print(f"\n=== against {reference} ===")
    try:
        on_disk = PramFile.parse(open(reference, "rb").read()).macro_object().data
    except (MacError, OSError) as exc:
        print(f"could not read the reference: {exc}")
    else:
        print(f"disk object data: {len(on_disk)} bytes; dumped: {len(data)} bytes")
        if on_disk == data:
            print("IDENTICAL — the RAM object is the file object, byte for byte.")
        else:
            first = next((i for i, (x, y) in enumerate(zip(on_disk, data)) if x != y),
                         min(len(on_disk), len(data)))
            print(f"differ from offset 0x{first:04x}")
            print("  disk:")
            hexdump(on_disk[first:first + 64])
            print("  dump:")
            hexdump(data[first:first + 64])
