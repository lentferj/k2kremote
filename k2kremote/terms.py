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

"""What the Kurzweil K2000 calls things, declared once.

**The instrument's word is the instrument's.** A K2000 stores **programs**, and
programs live in **banks** (the manual, the panel and the object database all
say so). Those are the words every string this project shows a user uses.

This is the ancestor of the family, so its vocabulary is the oldest rather than
a port of somebody else's: "program" is by a wide margin this project's own
dominant word for one stored sound, and "bank" for the area it lives in. That
is exactly the family's rule -- the unit prints its own word on its own LCD,
and a tool that renames it is a tool that has to translate.

**k2kremote is a remote, not a browser, and has no favourites store.** It
mirrors the front panel of a keyboard and presses its buttons; there is no
favourites database here and none is added. The family's key and flag checks
know that, so the vocabulary below is the whole of what this tool declares.
"""

from __future__ import annotations

from vinsynlib.terms import Terminology, register

__all__ = ["TERMS"]

TERMS = Terminology(
    app_name="k2kremote",
    sound="program",
    container="bank",
    device="Kurzweil K2000/K2000R",
)

#: Registered at import so the family's registry knows what this tool calls
#: its concepts. Registration rather than a monkeypatched module global: a
#: library cannot know the name of the program using it, and passing it in is
#: honest where patching is global.
register(TERMS)
