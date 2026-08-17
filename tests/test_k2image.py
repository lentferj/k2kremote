# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only: no MIDI hardware is ever opened, and no real disk image is
# touched. The fixtures are FAT16 volumes built here in the test, laid out the
# way a K2000 SCSI disk is (no partition table, OEM "KMSI"). One extra test
# cross-checks the reader against an image built by the sibling mpc2emu
# project's own FAT16 writer, and skips when mpc2emu is not installed.

import struct
from pathlib import Path

import pytest

from k2kmaced import mpc2emu_link
from k2kmaced.k2image import DiskImage, ImageError, is_disk_image

BPS = 512
SPC = 1
RESERVED = 1
NFATS = 2
FAT_SECTORS = 32
ROOT_ENTRIES = 512
ROOT_SECTORS = ROOT_ENTRIES * 32 // BPS
DATA_SECTOR = RESERVED + NFATS * FAT_SECTORS + ROOT_SECTORS
TOTAL_SECTORS = DATA_SECTOR + 512


def _dirent(name: str, attr: int, cluster: int, size: int) -> bytes:
    if name in (".", ".."):  # the self/parent links a real subdirectory carries
        short = name.ljust(11)
    else:
        stem, _, ext = name.partition(".")
        short = stem.upper().ljust(8)[:8] + ext.upper().ljust(3)[:3]
    return (
        short.encode("ascii")
        + bytes([attr])
        + bytes(14)
        + struct.pack("<HI", cluster, size)
    )


def build_image(path: Path, tree: dict) -> Path:
    """Write a K2000-style FAT16 volume.

    ``tree`` maps a directory name (``""`` = root) to ``{filename: bytes}``.
    """
    image = bytearray(TOTAL_SECTORS * BPS)
    fat = bytearray(FAT_SECTORS * BPS)
    struct.pack_into("<HH", fat, 0, 0xFFF8, 0xFFFF)

    next_cluster = 2

    def alloc(payload: bytes) -> int:
        nonlocal next_cluster
        first = next_cluster
        needed = max(1, -(-len(payload) // (BPS * SPC)))
        for i in range(needed):
            clus = first + i
            offset = (DATA_SECTOR + (clus - 2) * SPC) * BPS
            chunk = payload[i * BPS * SPC : (i + 1) * BPS * SPC]
            image[offset : offset + len(chunk)] = chunk
            struct.pack_into(
                "<H", fat, clus * 2, 0xFFFF if i == needed - 1 else clus + 1
            )
        next_cluster += needed
        return first

    root = bytearray()
    for directory, files in tree.items():
        if not directory:
            for name, payload in files.items():
                root += _dirent(name, 0x00, alloc(payload), len(payload))
            continue
        # Reserve the directory's own cluster before its files get theirs.
        dir_cluster = next_cluster
        next_cluster += 1
        struct.pack_into("<H", fat, dir_cluster * 2, 0xFFFF)
        entries = _dirent(".", 0x10, dir_cluster, 0) + _dirent("..", 0x10, 0, 0)
        for name, payload in files.items():
            entries += _dirent(name, 0x00, alloc(payload), len(payload))
        offset = (DATA_SECTOR + (dir_cluster - 2) * SPC) * BPS
        image[offset : offset + len(entries)] = entries
        root += _dirent(directory, 0x10, dir_cluster, 0)

    image[RESERVED * BPS : (RESERVED + FAT_SECTORS) * BPS] = fat
    start = (RESERVED + FAT_SECTORS) * BPS
    image[start : start + len(fat)] = fat
    root_off = (RESERVED + NFATS * FAT_SECTORS) * BPS
    image[root_off : root_off + len(root)] = root

    boot = bytearray(BPS)
    boot[0:3] = b"\xeb\x34\x90"
    boot[3:11] = b"KMSI    "
    struct.pack_into("<HBHBHHBHHHII", boot, 0x0B, BPS, SPC, RESERVED, NFATS,
                     ROOT_ENTRIES, 0, 0xF8, FAT_SECTORS, 0, 0, 0, TOTAL_SECTORS)
    image[0:BPS] = boot

    path.write_bytes(bytes(image))
    return path


@pytest.fixture
def image(tmp_path) -> Path:
    return build_image(
        tmp_path / "hd0.img",
        {
            "": {"BOOT.MAC": b"macro" * 10, "NULL.KRZ": b"\x00" * 580},
            "--FAVS": {"KPOWFAV.KRZ": bytes(range(256)) * 8},
        },
    )


def test_reads_the_boot_sector_geometry(image):
    with DiskImage.open(image) as img:
        assert img.oem == "KMSI"
        assert img.bytes_per_sector == BPS
        assert img.cluster_size == BPS * SPC


def test_lists_the_root_directory(image):
    with DiskImage.open(image) as img:
        assert sorted(e.path for e in img.listdir()) == [
            "\\--FAVS", "\\BOOT.MAC", "\\NULL.KRZ"
        ]


def test_walks_into_subdirectories(image):
    with DiskImage.open(image) as img:
        files = sorted(e.path for e in img.walk() if not e.is_dir)
    assert files == ["\\--FAVS\\KPOWFAV.KRZ", "\\BOOT.MAC", "\\NULL.KRZ"]


def test_reads_a_file_exactly(image):
    with DiskImage.open(image) as img:
        assert img.read_file("\\BOOT.MAC") == b"macro" * 10
        # Multi-cluster, so the FAT chain is actually followed.
        assert img.read_file("\\--FAVS\\KPOWFAV.KRZ") == bytes(range(256)) * 8


def test_lookup_is_case_insensitive(image):
    with DiskImage.open(image) as img:
        assert img.stat("\\boot.mac").size == 50


def test_find_by_suffix(image):
    with DiskImage.open(image) as img:
        assert [e.path for e in img.find(".mac")] == ["\\BOOT.MAC"]


def test_missing_file_raises(image):
    with DiskImage.open(image) as img:
        with pytest.raises(FileNotFoundError):
            img.read_file("\\NOPE.MAC")


def test_directory_metadata(image):
    with DiskImage.open(image) as img:
        entry = img.stat("\\--FAVS")
        assert entry.is_dir and entry.name == "--FAVS"
        assert img.stat("\\--FAVS\\KPOWFAV.KRZ").directory == "\\--FAVS\\"
        with pytest.raises(ImageError, match="is a directory"):
            img.read_file("\\--FAVS")


def test_non_fat_data_is_rejected(tmp_path):
    junk = tmp_path / "junk.img"
    junk.write_bytes(b"\x00" * 4096)
    with pytest.raises(ImageError, match="not a FAT16 volume"):
        DiskImage.open(junk)


def test_truncated_image_is_rejected(tmp_path):
    stub = tmp_path / "stub.img"
    stub.write_bytes(b"\xeb\x34\x90KMSI")
    with pytest.raises(ImageError, match="too small"):
        DiskImage.open(stub)


def test_is_disk_image_sniff():
    assert is_disk_image("HD0.img") and is_disk_image("HD0.img.lzo")
    assert not is_disk_image("BOOT.MAC")


def test_cluster_loop_is_detected(image):
    with DiskImage.open(image) as img:
        # A multi-cluster file, so the chain is actually walked past the first
        # cluster before the read is satisfied.
        entry = img.stat("\\--FAVS\\KPOWFAV.KRZ")
    raw = bytearray(image.read_bytes())
    struct.pack_into("<H", raw, RESERVED * BPS + entry.cluster * 2, entry.cluster)
    image.write_bytes(bytes(raw))
    with DiskImage.open(image) as img:
        with pytest.raises(ImageError, match="loops"):
            img.read_file("\\--FAVS\\KPOWFAV.KRZ")


@pytest.mark.skipif(not mpc2emu_link.available(),
                    reason="the sibling mpc2emu checkout is not available")
def test_reads_an_image_written_by_mpc2emu(tmp_path):
    """Cross-check against mpc2emu's own K2000 pseudo-DOS FAT16 writer."""
    payload = (Path(__file__).parent / "fixtures" / "BOOT.MAC").read_bytes()
    source = tmp_path / "BOOT.MAC"
    source.write_bytes(payload)
    path = tmp_path / "mpc2emu.img"

    volume = mpc2emu_link.format_new(
        str(path), 8, oem=b"KMSI    ", partition=False, spc=1
    )
    folder = volume.makedir("--FAVS")
    volume.add_file(str(source), "BOOT.MAC")
    volume.add_file(str(source), "KPOWFAV.KRZ", folder_cluster=folder)
    volume.close()

    with DiskImage.open(path) as img:
        assert img.oem == "KMSI"
        assert img.read_file("\\BOOT.MAC") == payload
        assert img.read_file("\\--FAVS\\KPOWFAV.KRZ") == payload
        assert [e.path for e in img.find(".MAC")] == ["\\BOOT.MAC"]
