# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 18c: exact soft-button columns of the save-as dialog."""
import sys; sys.path.insert(0, ".")
from probes.hw import connect
b = connect()
bottom = b.get_screen_text().split("\n")[7]
print("cols:", "".join(str(i % 10) for i in range(40)))
print("row :", bottom)
# 6 soft zones, ~ every 40/6
for i in range(6):
    lo = round(i*40/6); hi = round((i+1)*40/6)
    print(f"  F{i+1} [{lo:2d}:{hi:2d}] = {bottom[lo:hi].strip()!r}")
b.close()
