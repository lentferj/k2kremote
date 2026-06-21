# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 19: rename program 300 to a k2kremote name and re-save (Replace 300)."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import text_entry, screenshot
from k2kremote.refresh import Frame
from k2000.definitions import Button

b = connect()
def press(btn, s=0.9): b.press_button(btn); time.sleep(s)

press(Button.Program)
for d in (Button.Number3, Button.Number0, Button.Number0): press(d, 0.5)
press(Button.Enter); press(Button.Edit)
b.alpha_wheel(1); time.sleep(0.6); b.alpha_wheel(-1); time.sleep(0.6)   # net-zero, dirty
press(Button.Exit)                       # "Save ... before exiting?"
press(Button.SoftC)                      # Rename -> name dialog
name = "k2kremote demo  "                # 16 chars, overwrites old name fully
text_entry.type_name(b, name, settle=0.5)
field = b.get_screen_text().split("\n")[3][16:32]
print(f"name field: {field!r}")
press(Button.SoftE)                      # OK -> back to save dialog
press(Button.SoftE)                      # Yes -> save-as
text = b.get_screen_text()
print("save-as:", " | ".join(r.rstrip() for r in text.split("\n") if r.strip()))
assert "ID#300" in text, "not ID#300 — aborting"
press(Button.SoftE)                      # Replace ID#300
time.sleep(0.6)

press(Button.Program)
for d in (Button.Number3, Button.Number0, Button.Number0): press(d, 0.5)
press(Button.Enter)
rows = b.get_screen_text().split("\n")
screenshot.save_png(Frame(pixels=b.get_graphics(), text_rows=rows), "probes/prog300_named.png", scale=4)
print("done -> probes/prog300_named.png")
b.close()
