# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. The Disk-mode browser flow was mapped on a real K2000R
# (2026-08-18); the panel/screen SysEx it drives is the vendored k2000 library
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

"""Read the K2000's own disk directory by driving its Load browser.

The online counterpart to `k2kmaced`'s file picker, and **not a better one** —
they trade differently:

* the offline picker reads a disk *image*, which is byte-exact, complete and
  instant, but is a snapshot: it can be stale, or be an image of a different
  disk than the one currently in the machine;
* this asks the **running instrument**, so it reflects whatever is on the disk
  right now, including files saved since any image was taken — at the cost of a
  keypress and a screen read per entry.

So the image is the better source whenever it *is* the disk in the machine, and
this is the better source when that cannot be assumed, or when there is no image
to hand at all — which is the normal case with the instrument switched on.

**It never presses `OK`.** `OK` on the Load page *loads the file*, which is a
multi-minute operation and, for a `.KRZ` into a populated bank, a destructive
one. Only `Open` (descend), `Root`, `Parent` and `Cancel` are used, and the
browser is always left via `Cancel`.

Cost: a directory listing is one `CursorDown` plus a screen read per entry, so a
25-entry directory takes roughly ten seconds. That is the price of asking the
instrument rather than a stale copy.

Two traps, both met while mapping this:

* **The alpha wheel does not scroll every browser.** It scrolls the Load
  listing but not the Delete one. `CursorDown` works in both, so that is what
  this uses.
* **The browser opens on whatever `CurrentDisk` points at**, which a previous
  dialog may have repointed — see :mod:`k2kremote.macro_save`. The drive is
  reported alongside the listing rather than assumed.
"""
from __future__ import annotations

import time
from typing import List, NamedTuple, Optional

from k2000.definitions import Button

_SOFT = (Button.SoftA, Button.SoftB, Button.SoftC,
         Button.SoftD, Button.SoftE, Button.SoftF)

#: The browser draws a six-line window in rows 1-6 with the SELECTED entry
#: always on row 3 — rows 1-2 hold the entries above it and 4-6 those below. At
#: the top of a list rows 1-2 are blank; at the bottom, 4-6 are. Reading the
#: whole window and de-duplicating costs nothing and catches both ends.
_SEL_ROW = 3
_WINDOW = (1, 2, 3, 4, 5, 6)
#: Step by four, not six: the step must not exceed the number of *unseen* rows
#: below the selection, or entries would be skipped.
_STEP = 4


class Item(NamedTuple):
    """One directory entry as the K2000 renders it."""

    name: str          #: 8.3 name as shown, e.g. "BOOT     .MAC" or "--FAVS"
    is_dir: bool
    size: str          #: as shown, e.g. ".5K" — informational only

    @property
    def filename(self) -> str:
        """`NAME.EXT` with the K2000's column padding removed."""
        if self.is_dir:
            return self.name.strip()
        stem, _, ext = self.name.partition(".")
        return f"{stem.strip()}.{ext.strip()}" if ext else stem.strip()


class BrowseError(Exception):
    """The panel was not where this expected it."""


def _rows(bridge, tries: int = 5) -> List[str]:
    last = None
    for _ in range(tries):
        try:
            return bridge.get_screen_text().split("\n")
        except Exception as exc:                            # noqa: BLE001
            last = exc
            time.sleep(0.8)
    raise BrowseError(f"the K2000 stopped answering: {last}")


def _soft_index(row: str, label: str) -> Optional[int]:
    at = row.find(label)
    return None if at < 0 else min(5, int(at * 6 / 40))


def _press(bridge, label: str, *, settle: float = 1.2, hops: int = 4) -> None:
    for _ in range(hops):
        row = _rows(bridge)[7]
        i = _soft_index(row, label)
        if i is not None:
            bridge.press_button(_SOFT[i])
            time.sleep(settle)
            return
        j = _soft_index(row, "more>")
        if j is None:
            raise BrowseError(f"no {label!r} here: {row.rstrip()!r}")
        bridge.press_button(_SOFT[j])
        time.sleep(0.5)
    raise BrowseError(f"could not find {label!r}")


def _parse(line: str) -> Optional[Item]:
    """One listing line -> Item, or None when it is not an entry line."""
    # Check the RAW line for the footer: splitting on ":" first turns
    # "Total: 1252K" into "1252K", which then parses as a perfectly plausible
    # file entry named "1252K". Caught by a test, not by reading it.
    if not line.strip() or line.strip().startswith("Total"):
        return None
    body = line.split(":", 1)[-1] if ":" in line else line
    body = body.strip()
    if not body:
        return None
    if body.endswith("(dir)"):
        return Item(body[: -len("(dir)")].strip(), True, "")
    parts = body.rsplit(None, 1)
    if len(parts) == 2 and (parts[1].endswith("K") or parts[1].endswith("M")):
        return Item(parts[0].strip(), False, parts[1])
    return Item(body, False, "")


def header(bridge) -> str:
    return _rows(bridge)[0].rstrip()


def open_browser(bridge) -> str:
    """Enter Disk mode and open the Load browser. Returns its header."""
    if "DiskMode" not in _rows(bridge)[0]:
        bridge.press_button(Button.Disk)
        time.sleep(1.2)
    if "DiskMode" not in _rows(bridge)[0]:
        raise BrowseError("could not reach Disk mode")
    _press(bridge, "Load", settle=1.6)
    if "Dir:" not in _rows(bridge)[0]:
        raise BrowseError(f"expected a listing, got {_rows(bridge)[0].rstrip()!r}")
    return header(bridge)


def close(bridge) -> None:
    """Leave the browser without loading anything."""
    for _ in range(4):
        row = _rows(bridge)[7]
        i = _soft_index(row, "Cancel")
        if i is None:
            return
        bridge.press_button(_SOFT[i])
        time.sleep(1.2)
        if "DiskMode" in _rows(bridge)[0]:
            return


def listing(bridge, limit: int = 400) -> List[Item]:
    """Every entry at the current level.

    Reads the **whole four-line window** each time and then steps four, rather
    than one entry per keypress. That is the difference between a directory
    costing four screen reads and twenty-five: each press pays the ~0.5 s SysEx
    send gap, so stepping one at a time made a 25-entry directory take ~20 s.

    Steps with the alpha wheel, which carries the whole step in ONE message, and
    falls back to `CursorDown` presses if the wheel turns out to move nothing —
    the Load browser takes the wheel but the Delete listing does not, and a
    browser that ignored it would otherwise return just its first window and look
    like a short directory.

    Stops when a full window brings nothing new — the K2000 clamps at the end
    rather than wrapping, so the last window simply repeats.
    """
    items: List[Item] = []
    seen = set()
    stepped_by_wheel = True
    for _ in range(limit):
        rows = _rows(bridge)
        fresh = 0
        for row in (rows[i] for i in _WINDOW):
            item = _parse(row)
            if item is None or item.name in seen:
                continue
            seen.add(item.name)
            items.append(item)
            fresh += 1
        if not fresh:
            if stepped_by_wheel:
                # The wheel moved nothing: this browser does not take it (the
                # Delete listing does not, though the Load one does). Fall back
                # to cursor presses once before concluding the list has ended --
                # otherwise a browser that ignores the wheel silently returns
                # only its first window, which looks like a short directory.
                stepped_by_wheel = False
                _step_by_presses(bridge)
                continue
            break
        if stepped_by_wheel:
            # ONE message for the whole step. Every outgoing SysEx costs the
            # bridge's ~0.5 s send gap, so four presses cost four gaps while a
            # single wheel message of four clicks costs one -- the difference
            # between ~24 s and ~7 s for a 25-entry directory.
            bridge.alpha_wheel(_STEP)
            time.sleep(0.25)
        else:
            _step_by_presses(bridge)
    return items


def _step_by_presses(bridge) -> None:
    for _ in range(_STEP):
        bridge.press_button(Button.CursorDown)
        time.sleep(0.05)          # the bridge's own send gap does the spacing
    time.sleep(0.25)


def select(bridge, name: str, limit: int = 200) -> bool:
    """Put the selection on `name`, from wherever it is. True when found."""
    for _ in range(limit):
        current = _parse(_rows(bridge)[_SEL_ROW])
        if current is not None and current.name == name:
            return True
        bridge.press_button(Button.CursorDown)
        time.sleep(0.32)
    return False


def enter(bridge, name: str) -> str:
    """Descend into directory `name`. Never presses OK."""
    if not select(bridge, name):
        raise BrowseError(f"{name!r} is not in this directory")
    _press(bridge, "Open", settle=1.5)
    return header(bridge)


def parent(bridge) -> str:
    _press(bridge, "Parent", settle=1.4)
    return header(bridge)


def root(bridge) -> str:
    _press(bridge, "Root", settle=1.4)
    return header(bridge)


def current_path(bridge) -> str:
    """The `Dir:` path from the header, as a K2000 path."""
    head = _rows(bridge)[0]
    if "Dir:" not in head:
        return "\\"
    path = head.split("Dir:", 1)[1].split("Sel:")[0].strip()
    return path or "\\"
