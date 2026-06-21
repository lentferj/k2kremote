# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe: does this K2000 answer to device 0 and/or broadcast 127?"""
import sys
sys.path.insert(0, ".")
from probes.hw import connect

for dev in (0, 127):
    b = connect(device_id=dev)
    try:
        txt = b.get_screen_text()
        first = txt.split("\n")[0].strip()
        print(f"device {dev:3d}: OK  -> {first!r}")
    except TimeoutError:
        print(f"device {dev:3d}: TIMEOUT")
    finally:
        b.close()
