# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# The K2000 SCSI volume is a FAT16 filesystem (OEM name "KMSI"); the layout
# follows the public FAT specification, and matches the on-disk geometry the
# sibling mpc2emu project emits in writers/fat16.py (GPL-2.0-or-later) — this
# is the read direction mpc2emu does not have.
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

"""Read-only access to K2000 hard-disk images, so macros can be edited offline.

A K2000 SCSI volume is FAT16 with no partition table — the image *starts* with
the boot sector, whose OEM field reads ``KMSI``.  This module walks it and
hands out file bytes; **it never writes to the image.**  That is deliberate: you
open an image to *read* ``BOOT.MAC`` (and to check that the files a macro
references still exist), edit the macro in memory, and save it as a separate
``.MAC`` file.

Writing back is possible but lives in :mod:`k2kmaced.k2write`, deliberately not
here — it overwrites one existing file in place and never touches the FAT, and
keeping it in a separate module is what stops that narrow capability leaking
into the reader every other tool depends on.

``.lzo``-compressed images (what this project's backups are) are supported by
decompressing to a temporary file first, which needs disk space for the full
image — use :meth:`DiskImage.open` as a context manager so it is cleaned up.

Note that the K2000's own SCSI format is described in the manual as "close to
DOS, but not DOS"; a volume the K2000 formatted itself may differ from a
PC-formatted one.  Both images this was developed against are plain FAT16.

**The OEM string (``self.oem``) is read and kept, but never checked.**
:meth:`DiskImage.__init__` only validates the structural boot-sector fields
(bytes/sector, sectors/cluster, FAT count, FAT size, root-entry count) — so
this opens any FAT16-structured volume regardless of what its OEM field says,
``KMSI`` included.  Worth knowing before assuming "not plain FAT16" from the
OEM string alone and reaching for a manual disk browse instead (mpc2emu did
exactly that against a real K2000 hard-disk image on 2026-08-22, before
finding this class opened it directly).
"""

from __future__ import annotations

import atexit
import os
import shutil
import struct
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from typing import BinaryIO, Iterator, List, Optional

__all__ = ["DiskImage", "DirEntry", "ImageError", "is_disk_image"]

_ATTR_DIRECTORY = 0x10
_ATTR_LFN = 0x0F
_ATTR_VOLUME_ID = 0x08


class ImageError(ValueError):
    """Raised when an image is not a readable FAT16 volume."""


@dataclass(frozen=True)
class DirEntry:
    """One file or directory in the image."""

    path: str  #: full DOS path, e.g. ``\\--FAVS\\KPOWFAV.KRZ``
    size: int
    cluster: int
    is_dir: bool

    @property
    def name(self) -> str:
        return self.path.rsplit("\\", 1)[-1]

    @property
    def directory(self) -> str:
        head = self.path.rsplit("\\", 1)[0]
        return head + "\\" if head else "\\"


def is_disk_image(path) -> bool:
    """Cheap sniff: does this look like a raw or ``.lzo`` K2000 volume?"""
    return str(path).lower().endswith((".img", ".img.lzo", ".iso", ".hda"))


class _LzoDecompressionCache:
    """Keeps the most recently decompressed ``.lzo`` image around.

    Opening one image costs three decompressions in the editor today: the
    "which .MAC is on here?" scan, :func:`~k2kmaced.cli.load_macro` reading the
    member, and :func:`~k2kmaced.app.scan_image` listing the files to check the
    entries against.  On a 2 GB backup that is three multi-minute runs of
    ``lzop -dc`` for one keypress.  They all decompress the *same* bytes, so
    remember the temp file and hand it out again.

    Keyed by path, mtime and size, so editing the ``.lzo`` on disk invalidates
    it.  The file outlives the last :meth:`DiskImage.close` on purpose -- that
    is what makes the second and third open free -- and is dropped when a
    *different* image is decompressed with nothing still reading this one, or
    at exit.  Only one image is kept: these are gigabytes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: Optional[tuple] = None
        self._tmp: Optional[str] = None
        self._users = 0

    @staticmethod
    def _key_for(path: str) -> tuple:
        st = os.stat(path)
        return (os.path.abspath(path), st.st_mtime_ns, st.st_size)

    def acquire(self, path: str) -> str:
        key = self._key_for(path)
        with self._lock:
            if self._key == key and self._tmp is not None:
                self._users += 1
                return self._tmp
            if self._users:
                # Something is still reading the old image; leave it alone and
                # let its own release() clean it up.
                self._key = self._tmp = None
                self._users = 0
            else:
                self._discard_locked()
        tmp = self._decompress(path)
        with self._lock:
            if self._tmp is None:
                self._key, self._tmp, self._users = key, tmp, 1
                return tmp
        # Another thread won the race and cached its own copy; ours is a
        # duplicate, but it is already on disk and valid, so hand it out
        # uncached rather than decompressing a fourth time.
        return tmp

    def release(self, tmp: str) -> None:
        with self._lock:
            if tmp == self._tmp:
                self._users = max(0, self._users - 1)
                return  # kept for the next open
        _unlink_quiet(tmp)

    def clear(self, *, force: bool = False) -> None:
        """Drop the cached copy.  ``force`` at exit: nothing will read it now."""
        with self._lock:
            if self._users and not force:
                return
            self._discard_locked()

    def _discard_locked(self) -> None:
        if self._tmp:
            _unlink_quiet(self._tmp)
        self._key = self._tmp = None
        self._users = 0

    @staticmethod
    def _decompress(path: str) -> str:
        for tool in ("lzop", "dd"):
            if shutil.which(tool) is None:
                raise ImageError(
                    f"{os.path.basename(path)} is lzop-compressed but "
                    f"'{tool}' is not installed; decompress it first"
                )
        tmp = tempfile.NamedTemporaryFile(prefix="k2image-", suffix=".img", delete=False)
        try:
            with subprocess.Popen(
                ["lzop", "-dc", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ) as proc:
                # dd's sparse mode keeps the unused half of a 2 GB image off disk.
                subprocess.run(
                    ["dd", f"of={tmp.name}", "bs=1M", "conv=sparse", "status=none"],
                    stdin=proc.stdout,
                    check=True,
                )
                stderr = proc.stderr.read() if proc.stderr else b""
                if proc.wait() != 0:
                    # Say what lzop said: "not a lzop file" and "no space left"
                    # are the same silent failure without it.
                    detail = stderr.decode("utf-8", "replace").strip()
                    raise ImageError(
                        f"lzop failed to decompress {path}"
                        + (f": {detail}" if detail else "")
                    )
        except Exception:
            tmp.close()
            _unlink_quiet(tmp.name)
            raise
        tmp.close()
        return tmp.name


def _unlink_quiet(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


_LZO_CACHE = _LzoDecompressionCache()
# A gigabyte of temp file must not survive the process just because an image was
# left open; at exit nobody can still be reading it.
atexit.register(lambda: _LZO_CACHE.clear(force=True))


class DiskImage:
    """A FAT16 volume opened read-only."""

    def __init__(self, fh: BinaryIO, *, _cleanup: Optional[str] = None):
        self._fh = fh
        self._cleanup = _cleanup
        boot = self._read_at(0, 512)
        if len(boot) < 512:
            raise ImageError("image is too small to hold a boot sector")
        self.oem = boot[3:11].decode("latin-1").strip()
        (self.bytes_per_sector,) = struct.unpack_from("<H", boot, 0x0B)
        self.sectors_per_cluster = boot[0x0D]
        (self.reserved_sectors,) = struct.unpack_from("<H", boot, 0x0E)
        self.num_fats = boot[0x10]
        (self.root_entries,) = struct.unpack_from("<H", boot, 0x11)
        (self.fat_sectors,) = struct.unpack_from("<H", boot, 0x16)
        if not (
            self.bytes_per_sector in (512, 1024, 2048, 4096)
            and self.sectors_per_cluster
            and self.num_fats
            and self.fat_sectors
            and self.root_entries
        ):
            raise ImageError(
                "not a FAT16 volume (no partition table is expected; the image "
                "must start with the boot sector)"
            )
        self._root_sector = self.reserved_sectors + self.num_fats * self.fat_sectors
        root_bytes = self.root_entries * 32
        self._data_sector = self._root_sector + (
            (root_bytes + self.bytes_per_sector - 1) // self.bytes_per_sector
        )
        self._fat = self._read_at(
            self.reserved_sectors * self.bytes_per_sector,
            self.fat_sectors * self.bytes_per_sector,
        )

    # -- construction ------------------------------------------------------

    @classmethod
    def open(cls, path) -> "DiskImage":
        """Open a raw or ``.lzo`` image.  Use as a context manager."""
        path = str(path)
        if path.lower().endswith(".lzo"):
            return cls._open_lzo(path)
        return cls(open(path, "rb"))

    @classmethod
    def _open_lzo(cls, path: str) -> "DiskImage":
        tmp = _LZO_CACHE.acquire(path)
        try:
            return cls(open(tmp, "rb"), _cleanup=tmp)
        except Exception:
            _LZO_CACHE.release(tmp)
            raise

    def close(self) -> None:
        self._fh.close()
        if self._cleanup:
            _LZO_CACHE.release(self._cleanup)
            self._cleanup = None

    def __enter__(self) -> "DiskImage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- FAT internals -----------------------------------------------------

    def _read_at(self, offset: int, length: int) -> bytes:
        self._fh.seek(offset)
        return self._fh.read(length)

    @property
    def cluster_size(self) -> int:
        return self.sectors_per_cluster * self.bytes_per_sector

    def _cluster_offset(self, cluster: int) -> int:
        return (
            self._data_sector + (cluster - 2) * self.sectors_per_cluster
        ) * self.bytes_per_sector

    def _chain(self, cluster: int) -> Iterator[int]:
        seen = set()
        while 2 <= cluster < 0xFFF0:
            if cluster in seen:
                raise ImageError(f"cluster chain loops at {cluster}")
            seen.add(cluster)
            yield cluster
            (cluster,) = struct.unpack_from("<H", self._fat, cluster * 2)

    def _read_chain(self, cluster: int, size: Optional[int] = None) -> bytes:
        out = bytearray()
        for clus in self._chain(cluster):
            out += self._read_at(self._cluster_offset(clus), self.cluster_size)
            if size is not None and len(out) >= size:
                break
        return bytes(out[:size] if size is not None else out)

    # -- directory walk ----------------------------------------------------

    def _entries(self, raw: bytes, prefix: str) -> Iterator[DirEntry]:
        for i in range(0, len(raw) - 31, 32):
            rec = raw[i : i + 32]
            if rec[0] == 0x00:
                return
            attr = rec[11]
            if rec[0] == 0xE5 or attr == _ATTR_LFN or attr & _ATTR_VOLUME_ID:
                continue
            stem = rec[0:8].decode("latin-1").rstrip()
            ext = rec[8:11].decode("latin-1").rstrip()
            if stem in (".", "..") or not stem:
                continue  # the self/parent links, and anything nameless
            name = f"{stem}.{ext}" if ext else stem
            (cluster,) = struct.unpack_from("<H", rec, 26)
            (size,) = struct.unpack_from("<I", rec, 28)
            yield DirEntry(
                path=prefix + name,
                size=size,
                cluster=cluster,
                is_dir=bool(attr & _ATTR_DIRECTORY),
            )

    def listdir(self, path: str = "\\") -> List[DirEntry]:
        """List one directory (``\\`` is the root)."""
        path = path if path.startswith("\\") else "\\" + path
        prefix = path if path.endswith("\\") else path + "\\"
        if prefix == "\\":
            raw = self._read_at(
                self._root_sector * self.bytes_per_sector, self.root_entries * 32
            )
        else:
            entry = self.stat(prefix.rstrip("\\"))
            if not entry.is_dir:
                raise ImageError(f"{path} is not a directory")
            raw = self._read_chain(entry.cluster)
        return list(self._entries(raw, prefix))

    def walk(self, path: str = "\\", *, _depth: int = 0) -> Iterator[DirEntry]:
        """Yield every file and directory under ``path``, depth-first."""
        if _depth > 16:
            raise ImageError("directory nesting is implausibly deep")
        for entry in self.listdir(path):
            yield entry
            if entry.is_dir and entry.cluster >= 2:
                yield from self.walk(entry.path, _depth=_depth + 1)

    def stat(self, path: str) -> DirEntry:
        path = path if path.startswith("\\") else "\\" + path
        head, _, name = path.rpartition("\\")
        for entry in self.listdir(head or "\\"):
            if entry.name.upper() == name.upper():
                return entry
        raise FileNotFoundError(f"{path} is not in this image")

    def read_file(self, path: str) -> bytes:
        entry = self.stat(path)
        if entry.is_dir:
            raise ImageError(f"{path} is a directory")
        return self._read_chain(entry.cluster, entry.size)

    def find(self, suffix: str) -> List[DirEntry]:
        """Every file whose name ends with ``suffix`` (case-insensitive)."""
        want = suffix.upper()
        return [
            e for e in self.walk() if not e.is_dir and e.name.upper().endswith(want)
        ]
