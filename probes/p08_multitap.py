# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 8: verify plan_name() multi-tap in the live Rename dialog, then Cancel."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import text_entry
from k2000.definitions import Button

b = connect()
def do(cmd):
    kind, payload = cmd
    if kind == "press": b.press_button(payload)
    else: b.alpha_wheel(payload)
    time.sleep(0.6)

target = "Ab3"
plan = text_entry.plan_name(target)
print(f"applying plan_name({target!r}): {len(plan)} steps")
for c in plan: do(c)

row3 = b.get_screen_text().split("\n")[3]
got = row3[16:16+len(target)]
print(f"name field now: {row3.rstrip()!r}")
print(f"typed cols 16..: {got!r}  (expected {target!r})  -> {'PASS' if got==target else 'FAIL'}")

# Back out without saving: name-dialog Cancel (SoftF) -> save dialog No (SoftF).
b.press_button(Button.SoftF); time.sleep(1.0)
b.press_button(Button.SoftF); time.sleep(1.0)
print("backed out (no save); screen:", b.get_screen_text().split("\n")[0].rstrip())
b.close()
