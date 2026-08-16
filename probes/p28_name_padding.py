# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 28: does INFO return a stored name padded to the field width?  (READ-ONLY)

The `Ctrl+O` rename tool compares the name the user asked for against the name
the INFO reply says the device stored, and stops if they differ (RESOLUTION_NOTES
§20). That comparison strips trailing blanks, on the *assumption* that the
firmware might pad a short name out to the 16-column display field. The
assumption was never tested, and it matters in both directions:

* if the device does not pad, the strip is harmless and the check is exact;
* if it pads with **blanks**, the strip is what stops the tool reporting a
  mismatch on literally every rename of a short name;
* if it pads with anything else — nulls, or a fill character — the strip does
  *not* help and the tool will false-alarm every time.

Only the third case is a bug, and one read settles which world we are in.

**Read-only and safe to run any time.** It sends DIR (one message per program,
throttled) and reads the INFO reply. It writes nothing, opens no editor, and
touches no object — unlike p22, which renames. Uses programs found with short
names in the correlation capture; pass ids to override.

    .venv/bin/python probes/p28_name_padding.py
    .venv/bin/python probes/p28_name_padding.py 350 305 200
"""
import sys; sys.path.insert(0, ".")
import time

from probes.hw import connect
from k2000.definitions import ObjectType

# Short names seen on the panel during the 2026-08-17 capture, plus one full
# 16-char name as the control: if padding exists, the short ones grow to match
# the long one's length and the long one is unchanged.
DEFAULT_IDS = [350, 305, 323, 344, 200]

NAME_FIELD = 16          # the K2000's display field width


def stamp(title=""):
    print(f"\n[{time.strftime('%H:%M:%S')}] {title}".rstrip(), flush=True)


def main():
    ids = [int(a) for a in sys.argv[1:]] or DEFAULT_IDS
    bridge = connect()
    try:
        stamp(f"connected: {bridge.description}")
        print(f"reading {len(ids)} program names via DIR -> INFO (no writes)\n")
        print(f"{'id':>5}  {'len':>3}  {'padded?':<9}  name as returned")
        print("-" * 62)
        padded = []
        for idno in ids:
            info = bridge.client.dir(ObjectType.Program, idno)
            name = info.name
            # Trailing blanks OR nulls both count as padding; the repr shows which.
            stripped = name.rstrip(" \x00")
            is_padded = name != stripped
            if is_padded:
                padded.append(idno)
            print(f"{idno:>5}  {len(name):>3}  {'YES' if is_padded else 'no':<9}  "
                  f"{name!r}")

        stamp("verdict")
        if not padded:
            print("No padding: INFO returns the name exactly as stored.")
            print("The rename tool's rstrip is a no-op — harmless, and the")
            print("comparison is exact. TODO item closed.")
        else:
            fills = {repr(bridge.client.dir(ObjectType.Program, i).name[-1])
                     for i in padded}
            print(f"Padded on {len(padded)} of {len(ids)}: {padded}")
            print(f"Fill character(s): {sorted(fills)}")
            if fills <= {repr(' ')}:
                print("Blank-padded, which is exactly what the rstrip handles.")
                print("Without it the tool would false-alarm on every short name.")
            else:
                print("!! NOT blank-padded. The rename tool's rstrip does NOT")
                print("!! cover this and WILL report a mismatch on every rename.")
                print("!! Widen the strip in app.RenameObjectScreen._apply.")
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
