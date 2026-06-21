# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 6: map the dialog's soft-button labels to F1-F6 zones (no presses)."""
import sys; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote.app import soft_labels

b = connect()
rows = b.get_screen_text().split("\n")
bottom = rows[-1]
print("bottom row:", repr(bottom))
print("cols      :", "".join(str(i % 10) for i in range(len(bottom))))
print("soft_labels ->", soft_labels(rows))
print("top        :", rows[0].rstrip())
b.close()
