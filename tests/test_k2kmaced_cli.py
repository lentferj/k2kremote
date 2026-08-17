# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Synthetic only: no MIDI hardware is ever opened, and no real disk image is
# touched — the image fixture is built by tests/test_k2image.py's builder.

import shutil
from pathlib import Path

import pytest

from k2kmaced.macfile import PramFile
from k2kmaced.cli import main, parse_source

from test_k2image import build_image  # tests/ is on sys.path under pytest

FIXTURE = Path(__file__).parent / "fixtures" / "BOOT.MAC"


@pytest.fixture
def boot(tmp_path) -> Path:
    target = tmp_path / "BOOT.MAC"
    shutil.copy(FIXTURE, target)
    return target


@pytest.fixture
def image(tmp_path) -> Path:
    payload = FIXTURE.read_bytes()
    return build_image(
        tmp_path / "hd0.img",
        {
            "": {"BOOT.MAC": payload, "NULL.KRZ": b"\x00" * 580},
            "--FAVS": {
                "KPOWFAV.KRZ": b"\x00" * 64,
                "LFOALFAV.KRZ": b"\x00" * 64,
                "SOARCFAV.KRZ": b"\x00" * 64,
                "TCNOAFAV.KRZ": b"\x00" * 64,
            },
        },
    )


# --- source addressing -----------------------------------------------------


def test_parse_source_splits_image_members():
    assert parse_source(r"hd0.img:\BOOT.MAC") == ("hd0.img", "\\BOOT.MAC")
    assert parse_source(r"/backups/HD0.img.lzo:\A\B.MAC") == (
        "/backups/HD0.img.lzo", "\\A\\B.MAC"
    )


def test_parse_source_leaves_plain_paths_alone():
    assert parse_source("BOOT.MAC") == ("BOOT.MAC", None)
    assert parse_source("/tmp/odd:name.MAC") == ("/tmp/odd:name.MAC", None)


# --- list ------------------------------------------------------------------


def test_list_a_macro_file(boot, capsys):
    assert main(["list", str(boot)]) == 0
    out = capsys.readouterr().out
    assert "6 entries" in out and "K2000 OS v3.54" in out
    assert "0:\\NULL.KRZ" in out and "E:O:" in out
    assert "0:\\-RLNDCD2\\WAVSTFAV.KRZ" in out


def test_list_from_inside_an_image(image, capsys):
    assert main(["list", f"{image}:\\BOOT.MAC"]) == 0
    out = capsys.readouterr().out
    assert "6 entries" in out and "BOOT.MAC in" in out


def test_bare_image_path_is_refused(image, capsys):
    assert main(["list", str(image)]) == 1
    assert "address a file inside it" in capsys.readouterr().err


# --- find / extract --------------------------------------------------------


def test_find_macros_in_an_image(image, capsys):
    assert main(["find", str(image)]) == 0
    assert "\\BOOT.MAC" in capsys.readouterr().out


def test_extract_from_an_image(image, tmp_path, capsys):
    out = tmp_path / "OUT.MAC"
    assert main(["extract", str(image), "\\BOOT.MAC", "-o", str(out)]) == 0
    assert out.read_bytes() == FIXTURE.read_bytes()
    assert "wrote" in capsys.readouterr().out


def test_extract_refuses_a_non_macro(image, tmp_path, capsys):
    assert main(["extract", str(image), "\\NULL.KRZ", "-o",
                 str(tmp_path / "x.MAC")]) == 1
    assert "error:" in capsys.readouterr().err


# --- check -----------------------------------------------------------------


def test_check_an_images_own_boot_macro(image, capsys):
    # Source and target are the same image, so it is opened only once.
    assert main(["check", f"{image}:\\BOOT.MAC", "--image", str(image)]) == 1
    out = capsys.readouterr().out
    assert "ok       \\NULL.KRZ" in out and "5/6 present" in out


def test_check_reports_missing_files(boot, image, capsys):
    # The image fixture holds 5 of the 6 files the real BOOT.MAC references.
    assert main(["check", str(boot), "--image", str(image)]) == 1
    out = capsys.readouterr().out
    assert "MISSING  \\-RLNDCD2\\WAVSTFAV.KRZ" in out
    assert "5/6 present" in out


# --- edit ------------------------------------------------------------------


def test_edit_rebank_and_move(boot, tmp_path, capsys):
    out = tmp_path / "NEW.MAC"
    assert main(["edit", str(boot), "-o", str(out),
                 "--rebank", "1=700", "--move", "0=5"]) == 0
    table = PramFile.parse(out.read_bytes()).macro_table()
    assert table[0].bank == 700 and table[0].filename == "KPOWFAV.KRZ"
    assert table[5].filename == "NULL.KRZ"
    assert "entry 1 → bank 700" in capsys.readouterr().out


def test_edit_set_mode_and_drive(boot, tmp_path):
    out = tmp_path / "NEW.MAC"
    assert main(["edit", str(boot), "-o", str(out),
                 "--set-mode", "0=Fill", "--set-drive", "0=SCSI 3"]) == 0
    entry = PramFile.parse(out.read_bytes()).macro_table()[0]
    assert entry.mode_label == "Fill" and entry.drive_label == "SCSI 3"


def test_edit_delete_and_rebank_all(boot, tmp_path):
    out = tmp_path / "NEW.MAC"
    assert main(["edit", str(boot), "-o", str(out),
                 "--delete", "0", "--rebank-all", "E"]) == 0
    table = PramFile.parse(out.read_bytes()).macro_table()
    assert len(table) == 5
    assert {e.bank_label for e in table} == {"E"}


def test_edit_needs_an_operation(boot, tmp_path, capsys):
    assert main(["edit", str(boot), "-o", str(tmp_path / "NEW.MAC")]) == 2
    assert "nothing to do" in capsys.readouterr().err


def test_edit_will_not_clobber_without_force(boot, tmp_path, capsys):
    out = tmp_path / "NEW.MAC"
    out.write_bytes(b"keep me")
    assert main(["edit", str(boot), "-o", str(out), "--rebank", "0=100"]) == 1
    assert out.read_bytes() == b"keep me"
    assert "--force" in capsys.readouterr().err


def test_edit_never_writes_back_into_the_image(image, tmp_path):
    before = image.read_bytes()
    out = tmp_path / "NEW.MAC"
    assert main(["edit", f"{image}:\\BOOT.MAC", "-o", str(out),
                 "--rebank-all", "900"]) == 0
    assert image.read_bytes() == before
    assert {e.bank for e in PramFile.parse(out.read_bytes()).macro_table()} == {900}


# --- new -------------------------------------------------------------------


def test_new_builds_a_boot_macro(tmp_path, capsys):
    out = tmp_path / "BOOT.MAC"
    assert main(["new", "-o", str(out),
                 "\\NULL.KRZ@E:Overwrite",
                 "\\ANALOG\\SYNAPSE.KRZ@200:Fill"]) == 0
    table = PramFile.parse(out.read_bytes()).macro_table()
    assert [e.full_path for e in table] == [
        "\\NULL.KRZ", "\\ANALOG\\SYNAPSE.KRZ"
    ]
    assert [e.bank_label for e in table] == ["E", "200"]
    assert [e.mode_letter for e in table] == ["O", "F"]
    assert "wrote" in capsys.readouterr().out


def test_new_rejects_a_bad_bank(tmp_path, capsys):
    out = tmp_path / "x.MAC"
    assert main(["new", "-o", str(out), "\\A.KRZ@250"]) == 2
    assert "bank must be" in capsys.readouterr().err
    assert not out.exists()


def test_edit_rejects_a_bad_mode(boot, tmp_path, capsys):
    assert main(["edit", str(boot), "-o", str(tmp_path / "x.MAC"),
                 "--set-mode", "0=Sideways"]) == 2
    assert "mode must be" in capsys.readouterr().err


# --- install: the one command that writes into an image ----------------------

def test_install_aborts_without_the_typed_confirmation(image, boot, capsys,
                                                       monkeypatch):
    """The confirmation must be a deliberate act, so anything else aborts.

    A y/n prompt is answered by reflex; this one wants a word typed."""
    before = image.read_bytes()
    monkeypatch.setattr("builtins.input", lambda *_: "yes")
    assert main(["install", str(boot), str(image), "\\BOOT.MAC"]) == 1
    assert image.read_bytes() == before          # byte-for-byte untouched
    assert "aborted" in capsys.readouterr().out


def test_install_shows_the_backup_warning_before_asking(image, boot, capsys,
                                                        monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "no")
    main(["install", str(boot), str(image), "\\BOOT.MAC"])
    out = capsys.readouterr().out
    assert "YOUR responsibility" in out and "does NOT make a backup" in out
    assert "FAT untouched" in out               # the plan is shown too


def test_install_writes_when_confirmed(image, tmp_path, capsys):
    """A macro edited on the host lands inside the image and reads back."""
    edited = tmp_path / "EDITED.MAC"
    assert main(["edit", str(FIXTURE), "-o", str(edited), "--rebank", "1=700"]) == 0
    assert main(["install", str(edited), str(image), "\\BOOT.MAC", "--yes"]) == 0
    capsys.readouterr()
    assert main(["list", f"{image}:\\BOOT.MAC"]) == 0
    assert "700" in capsys.readouterr().out


def test_install_refuses_something_that_is_not_a_macro(image, tmp_path, capsys):
    """Installing a non-macro would be a bad boot with no warning at load time,
    so it is rejected before the image is opened for writing."""
    junk = tmp_path / "JUNK.MAC"
    junk.write_bytes(b"not a PRAM container at all")
    before = image.read_bytes()
    assert main(["install", str(junk), str(image), "\\BOOT.MAC", "--yes"]) == 1
    assert image.read_bytes() == before


def test_install_refuses_a_compressed_image(boot, tmp_path, capsys):
    fake = tmp_path / "hd0.img.lzo"
    fake.write_bytes(b"nope")
    assert main(["install", str(boot), str(fake), "\\BOOT.MAC", "--yes"]) == 1
    assert "lzop-compressed" in capsys.readouterr().err


def test_parse_source_does_not_split_a_windows_drive_letter():
    r"""A bare Windows path is a path, not image `C` plus member `\Users\...`.

    parse_source's docstring claimed drive letters were left alone while it split
    them, so every Windows job in CI failed with `FileNotFoundError: 'C'` the
    first time the macro tests ran there. It is a pure string function, so this
    catches it on any platform — which is where it should have been caught.
    """
    assert parse_source(r"C:\Users\me\hd0.img") == (r"C:\Users\me\hd0.img", None)
    assert parse_source(r"D:\hd0.img") == (r"D:\hd0.img", None)
    # ...while a member on a Windows path still splits, at the right colon.
    assert parse_source(r"C:\Users\me\hd0.img:\BOOT.MAC") == (
        r"C:\Users\me\hd0.img", r"\BOOT.MAC")
