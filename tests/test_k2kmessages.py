# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# The matcher is tested against a synthetic table and needs nothing. The
# extractor needs a ROM image at ~/temp/k2k_fw/k2000_v387j.bin and skips
# without it. No hardware either way.

import pathlib

import pytest

from k2kremote.k2kmessages import (SCREEN_ROWS, Message, _to_pattern,
                                   extract, identify, identify_screen,
                                   unmatched)

IMAGE = pathlib.Path.home() / "temp" / "k2k_fw" / "k2000_v387j.bin"


def _msg(text, addr=0x180000):
    pattern, is_format = _to_pattern(text)
    return Message(addr, text, pattern, is_format)


def test_a_literal_identifies_itself():
    table = [_msg("Too many objects to move.")]
    hit = identify("Too many objects to move.", table)
    assert hit is not None and hit.text == "Too many objects to move."
    assert hit.captures == ()


def test_a_format_string_identifies_the_line_it_rendered():
    table = [_msg("Loading program %s...")]
    hit = identify("Loading program VOX3...", table)
    assert hit is not None and hit.text == "Loading program %s..."
    assert hit.captures == ("VOX3",)


def test_numeric_conversions_match_digits_not_text():
    table = [_msg("%s %s to: ID#%3d")]
    assert identify("Copy Sample to: ID#201", table).captures \
        == ("Copy", "Sample", "201")
    assert identify("Copy Sample to: ID#abc", table) is None


def test_a_literal_beats_a_format_string_that_also_matches():
    """Otherwise a bare '%s' claims every line on the display."""
    table = [_msg("%s"), _msg("Please wait...")]
    hit = identify("Please wait...", table)
    assert hit.text == "Please wait..." and not hit.message.is_format


def test_the_more_specific_format_string_wins():
    table = [_msg("%s"), _msg("Loading program %s...")]
    assert identify("Loading program VOX3...", table).text \
        == "Loading program %s..."


def test_an_unmatched_line_is_none_rather_than_a_guess():
    table = [_msg("Please wait...")]
    assert identify("ACOUSTIC PIANO      ", table) is None
    assert identify("", table) is None
    assert identify("   ", table) is None


def test_identify_screen_returns_one_result_per_row():
    table = [_msg("Please wait...")]
    rows = ["Please wait...", "something else", ""]
    out = identify_screen(rows, table)
    assert len(out) == 3
    assert out[0] is not None and out[1] is None and out[2] is None


def test_percent_literal_is_not_a_wildcard():
    table = [_msg("100%% done")]
    assert identify("100% done", table) is not None
    assert not table[0].is_format


# --- the extractor, against a real image ---------------------------------

def _table():
    if not IMAGE.exists():
        pytest.skip("ROM image not present")
    return extract(IMAGE)


def test_extractor_finds_the_strings_the_import_work_quoted():
    """Each of these was read out of the ROM during the import tracing and
    is quoted in docs/IMPORT_CONVERSION.md, so the extractor must find them."""
    table = _table()
    texts = {m.text for m in table}
    for expected in ("Akai partition not found.",
                     "No Akai sample files found.",
                     "ROLAND.S",
                     "Please wait...",
                     "This is one file of a multi-disk set.",
                     "You must load disk #1 first."):
        assert expected in texts, expected


def test_extractor_finds_known_strings_at_their_known_addresses():
    table = _table()
    at = {m.addr: m.text for m in table}
    assert at[0x18D4B1] == "Akai partition not found."
    assert at[0x190CDF] == "ROLAND.S"


def test_no_extracted_string_exceeds_a_screen_row():
    table = _table()
    assert table, "extractor returned nothing"
    assert max(len(m.text) for m in table) <= 40


def test_a_real_dialog_line_identifies_against_the_real_table():
    table = _table()
    hit = identify("Sample to bank:", table)
    assert hit is not None
    assert hit.text == "%s to bank:" and hit.captures == ("Sample",)


def test_unmatched_reports_only_the_rows_no_string_accounts_for():
    table = [_msg("Please wait..."), _msg("Loading program %s...")]
    rows = ["Please wait...", "Loading program VOX3...",
            "SOME PRESET NAME", "", "   "]
    assert unmatched(rows, table) == [(2, "SOME PRESET NAME")]


def test_unmatched_is_empty_when_the_catalogue_covers_the_screen():
    table = [_msg("Change   OK   Cancel")]
    assert unmatched(["Change   OK   Cancel", ""], table) == []


def test_unmatched_ignores_rows_past_the_grid():
    table = [_msg("Please wait...")]
    rows = ["x"] * (SCREEN_ROWS + 3)
    assert max(i for i, _ in unmatched(rows, table)) < SCREEN_ROWS


# --- the curated state table ------------------------------------------------
#
# These are the only ROM-derived strings the project ships, so they get held to
# the ROM: every marker must actually occur in the message pool. That check is
# what retired "scanning", which had been guessed and matched nothing.


def test_every_state_marker_occurs_in_the_rom_message_pool():
    """No guessed wording. The image decides, when the image is present.

    `_BUSY_MARKERS` used to carry "scanning", which no v3.87J string contains
    -- a marker that could never fire, sitting in a list whose whole job was
    to fire in time.
    """
    from k2kremote.k2kmessages import STATE_MARKERS

    table = _table()  # skips without the image
    pool = " ".join(m.text for m in table).lower()
    missing = [marker for _, marker in STATE_MARKERS if marker not in pool]
    assert not missing, f"markers absent from the ROM: {missing}"


def test_an_error_screen_is_not_mistaken_for_a_busy_one():
    """The bug the ROM pool exposed.

    "writing" and "reading file" were BUSY markers, and in the firmware those
    substrings land mostly on failures: `Failed writing to disk`, `Problem
    reading file %s, error %d`. A device sitting on an error dialog answers
    perfectly well, so treating it as busy cost the pixel plane and delayed
    genuine disconnection reporting for no reason.
    """
    from k2kremote.k2kmessages import ScreenState, classify_screen

    for line in ("Failed writing to disk",
                 "Problem reading file BOOT.MAC, error 3",
                 "Error reading file DRUMS.KRZ",
                 "Not enough memory to load this file.",
                 "Can't delete file"):
        assert classify_screen([line]) is ScreenState.ERROR, line

    # ...while the progress forms sharing those verbs still read as busy.
    for line in ("Writing...", "Reading file DRUMS.KRZ", "Verifying..."):
        assert classify_screen([line]) is ScreenState.BUSY, line


def test_a_ram_wipe_in_progress_is_destructive_not_merely_busy():
    """`Initializing all memory. Please wait...` is the RAM clear happening.

    It contains "please wait", so the old two-list arrangement classified it
    BUSY -- which pauses the expensive read but leaves the heartbeat running,
    through exactly the object rewrite that can hang the K2000's CPU (the
    `lockup-heartbeat-during-deletes` finding, RESOLUTION_NOTES §9).
    """
    from k2kremote.k2kmessages import ScreenState, classify_screen

    for line in ("Initializing all memory. Please wait...",
                 "Clearing data...",
                 "Deleting Program 200...",
                 "WARNING! Hard reset? Are you sure?",
                 "WARNING! Delete all RAM progs?"):
        assert classify_screen([line]) is ScreenState.DESTRUCTIVE, line


def test_destructive_outranks_error_outranks_busy():
    """Order is the safety property, so it is asserted rather than assumed.

    Over-reporting DESTRUCTIVE costs a Ctrl+r; under-reporting it risks the
    hardware. The table must therefore be ordered, not merely populated.
    """
    from k2kremote.k2kmessages import STATE_MARKERS, ScreenState

    order = [state for state, _ in STATE_MARKERS]
    first = {s: order.index(s) for s in set(order)}
    last = {s: len(order) - 1 - order[::-1].index(s) for s in set(order)}
    assert last[ScreenState.DESTRUCTIVE] < first[ScreenState.ERROR]
    assert last[ScreenState.ERROR] < first[ScreenState.BUSY]


def test_an_ordinary_screen_is_classified_as_nothing_at_all():
    from k2kremote.k2kmessages import classify_screen

    assert classify_screen(["ProgramMode", "999 Grand Piano", "",
                            "Octav- Octav+ Chan- Chan+ Sample"]) is None
    assert classify_screen([]) is None


def test_a_message_wrapped_across_rows_is_still_recognised():
    """The K2000 wraps freely, so the frame is matched joined, not per row."""
    from k2kremote.k2kmessages import ScreenState, classify_screen

    rows = ["Are you sure you want to delete", "Program 200 Grand Piano?",
            "", "", "", "", "", "Yes       No"]
    assert classify_screen(rows) is ScreenState.DESTRUCTIVE
