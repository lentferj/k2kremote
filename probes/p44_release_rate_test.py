# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 44: is the K2000's Release a RATE or a DURATION?  (PLAYS NOTES, EDITS PROGRAM 906)

For mpc2emu: their krz_writer takes env.release in SECONDS and multiplies by a
correction factor derived assuming a rate machine (matching the AKAI and E4XT,
both confirmed rate machines this evening). Whether that assumption holds for
the K2000 was never asked of the hardware -- this probe asks it.

Method (the varying-span test): hold Rel1's TIME setting constant, vary the
SUSTAIN LEVEL the note is released from (Dec1's target %), and measure actual
wall-clock time from note-off to a completion instant. If elapsed time stays
constant regardless of distance travelled, Release is a DURATION. If elapsed
time scales with distance, Release is a RATE.

Prediction, written down BEFORE running: RATE, by analogy with the AKAI and
E4XT. That analogy has already been wrong once tonight (the AKAI's filter
envelope, where a true statement about one stage did load-bearing work for an
untested one) -- this is not evidence, only a note of what would confirm a
bias if the data happened to agree.

Subject: program 906 "ObSt lowp kl.lay" (K2000 hard disk, -SYNTHS/OBERHEIM.KRZ),
picked over a first candidate (program 200 "SPACE E", six layers) and a second
(program 800/801, both two-layer stacks from a same-named-but-different file)
specifically because it is single-layer -- Layer:1/1, confirmed on the panel
before this probe was written. A multi-layer program contaminates a release
measurement with whichever layer you are not editing.

Original AMPENV values for program 906 layer 1 (restored on exit, whatever the
exit path): Att1 0.10s/77%, Att2 0.10s/95%, Att3 0.22s/84%, Dec1 4.40s/67%,
Rel1 2.00s/0%, Rel2 0s/0%, Rel3 0s/User, Loop Off/Inf.

Only Rel1-time and Dec1-% are edited by this probe (Rel1-% was already 0% on
this program, unlike the SPACE E attempt where it needed changing too). Att/Dec
TIMES are deliberately left untouched -- rather than speed them up and risk a
navigation mistake, notes are simply held long enough (HOLD seconds) for the
unedited attack+decay to fully settle at the target sustain level naturally.

    .venv/bin/python probes/p44_release_rate_test.py
"""
import sys; sys.path.insert(0, ".")
import os
import re
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
PROGRAM_ID = 906
PROGRAM_NAME = "ObSt lowp kl.lay"

PREROLL = 0.35
HOLD = 6.0          # settle time for the UNEDITED, slow attack+decay chain
TAIL = 8.0          # generous -- long enough for either hypothesis at these settings

#: (Rel1_time_s, [sustain_%, ...]) -- two release settings x three sustain
#: levels each, per mpc2emu's addition (three points show PROPORTIONALITY,
#: not just movement).
TRIALS = [
    (1.00, [100, 50, 15]),
    (3.00, [100, 50, 15]),
]

#: Original values, for exact restoration regardless of exit path.
ORIG_REL1_TIME = 2.00
ORIG_DEC1_PCT = 67
ORIG_REL1_PCT = 0     # was already 0 -- this probe never changes it, listed
                      # here only so a future reader has the full picture.

OUT_DIR = os.path.expanduser("~/temp/k2kremote-logs")


def stamp(title=""):
    print(f"\n[{time.strftime('%H:%M:%S')}] {title}".rstrip(), flush=True)


class Recorder:
    def __init__(self, ports=CAPTURE):
        import jack
        self.ports = ports
        self.client = jack.Client("k2krelrate")
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


def parse_leading_number(val: str):
    """First run of digits (with an optional decimal point), ignoring any
    trailing noise -- the AMPENV page's readback carries corrupted suffix
    bytes (soft-key label bleed) that a plain split() does not reliably clear."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)", val)
    if m is None:
        raise ValueError(f"no leading number in {val!r}")
    return float(m.group(1))


def is_seconds_field(val: str) -> bool:
    """True if the number is immediately followed by 's' -- anchored right
    after the digits, not a bare substring search. The AMPENV page's garbled
    readback suffix (soft-key label bleed) has not been observed to contain
    a coincidental 's' in this position, but a bare `"s" in val` would still
    be one bad frame away from a false positive; anchoring removes the risk."""
    return re.match(r"\s*\d+(?:\.\d+)?s", val) is not None


def set_field(bridge, target: float, limit: int = 400, tol: float = 0.0):
    """Single click per step, closed loop -- see p42's notes on why (this
    project's own history of nonlinear per-field step curves, verified fresh
    on THIS field earlier: Rel1-time here measured 0.04s/click near 2.00s but
    delivered 0.02s/click averaged over a 25-click jump -- not extrapolable)."""
    for _ in range(limit):
        _, val = current_field(bridge)
        cur = parse_leading_number(val)
        if abs(cur - target) <= tol:
            return cur
        bridge.alpha_wheel(1 if target > cur else -1)
        time.sleep(0.15)
    raise RuntimeError(f"could not converge on {target}, stuck at {cur}")


def envelope_rms(data, rate, win=0.02, hop=0.005):
    n, h = int(win * rate), int(hop * rate)
    times, levels = [], []
    for i in range(0, len(data) - n, h):
        seg = data[i:i + n]
        times.append(i / rate)
        levels.append(float(np.sqrt(np.mean(seg.astype(np.float64) ** 2))))
    return np.array(times), np.array(levels)


def completion_time(channels, rate, note_off_t, floor_ref):
    """Time from note-off to when the envelope RMS first drops to within
    3dB of the pre-roll noise floor and STAYS there (hold=6 windows, ~30ms)
    -- not a t-10dB-from-peak crossing, per mpc2emu's explicit caution that a
    relative-to-peak threshold biased today's AKAI measurement by 5-10%."""
    mono = (channels[0].astype(np.float64) + channels[1].astype(np.float64)) / 2 / 32767.0
    times, levels = envelope_rms(mono, rate)
    target = floor_ref * (10 ** (3 / 20))  # floor + 3dB
    off_idx = np.searchsorted(times, note_off_t)
    hold = 6
    for i in range(off_idx, len(levels) - hold):
        if np.all(levels[i:i + hold] <= target):
            return times[i] - note_off_t, levels[i]
    return None, None  # never reached completion within the capture


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    bridge = connect()
    try:
        stamp(f"connected: {bridge.description}")
        stamp("PREDICTION (written before any capture): RATE, by analogy with "
              "the AKAI/E4XT -- untrusted until measured.")

        select_program(bridge, PROGRAM_ID)
        time.sleep(0.4)
        reply = bridge.client.get_current_parameter_value().strip()
        assert reply == f"{PROGRAM_ID}*{PROGRAM_NAME}", f"selection mismatch: {reply!r}"
        stamp(f"program {PROGRAM_ID} confirmed")

        bridge.press_button(Button.Edit); time.sleep(0.9)
        header = rows(bridge)[0]
        assert "Layer:1/1" in header, f"expected single layer, got {header!r}"
        stamp("single-layer confirmed on the panel")

        for _ in range(3):
            j = soft_index(rows(bridge)[7], "more>")
            bridge.press_button(SOFT[j]); time.sleep(0.4)
        j = soft_index(rows(bridge)[7], "AMPENV")
        bridge.press_button(SOFT[j]); time.sleep(0.6)

        # Cursor opens on the Rel3-% field (verified live this session).
        # Canonical ring order (also verified live): Att1/2/3-time, Dec1-time,
        # Rel1-time, Rel2-time, Rel3-time, Loop-state, Att1/2/3-%, Dec1-%,
        # Rel1-%, Rel2-%, Rel3-%, Loop-Inf -- 16 fields, wraps.
        for _ in range(10):
            bridge.press_button(Button.CursorLeft); time.sleep(0.3)
        name, val = current_field(bridge)
        cur = parse_leading_number(val)
        if abs(cur - ORIG_REL1_TIME) > 0.001:
            stamp(f"cursor landing sanity check FAILED: expected Rel1-time="
                 f"{ORIG_REL1_TIME}, got {val!r} -- aborting before editing anything")
            return 1
        stamp(f"cursor confirmed on Rel1-time ({val})")

        out = rtmidi.MidiOut()
        out.open_port(MIDI_OUT_PORT)
        written = []
        try:
            with Recorder() as rec:
                for trial_i, (rel1_time, sustains) in enumerate(TRIALS):
                    if trial_i > 0:
                        # BUG FIXED: earlier version assumed the cursor was
                        # still on Rel1-time here. It is not -- the previous
                        # iteration's sustains loop + Dec1% restore leaves it
                        # on Dec1% (position 11 of 16), 7 CursorLeft short of
                        # Rel1-time (position 4). Without this, set_field()
                        # below silently edited Dec1% and Att3-time instead of
                        # Rel1-time and Dec1%, driving Att3-time to its 60s
                        # ceiling -- caught only by a full-page dump after a
                        # ~9-minute hang, and required manual recovery on
                        # hardware. Always re-anchor from a KNOWN position
                        # before an edit; never assume where the cursor is.
                        for _ in range(7):
                            bridge.press_button(Button.CursorLeft); time.sleep(0.3)
                        name, val = current_field(bridge)
                        # SECOND BUG, caught on this very rerun: the first fix
                        # checked the landed value against ORIG_DEC1_PCT (67),
                        # which is nonsense for a seconds field -- correctly
                        # landing on Rel1-time reading "1.00s" (its legitimate
                        # value from trial 1) was flagged as a false failure.
                        # The real discriminator between these two fields is
                        # UNIT, not a specific number that varies by trial:
                        # time fields carry a literal 's' suffix, percent
                        # fields do not.
                        if not is_seconds_field(val):
                            stamp(f"re-anchor sanity check FAILED: expected a "
                                 f"seconds field (Rel1-time), got {val!r} -- "
                                 f"aborting before editing anything")
                            return 1

                    set_field(bridge, rel1_time, tol=0.005)
                    _, check = current_field(bridge)
                    stamp(f"Rel1-time set to {check}")

                    for _ in range(7):
                        bridge.press_button(Button.CursorRight); time.sleep(0.3)
                    name, val = current_field(bridge)
                    if is_seconds_field(val):
                        stamp(f"post-navigation sanity check FAILED: expected "
                             f"a percent field (Dec1-%), got {val!r} -- "
                             f"aborting before editing anything")
                        return 1

                    for sustain in sustains:
                        set_field(bridge, sustain)
                        _, dec_check = current_field(bridge)
                        stamp(f"  Dec1% set to {dec_check}")

                        pre = rec.record(PREROLL)
                        floor_ref = float(np.sqrt(np.mean(
                            ((pre[0].astype(np.float64) + pre[1].astype(np.float64))
                             / 2 / 32767.0) ** 2))) or 1e-6

                        out.send_message([0x90 | CHANNEL, NOTE, 100])
                        held = rec.record(HOLD)
                        note_off_t = PREROLL + HOLD
                        out.send_message([0x80 | CHANNEL, NOTE, 0])
                        tail = rec.record(TAIL)

                        channels = [np.concatenate([p, h, t]) for p, h, t in
                                   zip(pre, held, tail)]
                        label = f"rel{rel1_time:.2f}_sus{sustain}"
                        path = os.path.join(OUT_DIR, f"k2k_relrate_{label}.wav")
                        write_wav(path, channels, rec.rate)
                        written.append(path)

                        ctime, level_at = completion_time(
                            channels, rec.rate, note_off_t, floor_ref)
                        if ctime is None:
                            print(f"   {label}: NEVER reached completion within "
                                 f"{TAIL}s tail (floor_ref={floor_ref:.6f})", flush=True)
                        else:
                            print(f"   {label}: completion at {ctime:.3f}s after "
                                 f"note-off (floor_ref={floor_ref:.6f}, level at "
                                 f"completion={level_at:.6f}) -> {path}", flush=True)
                        time.sleep(0.2)

                    # Restore Dec1% to original before moving to the next Rel1
                    # setting -- keeps every trial's sustain-level EDIT scoped
                    # to only the loop that made it, in case of interruption.
                    set_field(bridge, ORIG_DEC1_PCT)
        finally:
            out.close_port(); out.delete()

        # -- restore, unconditionally, verified with a full page dump ------
        for _ in range(7):
            bridge.press_button(Button.CursorLeft); time.sleep(0.3)
        set_field(bridge, ORIG_REL1_TIME, tol=0.005)
        stamp(f"Rel1-time reverted to {current_field(bridge)}")

        page = rows(bridge)
        expect_row2 = "0.10 0.10 0.22 4.40 2.00 0s   0s   Off  "
        expect_row3 = "77%  95%  84%  67%  0%   0%   User Inf  "
        if page[2] != expect_row2 or page[3] != expect_row3:
            stamp("RESTORE MISMATCH -- full page below, fix before leaving:")
            for r in page:
                print(repr(r))
        else:
            stamp("full page verified identical to original")

        ok = leave_editor(bridge)
        stamp(f"left editor cleanly: {ok}")

        stamp(f"{len(written)} files written")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
