# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared connect() for hardware probes (real K2000R)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from k2kremote.midi_bridge import MidiBridge

def connect(device_id=0):
    # Auto-probe every port for the K2000 (matches ScreenReply, so a MIDI-thru
    # echo of the request isn't mistaken for the device — robust on any rig).
    return MidiBridge.autodetect(device_id=device_id)
