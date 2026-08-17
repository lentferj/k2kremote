# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 36: read the filter frequency page for many programs.  (READ-ONLY-ish)

Exists to name three unmapped bytes. The sibling mpc2emu's KRZ parser has
`seg[2]`, `seg[3]` and `seg[4]` undecoded on filter slots, and the F1 FRQ page has
exactly four fields it cannot account for: **Fine, KeyTrk, VelTrk, Pad**. Across
15451 filter slots in its corpus those bytes are non-zero on 0.9%, 15.9% and
66.4% respectively.

Why that matters more than any measurement: if **VelTrk** is `seg[3]` or `seg[4]`,
then thousands of filter slots carry a *direct* velocity->cutoff amount that the
converter currently reads as zero — against the 47 routings it counts today
through Src2/MaxDpt. The silenced-quiet-notes defect would have a second
population one to two orders of magnitude larger.

So this walks programs, opens the editor, finds the filter's F1 FRQ page, and
reports what the panel displays:

    program, name, layer, algorithm, block, Coarse, Fine, KeyTrk, VelTrk, Pad

mpc2emu joins that against `seg[1..4]` in the same files and names the bytes — the
same correlation that validated the depth field map at 581/581.

**Programs are chosen for VARIATION, not convenience.** A page of zeros identifies
nothing: with every candidate byte at 0 and every field at 0, any assignment fits.
That is the no-variation trap that left DRUM INPUTS undecodable in the sibling
project.

Enters the editor but changes nothing, and answers the "Save ... before exiting?"
prompt with **No** every time. It presses buttons, so it is not strictly read-only
— but it writes no parameter and saves no object.

    .venv/bin/python probes/p36_filter_fields.py 200 201 202 --out fields.jsonl
    .venv/bin/python probes/p36_filter_fields.py --bank 300 --count 12
"""
import sys; sys.path.insert(0, ".")
import argparse
import json
import time

from probes.hw import connect
from k2000.definitions import Button

DIGITS = {n: getattr(Button, f"Number{n}") for n in range(10)}
SOFT = [Button.SoftA, Button.SoftB, Button.SoftC,
        Button.SoftD, Button.SoftE, Button.SoftF]


def rows(bridge):
    return bridge.get_screen_text().split("\n")


def select_program(bridge, number: int) -> None:
    for ch in str(number):
        bridge.press_button(DIGITS[int(ch)]); time.sleep(0.22)
    bridge.press_button(Button.Enter); time.sleep(0.5)


def soft_index(soft_row: str, label: str):
    """Which soft key carries `label`, by the zone its text falls in."""
    idx = soft_row.find(label)
    if idx < 0:
        return None
    return min(5, int(idx * 6 / 40))


#: A filter's frequency page is "Fn FRQ", and n is the block slot the filter
#: happens to occupy — NOT always F1. Programs 1, 5 and 6 of the ROM put their
#: filter at F3 (PITCH SINE XFADE LOPAS2 AMP), and a reader that looks only for
#: "F1 FRQ" silently skips them and reports "no filter". Half the first six ROM
#: programs were lost that way.
FRQ_LABELS = ["F1 FRQ", "F2 FRQ", "F3 FRQ", "F4 FRQ"]


def open_filter_page(bridge, hops: int = 8):
    """Find and open whichever "Fn FRQ" page this program's filter lives on.

    `more>` cycles the soft-key LABELS, not the page — a trap this project has
    now hit twice — so the label set has to be advanced first and the key pressed
    second.
    """
    for _ in range(hops):
        soft = rows(bridge)[7]
        for label in FRQ_LABELS:
            i = soft_index(soft, label)
            if i is not None:
                bridge.press_button(SOFT[i]); time.sleep(0.7)
                header = rows(bridge)[0]
                return header if "FRQ" in header else None
        j = soft_index(soft, "more>")
        if j is None:
            return None
        bridge.press_button(SOFT[j]); time.sleep(0.45)
    return None


#: The page is two fixed columns on a 40-character screen; the right-hand one
#: begins here. Splitting on runs of spaces instead reads `Coarse:G 10 25088Hz`
#: as `G 10 25088Hz Src1 :FUN1`, because a 12-character value leaves no gap
#: before the next column. That contaminated value looked fine in a log and
#: would have joined against the wrong byte.
RIGHT_COLUMN = 20


def current_field(bridge):
    """(name, value) of the parameter the cursor is on, per the DEVICE.

    SysEx 0x17 / 0x16 -- "request the currently-selected parameter name / value".
    The K2000 answers `('Coarse:', 'E 4 330Hz')`, so the cursor position is
    directly readable and never has to be inferred.

    This project believed otherwise all evening, on the strength of
    RESOLUTION_NOTES §6, which says the name-edit cursor appears in neither
    device reply. That is true and it is about the *character* position inside a
    name field. Generalising it to "the parameter cursor is unreadable" cost a
    PNG-render loop, 48 wheel clicks into the wrong field, and two sweeps whose
    flat results were nearly reported as measurements. The message table had the
    answer the whole time.
    """
    return (bridge.client.get_current_parameter_name().strip().rstrip(":"),
            bridge.client.get_current_parameter_value().strip())


def goto_field(bridge, wanted: str, limit: int = 14):
    """Move the cursor onto `wanted`, verifying against the device each step.

    Walks down the column, then to the other column and down again, asking the
    instrument what is selected after every move. Returns the value on success and
    None when the field is not on this page -- which is a refusal, not a guess.
    """
    from k2000.definitions import Button
    seen = []
    for i in range(limit):
        name, value = current_field(bridge)
        if name == wanted:
            return value
        seen.append(name)
        # exhaust one column, then hop across
        bridge.press_button(Button.CursorDown if i < limit // 2
                            else Button.CursorRight)
        time.sleep(0.35)
        if i == limit // 2:
            for _ in range(limit // 2):
                bridge.press_button(Button.CursorUp); time.sleep(0.3)
    return None


def field(row: str, name: str):
    """`name:value`, taking the column the label actually sits in."""
    row = row.rstrip("\n")
    halves = (row[:RIGHT_COLUMN], row[RIGHT_COLUMN:])
    for half in halves:
        if name in half:
            value = half.split(name, 1)[1].lstrip()
            if value.startswith(":"):
                value = value[1:]
            return value.strip() or None
    return None


def read_filter_fields(bridge) -> dict:
    r = rows(bridge)
    header = r[0].rstrip()
    slot = None
    for cand in ("F1", "F2", "F3", "F4"):
        if f"{cand} FRQ" in header:
            slot = cand
    return {
        "header": header,
        "slot": slot,
        # The header is `EditProg*F3 FRQ(PARA TREBLE)<>Layer:1/2` and the closing
        # paren can be absent when the name is long enough to be truncated, so
        # cut on the layer marker too — otherwise the filter name comes out as
        # "PARA TREBLE<>Layer:1/2", which is a contaminated join key.
        "filter": (header.split("(")[-1].split(")")[0].split("<>")[0].strip()
                   if "(" in header else None),
        "layer": r[0].split("Layer:")[-1].strip() if "Layer:" in r[0] else None,
        "Coarse": field(r[1], "Coarse"),
        "Fine": field(r[2], "Fine"),
        "KeyTrk": field(r[4], "KeyTrk"),
        "VelTrk": field(r[5], "VelTrk"),
        "Pad": field(r[6], "Pad"),
        "Src1": field(r[1], "Src1"),
        "Depth": field(r[2], "Depth"),
        "Src2": field(r[3], "Src2"),
        "DptCtl": field(r[4], "DptCtl"),
        "MinDpt": field(r[5], "MinDpt"),
        "MaxDpt": field(r[6], "MaxDpt"),
    }


def leave_editor(bridge) -> bool:
    """Exit, answering any save prompt with No. True if we reached Program Mode."""
    bridge.press_button(Button.Exit); time.sleep(0.9)
    r = rows(bridge)
    if "before exiting?" in " ".join(r):
        i = soft_index(r[7], "No")
        if i is None:
            return False
        bridge.press_button(SOFT[i]); time.sleep(1.0)
        r = rows(bridge)
    return "ProgramMode" in r[0]


def algorithm_of(bridge):
    """Algorithm number and chain, from the ALG page, without changing anything."""
    for _ in range(8):
        soft = rows(bridge)[7]
        i = soft_index(soft, "ALG")
        if i is not None:
            bridge.press_button(SOFT[i]); time.sleep(0.6)
            r = rows(bridge)
            if "ALG" in r[0]:
                return r[2].split(":")[-1].strip(), r[5].rstrip()
            return None, None
        j = soft_index(soft, "more>")
        if j is None:
            return None, None
        bridge.press_button(SOFT[j]); time.sleep(0.4)
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("programs", nargs="*", type=int)
    ap.add_argument("--out", default="filter_fields.jsonl")
    args = ap.parse_args()
    if not args.programs:
        ap.error("give at least one program number")

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
                select_program(bridge, number)
                bridge.press_button(Button.Edit); time.sleep(0.9)
                alg, chain = algorithm_of(bridge)
                header = open_filter_page(bridge)
                if header is None:
                    print(f"  {number}: no F1 FRQ page (algorithm {alg}: {chain})")
                else:
                    row = read_filter_fields(bridge)
                    row.update({"program": number, "algorithm": alg, "chain": chain})
                    fh.write(json.dumps(row) + "\n")
                    fh.flush()
                    written += 1
                    print(f"  {number}: alg {alg:>2}  Coarse={row['Coarse']:<12} "
                          f"Fine={row['Fine']:<8} KeyTrk={row['KeyTrk']:<12} "
                          f"VelTrk={row['VelTrk']:<10} Pad={row['Pad']}", flush=True)
                if not leave_editor(bridge):
                    print(f"  !! could not get back to Program Mode after {number}; "
                          f"stopping rather than editing blind")
                    return 1
        print(f"\nwrote {written} row(s) to {args.out}")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
