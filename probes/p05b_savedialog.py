# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 5b: select existing prog 205, edit, dirty, Exit -> Save dialog."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import screenshot
from k2kremote.refresh import Frame
from k2000.definitions import Button

b = connect()
def press(btn, s=0.9): b.press_button(btn); time.sleep(s)
def snap(tag):
    rows = b.get_screen_text().split("\n")
    screenshot.save_png(Frame(pixels=b.get_graphics(), text_rows=rows), f"probes/{tag}.png", scale=4)
    print(f"[{tag}] " + " | ".join(r.rstrip() for r in rows if r.strip()))

press(Button.Program)
for d in (Button.Number2, Button.Number0, Button.Number5): press(d, 0.5)
press(Button.Enter)
snap("sd_prog205")
press(Button.Edit)
snap("sd_editor")
b.alpha_wheel(1); time.sleep(0.9)
press(Button.Exit)
snap("sd_dialog")
b.close()
