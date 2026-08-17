# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 35: how far does velocity move the filter corner?  (PLAYS NOTES, WRITES A PROGRAM FIELD)

Measures the K2000 side of a defect found in the sibling mpc2emu's KRZ->AKAI
converter: the K2000 specifies velocity->filter as a **range** (MinDpt 0,
MaxDpt +N cents) which only ever *opens* the filter, while the AKAI's MODVFILT1
is bipolar about a velocity pivot. Converting one to the other by matching the
value at velocity zero puts the AKAI's corner below a floor the K2000 never
crosses, and quiet notes go silent. 47 routings in the corpus, all unipolar.

What this yields: **octaves of corner movement per 1000 cents of MaxDpt**, and
whether the K2000 interpolates **linearly in velocity** between MinDpt and
MaxDpt — which the converter assumes and nobody has checked.

REQUIRES a program already set up (see --check, which verifies and refuses):

    playback mode   Noise      (KEYMAP page; replaces the sample outright.
                                NOT the NOISE+ DSP block, whose level is tied to
                                the sample it is added to and which *adds* rather
                                than replaces — useless as an excitation.)
    filter          4POLE LOPASS W/ SEP, a two-stage function
    FILFRQ          mid-range, headroom both ways
    resonance       stated as a BYTE (a dB on one page is not a dB on another
                    here: amplitude reads 1:1, resonance at half a dB per unit)
    Src2            AttVel,  MinDpt 0
    AMP Adjust      about -9 dB, i.e. ~0.35 of full scale, so the resonance peak
                    has somewhere to go before it clips

The sweep steps MaxDpt and plays each velocity, recording audio per cell:

    MaxDpt   0, 2700, 5400, 8100, 10800 cents  ->  bytes 0, 55, 82, 109, 127
    velocity 20, 40, 64, 90, 110, 127

The byte values come from mpc2emu's `_k2_depth_cents`, validated against the
machine's own display for every depth in a 581-row corpus. They are NOT
`100 x (byte - 28)`: that is the linear middle of a curve which is compressed at
the bottom (byte 28 is 250 ct, not 0) and steps 400 ct at 125..127, topping out
at byte 127 = 10800 ct. Asking for "byte 136" is asking for a byte that cannot
be sent.

**The MaxDpt=0 row is a control and is repeated at the END of the run**, so a rig
that died halfway is distinguishable from a genuinely flat result. Without it, a
flat result, a broken capture chain and a dead instrument look identical.

Audio goes to system:capture_17/18 (measured 2026-08-17: the K2000 sits there
about 60 dB above an idle pair). Do **not** capture 1/2 on this rig — that is a
stereo sum of the computer's own output, so it would record the monitoring path,
including this probe's own excitation, and look like a clean measurement.

    .venv/bin/python probes/p35_filter_velocity.py --check
    .venv/bin/python probes/p35_filter_velocity.py --run -o ~/temp/filtersweep
"""
import sys; sys.path.insert(0, ".")
import argparse
import json
import os
import threading
import time
import wave

import numpy as np

from probes.hw import connect

CHANNEL = 8                     # panel showed Channel:9
NOTE = 60
CAPTURE = ("system:capture_17", "system:capture_18")
IDLE_REFERENCE = ("system:capture_19", "system:capture_20")

#: MaxDpt in cents -> stored byte, from mpc2emu's validated depth curve.
MAXDPT = [(0, 0), (2700, 55), (5400, 82), (8100, 109), (10800, 127)]
VELOCITIES = [20, 40, 64, 90, 110, 127]

HOLD = 1.2                      # note length, seconds
TAIL = 0.4                      # recording tail after note-off
SETTLE = 0.35                   # after a parameter change, before the note


def stamp(title=""):
    print(f"\n[{time.strftime('%H:%M:%S')}] {title}".rstrip(), flush=True)


class Recorder:
    """Records CAPTURE into memory for the duration of a `with` block."""

    def __init__(self, ports=CAPTURE):
        import jack
        self.jack = jack
        self.ports = ports
        self.client = jack.Client("k2kfilter")
        self.ins = [self.client.inports.register(f"in{i}") for i in range(2)]
        self.rate = self.client.samplerate
        self._buf = None

        @self.client.set_process_callback
        def _process(frames):
            if self._buf is not None:
                for i, port in enumerate(self.ins):
                    self._buf[i].append(port.get_array().copy())

    def __enter__(self):
        self.client.activate()
        for port, src in zip(self.ins, self.ports):
            self.client.connect(src, port)
        return self

    def __exit__(self, *exc):
        self.client.deactivate()
        self.client.close()

    def record(self, seconds):
        self._buf = [[], []]
        time.sleep(seconds)
        chunks, self._buf = self._buf, None
        return [np.concatenate(c) if c else np.zeros(1, dtype=np.float32)
                for c in chunks]


def write_wav(path, channels, rate):
    data = np.stack([np.clip(c, -1.0, 1.0) for c in channels], axis=1)
    pcm = (data * 32767.0).astype("<i2")
    with wave.open(path, "wb") as fh:
        fh.setnchannels(2)
        fh.setsampwidth(2)
        fh.setframerate(int(rate))
        fh.writeframes(pcm.tobytes())


def read_panel(bridge):
    """The panel as rows, for asserting what the instrument actually shows."""
    return bridge.get_screen_text().split("\n")


def check(bridge) -> bool:
    """Report what the panel shows, and refuse if it is not a filter page.

    Deliberately does not try to *set up* the program. Building it means walking
    the editor's six soft pages, and this project has already lost a night to
    reading layer 1 of N and to a soft-key cycle that was one short. The setup is
    quicker and safer at the panel; this only checks it.
    """
    rows = read_panel(bridge)
    print("panel:")
    for r in rows:
        print(f"  |{r.rstrip()}|")
    header, soft = rows[0], rows[7]
    ok = "Edit" in header or "FILT" in "".join(rows).upper()
    if not ok:
        print("\nThis does not look like a filter page in the program editor.")
        print("Set up the program at the panel first (see the module docstring),")
        print("leave it on the filter's control-input page, and re-run --check.")
    return ok


def cursor_to_maxdpt(bridge):
    """Put the cursor on MaxDpt from wherever it is, and prove it moved.

    The parameter cursor is in the graphics overlay, not ALLTEXT, so it cannot be
    read as text. Rather than count presses -- twice today I assumed a cursor
    position, wheeled 48 clicks into the wrong field and reported the flat result
    as data -- this drives it to a known corner and then *verifies* by nudging the
    value and watching MaxDpt's text change.
    """
    from k2000.definitions import Button
    row = lambda: bridge.get_screen_text().split("\n")[6]
    for _ in range(8):                      # bottom of the right-hand column
        bridge.press_button(Button.CursorDown); time.sleep(0.3)
    for _ in range(4):
        bridge.press_button(Button.CursorRight); time.sleep(0.3)
    before = row()
    bridge.alpha_wheel(1); time.sleep(0.5)
    moved = row() != before
    bridge.alpha_wheel(-1); time.sleep(0.5)
    return moved


def set_maxdpt(bridge, cents):
    """Type MaxDpt in cents and return what the panel then shows."""
    from k2000.definitions import Button
    digits = {n: getattr(Button, f"Number{n}") for n in range(10)}
    for ch in str(cents):
        bridge.press_button(digits[int(ch)]); time.sleep(0.28)
    bridge.press_button(Button.Enter); time.sleep(0.55)
    return bridge.get_screen_text().split("\n")[6].split("MaxDpt:")[-1].strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="read the panel only")
    ap.add_argument("--run", action="store_true", help="perform the sweep")
    ap.add_argument("-o", "--output", default="filtersweep")
    ap.add_argument("--depths", default="0,1800,3600,5400,7200",
                    help="MaxDpt steps in cents; the first is repeated at the end "
                         "as a closing control")
    args = ap.parse_args()
    if not (args.check or args.run):
        ap.error("pass --check or --run")

    import rtmidi
    bridge = connect()
    try:
        print(f"connected: {bridge.description}")
        while bridge.client.midi_in.get_message() is not None:
            pass
        rows = bridge.get_screen_text().split("\n")
        if "F1 FRQ" not in rows[0]:
            print("panel is not on the filter's F1 FRQ page; it reads:")
            print(f"  {rows[0].rstrip()}")
            return 1
        if args.check:
            for r in rows:
                print(f"  |{r.rstrip()}|")
            return 0

        if not cursor_to_maxdpt(bridge):
            print("could not confirm the cursor is on MaxDpt -- refusing to sweep, "
                  "because a sweep that writes to the wrong field still produces "
                  "a full set of plausible numbers")
            return 1
        print("cursor confirmed on MaxDpt")

        os.makedirs(args.output, exist_ok=True)
        depths = [int(d) for d in args.depths.split(",")]
        plan = depths + [depths[0]]          # closing control repeats the first
        out = rtmidi.MidiOut()
        out.open_port(27)
        index = open(os.path.join(args.output, "index.jsonl"), "w")
        try:
            with Recorder() as rec:
                for pass_no, cents in enumerate(plan):
                    shown = set_maxdpt(bridge, cents)
                    panel = bridge.get_screen_text().split("\n")
                    stamp(f"MaxDpt requested {cents}ct -> panel shows {shown}")
                    for vel in VELOCITIES:
                        t_on = time.monotonic()
                        out.send_message([0x90 | CHANNEL, NOTE, vel])
                        audio = rec.record(HOLD)
                        out.send_message([0x80 | CHANNEL, NOTE, 0])
                        tail = rec.record(TAIL)
                        chans = [np.concatenate([a, t]) for a, t in zip(audio, tail)]
                        name = f"d{cents:05d}_v{vel:03d}_p{pass_no}.wav"
                        write_wav(os.path.join(args.output, name), chans, rec.rate)
                        peak = float(max(np.max(np.abs(c)) for c in chans))
                        index.write(json.dumps({
                            "program": 199, "layer": "1/1",
                            "playback_mode": "Noise",
                            "block": "4POLE LOPASS W/SEP",
                            "pass": pass_no,
                            "closing_control": pass_no == len(plan) - 1,
                            "req": {"maxdpt_ct": cents, "res_db": 12.0,
                                    "amp_db": -9, "amp_veltrk_db": 0,
                                    "coarse": "C 4 262Hz", "mindpt_ct": 0,
                                    "src2": "AttVel"},
                            "read": {"maxdpt": shown,
                                     "coarse": panel[1].split("Src1")[0].strip(),
                                     "src2": panel[3].split("Src2")[-1].strip(),
                                     "mindpt": panel[5].split("MinDpt:")[-1].strip()},
                            "velocity": vel, "note": NOTE,
                            "t_note_on": t_on, "peak": peak,
                            "wav": name, "samplerate": rec.rate,
                        }) + "\n")
                        index.flush()
                        print(f"   vel {vel:>3}  peak {peak:.4f}  -> {name}", flush=True)
                        time.sleep(0.25)
        finally:
            index.close()
            out.close_port(); out.delete()
        stamp(f"done; {len(plan) * len(VELOCITIES)} cells in {args.output}")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
