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


def _wait_for(bridge, kind, count=1, timeout=2.0):
    """Block until ``kind`` has been called ``count`` times; True if it was.

    The worker now spends as little wire time as it can get away with, so a
    GETGRAPHICS can legitimately arrive a settle-retry later than the ALLTEXT
    that preceded it. Waiting for the call we actually care about beats sleeping
    for a guessed interval.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if bridge.kinds().count(kind) >= count:
            return True
        time.sleep(0.01)
    return False


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
    worker = _worker(bridge, frames, settle=0.1, settle_retry=0.05, heartbeat=100.0)
    worker.start()
    try:
        _drain_startup(bridge)
        worker.press(Button.Program)
        assert _wait_for(bridge, "graphics")
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
    worker = _worker(bridge, frames, settle=0.15, settle_retry=0.05, heartbeat=100.0)
    worker.start()
    try:
        _drain_startup(bridge)
        for _ in range(5):
            worker.press(Button.Plus)
            time.sleep(0.02)  # faster than settle -> deadline keeps moving out
        assert _wait_for(bridge, "graphics")
        time.sleep(0.1)  # let any further refresh land, so the count means something
        kinds = bridge.kinds()
        assert kinds.count("press") == 5
        # Only one refresh for the whole burst (settle deadline kept resetting).
        assert kinds.count("graphics") == 1
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_submit_runs_a_plan_in_order_and_drops_zero_wheels():
    bridge = FakeBridge()
    worker = _worker(bridge, [], settle=0.05, settle_retry=0.05, heartbeat=100.0)
    worker.start()
    try:
        _drain_startup(bridge)
        worker.submit([
            ("wheel", 5),
            ("wheel", 0),  # dropped
            ("press", Button.CursorRight),
            ("wheel", -3),
        ])
        assert _wait_for(bridge, "graphics")  # settle refresh after the plan
        kinds = bridge.kinds()
        # Order kept, zero-wheel dropped — and the two wheel turns stay separate
        # even though they bracket a press: a plan is replayed exactly as written.
        assert kinds[:3] == ["wheel", "press", "wheel"]
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
        # A physical press goes through the settle, exactly like one of ours, so
        # a touch that changed nothing costs one cheap text read — not the ~1.1 s
        # of both planes a forced refresh would buy, on a device already busy
        # doing whatever the press asked for.
        assert _wait_for(bridge, "text")
        time.sleep(0.15)
        assert bridge.kinds().count("graphics") == 0
        # When the press did change the screen, the pixels follow.
        bridge.screen_text = "\n".join(["Program 042"] + [""] * 6 + ["A B C D E F"])
        bridge.queue_panel()
        assert _wait_for(bridge, "graphics")
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
        heartbeat=0.05, mirror_panel=False, disconnect_grace=0.05,
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
        # The heartbeat is polling again. On a quiet screen it stops at the cheap
        # ALLTEXT (nothing to repaint), so "is it alive?" is a text read...
        assert _wait_for(bridge, "text", count=2)
        # ...and the moment the screen actually changes, it buys the pixels.
        bridge.screen_text = "\n".join(["MOVED ON"] + [""] * 6 + ["A B C D E F"])
        assert _wait_for(bridge, "graphics")
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
        # A front-panel event still refreshes the mirror — cheaply when the
        # screen is unchanged, both planes once it actually moves.
        bridge.queue_panel()
        assert _wait_for(bridge, "text")
        bridge.screen_text = "\n".join(["Program 042"] + [""] * 6 + ["A B C D E F"])
        bridge.queue_panel()
        assert _wait_for(bridge, "graphics")
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_device_op_runs_on_worker_thread_even_while_paused():
    bridge = FakeBridge()
    worker = _worker(bridge, [], heartbeat=100.0, mirror_panel=False)
    worker.start()
    try:
        _drain_startup(bridge)
        worker.set_paused(True)  # destructive Master ops run with the mirror paused
        results = []
        done = threading.Event()

        def on_result(result, error):
            results.append((result, error))
            done.set()

        worker.device_op(lambda b: ("ran", b), on_result)
        assert done.wait(timeout=2.0)
        result, error = results[0]
        assert error is None
        assert result[0] == "ran"
        assert result[1] is bridge   # fn is handed the worker's own bridge
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_device_op_reports_errors_without_killing_the_worker():
    bridge = FakeBridge()
    worker = _worker(bridge, [], heartbeat=100.0, mirror_panel=False)
    worker.start()
    try:
        _drain_startup(bridge)
        results = []
        done = threading.Event()

        def on_result(result, error):
            results.append((result, error))
            done.set()

        def boom(_bridge):
            raise RuntimeError("device said no")

        worker.device_op(boom, on_result)
        assert done.wait(timeout=2.0)
        result, error = results[0]
        assert result is None
        assert "device said no" in error
        assert worker.is_alive()
    finally:
        worker.stop()
        worker.join(timeout=1.0)


# --- the cheap-probe refresh strategy ---------------------------------------
# ALLTEXT (321 bytes) stands in for the delta request the K2000 protocol does
# not have: a heartbeat that finds it unchanged buys no 2561-byte GETGRAPHICS
# and repaints nothing. See the refresh module docstring.

def test_quiet_heartbeat_stops_at_the_cheap_text_read():
    bridge = FakeBridge()
    frames = []
    worker = _worker(bridge, frames, heartbeat=0.05, mirror_panel=False)
    worker.start()
    try:
        assert _wait_for(bridge, "graphics")  # the startup read buys both planes
        _drain_startup(bridge)
        frames.clear()
        assert _wait_for(bridge, "text", count=4)   # the heartbeat keeps polling
        assert bridge.kinds().count("graphics") == 0  # ...but only the cheap half
        assert frames == []                           # and the UI is left alone
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_changed_text_buys_the_pixel_plane_again():
    bridge = FakeBridge()
    frames = []
    worker = _worker(bridge, frames, heartbeat=0.05, mirror_panel=False)
    worker.start()
    try:
        assert _wait_for(bridge, "graphics")
        _drain_startup(bridge)
        frames.clear()
        bridge.screen_text = "\n".join(["Program 999"] + [""] * 6 + ["A B C D E F"])
        assert _wait_for(bridge, "graphics")
        assert any(f.pixels is not None for f in frames)
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_reverse_video_change_alone_counts_as_a_change():
    """The cursor moving inverts a cell without altering any character."""
    class Attrs(FakeBridge):
        reverse = ["0" * 40] * 8

        def get_screen_text_attrs(self):
            with self.lock:
                self.calls.append(("text", None))
                text, reverse = self.screen_text, list(self.reverse)
            self.refreshed.set()
            return text, reverse

    bridge = Attrs()
    frames = []
    worker = _worker(bridge, frames, heartbeat=0.05, mirror_panel=False)
    worker.start()
    try:
        assert _wait_for(bridge, "graphics")
        _drain_startup(bridge)
        assert _wait_for(bridge, "text", count=3)
        assert bridge.kinds().count("graphics") == 0  # quiet: no pixel read
        bridge.reverse = ["1" + "0" * 39] * 8         # only the mask moved
        assert _wait_for(bridge, "graphics")
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_pixel_plane_is_reread_once_it_goes_stale():
    """A graphics-only change is invisible to the text compare, so bound the age."""
    bridge = FakeBridge()
    worker = _worker(bridge, [], heartbeat=0.05, graphics_max_age=0.3,
                     mirror_panel=False)
    worker.start()
    try:
        assert _wait_for(bridge, "graphics")
        _drain_startup(bridge)
        # Nothing about the screen ever changes, yet the pixels get refetched.
        assert _wait_for(bridge, "graphics", timeout=2.0)
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_explicit_refresh_always_reads_both_planes():
    """Ctrl+r means "just ask again" — "nothing changed" is not an answer."""
    bridge = FakeBridge()
    worker = _worker(bridge, [], heartbeat=100.0, mirror_panel=False)
    worker.start()
    try:
        assert _wait_for(bridge, "graphics")
        _drain_startup(bridge)
        worker.force_refresh()  # the screen is byte-identical to the last read
        assert _wait_for(bridge, "graphics")
        with bridge.lock:
            bridge.calls.clear()
        worker.request_refresh()
        assert _wait_for(bridge, "graphics")
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_settle_takes_a_second_look_before_paying_for_pixels():
    bridge = FakeBridge()
    worker = _worker(bridge, [], settle=0.05, settle_retry=0.05, heartbeat=100.0,
                     mirror_panel=False)
    worker.start()
    try:
        assert _wait_for(bridge, "graphics")
        _drain_startup(bridge)
        worker.press(Button.Program)
        # First look is cheap and finds nothing; the second gives up guessing
        # and reads the pixels, so a graphics-only change still lands.
        assert _wait_for(bridge, "graphics")
        assert bridge.kinds().count("text") >= 2
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_a_fast_spin_becomes_one_wheel_message():
    """Ten queued clicks are one PANEL delta, not ten throttled messages."""
    bridge = FakeBridge()
    worker = _worker(bridge, [], settle=100.0, heartbeat=100.0, mirror_panel=False)
    # Queue the burst before the thread starts, so it is all pending at once.
    for _ in range(10):
        worker.wheel(1)
    worker.wheel(-3)
    worker.start()
    try:
        deadline = time.time() + 2.0
        while ("wheel", 7) not in bridge.calls and time.time() < deadline:
            time.sleep(0.01)
        wheels = [c for c in bridge.calls if c[0] == "wheel"]
        assert wheels == [("wheel", 7)]  # 10 x +1 and one -3, summed and sent once
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_a_plan_is_never_merged_or_split_by_a_keystroke():
    bridge = FakeBridge()
    worker = _worker(bridge, [], settle=100.0, heartbeat=100.0, mirror_panel=False)
    # A name-entry plan's repeated steps must survive verbatim: the K2000's
    # multi-tap counts distinct presses, and adjacent wheel steps in a plan are
    # deliberate, not a spin to be summed.
    worker.submit([("wheel", 1), ("wheel", 1), ("press", Button.Number2)])
    worker.wheel(9)  # a keystroke racing the plan cannot land inside it
    worker.start()
    try:
        deadline = time.time() + 2.0
        while len([c for c in bridge.calls if c[0] in ("wheel", "press")]) < 4 \
                and time.time() < deadline:
            time.sleep(0.01)
        assert [c for c in bridge.calls if c[0] in ("wheel", "press")] == [
            ("wheel", 1), ("wheel", 1), ("press", Button.Number2), ("wheel", 9),
        ]
    finally:
        worker.stop()
        worker.join(timeout=1.0)


# --- "the device is busy" is not "the device is gone" -----------------------

def test_is_busy_screen_only_matches_seen_wording():
    from k2kremote.refresh import is_busy_screen, is_destructive_screen

    assert is_busy_screen(["Opening file", "", "", "", "", "", "", ""])
    assert is_busy_screen(["", "", "Reading file  BOOT.MAC", "", "", "", "", ""])
    assert not is_busy_screen(["ProgramMode", "", "", "", "", "", "", "A B C"])
    # Busy and destructive are separate ideas: busy is not a hold.
    assert not is_destructive_screen(["Opening file", "", "", "", "", "", "", ""])
    assert not is_busy_screen(["Are You sure?", "", "", "", "", "", "", "Yes  No"])


def test_busy_screen_skips_the_pixel_read():
    """A 963 ms GETGRAPHICS is the last thing a device doing disk I/O needs."""
    bridge = FakeBridge()
    bridge.screen_text = "\n".join(["Opening file"] + [""] * 7)
    frames = []
    worker = _worker(bridge, frames, heartbeat=0.05, mirror_panel=False)
    worker.start()
    try:
        assert _wait_for(bridge, "text", count=3)
        assert bridge.kinds().count("graphics") == 0
        assert worker.danger is False          # busy is not a destructive hold
        # ...and once the operation finishes, normal service resumes.
        bridge.screen_text = "\n".join([""] * 7 + ["A B C D E F"])
        assert _wait_for(bridge, "graphics")
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_busy_screen_does_not_report_a_disconnection():
    """The reported symptom: a front-panel load made the mirror cry disconnect."""
    class Busy(FakeBridge):
        fail = False

        def get_screen_text(self):
            text = super().get_screen_text()
            if self.fail:
                raise TimeoutError("device is busy reading a file")
            return text

    bridge = Busy()
    bridge.screen_text = "\n".join(["Reading file"] + [""] * 7)
    states = []
    worker = RefreshWorker(bridge, on_frame=lambda f: None, on_error=lambda e: None,
                           on_connection=states.append, heartbeat=0.05,
                           mirror_panel=False)
    worker.start()
    try:
        assert _wait_for(bridge, "text", count=2)
        assert states == [True]                 # connected on the first good read
        bridge.fail = True                      # now it stops answering, mid-load
        time.sleep(0.4)
        assert states == [True], "a busy device must not read as disconnected"
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_a_genuinely_absent_device_still_reports_disconnection():
    """The softening must not swallow a real disconnection on an ordinary screen."""
    class Gone(FakeBridge):
        def get_screen_text(self):
            raise TimeoutError("nothing there")

    states = []
    worker = RefreshWorker(Gone(), on_frame=lambda f: None, on_error=lambda e: None,
                           on_connection=states.append, heartbeat=0.05,
                           mirror_panel=False, disconnect_grace=0.05)
    worker.start()
    try:
        deadline = time.time() + 2.0
        while False not in states and time.time() < deadline:
            time.sleep(0.01)
        assert states and states[0] is False
    finally:
        worker.stop()
        worker.join(timeout=1.0)


# --- progress screens name what they are working on -------------------------

def test_progress_markers_match_the_variable_tail():
    """The K2000 writes "Deleting <the thing>" / "Please wait ...", so these are
    substring matches, never equality. Confirmed live 2026-08-16."""
    from k2kremote.refresh import is_busy_screen, is_destructive_screen

    def screen(line):
        return ["", "", line, "", "", "", "", ""]

    for line in ("Deleting Program 200", "Deleting SYNTHETICA 2", "Deleting ..."):
        assert is_destructive_screen(screen(line)), line
    for line in ("Please wait ...", "Please wait - Loading BOOT.MAC",
                 "Opening file FAVS/AFRICA", "Reading file BASS.KRZ"):
        assert is_busy_screen(screen(line)), line

    # A rewrite in progress is the §9 lock-up state: a hold, not merely busy.
    assert not is_busy_screen(screen("Deleting Program 200"))
    assert not is_destructive_screen(screen("Please wait ..."))


def test_a_brief_silence_is_not_a_disconnection():
    """Any disk operation silences the K2000; it comes back on its own.

    The first attempt keyed on reading the screen that says so — but a long load
    stops the device answering *before* that screen is ever read, which is why it
    still reported disconnections. Elapsed time needs no cooperation from a
    device that has stopped talking.
    """
    class Intermittent(FakeBridge):
        silent = False

        def get_screen_text(self):
            if self.silent:
                raise TimeoutError("busy")
            return super().get_screen_text()

    bridge = Intermittent()
    states = []
    worker = RefreshWorker(bridge, on_frame=lambda f: None, on_error=lambda e: None,
                           on_connection=states.append, heartbeat=0.02,
                           mirror_panel=False, disconnect_grace=1.0)
    worker.start()
    try:
        assert _wait_for(bridge, "text")
        deadline = time.time() + 1.0
        while states != [True] and time.time() < deadline:
            time.sleep(0.01)
        assert states == [True]
        bridge.silent = True          # a disk op starts; no screen ever read
        time.sleep(0.4)               # well inside the grace window
        assert states == [True], "a brief silence must not read as disconnected"
        bridge.silent = False         # the operation finishes
        time.sleep(0.2)
        assert states == [True], "and no flap on the way back"
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_silence_past_the_grace_window_is_a_disconnection():
    class Gone(FakeBridge):
        def get_screen_text(self):
            raise TimeoutError("nothing there")

    states = []
    worker = RefreshWorker(Gone(), on_frame=lambda f: None, on_error=lambda e: None,
                           on_connection=states.append, heartbeat=0.02,
                           mirror_panel=False, disconnect_grace=0.2)
    worker.start()
    try:
        deadline = time.time() + 3.0
        while False not in states and time.time() < deadline:
            time.sleep(0.01)
        assert states == [False]
    finally:
        worker.stop()
        worker.join(timeout=1.0)


# --- silent-but-present is not disconnected ---------------------------------
# Verified live 2026-08-16: a K2000 disk load silences the unit for *minutes*.
# It answers nothing, so no screen text reaches us and no elapsed-time rule can
# tell "busy" from "unplugged". The ports stay enumerated throughout, and that
# is the only signal that still works once the device has stopped talking.

class _SilentBridge(FakeBridge):
    """Answers nothing; reports whether its ports are still there."""

    present = True

    def get_screen_text(self):
        raise TimeoutError("device is busy loading")

    def ports_present(self):
        return self.present


def test_a_silent_but_plugged_in_device_reports_waiting_not_disconnected():
    bridge = _SilentBridge()
    conn, waiting = [], []
    worker = RefreshWorker(bridge, on_frame=lambda f: None, on_error=lambda e: None,
                           on_connection=conn.append, on_waiting=waiting.append,
                           heartbeat=0.02, mirror_panel=False, disconnect_grace=0.1)
    worker.start()
    try:
        deadline = time.time() + 2.0
        while not waiting and time.time() < deadline:
            time.sleep(0.01)
        assert waiting == [True]
        assert worker.waiting is True
        time.sleep(0.4)                      # well past the grace window
        assert conn == [], "a busy device must never be called disconnected"
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_ports_gone_still_reports_a_disconnection():
    bridge = _SilentBridge()
    bridge.present = False
    conn = []
    worker = RefreshWorker(bridge, on_frame=lambda f: None, on_error=lambda e: None,
                           on_connection=conn.append, heartbeat=0.02,
                           mirror_panel=False, disconnect_grace=0.1)
    worker.start()
    try:
        deadline = time.time() + 2.0
        while False not in conn and time.time() < deadline:
            time.sleep(0.01)
        assert conn == [False]
    finally:
        worker.stop()
        worker.join(timeout=1.0)


def test_waiting_clears_when_the_device_comes_back():
    bridge = _SilentBridge()
    waiting = []
    worker = RefreshWorker(bridge, on_frame=lambda f: None, on_error=lambda e: None,
                           on_waiting=waiting.append, heartbeat=0.02,
                           mirror_panel=False)
    worker.start()
    try:
        deadline = time.time() + 2.0
        while not waiting and time.time() < deadline:
            time.sleep(0.01)
        assert waiting == [True]
        # The load finishes and the K2000 starts answering again.
        bridge.get_screen_text = lambda: FakeBridge.get_screen_text(bridge)
        deadline = time.time() + 2.0
        while waiting == [True] and time.time() < deadline:
            time.sleep(0.01)
        assert waiting == [True, False]
        assert worker.waiting is False
    finally:
        worker.stop()
        worker.join(timeout=1.0)
