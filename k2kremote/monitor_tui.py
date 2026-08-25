# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""``k2kmon tui`` — an interactive object browser, on top of the same
one-shot primitives `k2kmon`'s CLI modes already use.

Kept in its own module so `import textual` stays optional for everyone who
only ever runs `k2kmon read`/`patch`/`watch` from the command line —
`k2kremote/monitor.py` only imports this module inside the `tui` branch of
its dispatch.

Modeled on the sibling project eosed's TUI (`eosed/app.py`): a persistent
connection instead of one-shot invocations, and known fields decoded
alongside their raw bytes rather than shown as bare hex. Threading follows
this project's own convention (`k2kremote/refresh.py`'s `RefreshWorker`) —
a plain background `threading.Thread` marshaling results back via
`call_from_thread` — rather than Textual's `@work` decorator, which eosed
uses but this codebase does not.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from k2000.definitions import ObjectType
from k2kremote import k2kfields
from k2kremote.monitor import describe, hexdump


class _DeviceWorker(threading.Thread):
    """Runs device ops off the UI thread, one at a time, via a work queue.

    Simpler than `refresh.RefreshWorker`: no polling loop, no heartbeat —
    `k2kmon tui` has nothing that needs refreshing on its own; every screen
    asks for what it wants, when it wants it. `watch` mode is the one
    thing that IS continuous, and it runs as its own separate thread
    (`WatchScreen._poll`), not through this queue, since it never finishes
    a unit of work to hand back.
    """

    def __init__(self, bridge):
        super().__init__(daemon=True)
        self.bridge = bridge
        self._queue: "list[tuple[Callable, Callable]]" = []
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(0.05)
            self._wake.clear()
            with self._lock:
                job = self._queue.pop(0) if self._queue else None
            if job is None:
                continue
            thunk, on_result = job
            try:
                result = thunk(self.bridge)
                on_result(result, None)
            except Exception as exc:  # noqa: BLE001 -- surfaced to the UI, not swallowed
                on_result(None, exc)

    def submit(self, thunk: Callable, on_result: Callable) -> None:
        with self._lock:
            self._queue.append((thunk, on_result))
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()


class PatchScreen(ModalScreen):
    """Confirm and send a write to one known field. Mirrors `k2kmon patch`'s
    own safety discipline (typed confirmation, read-back verification via
    `patch_object_bytes` itself) rather than a lighter one for the TUI."""

    BINDINGS = [("escape", "close", "Cancel")]

    CSS = """
    PatchScreen { align: center middle; }
    #patchbox { width: 60; padding: 1 2; border: round $warning;
                background: $surface; }
    #patchwarn { color: $warning; text-style: bold; }
    #patchinput { margin-top: 1; }
    """

    def __init__(self, app_ref, obj_type: ObjectType, idno: int, offset: int,
                current_hex: str, field_name: str):
        super().__init__()
        self._app = app_ref
        self._obj_type = obj_type
        self._idno = idno
        self._offset = offset
        self._field_name = field_name
        self._current_hex = current_hex
        self._input = Input(placeholder="new hex bytes, e.g. 28", id="patchinput")
        self._status = Static("", id="patchstatus")

    def compose(self) -> ComposeResult:
        with Container(id="patchbox"):
            yield Static(f"{self._field_name}  (type={self._obj_type.name}"
                         f" id={self._idno} offset={self._offset})")
            yield Static(f"current: {self._current_hex}")
            yield Static("!!! WRITES A LIVE OBJECT ON THE K2000 !!!",
                         id="patchwarn")
            yield self._input
            yield self._status

    def on_mount(self) -> None:
        self._input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        hex_data = event.value.strip()
        try:
            data = bytes.fromhex(hex_data)
        except ValueError as exc:
            self._status.update(f"not valid hex: {exc}")
            return
        if not data:
            self._status.update("no bytes to write")
            return
        self._status.update("writing ...")

        def op(bridge):
            return bridge.patch_object_bytes(self._obj_type, self._idno,
                                            self._offset, data)

        self._app.device_op(op, self._done)

    def _done(self, result, error) -> None:
        if error is not None:
            self._status.update(f"NOT written: {error}")
            return
        self._app.pop_screen()
        self._app.notify_status(f"wrote {result.hex()} to offset {self._offset}")
        self._app.refresh_fields()

    def action_close(self) -> None:
        self.app.pop_screen()


class WatchScreen(ModalScreen):
    """Live decoded SysEx traffic — k2kmon's own `watch` mode, no eosed
    equivalent to model this on. Runs its own poll thread (not through
    `_DeviceWorker`'s one-shot queue, since it never returns a single
    result) reading `bridge.client.midi_in` directly and rendering each
    message with `monitor.describe()` -- the exact function the CLI
    `watch` command already uses, so the two never decode differently."""

    BINDINGS = [("escape", "close", "Close")]

    CSS = """
    WatchScreen { align: center middle; }
    #watchbox { width: 90%; height: 90%; border: round $accent;
                background: $surface; padding: 1; }
    #watchlog { height: 1fr; }
    """

    def __init__(self, app_ref):
        super().__init__()
        self._app = app_ref
        self._lines: List[str] = []
        self._log = Static("", id="watchlog")
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def compose(self) -> ComposeResult:
        with Container(id="watchbox"):
            yield Static("watching (nothing is transmitted) -- escape to close")
            yield self._log

    def on_mount(self) -> None:
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def on_unmount(self) -> None:
        self._stop.set()

    def _poll(self) -> None:
        bridge = self._app.bridge
        while not self._stop.is_set():
            got = bridge.client.midi_in.get_message()
            if got is None:
                time.sleep(0.01)
                continue
            data, _delta = got
            line = describe(data, "in")
            self._app.call_from_thread(self._append, line)

    def _append(self, line: str) -> None:
        self._lines.append(f"[{time.strftime('%H:%M:%S')}] {line}")
        self._lines = self._lines[-200:]  # bounded -- this is a monitor, not a log file
        self._log.update("\n".join(self._lines))

    def action_close(self) -> None:
        self._stop.set()
        self.app.pop_screen()


class MonitorTuiApp(App):
    """`k2kmon tui` — browse objects, see known fields decoded, patch them."""

    CSS = """
    #panes { height: 1fr; }
    #objects { width: 40%; }
    #fields { width: 60%; }
    #status { height: auto; color: $text-muted; }
    #typebank { height: 3; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("w", "watch", "Watch traffic"),
        Binding("enter", "patch_selected", "Patch field", show=False),
        Binding("p", "patch_selected", "Patch field"),
    ]

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._worker = _DeviceWorker(bridge)
        self._obj_type = ObjectType.Program
        self._bank = 2
        self._selected_idno: Optional[int] = None
        self.last_status = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="titlebar")
        with Horizontal(id="typebank"):
            yield Input(value=self._obj_type.name, placeholder="type",
                       id="typeinput")
            yield Input(value=str(self._bank), placeholder="bank",
                       id="bankinput")
        with Horizontal(id="panes"):
            yield DataTable(id="objects")
            yield DataTable(id="fields")
        yield Static("", id="status")

    def on_mount(self) -> None:
        self._worker.start()
        objects = self.query_one("#objects", DataTable)
        objects.add_columns("Id", "Name", "Size", "RAM")
        objects.cursor_type = "row"
        fields = self.query_one("#fields", DataTable)
        fields.add_columns("Offset", "Name", "Decoded")
        fields.cursor_type = "row"
        self.action_refresh()

    def on_unmount(self) -> None:
        self._worker.stop()

    def device_op(self, thunk: Callable, on_result: Callable) -> None:
        """Run `thunk(bridge)` off the UI thread; `on_result(value, error)`
        always runs back on it."""
        self._worker.submit(
            thunk, lambda r, e: self.call_from_thread(on_result, r, e))

    def notify_status(self, text: str) -> None:
        self.last_status = text
        self.query_one("#status", Static).update(text)

    # -- object list ----------------------------------------------------

    def action_refresh(self) -> None:
        self.notify_status(f"listing {self._obj_type.name} bank {self._bank} ...")

        def op(bridge):
            return bridge.list_bank(self._obj_type, self._bank)

        self.device_op(op, self._objects_loaded)

    def _objects_loaded(self, result, error) -> None:
        if error is not None:
            self.notify_status(f"list failed: {error}")
            return
        found, done = result
        table = self.query_one("#objects", DataTable)
        table.clear()
        for info in found:
            table.add_row(str(info.idno), info.name, str(info.size),
                          "RAM" if info.in_ram else "ROM", key=str(info.idno))
        note = "" if done else "  (no ENDOFBANK -- possibly incomplete)"
        self.notify_status(f"{len(found)} object(s){note}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "objects":
            self._selected_idno = int(str(event.row_key.value))
            self.refresh_fields()

    # -- field pane -------------------------------------------------------

    def refresh_fields(self) -> None:
        if self._selected_idno is None:
            return
        idno = self._selected_idno
        relevant = [(offset, field) for (obj_type, offset), field
                   in k2kfields.KNOWN_FIELDS.items() if obj_type == self._obj_type]
        if not relevant:
            table = self.query_one("#fields", DataTable)
            table.clear()
            self.notify_status(f"no known fields for {self._obj_type.name} objects")
            return

        def op(bridge):
            return {offset: bridge.read_object_bytes(self._obj_type, idno,
                                                     offset, field.size)
                   for offset, field in relevant}

        self.device_op(op, self._fields_loaded)

    def _fields_loaded(self, result, error) -> None:
        if error is not None:
            self.notify_status(f"read failed: {error}")
            return
        table = self.query_one("#fields", DataTable)
        table.clear()
        for offset, raw in sorted(result.items()):
            field = k2kfields.KNOWN_FIELDS[(self._obj_type, offset)]
            decoded = k2kfields.describe_field(self._obj_type, offset, raw)
            table.add_row(str(offset), field.name, decoded, key=str(offset))
        self.notify_status(f"object {self._selected_idno}: "
                           f"{len(result)} known field(s)")

    # -- patch ------------------------------------------------------------

    def action_patch_selected(self) -> None:
        fields_table = self.query_one("#fields", DataTable)
        if fields_table.cursor_row is None or self._selected_idno is None:
            self.notify_status("select an object and a field first")
            return
        row_key = fields_table.coordinate_to_cell_key(
            (fields_table.cursor_row, 0)).row_key
        offset = int(str(row_key.value))
        field = k2kfields.KNOWN_FIELDS.get((self._obj_type, offset))
        if field is None:
            self.notify_status("not a known/patchable field")
            return

        def op(bridge):
            return bridge.read_object_bytes(self._obj_type, self._selected_idno,
                                           offset, field.size)

        def open_patch(current, error):
            if error is not None:
                self.notify_status(f"read failed: {error}")
                return
            self.push_screen(PatchScreen(
                self, self._obj_type, self._selected_idno, offset,
                current.hex(), field.name))

        self.device_op(op, open_patch)

    # -- watch --------------------------------------------------------------

    def action_watch(self) -> None:
        self.push_screen(WatchScreen(self))
