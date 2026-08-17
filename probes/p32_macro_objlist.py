# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 26: how is a macro entry's object list encoded? (NO MIDI — file analysis)

The one part of the ``.MAC`` format still opaque (MAC_FORMAT.md §6). A macro
entry can load *selected objects* from a file instead of the whole file; the
K2000 marks those ``Obj`` on the Macro page and shows them as ``Program 210``
type/id pairs. No such entry existed anywhere on this machine, so ``macfile``
preserves the surplus bytes verbatim (``MacroEntry.extra``) instead of guessing.

This probe **opens no MIDI port**. The hardware work is front-panel only.

On the K2000, build two macros that differ in exactly one thing:

  1. Disk mode → Macro → **On** (Record).
  2. Load page → highlight a ``.KRZ`` → **OK** → choose a bank → press *Macro*
     (not OK, so nothing loads). Save as ``PLAIN.MAC``.
  3. Macro → Off → On again (a fresh, empty table).
  4. Load page → highlight the **same** ``.KRZ`` → **Open** → select two or
     three objects → OK → same bank → press *Macro*. Save as ``OBJLIST.MAC``.
  5. Note which objects you picked — type and id — and copy both files over.

Then:

    .venv/bin/python probes/p32_macro_objlist.py PLAIN.MAC OBJLIST.MAC

It isolates the bytes the object list adds and reads them back as candidate
type/id pairs, so the layout can be written up against what you actually
selected.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from k2kmaced.macfile import MacError, PramFile  # noqa: E402

if len(sys.argv) != 3:
    sys.exit("usage: p32_macro_objlist.py PLAIN.MAC OBJLIST.MAC")

plain_path, objlist_path = sys.argv[1], sys.argv[2]


def load(path):
    try:
        return PramFile.parse(open(path, "rb").read()).macro_table()
    except (MacError, OSError) as exc:
        sys.exit(f"{path}: {exc}")


def hexdump(data, base=0, width=16):
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hexed = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  {base + off:04x}  {hexed:<{width * 3}} {text}")


plain, objlist = load(plain_path), load(objlist_path)
print(f"{os.path.basename(plain_path)}:   {len(plain)} entr(y/ies)")
print(f"{os.path.basename(objlist_path)}: {len(objlist)} entr(y/ies)\n")

for i, entry in enumerate(objlist):
    twin = plain[i] if i < len(plain) else None
    mine, theirs = entry.serialize(), twin.serialize() if twin else b""
    print(f"=== entry {i}: {entry.display().rstrip()} ===")
    print(f"  length {len(mine)} vs {len(theirs) if twin else '—'} in the plain macro"
          f"  ({len(mine) - len(theirs):+d} bytes)" if twin else f"  length {len(mine)}")
    print(f"  has_object_list={entry.has_object_list}  extra={len(entry.extra)} bytes")

    if not entry.extra:
        print("  no surplus bytes — either this entry has no object list, or the "
              "list is packed into the fields macfile already models. Diff the "
              "two entries by hand:")
        if twin and mine != theirs:
            print("  objlist entry:")
            hexdump(mine)
            print("  plain entry:")
            hexdump(theirs)
        print()
        continue

    print("  surplus bytes (offset is from the start of the entry):")
    hexdump(entry.extra, base=len(mine) - len(entry.extra))

    # The Macro Object List display names objects by type and id, so u16 pairs
    # are the obvious reading; print both alignments and let the operator match
    # them against what was actually selected.
    data = entry.extra
    print("  as u16 pairs (type, id):")
    for off in (0, 2):
        words = struct.unpack_from(f">{(len(data) - off) // 2}H", data, off) \
            if len(data) - off >= 2 else ()
        pairs = [f"({words[j]}, {words[j + 1]})" for j in range(0, len(words) - 1, 2)]
        print(f"    from +{off}: {' '.join(pairs) if pairs else '—'}")
    print("  as u16 words: "
          + " ".join(str(w) for w in struct.unpack(f">{len(data) // 2}H",
                                                   data[:len(data) // 2 * 2])))
    print("\n  Match these against the objects you selected. K2000 object types "
          "over MIDI: 132 Program, 133 Keymap, 134 Sample, 135 Setup, 112 Song, "
          "113 Effect (disk-file types are those minus 96). The manual also "
          "shows a '(load dependents)' flag on that display — look for a lone "
          "byte/word that changes when you toggle it.\n")

print("Write the result up in MAC_FORMAT.md §6 and teach MacroEntry to decode "
      "it; `extra` already isolates exactly these bytes.")
