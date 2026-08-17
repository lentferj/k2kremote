# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 34: record one real LCD frame as a fixture, for the docs.  (READ-ONLY)

The README's mirror screenshots were captured by hand in June 2026 and went stale
the moment the soft-key alignment and legend grouping landed in August: they still
show the old, unaligned bar. Re-shooting them by hand would put them straight back
on the same treadmill.

So instead: record **one** real frame here, and let
``docs/make_mirror_screenshots.py`` render it in every mode offline, for ever.
Real LCD content, accurate chrome, and reproducible by anyone with the fixture —
the same arrangement the k2kmaced screenshots already use.

Sends ALLTEXT and GETGRAPHICS, which are pure reads, and nothing else. No button
presses, so the panel stays exactly where you left it — point it at whatever page
should appear in the documentation before running this.

    .venv/bin/python probes/p34_capture_frame.py
    .venv/bin/python probes/p34_capture_frame.py -o docs/fixtures/frame-song.json

The fixture is JSON: the pixel plane as a flat 0/1 string (240x64 packs to 15 KB,
which compresses in git far better than a PNG and stays diffable), plus the text
rows and the reverse-video mask.
"""
import sys; sys.path.insert(0, ".")
import argparse
import json
import time

from probes.hw import connect
from k2kremote import braille

DEFAULT_OUT = "docs/fixtures/frame.json"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default=DEFAULT_OUT)
    args = ap.parse_args()

    bridge = connect()
    try:
        print(f"connected: {bridge.description}")
        # Drain anything still queued before asking for anything. The vendored
        # client returns the FIRST inbound message matching the response class,
        # so a reply left over from an earlier request gets handed to this one --
        # which showed up as "ScreenReply contains image data and cannot be
        # converted to str": the previous run's GETGRAPHICS answer being served
        # to an ALLTEXT request.
        drained = 0
        while bridge.client.midi_in.get_message() is not None:
            drained += 1
        if drained:
            print(f"  drained {drained} stale inbound message(s)")
        # Text first: it is the cheap plane (131.6 ms against GETGRAPHICS' 962.7),
        # so if the device is going to refuse, it refuses sooner.
        # get_screen_text_attrs returns the masked screen as ONE newline-joined
        # string plus the per-row reverse mask — not a list of rows. Passing it
        # straight to list() silently yields 327 single characters, which loads
        # without complaint and renders as nonsense.
        text, reverse = bridge.get_screen_text_attrs()
        rows = text.split("\n")
        pixels = bridge.get_graphics()
    finally:
        bridge.close()

    flat = "".join("1" if v else "0" for v in pixels.reshape(-1))
    payload = {
        "captured": time.strftime("%Y-%m-%dT%H:%M:%S"),
        # The array's OWN shape, not (SCREEN_H, SCREEN_W): get_graphics returns
        # (240, 64) — width-major — and reshaping the flattened copy to (64, 240)
        # transposes the screen into convincing noise. It looks like a decode
        # failure rather than a reshape, which is what made it worth a comment.
        "shape": list(pixels.shape),
        "width": braille.SCREEN_W,
        "height": braille.SCREEN_H,
        "pixels": flat,
        "text_rows": list(rows),
        "reverse": list(reverse),
        "note": "one real K2000R frame; see probes/p34_capture_frame.py",
    }
    import os
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as fh:
        json.dump(payload, fh, indent=1)

    print(f"wrote {args.output}")
    print(f"  screen: {rows[0].rstrip()!r}")
    print(f"  lit pixels: {flat.count('1')} of {len(flat)}")
    print("Now regenerate the docs images:")
    print("  .venv/bin/python docs/make_mirror_screenshots.py")


if __name__ == "__main__":
    main()
