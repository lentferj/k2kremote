# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 21: how is the name-edit cursor encoded? (read-only)

Navigate the K2000 to a Program rename / name dialog FIRST (so the underscore
cursor is on screen), then run this. It reads ALLTEXT (raw, high bits intact)
and GETGRAPHICS several times and reports:

  * which ALLTEXT cells have bit 7 set (our 'reverse-video / cursor' assumption);
  * where GETGRAPHICS has lit pixels in the *bottom* row of each text cell (an
    underscore lives there) — and whether that changes between reads (a blink).

No writes, no presses — safe to run while a name dialog is open.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from probes.hw import connect
from k2kremote import braille

READS = 5
COLS, ROWS, CW, CH = 40, 8, 6, 8

b = connect()


def raw_text():
    """Raw ALLTEXT string with the high bit still present."""
    return b.client.get_screen_text()


def hi_bits(raw):
    """Per-row list of column indices whose byte has bit 7 set."""
    out = []
    for line in raw.split("\n"):
        out.append([c for c, ch in enumerate(line) if ord(ch) & 0x80])
    return out


def bottom_lit(pixels):
    """Per text-cell, count lit pixels in the cell's BOTTOM pixel row (underscore)."""
    arr = braille._fit(braille._normalize(pixels))  # (64, 240) bool
    grid = []
    for r in range(ROWS):
        y = r * CH + (CH - 1)
        row = [int(arr[y, c * CW:(c + 1) * CW].sum()) for c in range(COLS)]
        grid.append(row)
    return grid


prev_pixels = None
for n in range(READS):
    raw = raw_text()
    ascii_rows = [("".join(chr(ord(ch) & 0x7F) for ch in line)).replace("\x00", " ")
                  for line in raw.split("\n")]
    hb = hi_bits(raw)
    pixels = b.get_graphics()
    bl = bottom_lit(pixels)

    print(f"\n===== read {n + 1}/{READS} =====")
    for r in range(min(ROWS, len(ascii_rows))):
        print(f"  row{r}: |{ascii_rows[r][:40]:40}|")
        if hb[r]:
            caret = "".join("^" if c in hb[r] else " " for c in range(40))
            print(f"        |{caret}|  <- ALLTEXT high bit (cols {hb[r]})")
        # bottom-row underscores (cells with >=4 of 6 px lit in their last row)
        under = [c for c in range(40) if bl[r][c] >= 4]
        if under:
            mark = "".join("_" if c in under else " " for c in range(40))
            print(f"        |{mark}|  <- GETGRAPHICS underscore row (cols {under})")

    if prev_pixels is not None:
        diff = int((np.asarray(pixels) != np.asarray(prev_pixels)).sum())
        print(f"  GETGRAPHICS pixels changed vs previous read: {diff} (blink? if it toggles)")
    prev_pixels = pixels
    time.sleep(0.6)

any_hi = any(hi_bits(raw_text()))
print("\nSUMMARY:")
print(f"  ALLTEXT high bit seen anywhere: {bool(any_hi)}")
print("  -> If high bits appear ONLY on the soft-label row (row 7) and not on the")
print("     edited name row, the cursor is NOT in ALLTEXT bit 7. If the underscore")
print("     row toggles between reads, the hardware cursor BLINKS.")
b.close()
