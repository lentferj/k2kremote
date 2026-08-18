# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Drives the live-macro screen through Textual's test harness, with a stub
# worker in place of a K2000. No hardware, no MIDI. This screen has broken four
# times in ways only pressing keys revealed — a focus-stealing scroll container,
# a hidden Input eating every letter, a blind tuple unpack, and a binding that
# collided with the panel's own F8 — so the keys are pressed here too.

import threading

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from k2kremote.app import DiskBrowserScreen, MacroScreen
from k2kmaced.macfile import MacroEntry, MacroTable

TABLE = MacroTable([
    MacroEntry(drive=1, bank=200, mode=3, path="\\", filename="A.KRZ"),
    MacroEntry(drive=1, bank=300, mode=2, path="\\DIR\\", filename="B.KRZ"),
])


class StubWorker:
    """`device_op` calls back from another thread, as the real worker does."""

    def __init__(self, payload=None, error=None):
        self.payload = TABLE.serialize() if payload is None else payload
        self.error = error

    def device_op(self, fn, on_result):
        threading.Thread(target=on_result, args=(self.payload, self.error),
                         daemon=True).start()


class Harness(App):
    """Just enough app: the screen calls master_apply and resume_mirror."""

    def __init__(self, op_result=None, op_error=None):
        super().__init__()
        self.op_result = op_result
        self.op_error = op_error
        self.resumed = 0
        self.paused_for = []

    def compose(self) -> ComposeResult:
        yield Static("", id="titlebar")

    def master_apply(self, summary, thunk, on_result):
        self.paused_for.append(summary)
        self.call_later(on_result, self.op_result, self.op_error)

    def resume_mirror(self):
        self.resumed += 1

    def _titlebar_text(self):
        return ""


async def _open(app, worker=None):
    screen = MacroScreen(worker or StubWorker())
    app.push_screen(screen)
    return screen


async def test_screen_loads_the_table_and_resumes_the_mirror():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause()
        await pilot.pause()
        assert len(screen._entries()) == 2
        assert app.resumed >= 1, "an idle screen must not hold the mirror paused"


async def test_cursor_keys_move_the_selection():
    """The scroll container used to take focus and eat these."""
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        assert screen._index == 0
        await pilot.press("down")
        assert screen._index == 1
        await pilot.press("up")
        assert screen._index == 0


async def test_letter_keys_reach_the_screen_not_a_hidden_input():
    """`display = False` does not remove a widget from the focus chain, so a
    hidden Input once swallowed every letter — `a` typed into a field nobody
    could see instead of adding an entry."""
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        before = len(screen._entries())
        await pilot.press("a")
        await pilot.pause()
        assert len(screen._entries()) == before + 1
        assert screen._path.display, "add should open the path editor"


async def test_delete_removes_an_entry():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("delete")
        assert len(screen._entries()) == 1


async def test_bank_and_mode_cycle_and_mark_the_table_changed():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        bank = screen._entries()[0].bank
        await pilot.press("b")
        assert screen._entries()[0].bank != bank
        assert screen._dirty, "an edit must mark the table as changed"


async def test_push_refuses_until_something_changed():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("p")
        assert not screen._armed, "nothing changed, so there is nothing to arm"


async def test_push_arms_before_it_writes():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("b")            # make a change
        await pilot.press("p")
        assert screen._armed, "the first p must only arm"


async def test_save_prompt_opens_and_ctrl_t_reaches_the_browser():
    """Ctrl+t crashed here: the browser's callback unpacked a None result."""
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert screen._save_name.display
        await pilot.press("ctrl+t")
        await pilot.pause(); await pilot.pause()
        assert isinstance(app.screen, DiskBrowserScreen)


async def test_browser_survives_a_callback_with_no_result_and_no_error():
    """The crash itself, isolated: `self._path, self._items = result` on None."""
    app = Harness(op_result=None, op_error=None)
    async with app.run_test() as pilot:
        app.push_screen(DiskBrowserScreen(app))
        await pilot.pause(); await pilot.pause()
        assert isinstance(app.screen, DiskBrowserScreen), "it must still be up"


async def test_a_read_failure_reports_and_does_not_strand_the_mirror():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app, StubWorker(payload=None, error="no device"))
        await pilot.pause(); await pilot.pause()
        assert screen._table is None
        assert app.resumed >= 1, "a failed read must still resume the mirror"
