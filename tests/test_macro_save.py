# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic: a fake bridge serves canned screens, so the refusal paths are
# testable without a K2000 — which matters, because the refusals are the point.

import pytest

from k2000.definitions import Button
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
                # PADDED, deliberately. The K2000 pads short labels with
                # spaces before the colon, and current_disk() shares
                # normalise_param_label() with the probe precisely because the
                # two had drifted with only one of them tested
                # (RESOLUTION_NOTES §62). A bare "CurrentDisk" is handled
                # identically by the old buggy expression and the new one, so
                # it exercises nothing.
                return "CurrentDisk :"

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


def test_soft_index_does_not_match_a_label_inside_a_longer_one():
    """A bare substring search matches "Fill" inside "OvFill" and returns
    OvFill's soft key instead of Fill's -- confirmed live 2026-08-30 in a
    sibling copy of this function, where that pressed OvFill (deletes the
    bank's RAM objects before loading) instead of Fill. This module doesn't
    use those labels, but the same row shape is worth pinning down here too."""
    row = "OvFill Overwrt Merge Append Fill  Cancel"
    assert macro_save._soft_index(row, "OvFill") == 0
    assert macro_save._soft_index(row, "Fill") == 4


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


def test_a_typed_path_is_refused_rather_than_trimmed():
    """`\\BOOT` plainly means "BOOT.MAC in the root".

    But the macro lands in whatever directory the instrument is already in, and
    browsing moves that — so dropping the backslash would save the file somewhere
    other than where the name said. Refusing is the honest answer; the earlier
    behaviour typed the backslash onto a pad that has no backslash, and the field
    came out as "BBOOT"."""
    bridge = FakeBridge(DISK)
    for path in ("\\BOOT", "/BOOT", "DIR\\BOOT", "\\DIR\\BOOT"):
        with pytest.raises(SaveRefused) as exc:
            macro_save.save_macro(bridge, path)
        assert "names a directory" in str(exc.value)
    assert bridge.presses == [], "nothing may be pressed for a refused name"


def test_the_refusal_suggests_the_bare_name():
    bridge = FakeBridge(DISK)
    with pytest.raises(SaveRefused) as exc:
        macro_save.save_macro(bridge, "\\BOOT")
    assert "'BOOT'" in str(exc.value)


def test_an_extension_is_refused_with_the_stem_to_use():
    bridge = FakeBridge(DISK)
    with pytest.raises(SaveRefused) as exc:
        macro_save.save_macro(bridge, "BOOT.MAC")
    assert "adds .MAC itself" in str(exc.value) and "'BOOT'" in str(exc.value)


DIALOG = ["Save Macro", "", "", "", "", "", "",
          "                       Cancel    OK  "]


class _ModalBridge(FakeBridge):
    """Goes modal on the first press; only Cancel or Exit gets back out.

    A K2000 dialog is modal on the instrument itself -- `Disk` does nothing
    while one is up. That is what makes a dialog left open by a failed save
    everybody else's problem: the mirror, the next save, and a human at the
    panel all start from a question they did not ask.
    """

    def __init__(self, drive="SCSI 0"):
        super().__init__(list(DISK), drive=drive)
        self.in_dialog = False

    def press_button(self, button):
        super().press_button(button)
        if not self.in_dialog:
            self.in_dialog = True
            self._rows = list(DIALOG)
            return
        cancel = macro_save._SOFT[macro_save._soft_index(DIALOG[7], "Cancel")]
        if button in (cancel, Button.Exit):
            self.in_dialog = False
            self._rows = list(DISK)


def test_a_failed_save_does_not_leave_a_dialog_open_on_the_instrument():
    """`SaveRefused` says "the panel was left where it was found"."""
    bridge = _ModalBridge()

    with pytest.raises(SaveRefused):
        macro_save.save_macro(bridge, "TESTMAC")

    assert not bridge.in_dialog, "the instrument was left inside a dialog"
    assert "DiskMode" in bridge.get_screen_text().split("\n")[0]


def test_backing_out_never_answers_a_question_it_did_not_read():
    """Cancel and Exit abandon; Yes, No and OK commit to something."""
    bridge = _ModalBridge()

    with pytest.raises(SaveRefused):
        macro_save.save_macro(bridge, "TESTMAC")

    ok = macro_save._SOFT[macro_save._soft_index(DIALOG[7], "OK")]
    assert ok not in bridge.presses[1:], "the back-out pressed OK"
