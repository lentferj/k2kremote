# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 15: does the dedicated combo code CursorLeftRight (0x1A) jump to end?"""
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
name0 = field(); print(f"name: {name0!r} (len {len(name0)})")

press(Button.CursorLeftRight)     # 0x1A — documented 'move to end of name'
press(Button.Number0)
name1 = field()
diff = [i for i in range(max(len(name0), len(name1))) if (name0+' '*9)[i] != (name1+' '*9)[i]]
print(f"after 0x1A + '0': {name1!r}  changed at {diff}")
print("MOVE-TO-END works" if diff and diff[0] >= len(name0)-1 else "did NOT jump to end")
press(Button.SoftF); press(Button.SoftF)
b.close()
