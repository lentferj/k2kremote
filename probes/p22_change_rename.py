# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 22: can a Program be renamed with one CHANGE (0x08) SysEx?  (WRITES)

This answers the open questions for the whole-name rename path (RESOLUTION_NOTES
§8 / TODO): does CHANGE actually rename a stored Program over SysEx, and is the
object **locked while the editor / name dialog is open** (DNAK code 1 = editing)?

It only ever sends ``newid=0`` (rename only — never relocates/overwrites another
id). It is still a WRITE (it changes a name), so it is user-run, single-session.

Usage:
    .venv/bin/python probes/p22_change_rename.py <program_id> <new name>

Run it three ways to map the lock behaviour, reading the printed result each time:
  1. from **Program mode** (program selected, NOT in the editor)  -> expect OK;
  2. with that program **open in the editor** (Edit pressed)      -> expect DNAK/fail?
  3. sitting in the **Name dialog** itself (Edit > Name)           -> expect DNAK/fail?
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from k2000.definitions import ObjectType  # noqa: E402
from probes.hw import connect  # noqa: E402

if len(sys.argv) < 3:
    sys.exit("usage: p22_change_rename.py <program_id> <new name>")

idno = int(sys.argv[1])
new_name = " ".join(sys.argv[2:])

b = connect()


def current_name(idno):
    try:
        return repr(b.client.dir(ObjectType.Program, idno).name)
    except Exception as exc:  # noqa: BLE001
        return f"<DIR failed: {type(exc).__name__}: {exc}>"


print(f"Program {idno} name before: {current_name(idno)}")
print(f"Sending CHANGE -> {new_name!r} (newid=0, rename only)...")
try:
    confirmed = b.rename(ObjectType.Program, idno, new_name)
    print(f"  CHANGE accepted; INFO.name = {confirmed!r}")
except Exception as exc:  # noqa: BLE001  -- DNAK/timeout tells us the lock story
    print(f"  CHANGE rejected: {type(exc).__name__}: {exc}")

print(f"Program {idno} name after:  {current_name(idno)}")
