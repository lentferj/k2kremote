# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 4: enter the Program Editor on prog 300; capture screen + soft labels."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import screenshot
from k2kremote.refresh import Frame
from k2000.definitions import Button

b = connect()
def press(btn, s=0.9): b.press_button(btn); time.sleep(s)

press(Button.Program)
for d in (Button.Number3, Button.Number0, Button.Number0): press(d, 0.5)
press(Button.Enter)
press(Button.Edit)           # enter Program Editor

rows = b.get_screen_text().split("\n")
hi = sorted({ord(c) for r in (b.client.get_screen_text(2.5),) for c in r if ord(c) > 127})
px = b.get_graphics()
screenshot.save_png(Frame(pixels=px, text_rows=rows), "probes/editor.png", scale=4)
print("soft labels (bottom text row):", repr(rows[-1]))
print("all text rows:")
for r in rows: print("   ", repr(r.rstrip()))
print("high-bit code points on editor page:", [hex(h) for h in hi])
press(Button.Exit)           # leave editor (clean, no change made)
b.close()
print("saved probes/editor.png")
