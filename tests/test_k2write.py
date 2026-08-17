# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only: every image here is built by the test, never a real backup.

import struct

import pytest

from k2kmaced.k2image import DiskImage
from k2kmaced.k2write import (
    ImageWriteError,
    plan_replacement,
    replace_file_in_image,
)

from test_k2image import build_image  # tests/ is on sys.path under pytest

TREE = {
    "": {"BOOT.MAC": b"original boot macro", "OTHER.KRZ": b"\xAA" * 4096},
    "SUBDIR": {"NESTED.KRZ": b"nested original"},
}


@pytest.fixture
def image(tmp_path):
    return build_image(tmp_path / "hd0.img", TREE)


def test_replaces_the_file_and_leaves_the_others_alone(image):
    replace_file_in_image(image, "\\BOOT.MAC", b"new macro contents")
    with DiskImage.open(image) as img:
        assert img.read_file("\\BOOT.MAC") == b"new macro contents"
        assert img.read_file("\\OTHER.KRZ") == b"\xAA" * 4096
        assert img.read_file("\\SUBDIR\\NESTED.KRZ") == b"nested original"


def test_updates_the_size_field_so_a_shorter_file_reads_short(image):
    replace_file_in_image(image, "\\BOOT.MAC", b"tiny")
    with DiskImage.open(image) as img:
        entry = img.stat("\\BOOT.MAC")
        assert entry.size == 4
        assert img.read_file("\\BOOT.MAC") == b"tiny"   # no trailing rubbish


def test_works_on_a_file_in_a_subdirectory(image):
    """A subdirectory is a cluster chain, so its records are not at a fixed
    offset from the start of the region the way the root's are."""
    replace_file_in_image(image, "\\SUBDIR\\NESTED.KRZ", b"replaced")
    with DiskImage.open(image) as img:
        assert img.read_file("\\SUBDIR\\NESTED.KRZ") == b"replaced"


def test_never_writes_to_the_fat(image):
    """The whole safety argument: the FAT is not touched, so it cannot be
    corrupted here. Compared byte-for-byte rather than argued from the code."""
    with DiskImage.open(image) as img:
        fat_start = img.reserved_sectors * img.bytes_per_sector
        fat_len = img.num_fats * img.fat_sectors * img.bytes_per_sector
    before = open(image, "rb").read()[fat_start:fat_start + fat_len]
    replace_file_in_image(image, "\\BOOT.MAC", b"x" * 100)
    after = open(image, "rb").read()[fat_start:fat_start + fat_len]
    assert before == after


def test_refuses_to_grow_beyond_the_clusters_the_file_owns(image):
    with DiskImage.open(image) as img:
        capacity = img.cluster_size          # BOOT.MAC owns exactly one cluster
    with pytest.raises(ImageWriteError, match="will not fit"):
        replace_file_in_image(image, "\\BOOT.MAC", b"z" * (capacity + 1))
    # and the original is still intact after the refusal
    with DiskImage.open(image) as img:
        assert img.read_file("\\BOOT.MAC") == b"original boot macro"


def test_fills_the_cluster_exactly_at_capacity(image):
    with DiskImage.open(image) as img:
        capacity = img.cluster_size
    replace_file_in_image(image, "\\BOOT.MAC", b"z" * capacity)
    with DiskImage.open(image) as img:
        assert img.read_file("\\BOOT.MAC") == b"z" * capacity


def test_refuses_a_file_that_does_not_exist(image):
    # Creating a file would mean a new directory record and a FAT allocation.
    with pytest.raises(FileNotFoundError):
        replace_file_in_image(image, "\\NOPE.MAC", b"data")


def test_refuses_a_directory(image):
    with pytest.raises(ImageWriteError, match="is a directory"):
        replace_file_in_image(image, "\\SUBDIR", b"data")


def test_refuses_a_compressed_image(tmp_path):
    """Writing into a .lzo would edit k2image's temp copy and be discarded — a
    silent no-op, which is worse than an error."""
    fake = tmp_path / "hd0.img.lzo"
    fake.write_bytes(b"not really lzo")
    with pytest.raises(ImageWriteError, match="lzop-compressed"):
        replace_file_in_image(fake, "\\BOOT.MAC", b"data")


def test_plan_describes_the_write_without_performing_it(image):
    plan = plan_replacement(image, "\\BOOT.MAC", 300)
    assert plan["old_size"] == len(b"original boot macro")
    assert plan["new_size"] == 300
    assert len(plan["clusters"]) == 1
    assert plan["slack"] == plan["capacity"] - 300
    with DiskImage.open(image) as img:      # nothing changed
        assert img.read_file("\\BOOT.MAC") == b"original boot macro"


def test_a_failed_verification_is_reported(image, monkeypatch):
    """If the bytes do not land, saying so is the whole point — a macro that
    silently did not get written is a boot that silently does the old thing."""
    import k2kmaced.k2write as k2write

    real = k2write.DiskImage.open

    class Liar:
        def __init__(self, inner):
            self._inner = inner

        def read_file(self, path):
            return b"something else entirely"

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._inner.close()

    calls = {"n": 0}

    def fake_open(path):
        calls["n"] += 1
        inner = real(path)
        return Liar(inner) if calls["n"] > 1 else inner

    monkeypatch.setattr(k2write.DiskImage, "open", staticmethod(fake_open))
    with pytest.raises(ImageWriteError, match="do not match"):
        replace_file_in_image(image, "\\BOOT.MAC", b"whatever")


def test_size_field_offset_is_where_fat_says_it_is(image):
    """Guards the one magic number: size lives at byte 28 of the record."""
    plan = plan_replacement(image, "\\BOOT.MAC", 42)
    raw = open(image, "rb").read()
    (size,) = struct.unpack_from("<I", raw, plan["record_offset"] + 28)
    assert size == len(b"original boot macro")
