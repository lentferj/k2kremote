# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic: real listing lines captured from the K2000R, parsed offline.

import pytest

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


# --- positioning -------------------------------------------------------------

class _WheelBridge:
    """Tracks a selection the way the K2000 does: clamped, never wrapping."""

    def __init__(self, names, index=0):
        self.names = names
        self.index = index
        self.messages = 0

    def alpha_wheel(self, clicks):
        self.messages += 1
        assert -64 <= clicks <= 63, f"{clicks} exceeds one PANEL message"
        self.index = max(0, min(len(self.names) - 1, self.index + clicks))

    def get_screen_text(self):
        rows = ["Dir:\\", "", "", f"    File to load:{self.names[self.index]}",
                "", "", "Total: 1K", "Select  Root  Parent  Open   OK   Cancel"]
        return "\n".join(rows)

    def press_button(self, button):
        pass


def test_select_index_reaches_an_entry_ABOVE_the_cursor():
    """The bug this exists for: listing() leaves the cursor on the LAST entry,
    and the K2000 clamps rather than wrapping — so a downward-only search could
    never reach anything above it, and opening any directory but the last did
    nothing at all."""
    names = [f"DIR{i:02d}" for i in range(25)]
    bridge = _WheelBridge(names, index=24)      # parked at the bottom
    got = disk_browse.select_index(bridge, 7, len(names))
    assert got == "DIR07"
    assert bridge.index == 7


def test_select_index_works_from_anywhere_including_the_target():
    names = [f"DIR{i:02d}" for i in range(25)]
    for start in (0, 5, 12, 24):
        bridge = _WheelBridge(names, index=start)
        assert disk_browse.select_index(bridge, 12, len(names)) == "DIR12"


def test_select_index_chunks_long_moves_into_legal_messages():
    """A PANEL wheel delta is -64..+63; a 200-entry directory needs chunking."""
    names = [f"DIR{i:03d}" for i in range(200)]
    bridge = _WheelBridge(names, index=199)
    assert disk_browse.select_index(bridge, 150, len(names)) == "DIR150"
    assert bridge.messages > 1


def test_enter_refuses_when_the_device_shows_a_different_entry():
    """Open on the wrong row opens the wrong directory."""
    names = ["AAA", "BBB", "CCC"]
    bridge = _WheelBridge(names)
    with pytest.raises(disk_browse.BrowseError) as exc:
        disk_browse.enter(bridge, 1, len(names), "NOTTHERE")
    assert "not pressing Open" in str(exc.value)


# --- backing out of a dialog -------------------------------------------------

class _PanelBridge:
    """Replays a sequence of screens, advancing when a soft key is pressed."""

    def __init__(self, screens):
        self.screens = list(screens)
        self.presses = []

    def get_screen_text(self):
        return "\n".join(self.screens[0])

    def press_button(self, button):
        self.presses.append(button)
        if len(self.screens) > 1:
            self.screens.pop(0)


DIALOG = ["Dir:\\-GRANDPI\\    Sel:0/9    Index:   9", "", "",
          "  File to rename:STWAYDSO .KRZ", "", "", "Total: 1K",
          "        Root  Parent  Open   OK   Cancel"]
DISKPAGE = ["DiskMode    Samples:1138K   Memory:414K", "Path = \\", "", "", "",
            "", "", "<more   Load   Save  Macro  Delete more>"]


def test_ensure_disk_mode_cancels_out_of_a_dialog():
    """A browser or prompt left open by anything at all -- an abandoned save, a
    probe, a human at the panel -- used to make this fail outright, because
    pressing Disk does nothing while a dialog is up."""
    from k2000.definitions import Button

    bridge = _PanelBridge([DIALOG, DISKPAGE])
    assert disk_browse.ensure_disk_mode(bridge) is True
    assert bridge.presses, "it has to press something to get out"
    assert Button.SoftF in bridge.presses, "Cancel is soft key 5 on that row"


def test_ensure_disk_mode_is_a_no_op_when_already_there():
    bridge = _PanelBridge([DISKPAGE])
    assert disk_browse.ensure_disk_mode(bridge) is True
    assert bridge.presses == []


def test_ensure_disk_mode_never_answers_a_question():
    """Yes/No/OK answer questions this code has not read. Only Cancel and Exit
    abandon, so only those are pressed."""
    from k2000.definitions import Button

    confirm = ["", "", "", "Are you sure you want to delete", "the selected file?",
               "", "", "                             Yes    No "]
    bridge = _PanelBridge([confirm, DISKPAGE])
    disk_browse.ensure_disk_mode(bridge)
    # No Cancel on that row, so it must fall back to Exit rather than pick Yes/No.
    assert Button.Exit in bridge.presses
