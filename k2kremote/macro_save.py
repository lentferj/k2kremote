# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. The Disk-mode flow was mapped on a real K2000R (2026-08-18);
# the panel/screen SysEx it drives is the vendored k2000 library
# (psobot/k2000, MIT, Peter Sobot).
#
# k2kremote is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# k2kremote is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Make the K2000 save its own macro table to disk, by driving the panel.

**This is the only part of the online macro editor that touches a disk**, so it
is the part with real safeguards. Everything else lives in battery-backed RAM and
is undone by a power cycle; a save is not.

There is no SysEx route: the protocol addresses the object database and the
panel, and has no message that writes a file, names a file, or triggers a Save
(K2vx Musician's Guide ch. 30). So this drives the Disk pages, and every step is
checked against what the instrument actually shows.

Four hazards, all met on hardware while mapping this flow:

* **`CurrentDisk` moves under you.** Browsing in the filename dialog's `Choose`
  browser repoints it and *leaves it repointed* — a later save then goes to that
  drive while the confirm prompt shows only `(Path = \\)`. The path is displayed;
  **the drive is not**. A save landed on the floppy that way. So the drive is read
  back over SysEx and must match what the caller asked for.
* **Soft-key positions are not stable.** `SoftD` is `Macro` on one label page and
  `Util` on another. Every key here is found by its **label**.
* **The filename field arrives pre-filled** with a content-derived default (it
  offered `WAVSTFAV` for one macro and `ORG_E1` for another). Pressing `OK`
  straight through saves under a plausible but unintended name, so the name is
  always cleared and retyped.
* **The device goes silent during the write** (~10 s), which is normal and not a
  disconnection — see RESOLUTION_NOTES §17.
"""
from __future__ import annotations

import time
from typing import List, Optional

from k2000.definitions import Button
from k2kremote import text_entry

#: Soft keys, left to right.
_SOFT = (Button.SoftA, Button.SoftB, Button.SoftC,
         Button.SoftD, Button.SoftE, Button.SoftF)

#: How long to wait for the disk write before giving up on the screen coming
#: back. Measured at ~10 s for a small macro on a ZuluSCSI.
WRITE_TIMEOUT = 45.0


class SaveRefused(Exception):
    """Nothing was written, and the panel was left where it was found."""


class SaveUnverified(Exception):
    """The flow ran but the result could not be confirmed."""


class SaveNeedsOverwrite(Exception):
    """The name is taken. Nothing was written; the K2000 was answered No.

    Carries the stem so the caller can offer the overwrite without making the
    user retype it.
    """

    def __init__(self, stem: str):
        super().__init__(f"{stem}.MAC already exists on the K2000's disk")
        self.stem = stem


def _rows(bridge, tries: int = 5) -> List[str]:
    """The screen, retrying a short/absent reply.

    ch. 30: `ALLTEXT` returns 320 bytes, and "if you receive less than that, then
    the screen was in the middle of redrawing and you should request the display
    again". The device is also simply silent during disk work.
    """
    last = None
    for _ in range(tries):
        try:
            return bridge.get_screen_text().split("\n")
        except Exception as exc:                            # noqa: BLE001
            last = exc
            time.sleep(1.0)
    raise SaveUnverified(f"the K2000 stopped answering: {last}")


def _soft_index(label_row: str, label: str) -> Optional[int]:
    """Which soft key carries `label`, by the zone its text falls in."""
    at = label_row.find(label)
    return None if at < 0 else min(5, int(at * 6 / 40))


def _press_labelled(bridge, label: str, *, settle: float = 1.3,
                    hops: int = 4) -> None:
    """Press the soft key showing `label`, cycling label pages to find it.

    Raises rather than guessing: pressing a position that happened to hold the
    right label a moment ago is how a save ends up somewhere else entirely.
    """
    for _ in range(hops):
        row = _rows(bridge)[7]
        i = _soft_index(row, label)
        if i is not None:
            bridge.press_button(_SOFT[i])
            time.sleep(settle)
            return
        j = _soft_index(row, "more>")
        if j is None:
            raise SaveRefused(f"no {label!r} soft key here: {row.rstrip()!r}")
        bridge.press_button(_SOFT[j])
        time.sleep(0.6)
    raise SaveRefused(f"could not find a {label!r} soft key")


def current_disk(bridge) -> Optional[str]:
    """The Disk page's `CurrentDisk`, straight from the device.

    Read over SysEx 0x17/0x16 rather than scraped, and rather than counted: the
    cursor is walked until the *instrument* names the field.
    """
    for _ in range(8):
        name = bridge.client.get_current_parameter_name().strip().rstrip(":")
        value = bridge.client.get_current_parameter_value().strip()
        if name == "CurrentDisk":
            return value
        bridge.press_button(Button.CursorDown)
        time.sleep(0.35)
    return None


def save_macro(bridge, filename: str, *, expect_drive: str = "SCSI 0",
               name_width: int = 12, overwrite: bool = False) -> str:
    """Save the live macro table to `filename` on the current disk.

    Returns the final screen's first row. Raises :class:`SaveRefused` before
    anything is written when the state is not what the caller expects.

    `filename` is the 8.3 stem without the extension — the K2000 appends `.MAC`.

    **The K2000 guards overwrites itself.** If the name is taken it asks
    `Replace existing file X.MAC?` — a genuine safety net nobody here had to
    build. This answers **No** unless `overwrite=True`, and raises rather than
    replacing a file the caller did not say it meant to replace. Answering it at
    all matters: the prompt blocks the save, so leaving it unanswered hangs until
    the timeout with the question still on screen.
    """
    # A save name is a FILENAME STEM, not a path. Strip the separators a person
    # naturally types -- "\BOOT" is an obvious way to mean BOOT -- and refuse
    # anything still carrying one. Left in, the backslash is not typeable on the
    # K2000's pad, so it was silently mapped to the nearest character that is and
    # "\BOOT" arrived as "BBOOT".
    stem = filename.strip().strip("\\/").upper()
    if not stem or len(stem) > 8:
        raise SaveRefused(
            f"{filename!r} is not a FAT 8.3 stem: give 1 to 8 characters and no "
            f"extension (the K2000 adds .MAC itself)"
        )
    if "." in stem or "\\" in stem or "/" in stem:
        raise SaveRefused(
            f"{filename!r} is not a plain file name: no directories and no "
            f"extension — the macro is saved into the current directory as "
            f"{stem.split('.')[0].split(chr(92))[-1]}.MAC"
        )
    if not text_entry.is_supported(stem):
        raise SaveRefused(f"{stem!r} contains characters the K2000 cannot type")

    # 1. The drive, before anything else. This is the check that a save landing
    #    on the floppy would have needed.
    from k2kremote import disk_browse
    if not disk_browse.ensure_disk_mode(bridge):
        raise SaveRefused(
            f"could not reach Disk mode; the panel shows "
            f"{_rows(bridge)[0].rstrip()!r}"
        )
    drive = current_disk(bridge)
    if drive is None:
        raise SaveRefused("could not read CurrentDisk from the device")
    if drive != expect_drive:
        raise SaveRefused(
            f"CurrentDisk is {drive!r}, not {expect_drive!r} — refusing to save. "
            f"Browsing in a file dialog repoints this and leaves it repointed, "
            f"and the save prompt shows the path but never the drive."
        )

    # 2. Disk -> Save -> Macro -> All lands on the filename editor.
    _press_labelled(bridge, "Save")
    _press_labelled(bridge, "Macro")
    _press_labelled(bridge, "All", settle=1.4)

    row = _rows(bridge)[3]
    if "Save as:" not in row:
        raise SaveRefused(f"expected the filename editor, got {row.rstrip()!r}")

    # 3. Clear the pre-filled default and type ours, then read it back.
    #    Delete removes the character to the RIGHT, so the first one can only be
    #    overwritten -- a delete-until-empty loop would never end.
    text_entry.home_cursor(bridge, width=name_width)
    for _ in range(name_width):
        current = _rows(bridge)[3].split("Save as:")[-1].strip()
        if len(current) <= 1:
            break
        i = _soft_index(_rows(bridge)[7], "Delete")
        if i is None:
            break
        bridge.press_button(_SOFT[i])
        time.sleep(0.45)
    text_entry.home_cursor(bridge, width=name_width)
    text_entry.type_name(bridge, stem, name_row=3, name_col=16, start_col=0)

    shown = _rows(bridge)[3].split("Save as:")[-1].strip()
    if shown.upper() != stem:
        raise SaveRefused(
            f"the field reads {shown!r}, not {stem!r} — nothing was written"
        )

    # 4. Commit: name -> OK, then the directory prompt -> OK.
    _press_labelled(bridge, "OK", settle=1.6)
    row = " ".join(_rows(bridge))
    if "current directory" not in row:
        raise SaveUnverified(f"expected the directory prompt, got {row[:80]!r}")
    if stem not in row.upper():
        raise SaveRefused(
            f"the prompt names a different file than {stem!r}: {row[:80]!r}"
        )
    _press_labelled(bridge, "OK", settle=2.5)

    # 5. The instrument's own overwrite guard, then the write. It goes silent
    #    while writing, which is normal.
    deadline = time.monotonic() + WRITE_TIMEOUT
    while time.monotonic() < deadline:
        try:
            rows = bridge.get_screen_text().split("\n")
        except Exception:                                   # noqa: BLE001
            time.sleep(1.5)
            continue
        text = " ".join(rows)
        if "eplace existing" in text:
            answer = "Yes" if overwrite else "No"
            i = _soft_index(rows[7], answer)
            if i is None:
                raise SaveUnverified(
                    f"the K2000 asks {rows[3].strip()!r} but offers no {answer!r}"
                )
            bridge.press_button(_SOFT[i])
            time.sleep(2.0)
            if not overwrite:
                # The instrument told us the name is taken -- which is how we
                # find out, since nothing here lists the directory first. Say so
                # in a way the caller can act on rather than as a flat failure.
                raise SaveNeedsOverwrite(stem)
            continue
        if "DiskMode" in rows[0]:
            return rows[0].rstrip()
        time.sleep(1.0)
    raise SaveUnverified("the K2000 did not return to Disk mode after the write")
