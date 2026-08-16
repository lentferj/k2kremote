# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 27: watch what the mirror actually sees during a disk operation.

Three attempts at "stop reporting a disconnection during a disk load" have each
been built on a guess about what the K2000 shows and when it stops answering.
This records it instead.

It polls ALLTEXT at the app's own cadence and logs, with wall-clock stamps:

* every screen it reads, **only when the text changes** (so the log is the
  sequence of screens, not thousands of identical lines);
* every read that fails, and how long the silence has lasted so far;
* what ``is_busy_screen`` and ``is_destructive_screen`` say about each screen.

The questions it answers, none of which are currently known:

1. What is the **last screen we successfully read** before the device goes
   quiet? If that is the file list rather than a progress message, no amount of
   progress-message matching can ever help.
2. **How long** is the silence? If a load is quiet for minutes, no fixed grace
   window is going to cover it and the fix has to be contextual.
3. Does the device ever show us a progress screen *over MIDI* at all, or only on
   its own LCD?

    .venv/bin/python probes/p27_watch.py            # until Ctrl+C
    .venv/bin/python probes/p27_watch.py --minutes 3

**Read-only**: it sends ALLTEXT and nothing else — never the 963 ms GETGRAPHICS,
never a button. It stops polling the moment a screen matches a destructive
marker, because a poll landing in an object rewrite is the one thing known to
lock the unit up (RESOLUTION_NOTES §9).
"""
import sys; sys.path.insert(0, ".")
import argparse
import time

from probes.hw import connect
from k2kremote.refresh import (HEARTBEAT, is_busy_screen, is_destructive_screen)


def stamp():
    return time.strftime("%H:%M:%S")


def summarise(rows):
    """The non-blank lines of a screen, joined — enough to identify it."""
    return " | ".join(r.rstrip() for r in rows if r.strip()) or "(blank)"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--interval", type=float, default=HEARTBEAT,
                    help=f"seconds between reads (default {HEARTBEAT}, the app's)")
    args = ap.parse_args()

    # Retry: the whole point is to watch a period when the device is silent, and
    # a load already in progress makes autodetect find nothing at all. Dying at
    # startup is exactly the wrong moment to give up.
    bridge = None
    give_up_at = time.monotonic() + 180
    while bridge is None:
        try:
            bridge = connect()
        except Exception as exc:
            if time.monotonic() >= give_up_at:
                sys.exit(f"no K2000 after 3 minutes of retrying: {exc}")
            print(f"[{stamp()}] no device yet ({str(exc)[:60]}…) — retrying in 5s")
            time.sleep(5.0)
    print(f"[{stamp()}] watching: {bridge.description}")
    print(f"[{stamp()}] ALLTEXT every {args.interval}s, timeout {bridge.timeout}s. "
          "Read-only — no graphics, no presses.")
    print(f"[{stamp()}] >>> start your disk operation now <<<\n")

    last_text = None
    silent_since = None
    longest_silence = 0.0
    last_good = None
    deadline = time.monotonic() + args.minutes * 60
    try:
        while time.monotonic() < deadline:
            try:
                rows = bridge.get_screen_text().split("\n")
            except Exception as exc:
                now = time.monotonic()
                if silent_since is None:
                    silent_since = now
                    print(f"[{stamp()}] SILENT  ({type(exc).__name__}) — "
                          f"last screen we read was:")
                    print(f"           {summarise(last_good or [])}")
                    print(f"           busy={is_busy_screen(last_good or [])} "
                          f"destructive={is_destructive_screen(last_good or [])}")
                else:
                    held = now - silent_since
                    longest_silence = max(longest_silence, held)
                    if int(held) % 5 == 0:
                        print(f"[{stamp()}]   ...still silent, {held:.0f}s")
                time.sleep(args.interval)
                continue

            if silent_since is not None:
                held = time.monotonic() - silent_since
                longest_silence = max(longest_silence, held)
                print(f"[{stamp()}] BACK after {held:.1f}s of silence")
                silent_since = None

            text = "\n".join(rows)
            last_good = rows
            if text != last_text:
                last_text = text
                busy, danger = is_busy_screen(rows), is_destructive_screen(rows)
                flag = "  <<< BUSY" if busy else ("  <<< DESTRUCTIVE" if danger else "")
                print(f"[{stamp()}] {summarise(rows)}{flag}")
                if danger:
                    print(f"[{stamp()}] destructive screen — stopping, a poll here "
                          "can lock the unit up (§9)")
                    break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n[{stamp()}] stopped by hand")
    finally:
        print(f"\n[{stamp()}] longest silence seen: {longest_silence:.1f}s")
        if last_good:
            print(f"[{stamp()}] last screen: {summarise(last_good)}")
        bridge.close()


if __name__ == "__main__":
    main()
