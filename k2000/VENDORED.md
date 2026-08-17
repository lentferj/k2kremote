<!-- SPDX-License-Identifier: MIT -->
# Vendored: psobot/k2000

This directory is a verbatim vendored copy of the **psobot/k2000** library by
Peter Sobot (https://github.com/psobot/k2000), which implements the Kurzweil
K2000 MIDI SysEx protocol. It is included in k2kremote's source tree so the
application runs without a separate manual/git install of this dependency.

It is licensed under the **MIT License** (see `LICENSE` in this directory),
which permits redistribution; k2kremote as a whole is GPL-2.0-or-later, and the
MIT terms continue to apply to the files in this directory.

## Local changes

Kept minimal, and each one is a separate commit so it stays easy to rebase onto
a new upstream release:

| File | Change | Why |
|---|---|---|
| `messages.py` | `_decode_object_type()` maps object type `0` to `None` for `EndOfBank` / `DelBank` / `MoveBank` | The all-types DELBANK ("Delete all objects") is acknowledged with an ENDOFBANK whose type field is `0`, which upstream fails to decode |
| `definitions.py` | `ObjectType.MacroTable = 100` | The Macro Table (type 100, id 35) is the object a `.MAC` file holds; needed to DUMP the live macro list. See [`docs/MAC_FORMAT.md`](../docs/MAC_FORMAT.md) |
