# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only -- never opens a MIDI port, per CLAUDE.md's hardware rule.

import threading
from types import SimpleNamespace

from k2000.definitions import ObjectType
from k2000.messages import Info

from k2kremote import k2kfields


def _program_field_count():
    """Rows the field pane shows for a Program.

    refresh_fields() filters KNOWN_FIELDS by the selected object type, so
    counting the whole registry would fail the moment a non-Program offset
    is registered -- against correct app behaviour.
    """
    return sum(1 for t, _ in k2kfields.KNOWN_FIELDS
               if t is ObjectType.Program)
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
        # Every offset in k2kfields.KNOWN_FIELDS, because that is exactly the
        # set the app reads -- a fake that answers only some of them makes the
        # field pane fail to populate and every later assertion fails on a
        # missing cell rather than on what it meant to test. Values chosen so
        # 906 decodes and 907 falls outside a formula's proven range.
        # 209 is not a registered field; it is the BLOCK-TYPE byte that
        # offset 210's entry is gated on, and refresh_fields() reads it
        # too, so a fake without it fails the read rather than the assert.
        self._data = {906: {215: b"\x28", 199: bytes([79]), 261: bytes([36]),
                            242: bytes([37]),
                            209: bytes([50]), 210: bytes([24]),
                            91: bytes([46]),
                            # RESOLUTION_NOTES §90, measured 2026-09-25/26
                            196: bytes([43]), 180: bytes([43]),
                            43: bytes([73]), 231: bytes([24])},
                      907: {215: b"\x05", 199: bytes([50]), 261: bytes([0]),
                            242: bytes([256 - 32]),
                            209: bytes([50]), 210: bytes([100]),
                            91: bytes([186]),
                            196: bytes([213]), 180: bytes([0]),
                            43: bytes([100]), 231: bytes([236])}}
        # every canned program must answer every known offset: if only 906
        # is checked, adding a field leaves 907 raising KeyError, which
        # device_op swallows into a "read failed" status and the test then
        # fails on a missing row instead of on this guard
        # ...and filtered by object type, for the same reason the row count
        # is: refresh_fields() only ever reads offsets registered for the
        # selected type, so a future Keymap or Setup entry must not make this
        # guard demand Program data for it
        for idno, data in self._data.items():
            missing = set(o for t, o in k2kfields.KNOWN_FIELDS
                          if t is ObjectType.Program) - set(data)
            assert not missing, (
                f"fake bridge has no data for offsets {missing} on {idno}")
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
        assert await _wait_for(pilot, lambda: fields.row_count == _program_field_count())
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
        await _wait_for(pilot, lambda: fields.row_count == _program_field_count())
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
        await _wait_for(pilot, lambda: fields.row_count == _program_field_count())

        app.action_patch_selected()
        assert await _wait_for(pilot, lambda: len(app.screen_stack) > 1)

        screen = app.screen
        screen._input.value = "50"
        screen.on_input_submitted(
            type(screen._input).Submitted(screen._input, "50"))

        assert await _wait_for(pilot, lambda: len(bridge.patches) == 1)
        obj_type, idno, offset, data = bridge.patches[0]
        # rows are sorted by offset ascending (_fields_loaded); cursor_row 0
        # is the LOWEST registered Program offset. That has moved twice now --
        # 199, then 91 (LFO1 MnRate) at §70, now 43 (FX Wet/Dry) at §90 --
        # so if this fails after a registry addition, check whether the new
        # field simply sorts first before hunting a bug.
        assert (obj_type, idno, offset, data) == (ObjectType.Program, 906,
                                                   43, bytes.fromhex("50"))
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
        await _wait_for(pilot, lambda: fields.row_count == _program_field_count())

        app.action_patch_selected()
        await _wait_for(pilot, lambda: len(app.screen_stack) > 1)

        screen = app.screen
        screen.on_input_submitted(
            type(screen._input).Submitted(screen._input, "50"))

        assert await _wait_for(
            pilot, lambda: "NOT written" in str(screen._status.render()))
        assert len(app.screen_stack) > 1  # modal stays open on failure


class _SlowPatchBridge(FakeK2000Bridge):
    """Holds the write open so the dialog can be poked while it is in flight."""

    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def patch_object_bytes(self, obj_type, idno, offset, data):
        self.started.set()
        self.release.wait(5)
        return super().patch_object_bytes(obj_type, idno, offset, data)


async def _open_patch_dialog(app, pilot):
    objects = app.query_one("#objects")
    await _wait_for(pilot, lambda: objects.row_count == 2)
    app._selected_idno = 906
    app.refresh_fields()
    fields = app.query_one("#fields")
    await _wait_for(pilot, lambda: fields.row_count == _program_field_count())
    app.action_patch_selected()
    assert await _wait_for(pilot, lambda: len(app.screen_stack) > 1)
    return app.screen


async def test_escape_during_a_write_neither_cancels_nor_closes():
    """A SysEx write cannot be called back once it is on the wire.

    Escape popped the modal anyway, and the result callback then popped
    *again* -- closing whatever screen had taken its place -- and reported the
    write as done for an operation the user had been told was cancelled.
    """
    bridge = _SlowPatchBridge()
    app = MonitorTuiApp(bridge)
    async with app.run_test() as pilot:
        screen = await _open_patch_dialog(app, pilot)
        screen.on_input_submitted(
            type(screen._input).Submitted(screen._input, "50"))
        assert await _wait_for(pilot, lambda: bridge.started.is_set())

        screen.action_close()
        await pilot.pause()
        assert app.screen is screen, "the modal closed over a write in flight"
        assert "cannot be cancelled" in str(screen._status.render())

        bridge.release.set()
        assert await _wait_for(pilot, lambda: len(app.screen_stack) == 1)
        assert len(bridge.patches) == 1


async def test_a_second_enter_does_not_queue_a_second_write():
    """Enter twice wrote the same field twice -- once per keypress."""
    bridge = _SlowPatchBridge()
    app = MonitorTuiApp(bridge)
    async with app.run_test() as pilot:
        screen = await _open_patch_dialog(app, pilot)
        submitted = type(screen._input).Submitted(screen._input, "50")
        screen.on_input_submitted(submitted)
        assert await _wait_for(pilot, lambda: bridge.started.is_set())

        screen.on_input_submitted(submitted)
        assert "already in flight" in str(screen._status.render())

        bridge.release.set()
        assert await _wait_for(pilot, lambda: len(app.screen_stack) == 1)
        assert len(bridge.patches) == 1, bridge.patches


def test_worker_stop_waits_for_the_op_in_flight():
    """Shutdown must not race `bridge.close()`.

    `k2kmon`'s own `finally: bridge.close()` runs the moment the app's
    `on_unmount` returns. With stop() only setting a flag, that deleted the
    rtmidi ports underneath a thread still inside a read -- a use-after-free
    in a C extension, which is not something Python will raise for you.
    """
    import threading
    import time

    from k2kremote.monitor_tui import _DeviceWorker

    started = threading.Event()
    finished = threading.Event()

    def slow(_bridge):
        started.set()
        time.sleep(0.3)
        finished.set()
        return "done"

    worker = _DeviceWorker(SimpleNamespace())
    worker.start()
    worker.submit(slow, lambda r, e: None)
    # Wait for the op to actually BE in flight rather than sleeping and hoping:
    # a fixed sleep is a race on a loaded runner, and stop() before the job is
    # picked up would make this pass for the wrong reason.
    assert started.wait(5), "the worker never picked the job up"

    worker.stop()

    assert finished.is_set(), "stop() returned with the device op still running"
    assert not worker.is_alive()


def test_worker_hands_nothing_back_once_it_is_stopping():
    """A callback after shutdown targets an event loop that is gone.

    Every callback here is marshalled with `call_from_thread`, which waits on
    the loop -- so firing one during shutdown is both useless and, while the UI
    thread is inside the join, a deadlock.
    """
    import threading
    import time

    from k2kremote.monitor_tui import _DeviceWorker

    called = []
    running = threading.Event()

    def slow(_bridge):
        running.set()
        time.sleep(0.2)
        return "done"

    worker = _DeviceWorker(SimpleNamespace())
    worker.start()
    worker.submit(slow, lambda r, e: called.append((r, e)))
    running.wait(2)

    worker.stop()
    time.sleep(0.4)          # long enough for the op to have finished and fired

    assert called == []
