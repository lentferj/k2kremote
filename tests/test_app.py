# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only: --demo frame, no MIDI hardware is ever opened.

import pytest

textual = pytest.importorskip("textual", reason="textual not installed")


def test_soft_labels_splits_bottom_row():
    from k2kremote.app import soft_labels, _SOFT_KEYS, _TEXT_COLS

    # Build a bottom row by placing each label at its own (rounded) zone start,
    # so the split is an exact round-trip.
    bounds = [round(i * _TEXT_COLS / _SOFT_KEYS) for i in range(_SOFT_KEYS + 1)]
    zones = ["Alg", "Key", "Pit", "Amp", "Flt", "Mor"]
    row = list(" " * _TEXT_COLS)
    for i, zone in enumerate(zones):
        for j, ch in enumerate(zone):
            row[bounds[i] + j] = ch
    labels = soft_labels([""] * 7 + ["".join(row)])
    assert labels == zones


def test_soft_labels_handles_empty():
    from k2kremote.app import soft_labels

    assert soft_labels([]) == [""] * 6


def test_soft_labels_keeps_word_whole_across_boundary():
    # "Format" sits at cols 28-33, straddling the old rounded F5/F6 split at 33,
    # which used to chop it into "Forma" + "t". Word-centre assignment keeps it
    # whole in F5.
    from k2kremote.app import soft_labels, _TEXT_COLS

    row = list(" " * _TEXT_COLS)
    for j, ch in enumerate("Format"):   # cols 28..33
        row[28 + j] = ch
    for j, ch in enumerate("more>"):    # cols 35..39
        row[35 + j] = ch
    labels = soft_labels([""] * 7 + ["".join(row)])
    assert labels[4] == "Format"
    assert labels[5] == "more>"


def test_wrap_blocks_never_splits_a_block():
    from k2kremote.app import wrap_blocks

    blocks = ["Alt+X panic", "F7 Edit", "F8 Exit", "Ctrl+R refresh"]
    folded = wrap_blocks(blocks, 16)
    # Every produced line is a whole-number of blocks; no block is cut.
    for line in folded.split("\n"):
        assert line  # no empty lines
        for block in line.split(" · "):
            assert block in blocks
    # And every block survives intact somewhere.
    flat = folded.replace("\n", " · ")
    for block in blocks:
        assert block in flat.split(" · ")


def test_apply_cursor_underline_marks_bottom_row():
    import numpy as np
    from k2kremote.app import apply_cursor_underline, _CELL_W, _CELL_H

    reverse = [""] * 3 + ["00000100" + "0" * 32] + [""] * 4  # row 3, col 5
    out = np.asarray(apply_cursor_underline(None, reverse))
    assert out.shape == (240, 64)  # blank width-major buffer
    y = 3 * _CELL_H + (_CELL_H - 1)  # bottom pixel row of the cell
    x0 = 5 * _CELL_W
    assert out[x0:x0 + _CELL_W, y].all()           # underline lit
    assert out[x0:x0 + _CELL_W, y - 1].sum() == 0  # nothing above it
    assert out.sum() == _CELL_W                     # only those pixels


def test_apply_cursor_underline_idempotent_on_filled_cell():
    import numpy as np
    from k2kremote.app import apply_cursor_underline

    reverse = [""] * 3 + ["00000100" + "0" * 32] + [""] * 4
    filled = np.zeros((240, 64), dtype=np.uint8)
    filled[30:36, 24:32] = 1  # cell (row 3, col 5) already fully on
    out = np.asarray(apply_cursor_underline(filled, reverse))
    assert (out == filled).all()  # bottom row already on -> no change


def test_apply_cursor_underline_noop_without_flags():
    import numpy as np
    from k2kremote.app import apply_cursor_underline

    px = np.zeros((240, 64), dtype=np.uint8)
    assert apply_cursor_underline(px, []) is px          # nothing flagged
    assert apply_cursor_underline(px, ["0000"]) is px


def test_render_text_overlay_highlights_reverse_cells():
    from k2kremote.app import render_text_overlay

    text_rows = ["AB"] + [""] * 7
    # No graphics plane at all; the high-bit mask alone must highlight cell (0,1).
    out = render_text_overlay(None, text_rows, ["01"])
    spans = [(s.start, s.style) for s in out.spans]
    # 'B' (index 1) is reverse; 'A' is not.
    styled = {out.plain[s.start]: str(s.style) for s in out.spans if "reverse" in str(s.style)}
    assert "B" in styled and "A" not in styled


def test_is_name_dialog_detects_naming_page():
    from k2kremote.app import is_name_dialog, _TEXT_COLS

    def place(pairs):
        row = list(" " * _TEXT_COLS)
        for col, word in pairs:
            for j, ch in enumerate(word):
                row[col + j] = ch
        return [""] * 7 + ["".join(row)]

    naming = place([(0, "Delete"), (7, "Insert"), (14, "<<<"),
                    (21, ">>>"), (28, "OK"), (34, "Cancel")])
    assert is_name_dialog(naming) is True

    other = place([(0, "Octav-"), (7, "Octav+"), (14, "Panic"),
                   (21, "View"), (28, "Chan-"), (35, "Chan+")])
    assert is_name_dialog(other) is False
    assert is_name_dialog([]) is False


@pytest.mark.asyncio
async def test_demo_app_renders_a_frame():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        # The braille mirror is populated (16 rows) in demo mode.
        assert app.last_render.count("\n") == 15


@pytest.mark.asyncio
async def test_keypress_without_device_updates_status():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("f1")
        await pilot.pause()
        assert "SoftA" in app.last_status


@pytest.mark.asyncio
async def test_name_entry_overlay_open_and_submit_builds_plan():
    from textual.widgets import Input

    from k2kremote import text_entry
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("f9")
        await pilot.pause()
        assert app._entry_active
        entry = app.query_one("#nameentry", Input)
        entry.value = "AB"
        await pilot.press("enter")  # Input submits; app dispatches the plan
        await pilot.pause()
        assert not app._entry_active
        assert not app.query("#nameentry")  # overlay removed
        assert app.last_plan == text_entry.plan_name("AB")


@pytest.mark.asyncio
async def test_name_entry_escape_cancels():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("f9")
        await pilot.pause()
        assert app._entry_active
        await pilot.press("escape")
        await pilot.pause()
        assert not app._entry_active
        assert not app.query("#nameentry")


def test_render_text_grid_pads_to_8x40():
    from k2kremote.app import render_text_grid

    grid = render_text_grid(["Program", "Bank"])
    lines = grid.split("\n")
    assert len(lines) == 8
    assert all(len(line) == 40 for line in lines)
    assert lines[0].startswith("Program")


@pytest.mark.asyncio
async def test_mode_cycle_covers_all_modes_and_wraps():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test(size=(130, 40)) as pilot:  # narrow -> blocks = quadrant
        await pilot.pause()
        assert app._mode == "auto" and "auto" in app._titlebar_text()
        renders = {}
        for _ in range(len(app._MODES)):
            renders[app._mode] = app.last_render
            await pilot.press("f10")
            await pilot.pause()
        assert app._mode == "auto"                 # wrapped back round
        assert set(renders) == set(app._MODES)     # visited every mode
        assert renders["braille"].count("\n") == 15      # 16 braille rows
        assert renders["blocks"].count("\n") == 31       # 32 quadrant rows at 130 cols
        assert renders["text"].count("\n") == 7          # 8-row text grid


@pytest.mark.asyncio
async def test_image_mode_renders_via_image_widget():
    import k2kremote.app as appmod
    if not appmod._HAS_IMAGE:
        import pytest
        pytest.skip("textual-image not installed")
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        app._mode = "image"
        app.show_frame(app._last_frame)
        await pilot.pause()
        assert app.last_render == "<image>"
        assert app.query_one("#imagedisplay").display is True
        assert app.query_one("#display").display is False


@pytest.mark.asyncio
async def test_blocks_mode_uses_wide_halfblock_when_terminal_is_wide():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test(size=(250, 40)) as pilot:  # >= 240 cols
        await pilot.pause()
        app._mode = "blocks"
        app.show_frame(app._last_frame)
        rows = app.last_render.split("\n")
        assert len(rows) == 32          # half-block rows
        assert all(len(r) == 240 for r in rows)  # full 240-wide, aspect-correct


def test_titlebar_reflects_connection_state():
    # Pure string builder — a live (non-demo) session with a bridge present.
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(bridge=object(), demo=False)
    assert "connecting" in app._titlebar_text()  # _connected is None until first refresh
    app._connected = False
    assert "disconnected" in app._titlebar_text()
    app._connected = True
    assert "connected" in app._titlebar_text()


@pytest.mark.asyncio
async def test_set_connection_updates_retry_status():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._set_connection(False)
        assert "retrying" in app.last_status


@pytest.mark.asyncio
async def test_name_entry_rejects_unsupported_character():
    from textual.widgets import Input

    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("f9")
        await pilot.pause()
        app.query_one("#nameentry", Input).value = "café"
        await pilot.press("enter")
        await pilot.pause()
        assert app.last_plan == []  # nothing dispatched
        assert "charset" in app.last_status.lower()


def _naming_frame():
    """A synthetic Program-rename frame (text-only, with the naming soft labels)."""
    from k2kremote.refresh import Frame

    rows = [""] * 8
    rows[3] = "Program Name:   CMI VOICES"
    rows[7] = "Delete Insert  <<<    >>>    OK   Cancel"
    return Frame(pixels=None, text_rows=rows)


class _RecordingWorker:
    """Minimal stand-in for RefreshWorker that records the presses it gets."""

    def __init__(self):
        self.presses = []
        self.prioritized = None
        self.typed = []
        self.looked_up = []
        self.renamed = []

    def press(self, button):
        self.presses.append(button)

    def wheel(self, clicks):
        pass

    def type_name(self, target, start_col=0):
        self.typed.append((target, start_col))

    def lookup_name(self, obj_type, idno, on_result):
        self.looked_up.append((obj_type, idno))

    def rename(self, obj_type, idno, name, on_result):
        self.renamed.append((obj_type, idno, name))

    def set_prioritize_graphics(self, on):
        self.prioritized = on

    def stop(self):
        pass

    @property
    def paused(self):
        return False

    @property
    def danger(self):
        return False


@pytest.mark.asyncio
async def test_name_dialog_opens_and_renders_software_cursor():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        frame = _naming_frame()
        app.show_frame(frame)
        await pilot.pause()
        # The software cursor opens on the first name cell (screen col 16).
        assert app._name_cursor.active and app._name_cursor.screen_col() == 16
        # …and that cell is flagged reverse-video for the renderers to draw it,
        # even though the frame's own reverse mask is empty.
        assert not frame.reverse
        assert app._effective_reverse(frame)[3][16] == "1"


@pytest.mark.asyncio
async def test_cursor_key_advances_and_sends_press():
    from k2000.definitions import Button

    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        app._worker = _RecordingWorker()       # pretend a device is attached
        app.show_frame(_naming_frame())
        await pilot.pause()
        await pilot.press("right")              # CursorRight
        await pilot.pause()
        assert app._name_cursor.screen_col() == 17           # advanced one cell
        assert app._effective_reverse(app._last_frame)[3][17] == "1"
        assert Button.CursorRight in app._worker.presses     # still drove the device


@pytest.mark.asyncio
async def test_name_entry_types_from_tracked_cursor_offset():
    # Move the cursor two cells in, then type: the app must hand type_name the
    # tracked offset so typing starts at the cursor, not the field's first cell.
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        app._worker = _RecordingWorker()
        app.show_frame(_naming_frame())
        await pilot.pause()
        await pilot.press("right")
        await pilot.press("right")              # cursor now on cell 2
        await pilot.pause()
        app._dispatch_name("abc")
        assert app._worker.typed == [("abc", 2)]
        assert app._name_cursor.pos == 4        # typed abc at cells 2,3,4


@pytest.mark.asyncio
async def test_name_cursor_closes_when_dialog_leaves():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        app.show_frame(_naming_frame())
        await pilot.pause()
        assert app._name_cursor.active
        # Navigate away: an ordinary page with no Delete/Insert soft labels.
        app.show_frame(_demo_frame_other())
        await pilot.pause()
        assert not app._name_cursor.active
        assert app._effective_reverse(app._last_frame) == []


def _demo_frame_other():
    from k2kremote.refresh import Frame

    rows = [""] * 7 + ["More>  Algorithm  KEYMAP   PITCH    AMPENV  more>"]
    return Frame(pixels=None, text_rows=rows)


def test_name_preview_colours_only_the_overflow():
    from k2kremote.app import _name_preview, _OVERFLOW_STYLE, _NAME_DISPLAY_WIDTH

    name = "a" * (_NAME_DISPLAY_WIDTH + 4)
    text = _name_preview("current name: ", name)
    assert text.plain == "current name: " + name           # full name is shown
    base = len("current name: ")
    overflow = [(s.start, s.end) for s in text.spans if str(s.style) == _OVERFLOW_STYLE]
    # exactly the characters past the display width carry the orange style
    assert overflow == [(base + _NAME_DISPLAY_WIDTH, base + _NAME_DISPLAY_WIDTH + 4)]


def test_name_preview_no_style_when_within_limit():
    from k2kremote.app import _name_preview, _OVERFLOW_STYLE, _NAME_DISPLAY_WIDTH

    text = _name_preview("current name: ", "a" * _NAME_DISPLAY_WIDTH)
    assert not [s for s in text.spans if str(s.style) == _OVERFLOW_STYLE]


@pytest.mark.asyncio
async def test_alt_keys_switches_legend_and_soft_bar():
    from k2kremote.app import K2KRemoteApp, SoftBar

    app = K2KRemoteApp(demo=True, text_mode=True, alt_keys=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        legend = app._legend_text()
        assert "a-h soft" in legend and "Ctrl+n name" in legend
        assert "F1-F6" not in legend and "F9 name" not in legend
        bar = app.query_one("#softbar", SoftBar)
        bar.labels = ["Octav-", "Octav+", "Panic", "View", "Chan-", "Chan+"]
        rendered = str(bar.render())
        assert "[a:Octav-]" in rendered and "[h:Chan+]" in rendered
        assert "[F1:" not in rendered


@pytest.mark.asyncio
async def test_mode_leader_sends_mode_under_super_alt_keys():
    from k2000.definitions import Button

    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True, super_alt_keys=True)
    async with app.run_test() as pilot:
        app._worker = _RecordingWorker()
        await pilot.pause()
        assert "m,d" in app._mode_bar_text()       # lowercase leader scheme (no Shift)
        assert "Alt+d" not in app._mode_bar_text()
        assert app._alt_keys                         # super implies the F-key alternates
        await pilot.press("m")                       # leader
        await pilot.pause()
        assert app._awaiting_mode
        await pilot.press("d")                       # -> Disk
        await pilot.pause()
        assert not app._awaiting_mode
        assert Button.Disk in app._worker.presses


@pytest.mark.asyncio
async def test_alt_keys_keeps_alt_mode_chords_and_no_leader():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True, alt_keys=True)  # not super
    async with app.run_test() as pilot:
        app._worker = _RecordingWorker()
        await pilot.pause()
        assert "Alt+d" in app._mode_bar_text() and "m,d" not in app._mode_bar_text()
        await pilot.press("m")                       # 'm' is NOT a leader here
        await pilot.pause()
        assert not app._awaiting_mode


@pytest.mark.asyncio
async def test_press_keeps_legend_visible():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        app._worker = _RecordingWorker()
        app.show_frame(_demo_frame_other())          # ordinary (non-name) page
        await pilot.pause()
        await pilot.press("right")                   # a routine navigation press
        await pilot.pause()
        # The hint legend lives on its own persistent line and is never replaced
        # by the label of what was just pressed.
        assert "cursor" in app.last_keyhints
        assert "Cursor→" not in app.last_status


@pytest.mark.asyncio
async def test_default_keys_show_fkeys():
    from k2kremote.app import K2KRemoteApp, SoftBar

    app = K2KRemoteApp(demo=True, text_mode=True)  # no alt_keys
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "F1-F6 soft" in app._legend_text()
        bar = app.query_one("#softbar", SoftBar)
        bar.labels = ["Octav-"] + [""] * 5
        assert "[F1:Octav-]" in str(bar.render())


@pytest.mark.asyncio
async def test_rename_apply_rejects_non_ascii_and_no_device():
    from k2000.definitions import ObjectType

    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test():
        out = []
        app.rename_apply(ObjectType.Program, 201, "Café", lambda n, e: out.append((n, e)))
        assert out[-1] == (None, "name must be ASCII")
        # ASCII but no worker attached (demo) -> reported, not sent.
        app.rename_apply(ObjectType.Program, 201, "Plain", lambda n, e: out.append((n, e)))
        assert out[-1] == (None, "no device connected")


@pytest.mark.asyncio
async def test_rename_tool_sends_change_through_worker():
    from k2000.definitions import ObjectType
    from textual.widgets import Input

    from k2kremote.app import K2KRemoteApp, RenameObjectScreen

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        app._worker = _RecordingWorker()
        await app.push_screen(RenameObjectScreen())
        await pilot.pause()
        screen = app.screen
        id_field = screen.query_one("#renameid", Input)
        id_field.focus()
        id_field.value = "201"
        await pilot.pause()
        # Enter advances to the new-name field; leaving the id field looks it up.
        await pilot.press("enter")
        await pilot.pause()
        assert app.focused is screen.query_one("#renamenew", Input)
        assert app._worker.looked_up == [(ObjectType.Program, 201)]
        # The modal's Enter must NOT bubble to the app's name-entry typer.
        assert app._worker.typed == []

        screen.query_one("#renamenew", Input).value = "Wave Of Mutilation"
        screen._apply()
        await pilot.pause()
        assert app._worker.renamed == [(ObjectType.Program, 201, "Wave Of Mutilation")]
        assert app._worker.typed == []


async def _rename_and_confirm(app, pilot, asked, confirmed):
    """Drive the rename tool and hand `done` the name the device claims to have
    stored. Returns (screen, still_open)."""
    from textual.widgets import Input

    from k2kremote.app import RenameObjectScreen

    captured = []
    app._worker = _RecordingWorker()
    app._worker.rename = lambda t, i, n, on_result: captured.append(on_result)
    await app.push_screen(RenameObjectScreen())
    await pilot.pause()
    screen = app.screen
    screen.query_one("#renameid", Input).value = "201"
    screen.query_one("#renamenew", Input).value = asked
    screen._apply()
    await pilot.pause()
    # The INFO reply arrives on the worker thread and the app marshals it back,
    # so it has to be delivered from a real one — call_from_thread refuses to
    # run on the app's own thread, and that marshalling is part of the contract.
    import asyncio

    await asyncio.to_thread(captured[0], confirmed, None)
    await pilot.pause()
    return screen, app.screen is screen


@pytest.mark.asyncio
async def test_rename_flags_a_name_the_device_did_not_store():
    """The INFO reply says what actually landed; a difference must not be
    reported as success.

    p22 round-tripped 18 characters intact, so this is not the expected
    long-name truncation — it is the device having done something else, and the
    old code printed the stored name inside a "renamed ..." line and dismissed."""
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        screen, still_open = await _rename_and_confirm(
            app, pilot, "Wave Of Mutilation", "Wave Of Mutilat")
        assert still_open, "a mismatch must keep the dialog up, not dismiss it"
        assert "Wave Of Mutilat" in str(screen.query_one("#renamecurrent").content)


@pytest.mark.asyncio
async def test_rename_accepts_a_device_name_padded_with_blanks():
    """Whether the firmware pads the field is untested, so trailing blanks must
    not read as a mismatch — that would false-alarm on every rename."""
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        _, still_open = await _rename_and_confirm(app, pilot, "Bass", "Bass   ")
        assert not still_open, "padding is not a difference; this should dismiss"


@pytest.mark.asyncio
async def test_rename_tool_looks_up_on_tab_out_of_id():
    from k2000.definitions import ObjectType
    from textual.widgets import Input

    from k2kremote.app import K2KRemoteApp, RenameObjectScreen

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test() as pilot:
        app._worker = _RecordingWorker()
        await app.push_screen(RenameObjectScreen())
        await pilot.pause()
        screen = app.screen
        id_field = screen.query_one("#renameid", Input)
        id_field.focus()
        id_field.value = "305"
        await pilot.pause()
        await pilot.press("tab")          # move off the id field without Enter
        await pilot.pause()
        assert app._worker.looked_up == [(ObjectType.Program, 305)]


def test_resolve_config_precedence(tmp_path):
    from types import SimpleNamespace

    from k2kremote.app import resolve_config
    from k2kremote.midi_bridge import BridgeConfig

    path = tmp_path / "config.toml"
    BridgeConfig(rig="standard", port="Saved Port").save(str(path))

    # File only.
    cfg = resolve_config(SimpleNamespace(config=str(path), rig="standard", port=None))
    assert cfg.rig == "standard" and cfg.port == "Saved Port"

    # CLI --port overrides the saved port.
    cfg = resolve_config(SimpleNamespace(config=str(path), rig="standard", port="CLI Port"))
    assert cfg.port == "CLI Port"

    # CLI --rig auto overrides.
    cfg = resolve_config(SimpleNamespace(config=str(path), rig="auto", port=None))
    assert cfg.rig == "auto"

    # No file -> defaults.
    cfg = resolve_config(SimpleNamespace(config=str(tmp_path / "none.toml"), rig="standard", port=None))
    assert cfg.rig == "standard" and cfg.port is None


def test_build_bridge_saves_effective_config(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from k2kremote import app as appmod
    from k2kremote.midi_bridge import BridgeConfig, MidiBridge

    captured = {}

    def fake_from_config(cfg, *, gap):
        captured["gap"] = gap
        return "BRIDGE"

    monkeypatch.setattr(MidiBridge, "from_config", staticmethod(fake_from_config))
    path = tmp_path / "config.toml"
    args = SimpleNamespace(config=str(path), rig="auto", port=None, save_config=True,
                           sysex_interval=200.0)

    assert appmod._build_bridge(args) == "BRIDGE"
    assert captured["gap"] == 0.2  # 200 ms -> 0.2 s
    assert BridgeConfig.load(str(path)).rig == "auto"  # persisted


@pytest.mark.asyncio
async def test_width_hint_appears_when_narrow():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert "widen" in app.last_status


@pytest.mark.asyncio
async def test_width_ok_when_wide_shows_legend():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        assert "widen" not in app.last_status


@pytest.mark.asyncio
async def test_screenshot_binding_saves_current_frame(monkeypatch):
    from k2kremote import screenshot
    from k2kremote.app import K2KRemoteApp

    captured = {}
    monkeypatch.setattr(screenshot, "save_png",
                        lambda frame, path, **kw: captured.setdefault("frame", frame) or path)

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()           # demo frame is shown -> _last_frame set
        await pilot.press("f12")
        await pilot.pause()
        assert "frame" in captured    # save_png was called with the live frame
        assert "saved" in app.last_status


@pytest.mark.asyncio
async def test_screenshot_without_frame_reports_nothing():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._last_frame = None  # simulate "no capture yet"
        app.action_screenshot()
        assert "nothing to capture" in app.last_status


@pytest.mark.asyncio
async def test_panic_binding_is_recognized():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)  # no worker -> "(no device)" path
    async with app.run_test() as pilot:
        await pilot.press("alt+x")
        await pilot.pause()
        assert "Panic" in app.last_status


@pytest.mark.asyncio
async def test_pause_binding_no_device():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)  # no worker
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.pause()
        assert "pause" in app.last_status.lower()


def test_text_mode_flag_starts_in_text():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    assert app._mode == "text"
    assert "text" in app._titlebar_text()


def test_is_text_page_uses_graphics_in_blank_cells():
    import numpy as np
    from k2kremote.app import _is_text_page
    from k2kremote.refresh import Frame

    blank_g = np.zeros((240, 64), dtype=np.uint8)

    # Disk/list: text in middle rows, graphics empty there -> text page.
    disk = Frame(pixels=blank_g, text_rows=["DiskMode", "Current dir:", "\\K2KREMOT"] + [""] * 5)
    assert _is_text_page(disk)

    # Program: middle text blank but the big name is drawn as graphics — thin
    # glyph strokes (partial cells), NOT full-width and NOT solid -> graphics page.
    prog_g = np.zeros((240, 64), dtype=np.uint8)
    prog_g[40:140, 26:30] = 0xFF  # a thin stroke over ~100px (cols 6-23), middle
    prog = Frame(pixels=prog_g, text_rows=["ProgramMode"] + [""] * 7)
    assert not _is_text_page(prog)

    # Edit page: param text in the middle AND a (thin-stroke) graphics diagram.
    edit_g = np.zeros((240, 64), dtype=np.uint8)  # (width, height)
    edit_g[120:200, 26:30] = 0xFF  # algorithm diagram strokes (right, middle rows)
    edit = Frame(pixels=edit_g, text_rows=["EditProg ALG", "Algorithm:5"] + [""] * 6)
    assert not _is_text_page(edit)

    # No graphics plane at all -> text.
    assert _is_text_page(Frame(pixels=None, text_rows=["DiskMode"]))

    # The K2000 draws a full-width horizontal divider line above the soft labels
    # on every page (1px tall, across all 240px). It is chrome, not graphics, so
    # a sparse Disk page with that line still reads as text. (This is the real
    # bug from probes/p23: ~108px of divider tipped it to braille.)
    div_g = np.zeros((240, 64), dtype=np.uint8)
    div_g[:, 54:56] = 0xFF  # full-width rule near the bottom of the content
    assert _is_text_page(Frame(pixels=div_g, text_rows=["DiskMode"] + [""] * 7))

    # Setup / program-list page: a thin box outline (chrome, ~hundreds of px) drawn
    # around a TEXT-HEAVY table. The graphics do NOT dominate the text -> text page
    # (this is the real Setup bug from probes/p23: a box tipped it to braille).
    busy = ["SetupMode",
            "          99 Earth and Sky",
            "Chan/Program Info   100 Basic Setup",
            "1  150 Magic Orch     1 Majesty",
            "2   16 Matrix 12      2 Sahara",
            "3   17 OBX Braz 4     3 Full Orch",
            "", "Octav-"]
    chrome = np.zeros((240, 64), dtype=np.uint8)
    chrome[0:60, 8:12] = 0xFF  # thin box-edge strokes in blank cells of row 1
    assert _is_text_page(Frame(pixels=chrome, text_rows=busy))
    # The same chrome on an otherwise-blank page (no text to dominate) is graphics.
    assert not _is_text_page(Frame(pixels=chrome, text_rows=[""] * 8))

    # A reverse-video highlight box (e.g. the Disk page's "SCSI 0" field) fills
    # blank padding cells with a SOLID block. That is a highlight, not graphics —
    # so the page stays text whether or not the high-bit flag is set.
    hl_g = np.zeros((240, 64), dtype=np.uint8)
    hl_g[30:90, 24:48] = 0xFF                 # solid block: cols 5-14, rows 3-5
    hl_row = "".join("1" if 5 <= c < 15 else "0" for c in range(40))
    rev = [""] * 3 + [hl_row] * 3 + [""] * 2  # rows 3-5, cols 5-14 flagged reverse
    text_rows = [""] * 8
    assert _is_text_page(Frame(pixels=hl_g, text_rows=text_rows, reverse=rev))
    assert _is_text_page(Frame(pixels=hl_g, text_rows=text_rows))  # solid even unflagged


def test_is_song_page_detection():
    from k2kremote.app import _is_song_page

    assert _is_song_page(["SongMode:MAIN  Events:189K   STOPPED"])
    assert _is_song_page(["   SongMode:MAIN"])  # tolerates leading spaces
    assert not _is_song_page(["SetupMode"])
    assert not _is_song_page(["DiskMode"])
    assert not _is_song_page([])


@pytest.mark.asyncio
async def test_auto_forces_braille_for_song_mode():
    import numpy as np

    from k2kremote.app import K2KRemoteApp
    from k2kremote.refresh import Frame

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._graphics_capable = lambda: False  # pretend a non-graphics terminal
        # Song page: mostly text, but the channel strip is graphics-only -> braille.
        song = Frame(pixels=np.zeros((240, 64), np.uint8),
                     text_rows=["SongMode:MAIN  Events:189K", "CurSong:1 NewSong"] + [""] * 6)
        assert app._effective_mode(song) == "braille"
        # An ordinary text page is still text.
        disk = Frame(pixels=np.zeros((240, 64), np.uint8),
                     text_rows=["DiskMode", "Current dir:", "\\K2KREMOT"] + [""] * 5)
        assert app._effective_mode(disk) == "text"


def test_text_overlay_marks_cursor_as_reverse():
    import numpy as np
    from k2kremote.app import render_text_overlay

    # A filled graphics block over text cell (row 0, col 0) = cursor/highlight.
    px = np.zeros((240, 64), dtype=np.uint8)
    px[0:6, 0:8] = 0xFF  # width 0..6 (col 0), height 0..8 (row 0)
    overlay = render_text_overlay(px, ["X" + " " * 39])
    # The first cell carries a 'reverse' style span; elsewhere plain.
    styles = {(str(span.style)) for span in overlay.spans}
    assert any("reverse" in s for s in styles)


def test_heavy_disk_op_detection():
    import numpy as np
    from k2000.definitions import Button
    from k2kremote.app import K2KRemoteApp, _SOFT_KEYS, _TEXT_COLS
    from k2kremote.refresh import Frame

    # Build a Disk-mode soft-label row: Format Load Move Util NewDir more>
    bounds = [round(i * _TEXT_COLS / _SOFT_KEYS) for i in range(_SOFT_KEYS + 1)]
    labels = ["Format", "Load", "Move", "Util", "NewDir", "more>"]
    row = list(" " * _TEXT_COLS)
    for i, lab in enumerate(labels):
        for j, ch in enumerate(lab):
            if bounds[i] + j < _TEXT_COLS:
                row[bounds[i] + j] = ch

    app = K2KRemoteApp(demo=True)
    app._last_frame = Frame(pixels=np.zeros((240, 64), dtype=np.uint8),
                            text_rows=[""] * 7 + ["".join(row)])
    assert app._heavy_op_for(Button.SoftB) == "Load"     # F2 = heavy
    assert app._heavy_op_for(Button.SoftA) == "Format"   # F1 = heavy
    assert app._heavy_op_for(Button.SoftC) == "Move"     # F3 = heavy
    assert app._heavy_op_for(Button.SoftD) is None       # Util = safe
    assert app._heavy_op_for(Button.Enter) is None       # not a soft key
    app._last_frame = None
    assert app._heavy_op_for(Button.SoftB) is None        # no frame -> unknown


@pytest.mark.asyncio
async def test_heavy_op_press_autopauses_before_sending():
    import numpy as np
    from k2000.definitions import Button
    from k2kremote.app import K2KRemoteApp, _SOFT_KEYS, _TEXT_COLS
    from k2kremote.refresh import Frame

    class FakeWorker:
        def __init__(self):
            self.paused = False
            self.danger = False
            self.presses = []
            self.order = []

        def set_paused(self, p):
            self.paused = p
            self.order.append("pause")

        def press(self, b):
            self.presses.append(b)
            self.order.append("press")

        def wheel(self, c):
            pass

        def stop(self):
            pass

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        fw = FakeWorker()
        app._worker = fw
        bounds = [round(i * _TEXT_COLS / _SOFT_KEYS) for i in range(_SOFT_KEYS + 1)]
        labels = ["Format", "Load", "Move", "Util", "NewDir", "more>"]
        row = list(" " * _TEXT_COLS)
        for i, lab in enumerate(labels):
            for j, ch in enumerate(lab):
                if bounds[i] + j < _TEXT_COLS:
                    row[bounds[i] + j] = ch
        app._last_frame = Frame(pixels=np.zeros((240, 64), dtype=np.uint8),
                                text_rows=[""] * 7 + ["".join(row)])

        await pilot.press("f2")  # Load
        await pilot.pause()
        assert fw.paused is True
        assert Button.SoftB in fw.presses
        assert fw.order[0] == "pause"  # paused BEFORE the press (no poll follows)
        assert "PAUSED" in app.last_status


@pytest.mark.asyncio
async def test_force_refresh_binding():
    from k2kremote.app import K2KRemoteApp

    sent = {"forced": False}

    class FakeWorker:
        paused = False

        def force_refresh(self):
            sent["forced"] = True

        def stop(self):
            pass

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._worker = FakeWorker()
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert sent["forced"] is True
        assert "refresh" in app.last_status.lower()


@pytest.mark.asyncio
async def test_p_resumes_confirm_autopause_via_force_refresh():
    """`p` is the universal resume: while auto-paused on a confirm screen it
    releases via force_refresh (a read), not by toggling the manual pause."""
    from k2kremote.app import K2KRemoteApp

    calls = {"forced": 0, "set_paused": 0}

    class FakeWorker:
        paused = False
        danger = True  # auto-paused on a confirm prompt

        def force_refresh(self):
            calls["forced"] += 1

        def set_paused(self, p):
            calls["set_paused"] += 1

        def stop(self):
            pass

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._worker = FakeWorker()
        await pilot.press("p")
        await pilot.pause()
        assert calls["forced"] == 1        # resumed by re-reading
        assert calls["set_paused"] == 0    # did NOT stack a manual pause


@pytest.mark.asyncio
async def test_ctrl_alternates_for_app_fkeys():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+v")  # alternate for F10 (view mode)
        await pilot.pause()
        assert app._mode == "braille"  # cycled auto -> braille
        await pilot.press("ctrl+n")  # alternate for F9 (name entry)
        await pilot.pause()
        assert app._entry_active


@pytest.mark.asyncio
async def test_auto_uses_image_on_graphics_capable_terminal():
    import k2kremote.app as appmod
    if not appmod._HAS_IMAGE:
        import pytest
        pytest.skip("textual-image not installed")
    import numpy as np
    from k2kremote.app import K2KRemoteApp
    from k2kremote.refresh import Frame

    # Force a graphics-capable protocol so auto prefers the image on graphics pages.
    app = K2KRemoteApp(demo=True, image_protocol="tgp")
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        # On a graphics-capable terminal, auto uses the image for EVERY page.
        g = np.zeros((240, 64), dtype=np.uint8)
        g[20:200, 16:48] = 0xFF
        graphics = Frame(pixels=g, text_rows=["ProgramMode"] + [""] * 7)
        assert app._effective_mode(graphics) == "image"
        text = Frame(pixels=np.zeros((240, 64), np.uint8),
                     text_rows=["DiskMode", "Current dir:", "\\K2KREMOT"] + [""] * 5)
        assert app._effective_mode(text) == "image"  # text page -> image too
        # The image lives inside the centring box.
        app.show_frame(graphics)
        await pilot.pause()
        assert app.query_one("#imagebox").display is True
        assert app.query_one("#display").display is False


@pytest.mark.asyncio
async def test_master_tool_two_step_confirm_and_autopause():
    """F11 Master tool: first Enter arms, second fires; firing auto-pauses the
    mirror and runs the op via device_op (bypassing the LCD menu)."""
    from k2kremote.app import K2KRemoteApp
    from k2000.definitions import ObjectType

    calls = {"paused": 0, "ops": []}

    class FakeWorker:
        paused = False
        danger = False

        def set_paused(self, p):
            self.paused = p
            calls["paused"] += 1

        def device_op(self, fn, on_result):
            calls["ops"].append(fn)  # don't invoke on_result (no cross-thread here)

        def lookup_name(self, obj_type, idno, cb):
            pass  # preview is irrelevant to this test

        def stop(self):
            pass

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._worker = FakeWorker()
        await pilot.press("f11")
        await pilot.pause()
        screen = app.screen
        screen.query_one("#mastertarget").value = "201"

        screen._attempt()                      # first Enter -> arm only
        assert screen._armed is True
        assert calls["ops"] == []

        screen._attempt()                      # second Enter -> fire
        assert len(calls["ops"]) == 1
        assert calls["paused"] >= 1            # mirror auto-paused around the op
        # The queued thunk targets the chosen object via the bridge's delete_object.
        rec = []
        SpyBridge = type("SpyBridge", (), {
            "delete_object": lambda self, t, i: rec.append((t, i))})
        calls["ops"][0](SpyBridge())
        assert rec == [(ObjectType.Program, 201)]


@pytest.mark.asyncio
async def test_master_tool_bank_delete_variants():
    """The three bank-scoped functions build the right DELBANK calls: one type,
    all types in a bank (type 0), and everything (type 0 / bank 127)."""
    from k2kremote.app import K2KRemoteApp
    from k2000.definitions import ObjectType

    ops = []

    class FakeWorker:
        paused = False
        danger = False

        def set_paused(self, p):
            pass

        def device_op(self, fn, on_result):
            ops.append(fn)

        def lookup_name(self, obj_type, idno, cb):
            pass

        def stop(self):
            pass

    bank_calls = []
    SpyBridge = type("SpyBridge", (), {
        "delete_bank": lambda self, t, k: bank_calls.append((t, k))})

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._worker = FakeWorker()
        await pilot.press("f11")
        await pilot.pause()
        screen = app.screen

        def fire(func, target=""):
            screen.query_one("#masterfunc").value = func
            screen._sync_fields()
            screen.query_one("#mastertarget").value = target
            screen._attempt()   # arm
            screen._attempt()   # fire

        fire("delete_bank", "3")        # one type's bank
        fire("delete_bank_all", "3")    # every type in bank 3
        fire("delete_all")              # everything (no target needed)

        for fn in ops:
            fn(SpyBridge())
        assert bank_calls == [
            (ObjectType.Program, 3),    # type-scoped (default type = Program)
            (None, 3),                  # all types in bank 3 -> DELBANK type 0
            (None, 127),                # everything -> type 0, bank 127
        ]


# --- the Save -> Name freeze ------------------------------------------------
# Reported live: "the name page reached through a Save takes no keyboard input".
# Hardware (probes/p25_savename.py) cleared the two suspected causes — the page
# IS recognised as a name dialog and the field IS located from its literal
# "Name:" label — and confirmed presses do reach the device there. What is left
# is this: the heavy-op guard pauses the mirror when a soft key labelled Save is
# pressed, and a paused worker still delivers presses but schedules no refresh.
# The screen therefore freezes while input keeps working, which is exactly what
# "takes no keyboard input" looks like from the outside.

class _PauseProbeWorker:
    """Stands in for RefreshWorker: records presses and the pause state."""

    def __init__(self):
        self.presses = []
        self.paused = False
        self.danger = False   # the titlebar reads this
        self.refreshes = 0

    def press(self, button):
        self.presses.append(button)

    def wheel(self, clicks):
        pass

    def set_paused(self, paused):
        self.paused = paused

    def request_refresh(self):
        self.refreshes += 1

    def set_prioritize_graphics(self, on):
        pass

    def stop(self):
        pass


def _soft_row_frame(bottom):
    from k2kremote.refresh import Frame

    return Frame(pixels=None, text_rows=[""] * 7 + [bottom.ljust(40)])


@pytest.mark.asyncio
async def test_save_soft_key_pauses_the_mirror_but_still_sends_presses():
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        worker = _PauseProbeWorker()
        app._worker = worker
        # A Disk-style page whose F2 is labelled "Save" — a heavy op.
        app._last_frame = _soft_row_frame("Load   Save   Rename Delete Copy   Util")

        await pilot.press("f2")
        await pilot.pause()
        assert worker.paused, "pressing a 'Save' soft key auto-pauses the mirror"
        assert len(worker.presses) == 1, "...and the press is still delivered"
        assert "PAUSED" in app.last_status

        # Now the K2000 shows its name page. Every further keystroke reaches the
        # device — and the mirror stays frozen, because the worker is paused.
        app._last_frame = _soft_row_frame("Delete Insert  <<<    >>>    OK   Cancel")
        for key in ("f1", "f3", "f4"):
            await pilot.press(key)
        await pilot.pause()
        assert len(worker.presses) == 4, "input keeps reaching the device while paused"
        assert worker.paused, "but nothing ever un-pauses it, so the screen never moves"


def test_save_page_soft_rows_do_not_themselves_trigger_the_guard():
    """The editor route to Save->Name never trips the heavy-op guard.

    Captured live 2026-08-15 (probes/p25_savename.py). None of these rows
    contains a heavy-op word, so reaching the name page by Exit -> Yes -> Rename
    leaves the mirror live — which is why that route works and the Disk one does
    not. Pinning the captured rows here so a future _HEAVY_OPS edit that would
    start freezing this flow fails loudly.
    """
    from k2kremote.app import _HEAVY_OPS, soft_labels

    captured = [
        "              Rename Cancel Yes    No",      # save dialog
        "Object             Rename Replace Cancel",   # save-as page
        "Delete Insert  <<<    >>>    OK   Cancel",   # the name page itself
    ]
    for bottom in captured:
        for label in soft_labels([""] * 7 + [bottom.ljust(40)]):
            assert not any(op in label.lower() for op in _HEAVY_OPS), (
                f"{label!r} would now auto-pause the editor's Save flow")


# --- soft-key labels line up under the mirror -------------------------------

def test_align_blocks_centres_each_block_in_its_zone():
    """Each block's centre must land in the same zone soft_labels reads back."""
    from k2kremote.app import align_blocks, _SOFT_KEYS

    blocks = ["[F1:Select]", "[F2:Root]", "[F3:Parent]", "[F4:Open]",
              "[F5:OK]", "[F6:Cancel]"]
    span = 120  # braille / the usual capped pixel image
    line = align_blocks(blocks, span, width=200)
    assert line is not None
    for i, block in enumerate(blocks):
        at = line.index(block)
        centre = at + (len(block) - 1) / 2
        assert int(centre * _SOFT_KEYS / span) == i, f"{block} drifted out of zone {i}"


def test_align_blocks_is_the_inverse_of_soft_labels():
    """Round-trip: split a real bottom row, align it, and land in the same zones.

    soft_labels assigns a word to the key its centre column falls under;
    align_blocks places block i back under zone i. The two must agree, or the
    strip would sit beneath the wrong keys.
    """
    from k2kremote.app import align_blocks, soft_labels, _SOFT_KEYS, _TEXT_COLS

    bottom = "Delete Insert  <<<    >>>    OK   Cancel"   # captured from hardware
    labels = soft_labels([""] * 7 + [bottom])
    blocks = [f"[F{i+1}:{l}]" for i, l in enumerate(labels)]
    span = 120
    line = align_blocks(blocks, span, width=200)
    assert line is not None
    for i, (label, block) in enumerate(zip(labels, blocks)):
        # where the label sits on the K2000's own 40-col row...
        src = bottom.index(label)
        src_zone = int((src + (len(label) - 1) / 2) * _SOFT_KEYS / _TEXT_COLS)
        # ...and where we put its block on the mirror-wide strip
        at = line.index(block)
        dst_zone = int((at + (len(block) - 1) / 2) * _SOFT_KEYS / span)
        assert src_zone == dst_zone == i


def test_align_blocks_shifts_by_offset():
    from k2kremote.app import align_blocks

    blocks = [f"[F{i+1}:X]" for i in range(6)]
    plain = align_blocks(blocks, 120, width=200)
    shifted = align_blocks(blocks, 120, width=200, offset=7)
    assert shifted == " " * 7 + plain


def test_align_blocks_declines_when_it_cannot_fit():
    """40-col text mode: six [F#:label] blocks do not fit under 40 columns."""
    from k2kremote.app import align_blocks

    blocks = ["[F1:Select]", "[F2:Root]", "[F3:Parent]", "[F4:Open]",
              "[F5:OK]", "[F6:Cancel]"]
    assert align_blocks(blocks, 40, width=200) is None      # span too narrow
    assert align_blocks(blocks, 120, width=30) is None      # bar too narrow
    assert align_blocks(blocks, 0, width=200) is None       # geometry unknown
    assert align_blocks(blocks[:3], 120, width=200) is None  # not six keys


@pytest.mark.asyncio
async def test_soft_bar_aligns_to_the_span_it_is_given():
    from k2kremote.app import K2KRemoteApp, SoftBar, align_blocks

    app = K2KRemoteApp(demo=True)
    async with app.run_test(size=(150, 44)) as pilot:
        await pilot.pause()
        bar = app.query_one("#softbar", SoftBar)
        bar.labels = ["Select", "Root", "Parent", "Open", "OK", "Cancel"]
        bar.span, bar.offset = 120, 3
        await pilot.pause()
        blocks = [f"[F{i+1}:{l}]" for i, l in enumerate(bar.labels)]
        assert str(bar.render()) == align_blocks(blocks, 120, bar.size.width or 9999,
                                                 3, bar.centres or None)

        # Span 0 (geometry unknown) falls back to left-packed blocks.
        bar.span, bar.offset = 0, 0
        await pilot.pause()
        assert str(bar.render()).startswith("[F1:Select]")


# --- a frozen mirror has to look frozen -------------------------------------

@pytest.mark.asyncio
async def test_paused_badge_is_styled_not_plain_text():
    """A stale mirror still looks live, so the badge must not blend into the bar."""
    from rich.text import Text

    from k2kremote.app import K2KRemoteApp, _PAUSED_STYLE

    app = K2KRemoteApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        worker = _PauseProbeWorker()
        app._worker = worker

        plain = app._titlebar_text()
        assert "PAUSED" not in plain.plain

        worker.paused = True
        app._pause_reason = "manual"
        badge = app._titlebar_text()
        assert "⏸ PAUSED · manual" in badge.plain
        styled = [span for span in badge.spans if span.style == _PAUSED_STYLE]
        assert styled, "the pause badge carries no style"
        assert "PAUSED" in badge.plain[styled[0].start:styled[0].end]

        # The auto-pause on a confirm screen gets the same treatment.
        worker.paused, worker.danger = False, True
        assert "⏸ PAUSED · confirm" in app._titlebar_text().plain


def test_paused_style_is_loud_and_distinct():
    from k2kremote.app import _PAUSED_STYLE, _OVERFLOW_STYLE

    assert "blink" in _PAUSED_STYLE          # kitty honours it; others degrade to bold
    assert "orange" in _PAUSED_STYLE
    assert _PAUSED_STYLE != _OVERFLOW_STYLE  # not confusable with the rename overflow


def test_align_blocks_follows_the_real_label_positions():
    """The K2000 does not centre its labels in their sixths, so neither do we.

    On the Program page the words sit at their own columns; centring each block
    in its nominal zone leaves it visibly off the word it names. Given the real
    centres, each block should straddle the label's own position instead.
    """
    from k2kremote.app import align_blocks, soft_label_centres, soft_labels, _TEXT_COLS

    bottom = "Octav- Octav+ Panic  View   Chan-  Chan+"   # captured from hardware
    rows = [""] * 7 + [bottom]
    labels = soft_labels(rows)
    centres = soft_label_centres(rows)
    blocks = [f"[F{i+1}:{l}]" for i, l in enumerate(labels)]
    span, offset = 120, 6

    line = align_blocks(blocks, span, width=140, offset=offset, centres=centres)
    assert line is not None
    for i, (label, block) in enumerate(zip(labels, blocks)):
        # Where the label's centre lands once the 40-col row is stretched to the
        # mirror, and where our block's centre ended up.
        want = offset + (bottom.index(label) + (len(label) - 1) / 2) * span / _TEXT_COLS
        at = line.index(block)
        got = at + (len(block) - 1) / 2
        assert abs(got - want) <= 1.5, f"{block} is {got - want:+.1f} cells off {label}"


def test_soft_label_centres_handles_gaps_and_multiword_labels():
    from k2kremote.app import soft_label_centres

    # A key with no label reports None, so it falls back to its zone centre.
    centres = soft_label_centres([""] * 7 + ["Object             Rename Replace Cancel"])
    assert centres[1] is None and centres[2] is None
    assert centres[0] is not None and centres[3] is not None
    assert all(0.0 <= c <= 1.0 for c in centres if c is not None)
    # Ascending: labels never cross each other.
    seen = [c for c in centres if c is not None]
    assert seen == sorted(seen)

    assert soft_label_centres([]) == [None] * 6


# --- window sizing ----------------------------------------------------------

def test_optimal_size_fits_the_mirror_and_all_the_chrome():
    from k2kremote import braille
    from k2kremote.app import optimal_size, _CHROME_ROWS

    cols, rows = optimal_size()
    # Narrower than this and the app itself puts up a "widen the window" hint.
    assert cols >= braille.BRAILLE_COLS
    # Tall enough for the widest everyday renderer plus every bar.
    assert rows >= _CHROME_ROWS + braille.BRAILLE_ROWS
    # ...but not extravagant: the 44 rows this replaced left half the window empty.
    assert rows <= _CHROME_ROWS + braille.BRAILLE_ROWS + 4


def test_size_is_remembered_across_launches(tmp_path, monkeypatch):
    from k2kremote.app import remember_size, remembered_size, startup_size, optimal_size

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert remembered_size() is None
    assert startup_size() == optimal_size()      # nothing cached yet

    remember_size(160, 40)
    assert remembered_size() == (160, 40)
    assert startup_size() == (160, 40)


def test_absurd_remembered_sizes_are_ignored(tmp_path, monkeypatch):
    """A window dragged tiny by accident must not become the new normal."""
    from k2kremote.app import remember_size, remembered_size, startup_size, optimal_size

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    remember_size(20, 5)
    assert remembered_size() is None
    assert startup_size() == optimal_size()

    (tmp_path / "k2kremote" / "window-size").write_text("not a size")
    assert remembered_size() is None


@pytest.mark.asyncio
async def test_closing_the_app_records_its_size(tmp_path, monkeypatch):
    from k2kremote.app import K2KRemoteApp, remembered_size

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    app = K2KRemoteApp(demo=True)
    async with app.run_test(size=(132, 30)) as pilot:
        await pilot.pause()
    assert remembered_size() == (132, 30)


# --- the legend folds between groups, not through them ----------------------

def test_wrap_groups_keeps_the_function_key_run_together():
    """The bug this fixes: F7 got orphaned onto the navigation line and was
    reported missing. Whatever the width, the F-keys must stay contiguous."""
    from k2kremote import keymap
    from k2kremote.app import wrap_groups

    fkeys = keymap.LEGEND_GROUPS[1]
    for width in (150, 140, 124, 110, 100, 90, 80):
        lines = wrap_groups(keymap.LEGEND_GROUPS, width).split("\n")
        holding = [i for i, line in enumerate(lines) if fkeys[0] in line]
        assert len(holding) == 1, f"width {width}: 'F1-F6 soft' appears oddly"
        line = lines[holding[0]]
        assert all(block in line for block in fkeys), (
            f"width {width}: the F-key run was split across the fold:\n"
            + "\n".join(lines))


def test_wrap_groups_still_respects_the_width():
    from k2kremote import keymap
    from k2kremote.app import wrap_groups

    for width in (150, 124, 100, 80, 60):
        for line in wrap_groups(keymap.LEGEND_GROUPS, width).split("\n"):
            assert len(line) <= width, f"width {width}: overflowed with {line!r}"


def test_wrap_groups_loses_nothing():
    from k2kremote import keymap
    from k2kremote.app import wrap_groups

    for groups in (keymap.LEGEND_GROUPS, keymap.LEGEND_GROUPS_ALT):
        flat = [b for g in groups for b in g]
        for width in (150, 124, 100, 70):
            rendered = wrap_groups(groups, width)
            for block in flat:
                assert block in rendered, f"{block!r} vanished at width {width}"


def test_wrap_groups_prefers_a_group_break_over_a_greedy_fit():
    from k2kremote.app import wrap_groups

    groups = (("aaa", "bbb"), ("ccc", "ddd"))
    # 13 cols fits "aaa · bbb" (9) and could greedily squeeze "ccc" too (15 > 13,
    # so no) — the point is the second group starts its own line intact.
    assert wrap_groups(groups, 13) == "aaa · bbb\nccc · ddd"
    # Wide enough for everything: one line.
    assert wrap_groups(groups, 40) == "aaa · bbb · ccc · ddd"


def test_legend_groups_and_flat_blocks_stay_in_sync():
    from k2kremote import keymap

    assert keymap.LEGEND_BLOCKS == tuple(b for g in keymap.LEGEND_GROUPS for b in g)
    assert keymap.LEGEND_BLOCKS_ALT == tuple(
        b for g in keymap.LEGEND_GROUPS_ALT for b in g)
    assert "F7 Edit" in keymap.LEGEND_BLOCKS
    assert "Ctrl+e Edit" in keymap.LEGEND_BLOCKS_ALT
