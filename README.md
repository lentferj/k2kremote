<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
-->

# k2kremote

A terminal remote for the Kurzweil **K2000 / K2000R**: it mirrors the hardware
LCD pixel-for-pixel, drives every front-panel button from the computer keyboard,
and can rename objects in one shot — all over ordinary MIDI SysEx.

> **Author:** Jan Lentfer &lt;jan.lentfer@web.de&gt;, with AI support
> (Anthropic Claude) — see [AI assistance](#ai-assistance--human-authorship).  
> **Legal:** [DISCLAIMER.md](DISCLAIMER.md) · [LICENSE](LICENSE)

<p align="center">
  <img src="docs/img/mirror-image.png" alt="k2kremote mirroring the Kurzweil K2000 LCD, pixel-perfect in colour" width="80%">
</p>

---

## ⚠️ Use at your own risk — back up first

k2kremote is provided **as is, with absolutely no warranty and no liability** for
data loss or **hardware damage**. You assume all risk.

**During development and testing, the K2000 was occasionally driven into a
hardware lockup that could only be cleared by a _factory reset_ of the
instrument** (which can erase user data). **Before using k2kremote with real
hardware, make complete, current backups of everything on your K2000** — RAM
Programs, Setups, Samples / Keymaps, Effects, Master / MIDI settings, and any
SCSI media. Full terms: [DISCLAIMER.md](DISCLAIMER.md).

---

## AI assistance & human authorship

k2kremote was built by its human author, **Jan Lentfer**, together with
Anthropic's **Claude**. The **ideas, the project vision, and every feature** came
from the human author; Claude assisted with **writing the code** and the docs.
Crucially, the **reverse engineering rests on hands-on human work** — all of the
MIDI protocol behaviour this depends on (the SysEx flood floor, the device-id
quirk, the LCD layout, the naming model, the rename behaviour) was verified on a
real K2000R. Full account in [DISCLAIMER.md](DISCLAIMER.md).

---

## What it does

- **Mirrors the LCD** live, in several render styles (braille / blocks / text and
  a pixel-perfect colour image on graphics terminals).
- **Drives the front panel** — every button and the alpha wheel, from your
  keyboard. The F1–F6 labels are **live** (they mirror the K2000's soft keys).
- **Feedback-driven name entry** (`F9`) that types a name into the open dialog,
  reading each position back to get the case right.
- **One-shot SysEx rename tool** (`Ctrl+o`) for any object by type + id — no
  dialling letters; characters past the panel's 16-char field are flagged.
- **Event-driven refresh** (never polls), throttled output, and automatic
  pausing around heavy disk operations to protect the K2000's CPU.
- **PNG screenshots** of the LCD (`F12`) and a **MIDI panic** (`Alt+x`).

All testing was on a real K2000R; the protocol reverse-engineering lives in the
author's sibling **mpc2emu** project (`docs/k2000r_midi_comms.md`).

---

## Render modes

`F10` cycles **auto → braille → blocks → text → image**. The K2000 LCD is a
240 × 64 pixel panel; each mode trades terminal size against fidelity.

**braille** — each character cell packs **2 × 4** pixels as Unicode braille dots,
so the whole 240 × 64 LCD fits in a compact **120 × 16** grid. The densest mode —
fits a small/short terminal — at the cost of the little dot gaps between cells.

![braille mode](docs/img/mirror-braille.png)

**blocks** — solid block characters (no dot gaps), so text reads cleaner. It comes
in two flavours and k2kremote picks automatically based on the window width
(shown in the title bar as `blocks/half` or `blocks/quad`):

- **half-block** (`▀ ▄ █`): each cell is **1 pixel wide × 2 tall**, so the mirror
  is **240 columns** — a 1 : 1 match for the LCD width that keeps its wide
  3.75 : 1 aspect ratio and is the **sharpest** of the text modes. Needs a wide
  (~240-column) terminal.

  ![blocks: half-block mode](docs/img/mirror-blocks-half.png)

- **quadrant** (`▘ ▚ ▛ …`): each cell is **2 × 2 pixels**, so it is only **120
  columns** and fits a normal-width terminal — at the cost of half the horizontal
  detail (and it is twice as tall as braille, ~32 rows).

  ![blocks: quadrant mode](docs/img/mirror-blocks.png)

**text** — the K2000's real **8 × 40** characters straight from ALLTEXT, with the
cursor / selection as reverse video. Crisp and exact for menus, lists and the
Disk pages.

![text mode](docs/img/mirror-text.png)

**image** — a **pixel-perfect colour LCD** (see the top of this page), only on
graphics-capable terminals (kitty / WezTerm / sixel / iTerm2).

**auto** — picks per page: the image where the terminal supports it, otherwise
braille for graphics pages and text for text-heavy pages. (Song mode is forced to
braille even on a text terminal, because its channel-number strip is drawn as
graphics that plain text can't show.)

---

## The rename tool (`Ctrl+o`)

Pick an object **type**, enter its **id**, see the **current name**, type a **new
name**, and it is set with a single SysEx `CHANGE` message — instead of dialling
each letter on the panel. It only ever *renames* (never relocates or deletes).
Characters beyond the K2000's 16-character display field are shown in **orange**
(they are stored, but won't be visible on the panel):

<p align="center">
  <img src="docs/img/rename-tool.svg" alt="The Ctrl+o rename tool, with overflow characters in orange" width="70%">
</p>

> The instrument applies the rename **from Program mode**, not while the object is
> open in its editor (the editor's own buffer wins there). For a Program, the tool
> re-selects the id afterwards so the panel and the mirror repaint with the new
> name.

---

## Installation — step by step

New to Python or the terminal? Follow these in order. The commands are written
for Linux/macOS; on Windows use the matching steps noted below.

**1. Install the prerequisites**

- **Python 3.11 or newer** — check with `python3 --version`. Install from your
  package manager or from <https://www.python.org/downloads/>.
- **Git** — to download this project (or download the ZIP from the project page
  and skip the `git clone`).
- A **MIDI interface** connected to the K2000's MIDI IN **and** OUT (only needed
  when you connect to real hardware — the `--demo` mode needs none).

**2. Download k2kremote**

```bash
git clone https://github.com/lentferj/k2kremote.git
cd k2kremote
```

**3. Create an isolated environment and install it**

```bash
python3 -m venv .venv                 # create a private virtual environment
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install --upgrade pip

pip install -e .                      # k2kremote + all its dependencies

# optional — pixel-perfect "image" render mode (needs a graphics terminal):
pip install -e ".[image]"
```

The Kurzweil SysEx protocol library (psobot/k2000, MIT) is **vendored in-tree**
(see [`k2000/`](k2000)), so there is **no separate manual or git install** — one
`pip install -e .` pulls everything from PyPI and you are ready to go.

> On Debian/Ubuntu you can save build time by reusing system packages for the
> heavier dependencies: `sudo apt install python3-rtmidi python3-numpy`, then
> create the venv with `python3 -m venv --system-site-packages .venv` before
> `pip install -e .`.

**4. Run it without any hardware (recommended first step)**

```bash
python -m k2kremote.app --demo        # explore the UI; press F10 to cycle modes
python -m k2kremote.app --long-help   # full prose manual: setup, controls, safety
```

`Ctrl+c` quits. When that works, connect your K2000 (next section).

> Whenever you open a new terminal, re-activate the environment first with
> `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`) before running
> `python -m k2kremote.app`.

### Terminals / consoles

The **text / braille / blocks** modes work in any modern terminal with a good
Unicode font (braille + block elements). The **image** mode needs an
inline-graphics protocol (kitty / sixel / iTerm2).

**Keep it simple.** A plain, "dumb" terminal that doesn't steal F-keys or Alt
shortcuts is the most trouble-free choice — then you never need `--alt-keys` at
all. Recommended simple terminals:

| Platform | Simple terminals | Image mode (graphics) |
|---|---|---|
| **Linux** | `xterm`†, [`st`](https://st.suckless.org/), [`alacritty`](https://alacritty.org/) | **kitty** (best), or WezTerm / any sixel terminal (`--image-protocol sixel`) |
| **macOS** | `alacritty`, `kitty` | kitty or iTerm2 |
| **Windows** | `alacritty`, Windows Terminal | Windows Terminal (`--image-protocol sixel`) |

> **† xterm and the Alt-chords.** xterm by default does *not* send `Alt+letter`
> as an escape sequence, so the `Alt+p/s/…` mode chords won't reach the app. Turn
> it on:
> ```bash
> xterm -fa "Monospace" -fs 12 -xrm 'XTerm*metaSendsEscape: true'
> ```
> (or put `XTerm*metaSendsEscape: true` in `~/.Xresources`). Alternatively, just
> run with **`--super-alt-keys`** and use the `m` mode leader instead — no Alt
> needed.

Rich GUI terminals (LXTerminal, GNOME Terminal, Konsole, …) often grab the F-keys
and `Alt+letter` for their own menus — that's what `--alt-keys` /
`--super-alt-keys` work around (and many let you hide the menu bar to free Alt).

> **Tested environment:** development and testing were done **only on Debian
> "Bookworm" with kitty 0.47.4**. The software has **not been tested on Windows or
> macOS**, nor on other terminals — those paths may need adjustment. Reports
> welcome.

### Other things you can run (no hardware needed)

With the environment active (`source .venv/bin/activate`):

```bash
python -m k2kremote.braille    # braille renderer self-test
python -m pytest               # the test suite — all synthetic, never opens MIDI
```

### With a K2000 attached

```bash
python -m k2kremote.app                  # first bidirectional MIDI port
python -m k2kremote.app --rig auto       # probe every port for the K2000
python -m k2kremote.app --port "My Port" # an exact port by name
python -m k2kremote.midi_bridge ports    # list MIDI ports
python -m k2kremote.midi_bridge probe    # auto-probe and report what answered

# Remember the selection in config.toml, then just run with no args next time
python -m k2kremote.app --port "My Port" --save-config
python -m k2kremote.app                  # reuses the saved port/rig
```

Selection precedence: an explicit `--port` / `--rig auto` overrides the config
file, which overrides the first-bidirectional-port fallback.

---

## Command-line options

Run `python -m k2kremote.app --help` for this list, or `--long-help` for a full
prose manual (setup, terminals, controls, safety).

**Connection**

| Option | Default | Description |
|---|---|---|
| `--rig {auto,standard}` | `standard` | How to find the K2000: `standard` uses one bidirectional MIDI port; `auto` probes every port for a K2000 that answers SysEx. |
| `--port NAME` | — | Exact MIDI port name to use (implies `--rig standard`). List names with `python -m k2kremote.midi_bridge ports`. |
| `--config FILE` | `config.toml` | TOML file remembering the port/rig selection (ignored if absent). |
| `--save-config` | off | Write the effective port/rig selection to `--config`, so later runs need no flags. |
| `-i, --sysex-interval MS` | `500` | Minimum delay between outgoing SysEx messages (like `amidi -i`). Lower = snappier UI, but more risk of garbling the K2000's LCD. |

**Display**

| Option | Default | Description |
|---|---|---|
| `--text` | off (auto) | Start in fast text (ALLTEXT) mode instead of auto. Cycle modes live with `F10`. |
| `--image-protocol {auto,tgp,sixel,halfcell}` | `auto` | Terminal graphics protocol for image mode. Force `tgp` (kitty), `sixel` (WezTerm/Windows Terminal), or `halfcell` (universal text fallback). |
| `--image-cols N` | `120` | Cap the pixel image at N columns so it isn't huge on wide monitors (height follows the LCD aspect). |
| `--model NAME` | `K2000R` | Model label shown in the title bar. |

**Behaviour**

| Option | Default | Description |
|---|---|---|
| `--settle MS` | `350` | Delay after a keypress before reading the redrawn LCD. Lower = snappier; too low may read the screen mid-redraw. |
| `--alt-keys` | off | Show terminal-safe key alternates (`a`–`h` soft keys, `Ctrl+e/x/n/v/g`) in the legend and soft-key bar — for terminals that intercept the F-keys (Alt-chords stay). |
| `--super-alt-keys` | off | Everything `--alt-keys` does, plus move the mode buttons to the `m` leader (press `m`, then `p/s/q/m/i/d/g/e`) — for terminals that also grab the `Alt+letter` mode chords. |
| `--manual-refresh` | off | Disable the periodic heartbeat entirely; refresh only on front-panel events and `Ctrl+r`. The strongest guard against polling the K2000 during a delete/save (a poll landing mid-rewrite can lock up the unit). |
| `--demo` | off | Run against a static synthetic frame with no MIDI — try the UI and render modes without any hardware. |
| `--long-help` | — | Print the full prose user manual and exit. |
| `-h, --help` | — | Print the option summary and exit. |

---

## Controls

Your keyboard drives the K2000's front panel. The **F1–F6 labels are live** —
they mirror the K2000's own soft-key row for the current page.

### Front panel

| Key | K2000 | | Key | K2000 |
|---|---|---|---|---|
| `F1`–`F6` | Soft A–F | | `0`–`9` | digits |
| `F7` / `F8` | Edit / Exit | | `+`/`-` or `PgUp`/`PgDn` | value Plus / Minus |
| `↑ ↓ ← →` | cursor | | `[` / `]` | Chan/Bank − / + |
| `Enter` | Enter | | `Ctrl+↑` / `Ctrl+↓` | alpha-wheel ±1 |
| `Esc` | **Exit** (back out) | | `Ctrl+PgUp`/`Ctrl+PgDn` | alpha-wheel ±5 |
| `Backspace` | Clear | | `Delete` | Cancel |

### Mode buttons (Alt-chords)

| Key | Mode | | Key | Mode |
|---|---|---|---|---|
| `Alt+p` | Program | | `Alt+i` | MIDI |
| `Alt+s` | Setup | | `Alt+d` | Disk |
| `Alt+q` | Quick-Access | | `Alt+g` | Song |
| `Alt+m` | Master | | `Alt+e` | Effects |

> **GTK terminals (e.g. LXTerminal) grab `Alt+letter` for their menu bar**, so
> the mode chords never reach the app. Run with **`--super-alt-keys`** and the
> modes move to a **leader key**: press **`m`**, then the mode's lowercase letter
> (`m` then `d` = Disk). Plain keys, no terminal intercepts them. (Plain
> `--alt-keys` keeps the Alt-chords and only remaps the F-keys.)

### App

| Key | Action |
|---|---|
| `F9` | Name-entry overlay — type a name, `Enter` sends it (feedback-driven), `Esc` cancels |
| `Ctrl+o` | **Rename object** tool — type + id + new name → one SysEx message |
| `F10` | Cycle render mode: **auto → braille → blocks → text → image** |
| `F12` | Save the current screen as a PNG (`k2kremote-<timestamp>.png`) |
| `Alt+x` | **Panic** — MIDI all-notes-off on all 16 channels |
| `Alt+End` | In a name dialog: jump the cursor to the end of the name |
| `p` | **Pause / resume** the mirror (no MIDI traffic) — the universal resume key: lifts a manual, disk-op, or confirm-screen pause |
| `Ctrl+r` | **Force** a full screen refresh now (works even while paused; also releases a confirm-screen pause) |
| `Ctrl+c` | Quit |

> **⚠ Disk & delete operations.** The K2000's CPU can crash under MIDI traffic
> while it is busy — a SCSI **Load**/**Save**, or rewriting its object table for a
> **delete**. A screen poll landing in that window can **lock up** the unit (needs
> a factory reset to clear). Guards: (1) k2kremote **auto-pauses** when you press a
> soft key whose label is a heavy op (Load/Save/Move/Format/…); (2) it **auto-pauses
> the mirror entirely** when a **confirmation prompt** is on screen — a bare
> **Yes/No** pair, or text "are you sure" — since the next press commits the
> rewrite; earlier idle screens (the delete *selection* list, object menus) stay
> live so you can navigate them; (3) **`--manual-refresh`** drops the periodic poll
> entirely. All three show one **`⏸ PAUSED · <reason>`** badge (manual / disk op /
> confirm) and all resume with **`p`** (the confirm pause also releases on
> `Ctrl+r`). **Best-effort caveat:** the auto-pause depends on reading the confirm
> screen *before* you press Yes, so for guaranteed safety press **`p`** yourself
> before any delete/save — that stops all MIDI regardless of what's on screen.

### If your terminal eats F-keys

Some terminals intercept function keys. Every F-key function has a terminal-safe
alternate:

| F-key | Alternate | |
|---|---|---|
| `F1`–`F6` (soft A–F) | `a` `s` `d` `f` `g` `h` | home-row run (QWERTY/QWERTZ) |
| `F7` / `F8` (Edit/Exit) | `Ctrl+e` / `Ctrl+x` | |
| `F9` (name entry) | `Ctrl+n` | |
| `F10` (view mode) | `Ctrl+v` | |
| `F12` (PNG) | `Ctrl+g` | |

> **`--alt-keys`** shows these alternates (`[a:Octav-]`, `Ctrl+n name`, …) in the
> legend and soft-key bar instead of the F-keys, so the hints match what works in
> your terminal. The Alt+letter mode chords are left alone. If your terminal also
> grabs Alt (see the mode-buttons note above), use **`--super-alt-keys`**, which
> additionally moves the modes to the `m` leader.
>
> The key-hint legend stays visible as you navigate (it is no longer hidden by
> the label of the last key you pressed).

> **Safety:** the destructive object commands (DEL / DELBANK / MOVEBANK) are
> deliberately **not bound to any key** — they can wipe RAM and must never fire
> from a keystroke.

---

## Modules

| Module | Role |
|---|---|
| `k2kremote/midi_bridge.py` | Portable MIDI transport — a single bidirectional port (`standard`) or auto-probe (`autodetect`), throttled output, device-id handling, and the SysEx rename/lookup. |
| `k2kremote/braille.py` | Renders the 240×64 LCD pixel buffer as a braille / blocks / half-block mirror. |
| `k2kremote/keymap.py` | Maps Textual key events onto K2000 front-panel buttons / alpha-wheel turns. |
| `k2kremote/refresh.py` | Event-driven (never-poll) refresh scheduler: press → settle → refresh, plus an idle heartbeat, on one throttled output stream. |
| `k2kremote/text_entry.py` | Feedback-driven name entry — types a name into the open dialog, reading each position back to fix case. |
| `k2kremote/name_cursor.py` | Software model of the name-edit cursor (the K2000 never exposes it over MIDI), drawn as the underline. |
| `k2kremote/screenshot.py` | Saves a captured screen as a high-fidelity PNG (reuses psobot/k2000's `image`). |
| `k2kremote/app.py` | The Textual TUI: the LCD mirror, live F1–F6 soft bar, mode/status lines, name entry, the rename tool, render-mode cycling. |

See [DESIGN.md](DESIGN.md) for the architecture and [TODO.md](TODO.md) for open
items.

---

## Requirements

All installed automatically by `pip install -e .`:

- Python 3.11 or later
- [`textual`](https://pypi.org/project/textual/) — the TUI
- [`python-rtmidi`](https://pypi.org/project/python-rtmidi/) — cross-platform MIDI I/O
- [`numpy`](https://pypi.org/project/numpy/)
- [`attrs`](https://pypi.org/project/attrs/)
- [`pillow`](https://pypi.org/project/pillow/)
- the [psobot/k2000](https://github.com/psobot/k2000) SysEx protocol library — **vendored in-tree** ([`k2000/`](k2000), MIT), no separate install
- _optional:_ [`textual-image`](https://pypi.org/project/textual-image/) for pixel-perfect image mode (`pip install -e ".[image]"`)

---

## License and Third-Party Sources

Released under the **GNU General Public License v2.0 or later
(GPL-2.0-or-later)** — see [`LICENSE`](LICENSE).

The Kurzweil SysEx protocol library is **vendored** under [`k2000/`](k2000)
under its own MIT license (kept intact in [`k2000/LICENSE`](k2000/LICENSE)); the
rest of the project is original GPL-2.0-or-later work. MIT is compatible with the
GPL, and the MIT terms continue to apply to the files in `k2000/`.

| File / dir | Reference | License | Author |
|---|---|---|---|
| `k2000/` | [psobot/k2000](https://github.com/psobot/k2000) — the full SysEx protocol library, **vendored verbatim** so the app runs out of the box | MIT | Peter Sobot |
| `midi_bridge.py` | Connection plumbing (throttled output, merged multi-input, connect logic) ported from the author's sibling mpc2emu project; MIDI quirks RE'd in its `docs/k2000r_midi_comms.md`, verified on real K2000R hardware | GPL-2.0-or-later | Original code |
| `braille.py` | Original work — renders the K2000's LCD pixel buffer | GPL-2.0-or-later | Original code |
| `text_entry.py` / `name_cursor.py` | Naming model from the Kurzweil K2vx manual; button codes from the vendored `k2000.definitions.Button` (MIT) | GPL-2.0-or-later | Original code |

---

*Kurzweil is a trademark of Young Chang Co. Ltd. All other trademarks are
property of their respective owners. This project is not affiliated with or
endorsed by Young Chang / Kurzweil.*
