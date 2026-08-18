# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 38: the filter page for EVERY layer, not just the first.  (READ-ONLY-ish)

Probe 36's successor, and it exists because of what p36 missed. p36 opens the
editor and reads whichever layer the editor happens to land on — always layer 1
— and reports one row per program. Run against 13 programs that file-side
analysis said carry a filter in slot **F3**, it confirmed 8 and appeared to
contradict 5: three showed a filter in F1/F2 instead, and two showed no filter
page at all.

None of those five was a contradiction. Every one of them reads `Layer:1/2` or
`Layer:1/3` in its header — the filter the file analysis found is simply on a
layer p36 never visited. A program's layers can carry completely different
algorithms, so "this program's filter is in F1" is not a property of the program
at all; it is a property of one layer of it.

That distinction matters beyond this probe. A survey that reads layer 1 and
reports per program will systematically under-count anything that lives deeper,
and it will do so *quietly*, because every row it returns is individually
correct. The sibling project's ROM sample said 43% of filters sit outside F1;
the corpus said 1.6%; both were reading different populations of the same thing.

So: walk every layer, record which slot the filter occupies in each, and keep
layers with no filter as explicit rows rather than dropping them — an absence
that was looked for is data, an absence that was never looked for is not.

    .venv/bin/python probes/p38_filter_layers.py 206 508 --out layers.jsonl
"""
import sys; sys.path.insert(0, ".")
import argparse
import json
import time

from probes.hw import connect
from probes.p36_filter_fields import (
    SOFT, rows, select_program, soft_index, open_filter_page,
    read_filter_fields, leave_editor, algorithm_of,
)
from k2000.definitions import Button


def layer_of(header: str):
    """`(current, total)` from a `…<>Layer:1/3` header, or `(None, None)`."""
    if "Layer:" not in header:
        return None, None
    field = header.split("Layer:")[-1].strip()
    if "/" not in field:
        return None, None
    current, _, total = field.partition("/")
    try:
        return int(current.strip()), int(total.strip())
    except ValueError:
        return None, None


def next_layer(bridge) -> None:
    """Advance to the next layer. Wraps at the last one."""
    bridge.press_button(Button.ChanBankInc)
    time.sleep(0.55)


#: Every filter page a layer might have, not just the first one found.
FRQ_ALL = ["F1 FRQ", "F2 FRQ", "F3 FRQ", "F4 FRQ"]


def open_named_filter_page(bridge, label: str, hops: int = 8):
    """Open one SPECIFIC `Fn FRQ` page, or return None if this layer has none.

    p36's version took the first `Fn FRQ` label it saw and stopped, which is
    wrong for any algorithm carrying more than one filter. `PITCH SAW LOPASS
    LOPASS` has a filter in F2 *and* F3; the first-match reader returns F2, and
    the F3 filter is then reported as absent. That produced three apparent
    contradictions of a file-side analysis which was in fact correct.

    `more>` cycles the soft-key LABELS rather than the page, so the label set has
    to be advanced first and the key pressed second.
    """
    for _ in range(hops):
        soft = rows(bridge)[7]
        i = soft_index(soft, label)
        if i is not None:
            bridge.press_button(SOFT[i])
            time.sleep(0.7)
            header = rows(bridge)[0]
            return header if "FRQ" in header else None
        j = soft_index(soft, "more>")
        if j is None:
            return None
        bridge.press_button(SOFT[j])
        time.sleep(0.45)
    return None


def survey_program(bridge, number: int, max_layers: int = 8):
    """One row per LAYER: algorithm, filter slot, and the FRQ page if there is one."""
    select_program(bridge, number)
    bridge.press_button(Button.Edit)
    time.sleep(0.9)

    collected = []
    seen_layers = set()
    for _ in range(max_layers):
        alg, chain = algorithm_of(bridge)
        current, total = layer_of(rows(bridge)[0])
        if current is None:
            # No layer marker means this program has a single layer and the
            # editor does not paginate; treat it as layer 1 of 1.
            current, total = 1, 1
        if current in seen_layers:
            break                       # wrapped round
        seen_layers.add(current)

        # Every filter this layer has, not the first one. A layer can hold two.
        found_any = False
        for label in FRQ_ALL:
            header = open_named_filter_page(bridge, label)
            if header is None:
                continue
            row = read_filter_fields(bridge)
            row["no_filter_page"] = False
            row.update({"program": number, "layer_index": current,
                        "layer_total": total, "algorithm": alg, "chain": chain,
                        "asked_for": label})
            collected.append(row)
            found_any = True
            print(f"  {number} L{current}/{total}: alg {str(alg):>2}  "
                  f"slot={str(row.get('slot')):<4} "
                  f"filter={str(row.get('filter'))[:18]:<18} "
                  f"VelTrk={str(row.get('VelTrk')):<10} "
                  f"Coarse={str(row.get('Coarse'))}", flush=True)

        if not found_any:
            # An algorithm with no filter block at all is a real observation,
            # not a failed read, and is kept as one.
            row = {"slot": None, "filter": None, "no_filter_page": True,
                   "program": number, "layer_index": current,
                   "layer_total": total, "algorithm": alg, "chain": chain}
            collected.append(row)
            print(f"  {number} L{current}/{total}: alg {str(alg):>2}  "
                  f"NO filter block  ({chain})", flush=True)

        if total and current >= total:
            break
        next_layer(bridge)
    return collected


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("programs", nargs="+", type=int)
    ap.add_argument("--out", default="filter_layers.jsonl")
    args = ap.parse_args()

    bridge = connect()
    written = 0
    try:
        print(f"connected: {bridge.description}")
        while bridge.client.midi_in.get_message() is not None:
            pass
        if "ProgramMode" not in rows(bridge)[0]:
            print("not in Program Mode; leave the editor first")
            return 1
        with open(args.out, "w") as fh:
            for number in args.programs:
                for row in survey_program(bridge, number):
                    fh.write(json.dumps(row) + "\n")
                    fh.flush()
                    written += 1
                if not leave_editor(bridge):
                    print(f"  !! stuck in the editor after {number}; stopping "
                          f"rather than pressing on blind")
                    return 1
        print(f"\nwrote {written} layer row(s) to {args.out}")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
