# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 11: feedback-driven name typer (reads + corrects). Verify, then Cancel."""
import sys, time; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote import text_entry as te
from k2000.definitions import Button

b = connect()
NAME_ROW, NAME_COL = 3, 16
def press(btn, s=0.55): b.press_button(btn); time.sleep(s)
def wheel(n, s=0.55): b.alpha_wheel(n); time.sleep(s)
def charat(col): return b.get_screen_text().split("\n")[NAME_ROW][NAME_COL+col]

def enter_char(col, ch):
    if ch == " ":
        press(Button.Number0)                      # known '0'
        for c in te.chunk_wheel(te.clicks_between("0", " ")): wheel(c)
        return
    if ch.isdigit():
        for _ in range(int(ch) + 1): press(Button.Number0)
        return
    if ch.isalpha():
        button, _ = te._LETTER_TAPS[ch.upper()]
        group = te.PAD_GROUPS[button]
        for _ in range(len(group) + 1):            # cycle until the letter matches
            press(button)
            if charat(col).upper() == ch.upper():
                break
        if charat(col) != ch:                       # fix case
            press(Button.PlusMinus)
        return
    # punctuation: nearest digit/letter anchor already known, then wheel
    anchor = te._nearest_anchor(ch)
    enter_char(col, anchor)
    for c in te.chunk_wheel(te.clicks_between(anchor, ch)): wheel(c)

# Reach the Rename dialog on 205.
press(Button.Program)
for d in (Button.Number2, Button.Number0, Button.Number5): press(d, 0.5)
press(Button.Enter); press(Button.Edit)
b.alpha_wheel(1); time.sleep(0.8); press(Button.Exit); press(Button.SoftC)

target = "Ab 7c"
for i, ch in enumerate(target):
    enter_char(i, ch)
    if i < len(target) - 1: press(Button.CursorRight)

got = b.get_screen_text().split("\n")[NAME_ROW][NAME_COL:NAME_COL+len(target)]
print(f"target {target!r} -> got {got!r}  {'PASS' if got==target else 'FAIL'}")
press(Button.SoftF); press(Button.SoftF)   # name Cancel, save No
b.close()
