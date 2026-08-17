# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

"""Shared helper for the screenshot generators: rasterise an exported SVG.

Every committed screenshot in this project is a **PNG**, which is the call the
sibling eosed made and the reason is worth stating once, here, rather than in each
generator:

Textual exports SVG whose glyphs are drawn in a font declared *by name* — a CDN
``@font-face`` for Fira Code with a ``local()`` fallback. These pictures are made
of glyphs that ordinary fonts do not all have: braille U+28xx for the braille
mirror, quadrant and half blocks for the block modes and the dialog borders. On a
machine without Fira Code, and there is no reason to assume one, the viewer falls
back — and no single common monospace font covers both ranges, so half the picture
becomes tofu. It is not hypothetical: it is what a Markdown editor showed of the
first SVG versions of these files, and GitHub sandboxes SVG so it cannot fetch the
font either.

Rasterising here resolves the glyphs at generation time, on a machine that has the
fonts. What is committed is then what is seen, everywhere, offline.

Headless Chrome does the rasterising because it performs per-glyph font fallback
the way a terminal does — a plain SVG rasteriser tends to give up on the whole run
instead — and because eosed uses it, so both projects fail identically if it is
ever absent.
"""

import pathlib
import re
import shutil
import subprocess


def svg_to_png(svg: pathlib.Path, *, keep_svg: bool = False) -> str:
    """Render ``svg`` beside itself as PNG and remove it. Returns the extension.

    The SVG Textual writes carries no ``width``/``height``, only a ``viewBox``, so
    the pixel size comes from there.
    """
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if chrome is None:
        print(f"  ! {svg.name}: no chrome found; leaving the SVG, which will "
              f"misrender wherever Fira Code is absent")
        return "svg"
    box = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg.read_text())
    if box is None:
        print(f"  ! {svg.name}: no viewBox; leaving the SVG")
        return "svg"
    width, height = int(float(box.group(1))), int(float(box.group(2)))
    png = svg.with_suffix(".png")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                    "--hide-scrollbars", f"--window-size={width},{height}",
                    f"--screenshot={png}", svg.as_uri()],
                   check=True, capture_output=True, timeout=180)
    if not keep_svg:
        svg.unlink()
    return "png"
