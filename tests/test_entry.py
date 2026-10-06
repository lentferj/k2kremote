# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

"""The console-script entry points, and the message for a missing library.

The interesting case cannot be reached by importing what is already imported:
the whole point of :mod:`k2kremote.entry` is that it runs *before* any module
that imports ``vinsynlib``, so a test that has already imported
``k2kremote.app`` -- and therefore already imported the library -- is testing
nothing. The diagnosis is therefore exercised by making the import fail inside
it, which is also the only way to prove the message says what it claims.

What these guard against is not hypothetical. A user who pulls this repository
without reinstalling has no ``vinsynlib``; before the entry points checked,
that produced a bare ``ModuleNotFoundError`` traceback naming a package they
never asked for. On Windows the console script closes before the traceback can
be read, so nothing is said at all.
"""

from __future__ import annotations

import builtins
from typing import Any

import pytest

from k2kremote import entry

REQUIRED_BITS = (
    "error:",
    "vinsynlib",
    "pip install",
    # The one instruction that works today, before the library is published.
    "git+https://github.com/lentferj/vinsynlib",
)


def _hide_vinsynlib(monkeypatch: Any) -> None:
    """Make ``import vinsynlib`` raise ModuleNotFoundError, as it would."""
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "vinsynlib" or name.startswith("vinsynlib."):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_a_missing_library_is_diagnosed(monkeypatch: Any) -> None:
    _hide_vinsynlib(monkeypatch)
    problem = entry._diagnose("k2kmon")
    assert problem is not None
    for bit in REQUIRED_BITS:
        assert bit in problem, bit


def test_the_message_goes_to_stderr_and_returns_one(monkeypatch: Any, capsys: Any) -> None:
    """Not a traceback, not exit 0, not stdout.

    A missing dependency is exit 1: the family's code for "it did not
    work". Exit 2 means the command line was wrong, which this is not.
    """
    _hide_vinsynlib(monkeypatch)
    assert entry.app() == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "vinsynlib" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("name", ["app", "monitor", "maced", "macli"])
def test_every_front_end_says_the_same_thing(name: str, monkeypatch: Any, capsys: Any) -> None:
    """All four commands are one message, not four different failures."""
    _hide_vinsynlib(monkeypatch)
    assert getattr(entry, name)() == 1
    assert "vinsynlib" in capsys.readouterr().err


def test_a_missing_module_that_is_not_ours_is_not_blamed_on_us(
    monkeypatch: Any,
) -> None:
    """A ModuleNotFoundError for something else is a bug in the library.

    Telling the user to install ``vinsynlib`` when the real problem is a
    missing dependency *inside* it would send them the wrong way, and the
    thing they would install is the thing they already have.
    """
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "vinsynlib":
            raise ModuleNotFoundError("No module named 'some_dep'", name="some_dep")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ModuleNotFoundError, match="some_dep"):
        entry._diagnose("k2kmon")


def test_an_installed_library_is_reported_healthy() -> None:
    """The normal case, in this very environment."""
    assert entry._diagnose("k2kmon") is None


def test_an_older_library_is_named_rather_than_ignored(
    monkeypatch: Any,
) -> None:
    """The failure without this check is an AttributeError deep in a call,
    which says nothing about which of the two things needs upgrading."""
    import vinsynlib

    monkeypatch.setattr(vinsynlib, "__version__", "0.0.9")
    problem = entry._diagnose("k2kmon")
    assert problem is not None
    assert "0.1.0" in problem
    assert "0.0.9" in problem


def test_a_current_library_passes(monkeypatch: Any) -> None:
    import vinsynlib

    wanted = ".".join(str(part) for part in entry.MINIMUM)
    monkeypatch.setattr(vinsynlib, "__version__", wanted)
    assert entry._diagnose("k2kmon") is None


def test_the_diagnosis_imports_nothing_from_this_project() -> None:
    """It has to be importable when nothing else is.

    ``k2kremote.entry`` is the console-script target. If it imported
    ``k2kremote.app`` or ``k2kremote.midi_bridge``, it would trigger the very
    import it exists to guard, and the friendly message would never be
    reached.
    """
    source = __import__("pathlib").Path(entry.__file__).read_text(encoding="utf-8")
    for banned in ("from k2kremote", "import k2kremote", "from k2kmaced", "import k2kmaced"):
        assert banned not in source, banned


def test_the_message_names_the_command_that_was_typed(monkeypatch: Any, capsys: Any) -> None:
    """Three of the four commands are not called `k2kremote`.

    A message telling somebody running `k2kmon` that `k2kremote` cannot
    start sends them looking for the wrong problem, and the four commands
    here share one distribution name and one launcher.
    """
    _hide_vinsynlib(monkeypatch)
    assert entry.monitor() == 1
    err = capsys.readouterr().err
    assert "error: k2kmon cannot start" in err
    # Names the distribution too, so it is clear where k2kmon comes from.
    assert "k2kremote" in err


def test_every_command_names_itself(monkeypatch: Any, capsys: Any) -> None:
    _hide_vinsynlib(monkeypatch)
    for fn, command in (
        (entry.app, "k2kremote"),
        (entry.monitor, "k2kmon"),
        (entry.maced, "k2kmaced"),
        (entry.macli, "k2kmacli"),
    ):
        assert fn() == 1
        err = capsys.readouterr().err
        assert f"error: {command} cannot start" in err, (command, err)
