#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Regenerate the README screenshots of the MAC editor.

    .venv/bin/python docs/make_k2kmaced_screenshots.py


Deliberately built against a **synthetic** disk image with neutral file names,
not the project's real K2000 backup: a screenshot is a tracked file, and the real
image's directories are commercial library and preset names that must not land in
the repository. A synthetic image also makes the shots reproducible by anyone.
"""
import asyncio
import pathlib
import shutil
import sys
import tempfile

from _shot import svg_to_png

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_k2image import build_image                       # noqa: E402
from k2kmaced.app import K2kmacedApp, build_editor  # noqa: E402

OUT = REPO / "docs" / "img"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="k2k-shots-"))

# Neutral names, but a realistic shape: several directories, a few files each,
# so the browser has something to walk and the flat-list problem is visible.
TREE = {
    "": {"BOOT.MAC": (REPO / "tests/fixtures/BOOT.MAC").read_bytes(),
         "STARTUP.KRZ": b"\x00" * 8},
    "DRUMKITS": {"KIT-ACOU.KRZ": b"\x00" * 8,
                 "KIT-BRUSH.KRZ": b"\x00" * 8,
                 "KIT-ELEC.KRZ": b"\x00" * 8},
    "BASSES": {"BASS-FING.KRZ": b"\x00" * 8,
               "BASS-UPR.KRZ": b"\x00" * 8},
    "PADS": {"PAD-GLASS.KRZ": b"\x00" * 8,
             "PAD-STRNG.KRZ": b"\x00" * 8},
    "SAMPLES": {"TAKE-01.WAV": b"\x00" * 8},
}


def _tidy(editor):
    """Point the entries at the synthetic image so nothing reads MISSING, and
    give the banks the shape a real startup macro has."""
    targets = ["\\STARTUP.KRZ", "\\DRUMKITS\\KIT-ACOU.KRZ",
               "\\BASSES\\BASS-FING.KRZ", "\\PADS\\PAD-GLASS.KRZ",
               "\\PADS\\PAD-STRNG.KRZ", "\\SAMPLES\\TAKE-01.WAV"]
    for i, target in enumerate(targets[:len(editor.table)]):
        editor.index = i
        editor.set_full_path(target)
        editor.table[i].bank = i * 100
    editor.index = 0
    editor.dirty = False
    return editor


def _fresh_tmp():
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    image = build_image(TMP / "hd0.img", TREE)
    shutil.copy(REPO / "tests/fixtures/BOOT.MAC", TMP / "BOOT.MAC")
    import os
    os.chdir(TMP)
    return image


def prepare_from_image():
    """An editor opened from *inside* the image, so `i` has a target.

    The install dialog is unreachable otherwise — by design: the write target is
    wherever the macro was opened from, never a path typed in later."""
    _fresh_tmp()
    return _tidy(build_editor("hd0.img:\\BOOT.MAC"))


def prepare():
    _fresh_tmp()
    editor = build_editor("BOOT.MAC", "hd0.img")
    return _tidy(editor)


async def shoot():
    OUT.mkdir(parents=True, exist_ok=True)
    size = (112, 22)

    # 1. the entry table
    app = K2kmacedApp(prepare(), "NEW.MAC")
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.save_screenshot(str(OUT / "k2kmaced_entries.svg"))

    # 2. the browser, at the root of the image
    app = K2kmacedApp(prepare(), "NEW.MAC")
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        app.save_screenshot(str(OUT / "k2kmaced_browse_root.svg"))

    # 3. the browser, inside a directory (walked into, not searched for)
    app = K2kmacedApp(prepare(), "NEW.MAC")
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("down", "enter")      # into DRUMKITS\
        await pilot.pause()
        app.save_screenshot(str(OUT / "k2kmaced_browse_dir.svg"))

    # 4. the reorder prompt
    app = K2kmacedApp(prepare(), "NEW.MAC")
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.press("down", "down", "down", "down")   # entry 4
        await pilot.press("o")
        await pilot.pause()
        app.save_screenshot(str(OUT / "k2kmaced_move_to.svg"))

    # 5. the write gate armed + the install dialog: the safeguard, which is the
    #    part a reader most needs to recognise before they meet it.
    app = K2kmacedApp(prepare_from_image(), None)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.press("w")          # arm the gate (header turns red)
        await pilot.press("i")          # open the install dialog
        await pilot.pause()
        await pilot.press("i")          # arm the write itself
        await pilot.pause()
        app.save_screenshot(str(OUT / "k2kmaced_install.svg"))

    # PNG, for the same reason as the mirror shots: the install dialog's border
    # is drawn with block glyphs, and the k2kmaced tables use box-drawing.
    print("rasterising to PNG (see docs/_shot.py):")
    for svg in sorted(OUT.glob("k2kmaced_*.svg")):
        svg_to_png(svg)
    for png in sorted(OUT.glob("k2kmaced_*.png")):
        print(f"  {png.relative_to(REPO)}  {png.stat().st_size:,} bytes")


if __name__ == "__main__":
    asyncio.run(shoot())
