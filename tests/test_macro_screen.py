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


async def test_push_arms_but_does_not_write():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("b")            # make a change
        await pilot.press("p")
        assert screen._armed, "p must only arm"
        assert "macro push" not in app.paused_for, "p alone must not write"


async def test_a_second_p_still_does_not_write():
    """The confirm is a DIFFERENT key: p twice is a double-tap, and a double-tap
    must not be able to write to the instrument."""
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("b")
        await pilot.press("p")
        await pilot.press("p")
        await pilot.pause()
        assert "macro push" not in app.paused_for


async def test_w_commits_the_armed_push():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("b")
        await pilot.press("p")
        await pilot.press("w")
        await pilot.pause()
        assert "macro push" in app.paused_for


async def test_w_does_nothing_when_no_write_is_armed():
    app = Harness()
    async with app.run_test() as pilot:
        await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert "macro push" not in app.paused_for


async def test_escape_disarms_a_pending_push():
    app = Harness()
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("b")
        await pilot.press("p")
        await pilot.press("escape")
        assert not screen._armed
        await pilot.press("w")
        await pilot.pause()
        assert "macro push" not in app.paused_for


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


async def test_browser_list_follows_the_cursor_off_screen():
    """The macro list scrolled to keep the cursor visible; the browser did not,
    so walking past the bottom of a long directory lost the ">" entirely."""
    from k2kremote.disk_browse import Item

    app = Harness(op_result=("\\", [Item(f"DIR{i:02d}", True, "")
                                    for i in range(40)]))
    async with app.run_test() as pilot:
        app.push_screen(DiskBrowserScreen(app))
        await pilot.pause(); await pilot.pause()
        screen = app.screen
        assert len(screen._items) == 40
        for _ in range(30):
            await pilot.press("down")
        await pilot.pause()
        assert screen._index == 30
        height = screen._scroll.scrollable_content_region.height
        top = int(screen._scroll.scroll_offset.y)
        assert top <= screen._index < top + height, (
            f"cursor {screen._index} outside the visible window {top}..{top+height}")


async def test_both_screens_say_they_are_experimental():
    """The warning belongs where the finger is, not only in the README."""
    from textual.widgets import Static

    app = Harness()
    async with app.run_test() as pilot:
        await _open(app)
        await pilot.pause(); await pilot.pause()
        warn = str(app.screen.query_one("#macrowarn", Static).render())
        assert "EXPERIMENTAL" in warn
        # The mirror is paused for the duration of every op, so the hardware LCD
        # is the only live view exactly when something goes wrong.
        assert "LCD" in warn and "PAUSED" in warn

    app2 = Harness(op_result=("\\", []))
    async with app2.run_test() as pilot:
        app2.push_screen(DiskBrowserScreen(app2))
        await pilot.pause(); await pilot.pause()
        warn2 = str(app2.screen.query_one("#browsewarn", Static).render())
        assert "EXPERIMENTAL" in warn2 and "LCD" in warn2




# --- save destination: show it, and two ways to change it -------------------

async def test_opening_save_shows_the_destination():
    """The bug this exists for: a save silently landed in \\-BAESSE\\-SLAP\\
    because nothing showed where it would go before it went there."""
    app = Harness(op_result="\\-BAESSE\\-SLAP\\")
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("s")
        await pilot.pause(); await pilot.pause()
        assert screen._save_name.display
        assert "\\-BAESSE\\-SLAP\\" in screen._status.render().__str__()


async def test_save_to_root_and_pick_directory_are_inert_without_the_prompt_open():
    app = Harness()
    async with app.run_test() as pilot:
        await _open(app)
        await pilot.pause(); await pilot.pause()
        before = app.paused_for.copy()
        await pilot.press("ctrl+d")
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert app.paused_for == before, "neither must touch the device unasked"


async def test_save_to_root_updates_the_shown_destination():
    app = Harness(op_result="\\")
    async with app.run_test() as pilot:
        screen = await _open(app)
        await pilot.pause(); await pilot.pause()
        await pilot.press("s")
        await pilot.pause(); await pilot.pause()
        app.op_result = "\\"          # what reset_to_root + disk_page_path give
        await pilot.press("ctrl+d")
        await pilot.pause(); await pilot.pause()
        assert "\\" in screen._status.render().__str__()
        assert screen._save_name.display, "still on the name field afterwards"


async def test_use_directory_dismisses_with_the_current_path():
    app = Harness()
    async with app.run_test() as pilot:
        screen = DiskBrowserScreen(app, directory_mode=True)
        screen._path = "\\-BAESSE\\-SLAP\\"
        app.push_screen(screen, lambda path: results.append(path))
        results = []
        await pilot.pause(); await pilot.pause()
        await pilot.press("u")
        await pilot.pause(); await pilot.pause()
        assert results == ["\\-BAESSE\\-SLAP\\"]


async def test_directory_mode_refuses_to_open_a_file():
    """Enter on a file in directory-pick mode must not behave as if a file had
    been chosen -- there is no macro entry here to point at one."""
    from k2kremote.disk_browse import Item

    app = Harness(op_result=("\\", [Item("BOOT     .MAC", False, ".5K")]))
    async with app.run_test() as pilot:
        screen = DiskBrowserScreen(app, directory_mode=True)
        app.push_screen(screen)
        await pilot.pause(); await pilot.pause()
        assert not screen._items[0].is_dir
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DiskBrowserScreen), "must not have dismissed"
        assert "u to use" in screen._hint.render().__str__()
