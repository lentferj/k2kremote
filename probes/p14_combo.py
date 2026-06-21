# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 14: verify the Name->end combo (CursorLeft+CursorRight) in the dialog."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2000.definitions import Button

b = connect()
def press(btn, s=0.55): b.press_button(btn); time.sleep(s)
def field(): return b.get_screen_text().split("\n")[3][16:].rstrip()

press(Button.Program)
for d in (Button.Number2, Button.Number0, Button.Number5): press(d, 0.5)
press(Button.Enter); press(Button.Edit)
b.alpha_wheel(1); time.sleep(0.8); press(Button.Exit); press(Button.SoftC)
name0 = field()
print(f"name              : {name0!r} (len {len(name0)})")

b.chord([Button.CursorLeft, Button.CursorRight]); time.sleep(0.8)  # Alt+End
press(Button.Number0)                                              # type at cursor
name1 = field()
print(f"after end-combo +0: {name1!r}")
# Which position changed?
diff = [i for i in range(min(len(name0), len(name1))) if name0[i] != name1[i]]
print(f"changed positions : {diff}  (end-combo works if near the last index)")
press(Button.SoftF); press(Button.SoftF)   # cancel out
b.close()
