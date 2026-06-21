# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 3: select Program 300, then visit every mode; confirm via the screen."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2000.definitions import Button

b = connect()

def press(btn, settle=0.9):
    b.press_button(btn)
    time.sleep(settle)

def top(label):
    rows = [r.rstrip() for r in b.get_screen_text().split("\n")]
    nonempty = [r for r in rows if r.strip()]
    print(f"{label:12s}: {nonempty[0] if nonempty else '(blank text layer)'}")
    return rows

# Make sure we're in Program mode, then select 300.
press(Button.Program)
for d in (Button.Number3, Button.Number0, Button.Number0):
    press(d, settle=0.5)
press(Button.Enter)
top("Program 300")

for name, btn in [
    ("Setup", Button.Setup), ("QuickAccess", Button.QuickAccess),
    ("Master", Button.Master), ("MIDI", Button.MIDI),
    ("Disk", Button.Disk), ("Song", Button.Song),
    ("Effects", Button.Effects), ("Program", Button.Program),
]:
    press(btn)
    top(name)

b.close()
print("done")
