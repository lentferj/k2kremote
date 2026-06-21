# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 1: read the LCD text layer; check the &0x7F reverse-video masking."""
import sys; sys.path.insert(0,".");from probes.hw import connect

b = connect()
print("connected:", b.description)
raw = b.client.get_screen_text(2.5)          # psobot, UNMASKED
masked = b.get_screen_text()                 # our bridge, masked &0x7F
hi = sorted({ord(c) for c in raw if ord(c) > 127})
print("\n--- RAW (psobot, unmasked) ---")
print(repr(raw))
print("\n--- MASKED (k2kremote &0x7F) ---")
print(masked)
print("\nhigh-bit code points present in raw:", [hex(h) for h in hi])
b.close()
