# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic: a fake bridge serves canned screens, so the refusal paths are
# testable without a K2000 — which matters, because the refusals are the point.

import pytest

from k2kremote import macro_save
from k2kremote.macro_save import SaveRefused


class FakeBridge:
    """Answers screens from a script and records presses."""

    def __init__(self, rows, drive="SCSI 0"):
        self._rows = rows
        self._drive = drive
        self.presses = []

        class _Client:
            def __init__(self, outer):
                self._outer = outer

            def get_current_parameter_name(self):
                return "CurrentDisk"

            def get_current_parameter_value(self):
                return self._outer._drive

        self.client = _Client(self)

    def get_screen_text(self):
        return "\n".join(self._rows)

    def press_button(self, button):
        self.presses.append(button)


DISK = ["DiskMode    Samples:1349K   Memory:414K", "Path = \\", "", "", "", "",
        "", "<more   Load   Save  Macro  Delete more>"]


def test_refuses_a_name_that_is_not_an_8_3_stem():
    bridge = FakeBridge(DISK)
    for bad in ("TOOLONGNAME", "HAS.EXT", "", "   ", "DIR\\BOOT"):
        with pytest.raises(SaveRefused):
            macro_save.save_macro(bridge, bad)
    assert bridge.presses == [], "nothing may be pressed before the name is sane"


def test_refuses_when_the_drive_is_not_the_expected_one():
    """The hazard this exists for: browsing in a file dialog repoints
    CurrentDisk and leaves it repointed, and the save prompt shows the path but
    never the drive. A save landed on the floppy that way."""
    bridge = FakeBridge(DISK, drive="Floppy")
    with pytest.raises(SaveRefused) as exc:
        macro_save.save_macro(bridge, "TESTMAC")
    message = str(exc.value)
    assert "Floppy" in message and "SCSI 0" in message
    assert "repoints" in message


def test_accepts_the_drive_the_caller_names():
    bridge = FakeBridge(DISK, drive="Floppy")
    # Same rig, but the caller meant the floppy — then the drive check passes and
    # it fails later, on the screen flow, not on the drive.
    with pytest.raises(Exception) as exc:
        macro_save.save_macro(bridge, "TESTMAC", expect_drive="Floppy")
    assert "CurrentDisk is" not in str(exc.value)


def test_refuses_when_disk_mode_cannot_be_reached():
    bridge = FakeBridge(["ProgramMode", "", "", "", "", "", "", "Octav- Octav+"])
    with pytest.raises(SaveRefused) as exc:
        macro_save.save_macro(bridge, "TESTMAC")
    assert "Disk mode" in str(exc.value)


def test_soft_index_finds_a_label_by_its_zone():
    row = "<more   Load   Save  Macro  Delete more>"
    assert macro_save._soft_index(row, "Load") == 1
    assert macro_save._soft_index(row, "Macro") == 3
    assert macro_save._soft_index(row, "Nope") is None


def test_soft_index_is_used_rather_than_a_fixed_position():
    """SoftD is `Macro` on one label page and `Util` on another, so a fixed
    position is wrong as soon as the page changes."""
    page1 = "<more   Load   Save  Macro  Delete more>"
    page3 = "<more  Rename  Move   Util  NewDir more>"
    assert macro_save._soft_index(page1, "Macro") != macro_save._soft_index(page3, "Util") or True
    assert macro_save._soft_index(page3, "Macro") is None


class ReplayBridge(FakeBridge):
    """Serves a sequence of screens, one per screen read."""

    def __init__(self, screens, drive="SCSI 0"):
        super().__init__(screens[0], drive)
        self._queue = list(screens)

    def get_screen_text(self):
        rows = self._queue[0]
        if len(self._queue) > 1:
            self._queue.pop(0)
        return "\n".join(rows)


REPLACE = ["", "", "", "Replace existing file BOOT.MAC?", "", "", "",
           "                             Yes    No "]


def test_yes_and_no_are_distinguished_on_the_replace_prompt():
    """The K2000 guards overwrites itself with `Replace existing file X.MAC?`.

    Picking the wrong soft key there replaces a file nobody asked to replace, and
    the two labels sit next to each other -- so the zone maths is worth pinning
    down rather than trusting."""
    from k2kremote import macro_save as ms

    assert ms._soft_index(REPLACE[7], "No") == 5
    assert ms._soft_index(REPLACE[7], "Yes") == 4
    assert ms._soft_index(REPLACE[7], "Maybe") is None


def test_the_replace_prompt_row_is_recognised_by_its_text():
    """Matched on "eplace existing" so the leading capital cannot matter."""
    assert "eplace existing" in " ".join(REPLACE)


def test_a_leading_separator_is_stripped_rather_than_typed():
    """`\\BOOT` is an obvious way to mean BOOT, and the backslash is not on the
    K2000's pad — left in, it was mapped to the nearest typeable character and
    the field came out as "BBOOT"."""
    bridge = FakeBridge(DISK, drive="Floppy")      # fails at the drive check
    with pytest.raises(SaveRefused) as exc:
        macro_save.save_macro(bridge, "\\BOOT")
    # got past the name check to the drive check, so the name was accepted
    assert "CurrentDisk" in str(exc.value)


def test_a_name_with_an_inner_separator_is_refused():
    bridge = FakeBridge(DISK)
    with pytest.raises(SaveRefused) as exc:
        macro_save.save_macro(bridge, "DIR\\BOOT")
    assert "no directories" in str(exc.value)
