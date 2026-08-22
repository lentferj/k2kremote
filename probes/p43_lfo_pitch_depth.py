# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 43: LFO1->Pitch depth, audio cross-check.  (PLAYS NOTES, EDITS PROGRAM 250)

Companion to p42: the panel's Depth field on the PITCH page is a claim in
cents, byte<->cents already mapped densely (see RESOLUTION_NOTES). This
verifies that claim against the actual played pitch, the same discipline
used for CUTCAL's Coarse-vs-spectrum cross-check -- a device label is a
claim, not ground truth, until something outside the label agrees with it.

Pitch-tracked via autocorrelation over short sliding windows across the
note's sustain (LFO1 runs at 2Hz, so a 3s hold covers ~6 full cycles --
plenty to read peak-to-peak off directly rather than fit a sinusoid).

    .venv/bin/python probes/p43_lfo_pitch_depth.py
"""
import sys; sys.path.insert(0, ".")
import os
import time
import wave

import numpy as np
import rtmidi

from probes.hw import connect
from probes.p36_filter_fields import (
    rows, soft_index, SOFT, current_field, select_program, leave_editor,
)
from k2000.definitions import Button

CHANNEL = 8
CAPTURE = ("system:capture_17", "system:capture_18")
MIDI_OUT_PORT = 27
NOTE = 60
PROGRAM_ID = 250
PROGRAM_NAME = "Default Program"

PREROLL = 0.35
HOLD = 3.0
TAIL = 0.5

#: (target_ct, label) -- the practically-significant low end mpc2emu asked
#: for: byte 41 (80ct) is the old writer's fixed "0.5 amount" target, byte 4
#: (4ct) is what byte the OLD buggy code actually wrote there -- a direct
#: audible-vs-not comparison of the bug against the fix.
DEPTHS = [(4, "byte4_oldbug"), (80, "byte41_fixed")]

OUT_DIR = os.path.expanduser("~/temp/k2kremote-logs")


def stamp(title=""):
    print(f"\n[{time.strftime('%H:%M:%S')}] {title}".rstrip(), flush=True)


class Recorder:
    def __init__(self, ports=CAPTURE):
        import jack
        self.ports = ports
        self.client = jack.Client("k2klfopitch")
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


def set_depth_ct(bridge, target: int, limit: int = 3000) -> int:
    """Single click per step -- see p42 for why (the field's own native step
    curve grows non-linearly; bursts overshoot unpredictably)."""
    for _ in range(limit):
        _, val = current_field(bridge)
        cur = int(val.replace("ct", ""))
        if cur == target:
            return cur
        bridge.alpha_wheel(1 if target > cur else -1)
        time.sleep(0.15)
    raise RuntimeError(f"could not converge on Depth={target}ct, stuck at {cur}")


def autocorr_pitch(frame, rate, fmin=80, fmax=700):
    """One pitch estimate (Hz) from a single windowed frame, via
    autocorrelation restricted to the plausible range around note 60's
    fundamental (~261.5Hz) -- narrow range means no octave-jump risk."""
    frame = frame - frame.mean()
    frame = frame * np.hanning(len(frame))
    corr = np.correlate(frame, frame, mode="full")[len(frame) - 1:]
    lag_min, lag_max = int(rate / fmax), int(rate / fmin)
    if lag_max >= len(corr):
        return None
    segment = corr[lag_min:lag_max]
    if len(segment) == 0 or corr[0] <= 0:
        return None
    peak = lag_min + int(np.argmax(segment))
    if peak == 0:
        return None
    return rate / peak


def pitch_track(data, rate, t0, t1, win=0.02, hop=0.005):
    start, end = int(t0 * rate), int(t1 * rate)
    n = int(win * rate)
    h = int(hop * rate)
    times, freqs = [], []
    for i in range(start, end - n, h):
        f = autocorr_pitch(data[i:i + n], rate)
        if f is not None:
            times.append(i / rate)
            freqs.append(f)
    return np.array(times), np.array(freqs)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    bridge = connect()
    try:
        stamp(f"connected: {bridge.description}")

        select_program(bridge, PROGRAM_ID)
        time.sleep(0.4)
        reply = bridge.client.get_current_parameter_value().strip()
        assert reply == f"{PROGRAM_ID}*{PROGRAM_NAME}", f"selection mismatch: {reply!r}"
        stamp(f"program {PROGRAM_ID} confirmed")

        bridge.press_button(Button.Edit); time.sleep(0.9)
        j = soft_index(rows(bridge)[7], "PITCH")
        bridge.press_button(SOFT[j]); time.sleep(0.6)
        name, val = current_field(bridge)
        if name.strip() != "Coarse":
            stamp(f"unexpected start field {name!r} -- aborting")
            return 1
        bridge.press_button(Button.CursorRight); time.sleep(0.3)
        name, _ = current_field(bridge)
        if name.strip() != "Src1":
            stamp(f"unexpected field {name!r} after right -- aborting")
            return 1
        bridge.press_button(Button.CursorDown); time.sleep(0.3)
        name, val = current_field(bridge)
        if name.strip() != "Depth" or val.strip() != "0ct":
            stamp(f"unexpected Depth start state {name!r}={val!r} -- aborting")
            return 1
        stamp(f"cursor on Depth, currently {val}")

        out = rtmidi.MidiOut()
        out.open_port(MIDI_OUT_PORT)
        try:
            with Recorder() as rec:
                for target_ct, label in DEPTHS:
                    actual = set_depth_ct(bridge, target_ct)
                    stamp(f"Depth set to {actual}ct ({label})")

                    pre = rec.record(PREROLL)
                    out.send_message([0x90 | CHANNEL, NOTE, 100])
                    held = rec.record(HOLD)
                    out.send_message([0x80 | CHANNEL, NOTE, 0])
                    tail = rec.record(TAIL)
                    channels = [np.concatenate([p, h, t]) for p, h, t in
                               zip(pre, held, tail)]
                    path = os.path.join(OUT_DIR, f"k2k_lfopitch_{label}.wav")
                    write_wav(path, channels, rec.rate)

                    mono = channels[0].astype(np.float64) / 32767.0
                    times, freqs = pitch_track(
                        mono, rec.rate, PREROLL + 0.1, PREROLL + HOLD)
                    if len(freqs) < 10:
                        stamp(f"  {label}: pitch tracker got only {len(freqs)} "
                             f"points -- not enough to measure")
                        continue
                    fmax, fmin = float(freqs.max()), float(freqs.min())
                    pp_cents = 1200 * np.log2(fmax / fmin)
                    fcenter = float(np.median(freqs))
                    half_up = 1200 * np.log2(fmax / fcenter)
                    half_down = 1200 * np.log2(fcenter / fmin)
                    print(f"   {label}: panel claims {actual}ct  |  measured "
                          f"fmin={fmin:.2f}Hz fmax={fmax:.2f}Hz fcenter={fcenter:.2f}Hz "
                          f"peak-to-peak={pp_cents:.1f}ct  half-swing up={half_up:.1f}ct "
                          f"down={half_down:.1f}ct  -> {path}", flush=True)
                    time.sleep(0.2)
        finally:
            out.close_port(); out.delete()

        set_depth_ct(bridge, 0)
        stamp(f"Depth reverted to {current_field(bridge)}")
        ok = leave_editor(bridge)
        stamp(f"left editor cleanly: {ok}")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
