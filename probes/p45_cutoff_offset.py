# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 45: find the RAM offset holding the filter cutoff byte.  READ-ONLY.

`filter_cutoff_byte_to_hz()` in `k2kremote/k2kfields.py` carries a law verified
to 0.08% against the device's own `Coarse:` display — and a docstring saying,
in as many words, that **nobody ever mapped which offset in a live Program
object holds that byte**.  CUTCAL set and read it entirely through the panel's
F1 FRQ page.  So the one conversion this project trusts most is the one it
cannot apply to a byte it found itself.

The CUTCAL bank is the instrument that closes it: eleven programs `CUT 000` ..
`CUT 100` that differ in *one parameter*.  DUMP all eleven, diff them, and the
offsets that vary are the candidates.  A byte that varies **monotonically**
across a monotone ladder of cutoffs, and whose values run through the law to a
smooth Hz sequence, is the byte.

No writes, no button presses, no editor — DUMP (0x00) only.  The panel
cross-check is a separate step, deliberately, so that this half cannot mutate
anything it is measuring.

    .venv/bin/python probes/p45_cutoff_offset.py --first 204 --count 11
"""
import sys; sys.path.insert(0, ".")
import argparse
import json
import time

from probes.hw import connect
from k2000.definitions import ObjectType
from k2kremote.k2kfields import filter_cutoff_byte_to_hz

SEND_GAP = 0.14          # CLAUDE.md: all device output throttled >= 120 ms


def dump(bridge, idno, size):
    time.sleep(SEND_GAP)
    return bridge.read_object_bytes(ObjectType.Program, idno, 0, size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=204)
    ap.add_argument("--count", type=int, default=11)
    ap.add_argument("--size", type=int, default=0,
                    help="object size; 0 = take it from DIRBANK")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    bridge = connect()
    try:
        bank = args.first // 100          # the K2000 bank field is the hundreds digit
        infos, complete = bridge.list_bank(ObjectType.Program, bank,
                                           ram_only=True)
        by_id = {i.idno: i for i in infos}
        wanted = list(range(args.first, args.first + args.count))

        print(f"DIRBANK bank {bank} (ids {bank*100}-{bank*100+99}): {len(infos)} objects, complete={complete}")
        missing = [i for i in wanted if i not in by_id]
        if missing:
            print(f"NOT IN RAM: {missing}")
            print("Refusing to diff a set the device does not have.")
            return 2
        for i in wanted:
            print(f"  {i}  {by_id[i].name!r}  size={by_id[i].size}")

        sizes = {by_id[i].size for i in wanted}
        if len(sizes) != 1:
            print(f"sizes differ across the set: {sorted(sizes)} — "
                  "these programs are NOT one-parameter variants.")
            return 2
        size = args.size or sizes.pop()

        objs = {}
        for i in wanted:
            objs[i] = dump(bridge, i, size)
            print(f"dumped {i}: {len(objs[i])} bytes")

        ref = objs[wanted[0]]
        varying = [off for off in range(size)
                   if len({objs[i][off] for i in wanted}) > 1]
        print(f"\n{len(varying)} of {size} offsets vary across the set:")
        for off in varying:
            vals = [objs[i][off] for i in wanted]
            mono = (all(b <= a for a, b in zip(vals, vals[1:]))
                    or all(b >= a for a, b in zip(vals, vals[1:])))
            hz = [round(filter_cutoff_byte_to_hz(v), 1) for v in vals]
            print(f"  offset {off:3d}  {'MONOTONIC' if mono else 'jumbled  '}"
                  f"  {vals}")
            if mono:
                print(f"              law -> {hz} Hz")

        if args.out:
            with open(args.out, "w") as fh:
                json.dump({"first": args.first, "count": args.count,
                           "size": size, "varying": varying,
                           "names": {i: by_id[i].name for i in wanted},
                           "bytes": {i: list(objs[i]) for i in wanted}},
                          fh, indent=1)
            print(f"\nwrote {args.out}")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
