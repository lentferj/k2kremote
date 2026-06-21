# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 7: open the Rename name dialog (SoftC) and capture its layout."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import screenshot
from k2kremote.refresh import Frame
from k2000.definitions import Button

b = connect()
b.press_button(Button.SoftC); time.sleep(1.0)   # Rename
rows = b.get_screen_text().split("\n")
screenshot.save_png(Frame(pixels=b.get_graphics(), text_rows=rows), "probes/name_dialog.png", scale=4)
for i, r in enumerate(rows):
    print(f"row{i}: {r.rstrip()!r}")
b.close()
