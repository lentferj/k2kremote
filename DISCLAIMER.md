<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# Disclaimer

## Use at your own risk — back up first

k2kremote talks to vintage hardware over MIDI System Exclusive. It is provided
**as is, with absolutely no warranty and no liability** for data loss, **hardware
damage**, corrupted media, or any other harm arising from its use. **You assume
all risk.**

**During development and testing, the K2000 was occasionally driven into a
hardware lockup that could only be cleared by a *factory reset* of the
instrument** — and a factory reset can erase user data on the unit. The old CPU
can also be destabilised by MIDI traffic while it is busy (e.g. during a SCSI
load/save).

**Before you use this software with real hardware, make complete, current
backups of everything on your K2000** — RAM Programs, Setups, Samples / Keymaps,
Effects, Master / MIDI settings, and any attached SCSI media — so you can restore
after a reset or an unexpected change.

## AI Assistance & Human Authorship

In the interest of transparency: k2kremote was created by its **human author,
Jan Lentfer**, working together with Anthropic's
**Claude**, an AI coding assistant.

**The ideas and the direction are human.** The concept of the tool, the project
vision, every feature (the pixel-accurate LCD mirror, the event-driven refresh,
the feedback-driven name entry, the SysEx rename tool, the render modes, the
safety behaviours), the priorities, and the design decisions all came from the
human author.

**Claude assisted with the execution:**
- writing and refactoring the implementation code (the MIDI bridge, the braille
  / blocks / text renderers, the Textual UI, the refresh scheduler, the name and
  rename logic, the CLI);
- drafting and maintaining the documentation and tests.

**The reverse engineering rests on hands-on human work** — the part no AI can do:
all of the MIDI-protocol behaviour this depends on (the SysEx flood floor, the
device-id quirk, the LCD pixel/text layout, the naming model, the in-editor vs.
dialog-free rename behaviour, the long-name display clipping) was **verified on a
real Kurzweil K2000R**, with the author at the instrument reading the panel and
confirming results. The protocol findings are recorded in the author's sibling
**mpc2emu** project (`docs/k2000r_midi_comms.md`).

In short, the AI accelerated the coding, but the ideas, the hardware reverse
engineering, the testing, and the correctness of the result are the product of
substantial human effort.

## No Warranty

This software is provided **as is**, without warranty of any kind, express or
implied, including but not limited to the warranties of merchantability, fitness
for a particular purpose, and non-infringement.

In no event shall the authors or copyright holders be liable for any claim,
damages, or other liability — including data loss or hardware damage — whether in
an action of contract, tort, or otherwise, arising from, out of, or in connection
with the software or the use or other dealings in the software.

See the [`LICENSE`](LICENSE) file (GPL-2.0-or-later) for the full legal terms.

## Hardware Risk

Driving vintage instruments over MIDI SysEx carries inherent risk. Before and
while using k2kremote with real hardware:

1. **Keep good, current backups** of all RAM objects and SCSI media on the
   K2000, so you can recover from a factory reset or an unintended change.
2. **Be ready to pause.** The K2000's CPU can be overwhelmed by MIDI traffic
   while it is busy. k2kremote auto-pauses around heavy disk operations and you
   can pause manually with `P`; resume with `P` or `Ctrl+R`.
3. **The rename tool writes to the instrument's object database.** It only ever
   *renames* (it never relocates or deletes objects), but it is still a write —
   target the right object id.
4. **Test against a non-critical instrument / backed-up state first.**

The author accepts **no responsibility** for data loss, hardware damage, or any
other adverse effects resulting from the use of this software.

## Tested Environment

Development and testing were done **only on Debian "Bookworm" with the kitty
terminal 0.47.4**, against a real K2000R. The software has **not been tested on
Windows or macOS**, nor on other terminals; those paths may require adjustment.
Compatibility across K2000/K2000R firmware revisions is not guaranteed.

## Trademarks

Kurzweil is a trademark of Young Chang Co. Ltd. All other product names,
trademarks, and registered trademarks mentioned in this project are the property
of their respective owners. Their use here is for identification purposes only
and does not imply endorsement. The author is not affiliated with, endorsed by,
or otherwise connected to Young Chang / Kurzweil.
