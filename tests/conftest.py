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


@pytest.fixture(autouse=True)
def _undo_the_device_id_shim():
    """Leave `k2000.messages.SysexMessage` as this test found it.

    `_install_device_id_tolerance` patches a class in the *vendored library*,
    process-wide, and nothing used to put it back -- so one test that installed
    it silently changed how every later test decoded SysEx, in whatever order
    pytest happened to run them.
    """
    from k2000 import messages

    was = (messages.SysexMessage.decode,
           messages.SysexMessage.has_valid_k2_headers,
           getattr(messages, "_k2kremote_devid_tolerant", False),
           getattr(messages, "_k2kremote_devid_originals", None))
    yield
    messages.SysexMessage.decode = was[0]
    messages.SysexMessage.has_valid_k2_headers = was[1]
    messages._k2kremote_devid_tolerant = was[2]
    if was[3] is None:
        if hasattr(messages, "_k2kremote_devid_originals"):
            del messages._k2kremote_devid_originals
    else:
        messages._k2kremote_devid_originals = was[3]
