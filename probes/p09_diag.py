# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 9: decode name-dialog button behaviour one press at a time."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2000.definitions import Button

b = connect()
def press(btn, s=0.7): b.press_button(btn); time.sleep(s)
def field():
    return b.get_screen_text().split("\n")[3][16:].rstrip()

# Re-reach the Rename name dialog on program 205.
press(Button.Program)
for d in (Button.Number2, Button.Number0, Button.Number5): press(d, 0.5)
press(Button.Enter); press(Button.Edit)
b.alpha_wheel(1); time.sleep(0.8)
press(Button.Exit)            # save dialog
press(Button.SoftC)           # Rename -> name dialog
print(f"{'start':14s}: {field()!r}")

trace = [("Number1",Button.Number1),("Number1",Button.Number1),("Number1",Button.Number1),
         ("CursorRight",Button.CursorRight),("Number2",Button.Number2),
         ("Clear",Button.Clear),("PlusMinus",Button.PlusMinus),("Number1",Button.Number1)]
for label, btn in trace:
    press(btn)
    print(f"{label:14s}: {field()!r}")

# Back out without saving.
press(Button.SoftF); press(Button.SoftF)
b.close()
