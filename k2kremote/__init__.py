# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
"""k2kremote — a terminal remote for the Kurzweil K2000 / K2000R.

Phase 1 modules:
  * :mod:`k2kremote.midi_bridge` — portable MIDI transport (StandardPort +
    Jan's split-rig), throttled output, device-id tolerance.
  * :mod:`k2kremote.braille` — 240x64 LCD pixel buffer rendered as 120x16
    Unicode braille.
"""

__version__ = "0.1.0"
