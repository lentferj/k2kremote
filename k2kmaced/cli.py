# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# Macro semantics from the Kurzweil K2vx manual, chapter 13 ("Macros",
# "Creating a Startup File"); see docs/MAC_FORMAT.md.
# Optionally reads the referenced .KRZ banks through the sibling mpc2emu
# project's parsers/krz_parser.py (GPL-2.0-or-later).
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

"""``k2kmaced.cli`` — inspect and edit K2000 ``.MAC`` macro files.

Sources a macro can come from:

* a ``.MAC`` file on the host;
* a **K2000 disk image** (raw ``.img`` or ``lzop``-compressed ``.img.lzo``),
  addressed as ``image.img:\\BOOT.MAC`` — the image is only ever read;
* the **live device** (``--device``), which dumps the in-RAM Macro Table.

Every command writes to a *new* file, **except ``install``**, which is the one
that puts an edited macro back into an image, in place, over a file already
there. It is separate, it asks for typed confirmation, and it makes no backup
for you — a bad ``BOOT.MAC`` is a bad boot, since it decides which banks are
resident after power-on. Nothing is ever sent to the K2000.

    k2kmacli list BOOT.MAC
    k2kmacli list ~/backup/HD0.img.lzo:'\\BOOT.MAC'
    k2kmacli find ~/backup/HD0.img.lzo
    k2kmacli check BOOT.MAC --image ~/backup/HD0.img.lzo
    k2kmacli edit BOOT.MAC -o NEW.MAC --rebank 3=700 --move 5=0
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Tuple

from k2kmaced.k2image import DiskImage, ImageError, is_disk_image
from k2kmaced.k2write import (
    ImageWriteError,
    plan_replacement,
    replace_file_in_image,
)
from k2kmaced.macfile import (
    BANK_EVERYTHING,
    DRIVE_LABELS,
    MODE_LABELS,
    MacError,
    MacroEntry,
    MacroTable,
    PramFile,
)

__all__ = ["parse_source", "load_macro", "format_table", "main"]


# --- sources ---------------------------------------------------------------


def parse_source(spec: str) -> Tuple[str, Optional[str]]:
    """Split ``image.img:\\BOOT.MAC`` into ``(image, member)``.

    A bare path returns ``(path, None)``. Only a ``:`` followed by a DOS path
    separator splits, and the part before it must be more than a single
    character — otherwise ``C:\\Users\\me\\hd0.img`` splits at the **drive
    letter** into image ``C`` and member ``\\Users\\me\\hd0.img``.

    That is not hypothetical: this function claimed to leave drive letters alone
    and did not, and every Windows job in CI failed on it with
    ``FileNotFoundError: 'C'`` the first time the macro tests ran there. A
    one-character head is never a real image path, so length is the whole test.
    """
    head, sep, tail = spec.rpartition(":")
    if sep and tail.startswith("\\") and len(head) > 1:
        return head, tail
    return spec, None


def load_macro(spec: str) -> Tuple[PramFile, str]:
    """Load a macro from a file or from ``image:\\member``.

    Returns the container and a human-readable description of where it came
    from.
    """
    path, member = parse_source(spec)
    if member is None and is_disk_image(path):
        raise MacError(
            f"{path} looks like a disk image; address a file inside it as "
            f"{path}:\\BOOT.MAC (or run 'find' to list the macros it holds)"
        )
    if member is None:
        with open(path, "rb") as fh:
            return PramFile.parse(fh.read()), path
    with DiskImage.open(path) as image:
        return PramFile.parse(image.read_file(member)), f"{member} in {path}"


def load_from_device(bridge) -> Tuple[MacroTable, str]:
    """Dump the live in-RAM Macro Table off a connected K2000."""
    data = bridge.read_macro_table()
    return MacroTable.parse(data), "the connected K2000"


# --- presentation ----------------------------------------------------------


def format_table(table: MacroTable, *, numbered: bool = True) -> List[str]:
    """Render the table the way the K2000's own Macro page would."""
    lines = []
    for i, entry in enumerate(table):
        prefix = f"{i:>3}  " if numbered else ""
        lines.append(prefix + entry.display().rstrip())
    if not lines:
        lines.append("    (empty macro table)")
    return lines


def _bank(text: str) -> int:
    if text.upper() in ("E", "EVERYTHING"):
        return BANK_EVERYTHING
    value = int(text)
    if not (0 <= value <= 900 and value % 100 == 0):
        raise argparse.ArgumentTypeError(
            f"bank must be 0, 100 … 900 or E (everything), not {text!r}"
        )
    return value


def _mode(text: str) -> int:
    for code, (name, letter) in MODE_LABELS.items():
        if text.upper() in (name.upper(), letter):
            return code
    raise argparse.ArgumentTypeError(
        f"mode must be one of {', '.join(n for n, _ in MODE_LABELS.values())}"
    )


def _drive(text: str) -> int:
    for code, name in DRIVE_LABELS.items():
        if text.upper() == name.upper():
            return code
    if text.upper().startswith("SCSI") and text[4:].strip().isdigit():
        return 1 + int(text[4:].strip())
    raise argparse.ArgumentTypeError(
        f"drive must be one of {', '.join(DRIVE_LABELS.values())}"
    )


def _index_value(arg: str) -> Tuple[int, str]:
    index, _, value = arg.partition("=")
    if not value:
        raise argparse.ArgumentTypeError(f"expected INDEX=VALUE, got {arg!r}")
    return int(index), value


# --- commands --------------------------------------------------------------


def _cmd_list(args) -> int:
    pram, where = load_macro(args.source)
    table = pram.macro_table()
    print(f"{where}: {len(table)} entr{'y' if len(table) == 1 else 'ies'} "
          f"(written by K2000 OS v{pram.software_version / 100:.2f})")
    for line in format_table(table):
        print(line)
    return 0


def _open_bridge(args):
    """Connect to the instrument. Imported lazily so the offline CLI never needs
    python-rtmidi installed just to list a file."""
    from k2kremote.midi_bridge import MidiBridge

    if getattr(args, "port", None):
        return MidiBridge.open(args.port)
    if getattr(args, "rig", "auto") == "auto":
        return MidiBridge.autodetect()
    return MidiBridge.open_first()


def _cmd_live(args) -> int:
    """Show the macro table the running instrument holds in RAM. READ-ONLY."""
    from k2kmaced import online

    bridge = _open_bridge(args)
    try:
        table = online.read_live(bridge)
        print(f"live macro table on {bridge.description}: "
              f"{len(table)} entr{'y' if len(table) == 1 else 'ies'}")
        for line in format_table(table):
            print(line)
    finally:
        bridge.close()
    return 0


def _cmd_diff(args) -> int:
    """Compare the live macro table against a .MAC file. READ-ONLY, both sides."""
    from k2kmaced import online

    pram, where = load_macro(args.source)
    on_disk = pram.macro_table()

    bridge = _open_bridge(args)
    try:
        live = online.read_live(bridge)
    finally:
        bridge.close()

    rows = online.diff(list(live), list(on_disk))
    print(f"   {'#':>2}  {'live (in RAM)':<34} {where}")
    for row in rows:
        print(row.format())
    print()
    print(online.summarise(rows))
    # Non-zero on a difference, so this is usable as a check in a script.
    return 0 if all(r.same for r in rows) else 1


def _cmd_find(args) -> int:
    with DiskImage.open(args.image) as image:
        macros = image.find(".MAC")
        if not macros:
            print(f"{args.image}: no .MAC files")
            return 1
        for entry in macros:
            print(f"{entry.size:>8}  {entry.path}")
    return 0


def _cmd_extract(args) -> int:
    with DiskImage.open(args.image) as image:
        data = image.read_file(args.member)
    PramFile.parse(data).macro_object()  # fail early if it is not a macro
    with open(args.output, "wb") as fh:
        fh.write(data)
    print(f"wrote {args.output} ({len(data)} bytes) from {args.member}")
    return 0


_WARNING_LINES = [
    "!!!   THIS WRITES INTO YOUR DISK IMAGE, IN PLACE, RIGHT NOW   !!!",
    "",
    "The image file you named is modified directly. There is no undo, and",
    "this tool does NOT make a backup for you.",
    "",
    "It is YOUR responsibility to have a good, current backup of this image,",
    "kept somewhere else - a different disk, not beside the original.",
    "",
    "Downstream of here it gets less forgiving still: an image you write to",
    "a K2000 disk replaces what was on that disk, and a bad BOOT.MAC is a",
    "bad boot. Verify the macro before you commit the image to the machine.",
]


def _boxed(lines) -> str:
    """Frame ``lines`` in a box sized to fit them.

    Drawn rather than typed out: a hand-drawn box's border stops matching its
    contents the first time anyone edits the wording, and a warning with a
    visibly broken frame reads as sloppy exactly where it needs to be believed.
    ASCII only inside, because ``!`` is one column wide everywhere and an emoji
    warning sign is two in some terminals and one in others.
    """
    width = max(len(line) for line in lines)
    top = "+" + "-" * (width + 2) + "+"
    body = [f"| {line.ljust(width)} |" for line in lines]
    return "\n".join([top, *body, top])


_BACKUP_WARNING = _boxed(_WARNING_LINES)


def _cmd_install(args) -> int:
    """Write a .MAC back into a disk image, over a file that is already there."""
    macro = open(args.source, "rb").read()
    PramFile.parse(macro).macro_object()      # refuse anything that is not a macro

    plan = plan_replacement(args.image, args.member, len(macro))
    print(f"image  : {args.image}")
    print(f"target : {plan['path']}  ({plan['old_size']} → {plan['new_size']} bytes)")
    print(f"clusters: {plan['clusters']} of {plan['cluster_size']} bytes "
          f"— {plan['slack']} bytes slack, FAT untouched")
    print(_BACKUP_WARNING)

    if not args.yes:
        # Typed confirmation, not a y/n: the point is that it cannot be a reflex.
        try:
            answer = input('type "overwrite" to continue (anything else aborts): ')
        except EOFError:
            answer = ""
        if answer.strip() != "overwrite":
            print("aborted; nothing was written")
            return 1

    replace_file_in_image(args.image, args.member, macro)
    print(f"wrote {len(macro)} bytes into {plan['path']} and verified it reads back")
    return 0


def _cmd_push(args) -> int:
    """Replace the RUNNING K2000's macro table over MIDI. WRITES to the device.

    Nothing on disk changes: the instrument saves its own `BOOT.MAC` afterwards,
    from Disk -> Macro -> Save. So the failure mode is "the machine's boot macro
    is now something else", which is recoverable, not "the card is corrupt".
    """
    import os
    from k2kmaced import online

    pram, where = load_macro(args.source)
    wanted = pram.macro_table()

    bridge = _open_bridge(args)
    try:
        live = online.read_live(bridge)
        rows = online.diff(list(live), list(wanted))
        print(f"   {'#':>2}  {'live now (in RAM)':<34} {where}")
        for row in rows:
            print(row.format())
        print()
        if all(r.same for r in rows):
            print("already identical — nothing to write")
            return 0
        print(online.summarise(rows))
        print("\nThis replaces the macro table in the K2000's battery-backed RAM.")
        print("It does NOT touch the disk. To keep it, save it on the instrument")
        print("from Disk -> Save -> Macro -- and you can save it under a NEW name")
        print("rather than over BOOT.MAC, then try it with Disk -> Load before")
        print("making it the startup macro. Nothing has to overwrite BOOT.MAC.")

        if not args.yes:
            # Typed, not y/n: the same reasoning as `install`. A reflex keypress
            # should not be able to change what the instrument boots into.
            try:
                answer = input('type "write" to continue (anything else aborts): ')
            except EOFError:
                answer = ""
            if answer.strip() != "write":
                print("aborted; nothing was sent")
                return 1

        backup = args.backup or os.path.join(
            os.path.expanduser("~"), ".k2kremote-macro-backup.bin")
        after = online.push(bridge, wanted, backup_path=backup)
        print(f"wrote {len(wanted)} entries; previous table saved to {backup}")
        print("read back and verified byte-identical to what was sent:")
        for line in format_table(after):
            print(line)
        print("\nThe DISK is unchanged. To keep this, save it on the instrument;"
              "\nsaving under a new name lets you test it with Disk -> Load first.")
    finally:
        bridge.close()
    return 0


def _cmd_check(args) -> int:
    """Verify every file a macro references still exists on the image."""
    source_image, member = parse_source(args.source)
    with DiskImage.open(args.image) as image:
        # The usual case is checking an image's own BOOT.MAC against it; then
        # the image is opened (and, for .lzo, decompressed) exactly once.
        if member is not None and os.path.samefile(source_image, args.image):
            pram, where = PramFile.parse(image.read_file(member)), (
                f"{member} in {args.image}")
        else:
            pram, where = load_macro(args.source)
        table = pram.macro_table()
        missing = 0
        present = {e.path.upper() for e in image.walk() if not e.is_dir}
        for i, entry in enumerate(table):
            ok = entry.full_path.upper() in present
            missing += not ok
            print(f"{i:>3}  {'ok     ' if ok else 'MISSING'}  {entry.full_path}")
    print(f"{where}: {len(table) - missing}/{len(table)} present on {args.image}")
    return 1 if missing else 0


def _cmd_edit(args) -> int:
    pram, where = load_macro(args.source)
    table = pram.macro_table()
    changes: List[str] = []

    for index, value in args.rebank or []:
        table[index].bank = _bank(value)
        changes.append(f"entry {index} → bank {table[index].bank_label}")
    for index, value in args.set_mode or []:
        table[index].mode = _mode(value)
        changes.append(f"entry {index} → mode {table[index].mode_label}")
    for index, value in args.set_drive or []:
        table[index].drive = _drive(value)
        changes.append(f"entry {index} → drive {table[index].drive_label}")
    for index, value in args.move or []:
        new = table.move(index, int(value) - index)
        changes.append(f"entry {index} → position {new}")
    for index in sorted(args.delete or [], reverse=True):
        removed = table.entries.pop(index)
        changes.append(f"deleted entry {index} ({removed.full_path})")
    if args.rebank_all is not None:
        table.rebank(_bank(args.rebank_all))
        changes.append(f"all entries → bank {args.rebank_all}")

    if not changes:
        print("nothing to do (no edit options given)", file=sys.stderr)
        return 2

    pram.set_macro_table(table)
    if os.path.exists(args.output) and not args.force:
        print(f"{args.output} exists; pass --force to overwrite", file=sys.stderr)
        return 1
    with open(args.output, "wb") as fh:
        fh.write(pram.serialize())

    print(f"{where} → {args.output}")
    for change in changes:
        print(f"  {change}")
    for line in format_table(table):
        print(line)
    return 0


def _cmd_new(args) -> int:
    entries = []
    for spec in args.entry:
        path_spec, _, banks = spec.partition("@")
        bank, _, mode = banks.partition(":")
        directory, _, filename = path_spec.replace("/", "\\").rpartition("\\")
        entries.append(
            MacroEntry(
                drive=_drive(args.drive),
                bank=_bank(bank or "0"),
                mode=_mode(mode or "Fill"),
                path=(directory or "") + "\\",
                filename=filename,
            )
        )
    pram = PramFile.for_macro(MacroTable(entries))
    if os.path.exists(args.output) and not args.force:
        print(f"{args.output} exists; pass --force to overwrite", file=sys.stderr)
        return 1
    with open(args.output, "wb") as fh:
        fh.write(pram.serialize())
    print(f"wrote {args.output}")
    for line in format_table(pram.macro_table()):
        print(line)
    return 0


# --- entry point -----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="k2kmacli",
        description="Inspect and edit Kurzweil K2000 .MAC macro files.",
        epilog="A macro source is either a .MAC path or IMAGE:\\PATH.MAC inside "
               "a K2000 disk image. Images are opened read-only.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="show a macro's entries")
    p.add_argument("source", help="FILE.MAC or IMAGE:\\PATH.MAC")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("live", help="show the RUNNING K2000's macro table (read-only)")
    p.add_argument("--port", help="exact MIDI port name")
    p.add_argument("--rig", choices=("standard", "auto"), default="auto")
    p.set_defaults(func=_cmd_live)

    p = sub.add_parser(
        "diff", help="compare the live macro table against a .MAC (read-only)")
    p.add_argument("source", help="FILE.MAC or IMAGE:\\PATH.MAC")
    p.add_argument("--port", help="exact MIDI port name")
    p.add_argument("--rig", choices=("standard", "auto"), default="auto")
    p.set_defaults(func=_cmd_diff)

    p = sub.add_parser("find", help="list the .MAC files in a disk image")
    p.add_argument("image")
    p.set_defaults(func=_cmd_find)

    p = sub.add_parser("extract", help="copy a .MAC out of a disk image")
    p.add_argument("image")
    p.add_argument("member", help="path inside the image, e.g. \\BOOT.MAC")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=_cmd_extract)

    p = sub.add_parser(
        "install",
        help="WRITES: put a .MAC back into an image, over an existing file")
    p.add_argument("source", help="the .MAC to install (a host file)")
    p.add_argument("image", help="the RAW .img to write into (not .lzo)")
    p.add_argument("member", help="the existing file to overwrite, e.g. \\BOOT.MAC")
    p.add_argument("--yes", action="store_true",
                   help="skip the typed confirmation (for scripts; you own the "
                        "backup either way)")
    p.set_defaults(func=_cmd_install)

    p = sub.add_parser(
        "push", help="WRITES: replace the running K2000's macro table over MIDI")
    p.add_argument("source", help="FILE.MAC or IMAGE:\\PATH.MAC")
    p.add_argument("--port", help="exact MIDI port name")
    p.add_argument("--rig", choices=("standard", "auto"), default="auto")
    p.add_argument("--backup", help="where to save the current table first")
    p.add_argument("--yes", action="store_true",
                   help="skip the typed confirmation")
    p.set_defaults(func=_cmd_push)

    p = sub.add_parser("check", help="verify a macro's files exist on an image")
    p.add_argument("source")
    p.add_argument("--image", required=True)
    p.set_defaults(func=_cmd_check)

    p = sub.add_parser("edit", help="change entries and write a new .MAC")
    p.add_argument("source")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--force", action="store_true", help="overwrite the output")
    p.add_argument("--rebank", metavar="INDEX=BANK", type=_index_value,
                   action="append", help="set one entry's target bank (or E)")
    p.add_argument("--rebank-all", metavar="BANK",
                   help="set every entry's target bank")
    p.add_argument("--set-mode", metavar="INDEX=MODE", type=_index_value,
                   action="append", help="Append/Merge/Fill/Overwrite/OvFill")
    p.add_argument("--set-drive", metavar="INDEX=DRIVE", type=_index_value,
                   action="append", help="Floppy/SCSI n/Unspecified/Library")
    p.add_argument("--move", metavar="INDEX=POSITION", type=_index_value,
                   action="append", help="reorder an entry")
    p.add_argument("--delete", metavar="INDEX", type=int, action="append")
    p.set_defaults(func=_cmd_edit)

    p = sub.add_parser("new", help="build a .MAC from scratch")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--drive", default="SCSI 0")
    p.add_argument("entry", nargs="+", metavar="PATH@BANK[:MODE]",
                   help=r"e.g. '\--FAVS\KPOWFAV.KRZ@200:Overwrite'")
    p.set_defaults(func=_cmd_new)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except argparse.ArgumentTypeError as exc:
        # The value converters also run inside the edit/new commands, where
        # argparse is no longer in the loop to format the message.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (MacError, ImageError, ImageWriteError, FileNotFoundError,
            OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
