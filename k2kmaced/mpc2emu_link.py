# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# Locates and imports the sibling mpc2emu project (GPL-2.0-or-later) — its
# parsers/krz_parser.py reads .KRZ banks and writers/fat16.py builds K2000
# pseudo-DOS FAT16 images. k2kremote works without it; this module only makes
# it usable when it is present.
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

"""Optional bridge to the sibling **mpc2emu** project.

mpc2emu already knows how to read a ``.KRZ`` bank and how to lay out a K2000
pseudo-DOS FAT16 volume. k2kremote uses it, when it is installed next door, to
say what is *inside* the banks a macro loads — the macro itself only stores
paths, banks and load modes, never object names.

Discovery order: ``$K2KREMOTE_MPC2EMU``, then a sibling ``../mpc2emu`` next to
this checkout, then whatever is already importable. Nothing here is required:
every entry point degrades to ``None``/``False`` when mpc2emu is absent.
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path
from typing import Optional

__all__ = ["locate", "available", "parse_krz", "krz_summary", "format_new"]


@functools.lru_cache(maxsize=1)
def locate() -> Optional[Path]:
    """Directory holding the mpc2emu package, or ``None``."""
    candidates = []
    env = os.environ.get("K2KREMOTE_MPC2EMU")
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(Path(__file__).resolve().parent.parent.parent / "mpc2emu")
    for path in candidates:
        if (path / "parsers" / "krz_parser.py").is_file():
            return path
    return None


def _import(module: str):
    """Import one mpc2emu module, or return ``None``.

    mpc2emu's modules import each other by top-level name (``from models.common
    import …``), so its **project root** goes on ``sys.path`` and its packages
    are imported unqualified. The path is *appended*, never prepended, so
    k2kremote's own modules always win a name clash.
    """
    root = locate()
    if root is None:
        return None
    if str(root) not in sys.path:
        sys.path.append(str(root))
    try:
        return __import__(module, fromlist=["_"])
    except Exception:  # a partial checkout, a missing numpy, an API change …
        return None


def available() -> bool:
    return _import("parsers.krz_parser") is not None


def parse_krz(path):
    """Parse a ``.KRZ`` bank via mpc2emu; ``None`` if that is not possible."""
    module = _import("parsers.krz_parser")
    if module is None:
        return None
    try:
        return module.parse_krz(str(path))
    except Exception:
        return None


def krz_summary(path) -> Optional[str]:
    """One-line description of a bank's contents, for the macro editor."""
    bank = parse_krz(path)
    if bank is None:
        return None
    presets = getattr(bank, "presets", None) or []
    samples = getattr(bank, "samples", None) or []
    return f"{len(presets)} program(s), {len(samples)} sample(s)"


def format_new(*args, **kwargs):
    """mpc2emu's FAT16 image builder — used by the tests to make a fixture."""
    module = _import("writers.fat16")
    if module is None:
        raise RuntimeError("mpc2emu is not available (see k2kremote.mpc2emu_link)")
    return module.format_new(*args, **kwargs)
