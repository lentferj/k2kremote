# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
#
# Tables read out of the v3.87J OS ROM. The exhaustive test needs the image
# at ~/temp/k2k_fw/k2000_v387j.bin and skips without it; no hardware.

def test_cents_ratio_reproduces_the_rom_table_byte_for_byte():
    """All 9601 entries, against the image itself -- not a spot check.

    The law alone is wrong on seven of them, which is why the exceptions
    exist; a spot check would have missed six of the seven, since they sit
    at arbitrary cent offsets (-80, -759, -807, -910, -1052, -1547).
    """
    import pathlib
    from k2kremote.k2kromtables import cents_ratio

    image = pathlib.Path.home() / "temp" / "k2k_fw" / "k2000_v387j.bin"
    if not image.exists():
        import pytest
        pytest.skip("ROM image not present")

    rom = image.read_bytes()
    base = 0x1F9602 - 0x100000
    for i in range(0, -9601, -1):
        off = base + 2 * i
        assert cents_ratio(i) == (rom[off] << 8) | rom[off + 1], f"cent {i}"


def test_cents_ratio_refuses_an_index_outside_the_table():
    import pytest
    from k2kremote.k2kromtables import cents_ratio

    with pytest.raises(ValueError):
        cents_ratio(1)
    with pytest.raises(ValueError):
        cents_ratio(-9601)


def test_roland_rate_table_matches_the_jump_table_arms():
    from k2kremote.k2kromtables import ROLAND_RATE_HZ, ROLAND_RATE_DEFAULT_HZ

    assert ROLAND_RATE_HZ == (48000, 44100, 24000, 22050, 30000, 15000)
    assert ROLAND_RATE_DEFAULT_HZ == 44100
    # the three octave pairs that made the pitch method unable to decide
    assert ROLAND_RATE_HZ[0] == 2 * ROLAND_RATE_HZ[2]
    assert ROLAND_RATE_HZ[1] == 2 * ROLAND_RATE_HZ[3]
    assert ROLAND_RATE_HZ[4] == 2 * ROLAND_RATE_HZ[5]
