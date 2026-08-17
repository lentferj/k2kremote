# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only: no MIDI hardware is ever opened; the editor never opens one
# at all. The macro is the checked-in BOOT.MAC fixture.

import shutil
from pathlib import Path

import pytest

from k2kmaced.macfile import BANK_EVERYTHING, PramFile
from k2kmaced.app import (
    BANK_VALUES,
    DIR_UP,
    MacroEditor,
    browse_rows,
    build_editor,
    cycle,
    dir_of,
    main,
    missing_files,
    parent_dir,
    path_tree,
)

from test_k2image import build_image  # tests/ is on sys.path under pytest

FIXTURE = Path(__file__).parent / "fixtures" / "BOOT.MAC"


@pytest.fixture
def boot(tmp_path) -> Path:
    target = tmp_path / "BOOT.MAC"
    shutil.copy(FIXTURE, target)
    return target


@pytest.fixture
def editor(boot) -> MacroEditor:
    return build_editor(str(boot))


# --- value cycling ---------------------------------------------------------


def test_cycle_wraps_in_both_directions():
    assert cycle(BANK_VALUES, 0, 1) == 100
    assert cycle(BANK_VALUES, 0, -1) == BANK_EVERYTHING     # wraps to the end
    assert cycle(BANK_VALUES, BANK_EVERYTHING, 1) == 0      # and back round


def test_cycle_recovers_from_an_unknown_value():
    assert cycle(BANK_VALUES, 250, 1) == BANK_VALUES[0]


# --- model -----------------------------------------------------------------


def test_loads_the_fixture(editor):
    assert len(editor.table) == 6
    assert not editor.dirty
    assert editor.current.filename == "NULL.KRZ"


def test_cycling_marks_dirty_and_changes_one_entry(editor):
    editor.index = 1
    editor.cycle_bank(1)
    assert editor.dirty
    assert editor.table[1].bank == 300     # 200 → 300
    assert editor.table[2].bank == 300     # untouched neighbour, unchanged
    editor.cycle_mode(1)
    assert editor.table[1].mode_label == "OvFill"   # Overwrite → OvFill
    editor.cycle_drive(-1)
    assert editor.table[1].drive_label == "Floppy"  # SCSI 0 → Floppy


def test_move_tracks_the_cursor(editor):
    editor.index = 0
    editor.move(2)
    assert editor.index == 2
    assert editor.table[2].filename == "NULL.KRZ"
    assert editor.dirty


def test_delete_clamps_the_cursor(editor):
    editor.index = 5
    editor.delete()
    assert len(editor.table) == 5
    assert editor.index == 4
    assert editor.current.filename == "TCNOAFAV.KRZ"


def test_editing_an_empty_macro_is_harmless(editor):
    for _ in range(len(editor.table)):
        editor.delete()
    assert editor.current is None
    editor.cycle_bank(1)      # no entry to edit — must not raise
    editor.move(1)
    editor.delete()
    assert editor.rows() == []


def test_rebank_all(editor):
    editor.rebank_all(700)
    assert {e.bank for e in editor.table} == {700}


def test_set_full_path_splits_directory_and_file(editor):
    editor.index = 1
    editor.set_full_path("\\ANALOG\\SYNAPSE.KRZ")
    assert editor.table[1].path == "\\ANALOG\\"
    assert editor.table[1].filename == "SYNAPSE.KRZ"
    assert editor.dirty


def test_set_full_path_accepts_host_style_input(editor):
    editor.set_full_path("ANALOG/SYNAPSE.KRZ")     # no leading \, unix separators
    assert editor.current.full_path == "\\ANALOG\\SYNAPSE.KRZ"


def test_set_full_path_to_the_root(editor):
    editor.set_full_path("\\NEW.KRZ")
    assert editor.current.path == "\\" and editor.current.filename == "NEW.KRZ"


@pytest.mark.parametrize("bad", ["", "   ", "\\ANALOG\\", "\\WAYTOOLONGNAME.KRZ"])
def test_set_full_path_rejects_what_the_k2000_could_not_load(editor, bad):
    from k2kmaced.macfile import MacError

    with pytest.raises(MacError):
        editor.set_full_path(bad)
    assert not editor.dirty


def test_repointed_entry_survives_a_round_trip(editor, tmp_path):
    editor.index = 5
    editor.set_full_path("\\ANALOG\\SYNAPSE.KRZ")
    out = tmp_path / "NEW.MAC"
    editor.save(str(out))
    entry = PramFile.parse(out.read_bytes()).macro_table()[5]
    assert entry.full_path == "\\ANALOG\\SYNAPSE.KRZ"
    assert entry.bank == 600 and entry.mode_label == "Overwrite"   # untouched


def test_add_inserts_after_the_cursor_and_inherits_its_settings(editor):
    editor.index = 1
    editor.add()
    assert editor.index == 2
    assert len(editor.table) == 7
    new = editor.current
    assert new.filename == "NEW.KRZ"
    assert new.bank == editor.table[1].bank        # inherited from the neighbour
    assert new.mode == editor.table[1].mode
    assert editor.dirty


def test_add_to_an_empty_macro(editor):
    for _ in range(len(editor.table)):
        editor.delete()
    editor.add()
    assert len(editor.table) == 1 and editor.index == 0
    assert editor.current.mode_label == "Fill"     # the default, no neighbour


def test_set_full_path_on_an_empty_macro_is_refused(editor):
    from k2kmaced.macfile import MacError

    for _ in range(len(editor.table)):
        editor.delete()
    with pytest.raises(MacError, match="no entry"):
        editor.set_full_path("\\A.KRZ")


def test_rows_render_the_manual_fields(editor):
    first = editor.rows()[0]
    assert first == ("0", "SCSI 0", "\\NULL.KRZ", "E", "Overwrite", "")


def test_save_writes_a_new_file_and_clears_dirty(editor, tmp_path):
    editor.index = 1
    editor.cycle_bank(1)
    out = tmp_path / "NEW.MAC"
    written = editor.save(str(out))
    assert written == out.stat().st_size
    assert not editor.dirty
    assert PramFile.parse(out.read_bytes()).macro_table()[1].bank == 300


def test_untouched_macro_saves_byte_identically(editor, tmp_path):
    out = tmp_path / "COPY.MAC"
    editor.save(str(out))
    assert out.read_bytes() == FIXTURE.read_bytes()


# --- image cross-check -----------------------------------------------------


@pytest.fixture
def image(tmp_path) -> Path:
    return build_image(
        tmp_path / "hd0.img",
        {
            "": {"BOOT.MAC": FIXTURE.read_bytes(), "NULL.KRZ": b"\x00" * 8},
            "--FAVS": {"KPOWFAV.KRZ": b"\x00" * 8},
        },
    )


def test_missing_files_are_flagged(boot, image):
    editor = build_editor(str(boot), str(image))
    flags = {row[2]: row[5] for row in editor.rows()}
    assert flags["\\NULL.KRZ"] == ""
    assert flags["\\--FAVS\\KPOWFAV.KRZ"] == ""
    assert flags["\\--FAVS\\LFOALFAV.KRZ"] == "MISSING"


def test_missing_files_helper(boot, image):
    table = PramFile.parse(Path(boot).read_bytes()).macro_table()
    assert "\\-RLNDCD2\\WAVSTFAV.KRZ" in missing_files(table, str(image))


def test_catalogue_lists_only_loadable_files(boot, image):
    editor = build_editor(str(boot), str(image))
    # BOOT.MAC and NULL.KRZ from the root, KPOWFAV.KRZ from the subdirectory.
    assert editor.catalogue == [
        "\\--FAVS\\KPOWFAV.KRZ", "\\BOOT.MAC", "\\NULL.KRZ"
    ]


def test_catalogue_is_empty_without_an_image(editor):
    assert editor.catalogue == []


# --- command line ----------------------------------------------------------


def test_bad_source_exits_cleanly(tmp_path, capsys):
    junk = tmp_path / "junk.MAC"
    junk.write_bytes(b"not a macro")
    assert main([str(junk)]) == 1
    assert "error:" in capsys.readouterr().err


def test_output_inside_an_image_is_refused(boot, capsys):
    assert main([str(boot), "-o", "hd0.img:\\BOOT.MAC"]) == 1
    assert "plain file" in capsys.readouterr().err


# --- the terminal app ------------------------------------------------------

textual = pytest.importorskip("textual", reason="textual not installed")


@pytest.mark.asyncio
async def test_app_lists_the_entries(editor):
    from textual.widgets import DataTable

    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(DataTable)
        assert table.row_count == 6
        # The status line reports what is loaded; the keys live in the legend
        # (see test_legend_shows_the_write_keys_even_in_a_narrow_window).
        assert "6 entries" in app.last_status


@pytest.mark.asyncio
async def test_app_edits_and_saves(editor, tmp_path):
    from k2kmaced.app import K2kmacedApp

    out = tmp_path / "NEW.MAC"
    app = K2kmacedApp(editor, str(out))
    async with app.run_test() as pilot:
        await pilot.press("down", "b")          # entry 1: bank 200 → 300
        await pilot.pause()
        assert app.last_status.startswith("* ")  # dirty marker
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert PramFile.parse(out.read_bytes()).macro_table()[1].bank == 300
    assert not editor.dirty


@pytest.mark.asyncio
async def test_app_cycles_bank_both_ways_and_reorders(editor):
    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor)
    async with app.run_test() as pilot:
        await pilot.press("down", "b", "b", "B")   # 200 → 300 → 400 → 300
        await pilot.pause()
        assert editor.table[1].bank == 300
        await pilot.press("ctrl+down")             # entry 1 moves down one
        await pilot.pause()
        assert editor.table[2].filename == "KPOWFAV.KRZ"


@pytest.mark.asyncio
async def test_app_edits_a_path_through_the_overlay(editor):
    from textual.widgets import Input

    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor)
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.pause()
        field = app.query_one("#pathentry", Input)
        assert field.display and field.value == "\\NULL.KRZ"
        field.value = "\\ANALOG\\SYNAPSE.KRZ"
        await pilot.press("enter")
        await pilot.pause()
        assert not field.display
        assert editor.table[0].full_path == "\\ANALOG\\SYNAPSE.KRZ"


@pytest.mark.asyncio
async def test_app_keeps_the_overlay_open_on_a_bad_path(editor):
    from textual.widgets import Input

    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor)
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.pause()
        field = app.query_one("#pathentry", Input)
        field.value = "\\ANALOG\\"          # no file name
        await pilot.press("enter")
        await pilot.pause()
        assert field.display                # still open, so it can be corrected
        assert "rejected:" in app.last_status
        assert editor.table[0].filename == "NULL.KRZ"


@pytest.mark.asyncio
async def test_app_escape_cancels_the_path_overlay(editor):
    from textual.widgets import Input

    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor)
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.pause()
        app.query_one("#pathentry", Input).value = "\\NOPE.KRZ"
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query_one("#pathentry", Input).display
        assert editor.table[0].filename == "NULL.KRZ"
        assert not editor.dirty


@pytest.mark.asyncio
async def test_app_adds_an_entry(editor):
    from textual.widgets import DataTable

    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor)
    async with app.run_test() as pilot:
        await pilot.press("a")
        await pilot.pause()
        assert app.query_one(DataTable).row_count == 7
        assert editor.table[1].filename == "NEW.KRZ"
        assert "press e" in app.last_status


@pytest.mark.asyncio
async def test_app_file_picker_needs_an_image(editor):
    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor)
    async with app.run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        assert "--image" in app.last_status


@pytest.mark.asyncio
async def test_app_file_picker_repoints_the_entry(boot, image):
    from k2kmaced.app import K2kmacedApp

    editor = build_editor(str(boot), str(image))
    assert editor.table[0].full_path == "\\NULL.KRZ"
    app = K2kmacedApp(editor)
    async with app.run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        # The picker opens on the entry's current file (\NULL.KRZ, last in the
        # sorted catalogue); step up one and take that instead.
        await pilot.press("up", "enter")
        await pilot.pause()
    assert editor.table[0].full_path == "\\BOOT.MAC"
    assert editor.dirty


@pytest.mark.asyncio
async def test_app_refuses_to_save_without_an_output(editor):
    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor, None)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "no output file" in app.last_status


# --- directory browser model ------------------------------------------------

CATALOGUE = [
    "\\NULL.KRZ",
    "\\--FAVS\\KPOWFAV.KRZ",
    "\\--FAVS\\LFOALFAV.KRZ",
    "\\-RLNDCD2\\WAVSTFAV.KRZ",
    "\\DEEP\\NEST\\INNER.KRZ",
]


def test_dir_of_and_parent_dir():
    assert dir_of("\\--FAVS\\KPOWFAV.KRZ") == "\\--FAVS\\"
    assert dir_of("\\NULL.KRZ") == "\\"
    assert parent_dir("\\--FAVS\\") == "\\"
    assert parent_dir("\\DEEP\\NEST\\") == "\\DEEP\\"
    assert parent_dir("\\") is None          # the root has no parent


def test_path_tree_registers_intermediate_directories():
    """A nested path must create every directory on the way down.

    \\DEEP\\NEST\\INNER.KRZ is the only file below \\DEEP\\, so if the walk only
    registered the file's own directory, \\DEEP\\ would be unreachable from the
    root and the browser could never get to it."""
    tree = path_tree(CATALOGUE)
    assert tree["\\"]["dirs"] == ["--FAVS", "-RLNDCD2", "DEEP"]
    assert tree["\\"]["files"] == ["NULL.KRZ"]
    assert tree["\\DEEP\\"]["dirs"] == ["NEST"]
    assert tree["\\DEEP\\"]["files"] == []          # nothing loadable of its own
    assert tree["\\DEEP\\NEST\\"]["files"] == ["INNER.KRZ"]


def test_browse_rows_orders_up_then_dirs_then_files():
    rows = browse_rows(path_tree(CATALOGUE), "\\--FAVS\\")
    assert rows[0] == (DIR_UP, "up", "\\")
    kinds = [kind for _, kind, _ in rows]
    assert kinds == ["up", "file", "file"]
    assert [label for label, _, _ in rows][1:] == ["KPOWFAV.KRZ", "LFOALFAV.KRZ"]
    # the target of a file row is the full path, ready for set_full_path()
    assert rows[1][2] == "\\--FAVS\\KPOWFAV.KRZ"


def test_browse_rows_at_the_root_has_no_up_entry():
    rows = browse_rows(path_tree(CATALOGUE), "\\")
    assert DIR_UP not in [label for label, _, _ in rows]
    assert [label for label, _, _ in rows] == [
        "--FAVS\\", "-RLNDCD2\\", "DEEP\\", "NULL.KRZ"]
    # directories are visibly directories, and descend rather than select
    assert rows[0][1] == "dir" and rows[0][2] == "\\--FAVS\\"


def test_browse_rows_of_an_unknown_directory_is_empty_not_an_error():
    # A stale entry can point at a directory that no longer exists on the image.
    assert browse_rows(path_tree(CATALOGUE), "\\GONE\\") == [
        (DIR_UP, "up", "\\")]


# --- move to an explicit position -------------------------------------------

def test_move_to_slides_the_others_along(editor):
    """4 -> 2 must leave 0,1,4,2,3 — an insert, not a swap.

    A swap would give 0,1,4,3,2, which changes the load order of two entries the
    user never mentioned. The macro replays top to bottom, so that is a
    different macro, not a differently-drawn one."""
    before = [e.full_path for e in editor.table]
    editor.index = 4
    assert editor.move_to(2) == 2
    after = [e.full_path for e in editor.table]
    assert after == [before[0], before[1], before[4], before[2], before[3],
                     *before[5:]]
    assert editor.index == 2          # the cursor follows the entry it moved
    assert editor.dirty


def test_move_to_clamps_instead_of_raising(editor):
    editor.index = 0
    last = len(editor.table) - 1
    assert editor.move_to(99) == last          # 99 means "last"
    assert editor.move_to(-5) == 0             # -5 means "first"


def test_move_to_is_a_no_op_on_a_short_table(editor):
    editor.table.entries[:] = editor.table.entries[:1]
    editor.dirty = False
    assert editor.move_to(3) == 0
    assert not editor.dirty                    # nothing changed, nothing to save


# --- the write gate and install-to-image safeguards -------------------------

@pytest.fixture
def img_editor(boot, image):
    """An editor opened *from inside* an image, so install has a target."""
    return build_editor(f"{image}:\\BOOT.MAC")


def test_install_target_comes_from_what_was_opened(img_editor, image):
    """The destination is never typed — it is where the macro was opened from.

    A destructive write whose target is inferred cannot be aimed at the wrong
    file by a typo, which is the failure the CLI's path argument allows."""
    assert img_editor.can_install
    assert img_editor.image_path == str(image)
    assert img_editor.member == "\\BOOT.MAC"


def test_a_plain_file_has_no_install_target(editor):
    assert not editor.can_install


def test_a_compressed_image_has_no_install_target(boot, tmp_path):
    """k2image reads .lzo via a temp copy, so a write would be discarded."""
    from k2kmaced.macfile import PramFile
    from k2kmaced.app import MacroEditor
    pram = PramFile.parse(FIXTURE.read_bytes())
    ed = MacroEditor(pram, "x", image_path="/tmp/hd0.img.lzo", member="\\BOOT.MAC")
    assert not ed.can_install


@pytest.mark.asyncio
async def test_write_gate_is_off_at_startup_and_install_refuses(img_editor, image):
    """Default-off is the point: the mistake guarded against is not a slip in a
    dialog, it is pressing a key before realising the image is the instrument's
    own disk."""
    from k2kmaced.app import K2kmacedApp

    before = image.read_bytes()
    app = K2kmacedApp(img_editor)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.allow_write is False
        await pilot.press("i")                 # try to install with the gate off
        await pilot.pause()
        assert "gate is off" in app.last_status
        from k2kmaced.app import InstallScreen
        assert not isinstance(app.screen, InstallScreen)
    assert image.read_bytes() == before


@pytest.mark.asyncio
async def test_arming_the_gate_shows_in_the_banner(img_editor):
    """A status line gets scrolled past; the gate stays on until turned off, so
    it has to be visible for as long as it is armed."""
    from textual.widgets import Static

    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(img_editor)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "write gate off" in str(app.query_one("#where", Static).content)
        await pilot.press("w")
        await pilot.pause()
        assert app.allow_write is True
        assert "ARMED" in str(app.query_one("#where", Static).content)
        await pilot.press("w")
        await pilot.pause()
        assert app.allow_write is False


@pytest.mark.asyncio
async def test_install_needs_arm_then_fire_not_one_keypress(img_editor, image):
    """Enter alone must not write: `i` in the modal arms, Enter fires."""
    from k2kmaced.app import InstallScreen, K2kmacedApp

    before = image.read_bytes()
    app = K2kmacedApp(img_editor)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")                 # arm the gate
        await pilot.press("i")                 # open the install modal
        await pilot.pause()
        assert isinstance(app.screen, InstallScreen)
        assert app.screen.armed is False
        await pilot.press("enter")             # fire without arming
        await pilot.pause()
        assert isinstance(app.screen, InstallScreen), "Enter alone dismissed it"
    assert image.read_bytes() == before, "nothing may be written unarmed"


@pytest.mark.asyncio
async def test_install_writes_once_armed_and_fired(img_editor, image, capsys):
    from k2kmaced.app import InstallScreen, K2kmacedApp
    from k2kmaced.k2image import DiskImage

    img_editor.index = 1
    img_editor.cycle_bank(1)                   # make a change worth writing
    expected = img_editor.serialize()

    app = K2kmacedApp(img_editor)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, InstallScreen)
        await pilot.press("i")                 # arm inside the modal
        await pilot.pause()
        assert app.screen.armed is True
        await pilot.press("enter")             # fire
        await pilot.pause()
    with DiskImage.open(image) as im:
        assert im.read_file("\\BOOT.MAC") == expected
    assert "read it back to verify" in app.last_status


@pytest.mark.asyncio
async def test_escape_in_the_install_modal_writes_nothing(img_editor, image):
    from k2kmaced.app import K2kmacedApp

    before = image.read_bytes()
    app = K2kmacedApp(img_editor)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.press("i")
        await pilot.pause()
        await pilot.press("i")                 # armed...
        await pilot.press("escape")            # ...then changed our mind
        await pilot.pause()
        assert "cancelled" in app.last_status
    assert image.read_bytes() == before


@pytest.mark.asyncio
async def test_opening_a_new_file_disarms_the_gate(img_editor, image, boot):
    """Permission is per-file: it must not carry over to a different image."""
    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(img_editor)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        assert app.allow_write is True
        app._load(str(boot))                   # a plain .MAC this time
        await pilot.pause()
        assert app.allow_write is False


@pytest.mark.asyncio
async def test_starting_with_nothing_open_is_survivable(capsys):
    """`k2kmaced` with no arguments must not crash on any key."""
    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(None)
    async with app.run_test() as pilot:
        await pilot.pause()
        from k2kmaced.app import OpenScreen
        assert isinstance(app.screen, OpenScreen), "should offer to open"
        await pilot.press("escape")            # dismiss it, then poke
        await pilot.pause()
        for key in ("b", "m", "d", "a", "o", "delete", "ctrl+s", "w", "i", "e", "f"):
            await pilot.press(key)
            await pilot.pause()
        assert "nothing open" in app.last_status


# --- the key legend must not lose keys ---------------------------------------

def test_wrap_blocks_never_splits_a_block():
    from k2kmaced.app import LEGEND_BLOCKS, wrap_blocks

    folded = wrap_blocks(LEGEND_BLOCKS, 40)
    for line in folded.split("\n"):
        for block in line.split(" · "):
            assert block in LEGEND_BLOCKS
    # and nothing is dropped, at any width
    for width in (20, 40, 80, 92, 200):
        flat = wrap_blocks(LEGEND_BLOCKS, width).replace("\n", " · ")
        assert set(flat.split(" · ")) == set(LEGEND_BLOCKS)


@pytest.mark.asyncio
async def test_legend_shows_the_write_keys_even_in_a_narrow_window(editor):
    """The reason the Footer was replaced: it showed as many bindings as fit and
    dropped the rest, which put `w` and `i` — the two that can change a disk
    image — off the end of the line where nobody would see them."""
    from textual.widgets import Static

    from k2kmaced.app import K2kmacedApp

    app = K2kmacedApp(editor)
    async with app.run_test(size=(70, 24)) as pilot:
        await pilot.pause()
        legend = str(app.query_one("#legend", Static).content)
        assert "w write gate" in legend
        assert "i install to image" in legend
        assert "ctrl+o open" in legend
