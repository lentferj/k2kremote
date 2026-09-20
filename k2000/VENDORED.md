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
| `messages.py` | `_encode_object_type()`, used by `EndOfBank` / `DelBank` / `MoveBank` `_encode_body` | Type `0` decodes to `None`, and `None.value` then made the round trip one-way: a message read off the wire could not be encoded again |
| `encoding.py` | `decode_data_field()` raises when the decoded data is shorter than the message's declared `size` | A clipped long SysEx dump came back silently short, and nothing downstream can tell that from a small object — a verified read-back could "confirm" bytes that never arrived |

The `MoveBank` half of the first row was documented before it was true: until
2026-09-20 only `EndOfBank` and `DelBank` used `_decode_object_type`, and an
all-types MOVEBANK still failed to decode.

## Upstream quirks we live with (not patched)

Recorded so nobody rediscovers them as bugs in *our* code:

- **`Button.SoftYes`/`SoftNo` are aliases, not buttons** (`definitions.py`):
  they repeat the values of `SoftE`/`SoftF`, so `Button(0x26).name` is
  `"SoftE"` and `client.yes()`/`.no()` press the fifth and sixth soft buttons
  whatever the screen happens to have on them. Nothing in k2kremote uses them:
  every dialog answer here searches the soft-button row for its *label* and
  presses the button under it (`macro_save.py`, `disk_browse.py`), because
  which soft button carries "Yes" is a property of the page, not of the
  hardware.
- **`EndOfBank._response_classes = [Info]`** (`messages.py`): a DIRBANK sent
  through `client._send_and_receive` can therefore never return the terminator
  that ends the listing — the reply shape (INFO×N then ENDOFBANK) does not fit
  one-reply-per-request at all. `MidiBridge.list_bank` drains the input itself
  for exactly this reason.
