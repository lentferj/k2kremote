# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 40: capture each DSP algorithm's SIGNAL-FLOW PICTURE.  (EDITS A BUFFER, SAVES NOTHING)

The algorithm's block chain is only half of what the K2000 draws on the ALG page.
`ALLTEXT` returns the block *names* — ``PITCH  LOPASS  LOPASS  LOPASS  x AMP`` —
but the **connecting lines between the blocks live in the graphics layer**, and
those lines are the signal flow: which slots are in series, which are bypassed,
which pair up, where a slot is double or triple width.

Text alone cannot express that. `x AMP` and `+ AMP` hint at it, and the wire
drawing states it.

So this pairs both planes per algorithm: the text chain from `ALLTEXT` (0x15) and
the pixels from `GETGRAPHICS` (0x18), written out as a PBM per algorithm so the
topology can actually be read by a human.

Why it matters right now: a converter needs to know whether DSP slot 3 holds a
filter, and the algorithm does not settle it on its own — the same slot offers a
list of selectable functions, and the same stored code can land on a filter under
one algorithm and a shaper under another. Slot WIDTH and routing are part of what
makes those lists differ, and the picture is where width and routing are visible.

GETGRAPHICS costs ~960 ms, so 31 algorithms is about a minute of wire time.

**Nothing is saved**: the algorithm is set in the edit buffer only, and the probe
exits answering the save prompt with No.

    .venv/bin/python probes/p40_algorithm_pictures.py --out ~/temp/algpics
"""
import sys; sys.path.insert(0, ".")
import argparse
import json
import os
import time

from probes.hw import connect
from probes.p36_filter_fields import (
    SOFT, rows, select_program, soft_index, leave_editor,
)
from probes.p39_algorithm_table import (
    ALGORITHMS, open_alg_page, goto_algorithm_field, set_algorithm, slots_of,
)
from k2000.definitions import Button


def write_pbm(path, pixels):
    """A plain PBM — no dependencies, and any image viewer opens it.

    `get_graphics()` returns a WIDTH-MAJOR array: its shape is (240, 64), not
    (64, 240). Reshaping to (height, width) instead of transposing produced
    screenshots that looked like noise and were nearly committed as documentation.
    So this transposes, and records the source shape alongside.
    """
    width, height = pixels.shape          # width-major, as returned
    with open(path, "wb") as fh:
        fh.write(b"P1\n%d %d\n" % (width, height))
        for y in range(height):
            fh.write(b" ".join(b"1" if pixels[x, y] else b"0"
                               for x in range(width)) + b"\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--program", type=int, default=206)
    ap.add_argument("--out", default="algpics")
    args = ap.parse_args()

    bridge = connect()
    try:
        print(f"connected: {bridge.description}")
        while bridge.client.midi_in.get_message() is not None:
            pass
        if "ProgramMode" not in rows(bridge)[0]:
            print("not in Program Mode; leave the editor first")
            return 1
        os.makedirs(args.out, exist_ok=True)

        select_program(bridge, args.program)
        bridge.press_button(Button.Edit)
        time.sleep(0.9)
        if not open_alg_page(bridge) or not goto_algorithm_field(bridge):
            print("could not reach the Algorithm field")
            leave_editor(bridge)
            return 1

        index = open(os.path.join(args.out, "index.jsonl"), "w")
        try:
            for number in ALGORITHMS:
                shown, chain = set_algorithm(bridge, number)
                blocks, filters = slots_of(chain)
                pixels = bridge.get_graphics()
                name = f"alg{int(shown):02d}.pbm"
                write_pbm(os.path.join(args.out, name), pixels)
                index.write(json.dumps({
                    "algorithm": int(shown), "chain": chain, "blocks": blocks,
                    "filter_slots": filters, "picture": name,
                    "shape": list(pixels.shape),
                    "ink": int(pixels.sum()),
                }) + "\n")
                index.flush()
                print(f"  alg {shown:>3}  {int(pixels.sum()):>5} px  "
                      f"filters at {filters or '-'}   {chain}", flush=True)
        finally:
            index.close()

        if not leave_editor(bridge):
            print("!! did NOT get back to Program Mode -- the edit buffer must "
                  "not be saved; check the panel")
            return 1
        print(f"\nleft the editor without saving; pictures in {args.out}")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
