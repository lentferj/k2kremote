# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only -- never opens a MIDI port, per CLAUDE.md's hardware rule.

from types import SimpleNamespace

from k2000.definitions import ObjectType
from k2000.messages import Info

from k2kremote.midi_bridge import PatchUnverified
from k2kremote.monitor_tui import MonitorTuiApp


async def _wait_for(pilot, predicate, tries: int = 60, step: float = 0.05) -> bool:
    for _ in range(tries):
        await pilot.pause(step)
        if predicate():
            return True
    return False


class FakeK2000Bridge:
    """Answers `list_bank`/`read_object_bytes`/`patch_object_bytes` from
    canned data -- the same three calls `MonitorTuiApp` makes on a real
    `MidiBridge`, none of which touch a MIDI port here."""

    def __init__(self):
        self.objects = [
            Info(ObjectType.Program, 906, 512, True, "TESTPRG"),
            Info(ObjectType.Program, 907, 512, True, "OTHERPRG"),
        ]
        # Program 906's two known offsets (k2kfields.KNOWN_FIELDS), plus the
        # rest of the object as zero so a whole-object read has *something*.
        self._data = {906: {215: b"\x28", 199: bytes([79])},
                      907: {215: b"\x05", 199: bytes([50])}}
        self.patches = []
        self.client = SimpleNamespace(
            midi_in=SimpleNamespace(get_message=lambda: None))

    def list_bank(self, obj_type, bank, *, ram_only=True, quiet_for=2.0):
        return (list(self.objects), True)

    def read_object_bytes(self, obj_type, idno, offset, size, timeout=None):
        return self._data[idno][offset]

    def patch_object_bytes(self, obj_type, idno, offset, data):
        self.patches.append((obj_type, idno, offset, data))
        self._data[idno][offset] = data
        return data


class _DnakBridge(FakeK2000Bridge):
    def patch_object_bytes(self, obj_type, idno, offset, data):
        raise PatchUnverified("device did not acknowledge the write")


async def test_object_list_populates_from_list_bank():
    app = MonitorTuiApp(FakeK2000Bridge())
    async with app.run_test() as pilot:
        table = app.query_one("#objects")
        assert await _wait_for(pilot, lambda: table.row_count == 2)
        assert "TESTPRG" in app.last_status or table.row_count == 2


async def test_selecting_an_object_populates_known_fields():
    bridge = FakeK2000Bridge()
    app = MonitorTuiApp(bridge)
    async with app.run_test() as pilot:
        objects = app.query_one("#objects")
        await _wait_for(pilot, lambda: objects.row_count == 2)
        app._selected_idno = 906
        app.refresh_fields()
        fields = app.query_one("#fields")
        assert await _wait_for(pilot, lambda: fields.row_count == 2)
        rendered = {str(fields.get_cell_at((r, 2)))
                   for r in range(fields.row_count)}
        assert any("ENV2->FilFreq Depth: 1200 cents" in text for text in rendered)
        assert any("LFO1->Pitch Depth: 1200 cents" in text for text in rendered)


async def test_unmapped_byte_reports_unmapped_not_a_fabricated_value():
    bridge = FakeK2000Bridge()
    app = MonitorTuiApp(bridge)
    async with app.run_test() as pilot:
        objects = app.query_one("#objects")
        await _wait_for(pilot, lambda: objects.row_count == 2)
        app._selected_idno = 907
        app.refresh_fields()
        fields = app.query_one("#fields")
        await _wait_for(pilot, lambda: fields.row_count == 2)
        rendered = {str(fields.get_cell_at((r, 2)))
                   for r in range(fields.row_count)}
        assert any("unmapped for this byte" in text for text in rendered)


async def test_patch_writes_through_patch_object_bytes():
    bridge = FakeK2000Bridge()
    app = MonitorTuiApp(bridge)
    async with app.run_test() as pilot:
        objects = app.query_one("#objects")
        await _wait_for(pilot, lambda: objects.row_count == 2)
        app._selected_idno = 906
        app.refresh_fields()
        fields = app.query_one("#fields")
        await _wait_for(pilot, lambda: fields.row_count == 2)

        app.action_patch_selected()
        assert await _wait_for(pilot, lambda: len(app.screen_stack) > 1)

        screen = app.screen
        screen._input.value = "50"
        screen.on_input_submitted(
            type(screen._input).Submitted(screen._input, "50"))

        assert await _wait_for(pilot, lambda: len(bridge.patches) == 1)
        obj_type, idno, offset, data = bridge.patches[0]
        # rows are sorted by offset ascending (_fields_loaded); cursor_row 0
        # is offset 199 (LFO1->Pitch Depth), not 215.
        assert (obj_type, idno, offset, data) == (ObjectType.Program, 906,
                                                   199, bytes.fromhex("50"))
        assert await _wait_for(pilot, lambda: len(app.screen_stack) == 1)


async def test_patch_reports_dnak_without_closing_the_modal():
    bridge = _DnakBridge()
    app = MonitorTuiApp(bridge)
    async with app.run_test() as pilot:
        objects = app.query_one("#objects")
        await _wait_for(pilot, lambda: objects.row_count == 2)
        app._selected_idno = 906
        app.refresh_fields()
        fields = app.query_one("#fields")
        await _wait_for(pilot, lambda: fields.row_count == 2)

        app.action_patch_selected()
        await _wait_for(pilot, lambda: len(app.screen_stack) > 1)

        screen = app.screen
        screen.on_input_submitted(
            type(screen._input).Submitted(screen._input, "50"))

        assert await _wait_for(
            pilot, lambda: "NOT written" in str(screen._status.render()))
        assert len(app.screen_stack) > 1  # modal stays open on failure
