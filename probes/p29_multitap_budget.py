# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 29: how many pad presses does a real multi-tap actually need?

`type_name` now derives its press budget from the pad's ring (`_passes`: one
reset plus a full lap) and **raises** `NameEntryFailed` when a cell never shows
the wanted character. Both are correct against the synthetic fake. The open
question (TODO, commit 79e4ab2) is what the *hardware* does:

* if every character lands inside the derived budget, the bound is right and the
  raise will effectively never fire — which is what we want;
* if the device occasionally drops a press, the budget is still right but the
  raise turns a formerly-silent wrong character into a visible failure. That is
  an improvement only if it is **rare**. If it fires routinely, the retry needs
  to be inside `_type_char`, not surfaced to the user.

So this measures the distribution rather than asserting a pass. It records every
button press `type_name` makes, splits the sequence on `CursorRight` (each one
ends a character) and reports the presses actually spent per character against
the budget for that character's pad.

**Writes to a name field, not to an object.** It types into an *already open*
name dialog, which edits a buffer, and it presses **Cancel** when it is done, so
nothing is stored. It never presses OK and never saves. It refuses to start
unless the panel is actually showing a name dialog, and refuses to run
unattended (p26's lesson: a probe that needs eyes must fail closed).

The cursor is *measured*, not assumed: it is not readable over MIDI, so the probe
writes one character, diffs the field to see which column moved, and walks it to
the first cell — then re-measures to confirm. Nothing to park by hand.

    # get the K2000 to a name dialog first, then:
    .venv/bin/python probes/p29_multitap_budget.py --attended
    .venv/bin/python probes/p29_multitap_budget.py --attended --keep  # no Cancel

Targets are chosen for the worst cases, not for realism: '9' sits ten presses
into the digit ring, and C/F/I/L/O/R/U/X are each third in their letter group.
"""
import sys; sys.path.insert(0, ".")
import argparse
import collections
import time

from probes.hw import connect
from k2kremote import text_entry as te
from k2kremote.app import is_name_dialog, soft_labels
from k2000.definitions import Button

# Each pass must fit the 16-column name field.
PASSES = [
    "0123456789",      # the whole digit ring; '9' is the far end (10 presses)
    "CFILORUX",        # every letter that sits 3rd in its pad group
    "AZ az",           # ring ends + the sticky case toggle both ways
]


def stamp(title=""):
    print(f"\n[{time.strftime('%H:%M:%S')}] {title}".rstrip(), flush=True)


class Counting:
    """Wraps the bridge and records every button press type_name makes."""

    def __init__(self, bridge):
        self._bridge = bridge
        self.presses = []          # Button, in order

    def press_button(self, button):
        self.presses.append(button)
        return self._bridge.press_button(button)

    def __getattr__(self, name):
        return getattr(self._bridge, name)

    def split_by_character(self):
        """Presses grouped per character: CursorRight ends each group."""
        groups, current = [], []
        for button in self.presses:
            if button == Button.CursorRight:
                groups.append(current)
                current = []
            else:
                current.append(button)
        groups.append(current)
        return groups


def locate_cursor(bridge, name_row, name_col, settle=0.55):
    """Find the name cursor's column by writing to it and seeing what moved.

    The cursor is not readable over MIDI, and every read-back in `type_name` is
    offset from it — one cell out and each character is verified against its
    neighbour, which looks identical to the device dropping presses.

    Asking a human to park it and confirm is one option; measuring is better,
    because the answer is observable. Pressing the digit pad always changes the
    cell under the cursor (it cycles 0..9, so even a cell already showing '0'
    becomes '1'), and diffing the field before and after says exactly which
    column that was. No assertion required, and nothing outside the buffer.
    """
    before = bridge.get_screen_text().split("\n")[name_row]
    bridge.press_button(Button.Number0)
    time.sleep(settle)
    after = bridge.get_screen_text().split("\n")[name_row]
    moved = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if len(moved) != 1:
        raise RuntimeError(
            f"could not locate the cursor: {len(moved)} columns changed "
            f"({moved}) — before {before!r} after {after!r}")
    return moved[0] - name_col


def budget_for(ch):
    """The budget type_name allows this character (mirrors `_passes`)."""
    if ch in te._DIGITS:
        return te._passes(len(te._DIGITS), None)
    if ch.isalpha():
        button, _ = te._LETTER_TAPS[ch.upper()]
        return te._passes(len(te.PAD_GROUPS[button]), None)
    return None                    # space/punctuation reach the wheel instead


def run_pass(bridge, target):
    stamp(f"typing {target!r}")
    counter = Counting(bridge)
    failed = None
    try:
        te.type_name(counter, target, settle=0.55)
    except te.NameEntryFailed as exc:
        failed = str(exc)

    groups = counter.split_by_character()
    rows = []
    for ch, presses in zip(target, groups):
        pad = [p for p in presses if p != Button.PlusMinus]
        budget = budget_for(ch)
        rows.append((ch, len(pad), budget,
                     sum(1 for p in presses if p == Button.PlusMinus)))
    print(f"  {'ch':<4}{'pad presses':>12}{'budget':>8}{'case fixes':>12}   verdict")
    worst = []
    for ch, used, budget, cases in rows:
        if budget is None:
            verdict = "wheel (n/a)"
        elif used > budget:
            verdict = "OVER BUDGET"
            worst.append((ch, used, budget))
        else:
            verdict = f"ok ({budget - used} spare)"
        print(f"  {ch!r:<4}{used:>12}{str(budget):>8}{cases:>12}   {verdict}")
    if failed:
        print(f"  !! NameEntryFailed: {failed}")
    return rows, worst, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep", action="store_true",
                    help="leave the dialog as typed instead of pressing Cancel")
    ap.add_argument("--attended", action="store_true",
                    help="you are at the panel, watching this type")
    args = ap.parse_args()

    # p26's rule is that a probe needing eyes must fail closed. The first version
    # of this one inferred "someone is watching" from stdin being a tty, which is
    # a proxy for the thing rather than the thing: a terminal can be idle, and a
    # perfectly attended run through a wrapper has no tty at all. It locked out
    # the human it was written for. So the assertion is now explicit — typing the
    # flag *is* the act of a person being present.
    if not args.attended:
        sys.exit("refusing to run unattended: this types on the panel.\n"
                 "  Pass --attended once you are at the K2000 watching it.")

    bridge = connect()
    try:
        rows = bridge.get_screen_text().split("\n")
        stamp(f"connected: {bridge.description}")
        print(f"screen: {rows[0].rstrip()!r}")
        print(f"soft keys: {soft_labels(rows)}")
        if not is_name_dialog(rows):
            sys.exit("the panel is NOT showing a name dialog — get to one first "
                     "(the soft row must read Delete Insert <<< >>> OK Cancel); "
                     "refusing to type blind")

        name_row, name_col = te._find_name_field(rows)
        start_col = locate_cursor(bridge, name_row, name_col)
        print(f"name field at row {name_row} col {name_col}; "
              f"cursor measured at offset {start_col}")
        if start_col < 0:
            sys.exit(f"cursor is left of the name field (offset {start_col}) — "
                     "not typing into whatever that is")

        # Walk it to the field's first cell. The count is now known rather than
        # guessed, so this is exact — and it is re-measured afterwards instead of
        # assumed to have worked, because "press left N times" is precisely the
        # kind of step that quietly clamps or wraps differently than expected.
        for _ in range(start_col):
            bridge.press_button(Button.CursorLeft)
            time.sleep(0.35)
        start_col = locate_cursor(bridge, name_row, name_col)
        if start_col != 0:
            sys.exit(f"cursor is at offset {start_col} after walking it left, "
                     "not 0 — the field does not move the way this assumed")
        print("cursor parked at the first cell, re-measured to confirm")

        all_worst, failures, all_rows = [], [], []
        for target in PASSES:
            got, worst, failed = run_pass(bridge, target)
            all_rows += got
            all_worst += worst
            if failed:
                failures.append((target, failed))
            # Back to the field's first cell for the next pass.
            for _ in range(len(target) - 1):
                bridge.press_button(Button.CursorLeft)

        stamp("=" * 60)
        used = collections.Counter()
        for ch, n, budget, _ in all_rows:
            if budget is not None:
                used[budget - n] += 1
        print(f"characters typed: {len(all_rows)}")
        print(f"spare presses left over, by count: {dict(sorted(used.items()))}")
        if not all_worst and not failures:
            print("\nNo character exceeded its budget and nothing raised.")
            print("The derived bound holds on hardware; the raise is a genuine")
            print("last resort rather than a routine event. TODO item closed.")
        else:
            print(f"\nOver budget: {all_worst}")
            print(f"Raised: {failures}")
            print("The budget is still right, but the device drops presses, so the")
            print("retry belongs INSIDE _type_char rather than raised at the user.")
    finally:
        if not args.keep:
            stamp("pressing Cancel — nothing is stored")
            try:
                bridge.press_button(Button.SoftF)      # Cancel, per is_name_dialog
            except Exception as exc:
                print(f"  could not press Cancel ({exc}); do it on the panel")
        bridge.close()


if __name__ == "__main__":
    main()
