# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 39: which DSP block slots does each ALGORITHM hold?  (EDITS A BUFFER, SAVES NOTHING)

The table the sibling mpc2emu needs, and the answer to a question that cost both
projects a shipped bug.

mpc2emu's KRZ reader treats tag `0x52` as a filter slot, gated on the block code
being a known filter value. That gate does not work: byte value **15** means a
filter under algorithm 10 and a *shaper* under algorithms 17 and 18. A value test
cannot separate them, because the same value means different things depending on
the algorithm. Reading it as a filter regardless invents a filter — with a cutoff
derived from a shaper parameter — for every program in the wrong family.

**The algorithm is what decides.** So the fix needs a table: algorithm number ->
what sits in each block slot. That table is a property of the *instrument*, not of
any program, which is why this probe enumerates algorithms rather than programs.
Reading it off 441 programs would be hundreds of editor visits to recover 31 rows.

Method: open any program's editor, go to the ALG page, and TYPE each algorithm
number into the Algorithm field, recording the block chain the K2000 draws for
it. The cursor is confirmed to be on `Algorithm` via SysEx 0x17 before anything
is typed — this project has twice wheeled dozens of clicks into the wrong field
and nearly reported the result.

**Nothing is saved.** Setting the algorithm changes the edit buffer only, and the
probe exits answering "Save ... before exiting?" with **No**. The stored program
is untouched; verify by reading it back afterwards if in doubt.

    .venv/bin/python probes/p39_algorithm_table.py --program 206 --out algs.jsonl
"""
import sys; sys.path.insert(0, ".")
import argparse
import json
import time

from probes.hw import connect
from probes.p36_filter_fields import (
    DIGITS, SOFT, rows, select_program, soft_index, leave_editor, current_field,
)
from k2000.definitions import Button

#: The K2000 ships 31 DSP algorithms (manual 6-3ff). Asking past the end is
#: harmless -- the field clamps -- and the clamp is recorded rather than assumed.
ALGORITHMS = range(1, 32)

#: Block names that are filters. Used ONLY to summarise the chain for humans;
#: the chain text itself is what gets stored, so a name missing from here cannot
#: silently drop a slot.
FILTER_WORDS = ("LOPASS", "HIPASS", "ALPASS", "BANDPASS", "NOTCH", "PARA",
                "LOPAS2", "HIPAS2", "BAND2", "2POLE", "4POLE", "LP", "HP")


def open_alg_page(bridge, hops: int = 8):
    """Open the ALG page, whichever soft-label page it currently sits on."""
    for _ in range(hops):
        soft = rows(bridge)[7]
        i = soft_index(soft, "ALG")
        if i is not None:
            bridge.press_button(SOFT[i])
            time.sleep(0.6)
            return "ALG" in rows(bridge)[0]
        j = soft_index(soft, "more>")
        if j is None:
            return False
        bridge.press_button(SOFT[j])
        time.sleep(0.45)
    return False


def goto_algorithm_field(bridge, limit: int = 8) -> bool:
    """Move the cursor onto `Algorithm`, asking the device after every step.

    The ALG page opens with the cursor on a *block* rather than on the algorithm
    number, and blocks report an EMPTY parameter name over SysEx 0x17 while the
    number reports `'Algorithm'`. So the two are cleanly distinguishable and
    there is no need to count presses -- which is the failure mode this project
    keeps paying for.
    """
    for _ in range(limit):
        name, _value = current_field(bridge)
        if name == "Algorithm":
            return True
        bridge.press_button(Button.CursorUp)
        time.sleep(0.35)
    return current_field(bridge)[0] == "Algorithm"


def set_algorithm(bridge, number: int):
    """Type an algorithm number, and return `(shown_number, chain)`.

    Refuses unless the device says the cursor is on `Algorithm`, because typing
    digits into whatever happens to be selected produces a full set of entirely
    plausible rows.
    """
    name, _value = current_field(bridge)
    if name != "Algorithm":
        raise RuntimeError(f"cursor is on {name!r}, not 'Algorithm' -- refusing "
                           f"to type digits into it")
    for ch in str(number):
        bridge.press_button(DIGITS[int(ch)])
        time.sleep(0.24)
    bridge.press_button(Button.Enter)
    time.sleep(0.6)
    r = rows(bridge)
    return r[2].split(":")[-1].strip(), r[5].rstrip()


def slots_of(chain: str):
    """The block chain split into slots, with the filter-looking ones flagged."""
    parts = [p for p in chain.split() if p]
    return parts, [i + 1 for i, p in enumerate(parts)
                   if any(w in p.upper() for w in FILTER_WORDS)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--program", type=int, default=206,
                    help="any program to borrow an edit buffer from")
    ap.add_argument("--out", default="algorithm_table.jsonl")
    args = ap.parse_args()

    bridge = connect()
    try:
        print(f"connected: {bridge.description}")
        while bridge.client.midi_in.get_message() is not None:
            pass
        if "ProgramMode" not in rows(bridge)[0]:
            print("not in Program Mode; leave the editor first")
            return 1

        select_program(bridge, args.program)
        bridge.press_button(Button.Edit)
        time.sleep(0.9)
        if not open_alg_page(bridge):
            print("could not reach the ALG page")
            return 1

        if not goto_algorithm_field(bridge):
            name, value = current_field(bridge)
            print(f"could not reach the Algorithm field; cursor reports "
                  f"{name!r} = {value!r}")
            leave_editor(bridge)
            return 1
        print(f"cursor confirmed on Algorithm = {current_field(bridge)[1]!r}")

        written = 0
        with open(args.out, "w") as fh:
            for number in ALGORITHMS:
                try:
                    shown, chain = set_algorithm(bridge, number)
                except RuntimeError as exc:
                    print(f"  !! {exc}")
                    break
                parts, filters = slots_of(chain)
                fh.write(json.dumps({
                    "requested": number, "shown": shown, "chain": chain,
                    "blocks": parts, "filter_slots": filters,
                }) + "\n")
                fh.flush()
                written += 1
                print(f"  alg {shown:>3}: filters at {filters or '-'}   {chain}",
                      flush=True)
        print(f"\nwrote {written} row(s) to {args.out}")
        # The buffer was edited; leaving without saving is the whole safety story.
        if not leave_editor(bridge):
            print("!! did NOT get back to Program Mode -- check the panel; the "
                  "edit buffer must not be saved")
            return 1
        print("left the editor without saving")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
