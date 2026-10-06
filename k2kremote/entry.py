# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
#
# k2kremote is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 2 of the License, or (at your option) any later
# version.
#
# k2kremote is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.

"""Console-script entry points, which check the shared library is installed.

``k2kremote`` and its front ends share one library, ``vinsynlib``. It is an
ordinary installation dependency, and the ordinary way for a dependency to be
missing is that somebody pulled the source without reinstalling.

Without this module the failure is a bare ``ModuleNotFoundError`` raised from
inside a module-level ``import`` -- a traceback naming a package the user never
asked for, with no hint that it is a normal dependency and no hint of what to
do about it. Worse on Windows, where a console script exits before the
traceback can be read: the terminal closes and nothing is said at all.

This is the one place that can say something useful, because it runs before any
module that imports the library. It is deliberately tiny, and it must keep
importing nothing but the standard library -- including it must not import
anything else from this project.
"""

from __future__ import annotations

import sys
from importlib import import_module

#: The minimum that has the API this project was written against.
MINIMUM = (0, 1, 0)

#: Where to get it while it is not on an index. Kept in one place because it
#: appears in the message twice and must not drift.
SOURCE = "vinsynlib @ git+https://github.com/lentferj/vinsynlib"


def _diagnose() -> str | None:
    """``None`` if the shared library is usable, else what to tell the user.

    ``ModuleNotFoundError.name`` is checked before blaming ourselves: a
    ``ModuleNotFoundError`` for something else is a bug in ``vinsynlib`` and a
    how-to-install message would be a lie about it.
    """
    try:
        import vinsynlib
    except ModuleNotFoundError as exc:
        if exc.name and not exc.name.startswith("vinsynlib"):
            raise
        return _missing()
    version = getattr(vinsynlib, "__version__", None)
    if not isinstance(version, str):
        return _missing()
    try:
        current = tuple(int(part) for part in version.split(".")[:3])
    except ValueError:
        return None
    if current < MINIMUM:
        return _too_old(version)
    return None


def _how_to_install() -> str:
    return (
        "Install it from source (it is not on PyPI yet):\n"
        "\n"
        f'    pip install "{SOURCE}"\n'
        "\n"
        "Installing this project itself brings it in too, which is the usual\n"
        "way in from a clone:\n"
        "\n"
        "    pip install -e .        # or: uv sync\n"
    )


def _missing() -> str:
    return (
        "error: k2kremote cannot start: the shared library "
        '"vinsynlib" is not installed.\n'
        "\n"
        "k2kremote is the ancestor of a family of terminal instrument\n"
        "tools that share this library for the settings cache, the keymap,\n"
        "the command line, the MIDI port listing and the clean-exit handler,\n"
        "so it cannot run without it.\n"
        "\n" + _how_to_install()
    )


def _too_old(found: str) -> str:
    wanted = ".".join(str(part) for part in MINIMUM)
    return (
        f"error: k2kremote needs vinsynlib {wanted} or newer, and {found} is "
        "installed.\n"
        "\n"
        "Something installed an older copy, most likely as a dependency of\n"
        "an older release of one of the sibling tools. Upgrade it:\n"
        "\n"
        f'    pip install --upgrade "{SOURCE}"\n'
    )


def _run(target: str) -> int:
    """Check the library, then hand over to the real entry point."""
    problem = _diagnose()
    if problem is not None:
        # stderr, and exit code 1: the family's error convention. A missing
        # dependency is not a wrong command line, which would be 2.
        sys.stderr.write(problem)
        return 1

    module, _, attribute = target.partition(":")
    entry = getattr(import_module(module), attribute)
    # `main` returning None is tolerated rather than a failure: the family
    # convention is an int, but a front end that has not been converted yet
    # must still launch.
    return int(entry() or 0)


def app() -> int:
    """The ``k2kremote`` command (the LCD mirror)."""
    return _run("k2kremote.app:main")


def monitor() -> int:
    """The ``k2kmon`` command (the SysEx inspector)."""
    return _run("k2kremote.monitor:main")


def maced() -> int:
    """The ``k2kmaced`` command (the macro editor TUI)."""
    return _run("k2kmaced.app:main")


def macli() -> int:
    """The ``k2kmacli`` command (the macro editor pipe front end)."""
    return _run("k2kmaced.cli:main")
