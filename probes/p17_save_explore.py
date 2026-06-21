# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 17: explore the Save flow up to 'Yes' (net-zero edit; stop & inspect)."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import screenshot
from k2kremote.refresh import Frame
from k2000.definitions import Button

b = connect()
def press(btn, s=0.8): b.press_button(btn); time.sleep(s)
def snap(tag):
    rows = b.get_screen_text().split("\n")
    screenshot.save_png(Frame(pixels=b.get_graphics(), text_rows=rows), f"probes/{tag}.png", scale=4)
    print(f"[{tag}] " + " | ".join(r.rstrip() for r in rows if r.strip()))
    return rows

press(Button.Program)
for d in (Button.Number2, Button.Number0, Button.Number5): press(d, 0.5)
press(Button.Enter); press(Button.Edit)
b.alpha_wheel(1); time.sleep(0.7); b.alpha_wheel(-1); time.sleep(0.7)  # net-zero, but dirty
press(Button.Exit)            # save dialog
snap("save_dialog")
press(Button.SoftE)           # 'Yes' -> save-as flow
snap("save_after_yes")
b.close()
print("STOPPED (no final save committed)")
