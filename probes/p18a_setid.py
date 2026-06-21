# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 18a: in the save-as dialog, retype ID to 300; inspect (don't save)."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote.app import soft_labels
from k2000.definitions import Button

b = connect()
def press(btn, s=0.7): b.press_button(btn); time.sleep(s)
rows = b.get_screen_text().split("\n")
print("now:", " | ".join(r.rstrip() for r in rows if r.strip()))
print("soft:", soft_labels(rows))
for d in (Button.Number3, Button.Number0, Button.Number0): press(d, 0.5)
rows = b.get_screen_text().split("\n")
print("after typing 300:", " | ".join(r.rstrip() for r in rows if r.strip()))
print("soft:", soft_labels(rows))
b.close()
print("STOPPED (not saved)")
