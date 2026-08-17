#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

"""Regenerate the README's mirror screenshots from a recorded frame.

    .venv/bin/python docs/make_mirror_screenshots.py

The originals were shot by hand in June 2026 and were stale by August: the
soft-key alignment and legend grouping changed the chrome, and no screenshot
followed. Hand-shooting them again would just restart that clock, so this renders
a **recorded real frame** (``docs/fixtures/frame.json``, captured read-only by
``probes/p34_capture_frame.py``) through the actual app, offline. Real LCD
content, current chrome, and anyone can re-run it after a UI change.

Output is **PNG**, the same call the sibling eosed made and for the same reason.
Textual exports SVG whose text depends on a font declared by name, with a CDN
`@font-face` and a `local()` fallback — and these pictures are made *of* glyphs:
braille U+28xx for the braille mode, quadrant and half blocks for the others. On
this machine Fira Code is not installed and no single local monospace font covers
both ranges, so a viewer renders half the screen as tofu. Rasterising here fixes
the glyphs at generation time: what is committed is what is seen.

**Except image mode.** That draws through the terminal's own graphics protocol —
kitty TGP, sixel — which by definition cannot be captured into an SVG at all.
That one screenshot stays a photograph of a real terminal; see `--image-help`.
"""
import asyncio
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import numpy as np                                          # noqa: E402

from _shot import svg_to_png                                 # noqa: E402

from k2kremote import braille                                # noqa: E402
from k2kremote.app import K2KRemoteApp                       # noqa: E402
from k2kremote.refresh import Frame                          # noqa: E402

FIXTURES = REPO / "docs" / "fixtures"
OUT = REPO / "docs" / "img"

# (filename stem, mode, terminal size, fixture). The two blocks flavours are
# chosen by width, not by name — 240 columns gets half-block, narrower gets
# quadrant — so the size is what distinguishes those two shots, and getting it
# wrong silently produces two pictures of the same thing.
#
# Two fixtures, because one frame cannot flatter every mode: the pixel modes want
# a graphics-heavy page (an editor algorithm diagram is the case they exist for),
# while text mode wants a page that is actually text — a menu or a list, where its
# advantage over braille is the point. A missing second fixture falls back to the
# first, so the script still works with only one captured frame.
GRAPHICS_FRAME = "frame.json"
TEXT_FRAME = "frame-text.json"

SHOTS = [
    ("mirror-braille",     "braille", (124, 23), GRAPHICS_FRAME),
    ("mirror-blocks",      "blocks",  (128, 40), GRAPHICS_FRAME),  # -> quadrant
    # 40 rows, not 24: half-block cells are 1px wide x 2px tall, so the mirror is
    # 240x32 — the same 32 rows the quadrant mode needs, just four times wider.
    # At 24 the LCD was clipped mid-glyph and its soft-label row fell off entirely,
    # which looked like a rendering bug rather than a window too short.
    ("mirror-blocks-half", "blocks",  (244, 40), GRAPHICS_FRAME),  # -> half-block
    # 124 columns even though text mode only draws 40: below 120 the app puts up
    # "terminal 88 cols; need 120 for a 1:1 mirror — widen the window", and a
    # screenshot carrying its own warning banner reads as a broken app. The empty
    # right-hand side is the honest picture of a left-aligned 40-column render.
    ("mirror-text",        "text",    (124, 23), TEXT_FRAME),
]

IMAGE_HELP = """\
image mode cannot be rendered to SVG: it hands pixels to the terminal over
kitty's graphics protocol (or sixel), so there is nothing in the character grid
to export. To retake docs/img/mirror-image.png:

  1. run the mirror in kitty against the instrument:
       .venv/bin/python -m k2kremote.app --rig auto
  2. press F10 until the title bar says "image"
  3. capture the window (any of these is on this machine):
       import -window "$(xdotool getactivewindow)" docs/img/mirror-image.png
       scrot -u docs/img/mirror-image.png

F12 inside the app writes a PNG of the *LCD alone*, which is a different picture
— useful, but it shows none of the chrome this screenshot is meant to show.
"""


#: Stand-in for "a bridge exists", so the title bar reads "connected" rather than
#: "no MIDI". Never called: the frame is injected directly, so nothing asks it for
#: anything.
_PRESENT = object()


def load_frame(path: pathlib.Path) -> Frame:
    data = json.loads(path.read_text())
    flat = np.frombuffer(data["pixels"].encode(), dtype="S1") == b"1"
    # Restore the array's original shape. get_graphics is width-major, (240, 64);
    # braille.coerce accepts either orientation, but only if it is told the truth.
    shape = tuple(data.get("shape") or (data["height"], data["width"]))
    pixels = flat.reshape(shape)
    return Frame(pixels=pixels,
                 text_rows=data["text_rows"],
                 reverse=data.get("reverse", []))


async def shoot(fixtures: pathlib.Path) -> None:
    primary = fixtures / GRAPHICS_FRAME
    if not primary.exists():
        sys.exit(f"no recorded frame at {primary.relative_to(REPO)}.\n"
                 f"Capture one first (read-only, needs the K2000 on):\n"
                 f"  .venv/bin/python probes/p34_capture_frame.py -o "
                 f"{primary.relative_to(REPO)}")

    cache = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for stem, mode, size, wanted in SHOTS:
        path = fixtures / wanted
        if not path.exists():
            # Skip rather than fall back. Falling back to the graphics frame
            # produced a text-mode shot of a page whose ALLTEXT plane is almost
            # empty, and wrote it over the existing file — replacing a stale
            # picture with a worse one. A missing fixture means "not this shot",
            # not "any shot".
            print(f"  - {stem}: skipped, no {wanted} "
                  f"(capture one with probes/p34_capture_frame.py -o "
                  f"docs/fixtures/{wanted})")
            continue
        note = ""
        if path not in cache:
            cache[path] = load_frame(path)
        # demo=True only so no MIDI port is opened; the frame is a real capture,
        # so the title bar must not claim otherwise. Presenting it as "connected"
        # is what a reader would see with the instrument attached, which is the
        # situation the screenshot is documenting.
        app = K2KRemoteApp(demo=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            # Three attributes, because _titlebar_text checks them in order:
            # demo wins, then "no MIDI" when there is no bridge, then connected.
            # Setting only the first two produced a red "no MIDI" badge, which
            # reads as a broken app rather than a documented one.
            app._demo = False
            app._bridge = _PRESENT
            app._connected = True
            app._mode = mode
            app.show_frame(cache[path])
            from textual.widgets import Static
            app.query_one("#titlebar", Static).update(app._titlebar_text())
            await pilot.pause()
            app.save_screenshot(str(OUT / f"{stem}.svg"))
        made = svg_to_png(OUT / f"{stem}.svg")
        print(f"  {stem}.{made}   mode={mode} size={size[0]}x{size[1]}{note}")


def main() -> int:
    if "--image-help" in sys.argv:
        print(IMAGE_HELP)
        return 0
    # --fixture exists so the pipeline can be exercised before any hardware is
    # available; the default is the recorded frame the docs actually ship.
    fixtures = FIXTURES
    if "--fixtures" in sys.argv:
        fixtures = pathlib.Path(sys.argv[sys.argv.index("--fixtures") + 1])
    print(f"rendering frames from {fixtures} through the real app:")
    asyncio.run(shoot(fixtures))
    print("\nimage mode is not regenerable here — see --image-help.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
