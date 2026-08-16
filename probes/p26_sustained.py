# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 26: does a timing profile survive *sustained* use? (the p24 blind spot)

p24 measured isolated round-trips, an idle duty cycle and single keypresses, and
on that evidence §13 shipped a 150 ms gap with a 1.2 s heartbeat. In real use the
K2000 hung within minutes (§15). The measurements were not wrong; they were of
the wrong thing. Nothing in them put sustained, overlapping traffic on the wire,
which is the only regime where this device fails.

This probe drives the **real** ``RefreshWorker`` — the actual mix of presses,
settle reads, heartbeats and periodic GETGRAPHICS — with a synthetic user
navigating for minutes at a time, and watches for the device getting into
trouble. Two signals, both script-visible:

* **stalls** — a request the device never answers. This is what a lock-up looks
  like from here, and it is unambiguous.
* **latency drift** — the median ALLTEXT time between the first and last third
  of a run. This was *meant* to be the early warning, on the theory that "reacts
  slow" precedes a hang. **It does not.** In the one failure caught so far the
  device held 131.4 ms with 0.1 ms of drift and then simply stopped answering:
  a cliff, not a slope. Kept because it is free and may catch some other mode,
  but do not read a flat median as safety.

Flicker still needs eyes; a stall does not.

    .venv/bin/python probes/p26_sustained.py                 # both profiles
    .venv/bin/python probes/p26_sustained.py --minutes 5
    .venv/bin/python probes/p26_sustained.py --profile fast

**Non-destructive**: the synthetic user sends net-zero cursor pairs, which on
Program Mode step the program list back and forth (the heavy, realistic case —
see §13's sweep). It refuses to start on a destructive screen, aborts on the
first stall, and always restores the conservative gap.
"""
import sys; sys.path.insert(0, ".")
import argparse
import statistics
import threading
import time

from probes.hw import connect
from k2kremote import midi_bridge
from k2kremote.refresh import RefreshWorker, is_destructive_screen
from k2000.definitions import Button

SAFE_GAP = 0.5


def stamp(title=""):
    """Head a block of output with a wall-clock time, so a run can be matched
    against what the panel was doing at that moment. Once per block, not per
    line — a timestamp on every progress line is just noise."""
    print(f"\n[{time.strftime('%H:%M:%S')}] {title}".rstrip(), flush=True)

# (gap, settle, settle_retry, heartbeat) — what shipped, and what §13 tried.
PROFILES = {
    "conservative": (0.5, 0.35, None, 2.5),
    "fast": (0.15, 0.15, 0.25, 1.2),
}


class Instrumented:
    """Wraps the bridge and times every call the worker makes through it."""

    def __init__(self, bridge):
        self._bridge = bridge
        self.samples = []          # (monotonic, kind, seconds, failed)
        self.lock = threading.Lock()
        self.panel_events = 0      # inbound PANEL: proof a human exercised the path

    def _timed(self, kind, fn, *a, **k):
        # Subtract the throttle's own sleep, or every number is dominated by how
        # long *we* chose to wait: at a 500 ms gap a call reads ~631 ms and the
        # device's 131 ms is buried inside it. What we want is the device's time.
        out = self._bridge.client.midi_out
        waited = getattr(out, "throttled_seconds", 0.0)
        start = time.monotonic()
        try:
            result = fn(*a, **k)
            failed = False
        except Exception:
            result, failed = None, True
        elapsed = time.monotonic() - start
        elapsed -= max(0.0, getattr(out, "throttled_seconds", 0.0) - waited)
        with self.lock:
            self.samples.append((start, kind, elapsed, failed))
        if failed:
            raise RuntimeError(f"{kind} did not answer after {elapsed:.2f}s")
        return result

    def get_screen_text_attrs(self):
        return self._timed("text", self._bridge.get_screen_text_attrs)

    def get_graphics(self):
        return self._timed("graphics", self._bridge.get_graphics)

    def press_button(self, button):
        return self._timed("press", self._bridge.press_button, button)

    def alpha_wheel(self, clicks):
        return self._timed("wheel", self._bridge.alpha_wheel, clicks)

    def poll_panel(self):
        seen = self._bridge.poll_panel()
        if seen:
            with self.lock:
                self.panel_events += 1
        return seen

    def __getattr__(self, name):
        return getattr(self._bridge, name)

    def stats(self, kind, since=None, until=None):
        with self.lock:
            xs = [s for t, k, s, f in self.samples
                  if k == kind and not f
                  and (since is None or t >= since) and (until is None or t < until)]
        return xs

    @property
    def failures(self):
        with self.lock:
            return [(k, s) for _, k, s, f in self.samples if f]


def drive(worker, stop, *, burst=4, gap=0.25, rest=2.5):
    """A synthetic user: bursts of navigation, then a pause. Net zero."""
    forward = True
    while not stop.is_set():
        for _ in range(burst):
            if stop.is_set():
                return
            worker.press(Button.CursorRight if forward else Button.CursorLeft)
            stop.wait(gap)
        forward = not forward          # undo the burst we just did
        stop.wait(rest)


def run_profile(bridge, name, minutes):
    gap, settle, retry, heartbeat = PROFILES[name]
    stamp(f"=== {name}: gap {gap*1000:.0f}ms  settle {settle*1000:.0f}ms  "
          f"re-look {retry}  heartbeat {heartbeat}s  —  {minutes:.1f} min ===")
    bridge._bridge.client.midi_out._gap = gap

    stop = threading.Event()
    errors = []
    # mirror_panel is ON: with XMIT Bttns set, a physical press reaches us and
    # schedules a read. Excluding it would leave the very path §15 blames
    # untested — it was live during the session that hung.
    worker = RefreshWorker(bridge, on_frame=lambda f: None,
                           on_error=lambda e: errors.append(str(e)),
                           settle=settle, settle_retry=retry,
                           heartbeat=heartbeat, mirror_panel=True)
    worker.start()
    user = threading.Thread(target=drive, args=(worker, stop), daemon=True)
    user.start()

    started = time.monotonic()
    deadline = started + minutes * 60
    stalled = False
    panel_before = bridge.panel_events
    try:
        while time.monotonic() < deadline:
            time.sleep(2.0)
            if bridge.failures:
                stalled = True
                stamp(f"*** STALLED after {time.monotonic()-started:.0f}s: "
                      f"{bridge.failures[0][0]} never answered")
                break
            done = time.monotonic() - started
            if int(done) % 30 < 2:
                recent = bridge.stats("text", since=time.monotonic() - 30)
                if recent:
                    print(f"  {done:4.0f}s  ALLTEXT median "
                          f"{statistics.median(recent)*1000:6.1f} ms "
                          f"({len(recent)} reads, "
                          f"{bridge.panel_events - panel_before} panel events)",
                          flush=True)
    finally:
        stop.set()
        worker.stop()
        worker.join(timeout=10)
        user.join(timeout=5)
        bridge._bridge.client.midi_out._gap = SAFE_GAP
        time.sleep(1.5)

    third = (time.monotonic() - started) / 3
    early = bridge.stats("text", since=started, until=started + third)
    late = bridge.stats("text", since=started + 2 * third)
    return {
        "name": name, "stalled": stalled, "errors": len(errors),
        "panel": bridge.panel_events - panel_before,
        "early": statistics.median(early) if early else float("nan"),
        "late": statistics.median(late) if late else float("nan"),
        "worst": max(bridge.stats("text") or [float("nan")]),
        "reads": len(bridge.stats("text")),
    }


def report(rows):
    stamp("=" * 68)
    print(f"{'profile':<14}{'stalled':>9}{'early':>10}{'late':>10}{'drift':>9}"
          f"{'worst':>10}{'panel':>8}")
    print("=" * 68)
    for r in rows:
        drift = r["late"] - r["early"]
        print(f"{r['name']:<14}{'YES' if r['stalled'] else 'no':>9}"
              f"{r['early']*1000:9.1f}m{r['late']*1000:9.1f}m"
              f"{drift*1000:+8.1f}m{r['worst']*1000:9.1f}m{r['panel']:>8}")
    print("=" * 68)
    if any(r["panel"] == 0 for r in rows):
        print("!! panel = 0 for some profile: nobody touched the front panel, so")
        print("!! the inbound-PANEL path was NOT exercised. That run proves nothing")
        print("!! about the path §15 blames.")
    print("A profile passes only if it never stalled AND the median barely moved.")
    print("Healthy ALLTEXT is ~131.6 ms with <2 ms spread, so tens of ms of drift")
    print("is the device falling behind — 'reacts slow' before it becomes a hang.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=float, default=3.0,
                    help="how long to hold each profile under load (default 3)")
    ap.add_argument("--profile", choices=sorted(PROFILES), action="append",
                    help="run only this profile (repeatable; default: both)")
    args = ap.parse_args()

    raw = connect()
    raw.client.midi_out._gap = SAFE_GAP
    rows = bridge = None
    try:
        text = raw.get_screen_text().split("\n")
        print(f"connected: {raw.description}")
        print(f"screen: {text[0].rstrip()!r}")
        if is_destructive_screen(text):
            sys.exit("panel is on a destructive prompt — refusing to load it")
        print(f"shipping default gap is {midi_bridge.SEND_GAP*1000:.0f} ms\n"
              "watch the panel if you can; stalls and drift are caught here, "
              "flicker is not.")
        bridge = Instrumented(raw)
        rows = []
        for name in (args.profile or ["conservative", "fast"]):
            rows.append(run_profile(bridge, name, args.minutes))
            if rows[-1]["stalled"]:
                print("  stopping: no point measuring anything faster.")
                break
            time.sleep(5.0)   # let the device settle between profiles
    finally:
        raw.client.midi_out._gap = SAFE_GAP
        if rows:
            report(rows)
        raw.close()


if __name__ == "__main__":
    main()
