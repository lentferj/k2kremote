# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
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

"""Name what the K2000 is showing, by matching it against the OS ROM's own
message strings.

k2kremote mirrors an 8x40 text grid. The grid says *what* is on the LCD and
nothing about *what it is* -- a prompt, an error, a soft-key row -- so a
mirror can show a dialog perfectly while the program driving it has no idea a
dialog is there. The firmware's own strings close that gap: the ROM carries
the text of every message it can display, including the `%s`/`%3d` format
strings behind the dynamic ones.

**The bulk table is not embedded, deliberately; a curated handful is.** The
ROM's ~7,500 printable runs have no law behind them -- unlike the tables in
`k2kromtables.py`, which ship as a formula plus its exceptions -- so a dump of
them here would be a copy of part of the OS ROM and nothing else. That stays
out: :func:`extract` reads it from an image the user already has.

:data:`STATE_MARKERS` is the exception, and it is a different kind of thing.
Those are the few short functional phrases k2kremote has to recognise to
work at all -- "is the device busy", "is this the prompt that must not be
polled" -- which the project has shipped since its first release, because
the mirror is unsafe without them (see `refresh.py`). They are load-bearing
for interoperability, each one is too short and too functional to carry
authorship on its own, and each is verifiable on the LCD of the machine in
front of you. What is new here is only that they are now *sourced*: picked
from the ROM's own message pool instead of from whatever happened to be on
screen when something last broke.

Typical use::

    table = extract(pathlib.Path.home() / "temp/k2k_fw/k2000_v387j.bin")
    hit = identify("Too many objects to move.", table)
    hit.text        # the ROM string it matched
    hit.addr        # where it lives, so it can be checked in the image

A format string matches the line it produced: ``'%s to bank:'`` identifies
``'Sample to bank:'``, and the wildcard's text comes back in `captures`.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

#: The LCD's text grid. A string longer than a row cannot be a whole line,
#: which is most of what separates display text from the rest of the image.
SCREEN_COLS = 40
SCREEN_ROWS = 8

#: `printf` conversions the firmware actually uses, and what each can match
#: on screen. Ordered longest-first so `%3.3d` is tried before `%d`.
_CONVERSIONS: Sequence[Tuple[str, str]] = (
    (r"%\d+\.\d+s", r".*?"),      # %12.12s -- a padded name
    (r"%\d+\.\d+ld", r"\s*-?\d+"),
    (r"%\d+\.\d+d", r"\s*-?\d+"),
    (r"%\d*ld", r"\s*-?\d+"),
    (r"%\d*d", r"\s*-?\d+"),
    (r"%\d*s", r".*?"),
    (r"%c", r"."),
    (r"%%", r"%"),
)


@dataclass(frozen=True)
class Message:
    """One string the firmware can put on the LCD."""

    addr: int
    text: str
    #: Compiled matcher. For a literal this is the text; for a format string
    #: the conversions become wildcards, so the compiled pattern recognises
    #: the *rendered* line rather than the template.
    pattern: re.Pattern
    #: True when `text` carries at least one `printf` conversion.
    is_format: bool


@dataclass(frozen=True)
class Match:
    """A screen line identified against the ROM."""

    message: Message
    captures: Tuple[str, ...]

    @property
    def addr(self) -> int:
        return self.message.addr

    @property
    def text(self) -> str:
        return self.message.text


def _to_pattern(text: str) -> Tuple[re.Pattern, bool]:
    """Turn one ROM string into a matcher for the line it renders as."""
    out, i, is_format = [], 0, False
    while i < len(text):
        for conv, wildcard in _CONVERSIONS:
            m = re.match(conv, text[i:])
            if m:
                out.append(f"({wildcard})" if wildcard != "%" else "%")
                is_format = is_format or wildcard != "%"
                i += m.end()
                break
        else:
            out.append(re.escape(text[i]))
            i += 1
    return re.compile("".join(out) + r"\s*$"), is_format


def extract(image: "os.PathLike | str", *, base: int = 0x100000,
            min_len: int = 3, data_from: int = 0x188000) -> List[Message]:
    """Read the displayable strings out of a K2000 OS ROM image.

    `base` is where the image maps (0x100000 on v3.87J, so a ROM address is
    the file offset plus that). `data_from` skips the code region: the string
    pool lives above it, and scanning code finds thousands of byte sequences
    that happen to be printable and are not text.

    Only strings that could occupy a screen row are returned -- at most
    `SCREEN_COLS` characters -- which is the cheapest filter that separates
    messages from the version banners, symbol names and tables also living up
    there.
    """
    import pathlib

    blob = pathlib.Path(image).read_bytes()
    out: List[Message] = []
    for m in re.finditer(rb"[\x20-\x7e]{%d,%d}" % (min_len, SCREEN_COLS), blob):
        if m.start() < data_from - base:
            continue
        text = m.group().decode("ascii")
        pattern, is_format = _to_pattern(text)
        out.append(Message(m.start() + base, text, pattern, is_format))
    return out


def identify(line: str, table: Sequence[Message]) -> Optional[Match]:
    """Which ROM message produced this screen line, if any.

    Literals are preferred over format strings, and among format strings the
    most specific (fewest wildcards, longest literal text) wins -- otherwise
    a bare ``'%s'`` would claim every line on the display.
    """
    line = line.rstrip()
    if not line:
        return None
    best: Optional[Tuple[Tuple[int, int, int], Match]] = None
    for msg in table:
        m = msg.pattern.match(line)
        if not m:
            continue
        literal = len(re.sub(r"\(.*?\)", "", msg.pattern.pattern))
        rank = (0 if not msg.is_format else 1, -literal, len(m.groups()))
        cand = Match(msg, tuple(g for g in m.groups() if g is not None))
        if best is None or rank < best[0]:
            best = (rank, cand)
    return None if best is None else best[1]


def identify_screen(rows: Sequence[str],
                    table: Sequence[Message]) -> List[Optional[Match]]:
    """`identify` for a whole mirrored frame -- one result per row."""
    return [identify(row, table) for row in rows[:SCREEN_ROWS]]


def unmatched(rows: Sequence[str],
              table: Sequence[Message]) -> List[Tuple[int, str]]:
    """Screen rows that no ROM string accounts for -- `(row index, text)`.

    The mirror is a free, continuous check on the catalogue, and it runs in
    the one direction that works. Building the message set *from* the screen
    cannot work well: you only ever see what you can trigger, and most of the
    pool is error paths, while a format string is unrecoverable from its
    output -- `Loading program VOX3...` never reveals that the ROM holds
    `Loading program %s...`.

    Checking the other way round costs nothing. Every line the K2000 displays
    should match something in the image it is running, so a line that does
    not is one of two things worth knowing about:

    * a gap in :func:`extract` -- its filter is deliberately loose (3..40
      printable bytes above the code region), which admits byte runs that are
      not text at all, and may equally miss text it should have caught;
    * genuinely dynamic content -- an object name, a user-typed value -- that
      no template covers.

    Neither is an error. The point is that the set shrinks as the machine is
    used, and what is left is evidence rather than a guess.
    """
    return [(i, row.rstrip()) for i, row in enumerate(rows[:SCREEN_ROWS])
            if row.strip() and identify(row, table) is None]


class ScreenState(enum.Enum):
    """What kind of screen the K2000 is showing, as far as polling is concerned.

    Three states, because two were not enough. `refresh.py` carried a
    hand-collected BUSY list containing ``"writing"`` and ``"reading file"``,
    and the ROM shows those substrings land overwhelmingly on *failures* --
    `Failed writing to disk`, `Problem reading file %s, error %d` -- not on
    progress. An error dialog is an idle screen: the device answers normally
    and the mirror should stay fully live on it. Calling it BUSY made the
    worker stop buying the pixel plane and stop reporting timeouts on a
    device that was in no difficulty at all.
    """

    #: Mid-operation, mostly disk I/O. Expect slow answers; nothing is at
    #: risk, so polling continues, just cheaply. Clears by itself.
    BUSY = "busy"
    #: A destructive commit -- the confirm prompt whose next keypress starts
    #: an object rewrite, or the rewrite itself. **All polling pauses here**;
    #: a SysEx read during the rewrite can lock the K2000's CPU up.
    DESTRUCTIVE = "destructive"
    #: A failure the device is reporting. Idle: it is waiting for a keypress,
    #: not working. Classified only so it stops being mistaken for BUSY.
    ERROR = "error"


#: Screen phrases worth recognising, and what each one means, **in order**:
#: the first marker found in the joined screen text decides, so the more
#: dangerous and more specific readings come first.
#:
#: Substrings, matched case-insensitively against the whole frame. Every one
#: occurs in the v3.87J message pool -- `test_k2kmessages.py` holds this table
#: to the ROM image when one is present, which is how ``"scanning"`` left:
#: it was a guess, and the firmware has never contained it.
#:
#: This is the whole of the ROM text k2kremote ships. It is here because the
#: mirror is unsafe without it; see the module docstring on why that is a
#: different question from shipping the pool.
STATE_MARKERS: Sequence[Tuple[ScreenState, str]] = (
    # --- destructive: pause everything -------------------------------------
    # The confirm prompt. Its next keypress commits, so we must be paused
    # *before* it is answered. `Are you sure?` is the general form; the
    # hard-reset and delete-all warnings carry their own wording.
    (ScreenState.DESTRUCTIVE, "are you sure"),
    (ScreenState.DESTRUCTIVE, "hard reset"),
    (ScreenState.DESTRUCTIVE, "delete all ram"),
    # The rewrites themselves -- the exact state a poll can hang the unit in.
    # A delete or a RAM clear started at the front panel never shows us a
    # confirm we recognise, so the operation has to be caught in its own
    # right. `Initializing all memory. Please wait...` is the RAM wipe, and
    # matched only "please wait" before, i.e. it read as BUSY and kept the
    # heartbeat running straight through the wipe.
    (ScreenState.DESTRUCTIVE, "deleting"),
    (ScreenState.DESTRUCTIVE, "initializing all memory"),
    (ScreenState.DESTRUCTIVE, "clearing data"),
    # --- error: idle, stay live --------------------------------------------
    # Ahead of BUSY on purpose: these share their verbs with progress text,
    # and the failure reading is the correct one when both could match.
    (ScreenState.ERROR, "not enough"),
    (ScreenState.ERROR, "failed writing"),
    (ScreenState.ERROR, "problem "),
    (ScreenState.ERROR, "error "),
    (ScreenState.ERROR, "can't "),
    (ScreenState.ERROR, "cannot "),
    (ScreenState.ERROR, "disk is write protected"),
    (ScreenState.ERROR, "disk not inserted"),
    (ScreenState.ERROR, "no room on disk"),
    (ScreenState.ERROR, "too many objects"),
    # --- busy: slow, but fine ----------------------------------------------
    # "please wait" is the most general and the one that actually mattered
    # when this was first needed; the rest are the progress forms the ROM
    # spells out separately.
    (ScreenState.BUSY, "please wait"),
    (ScreenState.BUSY, "opening file"),
    (ScreenState.BUSY, "reading file"),
    (ScreenState.BUSY, "replacing file"),
    (ScreenState.BUSY, "skipping file"),
    (ScreenState.BUSY, "loading"),
    (ScreenState.BUSY, "saving"),
    (ScreenState.BUSY, "writing"),
    (ScreenState.BUSY, "reading"),
    (ScreenState.BUSY, "formatting"),
    (ScreenState.BUSY, "verifying"),
    (ScreenState.BUSY, "checking free space"),
    (ScreenState.BUSY, "initializing"),
    (ScreenState.BUSY, "crossfading"),
    (ScreenState.BUSY, "mixing"),
    (ScreenState.BUSY, "inserting"),
    (ScreenState.BUSY, "inverting data"),
    (ScreenState.BUSY, "reversing data"),
    (ScreenState.BUSY, "volume adjusting"),
    (ScreenState.BUSY, "retrying read"),
    (ScreenState.BUSY, "retrying write"),
    (ScreenState.BUSY, "waiting for keyscanner"),
)


def classify_screen(rows: Sequence[str]) -> Optional[ScreenState]:
    """What kind of screen this is, or `None` for an ordinary one.

    First marker in :data:`STATE_MARKERS` order wins, so DESTRUCTIVE beats
    ERROR beats BUSY on a frame that could be read as more than one. That
    ordering is the safe direction: over-reporting DESTRUCTIVE only freezes
    the mirror until Ctrl+r, while under-reporting it risks a lockup.

    Matching is on the joined frame, not per row, because the K2000 wraps a
    message across rows freely (`Are you sure you want to delete` sits above
    the object it means).
    """
    joined = " ".join(rows).lower()
    for state, marker in STATE_MARKERS:
        if marker in joined:
            return state
    return None
