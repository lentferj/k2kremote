# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Uses a fake bridge and short timings — no hardware, no real time waits.

import threading
import time

import numpy as np

from k2000.definitions import Button

from k2kremote.refresh import Frame, RefreshWorker


class FakeBridge:
    """Records calls; get_graphics returns a tiny frame and signals an event."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.refreshed = threading.Event()
        self._panels = 0  # number of pending unsolicited PANEL "events"
        self._names = {}  # idno -> current object name, for rename/lookup tests
        # The mirrored screen text get_screen_text() returns; tests mutate it to
        # simulate navigating onto a destructive (delete/object-utility) screen.
        self.screen_text = "\n".join([""] * 7 + ["A B C D E F"])

    def press_button(self, button):
        with self.lock:
            self.calls.append(("press", button))

    def alpha_wheel(self, clicks):
        with self.lock:
            self.calls.append(("wheel", clicks))

    def panic(self):
        with self.lock:
            self.calls.append(("panic", None))

    def object_name(self, obj_type, idno):
        with self.lock:
            self.calls.append(("dir", (obj_type, idno)))
        return self._names.get(idno, "OLD NAME")

    def rename(self, obj_type, idno, name):
        with self.lock:
            self.calls.append(("rename", (obj_type, idno, name)))
        self._names[idno] = name
        return name

    def reselect_program(self, idno):
        with self.lock:
            self.calls.append(("reselect", idno))

    def get_graphics(self):
        with self.lock:
            self.calls.append(("graphics", None))
        self.refreshed.set()
        return np.zeros((240, 64), dtype=np.uint8)

    def get_screen_text(self):
        with self.lock:
            self.calls.append(("text", None))
            text = self.screen_text
        self.refreshed.set()
        return text

    def poll_panel(self):
        with self.lock:
            if self._panels:
                self._panels -= 1
                return True
        return False

    def queue_panel(self):
        with self.lock:
            self._panels += 1

    def kinds(self):
        with self.lock:
            return [c[0] for c in self.calls]


def _worker(bridge, frames, errors=None, **kw):
    return RefreshWorker(
        bridge,
        on_frame=frames.append,
        on_error=(errors.append if errors is not None else None),
        **kw,
    )


def _drain_startup(bridge):
    """Wait for the one-shot startup refresh, then reset the call log."""
    assert bridge.refreshed.wait(timeout=2.0)
    time.sleep(0.05)
    with bridge.lock:
        bridge.calls.clear()
    bridge.refreshed.clear()


def test_startup_heartbeat_refreshes_once():
    bridge = FakeBridge()
    frames = []
    worker = _worker(bridge, frames, heartbeat=0.05)
    worker.start()
    try:
        assert bridge.refreshed.wait(timeout=2.0)
        time.sleep(0.05)
        assert "graphics" in bridge.kinds()
        assert frames and isinstance(frames[0], Frame)
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_press_is_sent_before_refresh_and_then_settles():
    bridge = FakeBridge()
    frames = []
    # Long heartbeat so the only refresh we see is the post-press settle one.
    worker = _worker(bridge, frames, settle=0.1, heartbeat=100.0)
    worker.start()
    try:
        _drain_startup(bridge)
        worker.press(Button.Program)
        assert bridge.refreshed.wait(timeout=2.0)
        time.sleep(0.05)
        kinds = bridge.kinds()
        # The press is delivered, and a graphics refresh follows it.
        assert kinds[0] == "press"
        assert "graphics" in kinds
        assert kinds.index("press") < kinds.index("graphics")
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_burst_of_presses_collapses_to_one_refresh():
    bridge = FakeBridge()
    frames = []
    worker = _worker(bridge, frames, settle=0.15, heartbeat=100.0)
    worker.start()
    try:
        _drain_startup(bridge)
        for _ in range(5):
            worker.press(Button.Plus)
            time.sleep(0.02)  # faster than settle -> deadline keeps moving out
        assert bridge.refreshed.wait(timeout=2.0)
        time.sleep(0.05)
        kinds = bridge.kinds()
        assert kinds.count("press") == 5
        # Only one refresh for the whole burst (settle deadline kept resetting).
        assert kinds.count("graphics") == 1
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_submit_runs_a_plan_in_order_and_drops_zero_wheels():
    bridge = FakeBridge()
    worker = _worker(bridge, [], settle=0.05, heartbeat=100.0)
    worker.start()
    try:
        _drain_startup(bridge)
        worker.submit([
            ("wheel", 5),
            ("wheel", 0),  # dropped
            ("press", Button.CursorRight),
            ("wheel", -3),
        ])
        assert bridge.refreshed.wait(timeout=2.0)  # settle refresh after the plan
        time.sleep(0.05)
        kinds = bridge.kinds()
        assert kinds[:3] == ["wheel", "press", "wheel"]  # zero-wheel dropped, order kept
        assert kinds.count("graphics") == 1
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_panic_runs_and_jumps_the_queue():
    bridge = FakeBridge()
    worker = _worker(bridge, [], settle=0.05, heartbeat=100.0)
    worker.start()
    try:
        _drain_startup(bridge)
        worker.panic()
        deadline = time.time() + 2.0
        while "panic" not in bridge.kinds() and time.time() < deadline:
            time.sleep(0.01)
        assert "panic" in bridge.kinds()
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_pause_silences_all_device_traffic():
    bridge = FakeBridge()
    worker = _worker(bridge, [], heartbeat=0.05, mirror_panel=False)
    worker.start()
    try:
        _drain_startup(bridge)
        worker.set_paused(True)
        time.sleep(0.2)  # let any in-flight refresh finish
        with bridge.lock:
            bridge.calls.clear()
        time.sleep(0.3)  # several heartbeats would have fired if not paused
        assert bridge.kinds() == []  # nothing sent while paused
        bridge.refreshed.clear()
        worker.set_paused(False)
        assert bridge.refreshed.wait(timeout=2.0)  # resume triggers a refresh
        assert "graphics" in bridge.kinds()
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_refresh_defers_slow_graphics_when_a_press_is_waiting():
    bridge = FakeBridge()
    frames = []
    worker = RefreshWorker(bridge, on_frame=frames.append, mirror_panel=False)
    # A keypress is already queued -> the refresh should deliver text but skip
    # the ~0.8 s GETGRAPHICS so the press isn't blocked.
    worker._commands.append(("press", Button.Program))
    worker._do_refresh()
    assert "text" in bridge.kinds() and "graphics" not in bridge.kinds()
    assert frames and frames[-1].pixels is None  # text-only frame

    # With the queue drained, the next refresh fetches graphics.
    worker._commands.clear()
    with bridge.lock:
        bridge.calls.clear()
    worker._do_refresh()
    assert "graphics" in bridge.kinds()


def test_force_refresh_runs_even_while_paused():
    bridge = FakeBridge()
    frames = []
    worker = _worker(bridge, frames, heartbeat=100.0, mirror_panel=False)
    worker.start()
    try:
        _drain_startup(bridge)
        worker.set_paused(True)
        time.sleep(0.1)
        with bridge.lock:
            bridge.calls.clear()
        frames.clear()
        bridge.refreshed.clear()
        worker.force_refresh()  # one-shot, overrides pause
        assert bridge.refreshed.wait(timeout=2.0)
        time.sleep(0.05)
        assert "graphics" in bridge.kinds() and "text" in bridge.kinds()
        assert frames  # a frame was delivered
        assert worker.paused  # still paused afterward
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_wheel_zero_is_ignored():
    bridge = FakeBridge()
    worker = _worker(bridge, [], heartbeat=100.0)
    worker.start()
    try:
        worker.wheel(0)
        time.sleep(0.1)
        assert "wheel" not in bridge.kinds()
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_inbound_panel_triggers_refresh():
    bridge = FakeBridge()
    worker = _worker(bridge, [], settle=0.05, heartbeat=100.0, inbound_poll=0.05)
    worker.start()
    try:
        _drain_startup(bridge)
        bridge.queue_panel()  # the hardware "was touched"
        assert bridge.refreshed.wait(timeout=2.0)
        time.sleep(0.05)
        assert "graphics" in bridge.kinds()
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_refresh_fetches_both_planes_text_first():
    bridge = FakeBridge()
    frames = []
    worker = _worker(bridge, frames, heartbeat=0.05, mirror_panel=False)
    worker.start()
    try:
        assert bridge.refreshed.wait(timeout=2.0)
        time.sleep(0.1)
        kinds = bridge.kinds()
        assert "graphics" in kinds and "text" in kinds  # both planes every refresh
        assert kinds.index("text") < kinds.index("graphics")  # ALLTEXT delivered first
        # Two frames per refresh: a text-first frame, then one with pixels.
        assert any(f.pixels is not None and f.text_rows for f in frames)
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_connection_recovery_transitions():
    class Flaky(FakeBridge):
        fail = True

        def get_graphics(self):
            if self.fail:
                self.refreshed.set()
                raise TimeoutError("no reply")
            return super().get_graphics()

    bridge = Flaky()
    states = []
    worker = RefreshWorker(
        bridge, on_frame=lambda f: None, on_connection=states.append,
        heartbeat=0.05, mirror_panel=False,
    )
    worker.start()
    try:
        # First refresh fails: a single "disconnected" transition.
        deadline = time.time() + 2.0
        while False not in states and time.time() < deadline:
            time.sleep(0.01)
        assert states == [False]
        # Recover: the next heartbeat succeeds -> one "connected" transition.
        bridge.fail = False
        deadline = time.time() + 2.0
        while True not in states and time.time() < deadline:
            time.sleep(0.01)
        assert states == [False, True]
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_lookup_and_rename_program_repaints_and_refreshes():
    from k2000.definitions import ObjectType

    bridge = FakeBridge()
    bridge._names[201] = "CMI VOICES"
    worker = _worker(bridge, [], heartbeat=10, inbound_poll=10, settle=0.05)
    worker.start()
    try:
        got = []
        done = threading.Event()

        def on_result(name, error):
            got.append((name, error))
            done.set()

        worker.lookup_name(ObjectType.Program, 201, on_result)
        assert done.wait(1.0) and got[-1] == ("CMI VOICES", None)

        done.clear()
        bridge.refreshed.clear()
        worker.rename(ObjectType.Program, 201, "Wave Of Mutilation", on_result)
        assert done.wait(1.0) and got[-1] == ("Wave Of Mutilation", None)
        # The mirror is refreshed after a settle (so a stale screen is corrected
        # even when sitting on the renamed object).
        assert bridge.refreshed.wait(2.0)

        kinds = bridge.kinds()
        assert "rename" in kinds        # the SysEx CHANGE
        assert "reselect" in kinds      # Program repaint (re-enter the id)
        assert kinds.count("graphics") + kinds.count("text") > 0  # follow-up refresh
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_rename_non_program_does_not_reselect():
    from k2000.definitions import ObjectType

    bridge = FakeBridge()
    worker = _worker(bridge, [], heartbeat=10, inbound_poll=10, settle=0.05)
    worker.start()
    try:
        done = threading.Event()
        worker.rename(ObjectType.Keymap, 5, "My Keymap", lambda n, e: done.set())
        assert done.wait(1.0)
        assert "reselect" not in bridge.kinds()  # repaint trick is Program-only
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_error_is_reported_and_thread_survives():
    class Boom(FakeBridge):
        def get_graphics(self):
            self.refreshed.set()
            raise TimeoutError("no reply")

    bridge = Boom()
    errors = []
    worker = _worker(bridge, [], errors=errors, heartbeat=0.05)
    worker.start()
    try:
        assert bridge.refreshed.wait(timeout=2.0)
        time.sleep(0.05)
        assert errors and isinstance(errors[0], TimeoutError)
        assert worker.is_alive()
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_is_destructive_screen_flags_only_the_confirm_prompt():
    from k2kremote.refresh import is_destructive_screen

    # The actual commit prompt that precedes the rewrite (2026-06-25 flow):
    # "Are You sure?  Yes | No" — caught by the text and by the bare Yes/No row.
    assert is_destructive_screen(["Are You sure?"] + [""] * 5 + ["Yes      No"])
    assert is_destructive_screen(["Delete dependent objects?", "Yes  No"])
    # Structural Yes/No detection alone (wording unknown) is enough.
    assert is_destructive_screen(["Proceed?"] + [""] * 6 + ["Yes   No"])

    # Idle EARLIER screens in the delete flow are safe to poll, so they must stay
    # LIVE (not flagged) — freezing them just forces a Ctrl+r per line while you
    # navigate the ~12-line range list.
    assert not is_destructive_screen(
        ["Delete Selection:", "200...299|300...399|...|Everything", "", "OK  Cancel"])
    assert not is_destructive_screen(["Func:DELETE      Sel:4/4", "Select Next OK Cancel"])
    assert not is_destructive_screen(["Select database function:",
                                      "Move Copy Name Delete Dump Done"])
    # OK/Cancel is the *accept* button on ordinary dialogs — deliberately NOT a
    # trigger (it appears on the safe selection screen above).
    assert not is_destructive_screen(["Overwrite 201?"] + [""] * 6 + ["OK    Cancel"])
    # The name-edit dialog's six-label row (with its per-char Delete button) and a
    # plain screen are not flagged.
    assert not is_destructive_screen(
        ["Name: MYSOUND", "Delete Insert <<< >>> OK Cancel"])
    assert not is_destructive_screen(["", "A B C D E F"])


def test_heartbeat_gated_off_on_destructive_screen():
    bridge = FakeBridge()
    bridge.screen_text = "Delete dependent objects?\nYes  No"
    frames = []
    # Fast heartbeat: without the gate it would re-read many times.
    worker = _worker(bridge, frames, heartbeat=0.05, mirror_panel=False)
    worker.start()
    try:
        assert bridge.refreshed.wait(timeout=2.0)  # the one startup read
        time.sleep(0.4)  # several heartbeats would have fired if not gated
        assert worker.danger
        assert bridge.kinds().count("graphics") == 1  # startup only; gated after
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_destructive_screen_auto_pauses_then_resumes_on_force_refresh():
    bridge = FakeBridge()
    bridge.screen_text = "Are You sure?\n" + "\n" * 5 + "Yes      No"
    frames = []
    # Fast heartbeat + panel mirroring on: nothing must fire while auto-paused.
    worker = _worker(bridge, frames, heartbeat=0.05, settle=0.05, inbound_poll=0.03)
    worker.start()
    try:
        assert bridge.refreshed.wait(timeout=2.0)  # the startup read flags danger
        time.sleep(0.1)
        assert worker.danger
        # Auto-paused: no reads at all, even with a fast heartbeat and a panel event.
        with bridge.lock:
            bridge.calls.clear()
        bridge.queue_panel()        # a front-panel echo is ignored while auto-paused
        worker.request_refresh()    # so is an ordinary refresh request
        time.sleep(0.3)
        assert bridge.kinds().count("graphics") == 0
        # Leave the screen and force a refresh (Ctrl+r) — it reads, clears danger,
        # and the heartbeat resumes on its own.
        bridge.screen_text = "\n".join([""] * 7 + ["A B C D E F"])
        worker.force_refresh()
        deadline = time.time() + 2.0
        while worker.danger and time.time() < deadline:
            time.sleep(0.01)
        assert not worker.danger
        with bridge.lock:
            bridge.calls.clear()
        time.sleep(0.2)
        assert bridge.kinds().count("graphics") >= 1
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_force_refresh_reads_while_auto_paused_but_request_refresh_does_not():
    bridge = FakeBridge()
    # A confirmation prompt (bare Yes/No row) auto-pauses; Ctrl+r is the escape hatch.
    bridge.screen_text = "Are you sure?\n" + "\n" * 5 + "Yes      No"
    frames = []
    worker = _worker(bridge, frames, heartbeat=100.0, mirror_panel=False)
    worker.start()
    try:
        _drain_startup(bridge)      # startup read set danger
        assert worker.danger
        # An ordinary refresh request is ignored while auto-paused.
        bridge.refreshed.clear()
        worker.request_refresh()
        assert not bridge.refreshed.wait(timeout=0.3)
        assert bridge.kinds().count("graphics") == 0
        # ...but Ctrl+r (force_refresh) still reads.
        worker.force_refresh()
        assert bridge.refreshed.wait(timeout=2.0)
        assert "graphics" in bridge.kinds()
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_manual_refresh_mode_skips_heartbeat_but_honours_events():
    bridge = FakeBridge()
    frames = []
    worker = _worker(bridge, frames, heartbeat=None, settle=0.05, inbound_poll=0.03)
    worker.start()
    try:
        assert bridge.refreshed.wait(timeout=2.0)  # startup still draws once
        time.sleep(0.05)
        assert bridge.kinds().count("graphics") == 1
        with bridge.lock:
            bridge.calls.clear()
        bridge.refreshed.clear()
        # No periodic heartbeat in manual mode: nothing fires on its own.
        time.sleep(0.4)
        assert bridge.kinds().count("graphics") == 0
        # A front-panel event still refreshes the mirror.
        bridge.queue_panel()
        assert bridge.refreshed.wait(timeout=2.0)
        time.sleep(0.05)
        assert bridge.kinds().count("graphics") >= 1
    finally:
        worker.stop()
        worker.join(timeout=1.0)


