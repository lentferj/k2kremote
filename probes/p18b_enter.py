# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 18b: confirm ID#300 then identify the Save soft button (don't save yet)."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote.app import soft_labels
from k2000.definitions import Button

b = connect()
b.press_button(Button.Enter); time.sleep(1.0)
rows = b.get_screen_text().split("\n")
print("after Enter:", " | ".join(r.rstrip() for r in rows if r.strip()))
print("soft:", soft_labels(rows))
b.close()
