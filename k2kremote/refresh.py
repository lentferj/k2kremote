# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# The event-driven (never-poll-the-device) refresh strategy and its timing
# constants encode RE'd K2000 behaviour documented in
# mpc2emu/docs/k2000r_midi_comms.md, verified on real K2000R hardware.
#
# k2kremote is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# k2kremote is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Event-driven GETGRAPHICS scheduler — the load-bearing decision.

The K2000's old CPU crashes / garbles the LCD under a MIDI flood, so there is
**no poll loop**. A single worker thread owns the bridge and drives one
throttled output stream, refreshing the screen only when something could have
changed:

* a **button press / wheel turn** goes out immediately (prioritized over
  refreshes so typing stays responsive), then schedules a refresh after a
  ~0.5 s **settle** (the LCD redraw is slow — reading sooner returns blanks);
* an explicit **refresh request** (e.g. an inbound physical-panel PANEL) is
  honoured;
* an idle **heartbeat** every ~2.5 s catches anything else.

All three collapse to at most one GETGRAPHICS per loop iteration. A burst of
keystrokes keeps pushing the settle deadline out, so only one refresh fires once
typing pauses.

Internal scheduling waits on a :class:`threading.Condition` (we time our own
state — we never poll the *device*). Blocking MIDI I/O lives here, off the UI
thread; results are handed back via the ``on_frame`` / ``on_error`` callbacks,
which a Textual app should marshal with ``call_from_thread``.
"""

from __future__ import annotations

import re
import threading
from collections import deque
from time import monotonic
from typing import Callable, Deque, List, Optional, Tuple, Union

from attrs import define, field

from k2000.definitions import Button

# RE'd timing (see module docstring / mpc2emu k2000r_midi_comms.md).
SETTLE = 0.35       # seconds to wait after a press before reading the redrawn LCD
HEARTBEAT = 2.5     # idle refresh cadence; well under the flood threshold
INBOUND_POLL = 0.25  # how often to drain the local RX buffer for inbound PANEL

# We gate **only on the final confirmation prompt** — the screen whose next
# keypress (Yes) actually commits the destructive change and starts the object
# rewrite that crashes the K2000's CPU if polled. Earlier, *idle* screens in the
# flow (the "Delete Selection: 200...299 | … | Everything" range list, object
# menus) are SAFE to poll — the unit isn't rewriting anything there — so we leave
# the mirror fully live on them; freezing them just forces a Ctrl+r per line while
# navigating, which is useless. Verified live 2026-06-25: the lockup needs a poll
# *during the rewrite*, which only begins after the Yes on "Are You sure? Yes|No".
# See the project memory `lockup-heartbeat-during-deletes`.
#
# Two signals, both pointing at that confirmation step:
#  * body text containing "are you sure" (the prompt itself), and
#  * the soft-key row reduced to a bare **Yes/No** pair (structural — robust to
#    wording, and it doesn't trip the name-edit dialog's six-label row, nor the
#    selection screen, which proceeds with OK rather than Yes/No).
# OK/Cancel is deliberately NOT a trigger: it is the *accept* button on ordinary
# (idle, safe) dialogs including the delete-selection screen, so gating on it would
# re-freeze navigation. Destructive commits on the K2000 confirm with Yes/No.
_DESTRUCTIVE_MARKERS = ("are you sure",)
_CONFIRM_SOFT_PAIR = {"yes", "no"}


def _is_confirm_dialog(text_rows) -> bool:
    """True when the bottom soft-key row is a bare Yes/No pair (a commit prompt)."""
    bottom = text_rows[-1] if text_rows else ""
    words = {w.lower() for w in re.findall(r"[A-Za-z]+", bottom)}
    return words == _CONFIRM_SOFT_PAIR


def is_destructive_screen(text_rows) -> bool:
    """True when the mirrored LCD is at a destructive **commit** prompt.

    Two independent signals for the confirmation step (the keypress after it starts
    the object rewrite that crashes the K2000): the body text "are you sure", or a
    structural :func:`_is_confirm_dialog` (a bare Yes/No soft-key pair). Used to
    auto-pause all device polling while that prompt is shown. Idle earlier screens
    (range/selection lists, object menus) are intentionally NOT flagged so the
    mirror stays live for navigation. Conservative by design: a false positive only
    freezes the mirror until Ctrl+r; a false negative risks a hardware lockup.
    """
    joined = " ".join(text_rows).lower()
    if any(marker in joined for marker in _DESTRUCTIVE_MARKERS):
        return True
    return _is_confirm_dialog(text_rows)

# Internal command kinds queued ahead of refreshes.
_Press = Tuple[str, Button]   # ("press", button)
_Wheel = Tuple[str, int]      # ("wheel", clicks)
_Command = Union[_Press, _Wheel]


@define
class Frame:
    """One screen capture handed to the UI.

    In graphics mode ``pixels`` is the numpy array from GETGRAPHICS and
    ``text_rows`` the optional ALLTEXT layer (for soft-key labels). In fast
    text mode ``pixels`` is ``None`` and ``text_rows`` is the whole screen.
    """

    pixels: object  # numpy ndarray from bridge.get_graphics(), or None
    text_rows: List[str] = field(factory=list)
    # Per-row ALLTEXT high-bit mask ("1"/"0" per cell): the K2000's reverse-video
    # flag for any cells it inverts. (The name-edit cursor is NOT among them — it
    # is in neither plane and is tracked in software; see k2kremote.name_cursor.)
    reverse: List[str] = field(factory=list)

    @property
    def is_text_only(self) -> bool:
        return self.pixels is None


class RefreshWorker(threading.Thread):
    """Owns the MIDI bridge on its own thread; serializes presses + refreshes."""

    def __init__(
        self,
        bridge,
        on_frame: Callable[[Frame], None],
        on_error: Optional[Callable[[Exception], None]] = None,
        on_connection: Optional[Callable[[bool], None]] = None,
        *,
        settle: float = SETTLE,
        heartbeat: Optional[float] = HEARTBEAT,
        inbound_poll: float = INBOUND_POLL,
        mirror_panel: bool = True,
    ):
        super().__init__(name="k2kremote-refresh", daemon=True)
        self._bridge = bridge
        self._on_frame = on_frame
        self._on_error = on_error
        self._on_connection = on_connection
        self._settle = settle
        # heartbeat=None => manual-refresh-only mode: no periodic poll at all; the
        # mirror updates solely on front-panel events and explicit refreshes. The
        # numeric value is still kept as the error-backoff base.
        self._heartbeat_enabled = heartbeat is not None
        self._heartbeat = heartbeat if heartbeat is not None else HEARTBEAT
        self._inbound_poll = inbound_poll
        self._mirror_panel = mirror_panel

        self._cond = threading.Condition()
        self._commands: Deque[_Command] = deque()
        self._refresh_pending = False
        self._settle_due: Optional[float] = None
        self._next_heartbeat = 0.0
        self._running = False
        self._paused = False
        # The mirrored screen is a destructive/object-table op (delete/confirm/
        # erase). While true the worker is fully quiescent — it auto-pauses, sending
        # nothing, until an explicit force_refresh (Ctrl+r) reads a safe screen.
        self._danger = False
        self._backoff = 0.0  # grows while the device isn't answering (e.g. mid-load)
        self._last_pixels = None  # most recent GETGRAPHICS, for the text-first frame
        self._connected: Optional[bool] = None  # unknown until the first refresh
        self._prioritize_graphics = False  # never skip GETGRAPHICS (e.g. name dialog)

    # -- public API (thread-safe) -------------------------------------------
    def press(self, button: Button) -> None:
        """Queue a front-panel button press (high priority)."""
        with self._cond:
            self._commands.append(("press", button))
            self._cond.notify()

    def wheel(self, clicks: int) -> None:
        """Queue an alpha-wheel turn of ``clicks`` (signed, high priority)."""
        if clicks == 0:
            return
        with self._cond:
            self._commands.append(("wheel", clicks))
            self._cond.notify()

    def panic(self) -> None:
        """Jump the queue with a MIDI all-notes-off (highest priority)."""
        with self._cond:
            self._commands.appendleft(("panic", None))
            self._cond.notify()

    def type_name(self, target: str, start_col: int = 0) -> None:
        """Queue a feedback-driven name entry into the open K2000 name dialog.

        Runs :func:`k2kremote.text_entry.type_name` inline on the worker thread
        (it reads the screen back between keystrokes), so it blocks the worker
        for the duration — intentional for this multi-second operation.
        ``start_col`` is the field offset the device cursor is parked on (the
        app passes its tracked cursor position) so typing begins there.
        """
        if not target:
            return
        with self._cond:
            self._commands.append(("type_name", (target, start_col)))
            self._cond.notify()

    def lookup_name(self, obj_type, idno: int, on_result) -> None:
        """Read an object's current name (DIR) for the rename tool's preview.

        ``on_result(name, error)`` is invoked on the worker thread with exactly
        one of the two set; the callback must marshal back to the UI thread.
        """
        with self._cond:
            self._commands.append(("lookup", (obj_type, idno, on_result)))
            self._cond.notify()

    def rename(self, obj_type, idno: int, name: str, on_result) -> None:
        """Rename a stored object in one SysEx CHANGE (no multi-tap).

        For a Program the device is re-selected afterwards to force the LCD (and
        our mirror) to repaint with the new name. ``on_result(name, error)`` is
        invoked on the worker thread with exactly one set; it must marshal back
        to the UI thread.
        """
        with self._cond:
            self._commands.append(("rename", (obj_type, idno, name, on_result)))
            self._cond.notify()

    def device_op(self, fn, on_result) -> None:
        """Run a one-shot bridge operation ``fn(bridge)`` on the worker thread.

        For the destructive Master utilities (delete / move / delete-bank), which
        rewrite the object database directly. The app pauses the worker first so no
        heartbeat or settle follows the op; the command itself runs even while
        paused (like ``force_refresh``). ``on_result(result, error)`` is invoked on
        the worker thread with exactly one set; it must marshal back to the UI."""
        with self._cond:
            self._commands.append(("device_op", (fn, on_result)))
            self._cond.notify()

    def submit(self, commands) -> None:
        """Queue a pre-built command sequence atomically (e.g. a name-entry plan).

        The whole plan lands on the queue under one lock, so it can't be split
        by an interleaving keystroke. Each command is a ``("press", Button)`` or
        ``("wheel", clicks)`` tuple — the same shape :meth:`press`/:meth:`wheel`
        produce — and inherits their high priority over refreshes.
        """
        commands = [c for c in commands if not (c[0] == "wheel" and c[1] == 0)]
        if not commands:
            return
        with self._cond:
            self._commands.extend(commands)
            self._cond.notify()

    def set_prioritize_graphics(self, on: bool) -> None:
        """When ``on``, never skip the GETGRAPHICS half of a refresh.

        Normally the pixel plane is deferred while a keypress is queued (so
        navigation stays snappy). The app turns this on while the naming dialog
        is open so the surrounding graphics chrome (the dialog rules and
        soft-label bar) stays fresh as the name is edited. (The cursor itself is
        software-tracked — see :mod:`k2kremote.name_cursor` — so it no longer
        depends on this, but keeping the plane current avoids a stale frame.)
        """
        with self._cond:
            self._prioritize_graphics = on

    def request_refresh(self) -> None:
        """Ask for a screen refresh as soon as the output stream is free.

        Ignored while a destructive screen is mirrored (the worker is auto-paused);
        use :meth:`force_refresh` (Ctrl+r) to read once the operation is done.
        """
        with self._cond:
            self._refresh_pending = True
            self._cond.notify()

    def force_refresh(self) -> None:
        """Queue an immediate one-shot full refresh that runs even while paused.

        Use for a stale/garbled mirror or to peek after an operation. It does
        not change the pause state.
        """
        with self._cond:
            self._commands.append(("refresh", None))
            self._cond.notify()

    def set_paused(self, paused: bool) -> None:
        """Pause/resume **all** automatic device traffic.

        While paused the worker sends no GETGRAPHICS/ALLTEXT (no heartbeat, no
        settle, no inbound poll) — essential before a SCSI load/save or any
        long K2000 operation, whose busy CPU can crash under MIDI traffic.
        Resuming requests an immediate refresh.
        """
        with self._cond:
            self._paused = paused
            if not paused:
                self._refresh_pending = True
            self._cond.notify()

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def danger(self) -> bool:
        """True while the mirrored screen is a destructive/object-table op.

        In this state the worker is auto-paused — it sends nothing at all (like a
        manual pause) until a force_refresh (Ctrl+r) reads a safe screen. The app
        surfaces it so the user knows the mirror is intentionally frozen.
        """
        return self._danger

    def stop(self) -> None:
        with self._cond:
            self._running = False
            self._cond.notify()

    # -- thread body ---------------------------------------------------------
    def run(self) -> None:
        self._running = True
        # Draw once at startup so the mirror isn't blank before the first event
        # (a plain refresh request, not the heartbeat, so manual-refresh mode —
        # which has no heartbeat — still gets its initial frame).
        with self._cond:
            self._refresh_pending = True
        while True:
            # Drain the local RX buffer for unsolicited PANEL messages (the K2000
            # echoes its own front-panel presses when XMIT Buttons=On). This is a
            # local read, not device traffic, so it doesn't count toward the flood
            # floor. Done outside the lock and only when no command is queued.
            # Skipped while quiescent (manual pause or a destructive screen) so a
            # front-panel press can't trigger a read into an object rewrite.
            if (self._mirror_panel and not self._paused and not self._danger
                    and not self._commands):
                try:
                    if self._bridge.poll_panel():
                        self.request_refresh()
                except Exception as exc:
                    self._report_error(exc)

            with self._cond:
                if not self._running:
                    return
                command = self._commands.popleft() if self._commands else None
                if command is None:
                    # Quiescent: a manual pause, or a destructive screen we have
                    # auto-paused on. Send nothing until a command (e.g. Ctrl+r
                    # force_refresh, or resume) wakes us.
                    if self._paused or self._danger:
                        self._cond.wait()
                        continue
                    timeout = self._idle_timeout()
                    if timeout != 0:
                        wait = timeout
                        # Cap the wait so we revisit the RX buffer for inbound PANEL.
                        if self._mirror_panel:
                            wait = self._inbound_poll if wait is None else min(wait, self._inbound_poll)
                        self._cond.wait(timeout=wait)
                        continue
                    # A refresh is due now.
                    self._refresh_pending = False
                    self._settle_due = None
                    self._next_heartbeat = monotonic() + self._heartbeat

            # MIDI I/O happens outside the lock so the UI can keep enqueuing.
            if command is not None:
                self._run_command(command)
            else:
                self._do_refresh()

    # -- internals -----------------------------------------------------------
    def _idle_timeout(self) -> Optional[float]:
        """Seconds to wait before the next refresh; 0 = due now; None = wait.

        Only reached when not quiescent (see ``run``); a destructive screen is
        handled there as a full auto-pause. The heartbeat is omitted in
        manual-refresh mode (``heartbeat=None``).
        """
        now = monotonic()
        deadlines: List[float] = []
        if self._heartbeat_enabled:
            deadlines.append(self._next_heartbeat)
        if self._settle_due is not None:
            deadlines.append(self._settle_due)
        if self._refresh_pending:
            deadlines.append(now)  # do it immediately
        if not deadlines:
            return None  # nothing scheduled — wait until an event notifies us
        return max(0.0, min(deadlines) - now)

    def _run_command(self, command: _Command) -> None:
        kind, payload = command
        if kind == "refresh":
            # One-shot full refresh — runs even while paused (it's an explicit,
            # user-requested redraw), and schedules no follow-up settle.
            self._do_refresh()
            return
        if kind == "lookup":
            obj_type, idno, on_result = payload
            try:
                on_result(self._bridge.object_name(obj_type, idno), None)
            except Exception as exc:  # deliver to the tool, not the global error sink
                on_result(None, f"{type(exc).__name__}: {exc}")
            return
        if kind == "device_op":
            # A one-shot destructive Master op (delete/move/delete-bank). Runs even
            # while paused; schedules no follow-up refresh — the app keeps the mirror
            # paused until the user resumes, so no read can land during any rewrite.
            fn, on_result = payload
            try:
                on_result(fn(self._bridge), None)
            except Exception as exc:
                on_result(None, f"{type(exc).__name__}: {exc}")
            return
        if kind == "rename":
            from k2000.definitions import ObjectType
            obj_type, idno, name, on_result = payload
            try:
                confirmed = self._bridge.rename(obj_type, idno, name)
                if obj_type is ObjectType.Program:
                    self._bridge.reselect_program(idno)  # force the panel to repaint
                on_result(confirmed, None)
            except Exception as exc:
                on_result(None, f"{type(exc).__name__}: {exc}")
                return
            # Refresh the mirror AFTER a settle, not immediately: if the mirror is
            # sitting on the renamed object, the device needs a moment to switch
            # program and repaint, so an instant read would catch the old screen.
            # The delayed read (same path as a post-press settle) picks up the new
            # name. Even when the device shows a different object, this is a cheap,
            # safe extra refresh.
            with self._cond:
                if not self._paused:
                    self._settle_due = monotonic() + self._settle
            return
        try:
            if kind == "press":
                self._bridge.press_button(payload)
            elif kind == "wheel":
                self._bridge.alpha_wheel(payload)
            elif kind == "panic":
                self._bridge.panic()
            elif kind == "type_name":
                from k2kremote import text_entry
                target, start_col = payload
                text_entry.type_name(self._bridge, target, start_col=start_col)
        except Exception as exc:  # keep the worker alive on transient MIDI errors
            self._report_error(exc)
            return
        # Schedule a settle refresh; further keystrokes push this deadline out.
        # (Not while paused — stay silent.)
        with self._cond:
            if not self._paused:
                self._settle_due = monotonic() + self._settle

    def _do_refresh(self) -> None:
        # Fetch ALLTEXT first (~320 bytes ≈ 0.1 s) and deliver it immediately,
        # so text changes appear promptly, THEN fetch GETGRAPHICS (~2560 bytes
        # ≈ 0.8 s over 31250-baud MIDI) and deliver again so the cursor /
        # graphics catch up. This keeps navigation feeling responsive even
        # though the pixel-accurate frame is inherently slow to transmit.
        try:
            text_rows, reverse = self._fetch_text()
        except Exception as exc:
            self._on_refresh_error(exc)
            return
        # Gate the heartbeat on what's on screen: if this is a destructive /
        # object-table operation, stop polling until it clears (see _idle_timeout).
        self._danger = is_destructive_screen(text_rows)
        self._on_frame(Frame(pixels=self._last_pixels, text_rows=text_rows, reverse=reverse))

        # If a keypress is already waiting, don't block ~0.8 s on the full
        # GETGRAPHICS — process the input first (snappy navigation). The graphics
        # plane is fetched by the settle refresh once navigation pauses, or by
        # the heartbeat, so it always catches up. (Skipped when graphics is
        # prioritized — e.g. the name dialog, where the cursor matters.)
        if self._commands and not self._prioritize_graphics:
            return

        try:
            pixels = self._bridge.get_graphics()
        except Exception as exc:
            self._on_refresh_error(exc)
            return
        self._backoff = 0.0
        self._last_pixels = pixels
        self._set_connected(True)  # only after a full (both-planes) success
        self._on_frame(Frame(pixels=pixels, text_rows=text_rows, reverse=reverse))

    def _fetch_text(self):
        """Return ``(text_rows, reverse_mask)`` from ALLTEXT.

        Prefers the bridge's high-bit-aware reader (so the reverse-video cursor
        survives), falling back to plain text for older/fake bridges.
        """
        attrs = getattr(self._bridge, "get_screen_text_attrs", None)
        if attrs is not None:
            text, reverse = attrs()
            return text.split("\n"), reverse
        return self._bridge.get_screen_text().split("\n"), []

    def _on_refresh_error(self, exc: Exception) -> None:
        # The device isn't answering — likely busy (SCSI load/save) or
        # disconnected. Back off so we don't keep hammering its CPU, which can
        # crash it. Grows to a 20 s cap; resets on the next full success.
        self._set_connected(False)
        with self._cond:
            self._backoff = min(max(self._backoff * 2, self._heartbeat), 20.0)
            self._next_heartbeat = monotonic() + self._backoff
        self._report_error(exc)

    def _set_connected(self, connected: bool) -> None:
        """Fire the connection callback only on a state change."""
        if connected == self._connected:
            return
        self._connected = connected
        if self._on_connection is not None:
            self._on_connection(connected)

    def _report_error(self, exc: Exception) -> None:
        if self._on_error is not None:
            self._on_error(exc)
