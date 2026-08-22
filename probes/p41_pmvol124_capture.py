# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Probe 41: capture PMVOL124 for a KRZ->AKAI conversion A/B.  (PLAYS NOTES)

For the sibling mpc2emu project, comparing our K2000 audio against s3ked's AKAI
conversion of the same nine presets (ids 200..208, PMVOL124, verified resident
by name and id before this probe was written). Direct out, no effects, no
level-matching -- the K2000 as it is.

Two guards, both because a capture that silently failed and still "passed" has
already cost this collaboration real time tonight, in different disguises on
different machines:

* **Selection is confirmed by the DEVICE, never inferred from audio.**
  SysEx 0x16 (ParameterValue) in plain ProgramMode answers "<id>*<name>", which
  is checked against what was just selected before a single note is played. A
  Program Change the K2000 silently ignored would otherwise produce two
  identical takes filed under different names -- exactly the trap eosed hit.
* **Every take is checked for lift OVER ITS OWN PRE-ROLL, not "did it clip."**
  Silence never clips, so a clipping check alone passes a dropped note. Each
  take opens with a short silent pre-roll before the MIDI note-on; the note
  region must sit meaningfully above that pre-roll's own noise floor, which
  needs no absolute reference -- only the take compared with itself.

    .venv/bin/python probes/p41_pmvol124_capture.py --check
    .venv/bin/python probes/p41_pmvol124_capture.py --notes 69 --presets 200-208
"""
import sys; sys.path.insert(0, ".")
import argparse
import os
import time
import wave

import numpy as np

from probes.hw import connect
from probes.p36_filter_fields import select_program

CHANNEL = 8                     # panel: Channel:9 (1-indexed)
CAPTURE = ("system:capture_17", "system:capture_18")
MIDI_OUT_PORT = 27

PREROLL = 0.35                  # silent lead-in, for the lift check
HOLD = 3.0                      # note held, per the brief
TAIL = 6.0                      # let the release ring out fully
SETTLE = 0.3                    # after selecting a program, before recording

OUT_DIR = os.path.expanduser("~/temp/k2kremote-logs")

#: The nine presets, in the order verified resident on the device.
PRESETS = list(range(200, 209))

#: Lift threshold: the note region's peak must sit at least this many dB above
#: the pre-roll's own peak. 40 dB (100x amplitude) is comfortably above noise
#: floor variation but far below what a real note produces.
LIFT_DB = 40.0
#: Fallback floor when the pre-roll is at or near digital silence (division by
#: a near-zero pre-roll peak would otherwise inflate the dB ratio meaninglessly).
SILENCE_FLOOR = 1e-6
ABSOLUTE_MIN_PEAK = 1e-3         # ~ -60 dBFS: "did anything happen at all"


class GuardFailed(Exception):
    """A guard refused this take. Nothing here silently passes a bad capture."""


def stamp(title=""):
    print(f"\n[{time.strftime('%H:%M:%S')}] {title}".rstrip(), flush=True)


class Recorder:
    """Records CAPTURE (both channels, unmixed) for the duration of a block."""

    def __init__(self, ports=CAPTURE):
        import jack
        self.ports = ports
        self.client = jack.Client("k2kpmvol124")
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


def confirm_selection(bridge, expected_id: int, expected_name: str) -> None:
    """Ask the DEVICE what is selected. Raise rather than assume.

    SysEx 0x16 in plain ProgramMode answers "<id>*<name>", e.g.
    '200*Med. RainStick 1' -- both the id and the name in one message, so this
    checks both rather than trusting a Program Change was received at all.
    """
    reply = bridge.client.get_current_parameter_value().strip()
    if "*" not in reply:
        raise GuardFailed(
            f"expected '{expected_id}*{expected_name}', device answered "
            f"{reply!r} -- no '*' separator, cannot parse a selection at all"
        )
    shown_id, _, shown_name = reply.partition("*")
    ok_id = shown_id.strip() == str(expected_id)
    ok_name = shown_name.strip() == expected_name.strip()
    if not (ok_id and ok_name):
        raise GuardFailed(
            f"selection mismatch: asked for {expected_id} {expected_name!r}, "
            f"device shows id={shown_id.strip()!r} name={shown_name.strip()!r} "
            f"-- the Program Change was not received as sent"
        )


def lift_over_preroll(channels, rate) -> tuple:
    """(ok, detail) -- does the note region lift over this take's OWN pre-roll?

    Silence never clips, so a clipping check alone passes a dropped note. This
    compares the take against itself: the pre-roll segment (before note-on) is
    the noise floor, and the note region must sit LIFT_DB above it -- with an
    absolute floor for the case where the pre-roll is near-digital-silence,
    where a dB ratio against ~0 would be meaningless.
    """
    pre_n = int(PREROLL * rate)
    results = []
    for ch, name in zip(channels, ("L", "R")):
        pre = ch[:pre_n]
        note = ch[pre_n:]
        pre_peak = float(np.max(np.abs(pre))) if len(pre) else 0.0
        note_peak = float(np.max(np.abs(note))) if len(note) else 0.0
        if note_peak < ABSOLUTE_MIN_PEAK:
            results.append((False, f"{name}: note_peak {note_peak:.6f} below "
                                   f"the absolute floor -- nothing played"))
            continue
        if pre_peak < SILENCE_FLOOR:
            results.append((True, f"{name}: pre-roll silent, note_peak "
                                  f"{note_peak:.4f} clears the absolute floor"))
            continue
        lift_db = 20 * np.log10(note_peak / pre_peak)
        results.append((lift_db >= LIFT_DB,
                        f"{name}: lift {lift_db:.1f} dB (pre {pre_peak:.6f} -> "
                        f"note {note_peak:.4f})"))
    ok = all(r[0] for r in results)
    return ok, "; ".join(r[1] for r in results)


def capture_one(bridge, out, rec, preset: int, name: str, note: int, take: int,
                path: str) -> None:
    with_note = f"p{preset}_n{note}_t{take}"
    audio_task = rec.record(PREROLL)
    t_on = time.monotonic()
    out.send_message([0x90 | CHANNEL, note, 100])
    held = rec.record(HOLD)
    out.send_message([0x80 | CHANNEL, note, 0])
    tail = rec.record(TAIL)
    channels = [np.concatenate([p, h, t]) for p, h, t in
               zip(audio_task, held, tail)]

    ok, detail = lift_over_preroll(channels, rec.rate)
    peak = max(float(np.max(np.abs(c))) for c in channels)
    if not ok:
        raise GuardFailed(f"{with_note}: LIFT GATE FAILED -- {detail}")

    write_wav(path, channels, rec.rate)
    print(f"   {with_note}  peak {peak:.4f}  {detail}  -> {os.path.basename(path)}",
          flush=True)


def run(bridge, out, rec, presets, notes) -> dict:
    """Returns {(preset, note): 'ok'|'no-map'|error} for the caller's summary."""
    from k2000.definitions import ObjectType
    status = {}
    for preset in presets:
        name = bridge.object_name(ObjectType.Program, preset)
        select_program(bridge, preset)
        time.sleep(SETTLE)
        try:
            confirm_selection(bridge, preset, name)
        except GuardFailed as exc:
            stamp(f"preset {preset}: SELECTION GUARD FAILED -- {exc}")
            status[preset] = f"selection-failed: {exc}"
            continue
        stamp(f"preset {preset} '{name}' confirmed by the device")

        for note in notes:
            note_ok = True
            for take in range(1, 4):
                path = os.path.join(OUT_DIR, f"k2k_p{preset}_n{note}_t{take}.wav")
                try:
                    capture_one(bridge, out, rec, preset, name, note, take, path)
                except GuardFailed as exc:
                    print(f"   !! {exc}", flush=True)
                    note_ok = False
                    status[(preset, note)] = str(exc)
                    break
                time.sleep(0.3)
            if note_ok and (preset, note) not in status:
                status[(preset, note)] = "ok"
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify selection + lift gate on ONE preset/note/take")
    ap.add_argument("--presets", default="200-208",
                    help="e.g. 200-208 or 200,205")
    ap.add_argument("--notes", default="69", help="e.g. 69 or 69,57,79")
    args = ap.parse_args()

    def parse_ints(spec):
        out = []
        for part in spec.split(","):
            if "-" in part:
                a, b = part.split("-")
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(part))
        return out

    presets = parse_ints(args.presets)
    notes = parse_ints(args.notes)
    if args.check:
        presets, notes = presets[:1], notes[:1]

    os.makedirs(OUT_DIR, exist_ok=True)
    import rtmidi
    bridge = connect()
    try:
        stamp(f"connected: {bridge.description}")
        while bridge.client.midi_in.get_message() is not None:
            pass
        rows = bridge.get_screen_text().split("\n")
        if "ProgramMode" not in rows[0]:
            print("panel is not in ProgramMode; get there first")
            return 1

        out = rtmidi.MidiOut()
        out.open_port(MIDI_OUT_PORT)
        try:
            with Recorder() as rec:
                status = run(bridge, out, rec, presets, notes)
        finally:
            out.close_port(); out.delete()

        stamp("summary")
        bad = {k: v for k, v in status.items() if v != "ok"}
        for k, v in status.items():
            print(f"  {k}: {v}")
        if bad:
            print(f"\n{len(bad)} of {len(status)} FAILED a guard -- see above")
            return 1
        print(f"\nall {len(status)} passed both guards")
        return 0
    finally:
        bridge.close()


if __name__ == "__main__":
    sys.exit(main())
