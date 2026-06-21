# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 5: reach the Save/name dialog (edit -> dirty -> Exit). Cancel at end."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import screenshot
from k2kremote.refresh import Frame
from k2000.definitions import Button

b = connect()
def press(btn, s=0.9): b.press_button(btn); time.sleep(s)
def snap(tag):
    rows = b.get_screen_text().split("\n")
    px = b.get_graphics()
    screenshot.save_png(Frame(pixels=px, text_rows=rows), f"probes/{tag}.png", scale=4)
    ne = [r.rstrip() for r in rows if r.strip()]
    print(f"[{tag}] " + " | ".join(ne))
    return rows

press(Button.Program)
press(Button.Edit)               # edit currently loaded program
snap("ed_page")
b.alpha_wheel(1); time.sleep(0.9) # make a (benign) change -> dirty flag
press(Button.Exit)               # -> Save dialog
snap("ed_savedialog")
b.close()
print("done — left in Save dialog (no Save/Cancel pressed yet)")
