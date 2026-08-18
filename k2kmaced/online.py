# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. The Macro Table object's identity (type 100, id 35, name
# "Macro") comes from the K2vx Musician's Guide ch. 30 object model plus the
# `.MAC` container's own header; SysEx transport uses the vendored k2000 library
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

"""Read, compare and replace the K2000's **live** macro table over MIDI.

`read_live` and `diff` are read-only. **`push` writes** — it replaces the macro
table object in the instrument's battery-backed RAM, and then reads it back and
refuses to report success unless the bytes match.

**Nothing here touches a disk.** The K2000 saves the table itself, from its own
Disk → Save page, and it can save under **any filename** — so the safe order is
push, save as e.g. `TEST.MAC`, try it with Disk → Load, and only make it the
startup macro once it works. A working `BOOT.MAC` never has to be overwritten.

The macro list the K2000 replays at power-on lives in battery-backed RAM as
object **type 100, id 35, name "Macro"**. Type 100 is the *Table* type and holds
several unrelated objects — id 16 is `Master`, and reading the wrong id returns a
few hundred bytes of something that is not a macro at all and does not announce
itself as such.

**The RAM layout and the disk layout are identical** (verified 2026-08-17 against
a live instrument: the 814-byte RAM object is byte-for-byte the `.MAC` file's
object block at offset 48, and `MacroTable.parse` round-trips it unchanged). So
the offline parser reads the live table with no separate code path — which is why
this module is thin, and why it should stay thin.

Why bother, when `k2kmaced` already edits `BOOT.MAC` offline: because the two
answer different questions. Editing `BOOT.MAC` means the instrument is switched
off with its disk in the computer. This reads what a *running* machine actually
has, which is the only way to answer "is the macro in RAM the same as the
`BOOT.MAC` on the card?" — the two drift whenever someone records a macro from
the panel and does not save it, or saves it somewhere else.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from k2kmaced.macfile import MacError, MacroEntry, MacroTable

#: The live table's object identity. Not a guess: `macfile.MACRO_TYPE` /
#: `MACRO_ID` carry the same values, taken from the `.MAC` container's own
#: object header, and a live read at that id returns an object named "Macro".
MACRO_TYPE = 100
MACRO_ID = 35


def read_live(bridge, timeout: Optional[float] = None) -> MacroTable:
    """The instrument's current macro table.

    Raises :class:`MacError` with the byte count when the reply does not parse,
    rather than letting a struct error surface — a short or empty object means
    something specific (no macro recorded) and deserves to say so.
    """
    data = bridge.read_macro_table(timeout) if timeout is not None \
        else bridge.read_macro_table()
    if not data:
        raise MacError(
            "the K2000 returned an empty Macro Table object — nothing has been "
            "recorded into it (Disk → Macro shows an empty list)"
        )
    try:
        return MacroTable.parse(data)
    except Exception as exc:
        raise MacError(
            f"the live Macro Table ({len(data)} bytes) did not parse as a macro: "
            f"{exc}. Reading object type {MACRO_TYPE} at the wrong id returns "
            f"unrelated Table objects that look superficially plausible, so check "
            f"the id is {MACRO_ID} before suspecting the parser."
        ) from exc


@dataclass(frozen=True)
class DiffRow:
    """One position, as it appears live and in the file."""

    index: int
    live: Optional[str]
    other: Optional[str]

    @property
    def same(self) -> bool:
        return self.live == self.other

    def format(self, width: int = 34) -> str:
        mark = "  " if self.same else "!!"
        left = self.live if self.live is not None else "—"
        right = self.other if self.other is not None else "—"
        return f"{mark} {self.index:>2}  {left:<{width}} {right}"


def diff(live: Sequence[MacroEntry], other: Sequence[MacroEntry]) -> List[DiffRow]:
    """Compare two macro tables position by position.

    Compares the **rendered** entry — drive, path, bank, mode, and the `Obj`
    marker — because that is what the instrument acts on and what a person can
    check against the panel.

    Rendered rather than byte-wise for a reason, and the reason is narrower than
    "bytes are noisy". Entries can carry bytes past the modelled layout
    (`MacroEntry.extra`), and most of those are unknown padding — but *not all of
    them are cosmetic*: `extra` is also where a **selected-object list** lives,
    which makes the entry load particular objects instead of the whole file.
    `display()` marks that with `Obj`, so it shows up here as a difference, which
    is correct: two entries naming the same file with and without an object list
    do not load the same thing.

    A byte compare would additionally flag unknown padding, which is noise. A
    field compare that ignored `extra` would miss the object list, which is not.

    Lengths may differ, so both sides are padded with None rather than zipped —
    zip() would silently drop the tail, which is precisely where an appended
    entry lives.
    """
    rows = []
    for i in range(max(len(live), len(other))):
        a = live[i].display() if i < len(live) else None
        b = other[i].display() if i < len(other) else None
        rows.append(DiffRow(i, a, b))
    return rows


class PushRefused(MacError):
    """The write did not happen, and nothing was sent."""


class PushUnverified(MacError):
    """The write was sent but the read-back does not match. State is UNKNOWN."""


def push(bridge, table: MacroTable, *, backup_path=None, allow_empty=False):
    """Replace the instrument's live macro table, then prove it took.

    Returns the read-back :class:`MacroTable`. Raises :class:`PushRefused` before
    sending anything if the request looks wrong, and :class:`PushUnverified` if the
    object that comes back is not the one that went out.

    The verification is the point. `WRITE` deletes the existing object and
    allocates a new one, so a partial or mis-encoded write leaves the machine's
    boot behaviour altered in a way nothing announces — the macro page would render
    whatever landed there as though it were intended. `DACK` alone is not evidence:
    it says the message was accepted, not that the bytes are right.

    Note that this touches **RAM only**, and the instrument can save the table to
    disk under **any filename** — it does not have to be `BOOT.MAC`. So the safe
    workflow is: push, save as e.g. `TEST.MAC`, try it with Disk → Load, and only
    then make it the startup macro. Nothing in this path requires overwriting a
    working `BOOT.MAC`.

    An empty table is refused by default, because writing one is indistinguishable
    from a bug that produced no entries, and the result — a boot macro that loads
    nothing — looks like the instrument forgot its configuration.
    """
    payload = table.serialize()
    if not table.entries and not allow_empty:
        raise PushRefused(
            "refusing to write an empty macro table: the instrument would boot "
            "loading nothing, which is indistinguishable from this tool having a "
            "bug. Pass allow_empty=True if that is genuinely what you want."
        )

    # Keep what is there now, before replacing it. Cheap, and the only way back if
    # the new table turns out to be wrong in a way that is hard to retype.
    previous = bridge.read_macro_table()
    if backup_path is not None:
        with open(backup_path, "wb") as fh:
            fh.write(previous)

    reply = bridge.write_macro_table(payload)
    code = getattr(getattr(reply, "code", None), "name", None)
    if code is not None:
        raise PushUnverified(
            f"the K2000 rejected the write: DNAK {code}. The previous table should "
            f"be untouched, but read it back to be sure."
        )

    after = bridge.read_macro_table()
    if after != payload:
        raise PushUnverified(
            f"wrote {len(payload)} bytes but read back {len(after)} that differ — "
            f"the live macro table is now in an UNKNOWN state and must not be "
            f"saved to disk. "
            + (f"The previous contents are in {backup_path}." if backup_path
               else "No backup was taken.")
        )
    return MacroTable.parse(after)


def summarise(rows: Sequence[DiffRow]) -> str:
    """One line: identical, or how many positions differ."""
    bad = [r for r in rows if not r.same]
    if not bad:
        return f"identical — {len(rows)} entries match"
    return (f"{len(bad)} of {len(rows)} position(s) differ "
            f"(first at index {bad[0].index})")
