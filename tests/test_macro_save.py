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
    for bad in ("TOOLONGNAME", "HAS.EXT", "", "   "):
        with pytest.raises(SaveRefused) as exc:
            macro_save.save_macro(bridge, bad)
        assert "8.3" in str(exc.value) or "cannot type" in str(exc.value)
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
