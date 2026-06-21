# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 2: pull a real GETGRAPHICS frame, render braille + PNG."""
import sys; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import braille, screenshot
from k2kremote.refresh import Frame

b = connect()
px = b.get_graphics()
txt = b.get_screen_text().split("\n")
print("pixels shape:", px.shape, "dtype:", px.dtype, "on-pixels:", int((px != 0).sum()))
print("\n--- BRAILLE (120x16) ---")
print(braille.render(px))
screenshot.save_png(Frame(pixels=px, text_rows=txt), "probes/screen.png", scale=4)
print("\nsaved probes/screen.png")
b.close()
