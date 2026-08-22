# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 42: ENV2->FilFreq depth, octaves per cent.  (PLAYS NOTES, EDITS PROGRAM 250)

For mpc2emu's `hob_f1[6] = round(filter_env_amount * 127)` writer field, which
was never measured against real hardware. Program 250 (built this session: a
ROM Sawtooth keymap through algorithm 1's 4-pole lowpass, base cutoff 1047Hz,
`F1 FRQ` Src1=ENV2, ENV2 parked at a constant 100% -- see RESOLUTION_NOTES for
the build) is a dedicated scratch program for exactly this. Never save over
it destructively; this probe reverts Depth to 0 before exiting either way.

The K2000's own `Coarse` field does NOT show a live ENV2-modulated value
during a held note -- verified this session at max depth (10800ct) through a
full 3-second hold with no change. So unlike CUTCAL's base-cutoff check, this
is capture-only; corner measurement is a separate analysis pass (the sawtooth's
discrete harmonic spectrum needs a different detector than CUTCAL's white-noise
one -- see that script's own notes).

Depth is the K2000's own unit (cents; 1200ct = 1 octave by definition), not
mpc2emu's 0-127 byte -- report Depth(ct) -> corner shift and let the byte-to-
cents correlation happen on their side, the same division of labour as CUTCAL.

    .venv/bin/python probes/p42_env_filter_depth.py
"""
import sys; sys.path.insert(0, ".")
import os
import time
import wave

import numpy as np
import rtmidi

from probes.hw import connect
from probes.p36_filter_fields import (
    rows, soft_index, SOFT, current_field, open_filter_page, leave_editor,
)
from k2000.definitions import Button

CHANNEL = 8
CAPTURE = ("system:capture_17", "system:capture_18")
MIDI_OUT_PORT = 27
NOTE = 60
PROGRAM_ID = 250
PROGRAM_NAME = "Default Program"          # never renamed after Save As

PREROLL = 0.35
HOLD = 3.0
TAIL = 1.0

#: Octave steps 0..4 in cents. Base cutoff 1047Hz; +4 octaves = ~16.8kHz,
#: comfortably inside Nyquist at 48kHz -- the full +/-10800ct range would run
#: the top end straight past Nyquist and just measure the anti-alias filter.
DEPTHS_CT = [0, 600, 1200, 1800, 2400, 3600, 4800]
TAKES = 3

OUT_DIR = os.path.expanduser("~/temp/k2kremote-logs")


def stamp(title=""):
    print(f"\n[{time.strftime('%H:%M:%S')}] {title}".rstrip(), flush=True)


class Recorder:
    def __init__(self, ports=CAPTURE):
        import jack
        self.ports = ports
        self.client = jack.Client("k2kenv2depth")
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
    """Closed-loop, ONE click per step -- never trust a computed distance.

    A first attempt clamped each step to +/-8 clicks, reasoning ~2ct/click from
    an early single-click test. That test was single isolated clicks; bursts of
    even 8 clicks in one message turned out to accelerate unpredictably (a
    separate measurement this session: 63 clicks in one message went 0->3500ct,
    then the *next* 63-click message went 3500->10400ct -- not a fixed rate,
    and history-dependent). The +/-8 version oscillated and never converged on
    600ct, stopping at 450ct with nothing damaged -- but also nothing swept.
    Repeated *single* clicks measured perfectly linear (2ct/click, 6 clicks ->
    12ct, no drift), so this trades speed for a step size with no acceleration
    regime at all.
    """
    for _ in range(limit):
        _, val = current_field(bridge)
        cur = int(val.replace("ct", ""))
        if cur == target:
            return cur
        bridge.alpha_wheel(1 if target > cur else -1)
        time.sleep(0.15)
    raise RuntimeError(f"could not converge on Depth={target}ct, stuck at {cur}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    bridge = connect()
    try:
        stamp(f"connected: {bridge.description}")

        for ch in str(PROGRAM_ID):
            bridge.press_button(getattr(Button, f"Number{ch}"))
        bridge.press_button(Button.Enter)
        time.sleep(0.4)
        reply = bridge.client.get_current_parameter_value().strip()
        assert reply == f"{PROGRAM_ID}*{PROGRAM_NAME}", \
            f"selection mismatch: got {reply!r}"
        stamp(f"program {PROGRAM_ID} confirmed by the device")

        bridge.press_button(Button.Edit); time.sleep(0.9)
        header = open_filter_page(bridge)
        if header is None or "4P LOPASS" not in header:
            stamp(f"FILTER PAGE GATE FAILED: {header!r} -- stopping, not capturing")
            return 1
        stamp(f"filter gate passed: {header}")

        # Cursor is left on Coarse by open_filter_page's navigation. Verified
        # live this session: Coarse -3ups-> DptCtl -1up-> Src2 -1up-> Depth.
        for wanted, ups in (("DptCtl", 3), ("Src2", 1), ("Depth", 1)):
            for _ in range(ups):
                bridge.press_button(Button.CursorUp); time.sleep(0.3)
            name, val = current_field(bridge)
            if name.strip() != wanted:
                stamp(f"unexpected cursor landing {name!r} (wanted {wanted!r}) "
                     f"-- aborting before touching values")
                return 1
        stamp(f"cursor on Depth, currently {val}")

        out = rtmidi.MidiOut()
        out.open_port(MIDI_OUT_PORT)
        written = []
        try:
            with Recorder() as rec:
                for depth in DEPTHS_CT:
                    actual = set_depth_ct(bridge, depth)
                    stamp(f"Depth set to {actual}ct")
                    for take in range(1, TAKES + 1):
                        pre = rec.record(PREROLL)
                        out.send_message([0x90 | CHANNEL, NOTE, 100])
                        held = rec.record(HOLD)
                        out.send_message([0x80 | CHANNEL, NOTE, 0])
                        tail = rec.record(TAIL)
                        channels = [np.concatenate([p, h, t]) for p, h, t in
                                   zip(pre, held, tail)]
                        path = os.path.join(
                            OUT_DIR, f"k2k_env2depth_{actual}ct_t{take}.wav")
                        write_wav(path, channels, rec.rate)
                        peak = max(float(np.max(np.abs(c2))) for c2 in channels)
                        print(f"   depth={actual}ct take={take} peak={peak:.4f} "
                              f"-> {path}", flush=True)
                        written.append(path)
                        time.sleep(0.2)
        finally:
            out.close_port(); out.delete()

        # Revert to the saved baseline before leaving -- never save over 250
        # with a nonzero depth left in the live buffer.
        set_depth_ct(bridge, 0)
        stamp(f"Depth reverted to {current_field(bridge)}")
        ok = leave_editor(bridge)
        stamp(f"left editor cleanly: {ok}")

        stamp(f"{len(written)} files written, corner analysis is a separate pass")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
