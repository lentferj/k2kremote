# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 24: measure what the mirror's timing constants are actually worth.

The refresh strategy in ``k2kremote/refresh.py`` rests on numbers that were
reasoned about before they were measured. This probe measures them. Results
from the 2026-08-15 run are in ``docs/RESOLUTION_NOTES.md`` §13; re-run it after
any change to the timing constants, or on a different interface.

    .venv/bin/python probes/p24_timing.py             # read-only: safe unattended
    .venv/bin/python probes/p24_timing.py --press     # + reversible cursor presses
    .venv/bin/python probes/p24_timing.py --gap       # everything + sweep the floor
    .venv/bin/python probes/p24_timing.py --sweep-only  # JUST the sweep, ~1 min

**Phases 1-3 are read-only** and safe to run unattended. ``--press`` sends
net-zero cursor moves (left then right), which is reversible but does change the
cursored field while it runs — don't use it if the panel is sitting on a dialog.

``--sweep-only`` skips straight to the sweep after capturing a reference —
use it when a human is standing at the panel and should not be kept waiting
through 90 s of measurement first.

``--gap`` is the one phase that needs a human in the room, and the 2026-08-15
run proved why: the automated check passed at every step down to 40 ms while
the person watching saw the LCD flickering. ``intact()`` only catches damage
that *survives* to the next read; a flicker a repaint cleans up is invisible to
it, and so is a lock-up. **In this phase the human is the instrument and the
script is bookkeeping.** It now asks for your verdict after each step so the
onset can be pinned to a gap value instead of recalled afterwards.
"""
import sys; sys.path.insert(0, ".")
import statistics
import time

from probes.hw import connect
from k2kremote.midi_bridge import SEND_GAP, SYSEX_FLOOR, ThrottledOut
from k2kremote.refresh import is_destructive_screen

SAFE_GAP = 0.5   # what we fall back to between phases


class Panel:
    """A reference capture of the LCD, and a check that it still matches.

    Corruption that **survives** to the next read shows up here, since we read
    the same planes the panel draws. That is a genuinely useful self-check for
    the read-only phases.

    Do not mistake it for a garbling detector. On 2026-08-15 it returned CLEAN
    at every gap down to 40 ms while a human watched the LCD flicker: anything a
    repaint fixes before we look is invisible to it, and so is a lock-up. Where
    a person is watching, their verdict outranks this one.
    """

    def __init__(self, bridge):
        self.bridge = bridge
        self.text, self.reverse = bridge.get_screen_text_attrs()
        self.pixels = bridge.get_graphics()

    def intact(self, tag: str) -> bool:
        text, reverse = self.bridge.get_screen_text_attrs()
        pixels = self.bridge.get_graphics()
        bad = []
        if text != self.text:
            bad.append("TEXT")
        if reverse != self.reverse:
            bad.append("MASK")
        if not (pixels == self.pixels).all():
            bad.append(f"PIXELS({int((pixels != self.pixels).sum())} differ)")
        print(f"  [{tag}] panel {'CLEAN' if not bad else 'CHANGED -> ' + ', '.join(bad)}")
        return not bad


def _timed(fn, repeats=7, settle=0.65):
    """Median/min/max round trip, with the throttle slept off so we time the wire."""
    samples = []
    for _ in range(repeats):
        time.sleep(settle)
        start = time.monotonic()
        fn()
        samples.append(time.monotonic() - start)
    return statistics.median(samples), min(samples), max(samples)


def measure_reads(bridge):
    """Phase 1 — what each screen read actually costs. Read-only."""
    print("\n== 1. round-trip cost of the two screen reads ==")
    text = _timed(bridge.get_screen_text)
    graphics = _timed(bridge.get_graphics)
    for label, (median, low, high), predicted in (
        ("ALLTEXT", text, "~103 ms (321 bytes)"),
        ("GETGRAPHICS", graphics, "~819 ms (2561 bytes)"),
    ):
        print(f"  {label:<12} median {median*1000:7.1f} ms  "
              f"(min {low*1000:6.1f} max {high*1000:6.1f})   payload predicts {predicted}")
    print(f"\n  GETGRAPHICS costs {graphics[0]/text[0]:.1f}x an ALLTEXT — the whole")
    print("  argument for using the text plane as the change detector.")
    return text[0], graphics[0]


def measure_stability(bridge, panel, samples=40):
    """Phase 2 — the detector's load-bearing assumption. Read-only.

    If anything on the LCD blinks, counts or flickers, ALLTEXT never comes back
    identical, the shortcut never fires, and the whole strategy is inert. This
    is the check that says whether "identical means unchanged" is true at all.
    """
    print(f"\n== 2. is the text plane stable on a quiet screen? ({samples} reads) ==")
    text_diffs = mask_diffs = 0
    for _ in range(samples):
        time.sleep(0.55)
        text, reverse = bridge.get_screen_text_attrs()
        if text != panel.text:
            if not text_diffs:
                for row, (a, b) in enumerate(zip(panel.text.split("\n"), text.split("\n"))):
                    if a != b:
                        print(f"   row {row} changed:\n     {a!r}\n     {b!r}")
            text_diffs += 1
        if reverse != panel.reverse:
            mask_diffs += 1
    print(f"  {text_diffs} text differences, {mask_diffs} mask differences")
    if text_diffs or mask_diffs:
        print("  *** the detector will misfire on this page — investigate before trusting it")
    return not (text_diffs or mask_diffs)


def measure_self_spacing(bridge, panel):
    """Phase 3 — how much spacing reads give themselves for free. Read-only.

    A reply that takes longer than the floor *is* the spacing. If that holds,
    the throttle is doing nothing for reads and everything for button presses,
    which the device answers with nothing.
    """
    print("\n== 3. do reads space themselves? ==")
    out = bridge.client.midi_out
    out._gap = 0.001  # not below the floor in effect: the reply time dominates
    start = time.monotonic()
    for _ in range(10):
        bridge.get_screen_text()
    span = (time.monotonic() - start) / 10
    out._gap = SAFE_GAP
    time.sleep(0.6)
    print(f"  10 back-to-back ALLTEXT, throttle off: {span*1000:.1f} ms apart "
          f"(floor is {SYSEX_FLOOR*1000:.0f} ms)")
    if span >= SYSEX_FLOOR:
        print("  -> the reply alone clears the floor; the gap only affects presses")
    panel.intact("unthrottled read burst")

    print(f"\n  ...and at the shipping {SEND_GAP*1000:.0f} ms gap:")
    out._gap = SEND_GAP
    errors = 0
    start = time.monotonic()
    for _ in range(40):
        try:
            bridge.get_screen_text()
        except Exception as exc:
            errors += 1
            print(f"   ERROR: {type(exc).__name__}: {exc}")
    span = time.monotonic() - start
    out._gap = SAFE_GAP
    time.sleep(0.6)
    print(f"  40 ALLTEXT in {span:.1f} s ({span/40*1000:.0f} ms each), {errors} errors")
    return panel.intact(f"40 reads at {SEND_GAP*1000:.0f} ms gap")


def measure_redraw(bridge, panel):
    """Phase 4 (--press) — how long the LCD takes to redraw after a press.

    This is the only thing SETTLE is trying to cover. Note the read cannot be
    *issued* until the throttle allows it, so the earliest observable point is
    gap + one ALLTEXT: a SETTLE below SEND_GAP cannot buy anything.
    """
    from k2000.definitions import Button

    print("\n== 4. LCD redraw latency after a press (production timing) ==")
    out = bridge.client.midi_out
    out._gap = SEND_GAP
    for delay in (0.0, 0.05, 0.15, 0.30, 0.50):
        seen = 0
        elapsed = []
        for _ in range(3):
            before, _ = bridge.get_screen_text_attrs()
            start = time.monotonic()
            bridge.press_button(Button.CursorLeft)
            if delay:
                time.sleep(delay)
            after, _ = bridge.get_screen_text_attrs()
            elapsed.append(time.monotonic() - start)
            seen += after != before
            time.sleep(0.3)
            bridge.press_button(Button.CursorRight)  # net zero
            time.sleep(0.4)
        print(f"  sleep {delay*1000:4.0f} ms -> read landed "
              f"{sum(elapsed)/len(elapsed)*1000:5.0f} ms after the press: "
              f"redraw seen {seen}/3")
    out._gap = SAFE_GAP
    ok = panel.intact("redraw sweep")

    print(f"\n  press burst at {SEND_GAP*1000:.0f} ms (the one path the gap governs):")
    out._gap = SEND_GAP
    start = time.monotonic()
    for _ in range(8):
        bridge.press_button(Button.CursorLeft)
        bridge.press_button(Button.CursorRight)
    span = time.monotonic() - start
    out._gap = SAFE_GAP
    print(f"  16 net-zero presses in {span:.1f} s ({span/16*1000:.0f} ms apart)")
    return ok and panel.intact(f"16 presses at {SEND_GAP*1000:.0f} ms gap")


BURST_SECONDS = 4.0   # long enough to actually watch, at any gap


def sweep_gap(bridge, panel):
    """Phase 5 — push the gap below the floor. THE HUMAN IS THE INSTRUMENT.

    Structured so you never have to watch the monitor and the LCD at once. Each
    step is a three-beat turn: read the prompt, look at the panel while it runs,
    look back to give a verdict. Nothing is sent until you press Enter.

    Bursts are sized by *duration*, not press count, so every step gives roughly
    the same window to observe — and so a small gap means genuinely sustained
    traffic rather than a burst that is over before you have focused.

    The sweep opens with two **controls**: the old 500 ms default, which should
    look perfectly calm, and the shipping 150 ms. Those calibrate the eye before
    anything unusual happens — and if 150 ms already misbehaves, that is a fault
    in what we ship and the most important thing this probe can tell us.

    **What the presses actually do.** On Program Mode the cursor keys step
    through the program list, so each press *selects and loads an adjacent
    program* — observed live as the display alternating 996/995. This is not the
    cheap field-cursor move it was originally described as. That makes it the
    right test rather than the wrong one: sustained program loads are exactly
    what a user holding an arrow key produces, and a busy CPU is the regime the
    120 ms floor was derived from. It does mean the result is about "MIDI rate
    *plus* real work", not MIDI rate alone.
    """
    from k2000.definitions import Button

    interactive = sys.stdin.isatty()
    print("\n== 5. SysEx gap sweep BELOW the floor ==")
    if not interactive and "--force-unattended" not in sys.argv:
        # Fail closed. This phase deliberately provokes a hardware fault and its
        # only real instrument is a person looking at the panel; without one it
        # is not a weaker experiment, it is just damage with no observer. An
        # earlier version warned and carried on, which ran the 100 ms step
        # unattended and stalled the device -- exactly what the prompts existed
        # to prevent. Note `!cmd` from inside a Claude Code session is NOT a tty:
        # run this from a real terminal.
        print("  REFUSING: stdin is not a tty, so nobody can answer the prompts.")
        print("  This phase provokes a fault on purpose and needs a human watching")
        print("  the LCD. Run it from a real terminal, not through a wrapper.")
        print("  (--force-unattended overrides, but there is no good reason to.)")
        return None
    print(f"  Each step: press Enter, look at the LCD for ~{BURST_SECONDS:.0f} s,")
    print("  then look back here and say what you saw.")
    print("  Watch for: flicker, tearing, garbled characters, the display stalling.")

    out = bridge.client.midi_out
    onset = None
    try:
        for gap in (0.5, SEND_GAP, 0.12, 0.1, 0.08, 0.06, 0.04):
            pairs = max(8, int(BURST_SECONDS / (2 * gap)))
            if gap > SEND_GAP:
                flag = "  (CONTROL: the old default — expect it calm)"
            elif gap == SEND_GAP:
                flag = "  (CONTROL: what we ship today)"
            elif gap < SYSEX_FLOOR:
                flag = "  (below the RE'd floor)"
            else:
                flag = "  (at the RE'd floor)"
            while True:
                print(f"\n  --- gap {gap*1000:.0f} ms{flag} ---")
                print(f"  {pairs*2} net-zero cursor presses, about "
                      f"{pairs*2*gap:.0f} s of traffic.")
                if interactive:
                    go = input("  Enter to send  (s = skip this gap, q = stop): ")
                    go = go.strip().lower()[:1]
                    if go == "q":
                        print("  stopped by request.")
                        return onset
                    if go == "s":
                        break
                    print("  >>> LOOK AT THE LCD NOW <<<", flush=True)
                    time.sleep(1.5)

                out._gap = gap   # deliberately under the clamp: that is the experiment
                begin = time.monotonic()
                for _ in range(pairs):
                    bridge.press_button(Button.CursorLeft)
                    bridge.press_button(Button.CursorRight)
                span = time.monotonic() - begin
                out._gap = SAFE_GAP
                time.sleep(0.8)

                print(f"  sent {pairs*2} presses in {span:.1f} s "
                      f"({span/(pairs*2)*1000:.0f} ms apart)")
                try:
                    clean = panel.intact(f"gap {gap*1000:.0f} ms")
                except Exception as exc:
                    # The device stopping answering IS the failure we came for --
                    # don't let it come out as a traceback. Verified 2026-08-15:
                    # it recovers on its own after a few seconds.
                    print(f"  *** DEVICE STOPPED ANSWERING: {type(exc).__name__}: {exc}")
                    print(f"  *** that is the cliff — {gap*1000:.0f} ms is too fast.")
                    time.sleep(3.0)
                    return onset or gap
                if not interactive:
                    break
                answer = input("  Flicker/tearing/stall? [y = yes, n = no, "
                               "r = repeat this gap, q = stop] ").strip().lower()[:1]
                if answer == "r":
                    continue          # same gap again — subtle flicker is worth a second look
                if answer == "q":
                    print("  stopped by request.")
                    return onset
                if answer == "y":
                    onset = onset or gap
                    print(f"  *** noted: trouble visible at {gap*1000:.0f} ms")
                elif not clean:
                    print("  *** the panel also no longer matches the reference")
                break
    except KeyboardInterrupt:
        print("\n  stopped by hand.")
    finally:
        out._gap = SAFE_GAP

    print("\n  --- sweep result ---")
    if onset is None:
        print("  no trouble reported at any step, down to 40 ms.")
        print("  Note this is still an idle page: the 120 ms floor came from a busy CPU.")
    elif onset >= SEND_GAP:
        print(f"  *** trouble at {onset*1000:.0f} ms, which is AT OR ABOVE the shipping")
        print(f"  *** default of {SEND_GAP*1000:.0f} ms. Raise SEND_GAP — what we ship is")
        print("  *** stressing the panel in normal use.")
    else:
        print(f"  first trouble seen at {onset*1000:.0f} ms; the shipping "
              f"{SEND_GAP*1000:.0f} ms was clean.")
        print(f"  Margin is {(SEND_GAP-onset)*1000:.0f} ms. Keep SEND_GAP above it.")
    return onset


def main():
    bridge = connect()
    out = bridge.client.midi_out
    if not isinstance(out, ThrottledOut):
        sys.exit("output is not throttled; nothing here would mean anything")
    out._gap = SAFE_GAP
    print(f"connected: {bridge.description}")
    print(f"defaults: gap {SEND_GAP*1000:.0f} ms, floor {SYSEX_FLOOR*1000:.0f} ms")

    try:
        panel = Panel(bridge)
        rows = panel.text.split("\n")
        print(f"screen: {rows[0].rstrip()!r}")
        if is_destructive_screen(rows):
            sys.exit("the panel is on a destructive confirm prompt — refusing to probe it")

        if "--sweep-only" in sys.argv:
            sweep_gap(bridge, panel)
            return

        text_cost, graphics_cost = measure_reads(bridge)
        measure_stability(bridge, panel)
        measure_self_spacing(bridge, panel)
        if "--press" in sys.argv or "--gap" in sys.argv:
            measure_redraw(bridge, panel)
        if "--gap" in sys.argv:
            sweep_gap(bridge, panel)

        print("\n== what to do with this ==")
        print(f"  A quiet heartbeat costs one ALLTEXT ({text_cost*1000:.0f} ms), so")
        print(f"  HEARTBEAT stays a small fraction of the link at >= ~{text_cost*8:.1f} s.")
        print(f"  The GRAPHICS_MAX_AGE backstop costs a full {graphics_cost*1000:.0f} ms")
        print("  every time it fires — check it is not dominating the idle duty cycle.")
        print("  Record results in docs/RESOLUTION_NOTES.md, not in TODO.md.")
    finally:
        out._gap = SAFE_GAP
        bridge.close()


if __name__ == "__main__":
    main()
