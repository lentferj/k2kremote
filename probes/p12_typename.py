# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 12: verify production text_entry.type_name() live, then Cancel."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import text_entry
from k2000.definitions import Button

b = connect()
def press(btn, s=0.55): b.press_button(btn); time.sleep(s)

press(Button.Program)
for d in (Button.Number2, Button.Number0, Button.Number5): press(d, 0.5)
press(Button.Enter); press(Button.Edit)
b.alpha_wheel(1); time.sleep(0.8); press(Button.Exit); press(Button.SoftC)

target = "K2K Hello-1"
text_entry.type_name(b, target, settle=0.5)   # field auto-detected
got = b.get_screen_text().split("\n")[3][16:16+len(target)]
print(f"target {target!r} -> got {got!r}  {'PASS' if got==target else 'FAIL'}")
press(Button.SoftF); press(Button.SoftF)       # name Cancel, save No
b.close()
