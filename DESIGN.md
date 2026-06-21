<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# k2kremote — design

A terminal remote for the Kurzweil **K2000 / K2000R** that mirrors the hardware
LCD pixel-for-pixel and drives every front-panel button from the computer
keyboard, over MIDI SysEx.

> Status: **implemented and hardware-verified** on a real K2000R (2026-06-19/21).
> Locked decisions held: **Textual** TUI · **pixel-accurate** display
> (GETGRAPHICS) · **portable from day one**. The usable remote (mirror, keymap,
> event-driven refresh), feedback-driven name entry, a one-shot **SysEx rename
> tool**, five render modes (braille / blocks-half / blocks-quad / text / image)
> with **automatic per-page selection**, terminal-safe key alternates
> (`--alt-keys` / `--super-alt-keys` + an `m` mode leader), and a MIDI panic — all
> covered by a synthetic test suite (no hardware needed) and verified live (probes
> in `probes/`). The `psobot/k2000` SysEx library is **vendored in-tree** (MIT).
> Residual open items (physical-panel mirroring needs a human press; rig audio
> routing) are tracked in [TODO.md](TODO.md) /
> [docs/RESOLUTION_NOTES.md](docs/RESOLUTION_NOTES.md).

Protocol/RE foundation lives in the author's sibling mpc2emu project
(`docs/k2000r_midi_comms.md`, verified field notes) and the
[`psobot/k2000`](https://github.com/psobot/k2000) library (implements the full
SysEx protocol — wrap it, don't reimplement).

---

## Architecture: event-driven, never polling

This is the load-bearing decision. The K2000's old CPU **crashes/garbles the LCD
under a MIDI flood**, with a hard **120 ms floor** between SysEx messages
(documented repeatedly in the mpc2emu RE sessions). So there is **no poll loop**.
The screen is refreshed only when something could have changed:

```
keypress ─► output queue (throttled ≥120ms) ─► PANEL(button)
                                              ─► [wait ~0.5s settle] ─► GETGRAPHICS request
inbound PANEL (physical panel touched, XMIT Buttons=On) ──────────────► GETGRAPHICS request
idle heartbeat every ~2-3s (well under flood threshold) ─────────────► GETGRAPHICS request
```

One throttled output stream, **button-presses prioritized** over refresh
requests, so typing always feels responsive and the device never floods.

---

## Display: five render modes, auto-selected per page

`GETGRAPHICS` (msg `0x18`) returns the real **240×64** pixel buffer (2560 bytes,
low 6 bits/byte); `ALLTEXT` (`0x15`) returns the 8×40 characters plus a high-bit
reverse-video mask. The app renders the LCD in any of five modes (`F10` cycles;
`braille.py` does the heavy lifting):

| Mode | Mapping | Size | Notes |
|---|---|---|---|
| **braille** | 2×4 pixels / cell (Unicode braille dots) | 120×16 | densest; fits a short terminal |
| **blocks** (half) | 1×2 px / cell (`▀▄█`) | 240×16 | 1:1 LCD width, sharpest; needs a wide terminal |
| **blocks** (quad) | 2×2 px / cell (quadrant chars) | 120×32 | normal width, coarser; needs a tall terminal |
| **text** | the real ALLTEXT characters | 8×40 | crisp for menus/lists; cursor as reverse video |
| **image** | pixel-perfect colour bitmap | — | kitty/sixel/iTerm2 only (`screenshot.live_image`) |

- **auto** (`_effective_mode`): on a graphics terminal → **image** for every page;
  otherwise **text** for text-heavy pages and **braille** for graphics pages,
  decided by `_is_text_page` (below). `blocks` auto-picks half vs quad by width.
- **`_is_text_page`** distinguishes a page whose *content* is graphics (the big
  program name, an envelope) from a text page that merely has graphics *chrome*.
  It counts graphics pixels in blank, non-reverse cells — after dropping
  full-width **horizontal rules** (the divider the K2000 draws above the soft
  labels on every page), skipping (near-)**solid** cells (reverse-video
  highlights), and ignoring high-bit-flagged cells — and only calls a page
  *graphics* when those pixels **dominate the text** present. **Song mode** is a
  named exception (its channel-number strip is graphics-only) and is always
  rendered in braille on a text terminal. See `docs/RESOLUTION_NOTES.md §9`.
- The text plane is **composited** onto the graphics plane (`braille._composite`)
  because GETGRAPHICS is an overlay (it omits the ALLTEXT characters).
- `psobot/k2000`'s `image.py` decodes the pixel layer into an array — fed straight
  into the renderers; no decode work of our own.

---

## MIDI bridge: portable

```
midi_bridge.py
 ├─ standard()   : one user-selected bidirectional python-rtmidi port (Linux/Mac/Windows)
 ├─ autodetect() : probe every port for a K2000 that answers SysEx (handles
 │                 interfaces whose send/receive are different/dynamic sub-ports)
 └─ split (API)  : advanced config (`rig = "split"`): separate IN/OUT interfaces,
                   sub-ports listened to merged (`MultiIn`)
```

- Port selection at startup: list available ports, pick, remember in `config.toml`.
- `--rig auto` probes every port and binds the receive side to the interface the
  reply arrives on, so multi-port interfaces with reassigning sub-ports still work
  (`MultiIn`). (Ports the connection logic RE'd in the sibling mpc2emu project.)
- Device ID defaults to **0** (the K2000R's factory default and the value verified
  to work; broadcast 127 is *not* honoured by the tested unit). Replies are
  accepted from any id. SysEx is independent of MIDI channel.
- Timeouts **1.5–2 s** (slow-interface round-trip latency); throttle **≥120 ms**
  baked into the output queue.

### SysEx safety

Dangerous messages — **DEL (0x07), DELBANK (0x0E), MOVEBANK (0x0F)** — are
**never bound to a key**. They only ever fire behind an explicit confirm dialog.
`type=0, bank=127` DELBANK wipes all RAM; keep it unreachable.

---

## Keyboard map (Textual key events)

| Key        | K2000 button            | | Key       | K2000 button          |
|------------|-------------------------|-|-----------|-----------------------|
| F1–F6      | SoftA–SoftF (0x22–27)   | | `0`–`9`   | digits (0x00–09)      |
| ↑ ↓ ← →    | Cursor (0x10–13)        | | `+` / `-` | Plus/Minus (0x16/17)  |
| Enter      | Enter (0x0D)            | | `[` / `]` | Chan/Bank −/+ (0x14/15)|
| Esc        | Cancel (0x0B)           | | PgUp/PgDn | alpha-wheel ±1        |
| Backspace  | Clear (0x0C)            | | Ctrl+↑/↓  | alpha-wheel ±5        |
| F7 / F8    | Edit (0x20) / Exit (0x21)| | `\`       | Chan/Bank both (0x1C) |

**Mode buttons** via Alt-chords (Textual handles these portably — the reason it
was chosen over curses/urwid):

`Alt+P` Program (0x40) · `Alt+S` Setup (0x41) · `Alt+Q` Quick-Access (0x42) ·
`Alt+M` Master (0x43) · `Alt+I` MIDI (0x44) · `Alt+D` Disk (0x45) ·
`Alt+G` Song (0x46) · `Alt+E` Effects (0x47).

The **F1–F6 label bar regenerates from the live screen** (the K2000's own
soft-key labels are the bottom display row) so it always reflects the current
page.

### Button / event encoding (PANEL = 0x14)

Each press = 3 bytes `event, button, arg`:
- **event:** `08` up · `09` down · `0A` repeat · `0D` alpha-wheel.
- **arg:** wheel → `64 + clicks` (`0x46` = +6, `0x3A` = −6); else 0.
- Multiple `down`s then one `up` = auto-increment (holding `+`).

---

## Project layout

```
k2kremote/
├── k2kremote/
│   ├── midi_bridge.py   # standard + autodetect ports, throttled output queue
│   ├── refresh.py       # event-driven GETGRAPHICS scheduler (settle + heartbeat + inbound PANEL)
│   ├── braille.py       # 240x64 pixel buffer → 120x16 braille
│   ├── keymap.py        # terminal key → K2000 Button table
│   └── app.py           # Textual App: display widget, softkey bar, mode bar, status line
├── pyproject.toml       # textual, python-rtmidi, attrs ; psobot/k2000 (editable local)
├── config.toml          # saved port selection + rig mode
└── README.md
```

---

## TUI layout (≥120 cols)

```
 k2kremote · K2000R · connected · dev 127                              10:05:32
┌──────────────────────────────────────────────────────────────────────────┐
│   <240×64 LCD rendered as 120×16 braille — cursor box + curves visible>    │
└──────────────────────────────────────────────────────────────────────────┘
 [F1:…] [F2:…] [F3:…] [F4:…] [F5:…] [F6:…]      ← labels live from screen row
 [Alt+P Prog] [Alt+S Setup] [Alt+Q QA] [Alt+M Mstr] [Alt+D Disk] [Alt+E FX] …
 ↑↓←→ cursor · +/- value · Enter · Esc=Cancel · PgUp/Dn wheel · F7 Edit F8 Exit
```

---

## Phasing

1. ✅ **Core** — bridge + braille mirror + button keymap + mode switches. The
   usable remote. *(`midi_bridge.py`, `braille.py`, `keymap.py`, `refresh.py`,
   `app.py`.)*
2. ✅ **Smart alphanumeric entry** — in name/save dialogs, translate typed
   characters into the right number of alpha-wheel clicks to land on each
   character. *(`text_entry.py`; F9 overlay in `app.py`. Charset ring assumed
   ASCII pending hardware confirmation — TODO.md.)*
3. ✅ **Polish** — physical-panel mirroring (inbound PANEL), connection
   auto-recovery, optional fast text-mode (ALLTEXT) toggle. *(All in
   `refresh.py` + `app.py`; F10 toggles text mode. Inbound-PANEL echo behaviour
   pending hardware confirmation — TODO.md.)*

> **Implemented, not yet hardware-verified.** Everything above is built and
> tested synthetically (fake bridges, `--demo`). The device-touching
> assumptions are tracked in [TODO.md](TODO.md) with probes/fixes in
> [docs/RESOLUTION_NOTES.md](docs/RESOLUTION_NOTES.md).

---

## Dependencies

- `textual >= 0.80` — TUI (5 yrs mature, v8.x, ~91% issue-close rate, active
  releases through 2026; single-maintainer risk noted but low for this scope).
- `python-rtmidi >= 1.5` — cross-platform MIDI I/O.
- `attrs >= 23`.
- `psobot/k2000` — full SysEx protocol, **vendored in-tree** under `k2000/` (MIT).

## Why Textual (vs curses / urwid)

The UX hinges on reliable F1–F6, arrow, Alt+letter and Ctrl+arrow chords across
Linux/Mac/Windows terminals — exactly where raw `curses`/`urwid` are weakest
(terminal-dependent modifier detection, poor Windows support). Textual has a real
key-event model and first-class Windows support, making the keybinding spec
actually portable, which is the stated priority.
