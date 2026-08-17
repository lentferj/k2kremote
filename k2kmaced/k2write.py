# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# FAT16 layout per the public FAT specification; the K2000 volume geometry is
# the one k2image.py reads (OEM name "KMSI").
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

"""Replace the contents of a file that already exists in a K2000 disk image.

This is the one write direction the project has, and it is deliberately the
narrowest one that completes the macro workflow: you can edit ``BOOT.MAC``
offline, but until now there was no way to put it back, because
:mod:`k2kmaced.k2image` is read-only by design and ``mtools`` refuses these
volumes outright ("zero number of heads or sectors" — the K2000's BPB leaves the
geometry fields blank).

**It overwrites an existing file in place and changes nothing else.** That is not
a promise about the code, it is the shape of the operation:

* the file must already exist — nothing is created, so no directory entry is
  ever added and no free cluster is ever claimed;
* the new contents must fit the clusters that file **already owns** — so the FAT
  is never written to at all, and cannot be corrupted by this module;
* only two regions change: the bytes inside those clusters, and the 4-byte size
  field of that file's own directory record.

A macro is a few hundred bytes and a K2000 cluster is typically 32 KB, so
``BOOT.MAC`` fits its single existing cluster with room to spare. Anything that
does not fit is refused rather than grown.

If the new contents are *smaller*, the surplus clusters stay allocated to the
file. They are slack — reachable only through that file, and the size field says
where the data ends. Releasing them would mean editing the FAT, which is exactly
the risk this module is built to avoid.

Compressed images are refused: ``.lzo`` support in ``k2image`` works by
decompressing to a temporary copy, so writing to one would edit the copy and
throw the result away when it is cleaned up — a silent no-op, which is worse
than an error.

    from k2kmaced.k2write import replace_file_in_image
    replace_file_in_image("hd0.img", "\\\\BOOT.MAC", open("NEW.MAC","rb").read())

**Back up the image first.** This writes to the file you name, in place.
"""

from __future__ import annotations

import os
import struct
from typing import Iterator, Tuple

from k2kmaced.k2image import DiskImage, ImageError

__all__ = ["ImageWriteError", "replace_file_in_image", "plan_replacement"]

_SIZE_FIELD = 28          # offset of the 4-byte size within a 32-byte record
_ATTR_LFN = 0x0F
_ATTR_VOLUME_ID = 0x08


class ImageWriteError(ValueError):
    """Raised when a replacement cannot be done safely."""


def _records(image: DiskImage, directory: str) -> Iterator[Tuple[bytes, int]]:
    """Yield ``(32-byte record, absolute offset in the image)`` for a directory.

    The root directory is a contiguous run of sectors, but a subdirectory is a
    cluster *chain*, which need not be contiguous — so a record's offset cannot
    be computed from its index alone. This walks the chain and maps each record
    through it, which is the only reason this helper exists rather than reusing
    k2image's parser (that one never needs to know where a record lives).
    """
    if directory in ("\\", ""):
        base = image._root_sector * image.bytes_per_sector
        raw = image._read_at(base, image.root_entries * 32)
        for i in range(0, len(raw) - 31, 32):
            yield raw[i:i + 32], base + i
        return

    entry = image.stat(directory.rstrip("\\"))
    if not entry.is_dir:
        raise ImageWriteError(f"{directory} is not a directory")
    for cluster in image._chain(entry.cluster):
        base = image._cluster_offset(cluster)
        raw = image._read_at(base, image.cluster_size)
        for i in range(0, len(raw) - 31, 32):
            yield raw[i:i + 32], base + i


def _find_record(image: DiskImage, dos_path: str) -> int:
    """Absolute offset of the directory record for ``dos_path``."""
    dos_path = dos_path if dos_path.startswith("\\") else "\\" + dos_path
    head, _, name = dos_path.rpartition("\\")
    for record, offset in _records(image, head or "\\"):
        if record[0] == 0x00:
            break                     # end of directory
        attr = record[11]
        if record[0] == 0xE5 or attr == _ATTR_LFN or attr & _ATTR_VOLUME_ID:
            continue
        stem = record[0:8].decode("latin-1").rstrip()
        ext = record[8:11].decode("latin-1").rstrip()
        if not stem or stem in (".", ".."):
            continue
        if (f"{stem}.{ext}" if ext else stem).upper() == name.upper():
            return offset
    raise FileNotFoundError(f"{dos_path} is not in this image")


def plan_replacement(image_path, dos_path: str, length: int) -> dict:
    """Check a replacement without writing, and describe what it would do.

    Separated from the write so the CLI can show the user the plan — clusters,
    capacity, slack — before anything is touched, and so the refusals are
    testable without a writable image.
    """
    if str(image_path).lower().endswith(".lzo"):
        raise ImageWriteError(
            "this image is lzop-compressed; k2image reads it by decompressing to "
            "a temporary copy, so a write would edit that copy and be discarded. "
            "Decompress it to a .img first, write to that, and recompress.")
    with DiskImage.open(image_path) as image:
        entry = image.stat(dos_path)
        if entry.is_dir:
            raise ImageWriteError(f"{dos_path} is a directory")
        chain = list(image._chain(entry.cluster))
        capacity = len(chain) * image.cluster_size
        if length > capacity:
            raise ImageWriteError(
                f"{length} bytes will not fit the {len(chain)} cluster(s) "
                f"{dos_path} already owns ({capacity} bytes). Growing a file "
                f"means allocating clusters and writing the FAT, which this "
                f"deliberately will not do.")
        return {
            "path": entry.path,
            "old_size": entry.size,
            "new_size": length,
            "clusters": chain,
            "cluster_size": image.cluster_size,
            "capacity": capacity,
            "record_offset": _find_record(image, dos_path),
            "slack": capacity - length,
            # Where each of those clusters actually is. Captured here because the
            # geometry comes from the read-only open, while the write uses its
            # own handle — recomputing it there would mean re-deriving the layout
            # from a second parse and hoping the two agree.
            "_offsets": {c: image._cluster_offset(c) for c in chain},
        }


def replace_file_in_image(image_path, dos_path: str, data: bytes) -> dict:
    """Overwrite ``dos_path`` inside ``image_path`` with ``data``.

    Returns the plan that was carried out. Raises before touching anything if
    the replacement is not safe, and verifies by reading the file back
    afterwards — a write that reported success and did not land is the failure
    mode that would cost a boot, so it is checked rather than assumed.
    """
    plan = plan_replacement(image_path, dos_path, len(data))
    cluster_size = plan["cluster_size"]

    with open(image_path, "r+b") as fh:
        remaining = data
        for cluster in plan["clusters"]:
            if not remaining:
                break
            chunk, remaining = remaining[:cluster_size], remaining[cluster_size:]
            # Pad to the full cluster so no bytes of the previous contents
            # survive inside the region the file still owns.
            fh.seek(_offset_of(plan, cluster))
            fh.write(chunk + b"\x00" * (cluster_size - len(chunk)))
        fh.seek(plan["record_offset"] + _SIZE_FIELD)
        fh.write(struct.pack("<I", len(data)))
        fh.flush()
        os.fsync(fh.fileno())

    with DiskImage.open(image_path) as image:
        landed = image.read_file(dos_path)
    if landed != data:
        raise ImageWriteError(
            f"wrote {len(data)} bytes to {dos_path} but read back "
            f"{len(landed)} that do not match — do not boot from this image")
    return plan


def _offset_of(plan: dict, cluster: int) -> int:
    """Absolute offset of ``cluster``, from the geometry captured in the plan."""
    # Recomputed from the plan rather than kept as an open DiskImage: the plan is
    # taken with the image open read-only, and the write wants its own handle.
    return plan["_offsets"][cluster]
