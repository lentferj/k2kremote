# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
# Values extracted from the Kurzweil K2000 v3.87J OS ROM, which is
# Kurzweil/Young Chang's copyrighted firmware and is NOT redistributed here:
# these are the numbers the instrument displays, read out of the tables that
# produce them, the same facts a panel sweep produces one row at a time.
"""K2000 display tables, read out of the v3.87J OS ROM.

Every table in this file was found by matching against values this project
had already measured off the panel, and then spot-checked back against the
panel byte by byte -- the ROM is the source, the instrument is the check.
The provenance for each is in `docs/RESOLUTION_NOTES.md` §70.

Addresses are ROM addresses (the image maps at 0x100000), kept so anyone can
go back to the bytes.
"""

#: ROM 0x1FC204, 128 entries. `Coarse:` in whole Hz for a frequency
#: block, indexed by **signed byte + 48**, so the byte runs -48..79 --
#: which is why the field clamps exactly there. RESOLUTION_NOTES §69/§70.
FILTER_COARSE_HZ = (
    16, 17, 18, 19, 21, 22, 23, 24, 26, 28, 29, 31,
    33, 35, 37, 39, 41, 44, 46, 49, 52, 55, 58, 62,
    65, 69, 73, 78, 82, 87, 92, 98, 104, 110, 117, 123,
    131, 139, 147, 156, 165, 175, 185, 196, 208, 220, 233, 247,
    262, 277, 294, 311, 330, 349, 370, 392, 415, 440, 466, 494,
    523, 554, 587, 622, 659, 698, 740, 784, 831, 880, 932, 988,
    1047, 1109, 1175, 1245, 1319, 1397, 1480, 1568, 1661, 1760, 1865, 1976,
    2093, 2217, 2349, 2489, 2637, 2794, 2960, 3136, 3322, 3520, 3729, 3951,
    4186, 4435, 4699, 4978, 5274, 5588, 5920, 6272, 6645, 7040, 7459, 7902,
    8372, 8870, 9397, 9956, 10548, 11175, 11840, 12544, 13290, 14080, 14917, 15804,
    16744, 17740, 18795, 19912, 21096, 22351, 23680, 25088,
)

#: ROM 0x1F9604, 256 entries, indexed by the RAW byte (0..127 then
#: 128..255 = -128..-1). Cents, symmetric, +-10800. The negative half
#: was never measured before §70; eight bytes spot-checked on hardware.
ENV2_FILFREQ_CT = (
    0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22,
    24, 27, 30, 35, 40, 45, 50, 55, 60, 70, 80, 90,
    100, 120, 150, 200, 250, 300, 350, 400, 450, 500, 600, 700,
    800, 900, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900,
    2000, 2100, 2200, 2300, 2400, 2500, 2600, 2700, 2800, 2900, 3000, 3100,
    3200, 3300, 3400, 3500, 3600, 3700, 3800, 3900, 4000, 4100, 4200, 4300,
    4400, 4500, 4600, 4700, 4800, 4900, 5000, 5100, 5200, 5300, 5400, 5500,
    5600, 5700, 5800, 5900, 6000, 6100, 6200, 6300, 6400, 6500, 6600, 6700,
    6800, 6900, 7000, 7100, 7200, 7300, 7400, 7500, 7600, 7700, 7800, 7900,
    8000, 8100, 8200, 8300, 8400, 8500, 8600, 8700, 8800, 8900, 9000, 9100,
    9200, 9300, 9400, 9500, 9600, 10000, 10400, 10800, -10800, -10800, -10400, -10000,
    -9600, -9500, -9400, -9300, -9200, -9100, -9000, -8900, -8800, -8700, -8600, -8500,
    -8400, -8300, -8200, -8100, -8000, -7900, -7800, -7700, -7600, -7500, -7400, -7300,
    -7200, -7100, -7000, -6900, -6800, -6700, -6600, -6500, -6400, -6300, -6200, -6100,
    -6000, -5900, -5800, -5700, -5600, -5500, -5400, -5300, -5200, -5100, -5000, -4900,
    -4800, -4700, -4600, -4500, -4400, -4300, -4200, -4100, -4000, -3900, -3800, -3700,
    -3600, -3500, -3400, -3300, -3200, -3100, -3000, -2900, -2800, -2700, -2600, -2500,
    -2400, -2300, -2200, -2100, -2000, -1900, -1800, -1700, -1600, -1500, -1400, -1300,
    -1200, -1100, -1000, -900, -800, -700, -600, -500, -450, -400, -350, -300,
    -250, -200, -150, -120, -100, -90, -80, -70, -60, -55, -50, -45,
    -40, -35, -30, -27, -24, -22, -20, -18, -16, -14, -12, -10,
    -8, -6, -4, -2,
)

#: ROM 0x1FA204, same indexing, +-7200 cents.
LFO_PITCH_CT = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
    12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 24, 26,
    28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50,
    55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 110, 120,
    130, 140, 150, 160, 170, 180, 190, 200, 220, 240, 260, 280,
    300, 320, 340, 360, 380, 400, 450, 500, 550, 600, 650, 700,
    750, 800, 850, 900, 950, 1000, 1100, 1200, 1300, 1400, 1500, 1600,
    1700, 1800, 1900, 2000, 2100, 2200, 2300, 2400, 2500, 2600, 2700, 2800,
    2900, 3000, 3100, 3200, 3300, 3400, 3500, 3600, 3700, 3800, 3900, 4000,
    4100, 4200, 4300, 4400, 4500, 4600, 4700, 4800, 4900, 5000, 5300, 5500,
    6000, 6500, 6700, 7200, 7200, 7200, 7200, 7200, -7200, -7200, -7200, -7200,
    -7200, -7200, -6700, -6500, -6000, -5500, -5300, -5000, -4900, -4800, -4700, -4600,
    -4500, -4400, -4300, -4200, -4100, -4000, -3900, -3800, -3700, -3600, -3500, -3400,
    -3300, -3200, -3100, -3000, -2900, -2800, -2700, -2600, -2500, -2400, -2300, -2200,
    -2100, -2000, -1900, -1800, -1700, -1600, -1500, -1400, -1300, -1200, -1100, -1000,
    -950, -900, -850, -800, -750, -700, -650, -600, -550, -500, -450, -400,
    -380, -360, -340, -320, -300, -280, -260, -240, -220, -200, -190, -180,
    -170, -160, -150, -140, -130, -120, -110, -100, -95, -90, -85, -80,
    -75, -70, -65, -60, -55, -50, -48, -46, -44, -42, -40, -38,
    -36, -34, -32, -30, -28, -26, -24, -22, -20, -19, -18, -17,
    -16, -15, -14, -13, -12, -11, -10, -9, -8, -7, -6, -5,
    -4, -3, -2, -1,
)

#: ROM 0x1FB404, 256 entries indexed by the raw UNSIGNED byte,
#: hundredths of Hz. 0.00 .. 25.00 Hz, saturating from byte 186.
#: The wheel stops at byte 184 (24.00 Hz); SysEx does not.
LFO_RATE_CHZ = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
    12, 13, 14, 15, 16, 17, 18, 19, 20, 25, 30, 35,
    40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95,
    100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210,
    220, 230, 240, 250, 260, 270, 280, 290, 300, 310, 320, 330,
    340, 350, 360, 370, 380, 390, 400, 410, 420, 430, 440, 450,
    460, 470, 480, 490, 500, 510, 520, 530, 540, 550, 560, 570,
    580, 590, 600, 610, 620, 630, 640, 650, 660, 670, 680, 690,
    700, 710, 720, 730, 740, 750, 760, 770, 780, 790, 800, 810,
    820, 830, 840, 850, 860, 870, 880, 890, 900, 910, 920, 930,
    940, 950, 960, 970, 980, 990, 1000, 1020, 1040, 1060, 1080, 1100,
    1120, 1140, 1160, 1180, 1200, 1220, 1240, 1260, 1280, 1300, 1320, 1340,
    1360, 1380, 1400, 1420, 1440, 1460, 1480, 1500, 1520, 1540, 1560, 1580,
    1600, 1620, 1640, 1660, 1680, 1700, 1720, 1740, 1760, 1780, 1800, 1820,
    1840, 1860, 1880, 1900, 1920, 1940, 1960, 1980, 2000, 2050, 2100, 2150,
    2200, 2250, 2300, 2350, 2400, 2450, 2500, 2500, 2500, 2500, 2500, 2500,
    2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500,
    2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500,
    2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500,
    2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500,
    2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500,
    2500, 2500, 2500, 2500,
)



# --------------------------------------------------------------------------
# The sample-import tables, read out of the same image (2026-09-21/22).
#
# Unlike the three above, these were not found by matching panel readings --
# they came from tracing the Roland and AKAI import paths, and were then
# checked against objects the K2000 itself wrote (docs/IMPORT_CONVERSION.md).
# --------------------------------------------------------------------------

#: ROM 0x169D90: `moveb %a1@(44),%d0; andiw #15,%d0; cmpiw #5; bhis` then a
#: six-entry PC-relative jump table at 0x169DA8. Index is the low nibble of
#: the Roland sample record's byte +44; 6..15 fall through to the default.
#:
#: Confirmed on device output: an import at code 1 wrote samplePeriod 22675,
#: which is TRUNC(1e9/44100) and not the rounded 22676.
ROLAND_RATE_HZ = (48000, 44100, 24000, 22050, 30000, 15000)

#: What codes 6..15 get (the `bhis` default arm at 0x169DDC).
ROLAND_RATE_DEFAULT_HZ = 44100

#: ROM 0x1F4B02..0x1F9602: 9601 BE u16, addressed as `0x1F9602 + 2*i` for
#: i = 0 down to -9600, i.e. **one entry per cent**, searched downwards for
#: the first entry <= (rate << 16) / 96000.
#:
#: The entries are `round(65536 * 2**(i/1200))` -- exactly, on 9594 of 9601.
#: The seven exceptions are listed below rather than smoothed over, because
#: they say something about the firmware: six of them sit within 0.0021 of a
#: rounding boundary and the ROM rounds them UP from *below* .5, so its own
#: table was computed at lower precision than a double. The seventh is the
#: u16 ceiling.
CENTS_RATIO_EXCEPTIONS = {
    0: 65535,       # 65536 does not fit a u16
    -80: 62577,     # exact 62576.499354 -> ROM rounds up
    -759: 42275,    # exact 42274.497923
    -807: 41119,    # exact 41118.499555
    -910: 38744,    # exact 38743.499933
    -1052: 35693,   # exact 35692.499964
    -1547: 26817,   # exact 26816.500000
}


def cents_ratio(i: int) -> int:
    """The ROM's entry for `i` cents below unity, reproduced byte-exactly.

    `i` runs 0 down to -9600. Returns the BE u16 the ROM holds at
    `0x1F9602 + 2*i` -- the law where it holds, the measured value where it
    does not.
    """
    if not -9600 <= i <= 0:
        raise ValueError(f"cents index {i} outside the table's 0..-9600")
    if i in CENTS_RATIO_EXCEPTIONS:
        return CENTS_RATIO_EXCEPTIONS[i]
    return round(65536 * 2 ** (i / 1200))
