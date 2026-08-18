# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 37: census every resident program, then dump the objects.  (READ-ONLY)

Runs after a macro load has filled the instrument, and produces the two things a
file-to-device join needs:

1. **The census** — `DIRBANK` per bank, giving `id -> name` for everything
   resident. This is the join key. It is deliberately collected *first* and
   written out on its own, because it is what tells you whether the join is
   even sound: a bank whose names match the source file's in order proves the
   alignment, and a bank whose names diverge is a finding about the loader
   rather than a silent mis-join.

2. **The objects** — one `Read` each, in a NAMED encoding.

Why not compute `id - base` and skip the census: because most entries of the
macro that fills this machine load in **Fill** mode, where a file's first object
lands at whatever id was free rather than at the bank base. Eleven files Fill
into one bank in sequence, so every base after the first is a function of the
object counts of everything before it, plus Fill's gap behaviour, which nobody
has observed. Joining by name needs none of that and checks itself.

The encoding is recorded on every row. The two formats are only different
*packings* of the same bytes — 4 bits per MIDI byte or 7 — so they must decode
identically; ours did not for a while, because a left-aligned bit stream was being
front-padded, and the difference was briefly mistaken for a fact about the
protocol. Recording the form is what makes that checkable after the fact.

    .venv/bin/python probes/p37_census_and_dump.py --census-only
    .venv/bin/python probes/p37_census_and_dump.py -o ~/temp/k2k_full
"""
import sys; sys.path.insert(0, ".")
import argparse
import json
import os
import time

from probes.hw import connect
from probes.p33_bankdir import list_bank
from k2000.definitions import EncodingFormat, ObjectType
from k2000.messages import Read

#: DIRBANK takes the BANK NUMBER (one 7-bit byte), not the id base. Bank 2 is
#: the 200s. Passing 200 raises "Can't encode value 200 in 1 7-bit bytes", which
#: is at least loud; passing a number that happens to fit would not be.
BANKS = list(range(10))


def census(bridge, banks=BANKS):
    """`[{bank, id, name}]` for every resident program, bank by bank."""
    found = []
    for bank in banks:
        try:
            # NOTE the tuple: list_bank returns (infos, saw_end_of_bank).
            # Binding this to a single name makes len() report 2 for every bank
            # -- a plausible-looking count that is really the arity of a tuple.
            infos, complete = list_bank(bridge, bank, ObjectType.Program,
                                        ram_only=True)
        except Exception as exc:
            print(f"  bank {bank}: {type(exc).__name__}: {exc}", flush=True)
            continue
        if not complete:
            # No ENDOFBANK means the listing timed out mid-way, so the bank is
            # under-reported. Silently accepting it would look like a short bank.
            print(f"  bank {bank}: !! no ENDOFBANK -- listing INCOMPLETE",
                  flush=True)
        for info in infos:
            found.append({"bank": bank,
                          "id": getattr(info, "idno", None),
                          # VERBATIM. Object names carry significant leading and
                          # trailing spaces and sometimes embedded quotes --
                          # ' BELL MAGIC   ' is a real name. Stripping here would
                          # break the join against the file's names, and it would
                          # break it silently, as a near-match. The sibling
                          # project manufactured fourteen phantom findings from
                          # one inconsistent strip() of a leading space.
                          "name": getattr(info, "name", "") or "",
                          "complete": complete})
        print(f"  bank {bank} ({bank * 100:>3}s): {len(infos):>4} programs",
              flush=True)
    return found


def dump(bridge, entries, encoding, path):
    """One `Read` per program, appending to `path` as it goes.

    Flushes every row: a run interrupted at object 300 should leave 300 usable
    rows rather than a truncated buffer.
    """
    written = failed = 0
    started = time.monotonic()
    with open(path, "w") as fh:
        for entry in entries:
            idno = entry["id"]
            while bridge.client.midi_in.get_message() is not None:
                pass
            try:
                reply = bridge.client._send_and_receive(
                    Read(ObjectType.Program, idno, encoding), 5.0)
            except Exception as exc:
                failed += 1
                print(f"  {idno}: {type(exc).__name__}", flush=True)
                continue
            data = getattr(reply, "data", b"") or b""
            fh.write(json.dumps({
                "id": idno,
                "bank": entry["bank"],
                # Both verbatim, and both kept: DIRBANK and Read each report a
                # name, and a disagreement between them is worth seeing rather
                # than collapsing into one field.
                "census_name": entry["name"],
                "read_name": getattr(reply, "name", "") or "",
                "encoding": encoding.name,
                "bytes": len(data),
                "data": data.hex(),
            }) + "\n")
            fh.flush()
            written += 1
    elapsed = time.monotonic() - started
    print(f"\ndumped {written} objects ({failed} failed) in {elapsed:.0f} s "
          f"-> {path}")
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default="k2k_full")
    ap.add_argument("--census-only", action="store_true")
    ap.add_argument("--encoding", choices=("Nibblized", "BitStream"),
                    default="Nibblized",
                    help="transmission packing only; both must decode alike, and it is recorded per row so that stays checkable")
    args = ap.parse_args()

    bridge = connect()
    try:
        print(f"connected: {bridge.description}")
        while bridge.client.midi_in.get_message() is not None:
            pass
        os.makedirs(args.output, exist_ok=True)

        print("census:")
        entries = census(bridge)
        census_path = os.path.join(args.output, "census.jsonl")
        with open(census_path, "w") as fh:
            for row in entries:
                fh.write(json.dumps(row) + "\n")
        print(f"\n{len(entries)} resident programs -> {census_path}")
        if args.census_only:
            return 0

        return 0 if dump(bridge, entries,
                         getattr(EncodingFormat, args.encoding),
                         os.path.join(args.output, "objects.jsonl")) else 1
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
