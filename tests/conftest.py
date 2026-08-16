# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

import pytest


@pytest.fixture(autouse=True)
def _isolate_user_state(tmp_path, monkeypatch):
    """Keep the suite out of the real ``$XDG_CACHE_HOME``.

    The app caches its window size on unmount, and every ``run_test()`` unmounts
    — so without this the suite quietly writes Textual's default 80x24 into the
    user's own cache and the next real launch inherits it. It was caught only
    because that junk value showed up in a live cache dir. Autouse, because any
    test that starts the app triggers it whether or not it cares about sizing.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
