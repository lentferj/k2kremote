# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 16: does the K2000 echo our injected PANEL presses? (feedback-loop risk)"""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2000.definitions import Button

b = connect()
# Drain any stale inbound first.
for _ in range(5):
    b.poll_panel(); time.sleep(0.1)

print("sending an injected press (CursorRight) and watching for an echo...")
b.press_button(Button.CursorRight)
echoed = False
t = time.time()
while time.time() - t < 1.5:
    if b.poll_panel():
        echoed = True
        break
    time.sleep(0.1)
print("INJECTED PRESS ECHOED BACK (feedback-loop risk!)" if echoed
      else "no echo of injected presses (good — XMIT Buttons off, or external not echoed)")
b.close()
