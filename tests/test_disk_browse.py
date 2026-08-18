# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic: real listing lines captured from the K2000R, parsed offline.

from k2kremote import disk_browse
from k2kremote.disk_browse import Item, _parse, _soft_index


def test_parses_a_directory_line():
    item = _parse("    File to load:--FAVS       (dir)")
    assert item == Item("--FAVS", True, "")
    assert item.filename == "--FAVS"


def test_parses_a_file_line_and_rebuilds_the_8_3_name():
    """The K2000 pads the stem to 8 columns, so the displayed name is not the
    filename — 'BOOT     .MAC' has to come back as 'BOOT.MAC'."""
    item = _parse("    File to load:BOOT     .MAC     .5K")
    assert item.is_dir is False
    assert item.filename == "BOOT.MAC"
    assert item.size == ".5K"


def test_parses_a_file_with_a_long_stem():
    assert _parse("  File to delete:TESTMAC  .MAC     .5K").filename == "TESTMAC.MAC"


def test_ignores_the_total_line_and_blanks():
    assert _parse("Total: 1252K") is None
    assert _parse("   ") is None
    assert _parse("") is None


def test_soft_index_locates_a_label_by_zone():
    row = "Select  Root  Parent  Open   OK   Cancel"
    assert _soft_index(row, "Root") == 1
    assert _soft_index(row, "Open") == 3
    assert _soft_index(row, "Cancel") == 5
    assert _soft_index(row, "Macro") is None


def test_ok_is_never_among_the_labels_this_module_presses():
    """OK on the Load page LOADS the file -- slow, and destructive into a
    populated bank. The browser must only ever descend, ascend and cancel."""
    import inspect

    source = inspect.getsource(disk_browse)
    pressed = {line.split('"')[1]
               for line in source.splitlines()
               if "_press(bridge, " in line and '"' in line}
    assert pressed <= {"Load", "Open", "Parent", "Root"}, pressed
    assert "OK" not in pressed
