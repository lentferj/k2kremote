# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 18d: commit Save to ID#300, then verify program 300 exists."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import screenshot
from k2kremote.refresh import Frame
from k2000.definitions import Button

b = connect()
def press(btn, s=0.9): b.press_button(btn); time.sleep(s)

text = b.get_screen_text()
print("pre-save:", " | ".join(r.rstrip() for r in text.split("\n") if r.strip()))
assert "ID#300" in text, "NOT on ID#300 screen — aborting"

press(Button.SoftE)            # Save -> commits program 300
time.sleep(0.6)
print("after save:", " | ".join(r.rstrip() for r in b.get_screen_text().split("\n") if r.strip()))

press(Button.Program)
for d in (Button.Number3, Button.Number0, Button.Number0): press(d, 0.5)
press(Button.Enter)
rows = b.get_screen_text().split("\n")
screenshot.save_png(Frame(pixels=b.get_graphics(), text_rows=rows), "probes/prog300.png", scale=4)
print("select 300:", rows[0].rstrip(), "(see probes/prog300.png)")
b.close()
