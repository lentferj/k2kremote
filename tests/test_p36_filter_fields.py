# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""current_field() must strip internal label padding, not just outer whitespace.

The K2000 pads short labels with spaces before the colon to align the value
column across a page -- e.g. "Depth :", "Src1  :" -- so a naive
strip().rstrip(":") leaves "Depth ", "Src1  " and goto_field() can never match
the plain field name. Found 2026-08-31 chasing a silent goto_field(bridge,
'Depth') failure live on hardware; see RESOLUTION_NOTES.md.
"""
import pathlib
import sys
from types import SimpleNamespace

# Not sys.path.insert(0, ".") -- that resolves against the process CWD, so
# running pytest from inside tests/ aborts collection with ModuleNotFoundError
# rather than skipping.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from probes.p36_filter_fields import current_field


def _bridge(raw_name, raw_value):
    return SimpleNamespace(
        client=SimpleNamespace(
            get_current_parameter_name=lambda: raw_name,
            get_current_parameter_value=lambda: raw_value,
        )
    )


def test_current_field_strips_internal_padding_before_colon():
    assert current_field(_bridge("Depth :", "0ct")) == ("Depth", "0ct")
    assert current_field(_bridge("Src1  :", "OFF")) == ("Src1", "OFF")


def test_current_field_unpadded_label_unaffected():
    assert current_field(_bridge("Coarse:", "0ST")) == ("Coarse", "0ST")
    assert current_field(_bridge("FineHz:", " 0.00Hz")) == ("FineHz", "0.00Hz")
