# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 25: what are the real drive and load-mode codes? (NO MIDI — file analysis)

MAC_FORMAT.md §5 decodes the ``drive`` and ``mode`` words as 0-based indices into
the value lists the manual prints for the *Modify Macro Entries* page. Three
offline checks agree on the one real BOOT.MAC we have, but the reading has never
been confirmed. Until it is, every ``.MAC`` this project writes is unverified.

This probe **opens no MIDI port**. The hardware work is front-panel only; this
script is what you run afterwards, on the files that came out of it.

On the K2000:

  1. Disk mode → Macro → **On** (Record).
  2. Load a file with Macro on, pressing *Macro* rather than *OK* so nothing is
     actually loaded — one entry now exists.
  3. Macro → Modify → set **Drive** to the value you are testing → OK.
     Save the table (Disk → Save → Macro → All) as e.g. ``DRV_F.MAC`` for
     Floppy, ``DRV_S0.MAC`` for SCSI 0, … ``DRV_UNS.MAC``, ``DRV_LIB.MAC``.
  4. Same again with **Mode**: ``MODE_A``, ``MODE_M``, ``MODE_F``, ``MODE_O``,
     ``MODE_V`` (Append / Merge / Fill / Overwrite / OvFill).
  5. Copy the .MAC files to the host.

Then, naming each file after the setting you chose:

    .venv/bin/python probes/p31_macro_codes.py \\
        "Floppy=DRV_F.MAC" "SCSI 0=DRV_S0.MAC" "Library=DRV_LIB.MAC" \\
        "Append=MODE_A.MAC" "Overwrite=MODE_O.MAC"

Files may also be passed bare, in which case the label is the file name. Any
directory given is expanded to the ``.MAC`` files inside it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from k2kmaced.macfile import (  # noqa: E402
    DRIVE_LABELS,
    MODE_LABELS,
    MacError,
    PramFile,
)

if len(sys.argv) < 2:
    sys.exit(__doc__)

pairs = []
for arg in sys.argv[1:]:
    label, sep, path = arg.partition("=")
    if not sep:
        label, path = os.path.splitext(os.path.basename(arg))[0], arg
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if name.upper().endswith(".MAC"):
                pairs.append((os.path.splitext(name)[0], os.path.join(path, name)))
    else:
        pairs.append((label, path))

expected_drive = {name.upper(): code for code, name in DRIVE_LABELS.items()}
expected_mode = {name.upper(): code for code, (name, _) in MODE_LABELS.items()}

print(f"{'label':<14} {'drive':>6} {'mode':>6}  {'decoded as':<26} entry")
print("-" * 88)

observed_drive, observed_mode = {}, {}
for label, path in pairs:
    try:
        table = PramFile.parse(open(path, "rb").read()).macro_table()
    except (MacError, OSError) as exc:
        print(f"{label:<14} {'—':>6} {'—':>6}  <{exc}>")
        continue
    if not len(table):
        print(f"{label:<14} {'—':>6} {'—':>6}  <empty macro table>")
        continue
    for entry in table:
        decoded = f"{entry.drive_label} / {entry.mode_label}"
        print(f"{label:<14} {entry.drive:>6} {entry.mode:>6}  {decoded:<26} "
              f"{entry.display().rstrip()}")
    first = table[0]
    observed_drive.setdefault(label.upper(), first.drive)
    observed_mode.setdefault(label.upper(), first.mode)

print("\n=== verdict ===")
checked = 0
for label, code in sorted(observed_drive.items()):
    if label in expected_drive:
        checked += 1
        want = expected_drive[label]
        print(f"drive {label:<12} code {code:<3} "
              f"{'OK' if code == want else f'MISMATCH — MAC_FORMAT.md §5 predicts {want}'}")
for label, code in sorted(observed_mode.items()):
    if label in expected_mode:
        checked += 1
        want = expected_mode[label]
        print(f"mode  {label:<12} code {code:<3} "
              f"{'OK' if code == want else f'MISMATCH — MAC_FORMAT.md §5 predicts {want}'}")
if not checked:
    print("no file was labelled with a drive or mode name, so nothing could be "
          "checked — name them 'Floppy=…', 'SCSI 0=…', 'Overwrite=…' and rerun.")
else:
    print(f"\n{checked} setting(s) checked. Fold the result into "
          f"MAC_FORMAT.md §5 (and drop its hedge if every one is OK).")
