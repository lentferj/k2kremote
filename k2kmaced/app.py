# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# Macro semantics from the Kurzweil K2vx manual, chapter 13 ("Macros"); the
# entry line mirrors the layout of the K2000's own Macro page (13-45).
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

"""``k2kmaced`` — the standalone TUI editor for K2000 ``.MAC`` macro files.

A **separate program** from the k2kremote LCD mirror, shipped with it. It never
opens a MIDI port, and that is not caution but arithmetic: on a modern setup the
K2000's disk *is* its SD/CF card, so reaching ``BOOT.MAC`` means the instrument
is switched **off** with its disk in the computer. The mirror needs the opposite.
The two can essentially never be useful at the same moment.

Everything is driven from the TUI, including writing back — start it with no
arguments and open a file from inside:

    k2kmaced                                  # then ctrl+o to pick a file
    k2kmaced BOOT.MAC -o NEW.MAC              # or name one up front
    k2kmaced hd0.img:'\\BOOT.MAC'              # a macro inside an image

Opening ``image:\\member`` implies the image, so entries are checked against it,
the ``f`` browser gets its file list, and ``i`` can write back to where it came
from. An entry whose file is not on that image is flagged ``MISSING`` — the
failure a stale macro actually has ("Not Found" at boot, 13-44).

Keys: ``ctrl+o`` open, ``b``/``B`` bank, ``m`` mode, ``d`` drive, ``e`` type a
path, ``f`` browse the image, ``o`` move an entry to a position, ``a`` add,
``ctrl+↑``/``ctrl+↓`` nudge, ``delete`` remove, ``ctrl+s`` write a new ``.MAC``,
``w`` arm the write gate, ``i`` install back into the image.

Order is not cosmetic: the macro replays top to bottom, so which entry loads
first decides what a later one overwrites. ``o`` takes a destination directly
(entry 4 to position 2 gives 0,1,4,2,3) because saying that with ``ctrl+↑``
costs one keypress per step.

**Writing back into the image is destructive and guarded in layers**, following
the same shape the sibling eosed and s3ked use for their erase operations:

* the **write gate** (``w``) is off at start-up and shown in the header for as
  long as it is on. Opening a different file turns it off again — permission is
  per-file and is not inherited;
* inside the install dialog nothing happens on one keypress: ``i`` arms,
  ``enter`` fires, ``escape`` cancels;
* the destination is **not typed**. It is the image and member the macro was
  opened from, so it cannot be aimed at the wrong file by a typo;
* the write itself only ever overwrites a file that already exists, within the
  clusters it already owns, so the FAT is never written (:mod:`k2kmaced.k2write`);
* ``ctrl+s`` remains the non-destructive path: a new file, never the image.

**You are responsible for having a current backup of the image**, kept somewhere
else. It writes in place, there is no undo, and nothing here makes a backup.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence

from rich.text import Text

from k2kmaced.k2image import DiskImage, ImageError, is_disk_image
from k2kmaced.k2write import (
    ImageWriteError,
    plan_replacement,
    replace_file_in_image,
)
from k2kmaced.macfile import (
    BANK_EVERYTHING,
    DRIVE_LABELS,
    MODE_LABELS,
    MacError,
    MacroEntry,
    MacroTable,
    PramFile,
)
from k2kmaced.cli import load_macro, parse_source

__all__ = ["BANK_VALUES", "cycle", "MacroEditor", "K2kmacedApp", "main"]

#: The bank values the K2000 offers, in the order its Bank parameter scrolls.
BANK_VALUES: List[int] = [b * 100 for b in range(10)] + [BANK_EVERYTHING]

DRIVE_VALUES: List[int] = sorted(DRIVE_LABELS)
MODE_VALUES: List[int] = sorted(MODE_LABELS)


#: Label for the entry that walks out of a directory in the browser.
DIR_UP = ".."

#: How an armed write gate is drawn. Blinking is not decoration: the gate is a
#: state you can forget you left on, and the danger is doing something else for
#: ten minutes and then pressing `i` out of muscle memory.
_ARMED_STYLE = "blink bold red"


def dir_of(full_path: str) -> str:
    """The directory part of ``\\DIR\\FILE.KRZ``, keeping its trailing ``\\``."""
    directory, _, _ = full_path.rpartition("\\")
    return (directory or "") + "\\"


def parent_dir(directory: str) -> Optional[str]:
    """The directory above ``directory``, or ``None`` at the root."""
    parts = [p for p in directory.split("\\") if p]
    if not parts:
        return None
    return "\\" + "".join(p + "\\" for p in parts[:-1])


def path_tree(catalogue: Sequence[str]) -> dict:
    """Directory tree derived from a flat list of full paths.

    ``{directory: {"dirs": [names], "files": [names]}}``, every directory keyed
    with a leading and trailing ``\\``.

    Built from the *paths* rather than by re-walking the image: the catalogue
    already lists every loadable file with its full path, so the structure is
    implied by it and no second read of the disk is needed. The consequence
    worth knowing is that a directory containing nothing loadable does not
    appear — which is right for picking a macro target, and would be wrong if
    this were ever reused as a general file browser.
    """
    tree: dict = {}

    def ensure(directory: str) -> dict:
        return tree.setdefault(directory, {"dirs": set(), "files": []})

    ensure("\\")
    for full in catalogue:
        directory = dir_of(full)
        filename = full.rpartition("\\")[2]
        walk = "\\"
        for part in [p for p in directory.split("\\") if p]:
            ensure(walk)["dirs"].add(part)
            walk += part + "\\"
            ensure(walk)
        if filename:
            ensure(directory)["files"].append(filename)
    return {d: {"dirs": sorted(v["dirs"]), "files": sorted(v["files"])}
            for d, v in tree.items()}


def browse_rows(tree: dict, directory: str) -> List[tuple]:
    """Rows for one directory: ``(label, kind, target)``.

    ``kind`` is ``"up"``, ``"dir"`` or ``"file"``; ``target`` is the directory to
    move to, or the full path to select. Directories sort before files and carry
    a trailing ``\\`` so the two are never confused by eye.
    """
    node = tree.get(directory, {"dirs": [], "files": []})
    rows: List[tuple] = []
    above = parent_dir(directory)
    if above is not None:
        rows.append((DIR_UP, "up", above))
    for name in node["dirs"]:
        rows.append((name + "\\", "dir", directory + name + "\\"))
    for name in node["files"]:
        rows.append((name, "file", directory + name))
    return rows


#: Every binding, as whole blocks. Textual's Footer shows as many as fit and
#: silently drops the rest, which put `w` (write gate) and `i` (install) — the
#: two keys that can change a disk image — off the end of the line where nobody
#: would ever see them. So the legend is folded instead of clipped.
LEGEND_BLOCKS: tuple = (
    "ctrl+o open", "↑↓ select", "b/B bank", "m mode", "d drive", "e path",
    "f browse", "o move to #", "a add", "ctrl+↑↓ nudge", "del remove",
    "ctrl+s write file", "w write gate", "i install to image", "ctrl+c quit",
)

_BAR_SEP = " · "


def wrap_blocks(blocks: Sequence[str], width: int, sep: str = _BAR_SEP) -> str:
    """Pack ``blocks`` into lines no wider than ``width``, joined by ``sep``.

    Breaks happen only *between* blocks, so "ctrl+↑↓ nudge" is never split. The
    mirror has the same function for the same reason; it is duplicated rather
    than shared because k2kmaced deliberately imports nothing from k2kremote —
    twelve lines is a cheaper price than a dependency between two programs that
    are meant to be independent.
    """
    lines: List[str] = []
    current = ""
    for block in blocks:
        candidate = block if not current else current + sep + block
        if width and len(candidate) > width and current:
            lines.append(current)
            current = block
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def cycle(values: Sequence[int], current: int, step: int) -> int:
    """Next/previous value in ``values``, wrapping; unknown ⇒ first value."""
    try:
        index = list(values).index(current)
    except ValueError:
        return values[0]
    return values[(index + step) % len(values)]


class MacroEditor:
    """The editor's model — all of the behaviour, none of the Textual.

    Split out so the editing rules are unit-testable without a terminal.
    """

    def __init__(self, pram: PramFile, source: str, *,
                 missing: Optional[set] = None,
                 catalogue: Optional[Sequence[str]] = None,
                 image_path: Optional[str] = None,
                 member: Optional[str] = None):
        self.pram = pram
        self.table: MacroTable = pram.macro_table()
        self.source = source
        self.missing = missing or set()
        #: Loadable files on the image the macro was checked against, for the
        #: file picker. Empty when no image was given.
        self.catalogue: List[str] = list(catalogue or ())
        #: Where this macro came from, when it came from inside an image. These
        #: are what "install back" targets, and it targets *only* this — never a
        #: path typed in later. A destructive write whose destination is inferred
        #: from what you opened cannot be aimed at the wrong file by a typo.
        self.image_path = image_path
        self.member = member
        self.dirty = False
        self.index = 0

    @property
    def can_install(self) -> bool:
        """True when there is an unambiguous place to write back to."""
        return bool(self.image_path and self.member
                    and not str(self.image_path).lower().endswith(".lzo"))

    def serialize(self) -> bytes:
        """The macro as it would be written, without writing it anywhere."""
        self.pram.set_macro_table(self.table)
        return self.pram.serialize()

    # -- cursor ------------------------------------------------------------

    def clamp(self) -> int:
        self.index = max(0, min(len(self.table) - 1, self.index))
        return self.index

    @property
    def current(self):
        return self.table[self.clamp()] if len(self.table) else None

    # -- edits -------------------------------------------------------------

    def _touch(self) -> None:
        self.dirty = True

    def cycle_bank(self, step: int) -> None:
        if self.current is not None:
            self.current.bank = cycle(BANK_VALUES, self.current.bank, step)
            self._touch()

    def cycle_mode(self, step: int) -> None:
        if self.current is not None:
            self.current.mode = cycle(MODE_VALUES, self.current.mode, step)
            self._touch()

    def cycle_drive(self, step: int) -> None:
        if self.current is not None:
            self.current.drive = cycle(DRIVE_VALUES, self.current.drive, step)
            self._touch()

    def move(self, step: int) -> None:
        if len(self.table) > 1:
            self.index = self.table.move(self.clamp(), step)
            self._touch()

    def move_to(self, position: int) -> int:
        """Move the current entry to ``position``, sliding the rest along.

        Nudging one step at a time is fine for a swap and tedious for "this
        belongs third": six entries can need five keypresses to say one thing.
        This takes the destination directly — entry 4 to position 2 leaves the
        order 0,1,4,2,3 and every number after the insertion point shifts by
        one, which is what the K2000 does with the load order anyway.

        Order *is* meaning here: the macro replays top to bottom, so a file that
        loads into a bank another entry then overwrites depends entirely on which
        came first. Hence a real reorder rather than a display sort.

        ``position`` is clamped to the table, so 99 means "last" and -1 means
        "first" rather than raising. Returns the index actually landed on.
        """
        if len(self.table) < 2:
            return self.clamp()
        entry = self.table.entries.pop(self.clamp())
        target = max(0, min(len(self.table.entries), position))
        self.table.entries.insert(target, entry)
        self.index = target
        self._touch()
        return target

    def delete(self) -> None:
        if len(self.table):
            self.table.entries.pop(self.clamp())
            self.clamp()
            self._touch()

    def rebank_all(self, bank: int) -> None:
        self.table.rebank(bank)
        self._touch()

    def set_full_path(self, text: str) -> None:
        """Repoint the current entry at ``\\DIR\\FILE.KRZ``.

        Accepts ``/`` as a separator and a missing leading ``\\``, since those
        are what a host keyboard produces; everything else is rejected rather
        than silently mangled — a macro entry that names a file the K2000
        cannot find is a "Not Found" at boot.
        """
        entry = self.current
        if entry is None:
            raise MacError("there is no entry to repoint")
        cleaned = text.strip().replace("/", "\\")
        if not cleaned:
            raise MacError("the path is empty")
        if not cleaned.startswith("\\"):
            cleaned = "\\" + cleaned
        directory, _, filename = cleaned.rpartition("\\")
        if not filename:
            raise MacError("the path has no file name")
        if len(filename.encode("latin-1", errors="replace")) > 15:
            raise MacError(f"{filename!r} is longer than the 15-character field")
        entry.path = directory + "\\"
        entry.filename = filename
        self._touch()

    def add(self) -> None:
        """Insert a new entry after the cursor and select it.

        Bank, mode and drive are copied from the entry you were on, since a new
        step usually belongs with its neighbours; the path is a placeholder to
        be replaced with :meth:`set_full_path`.
        """
        template = self.current
        entry = MacroEntry(
            drive=template.drive if template else 1,
            bank=template.bank if template else 0,
            mode=template.mode if template else 2,   # Fill
            path="\\",
            filename="NEW.KRZ",
        )
        at = self.index + 1 if len(self.table) else 0
        self.table.entries.insert(at, entry)
        self.index = at
        self._touch()

    # -- output ------------------------------------------------------------

    def rows(self) -> List[tuple]:
        """One display row per entry, for the table widget."""
        out = []
        for i, entry in enumerate(self.table):
            flag = "MISSING" if entry.full_path.upper() in self.missing else ""
            if not flag and entry.has_object_list:
                flag = "Obj"
            out.append((
                str(i),
                entry.drive_label,
                entry.full_path,
                entry.bank_label,
                entry.mode_label,
                flag,
            ))
        return out

    def save(self, path: str) -> int:
        self.pram.set_macro_table(self.table)
        blob = self.pram.serialize()
        with open(path, "wb") as fh:
            fh.write(blob)
        self.dirty = False
        return len(blob)


#: Extensions a macro entry can name. Ensoniq files are excluded because the
#: manual says they are not supported in macros (13-38).
LOADABLE = (".KRZ", ".MAC", ".AIF", ".WAV")


def scan_image(image_path: str) -> tuple:
    """``(every file path, the loadable ones)`` on an image, upper-cased set first."""
    with DiskImage.open(image_path) as image:
        files = [e.path for e in image.walk() if not e.is_dir]
    present = {p.upper() for p in files}
    catalogue = sorted(p for p in files if p.upper().endswith(LOADABLE))
    return present, catalogue


def missing_files(table: MacroTable, image_path: str) -> set:
    """Paths in ``table`` that are not on the image (upper-cased)."""
    present, _ = scan_image(image_path)
    return {e.full_path.upper() for e in table if e.full_path.upper() not in present}


def build_editor(source: str, image: Optional[str] = None) -> MacroEditor:
    pram, where = load_macro(source)
    # Opening `image.img:\BOOT.MAC` implies the image, so the entries get checked
    # and the browser gets its file list without a second flag. That is also what
    # makes install-back available: the target is where it was opened from.
    from_image, member = parse_source(source)
    if member is not None and not image:
        image = from_image
    missing, catalogue = set(), []
    if image:
        present, catalogue = scan_image(image)
        missing = {e.full_path.upper() for e in pram.macro_table()
                   if e.full_path.upper() not in present}
    return MacroEditor(pram, where, missing=missing, catalogue=catalogue,
                       image_path=from_image if member is not None else None,
                       member=member)


# --- the terminal app ------------------------------------------------------

try:  # Textual is optional here: the model above is useful without it.
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import ModalScreen
    from textual.widgets import DataTable, Header, Input, OptionList, Static
except ImportError:  # pragma: no cover - exercised only without textual
    App = object  # type: ignore
    ComposeResult = object  # type: ignore

    class K2kmacedApp:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError("the macro editor UI needs Textual installed")

else:

    class PickFileScreen(ModalScreen):
        """Browse the image's loadable files by directory and pick one.

        This was a single flat OptionList of every loadable path on the disk,
        which is fine for a handful of files and unusable for a full drive: the
        K2000's own directories carry the organisation, and a flat alphabetical
        list throws exactly that away. So it walks instead — enter descends into
        a directory, `..` comes back out, enter on a file selects it.

        It opens in the directory the current entry already points at, because
        the common edit is "the same folder, a different file".
        """

        BINDINGS = [
            ("escape", "close", "Cancel"),
            ("backspace", "up", "Up a level"),
        ]

        CSS = """
        PickFileScreen { align: center middle; }
        PickFileScreen > Vertical {
            width: 80%; max-height: 80%; border: round $accent;
        }
        PickFileScreen #browsewhere { height: 1; color: $text-muted; }
        """

        def __init__(self, catalogue: Sequence[str], current: str = ""):
            super().__init__()
            self._tree = path_tree(catalogue)
            self.current = current
            # Start where the entry points, when that directory exists on this
            # image; a stale entry (the MISSING flag) falls back to the root
            # rather than opening on nothing.
            wanted = dir_of(current) if current else "\\"
            self.directory = wanted if wanted in self._tree else "\\"
            self.rows: List[tuple] = []

        def compose(self) -> ComposeResult:
            # The widgets are kept as attributes rather than looked up later with
            # query_one. `on_mount` fires before a screen's composed children are
            # necessarily mounted, so querying them there is a race: it worked on
            # Linux, macOS and Windows/3.13 and lost on Windows/3.11, where the
            # whole app died with NoMatches inside Mount. A reference cannot
            # be unmounted out from under itself.
            self._where = Static("", id="browsewhere")
            self._list = OptionList(id="browselist")
            with Vertical():
                yield self._where
                yield self._list

        def on_mount(self) -> None:
            self._show()
            self._list.focus()

        def _show(self) -> None:
            """Redraw for :attr:`directory`, highlighting the current file."""
            self.rows = browse_rows(self._tree, self.directory)
            options = self._list
            options.clear_options()
            options.add_options([label for label, _, _ in self.rows])
            self._where.update(
                f"{self.directory}   (enter opens · backspace up · esc cancels)")
            for i, (_, kind, target) in enumerate(self.rows):
                if kind == "file" and target.upper() == self.current.upper():
                    options.highlighted = i
                    break
            else:
                if self.rows:
                    options.highlighted = 0

        def action_close(self) -> None:
            self.dismiss(None)

        def action_up(self) -> None:
            above = parent_dir(self.directory)
            if above is not None:
                self.directory = above
                self._show()

        def on_option_list_option_selected(self, event) -> None:
            _, kind, target = self.rows[event.option_index]
            if kind == "file":
                self.dismiss(target)
            else:                      # "dir" or "up": both just move
                self.directory = target
                self._show()

    class OpenScreen(ModalScreen):
        """Pick a ``.MAC`` or a disk image from the host filesystem.

        Exists so ``k2kmaced`` starts with no arguments at all. Requiring a path
        on the command line is a poor fit for this program: the file you want is
        on a card you have just plugged in, under a mount point you do not
        remember, and its name is ``BOOT.MAC`` inside a 2 GB image. Browsing to
        it is the natural way to say that; typing it is how you get a typo in the
        one path that later becomes a write target.

        Directories and candidates only — ``.MAC``, ``.img``, ``.img.lzo`` — so
        the list stays readable on a card full of ISOs.
        """

        SUFFIXES = (".mac", ".img", ".img.lzo", ".iso", ".hda")

        BINDINGS = [
            Binding("escape", "cancel", "Cancel"),
            Binding("backspace", "up", "Up"),
        ]

        CSS = """
        OpenScreen { align: center middle; }
        OpenScreen > Vertical {
            width: 90%; max-height: 80%; border: round $accent; background: $surface;
        }
        OpenScreen #openwhere { height: 1; color: $text-muted; }
        """

        def __init__(self, start: Optional[str] = None):
            super().__init__()
            import pathlib
            self.here = pathlib.Path(start or ".").expanduser().resolve()
            self.rows: List[tuple] = []

        def compose(self) -> ComposeResult:
            # References, not query_one — see PickFileScreen.compose.
            self._where = Static("", id="openwhere")
            self._list = OptionList(id="openlist")
            with Vertical():
                yield self._where
                yield self._list

        def on_mount(self) -> None:
            self._show()
            self._list.focus()

        def _candidates(self) -> List[tuple]:
            import pathlib
            rows: List[tuple] = [("..", "dir", str(self.here.parent))]
            try:
                entries = sorted(self.here.iterdir(),
                                 key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                return rows
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir():
                        rows.append((entry.name + "/", "dir", str(entry)))
                    elif entry.name.lower().endswith(self.SUFFIXES):
                        size = entry.stat().st_size
                        rows.append((f"{entry.name}   ({size:,} bytes)",
                                     "file", str(entry)))
                except OSError:
                    continue
            del pathlib
            return rows

        def _show(self) -> None:
            self.rows = self._candidates()
            options = self._list
            options.clear_options()
            options.add_options([label for label, _, _ in self.rows])
            self._where.update(
                f"{self.here}   (enter opens · backspace up · esc cancels)")
            if self.rows:
                options.highlighted = 0

        def action_up(self) -> None:
            self.here = self.here.parent
            self._show()

        def action_cancel(self) -> None:
            self.dismiss(None)

        def on_option_list_option_selected(self, event) -> None:
            import pathlib
            _, kind, target = self.rows[event.option_index]
            if kind == "dir":
                self.here = pathlib.Path(target)
                self._show()
                return
            self.dismiss(target)

    class PickMacroScreen(ModalScreen):
        """Choose which ``.MAC`` to open, when an image holds more than one."""

        BINDINGS = [Binding("escape", "cancel", "Cancel")]

        CSS = """
        PickMacroScreen { align: center middle; }
        PickMacroScreen > OptionList {
            width: 80%; max-height: 60%; border: round $accent; background: $surface;
        }
        """

        def __init__(self, macros: Sequence[str]):
            super().__init__()
            self.macros = list(macros)

        def compose(self) -> ComposeResult:
            self._list = OptionList(*self.macros)
            self._list.border_title = "macro to open (esc cancels)"
            yield self._list

        def on_mount(self) -> None:
            self._list.focus()

        def action_cancel(self) -> None:
            self.dismiss(None)

        def on_option_list_option_selected(self, event) -> None:
            self.dismiss(self.macros[event.option_index])

    class InstallScreen(ModalScreen):
        """Arm-then-fire before writing the macro back into the disk image.

        This is the only destructive thing k2kmaced can do, and it decides
        whether an instrument boots — so it follows the same shape the sibling
        eosed/s3ked use for erase operations rather than inventing a milder one:

        * it is unreachable unless the **write gate** is armed (``w``), which is
          off at start-up and shown in the header the whole time it is on;
        * inside here, a destructive action is never one keypress — ``i`` arms,
          ``enter`` fires, ``escape`` cancels;
        * the target is not typed. It is the image and member the macro was
          *opened* from, so it cannot be aimed at the wrong file by a typo;
        * the plan is shown before arming: which clusters, how much slack, and
          that the FAT is untouched.

        The backup warning is here rather than in a doc because this is the last
        moment at which reading it changes anything.
        """

        BINDINGS = [
            Binding("escape", "cancel", "Cancel"),
            Binding("i", "arm", "Arm", show=False),
            Binding("enter", "fire", "Fire", show=False),
        ]

        CSS = """
        InstallScreen { align: center middle; }
        InstallScreen > Vertical {
            width: 84; height: auto; border: thick $error; background: $surface;
            padding: 1 2;
        }
        InstallScreen .armed { color: $error; text-style: bold; }
        """

        def __init__(self, editor: MacroEditor, plan: Optional[dict],
                     problem: Optional[str] = None):
            super().__init__()
            self.editor = editor
            self.plan = plan
            self.problem = problem
            self.armed = False

        def compose(self) -> ComposeResult:
            self._body = Static(id="installbody")
            with Vertical():
                yield self._body

        def on_mount(self) -> None:
            self._refresh()

        def _refresh(self) -> None:
            editor = self.editor
            lines = [f"Write the macro back into the image, over {editor.member}", ""]
            if self.problem:
                lines += [f"CANNOT: {self.problem}", "", "escape) close"]
                self._body.update("\n".join(lines))
                return
            plan = self.plan or {}
            lines += [
                f"  image    {editor.image_path}",
                f"  target   {plan.get('path')}   "
                f"{plan.get('old_size')} -> {plan.get('new_size')} bytes",
                f"  clusters {plan.get('clusters')}  "
                f"({plan.get('slack')} bytes slack; the FAT is not touched)",
                "",
                "  YOU are responsible for having a good, current backup of this",
                "  image, kept somewhere else. This writes in place, there is no",
                "  undo, and k2kmaced does not make a backup for you.",
                "",
                "  A bad BOOT.MAC is a bad boot. The K2000 offers Cancel for the",
                "  first seconds of a startup load, so it is recoverable at the",
                "  panel — but verify before you commit the image to the machine.",
                "",
            ]
            if self.armed:
                lines.append("ARMED — press Enter to WRITE, Escape to cancel.")
            else:
                lines.append("i) arm     escape) cancel")
            self._body.update("\n".join(lines))

        def action_arm(self) -> None:
            if not self.problem:
                self.armed = True
                self._refresh()

        def action_fire(self) -> None:
            if self.armed and not self.problem:
                self.dismiss(True)

        def action_cancel(self) -> None:
            self.dismiss(False)

    class K2kmacedApp(App):
        """Textual front end for :class:`MacroEditor`."""

        CSS = """
        Screen { layout: vertical; }
        #where  { height: 1; color: $text-muted; }
        #status { height: 1; color: $text; }
        DataTable { height: 1fr; }
        #pathentry { dock: bottom; height: 3; border: round $accent; }
        #moveentry { dock: bottom; height: 3; border: round $accent; }
        #legend { dock: bottom; height: auto; color: $accent; }
        """

        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("b", "bank(1)", "Bank +"),
            ("B", "bank(-1)", "Bank −"),  # Textual names a shifted letter by its case
            ("m", "mode(1)", "Mode"),
            ("d", "drive(1)", "Drive"),
            ("e", "edit_path", "Edit path"),
            ("f", "pick_file", "Pick file"),
            ("a", "add", "Add entry"),
            ("o", "move_to", "Move to #"),
            ("ctrl+up", "shift(-1)", "Move up"),
            ("ctrl+down", "shift(1)", "Move down"),
            ("delete", "remove", "Delete entry"),
            ("ctrl+s", "save", "Save to file"),
            ("ctrl+o", "open", "Open"),
            ("w", "toggle_write", "Write gate"),
            ("i", "install", "Install to image"),
        ]

        COLUMNS = ("#", "Drive", "File", "Bank", "Mode", "")

        def __init__(self, editor: Optional[MacroEditor] = None,
                     output: Optional[str] = None,
                     allow_write: bool = False):
            super().__init__()
            self.editor = editor
            self.output = output
            self.last_status = ""
            #: Whether writing back into the disk image is permitted at all.
            #: Off at start-up, deliberately: the mistake this guards against is
            #: not a wrong keypress in a dialog, it is a keypress made before
            #: realising the image is the instrument's actual disk. `w` arms it,
            #: and the header says so for as long as it is armed — a status line
            #: is too easy to stop reading.
            self.allow_write = allow_write

        # -- layout --------------------------------------------------------

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            yield Static("", id="where")
            yield DataTable(id="entries", cursor_type="row")
            yield Static("", id="status")
            entry = Input(placeholder="\\DIR\\FILE.KRZ", id="pathentry")
            entry.display = False  # shown only while editing a path
            yield entry
            move = Input(placeholder="move to position #", id="moveentry")
            move.display = False
            yield move
            yield Static("", id="legend")

        def on_mount(self) -> None:
            table = self.query_one(DataTable)
            table.add_columns(*self.COLUMNS)
            self.refresh_legend()
            self.refresh_banner()
            self.refresh_rows()
            if self.editor is None:
                # Started with no arguments: the first thing to do is say what to
                # edit, so ask rather than sit there showing an empty table.
                self.call_after_refresh(self.action_open)
            # The legend below lists every key, so this says what is loaded
            # instead of repeating it — including the count that matters most
            # when opening someone else's macro: how many files are missing.
            if self.editor is None:
                self._status("nothing open — ctrl+o to choose a .MAC or an image")
            else:
                missing = len(self.editor.missing)
                self._status(
                    f"{len(self.editor.table)} entries from {self.editor.source}"
                    + (f" — {missing} file(s) MISSING from the image" if missing
                       else ""))

        # -- state ---------------------------------------------------------

        def refresh_rows(self) -> None:
            table = self.query_one(DataTable)
            table.clear()
            if self.editor is None:
                return
            for row in self.editor.rows():
                table.add_row(*row)
            if len(self.editor.table):
                table.move_cursor(row=self.editor.clamp())

        def _status(self, text: str) -> None:
            dirty = self.editor.dirty if self.editor else False
            self.last_status = f"{'* ' if dirty else ''}{text}"
            self.query_one("#status", Static).update(self.last_status)

        def _sync_index(self) -> None:
            self.editor.index = self.query_one(DataTable).cursor_row or 0
            self.editor.clamp()

        def _after_edit(self) -> None:
            entry = self.editor.current
            self.refresh_rows()
            self._status(entry.display().rstrip() if entry else "macro is empty")

        # -- actions -------------------------------------------------------

        def action_bank(self, step: int) -> None:
            if not self._loaded():
                return
            self._sync_index()
            self.editor.cycle_bank(step)
            self._after_edit()

        def action_mode(self, step: int) -> None:
            if not self._loaded():
                return
            self._sync_index()
            self.editor.cycle_mode(step)
            self._after_edit()

        def action_drive(self, step: int) -> None:
            if not self._loaded():
                return
            self._sync_index()
            self.editor.cycle_drive(step)
            self._after_edit()

        def action_shift(self, step: int) -> None:
            if not self._loaded():
                return
            self._sync_index()
            self.editor.move(step)
            self._after_edit()

        def action_remove(self) -> None:
            if not self._loaded():
                return
            self._sync_index()
            self.editor.delete()
            self._after_edit()

        def action_add(self) -> None:
            if not self._loaded():
                return
            self._sync_index()
            self.editor.add()
            self.refresh_rows()
            self._status("new entry — press e to point it at a file")

        # -- path editing ---------------------------------------------------

        def action_edit_path(self) -> None:
            if not self._loaded():
                return
            self._sync_index()
            entry = self.editor.current
            if entry is None:
                self._status("nothing to repoint — press a to add an entry")
                return
            field = self.query_one("#pathentry", Input)
            field.value = entry.full_path
            field.display = True
            field.focus()
            self._status("path: enter to apply, escape to cancel")

        def _close_entry(self, which: str) -> None:
            field = self.query_one(f"#{which}", Input)
            field.display = False
            self.query_one(DataTable).focus()

        def action_move_to(self) -> None:
            """Ask for a destination position for the current entry."""
            if not self._loaded():
                return
            self._sync_index()
            if len(self.editor.table) < 2:
                self._status("nothing to reorder — one entry or fewer")
                return
            field = self.query_one("#moveentry", Input)
            field.value = ""
            field.display = True
            field.focus()
            self._status(f"move entry {self.editor.index} to which position? "
                         f"(0-{len(self.editor.table) - 1}, enter to apply)")

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "moveentry":
                text = event.value.strip()
                if not text.lstrip("-").isdigit():
                    self._status(f"not a position: {text!r}")
                    return
                was = self.editor.index
                landed = self.editor.move_to(int(text))
                self._close_entry("moveentry")
                self._after_edit()
                self._status(f"moved entry {was} to position {landed}"
                             + ("" if landed == int(text) else
                                f" (clamped from {int(text)})"))
                return
            try:
                self.editor.set_full_path(event.value)
            except MacError as exc:
                self._status(f"rejected: {exc}")
                return
            self._close_entry("pathentry")
            self._after_edit()

        def on_key(self, event) -> None:
            # Escape cancels either overlay; Textual routes the key to the
            # focused Input, so the app-level binding never sees it.
            if event.key != "escape":
                return
            for which, message in (("pathentry", "path unchanged"),
                                   ("moveentry", "order unchanged")):
                if self.query_one(f"#{which}", Input).display:
                    self._close_entry(which)
                    self._status(message)
                    event.stop()
                    return

        def action_pick_file(self) -> None:
            if not self._loaded():
                return
            self._sync_index()
            if not self.editor.catalogue:
                self._status("no file list: rerun with --image to pick from a disk")
                return
            if self.editor.current is None:
                self._status("nothing to repoint — press a to add an entry")
                return

            def apply(path: Optional[str]) -> None:
                if path is None:
                    self._status("pick cancelled")
                    return
                try:
                    self.editor.set_full_path(path)
                except MacError as exc:
                    self._status(f"rejected: {exc}")
                    return
                self._after_edit()

            self.push_screen(
                PickFileScreen(self.editor.catalogue, self.editor.current.full_path),
                apply,
            )

        def action_save(self) -> None:
            if not self._loaded():
                return
            if not self.output:
                self._status("no output file: restart with -o NEW.MAC")
                return
            try:
                written = self.editor.save(self.output)
            except (MacError, OSError) as exc:
                self._status(f"save failed: {exc}")
                return
            self._status(f"wrote {self.output} ({written} bytes)")

        # -- opening ---------------------------------------------------------

        def _loaded(self) -> bool:
            """False (and says so) when no macro is open yet.

            The app can now start with nothing loaded, so every action that
            touches the table has to tolerate that. One guard rather than a
            null-object model: an empty MacroEditor would make "no file open" and
            "an open file with no entries" indistinguishable, and those want
            different messages."""
            if self.editor is None:
                self._status("nothing open — ctrl+o to choose a .MAC or an image")
                return False
            return True

        def action_open(self) -> None:
            def chosen(path: Optional[str]) -> None:
                if path is None:
                    if self.editor is None:
                        self._status("nothing open — ctrl+o to choose a file")
                    return
                self._open_path(path)

            self.push_screen(OpenScreen(), chosen)

        def _open_path(self, path: str) -> None:
            """Load a .MAC, or ask which macro when given an image."""
            if not is_disk_image(path):
                self._load(path)
                return
            try:
                with DiskImage.open(path) as image:
                    macros = [e.path for e in image.find(".MAC")]
            except (ImageError, OSError) as exc:
                self._status(f"cannot read {path}: {exc}")
                return
            if not macros:
                self._status(f"{path} holds no .MAC files")
                return
            if len(macros) == 1:
                self._load(f"{path}:{macros[0]}")
                return

            def picked(member: Optional[str]) -> None:
                if member is not None:
                    self._load(f"{path}:{member}")

            self.push_screen(PickMacroScreen(macros), picked)

        def _load(self, source: str) -> None:
            try:
                editor = build_editor(source)
            except (MacError, ImageError, FileNotFoundError, OSError) as exc:
                self._status(f"cannot open: {exc}")
                return
            self.editor = editor
            # A freshly opened macro is never armed: the gate is per-file, so
            # opening a different image cannot inherit permission granted for
            # the previous one.
            self.allow_write = False
            self.refresh_banner()
            self.refresh_rows()
            self._status(f"opened {editor.source} — {len(editor.table)} entries"
                         + ("" if editor.can_install else
                            "  (read-only source: no install target)"))

        # -- writing back into the image ------------------------------------

        def refresh_legend(self) -> None:
            """Fold the key legend to the current width, so none of it is lost."""
            legend = self.query_one("#legend", Static)
            width = max(self.size.width - 1, 20)
            legend.update(wrap_blocks(list(LEGEND_BLOCKS), width))

        def on_resize(self, event) -> None:
            self.refresh_legend()

        def refresh_banner(self) -> None:
            """Redraw the source line, including the write-gate state.

            The gate lives here rather than only in the status line because a
            status line is transient and gets scrolled past by the next message,
            while the gate stays on until it is turned off. eosed makes the same
            call for the same reason: a persistent hazard needs persistent
            display."""
            target = self.output or "(no output set)"
            source = self.editor.source if self.editor else "(nothing open)"
            text = Text(f"{source} → {target}")
            if self.allow_write:
                text.append("   [WRITE GATE ARMED — i installs to the image]",
                            style=_ARMED_STYLE)
            else:
                text.append("   (write gate off; w to arm)", style="dim")
            self.query_one("#where", Static).update(text)

        def action_toggle_write(self) -> None:
            if not self._loaded():
                return
            if not self.editor.can_install:
                self._status("nothing to install into: open a macro from inside "
                             "a raw .img to enable writing back")
                return
            self.allow_write = not self.allow_write
            self.refresh_banner()
            self._status("write gate ARMED — i installs into the image"
                         if self.allow_write else "write gate off")

        def action_install(self) -> None:
            """Write the macro back into the image it was opened from."""
            if not self._loaded():
                return
            if not self.editor.can_install:
                self._status("this macro did not come from a raw .img, so there "
                             "is nowhere unambiguous to write it back to")
                return
            if not self.allow_write:
                self._status("write gate is off — press w to arm it first")
                return

            data = self.editor.serialize()
            plan, problem = None, None
            try:
                plan = plan_replacement(self.editor.image_path,
                                        self.editor.member, len(data))
            except (ImageWriteError, ImageError, FileNotFoundError, OSError) as exc:
                problem = str(exc)

            def done(go: Optional[bool]) -> None:
                if not go:
                    self._status("install cancelled — nothing was written")
                    return
                try:
                    replace_file_in_image(self.editor.image_path,
                                          self.editor.member, data)
                except (ImageWriteError, ImageError, OSError) as exc:
                    self._status(f"install FAILED: {exc}")
                    return
                self.editor.dirty = False
                self._status(f"wrote {len(data)} bytes into {self.editor.member} "
                             f"and read it back to verify")

            self.push_screen(InstallScreen(self.editor, plan, problem), done)


# --- entry point -----------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="k2kmaced",
        description="Edit a Kurzweil K2000 .MAC macro. Never opens a MIDI port. "
                    "Run with no arguments and pick the file in the app.",
    )
    parser.add_argument("source", nargs="?",
                        help="FILE.MAC or IMAGE:\\PATH.MAC (optional — ctrl+o "
                             "opens one from inside the app)")
    parser.add_argument("-o", "--output", help="where ctrl+s writes")
    parser.add_argument("--image", help="check the entries against this image")
    parser.add_argument("--allow-write", action="store_true",
                        help="start with the write gate already armed; off by "
                             "default, because writing back edits the disk image "
                             "in place")
    args = parser.parse_args(argv)

    editor = None
    if args.source:
        try:
            editor = build_editor(args.source, args.image)
        except (MacError, ImageError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if args.output and parse_source(args.output)[1] is not None:
        print("error: the output must be a plain file, not a path in an image",
              file=sys.stderr)
        return 1

    K2kmacedApp(editor, args.output, allow_write=args.allow_write).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
