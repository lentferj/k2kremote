# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# The PRAM container framing (32-byte header, negative-length object blocks,
# hash = type/id, int32 end marker) is the layout documented by the sibling
# mpc2emu project in docs/KRZ_FORMAT.md §2 (GPL-2.0-or-later), itself
# reverse-engineered from hardware-saved banks and KurzFiler.
# The Macro Table semantics (drive / path / bank / load-mode / object list) come
# from the Kurzweil K2vx manual, chapter 13 "Macros" (13-38 … 13-54) and
# "Creating a Startup File" (13-63), cross-checked byte-for-byte against the
# real BOOT.MAC recovered from this project's K2000R disk image
# (see docs/MAC_FORMAT.md).
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

"""Read, edit and write Kurzweil K2000 ``.MAC`` macro files.

A ``.MAC`` file is a :class:`PramFile` (the same container a ``.KRZ`` bank
uses) holding exactly **one** object: the *Macro Table*, object type 100,
id 35, named ``Macro``.  The table is a list of :class:`MacroEntry` records —
one per file the macro loads — terminated by a ``u16 0``.

``BOOT.MAC`` in the root directory of the startup drive is what the K2000
replays at power-on, so this table decides what is resident after boot.

Everything is **big-endian** (68000 platform).

Fidelity
--------
Real macro entries carry a few bytes the firmware never clears — uninitialised
stack/heap left over in the name and path padding.  Parsing keeps those bytes,
and an entry that has not been edited re-serialises **byte-identically**;
:func:`MacroTable.parse` → :func:`MacroTable.serialize` on a hardware-written
file is a bit-exact round trip.  Only entries you actually modify are rebuilt
canonically (padding zeroed).

Unverified
----------
The drive and load-mode codes are decoded as 0-based indices into the value
lists the manual prints for the "Modify Macro Entries" page.  Three independent
checks agree on the real ``BOOT.MAC`` (see ``docs/MAC_FORMAT.md`` §5), but this
has **not** been confirmed against the hardware, and only one real ``.MAC``
file was available to reverse-engineer.  Treat writes accordingly: never
replace a ``BOOT.MAC`` without keeping the previous one.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional

__all__ = [
    "MacroEntry",
    "MacroTable",
    "PramFile",
    "PramObject",
    "MacError",
    "DRIVE_LABELS",
    "MODE_LABELS",
    "BANK_EVERYTHING",
    "MACRO_TYPE",
    "MACRO_ID",
    "MACRO_OBJECT_NAME",
]


class MacError(ValueError):
    """Raised when a buffer is not a well-formed PRAM file or macro table."""


# --- object identity -------------------------------------------------------

#: Object type of a Macro Table.  The K2000 packs ``type``/``id`` into a u16
#: "hash"; for types above 42 the 0x8000 bit is clear and the split is 8/8
#: (mpc2emu's ``_gtype``/``_gid``), so hash 0x6423 = type 100, id 35.  Type 100
#: is the K2000's "Table" type — the Master table is 100/16 (mpc2emu,
#: ``docs/k2000r_midi_comms.md`` §4), the Macro table 100/35, which is exactly
#: the ``Table  35  Macro`` line the manual shows in the Save-Object list.
MACRO_TYPE = 100
MACRO_ID = 35
MACRO_OBJECT_NAME = "Macro"

#: Bank field value meaning "Everything" (the whole object RAM).
BANK_EVERYTHING = 0xFFFF

#: Drive-ID codes, in the order the manual lists the ``Drive`` parameter's
#: values (13-52).  UNVERIFIED against hardware — see the module docstring.
DRIVE_LABELS = {
    0: "Floppy",
    1: "SCSI 0",
    2: "SCSI 1",
    3: "SCSI 2",
    4: "SCSI 3",
    5: "SCSI 4",
    6: "SCSI 5",
    7: "SCSI 6",
    8: "SCSI 7",
    9: "Unspecified",
    10: "Library",
}

#: Load-mode codes, in the order the manual lists the ``Mode`` parameter's
#: values (13-52).  The one-letter codes are what the Macro page displays.
MODE_LABELS = {
    0: ("Append", "A"),
    1: ("Merge", "M"),
    2: ("Fill", "F"),
    3: ("Overwrite", "O"),
    4: ("OvFill", "V"),
}

#: Top bit of an entry's length word: the K2000's **selected** marker, shown as
#: a `*` beside the entry on the Macro page and set for every entry by the Save
#: page's `All` soft key. It is stored in the object, so a table read back after
#: a Select has 0x8000 on each length — which parsed as a 32802-byte entry and
#: failed with "runs past the object data". It is a flag, not corruption.
ENTRY_SELECTED = 0x8000

#: Byte length of the fixed part of an entry, and of the file-name field.
_ENTRY_HEADER = 14
_NAME_FIELD = 16


def _even(n: int) -> int:
    return n + (n & 1)


def _cstr(buf: bytes) -> str:
    """Decode a NUL-terminated field; everything past the NUL is padding."""
    end = buf.find(b"\x00")
    return buf[: end if end >= 0 else len(buf)].decode("latin-1")


# --- macro entry -----------------------------------------------------------


@dataclass
class MacroEntry:
    """One file-load step of a macro.

    ``drive``/``mode`` are raw codes; use :attr:`drive_label` / :attr:`mode_label`
    for the manual's names.  ``bank`` is the load target (0, 100 … 900, or
    :data:`BANK_EVERYTHING`).
    """

    drive: int
    bank: int
    mode: int
    path: str
    filename: str

    #: Fields whose meaning is not established.  They are all zero or leftover
    #: garbage in the one real file we have; kept so unmodified entries
    #: round-trip byte-exactly.
    unknown4: int = 0
    unknown10: int = 0
    unknown12: int = 0
    #: The K2000's own "selected" marker (ENTRY_SELECTED in the length word),
    #: shown as `*` on the Macro page. Carried through so a table read after a
    #: Select re-serialises byte-for-byte instead of quietly losing the marks.
    selected: bool = False
    trailer: int = 0

    #: Bytes past the end of the modelled layout.  A macro entry that carries
    #: an *object list* ("Obj" in the K2000 display) is longer than the layout
    #: below; we have no sample of one, so those bytes are preserved verbatim
    #: rather than guessed at.  See docs/MAC_FORMAT.md §6.
    extra: bytes = b""

    #: Exact bytes this entry was parsed from, or ``None`` if it was built in
    #: code.  Dropped as soon as any modelled field changes.
    _source: Optional[bytes] = field(default=None, repr=False, compare=False)

    # -- presentation ------------------------------------------------------

    @property
    def drive_label(self) -> str:
        return DRIVE_LABELS.get(self.drive, f"drive {self.drive}")

    @property
    def mode_label(self) -> str:
        return MODE_LABELS.get(self.mode, (f"mode {self.mode}", "?"))[0]

    @property
    def mode_letter(self) -> str:
        return MODE_LABELS.get(self.mode, ("", "?"))[1]

    @property
    def bank_label(self) -> str:
        return "E" if self.bank == BANK_EVERYTHING else str(self.bank)

    @property
    def has_object_list(self) -> bool:
        """True when the entry loads only selected objects from the file."""
        return bool(self.extra)

    @property
    def full_path(self) -> str:
        """``\\DIR\\FILE.KRZ`` — the path field already ends in a separator."""
        sep = "" if self.path.endswith("\\") or not self.path else "\\"
        return f"{self.path}{sep}{self.filename}"

    def display(self) -> str:
        """The line the K2000's own Macro page would show for this entry."""
        drive = {0: "F", 9: "U", 10: "L"}.get(self.drive)
        if drive is None:
            drive = str(self.drive - 1) if 1 <= self.drive <= 8 else "?"
        obj = "Obj" if self.has_object_list else ""
        left = f"{drive}:{self.full_path}"
        return f"{left:<30}{self.bank_label}:{self.mode_letter}:{obj}"

    # -- editing -----------------------------------------------------------

    def __setattr__(self, name, value):
        # Any change to a modelled field invalidates the verbatim source, so
        # the entry is re-serialised canonically (with zeroed padding).
        if name != "_source" and getattr(self, "_source", None) is not None:
            if getattr(self, name, object()) != value:
                object.__setattr__(self, "_source", None)
        object.__setattr__(self, name, value)

    # -- codec -------------------------------------------------------------

    @classmethod
    def parse(cls, buf: bytes, offset: int) -> "MacroEntry":
        (word,) = struct.unpack_from(">H", buf, offset)
        selected = bool(word & ENTRY_SELECTED)
        length = word & ~ENTRY_SELECTED
        if length < _ENTRY_HEADER + _NAME_FIELD + 2:
            raise MacError(f"macro entry at {offset} is too short ({length} bytes)")
        if offset + length > len(buf):
            raise MacError(f"macro entry at {offset} runs past the object data")
        raw = bytes(buf[offset : offset + length])

        drive, unknown4, bank, mode, unknown10, unknown12 = struct.unpack_from(
            ">6H", raw, 2
        )
        name = _cstr(raw[_ENTRY_HEADER : _ENTRY_HEADER + _NAME_FIELD])

        rest = raw[_ENTRY_HEADER + _NAME_FIELD :]
        end = rest.find(b"\x00")
        if end < 0:
            raise MacError(f"macro entry at {offset} has an unterminated path")
        path = rest[:end].decode("latin-1")
        tail = rest[_even(end + 1) :]
        trailer = struct.unpack_from(">H", tail)[0] if len(tail) >= 2 else 0

        return cls(
            drive=drive,
            bank=bank,
            mode=mode,
            path=path,
            filename=name,
            unknown4=unknown4,
            unknown10=unknown10,
            unknown12=unknown12,
            trailer=trailer,
            selected=selected,
            extra=bytes(tail[2:]),
            _source=raw,
        )

    def serialize(self) -> bytes:
        if self._source is not None:
            return self._source

        name = self.filename.encode("latin-1")
        if len(name) >= _NAME_FIELD:
            raise MacError(
                f"file name {self.filename!r} does not fit the "
                f"{_NAME_FIELD - 1}-character field"
            )
        path = self.path.encode("latin-1")

        body = (
            name.ljust(_NAME_FIELD, b"\x00")
            + (path + b"\x00").ljust(_even(len(path) + 1), b"\x00")
            + struct.pack(">H", self.trailer)
            + self.extra
        )
        length = _ENTRY_HEADER + len(body)
        return (
            struct.pack(
                ">7H",
                length | (ENTRY_SELECTED if self.selected else 0),
                self.drive,
                self.unknown4,
                self.bank,
                self.mode,
                self.unknown10,
                self.unknown12,
            )
            + body
        )


# --- macro table -----------------------------------------------------------


@dataclass
class MacroTable:
    """The list of entries a macro replays, in order."""

    entries: List[MacroEntry] = field(default_factory=list)

    #: Bytes following the ``u16 0`` terminator inside the object, if any.
    tail: bytes = b""

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __getitem__(self, i):
        return self.entries[i]

    @classmethod
    def parse(cls, data: bytes) -> "MacroTable":
        """Parse the *object body* of a Macro Table object."""
        entries: List[MacroEntry] = []
        pos = 0
        while pos + 2 <= len(data):
            (word,) = struct.unpack_from(">H", data, pos)
            if word == 0:
                return cls(entries=entries, tail=bytes(data[pos + 2 :]))
            # Mask the selected marker here too: the walk advances by the entry
            # length, and 0x8000 in that word made it step 32802 bytes and fall
            # off the end of a perfectly good table.
            length = word & ~ENTRY_SELECTED
            entry = MacroEntry.parse(data, pos)
            entries.append(entry)
            pos += length
        raise MacError("macro table is not terminated")

    def serialize(self) -> bytes:
        return b"".join(e.serialize() for e in self.entries) + b"\x00\x00" + self.tail

    # -- editing helpers ---------------------------------------------------

    def move(self, index: int, delta: int) -> int:
        """Move an entry within the list; returns its new index."""
        target = max(0, min(len(self.entries) - 1, index + delta))
        if target != index:
            self.entries.insert(target, self.entries.pop(index))
        return target

    def rebank(self, bank: int, mode: Optional[int] = None, indices=None) -> None:
        """Set bank (and optionally mode) on selected (default: all) entries.

        This is the K2000's own "rebanking" operation from the Modify Macro
        Entries page.
        """
        for i in range(len(self.entries)) if indices is None else indices:
            self.entries[i].bank = bank
            if mode is not None:
                self.entries[i].mode = mode


# --- PRAM container --------------------------------------------------------


@dataclass
class PramObject:
    """One length-prefixed object block inside a PRAM file."""

    type: int
    idno: int
    name: str
    data: bytes

    @property
    def hash(self) -> int:
        return (
            ((self.type << 10) | self.idno)
            if self.type <= 42
            else ((self.type << 8) | self.idno)
        )

    def serialize(self) -> bytes:
        name = self.name.encode("ascii", errors="replace")[:16]
        # ofs counts from the ofs field to the object data: name + NUL,
        # padded to an even total.
        padded = name + (b"\x00" if len(name) & 1 else b"\x00\x00")
        ofs = len(name) + 3 if len(name) & 1 else len(name) + 4
        body = padded + self.data
        body += b"\x00" * (len(body) & 1)
        size = 4 + len(body) + 2  # hash..object end, from the size field, +2
        block = struct.pack(">HHH", self.hash, size, ofs) + body
        block += b"\x00" * (-(len(block) + 4) % 4)
        return struct.pack(">i", -(len(block) + 4)) + block


@dataclass
class PramFile:
    """A ``PRAM`` object-database dump — a ``.KRZ`` bank or a ``.MAC`` macro."""

    objects: List[PramObject] = field(default_factory=list)
    #: The 24 header bytes after the magic and the ``osize`` field.  The K2000
    #: writes free-RAM figures and its OS version here; preserved verbatim.
    header_rest: bytes = b"\x00" * 24
    #: Everything past the object-section end marker (PCM data in a ``.KRZ``;
    #: empty in a ``.MAC``).
    payload: bytes = b""

    MAGIC = b"PRAM"

    @property
    def software_version(self) -> int:
        """K2000 OS version that wrote the file, ×100 (354 = v3.54)."""
        return struct.unpack_from(">I", self.header_rest, 8)[0]

    @classmethod
    def parse(cls, buf: bytes) -> "PramFile":
        if len(buf) < 32 or buf[:4] != cls.MAGIC:
            raise MacError("not a PRAM file (bad magic)")
        (osize,) = struct.unpack_from(">i", buf, 4)
        objects: List[PramObject] = []
        pos = 32
        while pos + 4 <= len(buf):
            (blocksize,) = struct.unpack_from(">i", buf, pos)
            if blocksize == 0:
                pos += 4
                break
            if blocksize > 0 or pos - blocksize > len(buf):
                raise MacError(f"bad object block size {blocksize} at {pos}")
            block = buf[pos + 4 : pos - blocksize]
            hash_, size, ofs = struct.unpack_from(">HHH", block)
            type_ = (hash_ >> 10) if (hash_ & 0x8000) else (hash_ >> 8)
            idno = (hash_ & 0x3FF) if (hash_ & 0x8000) else (hash_ & 0xFF)
            name = _cstr(block[6 : 4 + ofs])
            # size counts from the size field (block offset 2) and includes 2.
            objects.append(
                PramObject(type_, idno, name, bytes(block[4 + ofs : 2 + size - 2]))
            )
            pos -= blocksize
        else:
            raise MacError("object section is not terminated")
        return cls(
            objects=objects,
            header_rest=bytes(buf[8:32]),
            payload=bytes(buf[osize:]) if 0 < osize <= len(buf) else b"",
        )

    def serialize(self) -> bytes:
        body = b"".join(o.serialize() for o in self.objects) + b"\x00\x00\x00\x00"
        osize = 32 + len(body)
        return (
            self.MAGIC
            + struct.pack(">i", osize)
            + self.header_rest
            + body
            + self.payload
        )

    # -- macro convenience -------------------------------------------------

    def macro_object(self) -> PramObject:
        for obj in self.objects:
            if obj.type == MACRO_TYPE and obj.idno == MACRO_ID:
                return obj
        raise MacError("this PRAM file holds no Macro Table (type 100, id 35)")

    def macro_table(self) -> MacroTable:
        return MacroTable.parse(self.macro_object().data)

    def set_macro_table(self, table: MacroTable) -> None:
        self.macro_object().data = table.serialize()

    @classmethod
    def for_macro(cls, table: MacroTable, *, software_version: int = 354) -> "PramFile":
        """Build a fresh ``.MAC`` file around ``table``."""
        rest = bytearray(24)
        struct.pack_into(">I", rest, 8, software_version)
        return cls(
            objects=[
                PramObject(MACRO_TYPE, MACRO_ID, MACRO_OBJECT_NAME, table.serialize())
            ],
            header_rest=bytes(rest),
        )


# --- file-level helpers ----------------------------------------------------


def read_mac(path) -> PramFile:
    with open(path, "rb") as fh:
        return PramFile.parse(fh.read())


def write_mac(path, pram: PramFile) -> None:
    with open(path, "wb") as fh:
        fh.write(pram.serialize())
