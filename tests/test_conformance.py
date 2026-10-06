# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

"""k2kremote keeps the contract the rest of the family keeps.

Every check below is the shared one, run against this program rather than
written out again here. The reasons are in ``vinsynlib`` and in the family's
``docs/UX-SPEC.md``: what drifted was never a bug anyone chose, it was a copy
that nobody had a second copy to compare against.

**k2kremote is neither of the library's two key tiers.** It mirrors a
keyboard's front panel -- function keys, soft keys, cursor, Enter -- rather
than browsing banks or editing a sampler, and it has no favourites store. So
``check_bindings`` and ``check_legend`` are deliberately NOT run against it:
they would demand browser keys (``f`` favourite, ``/`` search) this program has
no concept for, or editor keys it does not have either. What IS checked is what
it genuinely shares: the canonical flags, the vocabulary, and the legend
widget.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from k2kmaced import app as macro_app
from k2kmaced import cli as macro_cli
from k2kremote import app as mirror_app
from k2kremote import monitor
from k2kremote.terms import TERMS
from vinsynlib import conformance
from vinsynlib.keys import wrap_blocks as family_wrap_blocks
from vinsynlib.ui.hints import KeyHints as family_key_hints


def _subparsers(parser: argparse.ArgumentParser) -> dict:
    """The named subparsers of ``parser``, for the commands that carry --port."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


# --- the command line --------------------------------------------------------


def test_the_mirror_offers_the_shared_flags_it_has() -> None:
    """--port, --config and --demo, worded the family's way.

    The options this program does NOT have are named as forbidden rather than
    left out: that is the assertion that a future change cannot quietly add a
    --channel or a --favorites it has no concept for.
    """
    problems = conformance.check_flags(
        mirror_app.build_parser(),
        required=("port", "config", "demo"),
        forbidden=("scan", "channel", "device-id", "favorites", "timeout"),
    )
    assert not problems, "\n".join(problems)


def test_the_monitor_offers_only_the_shared_port() -> None:
    problems = conformance.check_flags(
        monitor.build_parser(),
        required=("port",),
        forbidden=("config", "demo", "channel", "device-id", "scan"),
    )
    assert not problems, "\n".join(problems)


def test_the_macro_editor_offers_no_shared_flags_it_has_no_concept_for() -> None:
    """It never opens a MIDI port, so it takes none of the family's options."""
    problems = conformance.check_flags(
        macro_app.build_parser(),
        required=(),
        forbidden=("port", "config", "demo", "channel", "device-id", "scan"),
    )
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("command", ["live", "diff", "push"])
def test_the_macro_cli_device_commands_take_the_shared_port(command: str) -> None:
    """The three commands that open a port use the family's --port."""
    parsed = _subparsers(macro_cli.build_parser())
    assert command in parsed, f"{command} is not a command any more"
    assert not conformance.check_flags(parsed[command], required=("port",))


# --- the vocabulary ----------------------------------------------------------


def test_the_vocabulary_is_declared() -> None:
    assert not conformance.check_terms(TERMS)
    assert TERMS.sound == "program", "the K2000's own word for one stored sound"
    assert TERMS.container == "bank", "where those programs live"
    assert TERMS.device == "Kurzweil K2000/K2000R"


# --- the legend --------------------------------------------------------------


def test_both_legends_are_produced_through_the_shared_code() -> None:
    """Not the shared *browser* legend -- the shared *widget*.

    The mirror wraps the family's :class:`KeyHints` (to fold between this
    project's key groups); the macro editor uses it directly. Both fold with
    :func:`vinsynlib.keys.wrap_blocks`, which is the point: a footer that
    truncates silently teaches the user a key does not exist.
    """
    assert mirror_app.wrap_blocks is family_wrap_blocks
    assert macro_app._wrap_blocks is family_wrap_blocks
    assert issubclass(mirror_app.KeyHints, family_key_hints)
    assert macro_app.KeyHints is family_key_hints


@pytest.mark.asyncio
async def test_the_mirror_legend_wraps_and_loses_no_key() -> None:
    from k2kremote.app import K2KRemoteApp

    app = K2KRemoteApp(demo=True, text_mode=True)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        widget = app.query_one("#keyhints")
        assert isinstance(widget, family_key_hints)
        rendered = str(widget.render())
    # The last block of the flat legend: with truncation it was the one a
    # narrow window dropped, so it is the one that proves wrapping.
    assert "Ctrl+c quit" in rendered


@pytest.mark.asyncio
async def test_the_macro_legend_wraps_and_loses_no_key() -> None:
    fixture = Path(__file__).parent / "fixtures" / "BOOT.MAC"
    app = macro_app.K2kmacedApp(macro_app.build_editor(str(fixture)))
    async with app.run_test(size=(70, 24)) as pilot:
        await pilot.pause()
        widget = app.query_one("#legend")
        assert isinstance(widget, family_key_hints)
        rendered = str(widget.render())
    missing = [block for block in macro_app.LEGEND_BLOCKS if block not in rendered]
    assert not missing, missing


@pytest.mark.parametrize(
    "name,builder",
    [
        ("k2kremote", mirror_app.build_parser),
        ("k2kmon", monitor.build_parser),
        ("k2kmaced", macro_app.build_parser),
        ("k2kmacli", macro_cli.build_parser),
    ],
)
def test_every_command_can_report_its_version(name: str, builder) -> None:
    """All four come from one distribution, and three are named differently.

    `--version` is found from the installed distribution, and the lookup
    uses the program's name unless the parser is told otherwise. With one
    distribution and four command names, three of them found no version and
    silently had no `--version` at all -- so this walks all four and checks
    the option is there and answers with a number.
    """
    parser = builder()
    options = {opt for action in parser._actions for opt in action.option_strings}
    assert "--version" in options, f"{name} has no --version"
