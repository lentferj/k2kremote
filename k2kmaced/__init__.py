# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

"""k2kmaced — a standalone editor for Kurzweil K2000 ``.MAC`` macro files.

Shipped in the same repository as the k2kremote LCD mirror, and deliberately a
**separate program**: the two can essentially never be useful at the same time.
The mirror needs the instrument switched on and answering MIDI, while editing
``BOOT.MAC`` means the instrument is switched **off** and its disk is in the
computer — on a modern setup (ZuluSCSI, SCSI2SD, CF adapter) the K2000's disk
*is* the card, so reaching the macro requires taking it out.

Same repo rather than its own, because they share the K2000 domain and a future
online macro editor — reading and writing the live Macro Table over MIDI — would
need both halves at once.

    k2kmaced            # the TUI; everything is driven from it
    k2kmacli --help     # the scriptable command-line companion
"""

__all__ = ["__doc__"]
