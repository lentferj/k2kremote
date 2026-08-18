# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.
# Original work. No third-party source code used.
# Built on Textual (MIT, Textualize) and wraps psobot/k2000 (MIT, Peter Sobot)
# via k2kremote.midi_bridge — both runtime dependencies, not copied.
#
# k2kremote is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# k2kremote is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Textual TUI: pixel-accurate K2000 mirror + front-panel control.

Run it::

    python -m k2kremote.app                # first bidirectional MIDI port
    python -m k2kremote.app --rig jan       # Jan's split send/receive rig
    python -m k2kremote.app --port "My Port"
    python -m k2kremote.app --demo          # no hardware: a static frame

A keypress resolves through :mod:`k2kremote.keymap` and is handed to the
:class:`~k2kremote.refresh.RefreshWorker`, which serializes it onto the single
throttled output stream and schedules the screen refresh. Frames come back on
the worker thread and are marshalled onto the UI with ``call_from_thread``.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Optional, Tuple

import numpy as np
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Select, Static

from k2000.definitions import Button, ObjectType

from k2kremote import braille, keymap, name_cursor, screenshot, text_entry
from k2kremote.name_cursor import NameCursor
from k2kremote.refresh import Frame, RefreshWorker

try:  # optional: pixel-perfect image mode via kitty/sixel (textual-image)
    import textual_image.widget as _ti_widget
    _HAS_IMAGE = True
except Exception:  # pragma: no cover - depends on optional dep
    _ti_widget = None
    _HAS_IMAGE = False


def _image_widget_class(protocol: str):
    """Return the textual-image widget class for ``protocol`` ('auto' picks the
    best detected at import; 'tgp'/'sixel'/'halfcell' force one)."""
    if not _HAS_IMAGE:
        return None
    return {
        "tgp": _ti_widget.TGPImage,
        "sixel": _ti_widget.SixelImage,
        "halfcell": _ti_widget.HalfcellImage,
    }.get(protocol, _ti_widget.Image)


def _detected_image_protocol() -> str:
    """Name of the renderer textual-image auto-detected at import (tgp/sixel/…)."""
    try:
        import textual_image.renderable as r
        return r.Image.__module__.rsplit(".", 1)[-1]
    except Exception:  # pragma: no cover
        return "?"


_BAR_SEP = " · "  # block separator in the legend / mode bar


def wrap_blocks(blocks: List[str], width: int, sep: str = _BAR_SEP) -> str:
    """Pack ``blocks`` into lines no wider than ``width``, joined by ``sep``.

    Breaks happen only *between* blocks, never inside one, so a label such as
    "Alt+X panic" or "[F5:Format]" is never split across a line. (A non-breaking
    space inside a block isn't enough — Rich/Textual still treats it as a wrap
    point — so we fold here and render the result with wrapping disabled.)
    A block longer than ``width`` simply occupies its own line.
    """
    lines: List[str] = []
    current = ""
    for block in blocks:
        candidate = block if not current else current + sep + block
        if width and len(candidate) > width and current:
            lines.append(current)
            current = block
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def align_blocks(blocks: List[str], span: int, width: int, offset: int = 0,
                 centres: Optional[List[Optional[float]]] = None) -> Optional[str]:
    """Lay ``blocks`` out so each sits under its zone of an ``span``-wide mirror.

    The K2000 divides its 40-column bottom row into six equal soft-key zones, and
    :func:`soft_labels` reads them back by which zone a word's centre falls in.
    This is the inverse: block *i* is centred in zone *i* of the LCD **as
    currently drawn**, so the ``[F#:label]`` strip lines up under the labels on
    screen instead of being packed against the left margin. ``span`` is the width
    of the rendered mirror in cells (40 in text mode, 120 for braille, up to 240
    for half-blocks, whatever the pixel image occupies), and ``offset`` shifts
    everything right — the image is centred in its box.

    Returns ``None`` when the blocks cannot be placed under their zones without
    overlapping, or would run past ``width``; the caller then falls back to plain
    packing. That is the normal outcome in 40-column text mode, where six
    ``[F#:label]`` blocks simply do not fit under 40 columns of LCD.
    """
    if span <= 0 or len(blocks) != _SOFT_KEYS:
        return None
    if sum(len(b) for b in blocks) + len(blocks) - 1 > span:
        return None
    line = ""
    for i, block in enumerate(blocks):
        # Prefer the label's real position on the K2000's row; fall back to the
        # centre of the nominal zone when that key carries no label.
        frac = None if centres is None or i >= len(centres) else centres[i]
        if frac is None:
            frac = (i + 0.5) / _SOFT_KEYS
        pos = offset + int(round(frac * span)) - len(block) // 2
        pos = max(pos, offset)                 # never hang off the mirror's left
        if line:
            pos = max(pos, len(line) + 1)      # never butt two blocks together
        if width and pos + len(block) > width:
            return None
        line = line.ljust(pos) + block
    return line


def wrap_groups(groups, width: int, sep: str = _BAR_SEP) -> str:
    """Fold ``groups`` of blocks, preferring to break *between* groups.

    :func:`wrap_blocks` packs greedily, which is fine until it splits a run that
    reads as a unit: at 150 columns it fitted "F7 Edit" onto the end of the
    navigation line and began the next with "F8 Exit", and F7 was duly reported
    missing. A group that will not fit on the current line starts a new one
    instead of being broken across the fold.

    A group too wide for a whole line still wraps inside itself — better a split
    run than a clipped one — and groups keep sharing a line whenever they fit,
    so nothing gets taller than it needs to be.
    """
    lines: List[str] = []
    current = ""
    for group in groups:
        block = sep.join(group)
        candidate = block if not current else current + sep + block
        if width and len(candidate) > width and current:
            lines.append(current)
            current = ""
            candidate = block
        if width and len(candidate) > width:
            # This group alone overflows: fall back to packing it block by block.
            packed = wrap_blocks(list(group), width, sep).split("\n")
            lines.extend(packed[:-1])
            current = packed[-1]
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


# The bottom text row carries the K2000's own soft-key labels.
_SOFT_KEYS = 6
_TEXT_COLS = 40  # 240 px / 6 px per char

# F1-F6 soft keys -> label index, for spotting heavy disk operations.
_SOFT_INDEX = {
    Button.SoftA: 0, Button.SoftB: 1, Button.SoftC: 2,
    Button.SoftD: 3, Button.SoftE: 4, Button.SoftF: 5,
}
# Soft-key labels that start a long, CPU-pegging K2000/SCSI operation. Polling
# the device while one runs can crash it, so we auto-pause when one is pressed.
_HEAVY_OPS = ("load", "save", "move", "copy", "format", "backup",
              "store", "erase", "scan", "build", "macro")


def soft_labels(text_rows: List[str]) -> List[str]:
    """Split the bottom screen row into the six F1-F6 soft-key labels.

    Assigns each whole **word** to the soft key its centre column falls under
    (40 cols / 6 keys), so a label is never cut in half across the boundary
    (e.g. "Format" no longer splits into "Forma" + "t").
    """
    bottom = (text_rows[-1] if text_rows else "").ljust(_TEXT_COLS)[:_TEXT_COLS]
    labels = [""] * _SOFT_KEYS
    for match in re.finditer(r"\S+", bottom):
        centre = (match.start() + match.end() - 1) / 2
        key = min(_SOFT_KEYS - 1, int(centre * _SOFT_KEYS / _TEXT_COLS))
        labels[key] = (labels[key] + " " + match.group()).strip()
    return labels


# --- window sizing ----------------------------------------------------------
# Chrome around the mirror, in rows: title bar, soft-key strip, mode bar, the
# two-line key legend, and the status line.
_CHROME_ROWS = 1 + 1 + 1 + 2 + 1


def optimal_size() -> Tuple[int, int]:
    """The smallest terminal that shows the mirror without compromise, in cells.

    Width is set by the mirror itself: below :data:`braille.BRAILLE_COLS` the app
    puts up a "widen the window" hint, because the LCD can no longer be shown
    1:1. Height is that chrome plus the tallest of the everyday renderers —
    braille at 16 rows; the pixel image works out shorter, and the 32-row
    half-block mode is a deliberate wide-screen choice, not the default.

    A couple of columns of slack keeps the centred pixel image off the edges.
    """
    return braille.BRAILLE_COLS + 4, _CHROME_ROWS + braille.BRAILLE_ROWS + 1


def _size_state_path() -> "pathlib.Path":
    """Where the last-used window size is cached (XDG, falling back to ~/.cache)."""
    import os
    import pathlib

    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return pathlib.Path(base) / "k2kremote" / "window-size"


def remembered_size() -> Optional[Tuple[int, int]]:
    """The size the app was last closed at, or None if unknown/implausible.

    Anything narrower than the mirror is rejected rather than remembered — a
    window that was accidentally dragged tiny should not become the new normal.
    """
    try:
        raw = _size_state_path().read_text().split()
        cols, rows = int(raw[0]), int(raw[1])
    except Exception:
        return None
    least_cols, least_rows = optimal_size()
    if cols < braille.BRAILLE_COLS or rows < _CHROME_ROWS + 4:
        return None
    return cols, max(rows, min(least_rows, rows))


def remember_size(cols: int, rows: int) -> None:
    """Cache the window size for the next launch; never raise."""
    try:
        path = _size_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{cols} {rows}\n")
    except Exception:
        pass


def startup_size() -> Tuple[int, int]:
    """What to open the window at: last used if sane, else the optimum."""
    return remembered_size() or optimal_size()


def soft_label_centres(text_rows: List[str]) -> List[Optional[float]]:
    """Where each soft-key label actually sits, as a fraction of the row width.

    :func:`soft_labels` only says *which* key a word belongs to. For lining the
    ``[F#:label]`` strip up under the mirror that is not enough: the K2000 does
    not centre its labels in their sixths — ``Octav- Octav+ Panic  View   Chan-
    Chan+`` puts each word wherever it likes — so centring our blocks in the
    nominal zones leaves them visibly off. This returns the centre column of the
    label the same word-assignment produced, normalised to 0..1, or ``None`` for
    a key with no label (which falls back to its zone centre).
    """
    bottom = (text_rows[-1] if text_rows else "").ljust(_TEXT_COLS)[:_TEXT_COLS]
    bounds: List[Optional[List[int]]] = [None] * _SOFT_KEYS
    for match in re.finditer(r"\S+", bottom):
        centre = (match.start() + match.end() - 1) / 2
        key = min(_SOFT_KEYS - 1, int(centre * _SOFT_KEYS / _TEXT_COLS))
        span = bounds[key]
        if span is None:
            bounds[key] = [match.start(), match.end()]
        else:  # a multi-word label ("Delete Insert" style) spans both
            span[0], span[1] = min(span[0], match.start()), max(span[1], match.end())
    return [None if b is None else ((b[0] + b[1] - 1) / 2) / _TEXT_COLS
            for b in bounds]


def is_name_dialog(text_rows: List[str]) -> bool:
    """True when the K2000 is showing its naming dialog.

    The signature is the soft-key row ``Delete Insert <<< >>> OK Cancel`` (the
    page where F9 / Ctrl+N types a name). Used to surface that hint, which is
    otherwise easy to miss.
    """
    labels = {label.lower() for label in soft_labels(text_rows)}
    return "delete" in labels and "insert" in labels


_TEXT_ROWS = 8  # the K2000 LCD text layer is 8 rows x 40 cols
_CELL_W = 6     # px per character column
_CELL_H = 8     # px per character row


def render_text_grid(text_rows: List[str]) -> str:
    """Render the ALLTEXT layer as a plain 8x40 character grid."""
    rows = list(text_rows or [])
    rows = (rows + [""] * _TEXT_ROWS)[:_TEXT_ROWS]
    return "\n".join(row.ljust(_TEXT_COLS)[:_TEXT_COLS] for row in rows)


# Graphics-only pixels (in blank text cells, middle rows) above which a page is
# treated as graphics-rich — an algorithm diagram / envelope / big name — rather
# than text. A cursor highlight sits over text cells, so it doesn't count.
_GRAPHICS_PAGE_PIXELS = 64
# A blank cell filled to at least this many of its 48 (6×8) pixels is a *solid*
# block — a reverse-video highlight (a selected value field, a status bar), not
# graphics. Real graphics (glyph strokes, lines, curves) only partially fill a
# cell. Solid blank cells are skipped so list/Disk pages stay text.
_SOLID_CELL_PIXELS = 44
# A pixel-row this full (of the 240-px width) is a horizontal rule — the divider
# line the K2000 draws above the soft labels, or a full-width reverse bar — not
# page graphics; it is dropped before the per-cell graphics count.
_RULE_ROW_FRACTION = 0.8
# To count as a *graphics* page, the graphics must dominate the text: at least
# this many graphics pixels per text cell present in the middle rows. A big
# program name / envelope has hundreds of px per (near-zero) text cell; a box
# around a Setup/list table has only a few px per cell of a text-heavy page.
_GRAPHICS_PER_TEXT_CELL = 10


def _is_song_page(text_rows: List[str]) -> bool:
    """True on the Song-mode pages. They draw the per-track **channel-number
    strip** (1 2 3 … 16) as graphics only — it is absent from ALLTEXT — so auto
    must render them in braille; in plain text the numbers would be invisible."""
    return bool(text_rows) and text_rows[0].lstrip().startswith("SongMode")


def _is_text_page(frame: Frame) -> bool:
    """True if the page is readable as plain text (no graphics-only shapes).

    A page is *graphics* (→ braille/blocks) when the graphics plane has real
    content — lines, arrowheads, envelope curves, the big program name — sitting
    in **blank** text cells. Disk/list pages only put **reverse-video** cursors /
    highlights over the text (a selected value field, a status bar). Those are
    *solid* filled blocks, so we skip any blank cell that is reverse-flagged
    (``frame``'s high-bit mask) **or** (near-)solid — a highlight's blank padding
    fills the graphics plane but is not graphics. We also drop **full-width
    horizontal rules** (the divider line the K2000 draws above the soft labels on
    every page). Finally, a Setup/list page draws a thin **box outline** around a
    text table — non-solid, non-full-width chrome that survives those filters — so
    the final test is **dominance**: a page counts as graphics only when the
    remaining graphics outweigh the text (lots of graphics, little text = the big
    program name / an envelope; a little chrome around a lot of text = a list).
    """
    if frame.pixels is None:
        return True
    arr = np.array(braille._fit(braille._normalize(frame.pixels)))  # (64, 240) bool
    # Drop (near-)full-width horizontal rules: the K2000 draws a divider line
    # above the soft-label bar on every page (and full-width reverse bars). Those
    # are chrome, not page graphics, and would otherwise count in every blank cell.
    arr[arr.sum(axis=1) >= int(_RULE_ROW_FRACTION * arr.shape[1])] = False
    grid = render_text_grid(frame.text_rows).split("\n")
    reverse = frame.reverse or []
    graphics_only = 0
    text_cells = 0
    for r in range(1, _TEXT_ROWS - 1):  # middle rows (skip status bar / soft labels)
        line = grid[r] if r < len(grid) else ""
        rev = reverse[r] if r < len(reverse) else ""
        band = arr[r * _CELL_H:(r + 1) * _CELL_H]
        for c in range(_TEXT_COLS):
            if (line[c] if c < len(line) else " ") != " ":
                text_cells += 1
                continue  # the cell holds text
            if c < len(rev) and rev[c] == "1":
                continue  # reverse-video highlight (high-bit flagged)
            cell = int(band[:, c * _CELL_W:(c + 1) * _CELL_W].sum())
            if cell >= _SOLID_CELL_PIXELS:
                continue  # a solid block = highlight/inverse bar, not graphics
            graphics_only += cell
    if graphics_only < _GRAPHICS_PAGE_PIXELS:
        return True  # barely any graphics -> text
    # There is graphics, but on a text-heavy page it is chrome (a box around a
    # table, dividers) rather than content. Only call it a graphics page when the
    # graphics *dominate* the text — true for the big program name / an envelope
    # (lots of graphics, ~no text), false for Setup/list pages (a little chrome
    # around a lot of text).
    return graphics_only < _GRAPHICS_PER_TEXT_CELL * text_cells


def render_text_overlay(pixels, text_rows: List[str], reverse_rows=None):
    """ALLTEXT as real characters, reverse-video where the graphics plane fills.

    That makes the cursor / selection / status bar / soft-key labels visible
    (they live in the graphics plane as inverted blocks) while keeping the text
    perfectly readable — unlike braille, which is exact but hard to read at this
    tiny font size. ``reverse_rows`` is a per-cell reverse-video mask: any cells
    the device flags, plus the **software-tracked name-edit cursor** (which the
    K2000 exposes in neither the text nor the graphics plane — see
    :mod:`k2kremote.name_cursor`), so the cursor is highlighted even though no
    device reply contains it. Returns a Rich ``Text``.
    """

    grid = render_text_grid(text_rows).split("\n")
    arr = None
    if pixels is not None:
        arr = braille._fit(braille._normalize(pixels))  # (64, 240) bool

    out = Text()
    for r, line in enumerate(grid):
        attr = reverse_rows[r] if reverse_rows and r < len(reverse_rows) else ""
        for c, ch in enumerate(line):
            highlighted = (c < len(attr) and attr[c] == "1") or (
                arr is not None and bool(
                    arr[r * _CELL_H:(r + 1) * _CELL_H,
                        c * _CELL_W:(c + 1) * _CELL_W].mean() > 0.5
                )
            )
            out.append(ch, style="reverse" if highlighted else "")
        if r < len(grid) - 1:
            out.append("\n")
    return out


def apply_cursor_underline(pixels, reverse_rows):
    """Draw each reverse-flagged cell into the pixel buffer as an underline.

    ``reverse_rows`` is the merged reverse-video mask — device-reported cells
    plus the **software-tracked name-edit cursor** (which the K2000 exposes in
    neither plane; see :mod:`k2kremote.name_cursor`). We bake the bottom
    pixel-row of each flagged cell on, so every graphics renderer (braille /
    blocks / image) shows it. This is idempotent where the graphics plane already
    fills the cell (soft labels, a selected list value) — those rows are on
    already — and corrective exactly where the cursor would otherwise be
    invisible. Returns ``pixels`` unchanged if nothing is flagged.
    """
    if not reverse_rows or not any("1" in row for row in reverse_rows):
        return pixels
    if pixels is None:
        arr = np.zeros((braille.SCREEN_W, braille.SCREEN_H), dtype=np.uint8)  # (240, 64)
    else:
        arr = np.array(pixels).copy()
    width_major = arr.shape[0] >= arr.shape[1]  # (240,64) vs (64,240)
    for r, mask in enumerate(reverse_rows):
        y = r * _CELL_H + (_CELL_H - 1)  # bottom pixel row of this text cell
        if y >= braille.SCREEN_H:
            continue
        for c, bit in enumerate(mask):
            if bit != "1":
                continue
            x0, x1 = c * _CELL_W, c * _CELL_W + _CELL_W
            if width_major:
                arr[x0:x1, y] = 1
            else:
                arr[y, x0:x1] = 1
    return arr


def _demo_frame() -> Frame:
    """A hardware-free frame: border + an 'X', and a fake soft-label row."""
    pixels = np.zeros((braille.SCREEN_H, braille.SCREEN_W), dtype=bool)
    pixels[0, :] = pixels[-1, :] = True
    pixels[:, 0] = pixels[:, -1] = True
    for i in range(braille.SCREEN_H):
        pixels[i, int(i * braille.SCREEN_W / braille.SCREEN_H)] = True
    rows = [""] * 7 + ["More>  Algorithm  KEYMAP   PITCH    AMPENV  more>"]
    return Frame(pixels=pixels, text_rows=rows)


class Display(Static):
    """The braille LCD mirror."""


class SoftBar(Static):
    """The live F1-F6 label strip (or the a-h alternates under --alt-keys)."""

    labels: reactive[List[str]] = reactive(list)
    alt_keys: reactive[bool] = reactive(False)
    # Geometry of the mirror drawn above us, so each block can sit under the
    # soft key it names. span = width of the rendered LCD in cells, offset = how
    # far right it starts. Zero span means "unknown" and we fall back to packing.
    span: reactive[int] = reactive(0)
    offset: reactive[int] = reactive(0)
    # Where each label really sits on the K2000's row (0..1), so blocks land
    # under the words rather than under the middle of a nominal sixth.
    centres: reactive[List[Optional[float]]] = reactive(list)

    def render(self):
        cells = self.labels or [""] * _SOFT_KEYS
        keys = keymap.SOFT_KEY_LABELS_ALT if self.alt_keys else keymap.SOFT_KEY_LABELS
        blocks = [
            f"[{keys[i]}:{label}]" if label else f"[{keys[i]}]"
            for i, label in enumerate(cells)
        ]
        width = self.size.width or 9999
        # Preferred: line each block up under its zone of the mirror above.
        aligned = align_blocks(blocks, self.span, width, self.offset,
                               self.centres or None)
        if aligned is not None:
            return Text(aligned, no_wrap=True)
        # Otherwise fold to the bar width so a whole [F#:label] block is never
        # split, and disable Rich wrapping so it honours our line breaks verbatim.
        return Text(wrap_blocks(blocks, width, sep="  "), no_wrap=True)


# Characters of a name past this many won't fit the K2000's display field; the
# rename tool colours the overflow so it's clear they're stored but not shown.
# A frozen mirror shows stale data that still looks live, which is the one UI
# state that can actively mislead — so it gets the loudest treatment the terminal
# offers. Blink is honoured by kitty and degrades to plain bold orange elsewhere,
# which is still unmistakable against the muted bar.
_PAUSED_STYLE = "blink bold orange1"
# Silent-but-present: informational, not alarming. Deliberately not red — the
# device is fine, it is just busy, and red for a routine disk load is what made
# the old "disconnected" claim so misleading.
_WAITING_STYLE = "bold yellow"

_NAME_DISPLAY_WIDTH = name_cursor.NAME_MAX_LEN  # 16
_OVERFLOW_STYLE = "bold orange1"  # high-contrast orange for the clipped tail


def _name_preview(prefix: str, name: str, width: int = _NAME_DISPLAY_WIDTH) -> Text:
    """``prefix`` + ``name`` as a Rich ``Text`` with the part of ``name`` beyond
    ``width`` styled :data:`_OVERFLOW_STYLE` — those characters are stored on the
    K2000 but fall off the right of its display field."""
    text = Text(prefix)
    text.append(name[:width])
    if len(name) > width:
        text.append(name[width:], style=_OVERFLOW_STYLE)
    return text


# Object types the rename tool offers (the user-facing ones; "Sample" is the
# label for the Soundblock object type). Order = the Select dropdown order.
_RENAMEABLE_TYPES = [
    ("Program", ObjectType.Program),
    ("Sample", ObjectType.Soundblock),
    ("Keymap", ObjectType.Keymap),
    ("Setup", ObjectType.Setup),
    ("Effect (FX)", ObjectType.Effect),
    ("Song", ObjectType.Song),
    ("QuickAccess", ObjectType.QuickAccessBank),
]


class RenameObjectScreen(ModalScreen):
    """Standalone rename tool — *not* a screen mirror.

    Pick an object **type**, enter its **id**, see the **current name**, type a
    **new name**, and it renames via a single SysEx CHANGE
    (:meth:`k2kremote.midi_bridge.MidiBridge.rename`). Because it targets the
    stored object directly it is independent of the on-screen editor/dialogs
    (which keep the multi-tap typer) and of the editing lock; for a Program the
    device is re-selected afterwards so the panel repaints. See
    ``docs/RESOLUTION_NOTES.md`` §8.
    """

    BINDINGS = [("escape", "close", "Close")]

    CSS = """
    RenameObjectScreen { align: center middle; }
    #renamebox { width: 60; height: auto; padding: 1 2; border: round $accent;
                 background: $surface; }
    #renametitle { text-style: bold; }
    #renamecurrent { color: $text-muted; }
    #renamehint { color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="renamebox"):
            yield Static("Rename object — SysEx (no dial-in)", id="renametitle")
            yield Select(_RENAMEABLE_TYPES, value=ObjectType.Program,
                         allow_blank=False, id="renametype")
            yield Input(placeholder="id (e.g. 201) — Enter/Tab looks it up",
                        id="renameid", restrict=r"[0-9]*")
            yield Static("", id="renamecurrent")
            yield Input(placeholder="new name — Enter to rename",
                        id="renamenew")
            yield Static("Esc to close", id="renamehint")

    def _type(self) -> ObjectType:
        return self.query_one("#renametype", Select).value

    def _set_current(self, text: str) -> None:
        self.query_one("#renamecurrent", Static).update(text)

    def action_close(self) -> None:
        self.dismiss()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Stop here: otherwise this bubbles to the app's own on_input_submitted
        # (the bottom name-entry overlay), which would clear focus and try to
        # type our id/name onto the device.
        event.stop()
        if event.input.id == "renameid":
            # Enter just advances to the new-name field; the blur that leaving
            # the id field causes is what fires the lookup (same path as Tab),
            # so there is a single lookup trigger and focus lands cleanly.
            self.set_focus(self.query_one("#renamenew", Input))
        elif event.input.id == "renamenew":
            self._apply()

    def on_descendant_blur(self, event) -> None:
        # Look up the current name whenever focus leaves the id field — by Tab or
        # by the Enter-driven focus_next above.
        if getattr(event.widget, "id", None) == "renameid":
            self._lookup()

    # -- worker round-trips (results marshalled back to the UI thread) -------
    def _lookup(self) -> None:
        try:
            idno = self.query_one("#renameid", Input).value
        except Exception:  # screen torn down (e.g. blur during dismiss)
            return
        if not idno:
            return
        self._set_current("looking up…")

        def done(name, error):  # runs on the UI thread (app marshals it)
            if error is None:
                self._set_current(_name_preview("current name: ", name))
            else:
                self._set_current(f"lookup failed: {error}")

        self.app.rename_lookup(self._type(), int(idno), done)

    def on_input_changed(self, event: Input.Changed) -> None:
        # Live-flag a new name that overflows the display field as it's typed.
        if event.input.id != "renamenew":
            return
        hint = self.query_one("#renamehint", Static)
        if len(event.value) > _NAME_DISPLAY_WIDTH:
            hint.update(_name_preview("won't fully show on panel: ", event.value))
        else:
            hint.update("Esc to close")

    def _apply(self) -> None:
        idno = self.query_one("#renameid", Input).value
        new_name = self.query_one("#renamenew", Input).value
        if not idno or not new_name:
            self._set_current("enter both an id and a new name")
            return

        def done(name, error):  # runs on the UI thread (app marshals it)
            if error is not None:
                self._set_current(f"rename failed: {error}")
                return
            # The INFO reply says what the device actually stored, and until now
            # we printed it inside a success line without ever comparing it to
            # what was asked for. p22 round-tripped an 18-char name intact, so a
            # difference here is *not* the expected long-name truncation — it is
            # the device doing something we did not ask for, which is worth
            # stopping on rather than reporting as done. Trailing blanks are not
            # a difference: whether the firmware pads the field is untested.
            if (name or "").rstrip() != new_name.rstrip():
                self._set_current(_name_preview(f"device stored {name!r}, not: ",
                                                new_name))
                return
            self.app._set_status(f" renamed {self._type().name} {idno} → {name!r}")
            self.dismiss()

        self.app.rename_apply(self._type(), int(idno), new_name, done)


# The Master object-utility functions the F11 tool offers (label, key). "Copy" has
# no single SysEx on the K2000, so it is not offered; "Name" is the Ctrl+O tool.
_MASTER_FUNCTIONS = [
    ("Delete object", "delete"),
    ("Move/relocate object", "move"),
    ("Delete bank — one type", "delete_bank"),
    ("Delete bank — all types", "delete_bank_all"),
    ("Delete all objects (Program RAM)", "delete_all"),
]


class DiskBrowserScreen(ModalScreen):
    """Pick a file off the K2000's OWN disk, by driving its Load browser.

    The online counterpart to the offline editor's picker, and not a better one:
    a disk image is byte-exact, complete and instant, while this costs a keypress
    and a screen read per entry. What it offers is *freshness* — it reflects the
    disk that is in the machine now, which an image only does while it remains a
    copy of that same disk.

    **It never presses `OK`** — on the Load page that loads the file, which is
    slow and, into a populated bank, destructive. Only descend, ascend and
    cancel. See :mod:`k2kremote.disk_browse`.

    Listing a directory costs one keypress and one screen read per entry, so a
    full directory takes a few seconds and the screen says so while it works.
    """

    BINDINGS = [
        ("escape", "close", "Cancel"),
        ("enter", "choose", "Open / pick"),
        ("backspace", "up", "Parent"),
        ("up", "cursor(-1)", "Up"),
        ("down", "cursor(1)", "Down"),
        ("r", "to_root", "Root"),
        ("u", "use_directory", "Use this directory"),
    ]

    CSS = """
    DiskBrowserScreen { align: center middle; }
    #browsebox { width: 74; max-height: 90%; padding: 1 2; border: round $accent;
                 background: $surface; }
    #browsescroll { height: 1fr; min-height: 3; }
    #browsewarn { color: $warning; text-style: bold; }
    #browsetitle { text-style: bold; }
    #browsehint { color: $text-muted; }
    """

    def __init__(self, app_ref, *, directory_mode: bool = False):
        super().__init__()
        self._app = app_ref
        #: When True, this is being used to pick a DESTINATION directory (for a
        #: save) rather than a FILE (for a macro entry). `u` -- "use this
        #: directory" -- works either way; directory_mode only changes what
        #: Enter on a file does, since picking a file makes no sense here.
        self._directory_mode = directory_mode
        self._items = []
        self._path = "\\"
        self._index = 0
        self._busy = True
        self._scroll = VerticalScroll(id="browsescroll")
        self._scroll.can_focus = False      # same reason as MacroScreen
        self._list = Static("", id="browselist")
        self._title = Static("K2000 disk", id="browsetitle")
        self._hint = Static("", id="browsehint")

    def compose(self) -> ComposeResult:
        with Container(id="browsebox"):
            yield Static("⚠  EXPERIMENTAL — reads the disk by driving the "
                         "panel\n   keep the K2000's own LCD in sight: the "
                         "mirror is PAUSED while this works", id="browsewarn")
            yield self._title
            with self._scroll:
                yield self._list
            yield self._hint

    def on_mount(self) -> None:
        self._hint.update("opening the disk browser on the instrument ...")
        self._run(lambda b: self._open_and_list(b))

    # -- device work --------------------------------------------------------

    @staticmethod
    def _open_and_list(bridge):
        from k2kremote import disk_browse
        disk_browse.open_browser(bridge)
        # Force ROOT rather than trusting wherever the device was last left, and
        # then track the path ourselves from here on -- never by reading it back
        # off the screen. The K2000's header truncates a path that does not fit
        # its 40-column display, rendering "\-BAESSE\-SLAP\" as "..\-SLAP\".
        # That is the device's own ellipsis convention, not a literal parent
        # reference, and reading it back verbatim stored a macro entry pointing
        # at a path that does not exist. Nothing about this needs the device's
        # rendering: every directory this browser enters, it entered by name.
        disk_browse.root(bridge)
        return "\\", disk_browse.listing(bridge)

    def _run(self, op) -> None:
        self._busy = True
        self._app.master_apply("disk browse", op, self._done)

    def _done(self, result, error) -> None:
        self._busy = False
        if error:
            self._hint.update(f"browser failed: {error}")
            return
        if not result:
            # A callback with neither a result nor an error. Unpacking it blindly
            # raised TypeError and took the whole app down, which is a poor trade
            # for a browser that could simply say it got nothing.
            self._hint.update("the browser returned nothing — esc to close")
            return
        self._path, self._items = result
        self._index = 0
        self._redraw()

    # -- navigation ---------------------------------------------------------

    def action_cursor(self, delta: int) -> None:
        if self._items:
            self._index = max(0, min(len(self._items) - 1, self._index + delta))
            self._redraw()

    def action_use_directory(self) -> None:
        """Pick the CURRENT directory as the destination, without opening it
        further or picking any file inside it."""
        if self._busy:
            return
        chosen_dir = self._path
        self._app.master_apply("disk browse", self._close_op,
                               lambda r, e: self._leave(chosen_dir))

    def action_choose(self) -> None:
        if self._busy or not self._items:
            return
        item = self._items[self._index]
        if not item.is_dir:
            if self._directory_mode:
                # This browser is only choosing a DIRECTORY -- opening a file
                # makes no sense here, so say what `u` is for instead.
                self._hint.update("this picks a DIRECTORY — press u to use "
                                  f"{self._path}, or open a folder")
                return
            # A file: hand back the full path and leave the browser cleanly.
            path = self._path if self._path.endswith("\\") else self._path + "\\"
            chosen = path + item.filename
            self._app.master_apply("disk browse", self._close_op,
                                   lambda r, e: self._leave(chosen))
            return

        # A directory: descend into it.
        name = item.name
        self._hint.update(f"opening {name} ...")

        index, total = self._index, len(self._items)
        names = [i.name for i in self._items]
        # Compose the new path from what we already know -- the name of the
        # directory just entered -- rather than from the device's display.
        from k2kremote.disk_browse import descend
        new_path = descend(self._path, name)

        def op(bridge, name=name, index=index, total=total, names=names,
              new_path=new_path):
            from k2kremote import disk_browse
            disk_browse.enter(bridge, index, total, name, names)
            return new_path, disk_browse.listing(bridge)

        self._run(op)

    def action_up(self) -> None:
        if self._busy:
            return
        self._hint.update("going up ...")
        # Pop the last component from our OWN tracked path, not the device's.
        from k2kremote.disk_browse import ascend
        parent_path = ascend(self._path)

        def op(bridge, parent_path=parent_path):
            from k2kremote import disk_browse
            disk_browse.parent(bridge)
            return parent_path, disk_browse.listing(bridge)

        self._run(op)

    def action_to_root(self) -> None:
        if self._busy:
            return
        self._hint.update("going to the root ...")

        def op(bridge):
            from k2kremote import disk_browse
            disk_browse.root(bridge)
            return "\\", disk_browse.listing(bridge)

        self._run(op)

    def _leave(self, result) -> None:
        """Hand back and stop holding the wire."""
        self._app.resume_mirror()
        self.dismiss(result)

    @staticmethod
    def _close_op(bridge):
        """Leave the instrument's browser via Cancel, never OK."""
        from k2kremote import disk_browse
        disk_browse.close(bridge)

    def action_close(self) -> None:
        self._app.master_apply("disk browse", self._close_op,
                               lambda r, e: self._leave(None))

    # -- view ---------------------------------------------------------------

    def _redraw(self) -> None:
        self._title.update(f"K2000 disk — {self._path}")
        if not self._items:
            self._list.update("  (empty)")
        else:
            lines = []
            for i, item in enumerate(self._items):
                mark = ">" if i == self._index else " "
                kind = "/" if item.is_dir else " "
                lines.append(f"{mark} {item.name}{kind}   {item.size}")
            self._list.update("\n".join(lines))
        self._ensure_visible()
        if self._directory_mode:
            self._hint.update(f"target: {self._path}   enter open folder · u "
                              f"USE THIS DIRECTORY · backspace parent · r root "
                              f"· esc cancel")
        else:
            self._hint.update("enter open/pick · backspace parent · r root · "
                              "esc cancel   (never loads anything)")

    def _ensure_visible(self) -> None:
        """Keep the cursor on screen — a directory is easily taller than the box.

        Same rule as the macro list: move only when the cursor has actually left
        the window, and then by the minimum. Scrolling on every redraw makes the
        list jump under the eye; never scrolling loses the cursor entirely, which
        is what happened here.
        """
        try:
            height = self._scroll.scrollable_content_region.height
            top = int(self._scroll.scroll_offset.y)
        except Exception:                                   # noqa: BLE001
            return                                          # not mounted yet
        if height <= 0:
            return
        if self._index < top:
            self._scroll.scroll_to(y=self._index, animate=False)
        elif self._index >= top + height:
            self._scroll.scroll_to(y=self._index - height + 1, animate=False)


class MacroScreen(ModalScreen):
    """The RUNNING instrument's macro table — view, reorder, and push it back.

    The macro list the K2000 replays at power-on lives in battery-backed RAM as
    object type 100, id 35. This reads it, lets you rearrange it, and writes it
    back — all over SysEx, with the instrument switched on and its disk in place.

    That is the whole point of it being here rather than in `k2kmaced`. The macro
    editor is deliberately offline and opens no MIDI port, because editing a
    `BOOT.MAC` on a card means the K2000 is switched **off**. This screen answers
    the opposite case: the machine is running, so the card is unreachable, but the
    table is one SysEx away.

    **Nothing here touches a disk.** A push replaces the RAM object only; the
    K2000 saves it itself, from its own Disk pages, and can save under any
    filename — so a working `BOOT.MAC` is never at risk from this screen.

    Editing paths and filenames stays in `k2kmaced`, which has a file picker and a
    disk image to validate against. This screen does the things that only make
    sense against a live machine.
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("r", "reload", "Reload"),
        ("b", "bank(1)", "Bank +"),
        ("B", "bank(-1)", "Bank -"),
        ("m", "mode", "Mode"),
        ("ctrl+up", "shift(-1)", "Move up"),
        ("ctrl+down", "shift(1)", "Move down"),
        ("a", "add", "Add entry"),
        ("e", "edit_path", "Edit path"),
        ("f", "pick_file", "Pick file"),
        # Also reachable WHILE the path field has focus, where a plain letter is
        # just text. priority=True so it beats the Input's own handling.
        Binding("ctrl+f", "pick_file", "Pick file", priority=True),
        Binding("ctrl+t", "pick_target", "Pick target file", priority=True),
        ("delete", "remove", "Delete entry"),
        ("up", "cursor(-1)", "Up"),
        ("down", "cursor(1)", "Down"),
        ("p", "push", "Push to K2000"),
        ("s", "save_disk", "Save to disk"),
        Binding("ctrl+d", "save_to_root", "Save destination: root",
               priority=True),
        # Reuses Ctrl+g, which the main app binds to "Save PNG" -- harmless,
        # since Textual resolves bindings against the active screen first, and
        # this screen shadows the app's binding for as long as it is on top.
        Binding("ctrl+g", "pick_save_directory", "Pick save directory",
               priority=True),
        # Deliberately NOT Enter: Enter accepted the filename, and confirming an
        # overwrite with the same key one keystroke later is how a double-tap
        # destroys a file. A different finger, a different decision.
        # One key that COMMITS whatever write is pending -- a push, or a save
        # over an existing file. Never the key that armed it: `p` arms the push
        # and Enter accepts a filename, and confirming with the same key one
        # keystroke later is how a double-tap writes to the instrument.
        ("w", "confirm_write", "Confirm write"),
    ]

    CSS = """
    MacroScreen { align: center middle; }
    /* A macro can hold far more entries than fit a small window -- 19 is
       ordinary and each is one line -- so the box is bounded and the list
       scrolls inside it. Without this the entries ran past the bottom edge,
       taking the status and hint lines with them. */
    #macrobox { width: 82; max-height: 90%; padding: 1 2; border: round $warning;
                background: $surface; }
    #macroscroll { height: 1fr; min-height: 3; }
    #macrowarn { color: $warning; text-style: bold; }
    #macrotitle { text-style: bold; }
    #macrohint { color: $text-muted; }
    #macrostatus { color: $warning; }
    """

    def __init__(self, worker):
        super().__init__()
        self._worker = worker
        self._table = None          # k2kmaced.macfile.MacroTable
        self._index = 0
        self._dirty = False
        self._armed = False
        # Held from compose(): querying children in on_mount is a race this
        # project has already lost once, on one CI platform only.
        self._scroll = VerticalScroll(id="macroscroll")
        # A VerticalScroll takes focus and eats up/down to scroll ITSELF, so the
        # screen's cursor bindings never fire: the view moved while the ">" sat
        # on entry 0 and scrolled out of sight. This screen drives the scrolling
        # itself, from the cursor, so the container must not compete for keys.
        self._scroll.can_focus = False
        # Hidden inputs must also be UNFOCUSABLE, not merely invisible. Textual
        # focuses the first focusable widget on mount, and `display = False` does
        # not take a widget out of the focus chain — so with the scroll container
        # no longer focusable, focus landed on this hidden Input and every
        # keystroke went into it. Pressing `a` typed an "a" nobody could see
        # instead of adding an entry.
        self._path = Input(placeholder="\\DIR\\FILE.KRZ  (or Ctrl+f to browse)",
                           id="macropath")
        self._path.display = False      # shown only while editing a path
        self._path.can_focus = False
        self._save_name = Input(
            placeholder="file name, no extension  (or Ctrl+t to pick one to "
                        "overwrite)", id="macrosave")
        self._save_name.display = False
        self._save_name.can_focus = False
        #: Set when the save name was picked from the browser, i.e. names a file
        #: that already exists. Saving then OVERWRITES it, so it is confirmed
        #: separately rather than going through on the same Enter as a new name.
        self._save_overwrites: Optional[str] = None
        #: Name accepted and waiting on the separate overwrite keystroke.
        self._pending_save: Optional[str] = None
        #: Where the save will land, as last reported by the instrument. Purely
        #: informational -- macro_save re-checks the drive itself before writing.
        self._where: Optional[str] = None
        self._list = Static("", id="macrolist")
        self._status = Static("", id="macrostatus")
        self._hint = Static("", id="macrohint")

    def compose(self) -> ComposeResult:
        with Container(id="macrobox"):
            # Said on the screen itself, not only in the README: this drives the
            # instrument's own panel for anything SysEx cannot express, and the
            # person about to press `p` or `s` is the one who needs to know.
            yield Static("⚠  EXPERIMENTAL — writes to the running instrument\n"
                         "   keep the K2000's own LCD in sight: the mirror is "
                         "PAUSED while this works", id="macrowarn")
            yield Static("Macro table on the running K2000 (type 100, id 35)",
                         id="macrotitle")
            with self._scroll:
                yield self._list
            yield self._path
            yield self._save_name
            yield self._status
            yield self._hint

    def on_mount(self) -> None:
        self._refresh_hint()
        self.set_focus(None)            # keys belong to the screen's bindings
        self.action_reload()

    def _show_input(self, widget) -> None:
        widget.can_focus = True
        widget.display = True
        widget.focus()

    def _hide_input(self, widget) -> None:
        widget.display = False
        widget.can_focus = False
        self.set_focus(None)

    # -- device -------------------------------------------------------------

    def action_reload(self) -> None:
        self._status.update("reading the live macro table ...")

        def done(data, error):
            self.app.call_from_thread(self._loaded, data, error)

        self._worker.device_op(lambda b: b.read_macro_table(), done)

    def _loaded(self, data, error) -> None:
        if error:
            self._status.update(f"could not read it: {error}")
            self.app.resume_mirror()
            return
        try:
            from k2kmaced.macfile import MacroTable
            self._table = MacroTable.parse(data)
        except Exception as exc:                      # noqa: BLE001
            # A wrong id returns a plausible-looking object rather than an error,
            # so say which object was asked for instead of blaming the parser.
            self._status.update(f"type 100 id 35 did not parse as a macro: {exc}")
            return
        self._index = min(self._index, max(0, len(self._table.entries) - 1))
        self._dirty = False
        self._armed = False
        # The read is done and the wire is free again. Pausing for the seconds an
        # op runs is right; leaving PAUSED blinking over an idle machine for as
        # long as this screen happens to be open is not.
        self.app.resume_mirror()
        self._status.update(f"{len(self._table.entries)} entries, as the "
                            f"instrument has them")
        self._redraw()

    def action_push(self) -> None:
        if self._table is None:
            return
        if not self._dirty:
            self._status.update("nothing changed — reorder or re-bank first")
            return
        self._armed = True
        self._refresh_hint()
        self._status.update("ARMED — press w to write it to the K2000, Esc to "
                            "cancel")
        return

    def _write_table(self) -> None:
        self._status.update("writing ...")
        table = self._table
        backup = os.path.join(os.path.expanduser("~"),
                              ".k2kremote-macro-backup.bin")

        def op(bridge):
            from k2kmaced import online
            return online.push(bridge, table, backup_path=backup)

        # Through master_apply, not device_op: replacing an object rewrites the
        # object database, and the heartbeat's GETGRAPHICS during a destructive
        # object op is what locks this instrument up (RESOLUTION_NOTES §9). It
        # pauses the mirror, marshals the callback to the UI thread, and leaves
        # the mirror paused until `p`.
        self.app.master_apply(
            "macro push", op,
            lambda r, e: self._pushed(r, e, backup))

    def _pushed(self, result, error, backup) -> None:
        if error:
            # push() verifies by reading the object back, so a failure here means
            # the live table may be neither the old one nor the new one. Do NOT
            # resume: the mirror repainting over that message is the last thing
            # wanted, and the instrument's state is exactly what needs looking at.
            self._status.update(f"NOT written: {error}")
            return
        self._dirty = False
        self._status.update(f"written and verified by read-back; previous table "
                            f"saved to {backup}")
        self._redraw()
        self.app.resume_mirror()

    def action_save_disk(self) -> None:
        """Make the K2000 write the live macro table to its own disk.

        The only step here that touches a disk, so it is the only one that
        arms twice and asks for a filename. Everything else is RAM and a power
        cycle undoes it.

        Deliberately saves under a name YOU type rather than over `BOOT.MAC`:
        the safe order is save as something new, try it with Disk -> Load, and
        promote it once it works.
        """
        if self._table is None:
            return
        if self._dirty:
            self._status.update("push the changes to the K2000 first (p) — the "
                                "instrument saves what is in ITS memory, not "
                                "what is on this screen")
            return
        self._save_name.value = ""
        self._show_input(self._save_name)
        self._save_overwrites = None
        self._pending_save = None
        self._status.update("reading the current directory ...")

        def op(bridge):
            from k2kremote.disk_browse import disk_page_path
            return disk_page_path(bridge)

        self.app.master_apply("disk browse", op, self._show_save_destination)

    def _show_save_destination(self, where, error) -> None:
        # Purely informational -- macro_save re-derives it fresh at write time,
        # and refuses if the drive is not what it expects regardless of what
        # this shows. But NOT showing it is how a save landed in
        # \-BAESSE\-SLAP\ without anyone choosing that: the destination is
        # wherever the last browse left the instrument, invisible until you look.
        self._where = where if not error else None
        dest = where if not error else "(could not read — will be re-checked)"
        self._status.update(
            f"will save into: {dest}   Ctrl+d root · Ctrl+g browse · Ctrl+t "
            f"overwrite existing · type a name (up to 8 chars); Enter saves")

    def action_save_to_root(self) -> None:
        """Reset the save destination to the root, without touching any file.

        For exactly the case that had no answer before: typing "\\BOOT" was
        refused (see macro_save's own docstring on why), and there was nothing
        else to press. This opens the Load browser, presses Root, and closes it
        again -- no OK, nothing on disk changes -- which is the only way to move
        where a save lands, since the protocol has no message for it.
        """
        if not self._save_name.display:
            return
        self._status.update("moving to the root directory ...")

        def op(bridge):
            from k2kremote.disk_browse import reset_to_root, disk_page_path
            reset_to_root(bridge)
            return disk_page_path(bridge)

        self.app.master_apply("disk browse", op, self._show_save_destination)

    def action_pick_save_directory(self) -> None:
        """Browse to the directory the save should land in."""
        if not self._save_name.display:
            return

        def chosen(path):
            if not path:
                self._status.update("directory unchanged")
                return
            self._where = path
            self._status.update(
                f"will save into: {path}   Ctrl+d root · Ctrl+g browse · "
                f"type a name; Enter saves")

        self.app.push_screen(DiskBrowserScreen(self.app, directory_mode=True),
                             chosen)

    def action_confirm_write(self) -> None:
        """Commit whatever write is armed: a save over a file, or a push.

        The two cannot both be pending — a push needs unsaved edits and a save
        refuses to run with any — so one key is unambiguous.
        """
        if self._pending_save:
            stem, self._pending_save = self._pending_save, None
            self._save_overwrites = None
            self._do_save(stem, overwrite=True)
            return
        if self._armed:
            self._armed = False
            self._refresh_hint()
            self._write_table()

    def _do_save(self, stem: str, *, overwrite: bool = False) -> None:
        self._status.update(f"saving as {stem}.MAC — the K2000 goes quiet while "
                            f"it writes")

        def op(bridge, overwrite=overwrite):
            from k2kremote import macro_save
            return macro_save.save_macro(bridge, stem, overwrite=overwrite)

        # Through master_apply: a disk write is exactly the kind of destructive
        # operation the heartbeat must not interrupt (RESOLUTION_NOTES §9), and
        # the panel navigation must not race the mirror's own reads.
        self.app.master_apply("macro save", op, self._saved)

    def _saved(self, result, error) -> None:
        # Resume either way: save_macro only returns once the K2000 is back on
        # its Disk page, so the instrument is idle whether it worked or not.
        self.app.resume_mirror()
        if error:
            stem = getattr(error, "stem", None)
            if stem:
                # The instrument answered "Replace existing file?" and we said
                # No. That is not a failure, it is the overwrite question -- and
                # it arrives the same way whether the name was typed or picked,
                # so it arms the same confirm rather than making the user guess.
                self._pending_save = stem
                self._save_overwrites = f"{stem}.MAC"
                self._refresh_hint()
                self._status.update(
                    f"{stem}.MAC ALREADY EXISTS — nothing was written. "
                    f"Press w to overwrite it, Esc to cancel")
                return
            self._status.update(f"NOT saved: {error}")
            return
        self._status.update(f"saved — {result}")

    # -- editing ------------------------------------------------------------

    def _entries(self):
        return self._table.entries if self._table else []

    def action_cursor(self, delta: int) -> None:
        if self._entries():
            self._index = max(0, min(len(self._entries()) - 1,
                                     self._index + delta))
            self._redraw()

    def action_bank(self, delta: int) -> None:
        entries = self._entries()
        if not entries:
            return
        entry = entries[self._index]
        banks = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 0xFFFF]
        try:
            i = banks.index(entry.bank)
        except ValueError:
            i = 0
        entry.bank = banks[(i + delta) % len(banks)]
        self._touch()

    def action_mode(self) -> None:
        entries = self._entries()
        if not entries:
            return
        entry = entries[self._index]
        entry.mode = (entry.mode + 1) % 5      # Append/Merge/Fill/Overwrite/OvFill
        self._touch()

    def action_shift(self, delta: int) -> None:
        entries = self._entries()
        target = self._index + delta
        if not entries or not (0 <= target < len(entries)):
            return
        entries[self._index], entries[target] = entries[target], entries[self._index]
        self._index = target
        self._touch()

    def action_add(self) -> None:
        """Insert an entry after the cursor, inheriting its neighbour's settings.

        Drive, bank and mode are copied from the entry you were on, because a new
        load step almost always belongs with the one next to it. The path starts
        as a placeholder and the editor opens straight away — an entry naming
        NEW.KRZ is a "Not Found" at boot, so it should never be left that way by
        accident.
        """
        if self._table is None:
            return
        from k2kmaced.macfile import MacroEntry

        entries = self._table.entries
        template = entries[self._index] if entries else None
        entries.insert(self._index + 1 if entries else 0, MacroEntry(
            drive=template.drive if template else 1,
            bank=template.bank if template else 0,
            mode=template.mode if template else 2,      # Fill
            path="\\",
            filename="NEW.KRZ",
        ))
        self._index = self._index + 1 if len(entries) > 1 else 0
        self._touch()
        self.action_edit_path()

    def action_remove(self) -> None:
        if self._table is None or not self._table.entries:
            return
        del self._table.entries[self._index]
        self._index = max(0, min(self._index, len(self._table.entries) - 1))
        self._touch()

    def action_edit_path(self) -> None:
        """Type a full `\\DIR\\FILE.KRZ` for the current entry.

        Typed here on the host keyboard rather than dialled on the K2000: the
        instrument's own name entry is a three-letter-group pad with no cursor
        readback, and there is no reason to go near it when the path never has to
        touch the device to be composed.
        """
        entries = self._table.entries if self._table else []
        if not entries:
            return
        self._path.value = entries[self._index].full_path   # a property, not a call
        self._show_input(self._path)
        self._status.update("type the full path — or Ctrl+f to browse the "
                            "K2000's disk; Enter accepts, Esc cancels")

    def action_pick_file(self) -> None:
        """Choose this entry's file from the instrument's own disk.

        Works from the list and from inside the path editor — typing a path and
        browsing for one are two ways at the same field, and being three
        keystrokes into a path is exactly when you realise you do not remember
        the rest of it.
        """
        entries = self._table.entries if self._table else []
        if not entries:
            return
        if self._path.display:          # abandon the half-typed path
            self._close_path()

        def chosen(path):
            if not path:
                self._status.update("nothing picked")
                return
            entry = entries[self._index]
            directory, _, filename = path.rpartition("\\")
            entry.path = (directory or "") + "\\"
            entry.filename = filename
            self._touch()
            self._status.update(f"pointed at {path}")
            self.app.resume_mirror()

        self.app.push_screen(DiskBrowserScreen(self.app), chosen)

    def action_pick_target(self) -> None:
        """Pick an EXISTING file to save over, instead of typing a new name.

        Only meaningful while the save prompt is open. Note that browsing also
        moves the instrument's current directory, and the save follows it — so
        the file you pick determines both the name and where it lands.
        """
        if not self._save_name.display:
            self._status.update("Ctrl+t picks a file to save over — press s first")
            return

        def chosen(path):
            if not path:
                self._status.update("nothing picked")
                return
            filename = path.rpartition("\\")[2]
            stem = filename.rpartition(".")[0] or filename
            self._save_name.value = stem
            self._save_overwrites = path
            self._show_input(self._save_name)
            self._status.update(f"WILL OVERWRITE {path} — Enter to confirm, "
                                f"Esc to cancel")

        self.app.push_screen(DiskBrowserScreen(self.app), chosen)

    def on_input_submitted(self, event) -> None:
        if event.input is self._save_name:
            stem = event.value.strip()
            if not stem:
                self._hide_input(self._save_name)
                self._status.update("no name given; nothing was saved")
                return
            if self._save_overwrites:
                # A name picked from the browser names a file that is already
                # there. Confirming that is a separate decision and takes a
                # DIFFERENT key — Enter has just been pressed to accept the
                # name, and a second Enter is one twitch away.
                self._hide_input(self._save_name)
                self._pending_save = stem
                self._status.update(
                    f"{self._save_overwrites} EXISTS — press w to overwrite it, "
                    f"Esc to cancel")
                return
            self._hide_input(self._save_name)
            self._do_save(stem)
            return
        if event.input is not self._path:
            return
        entries = self._table.entries if self._table else []
        try:
            if not entries:
                raise ValueError("there is no entry to repoint")
            cleaned = event.value.strip().replace("/", "\\")
            if not cleaned:
                raise ValueError("the path is empty")
            if not cleaned.startswith("\\"):
                cleaned = "\\" + cleaned
            directory, _, filename = cleaned.rpartition("\\")
            if not filename:
                raise ValueError("the path has no file name")
            if len(filename.encode("latin-1", errors="replace")) > 15:
                raise ValueError(f"{filename!r} is longer than the 15-character "
                                 f"field")
            entry = entries[self._index]
            entry.path = (directory or "") + "\\"
            entry.filename = filename
        except ValueError as exc:
            self._status.update(str(exc))
            return
        self._close_path()
        self._touch()

    def _close_path(self) -> None:
        self._hide_input(self._path)

    def _touch(self) -> None:
        self._dirty = True
        self._armed = False
        self._refresh_hint()
        self._redraw()

    # -- view ---------------------------------------------------------------

    def _redraw(self) -> None:
        entries = self._entries()
        if not entries:
            self._list.update("  (no entries)")
            return
        lines = []
        for i, entry in enumerate(entries):
            mark = ">" if i == self._index else " "
            lines.append(f"{mark}{i:>3}  {entry.display().rstrip()}")
        self._list.update("\n".join(lines))
        self._ensure_visible()

    def _ensure_visible(self) -> None:
        """Scroll only when the cursor has actually left the window.

        Scrolling on every redraw makes the list jump under the eye even when
        nothing moved; never scrolling leaves the cursor invisible on a long
        macro. So: move the minimum, and only when needed."""
        try:
            height = self._scroll.scrollable_content_region.height
            top = int(self._scroll.scroll_offset.y)
        except Exception:                                   # noqa: BLE001
            return                                          # not mounted yet
        if height <= 0:
            return
        if self._index < top:
            self._scroll.scroll_to(y=self._index, animate=False)
        elif self._index >= top + height:
            self._scroll.scroll_to(y=self._index - height + 1, animate=False)

    def _refresh_hint(self) -> None:
        state = "CHANGED" if self._dirty else "unchanged"
        arm = "  [ARMED]" if self._armed else ""
        self._hint.update(
            f"{state}{arm}   a add · f pick · e path · del remove · b/B bank · m mode · "
            f"ctrl+up/down move · r reload · p push · s save to disk · "
            f"esc close"
            + ("   [w = CONFIRM OVERWRITE]" if self._pending_save
               else "   [w = CONFIRM PUSH]" if self._armed else ""))

    def action_close(self) -> None:
        # Esc closes the path editor first: losing a half-typed path is annoying,
        # losing the whole screen with unpushed edits in it is worse.
        if self._save_name.display:
            self._hide_input(self._save_name)
            self._save_overwrites = None
            self._pending_save = None
            self._status.update("save cancelled")
            return
        if self._path.display:
            self._close_path()
            self._status.update("path unchanged")
            return
        if self._pending_save:
            self._pending_save = None
            self._save_overwrites = None
            self._status.update("overwrite cancelled; nothing was saved")
            return
        if self._armed:
            self._armed = False
            self._refresh_hint()
            self._status.update("push cancelled; nothing was written")
            return
        self.app.resume_mirror()
        self.dismiss(None)


class MasterFunctionScreen(ModalScreen):
    """Standalone Master object-utility tool — fires one SysEx, bypassing the LCD.

    Pick a function (Delete / Move / Delete bank), an object type and an id (or
    bank), and it is done with a single SysEx (DEL 0x07 / CHANGE 0x08 / DELBANK
    0x0E) — no front-panel navigation, so it never drives the K2000 through the
    menu flow that can lock it up. These are **destructive**: a two-step Enter
    confirms the fire, and the app auto-pauses the mirror around the op (resume
    with ``p``). **Move** overwrites whatever sits at the destination id; **Delete
    bank** wipes a whole 100-id bank. **Delete all objects** clears every
    Program-RAM object but DELBANK does *not* reclaim sample RAM — any loaded RAM
    samples are orphaned (gone from the object DB, but the bytes stay resident)
    until a front-panel Master → Delete → Everything (fast) or a K2000 power-cycle.
    See ``docs/RESOLUTION_NOTES.md`` §10.
    """

    BINDINGS = [("escape", "close", "Close")]

    CSS = """
    MasterFunctionScreen { align: center middle; }
    #masterbox { width: 64; height: auto; padding: 1 2; border: round $error;
                 background: $surface; }
    #mastertitle { text-style: bold; }
    #mastercurrent { color: $text-muted; }
    #masterhint { color: $text-muted; }
    """

    _armed = False  # set True after the first Enter; second Enter fires

    def compose(self) -> ComposeResult:
        with Container(id="masterbox"):
            yield Static("Master functions — SysEx (bypasses the LCD)", id="mastertitle")
            yield Select(_MASTER_FUNCTIONS, value="delete", allow_blank=False,
                         id="masterfunc")
            yield Select(_RENAMEABLE_TYPES, value=ObjectType.Program,
                         allow_blank=False, id="mastertype")
            yield Input(placeholder="object id (e.g. 201)", id="mastertarget",
                        restrict=r"[0-9]*")
            yield Input(placeholder="new id (move only)", id="masternewid",
                        restrict=r"[0-9]*")
            yield Static("", id="mastercurrent")
            yield Static("Esc to close", id="masterhint")

    def on_mount(self) -> None:
        self._sync_fields()

    def _func(self) -> str:
        return self.query_one("#masterfunc", Select).value

    def _type(self) -> ObjectType:
        return self.query_one("#mastertype", Select).value

    def _set_current(self, text: str) -> None:
        self.query_one("#mastercurrent", Static).update(text)

    def _reset_hint(self) -> None:
        self._armed = False
        self.query_one("#masterhint", Static).update("Esc to close")

    def action_close(self) -> None:
        self.dismiss()

    def _sync_fields(self) -> None:
        """Adapt the inputs to the chosen function (id vs bank; show newid for move)."""
        func = self._func()
        target = self.query_one("#mastertarget", Input)
        newid = self.query_one("#masternewid", Input)
        newid.display = func == "move"
        # The type applies to delete/move and to a one-type bank delete (DELBANK is
        # type-scoped — verified live: deleting "Program" bank 3 left keymaps and
        # samples intact). The all-types bank delete and "Delete all objects" ignore
        # it (they send DELBANK type 0 = all object types).
        self.query_one("#mastertype", Select).display = func in (
            "delete", "move", "delete_bank")
        # The target field stays visible for every function: a bank number for the
        # bank deletes, an object id for delete/move, and (for Delete all objects)
        # the Enter-trigger for the confirm.
        if func == "delete_all":
            target.placeholder = ("press Enter twice to delete every Program-RAM "
                                  "object (sample RAM needs a power-cycle)")
        elif func == "delete_bank":
            target.placeholder = "bank 0-9 (the 200s bank = 2)"
        elif func == "delete_bank_all":
            target.placeholder = "bank 0-9 — deletes EVERY type in it"
        elif func == "move":
            target.placeholder = "object id to move (e.g. 201)"
        else:
            target.placeholder = "object id to delete (e.g. 201)"
        self._reset_hint()
        self._lookup()

    def on_select_changed(self, event) -> None:
        event.stop()
        self._sync_fields()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._reset_hint()  # any edit disarms the pending confirmation
        if event.input.id == "mastertarget":
            self._lookup()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        # Move needs a destination: Enter on the id field advances to newid.
        if event.input.id == "mastertarget" and self._func() == "move":
            self.set_focus(self.query_one("#masternewid", Input))
            return
        self._attempt()

    def on_descendant_blur(self, event) -> None:
        if getattr(event.widget, "id", None) == "mastertarget":
            self._lookup()

    def _lookup(self) -> None:
        """Preview the target object's current name (only for single-object ops)."""
        if self._func() not in ("delete", "move"):
            self._set_current("")
            return
        try:
            idno = self.query_one("#mastertarget", Input).value
        except Exception:  # screen torn down
            return
        if not idno:
            self._set_current("")
            return
        self._set_current("looking up…")

        def done(name, error):  # runs on the UI thread (app marshals it)
            self._set_current(f"current name: {name!r}" if error is None
                              else f"lookup failed: {error}")

        self.app.rename_lookup(self._type(), int(idno), done)

    def _attempt(self) -> None:
        """Build the op from the fields, then require a second Enter before firing."""
        func, t = self._func(), self._type()
        if func == "delete_all":
            # type 0 + bank 127 = every Program-RAM object (no id/bank to enter).
            # DELBANK frees Program RAM only; it orphans (does NOT reclaim) any
            # loaded sample RAM. Reclaim that with a front-panel Master → Object →
            # Delete → Everything (fast), or a K2000 power-cycle. See §10.
            self._confirm_or_fire(
                "DELETE ALL objects — frees Program RAM only; loaded sample RAM "
                "stays (reclaim via front-panel Master→Delete→Everything, or "
                "power-cycle)",
                lambda b: b.delete_bank(None, 127))
            return
        target = self.query_one("#mastertarget", Input).value
        if not target:
            self._set_current("enter a bank 0-9"
                              if func in ("delete_bank", "delete_bank_all")
                              else "enter an id")
            return
        if func == "delete":
            summary = f"DELETE {t.name} {target}"
            thunk = lambda b, t=t, i=int(target): b.delete_object(t, i)
        elif func == "move":
            newid = self.query_one("#masternewid", Input).value
            if not newid:
                self._set_current("enter a destination id")
                return
            summary = f"MOVE {t.name} {target} → {newid}  (overwrites id {newid})"
            thunk = lambda b, t=t, i=int(target), n=int(newid): b.move_object(t, i, n)
        elif func == "delete_bank":  # one type's bank (DELBANK is type-scoped)
            bank = int(target)
            if not 0 <= bank <= 9:
                self._set_current("bank must be 0-9")
                return
            summary = f"DELETE all {t.name} in bank {bank} ({bank}00-{bank}99)"
            thunk = lambda b, t=t, k=bank: b.delete_bank(t, k)
        else:  # delete_bank_all — every object type in the bank (DELBANK type 0)
            bank = int(target)
            if not 0 <= bank <= 9:
                self._set_current("bank must be 0-9")
                return
            summary = (f"DELETE EVERY type in bank {bank} "
                       f"({bank}00-{bank}99 — Programs, Keymaps, Samples, …)")
            thunk = lambda b, k=bank: b.delete_bank(None, k)
        self._confirm_or_fire(summary, thunk)

    def _confirm_or_fire(self, summary: str, thunk) -> None:
        """First call arms (shows the ⚠ summary); the second actually fires it."""
        if not self._armed:
            self._armed = True
            self.query_one("#masterhint", Static).update(
                f"⚠ {summary} — press Enter again to FIRE, Esc to cancel")
            return

        def done(info, error):  # runs on the UI thread (app marshals it)
            if error is None:
                self.app._set_status(
                    f" {summary} — done; mirror PAUSED, press p to resume")
                self.dismiss()
            else:
                self._reset_hint()
                self._set_current(f"failed: {type(error).__name__}: {error}")

        self.app.master_apply(summary, thunk, done)


class K2KRemoteApp(App):
    """The k2kremote terminal UI."""

    CSS = """
    Screen { layout: vertical; }
    #titlebar { height: 1; background: $boost; color: $text; }
    /* No padding and no wrap so a full 240-col half-block frame fits exactly. */
    #display { height: 1fr; padding: 0; overflow-x: hidden; }
    /* Centre the (capped) pixel image in the available area. */
    #imagebox { height: 1fr; align: center middle; }
    /* Fill up to the cap, derive height from the LCD's 3.75:1 aspect. */
    #imagedisplay { width: 1fr; height: auto; }
    /* height: auto so long rows wrap to multiple lines instead of being
       clipped on the right when the terminal is narrow. */
    #softbar  { height: auto; color: $accent; }
    #modebar  { height: auto; color: $text-muted; }
    #keyhints { height: auto; color: $text-muted; }
    #status   { height: auto; color: $text; }
    #nameentry { dock: bottom; height: 3; border: round $accent; }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("f9", "name_entry", "Name entry"),
        ("f10", "toggle_text", "View mode"),
        ("f12", "screenshot", "Save PNG"),
        ("alt+x", "panic", "Panic"),
        ("p", "pause", "Pause mirror"),
        ("ctrl+r", "refresh", "Force refresh"),
        ("ctrl+o", "rename_object", "Rename object"),
        # F11 (not Ctrl+M — terminals send that as Enter) opens the Master object
        # utilities tool (delete / move / delete-bank via one SysEx).
        ("f11", "master_functions", "Master functions"),
        # Terminal-safe alternates for the app F-keys (F-keys may be intercepted).
        ("ctrl+n", "name_entry", "Name entry"),
        ("ctrl+v", "toggle_text", "View mode"),
        ("ctrl+u", "master_functions", "Master functions"),
        ("ctrl+g", "screenshot", "Save PNG (grab)"),
        # Ctrl+k, not an F-key: every F-key is already the K2000's own panel —
        # F7 Edit, F8 Exit, F9 name, F10 view, F11 master, F12 png — and F1-F6
        # are the soft keys. Binding the macro table to F8 shadowed Exit.
        ("ctrl+k", "macro_table", "Macro table"),
    ]

    def __init__(self, bridge=None, *, demo: bool = False, model: str = "K2000R",
                 text_mode: bool = False, settle: Optional[float] = None,
                 heartbeat: Optional[float] = None,
                 image_protocol: str = "auto", image_cols: int = 120,
                 alt_keys: bool = False, super_alt_keys: bool = False,
                 manual_refresh: bool = False, mirror_panel: bool = True):
        super().__init__()
        self._bridge = bridge
        self._demo = demo
        self._model = model
        self._settle = settle
        self._heartbeat = heartbeat
        # Manual-refresh-only: no periodic heartbeat at all (the worker gets
        # heartbeat=None). The mirror then updates only on front-panel events and
        # explicit refreshes — the strongest guard against the heartbeat polling
        # the K2000 during a destructive op. See refresh.RefreshWorker.
        self._manual_refresh = manual_refresh
        self._mirror_panel = mirror_panel
        # --alt-keys: show the F-key alternates (a-h soft keys, Ctrl-chords) in the
        # soft bar + legend, for terminals that swallow the F-keys. The Alt+letter
        # mode chords are left as-is.
        # --super-alt-keys: all of the above PLUS move the mode buttons to the 'm'
        # leader, for terminals that also grab the Alt-chords (e.g. GTK menus).
        self._super_alt = super_alt_keys
        self._alt_keys = alt_keys or super_alt_keys
        # True while waiting for the second key of the mode leader (press 'm',
        # then the mode letter) — only under --super-alt-keys.
        self._awaiting_mode = False
        self._image_protocol = image_protocol
        self._image_cols = image_cols  # max width (cells) of the pixel image
        self._worker: Optional[RefreshWorker] = None
        self._entry_active = False
        # The name-edit cursor is exposed in neither the ALLTEXT nor GETGRAPHICS
        # reply (verified on hardware), so we track its column in software and
        # draw the underline ourselves. See k2kremote.name_cursor.
        self._name_cursor = NameCursor()
        # Render mode: "auto" picks per page (braille for graphics pages like
        # Program mode, text+cursor for text pages like Disk); "braille"/"text"
        # force one. F10 cycles them.
        self._mode = "text" if text_mode else "auto"
        self._connected: Optional[bool] = None
        # Silent but still plugged in (a disk op). Distinct from disconnected.
        self._waiting = False
        self._last_frame: Optional[Frame] = None
        self._danger_shown = False  # last destructive-screen state reflected in the UI
        # Why the (manual) pause is engaged, for the unified "⏸ PAUSED · <reason>"
        # badge. The confirm-screen auto-pause is tracked by the worker's `danger`.
        self._pause_reason = "manual"
        # Last values pushed to the widgets — readable without poking Textual
        # internals (handy for tests and for resizing).
        self.last_render: str = ""
        self.last_status: str = ""
        self.last_keyhints: str = ""
        self.last_plan: list = []

    def compose(self) -> ComposeResult:
        yield Static(self._titlebar_text(), id="titlebar")
        yield Display(self._placeholder(), id="display")
        if _HAS_IMAGE:
            img = _image_widget_class(self._image_protocol)(id="imagedisplay")
            if self._image_cols:  # cap the width so it isn't huge on wide monitors
                img.styles.max_width = self._image_cols
            box = Container(img, id="imagebox")
            box.display = False  # hidden until image mode is selected
            yield box
        bar = SoftBar(id="softbar")
        bar.labels = [""] * _SOFT_KEYS
        bar.alt_keys = self._alt_keys
        yield bar
        yield Static(Text(self._mode_bar_text(), no_wrap=True), id="modebar")
        # The key-hint legend lives on its own persistent line so transient
        # status messages (below) can never bury it.
        yield Static(Text(self._legend_text(), no_wrap=True), id="keyhints")
        yield Static("", id="status")

    def on_mount(self) -> None:
        self._show_legend()
        self._check_width()
        if self._demo:
            self.show_frame(_demo_frame())
            return
        if self._bridge is None:
            return
        from k2kremote.refresh import HEARTBEAT, SETTLE
        self._worker = RefreshWorker(
            self._bridge,
            on_frame=lambda frame: self.call_from_thread(self.show_frame, frame),
            on_error=lambda exc: self.call_from_thread(self._set_status, f"MIDI: {exc}"),
            on_connection=lambda ok: self.call_from_thread(self._set_connection, ok),
            on_waiting=lambda w: self.call_from_thread(self._set_waiting, w),
            settle=self._settle if self._settle is not None else SETTLE,
            heartbeat=None if self._manual_refresh
            else (self._heartbeat if self._heartbeat is not None else HEARTBEAT),
            mirror_panel=self._mirror_panel,
        )
        self._worker.start()
        self._worker.request_refresh()

    def on_resize(self, event) -> None:
        self._check_width()
        self.query_one("#titlebar", Static).update(self._titlebar_text())  # show new width
        # Re-fold the block bars (soft keys / modes / legend) to the new width.
        self.query_one("#softbar", SoftBar).refresh()
        self.query_one("#modebar", Static).update(Text(self._mode_bar_text(), no_wrap=True))
        self._render_keyhints()  # re-fold the persistent legend to the new width
        # Re-render the last frame so a resize re-evaluates braille/half/quadrant
        # immediately (e.g. widening past 240 cols switches blocks -> half-block).
        if self._last_frame is not None:
            self.show_frame(self._last_frame)

    def _display_width(self) -> int:
        """Live width of the display area (falls back to the screen width)."""
        try:
            w = self.query_one("#display", Display).size.width
        except Exception:
            w = 0
        return w or (self.size.width or 0)

    def _soft_bar_geometry(self, mode: str) -> Tuple[int, int]:
        """``(span, offset)`` in cells describing where the mirror is drawn.

        Feeds :func:`align_blocks` so the ``[F#:label]`` strip sits under the
        soft keys it names. In the character modes the render is left-aligned in
        ``#display`` and its own line length is the span (40 text / 120 braille /
        240 half-block). The pixel image is *centred* in ``#imagebox`` and capped
        at ``--image-cols``, so it needs the widget's real width and x. Returns
        ``(0, 0)`` if the layout can't be measured yet — the bar then packs.
        """
        try:
            bar_x = self.query_one("#softbar", SoftBar).region.x
        except Exception:
            return 0, 0
        if mode == "image" and _HAS_IMAGE:
            try:
                region = self.query_one("#imagedisplay").region
            except Exception:
                return 0, 0
            return region.width, max(0, region.x - bar_x)
        span = max((len(line) for line in self.last_render.split("\n")), default=0)
        try:
            display_x = self.query_one("#display", Display).region.x
        except Exception:
            display_x = bar_x
        return span, max(0, display_x - bar_x)

    def on_unmount(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        # Remember the size so the next launch reopens like this one.
        if self.size.width and self.size.height:
            remember_size(self.size.width, self.size.height)

    # -- input ---------------------------------------------------------------
    def on_key(self, event) -> None:
        # A modal (e.g. the rename tool) owns the keyboard while it is open —
        # never let a stray key bubble through and drive the device.
        if len(self.screen_stack) > 1:
            return
        # While the name-entry overlay is open, keys belong to the Input (which
        # has already handled them by the time this bubbles up) — never drive
        # the device. Escape cancels the overlay.
        if self._entry_active:
            if event.key == "escape":
                event.stop()
                self._close_entry()
            return

        # Mode leader (under --alt-keys): the key after 'm' selects a mode.
        if self._awaiting_mode:
            event.stop()
            event.prevent_default()
            self._awaiting_mode = False
            mode = keymap.MODE_KEYS.get(event.key)
            if mode is not None and self._worker is not None:
                self._worker.press(mode.button)
                self._set_status(f" {mode.label}")
            else:
                self._show_legend()  # cancelled / unknown
            return
        if self._super_alt and event.key == keymap.MODE_LEADER:
            event.stop()
            event.prevent_default()
            self._awaiting_mode = True
            self._set_status(" mode → p Prog · s Setup · q QA · m Mstr · "
                             "i MIDI · d Disk · g Song · e FX   (Esc cancels)")
            return

        action = keymap.resolve(event.key)
        if action is None:
            return
        event.stop()
        event.prevent_default()
        if self._worker is None:
            self._set_status(f" {action.label}  (no device)")
            return

        # Safety: a soft key whose live label is a heavy disk op (Load/Save/…)
        # starts a SCSI operation that pegs the K2000's CPU — polling it then can
        # crash it. Pause *before* the press so no GETGRAPHICS follows, and let
        # the user resume with P once the operation finishes.
        op = self._heavy_op_for(action.button)
        if op is not None:
            self._pause_reason = "disk op"
            self._worker.set_paused(True)
            self._worker.press(action.button)
            self._set_status(f" {op!r} sent — mirror PAUSED while the K2000 works; "
                             "press p to resume when it's done",
                             style=_PAUSED_STYLE)
            self.query_one("#titlebar", Static).update(self._titlebar_text())
            return

        if action.is_wheel:
            self._worker.wheel(action.wheel)
        else:
            # Mirror the cursor move this button causes in the open name dialog,
            # then re-render the last frame at once so the underline tracks
            # without waiting for the device's settle refresh to come back.
            if (self._name_cursor.move(action.button, self._name_len())
                    and self._last_frame is not None):
                self.show_frame(self._last_frame)
            self._worker.press(action.button)
        # Keep the key-hint legend visible rather than burying it under the label
        # of what was just pressed — the screen itself shows the result. (The
        # name dialog keeps its own hint, maintained by show_frame.)
        if not self._name_cursor.active:
            self._show_legend()

    def _heavy_op_for(self, button) -> Optional[str]:
        """If ``button`` is a soft key whose current label is a heavy disk op,
        return that label; else None."""
        idx = _SOFT_INDEX.get(button)
        if idx is None or self._last_frame is None:
            return None
        label = soft_labels(self._last_frame.text_rows)[idx]
        return label if any(op in label.lower() for op in _HEAVY_OPS) else None

    # -- name entry (Phase 2) ------------------------------------------------
    async def action_name_entry(self) -> None:
        """Open the overlay to type a name into the K2000's current dialog."""
        if self._entry_active:
            return
        self._entry_active = True
        entry = Input(placeholder="name to type (Enter to send, Esc to cancel)",
                      id="nameentry")
        await self.mount(entry)
        entry.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Only the bottom name-entry overlay; never a submit from another screen's
        # Input (e.g. the rename tool) that bubbled up here.
        if event.input.id != "nameentry":
            return
        target = event.value
        self._close_entry()
        self._dispatch_name(target)

    def _close_entry(self) -> None:
        self._entry_active = False
        for entry in self.query("#nameentry"):
            entry.remove()
        self.set_focus(None)

    def _dispatch_name(self, target: str) -> None:
        if not target:
            self._set_status(" name entry cancelled")
            return
        try:
            self.last_plan = text_entry.plan_name(target)  # offline reference
        except text_entry.UnsupportedCharacter as exc:
            self._set_status(f" {exc}")
            return
        if self._worker is not None:
            # Feedback-driven entry: reads each position back and self-corrects
            # letter/case. The name dialog must already be open on the K2000.
            # Type from the cursor's tracked offset (not always cell 0), so a
            # name typed onto a mid-field cursor lands where the user placed it.
            start_col = self._name_cursor.pos if self._name_cursor.active else 0
            self._worker.type_name(target, start_col)
            # type_name advances the device cursor to the last typed cell; mirror
            # that so our underline lands there when typing finishes.
            self._name_cursor.set_typed(len(target))
            if self._last_frame is not None:
                self.show_frame(self._last_frame)
            self._set_status(f" typing {target!r} into the name dialog…")
        else:
            self._set_status(f" plan for {target!r}: {len(self.last_plan)} steps (no device)")

    # -- standalone rename tool (SysEx CHANGE, not a screen mirror) -----------
    def action_rename_object(self) -> None:
        """Open the rename-any-object tool (type + id + new name → SysEx CHANGE)."""
        self.push_screen(RenameObjectScreen())

    def rename_lookup(self, obj_type: ObjectType, idno: int, on_result) -> None:
        """Read an object's current name for the tool.

        ``on_result(name, error)`` always runs on the UI thread: the synchronous
        error path calls it directly, and the worker's (background-thread) result
        is marshalled back via :meth:`call_from_thread`.
        """
        if self._worker is None:
            on_result(None, "no device connected")
            return
        self._worker.lookup_name(
            obj_type, idno, lambda n, e: self.call_from_thread(on_result, n, e))

    def rename_apply(self, obj_type: ObjectType, idno: int, name: str, on_result) -> None:
        """Rename an object via SysEx CHANGE; ``on_result(confirmed_name, error)``
        always runs on the UI thread (see :meth:`rename_lookup`)."""
        if not name.isascii():
            on_result(None, "name must be ASCII")
            return
        if self._worker is None:
            on_result(None, "no device connected")
            return
        self._worker.rename(
            obj_type, idno, name, lambda n, e: self.call_from_thread(on_result, n, e))

    # -- standalone Master object-utility tool (delete/move/delete-bank SysEx) -
    def action_macro_table(self) -> None:
        """Open the live macro table — the online macro editor.

        Distinct from `k2kmaced`, which edits `BOOT.MAC` offline with the
        instrument switched off and its card in the computer. This edits what a
        *running* machine holds in RAM, which is unreachable that way.
        """
        if self._worker is None:
            self._set_status(" macro table needs a connected device")
            return
        self.push_screen(MacroScreen(self._worker))

    def action_master_functions(self) -> None:
        """Open the Master functions tool (delete / move / delete-bank via SysEx)."""
        self.push_screen(MasterFunctionScreen())

    def master_apply(self, summary: str, thunk, on_result) -> None:
        """Fire a destructive Master op, auto-pausing the mirror around it.

        The op rewrites the object database, so we pause first (no heartbeat/settle
        follows) and leave the mirror paused — the user resumes with ``p`` once the
        K2000 has finished. ``on_result(info, error)`` always runs on the UI thread.
        """
        if self._worker is None:
            on_result(None, "no device connected")
            return
        # The caller's own words, not a fixed label: the title bar reads
        # "PAUSED · macro save" rather than "master op" for something that is
        # not a Master utility at all.
        self._pause_reason = summary or "device op"
        self._worker.set_paused(True)
        self.query_one("#titlebar", Static).update(self._titlebar_text())
        self._worker.device_op(
            thunk, lambda r, e: self.call_from_thread(on_result, r, e))

    def resume_mirror(self) -> None:
        """Lift an op-pause and repaint, once a screen that took the wire closes.

        `master_apply` leaves the mirror paused on purpose for the destructive
        Master utilities: the K2000 may still be chewing, and the user decides
        when to look again. Browsing a directory or reading the macro table is
        not that — it borrows the wire for a few seconds and gives it back — so
        those screens call this on the way out rather than leaving a PAUSED
        banner blinking over a machine that is perfectly idle.
        """
        if self._worker is None:
            return
        self._pause_reason = "manual"
        self._worker.set_paused(False)
        self._worker.force_refresh()
        self.query_one("#titlebar", Static).update(self._titlebar_text())

    def action_refresh(self) -> None:
        """Force an immediate full screen refresh (works even while paused)."""
        if self._worker is None:
            if self._demo:
                self.show_frame(_demo_frame())
            self._set_status(" refresh (no device)")
            return
        self._worker.force_refresh()
        self._set_status(" forcing full refresh…")

    def action_pause(self) -> None:
        """Freeze/unfreeze all automatic mirror traffic — the universal resume key.

        `p` lifts whichever pause is in effect: a manual/disk-op pause toggles off,
        and a confirm-screen auto-pause is released via a force_refresh (which only
        lifts it once the screen is no longer a destructive confirm — so pressing
        `p` while the prompt is still up safely re-reads rather than barging on)."""
        if self._worker is None:
            self._set_status(" pause (no device)")
            return
        # Auto-paused on a confirm screen: resume the same way Ctrl+r does — read
        # once; the worker clears the hold if the screen is now safe.
        if self._worker.danger:
            self._worker.force_refresh()
            self._set_status(" resuming — re-reading; confirm the K2000 has finished")
            return
        paused = not self._worker.paused
        if paused:
            self._pause_reason = "manual"
        self._worker.set_paused(paused)
        self._set_status(" PAUSED — mirror frozen; press p before SCSI load/save"
                         if paused else " resumed",
                         style=_PAUSED_STYLE if paused else None)
        self.query_one("#titlebar", Static).update(self._titlebar_text())

    def action_panic(self) -> None:
        """Send a MIDI all-notes-off panic on all channels."""
        if self._worker is not None:
            self._worker.panic()
            self._set_status(" PANIC — all notes off")
        else:
            self._set_status(" Panic (no device)")

    _MODES = ("auto", "braille", "blocks", "text") + (("image",) if _HAS_IMAGE else ())

    def action_toggle_text(self) -> None:
        """Cycle the render mode (… → image on kitty/sixel terminals)."""
        self._mode = self._MODES[(self._MODES.index(self._mode) + 1) % len(self._MODES)]
        if self._last_frame is not None:
            self.show_frame(self._last_frame)  # re-render, no MIDI
        self._set_status(f" mirror: {self._mode}")
        self.query_one("#titlebar", Static).update(self._titlebar_text())

    def action_screenshot(self) -> None:
        """Save the current screen as a high-fidelity PNG (reuses psobot/k2000)."""
        if self._last_frame is None:
            self._set_status(" nothing to capture yet")
            return
        try:
            path = screenshot.save_png(self._last_frame, screenshot.default_filename())
        except Exception as exc:  # Pillow missing, unwritable path, …
            self._set_status(f" screenshot failed: {exc}")
            return
        self._set_status(f" saved {path}")

    # -- rendering -----------------------------------------------------------
    def _graphics_capable(self) -> bool:
        """True if a real pixel protocol (kitty TGP / sixel) is available."""
        if not _HAS_IMAGE:
            return False
        proto = self._image_protocol if self._image_protocol != "auto" else _detected_image_protocol()
        return proto in ("tgp", "sixel")

    def _effective_mode(self, frame: Frame) -> str:
        if self._mode != "auto":
            return self._mode
        # On a pixel-capable terminal (kitty/sixel), show the real image for
        # every page. Otherwise: text+cursor for pure-text pages (Disk/lists),
        # braille for graphics pages (Program name, Edit diagrams/envelopes).
        if self._graphics_capable():
            return "image"
        # Song mode is mostly text but draws its channel-number strip as graphics
        # only, so force braille (in text it would be invisible). On a graphics
        # terminal the image above already shows it.
        if _is_song_page(frame.text_rows):
            return "braille"
        return "text" if _is_text_page(frame) else "braille"

    def show_frame(self, frame: Frame) -> None:
        self._last_frame = frame
        # Track the name-edit cursor first, so this frame's reverse mask carries
        # the up-to-date cursor cell.
        if frame.text_rows:
            self._update_name_hint(frame.text_rows)
        mode = self._effective_mode(frame)
        image_active = mode == "image" and _HAS_IMAGE

        # Merge any device-reported reverse-video cells with the software-tracked
        # name-edit cursor, then bake them into the pixel buffer as underlines so
        # every graphics renderer shows the cursor — the K2000 reports it in
        # neither the text nor the graphics plane.
        reverse = self._effective_reverse(frame)
        pixels = apply_cursor_underline(frame.pixels, reverse)

        # Swap between the character display and the (centred) pixel image.
        if _HAS_IMAGE:
            self.query_one("#imagebox").display = image_active
        self.query_one("#display", Display).display = not image_active

        if image_active:
            try:
                # Pixel-perfect bitmap via kitty/sixel (textual-image picks the
                # protocol; falls back to half-blocks on plain terminals).
                self.query_one("#imagedisplay").image = \
                    screenshot.live_image(Frame(pixels=pixels, text_rows=frame.text_rows),
                                          scale=4)
                self.last_render = "<image>"
            except Exception as exc:  # pragma: no cover - protocol/term specific
                self._set_status(f" image render failed: {exc}")
        elif frame.pixels is None or mode == "text":
            # Real characters (readable) with the graphics plane's cursor /
            # highlight / status bar shown as reverse video, plus the high-bit
            # cursor cells (name-edit underscore) marked directly.
            renderable = render_text_overlay(pixels, frame.text_rows, reverse)
            self.last_render = renderable.plain
            self.query_one("#display", Display).update(renderable)
        elif mode == "blocks":
            # Solid blocks — cleaner than braille. Use the wide, aspect-correct
            # half-block (240 cols) when the display is wide enough, else the
            # narrower quadrant (120 cols). Decided from the live display width.
            if self._display_width() >= braille.HALF_COLS:
                self.last_render = braille.render_halfblock(pixels, frame.text_rows)
            else:
                self.last_render = braille.render_quadrant(pixels, frame.text_rows)
            self.query_one("#display", Display).update(self.last_render)
        else:
            # Composite the text plane onto the graphics plane so nothing's lost.
            self.last_render = braille.render(pixels, frame.text_rows)
            self.query_one("#display", Display).update(self.last_render)
        if frame.text_rows:
            bar = self.query_one("#softbar", SoftBar)
            # Geometry first, so the labels render already aligned rather than
            # jumping into place on a second pass.
            bar.span, bar.offset = self._soft_bar_geometry(mode)
            bar.centres = soft_label_centres(frame.text_rows)
            bar.labels = soft_labels(frame.text_rows)
        self._reflect_danger()

    def _reflect_danger(self) -> None:
        """When the worker enters/leaves a destructive screen, repaint the
        titlebar indicator and flash a one-line status hint."""
        danger = self._worker is not None and self._worker.danger
        if danger == self._danger_shown:
            return
        self._danger_shown = danger
        self.query_one("#titlebar", Static).update(self._titlebar_text())
        if danger:
            self._set_status(" ⏸ PAUSED · confirm — mirror frozen (no MIDI); press "
                             "p (or Ctrl+r) when the K2000 has finished",
                             style=_PAUSED_STYLE)
        elif self.last_status.startswith(" ⏸ PAUSED · confirm"):
            self._show_legend()

    def _effective_reverse(self, frame: Frame) -> List[str]:
        """Device-reported reverse-video cells OR'd with the software cursor cell."""
        return name_cursor.merge_reverse(
            list(frame.reverse or []), self._name_cursor.reverse_mask())

    def _name_len(self) -> int:
        """Length of the name currently in the field (trailing blanks trimmed)."""
        if self._last_frame is None or not self._name_cursor.active:
            return 0
        rows = self._last_frame.text_rows
        if self._name_cursor.row >= len(rows):
            return 0
        return len(rows[self._name_cursor.row][self._name_cursor.origin:].rstrip())

    _NAME_HINT = " ✎ name dialog — press F9 (or Ctrl+n) to type a name"

    def _update_name_hint(self, text_rows: List[str]) -> None:
        """Show a persistent F9 hint while the K2000 is on its naming page;
        restore the legend once it closes. Also open/close the software name-edit
        cursor (the device exposes it in neither plane, so we draw it ourselves)
        and keep the pixel plane fresh there for the surrounding chrome."""
        naming = is_name_dialog(text_rows)
        if self._worker is not None:
            self._worker.set_prioritize_graphics(naming)
        if naming:
            row, origin = text_entry._find_name_field(text_rows)
            if self._name_cursor.active:
                self._name_cursor.row, self._name_cursor.origin = row, origin
            else:
                self._name_cursor.open(row, origin)
            if self.last_status != self._NAME_HINT:
                self._set_status(self._NAME_HINT)
        else:
            if self._name_cursor.active:
                self._name_cursor.close()
            if self.last_status == self._NAME_HINT:
                self._show_legend()

    def _bar_width(self) -> int:
        """Width to fold the legend / mode bar to (full window width)."""
        return self.size.width or 0

    def _legend_text(self) -> str:
        groups = keymap.LEGEND_GROUPS_ALT if self._alt_keys else keymap.LEGEND_GROUPS
        return " " + wrap_groups(groups, max(self._bar_width() - 1, 0))

    def _render_keyhints(self) -> None:
        """(Re)draw the persistent key-hint legend on its own line."""
        self.last_keyhints = self._legend_text()
        self.query_one("#keyhints", Static).update(Text(self.last_keyhints, no_wrap=True))

    def _show_legend(self) -> None:
        """Clear any transient status message; the hints stay on the #keyhints
        line, so there is nothing to restore there."""
        self._render_keyhints()
        self._set_status("")

    def _set_status(self, text: str, *, style: Optional[str] = None) -> None:
        self.last_status = text  # stays a plain str — callers do e.g. .lower() on it
        # no_wrap: honour the line breaks we folded in, never re-break a block.
        rendered = Text(text, no_wrap=True)
        if style:
            rendered.stylize(style)
        self.query_one("#status", Static).update(rendered)

    def _set_waiting(self, waiting: bool) -> None:
        """The device went quiet but is still plugged in — say so honestly.

        A K2000 disk load silences the unit for minutes; it answers nothing, so
        there is no screen to read and no timeout long enough to wait it out.
        Calling that "disconnected" was wrong every time a file was opened. The
        ports are still there, so this is the accurate word for it.
        """
        self._waiting = waiting
        self.query_one("#titlebar", Static).update(self._titlebar_text())
        if waiting:
            self._set_status(" ⏳ device is not answering — busy (disk op?). The "
                             "mirror will pick up on its own when it replies.",
                             style=_WAITING_STYLE)
        elif self.last_status.startswith(" ⏳ device is not answering"):
            self._show_legend()

    def _set_connection(self, connected: bool) -> None:
        self._connected = connected
        self.query_one("#titlebar", Static).update(self._titlebar_text())
        if not connected:
            self._set_status(" disconnected — retrying…", style="bold red")

    def _titlebar_text(self) -> Text:
        if self._demo:
            conn, conn_style = "demo", "cyan"
        elif self._bridge is None:
            conn, conn_style = "no MIDI", "bold red"
        elif self._connected is None:
            conn, conn_style = "connecting…", "bold yellow"
        elif self._waiting:
            conn, conn_style = "busy — not answering", _WAITING_STYLE
        elif self._connected:
            conn, conn_style = "connected", "bold green"
        else:
            conn, conn_style = "disconnected", "bold red"
        # One unified "⏸ PAUSED · <reason>" badge whether the freeze was manual, a
        # disk op, or the automatic confirm-screen hold — all resumed with `p`.
        if self._worker is not None and self._worker.danger:
            state = "  ·  ⏸ PAUSED · confirm"      # auto-paused on a Yes/No prompt
        elif self._worker is not None and self._worker.paused:
            state = f"  ·  ⏸ PAUSED · {self._pause_reason}"
        elif self._manual_refresh:
            state = "  ·  manual refresh"
        else:
            state = ""
        paused = state
        width = self._display_width()
        mirror = self._mode
        if self._mode == "blocks":
            # Show which solid renderer is active and why (width gates half-block).
            mirror = "blocks/half" if width >= braille.HALF_COLS else "blocks/quad"
        elif self._mode == "image":
            proto = self._image_protocol if self._image_protocol != "auto" else _detected_image_protocol()
            mirror = f"image/{proto}"
        # conn is styled so a disconnected/no-MIDI state can't blend into the
        # rest of the bar and go unnoticed (it did — see the 2026-08-02 report).
        text = Text(no_wrap=True)
        text.append(f" k2kremote · {self._model} · ")
        text.append(conn, style=conn_style)
        text.append(f" · {mirror} · {width}w")
        if paused:
            text.append(paused, style=_PAUSED_STYLE)
        return text

    def _placeholder(self) -> str:
        blank = np.zeros((braille.SCREEN_H, braille.SCREEN_W), dtype=bool)
        return braille.render(blank)

    def _mode_bar_text(self) -> str:
        bar = keymap.MODE_BAR_ALT if self._super_alt else keymap.MODE_BAR
        blocks = [f"[{chord} {name}]" for chord, name in bar]
        return " " + wrap_blocks(blocks, max(self._bar_width() - 1, 0), sep="  ")

    _WIDTH_HINT_PREFIX = " terminal "

    def _check_width(self) -> None:
        """Show a 'widen the window' hint below 120 cols; restore the legend above."""
        width = self.size.width
        if width and width < braille.BRAILLE_COLS:
            self._set_status(
                f"{self._WIDTH_HINT_PREFIX}{width} cols; need {braille.BRAILLE_COLS} "
                "for a 1:1 mirror — widen the window"
            )
        elif self.last_status.startswith(self._WIDTH_HINT_PREFIX):
            self._show_legend()


def resolve_config(args):
    """Merge a saved config.toml with CLI overrides into a BridgeConfig.

    File config is the base; explicit ``--port`` / ``--rig auto`` win over it.
    Returns the effective :class:`~k2kremote.midi_bridge.BridgeConfig`.
    """
    from k2kremote.midi_bridge import BridgeConfig

    config = BridgeConfig()
    if args.config and os.path.exists(args.config):
        config = BridgeConfig.load(args.config)

    if args.rig == "auto":
        config.rig = args.rig
    if args.port:
        config.rig = "standard"
        config.port = args.port
    return config


def _build_bridge(args):
    from k2kremote.midi_bridge import MidiBridge, SEND_GAP, bidirectional_ports

    config = resolve_config(args)
    # Standard rig with no remembered port: fall back to the first bidirectional
    # port so first-run-without-config still works. (auto needs no port.)
    if config.rig == "standard" and not config.port:
        candidates = bidirectional_ports()
        if not candidates:
            sys.exit("no MIDI port found; pass --port NAME, --rig auto, or --demo")
        config.port = candidates[0]

    gap = args.sysex_interval / 1000.0 if args.sysex_interval is not None else SEND_GAP
    try:
        bridge = MidiBridge.from_config(config, gap=gap)
    except RuntimeError as exc:
        sys.exit(str(exc))
    if args.save_config and args.config:
        config.save(args.config)
    return bridge


LONG_HELP = """
k2kremote — user manual
=======================

WHAT IT IS
  k2kremote is a terminal remote for the Kurzweil K2000 and K2000R. Over an
  ordinary MIDI connection it mirrors the instrument's small LCD on your screen
  and lets your computer keyboard press the front-panel buttons and turn the
  alpha wheel. It talks to the hardware purely with MIDI System Exclusive
  (SysEx) messages — no extra cables or modifications. There is also a SysEx
  "rename object" tool that sets a Program/Sample/Keymap/Setup/Effect name in one
  go, instead of dialling each letter in on the panel.

  IMPORTANT — please read the SAFETY section at the end before connecting real
  hardware, and make backups first.

REQUIREMENTS
  - Python 3.11 or newer.
  - A MIDI interface connected to the K2000's MIDI IN and OUT (or a USB-MIDI
    interface plus DIN cables). SysEx must be able to travel in both directions.
  - The K2000's SysEx must be enabled and its "SysX Device ID" known (this unit
    answers as device id 0). MIDI sysex IDs are independent of the MIDI channel.
  - Python packages: textual, python-rtmidi, numpy, attrs, and the psobot/k2000
    protocol library (installed editable from a local checkout). The optional
    pixel-perfect image mode additionally needs textual-image and pillow.

TERMINAL / CONSOLE RECOMMENDATIONS
  The text/braille/blocks render modes work in any reasonably modern terminal
  with a Unicode font. The "image" mode draws a pixel-perfect colour LCD and
  needs a terminal that supports an inline-graphics protocol:
    - Linux:   kitty (Terminal Graphics Protocol) is recommended; WezTerm or any
               sixel-capable terminal also works (use --image-protocol sixel).
    - macOS:   iTerm2 or kitty (graphics), otherwise the text/braille modes.
    - Windows: Windows Terminal supports sixel (--image-protocol sixel); or use
               the text/braille/blocks modes in any console.
  Use a font with good Unicode-braille and block-element coverage for the
  text-based modes.

  KEEP IT SIMPLE: a plain, "dumb" terminal that does not steal F-keys or Alt
  shortcuts is the most trouble-free choice (then you never need --alt-keys).
  Good ones:
    - Linux:   xterm, st (suckless), or alacritty. kitty too, for image mode.
    - macOS:   alacritty or kitty. (Terminal.app and iTerm2 work but use Cmd-/
               menu shortcuts.)
    - Windows: alacritty, or Windows Terminal (also gives sixel image mode).
  Rich GUI terminals (LXTerminal, GNOME Terminal, Konsole, …) often grab the
  F-keys and Alt+letter for their own menus — that is what --alt-keys /
  --super-alt-keys work around.

  NOTE on xterm: by default it does NOT send Alt+letter as an escape sequence, so
  the Alt+p/s/… mode chords won't reach the app. Enable it with
      xterm -fa "Monospace" -fs 12 -xrm 'XTerm*metaSendsEscape: true'
  (or put 'XTerm*metaSendsEscape: true' in ~/.Xresources) — or just use
  --super-alt-keys and the 'm' mode leader instead.

  TESTED ENVIRONMENT: development and testing were done ONLY on Debian "Bookworm"
  with the kitty terminal 0.47.4. The software has NOT been tested on Windows or
  macOS, and not on other terminals; those paths may need adjustment. Reports
  welcome.

CONNECTING
  No hardware, just to look around:
      python -m k2kremote.app --demo

  List the MIDI ports your system exposes, and probe for a K2000:
      python -m k2kremote.midi_bridge ports
      python -m k2kremote.midi_bridge probe

  Connect (pick one):
      python -m k2kremote.app                     # first bidirectional MIDI port
      python -m k2kremote.app --rig auto          # probe every port for a K2000
      python -m k2kremote.app --port "Your Port"  # an exact port by name

  Remember the choice so later runs need no flags:
      python -m k2kremote.app --port "Your Port" --save-config
      python -m k2kremote.app                     # reuses config.toml

RENDER MODES (press F10 to cycle: auto -> braille -> blocks -> text -> image)
  - auto    On a graphics-capable terminal shows the image for graphics pages and
            text for text pages; otherwise picks braille/text per page.
  - braille The densest text mirror: 2x4 Unicode braille dots per cell, so the
            whole LCD fits a compact 120x16 grid. Fits a short terminal.
  - blocks  Solid block characters (no braille dot-gaps). Picks automatically by
            width (the title bar shows which):
              * half-block - 1px wide x 2 tall per cell => 240 columns, a 1:1
                match for the LCD width that keeps its wide aspect and is the
                sharpest. Needs a ~240-column terminal.
              * quadrant   - 2x2 px per cell => 120 columns, fits a normal-width
                terminal, but half the horizontal detail (and ~32 rows tall).
  - text    The real 8x40 characters from the LCD, with the cursor as reverse
            video. Fast and crisp for menus and lists.
  - image   A pixel-perfect colour LCD, only on graphics-capable terminals.

CONTROLS (your keyboard drives the K2000's front panel)
  F1-F6            The six soft keys (their labels are LIVE — they mirror the
                   K2000's own soft-key row). Terminal-safe alternates: a s d f g h.
  F7 / F8          Edit / Exit.            (alternates: Ctrl+e / Ctrl+x)
  0-9              Number pad.
  Arrows           Cursor up/down/left/right.
  + / -  (or PgUp/PgDn)   Value increment / decrement.
  [ / ]            Chan/Bank down / up.
  Enter            Enter.       Esc = Exit (back out).      Backspace = Clear.
  Delete           Cancel.
  Ctrl+Up/Down     Alpha wheel by 1.       Ctrl+PgUp/PgDn = alpha wheel by 5.
  Alt+p/s/q/m/i/d/g/e   Jump to Program / Setup / Quick-Access / Master / MIDI /
                   Disk / Song / Effects mode. (GTK terminals like LXTerminal
                   grab Alt+letter for their menus; with --super-alt-keys press
                   the leader 'm' then the same letter instead, e.g. m then d =
                   Disk.)
  F9               Name-entry overlay: type a name and press Enter to send it
                   (typed into the open dialog, letter by letter with read-back),
                   Esc cancels. (alternate: Ctrl+n)
  Ctrl+o           "Rename object" tool: pick a type, enter the id, see the
                   current name, type a new one, and it is set with a single SysEx
                   message. Characters past the 16-char display field are shown in
                   orange (stored, but not visible on the panel).
  F11              "Master functions" tool, each via ONE SysEx (bypassing the
                   front-panel menu that can lock the unit up): delete an object;
                   move/relocate an object (OVERWRITES the destination id); delete
                   one type's bank (e.g. all Programs in the 300s); delete every
                   type in one bank; or delete all objects (all Program-RAM banks
                   — frees Program RAM only; DELBANK does not reclaim loaded sample
                   RAM, so reclaim that with a front-panel Master→Delete→Everything
                   or a K2000 power-cycle).
                   Destructive: two-step Enter confirm + the mirror auto-pauses
                   around the op (resume with p). (Not Ctrl+M — terminals send that
                   as Enter; --alt-keys offers Ctrl+u.)
  F10              Cycle render mode.       (alternate: Ctrl+v)
  F12              Save the current screen as a PNG.   (alternate: Ctrl+g)
  Alt+x            PANIC — MIDI all-notes-off on all 16 channels.
  p                Pause / resume the mirror (stop all MIDI traffic). Universal
                   resume: lifts a manual, disk-op, or confirm-screen pause.
  Ctrl+r           Force an immediate full refresh (works even while paused; also
                   releases a confirm-screen auto-pause).
  Ctrl+c           Quit.

  Destructive object commands are not on the ordinary keys — they live only behind
  the F11 "Master functions" tool, gated by a two-step confirm and an auto-pause.

  If your terminal steals keys, two options remap the hints (and the keys you
  press) to plain alternates, and the on-screen hints update to match:
    --alt-keys        the soft keys become a-h and the legend shows Ctrl+e/x/n/v/g
                      instead of the F-keys. The Alt+letter mode chords stay.
    --super-alt-keys  all of the above, plus the mode buttons move to the 'm'
                      leader: press m, then the mode's lowercase letter
                      (m then d = Disk) - no Alt, for terminals (e.g. GTK menus)
                      that also grab the Alt-chords.
  The simplest fix, though, is to use a plain terminal that does not grab keys at
  all - see TERMINAL / CONSOLE RECOMMENDATIONS above.

WHY PAUSE MATTERS
  The K2000's CPU can be overwhelmed by MIDI traffic while it is busy — for
  example during a SCSI Load or Save, or while it rewrites its object table for a
  delete. A screen poll landing in that window can LOCK UP the unit. k2kremote
  guards against this several ways:
    * it automatically pauses the mirror when you press a soft key whose label is
      a heavy disk operation, and backs off when the device stops answering;
    * it AUTO-PAUSES the mirror entirely (no MIDI at all) when a CONFIRMATION
      prompt is on screen — a bare Yes/No soft-key pair, or the text "are you
      sure" — because the next press commits the rewrite. Earlier idle screens
      (the delete selection list, object menus) stay LIVE so you can navigate
      them;
    * --manual-refresh disables the periodic refresh entirely (the mirror then
      updates only on front-panel events and Ctrl+r) — the strongest guard.
  All of these show one "⏸ PAUSED · <reason>" badge (manual / disk op / confirm)
  and all resume with p (the confirm pause also releases on Ctrl+r).
  Best-effort caveat: the auto-pause must read the confirm screen BEFORE you press
  Yes, so for guaranteed safety press p yourself before any delete/save — that
  stops all MIDI regardless of what is on screen.

SAFETY — USE AT YOUR OWN RISK
  This software is provided "as is", with NO WARRANTY and NO LIABILITY of any
  kind, including for DATA LOSS or HARDWARE DAMAGE. You use it entirely at your
  own risk.

  During development and testing, the K2000 was occasionally driven into a
  HARDWARE LOCKUP that could only be cleared by a FACTORY RESET of the
  instrument. A factory reset can erase user data on the unit.

  Therefore, BEFORE using k2kremote with real hardware, make COMPLETE, CURRENT
  BACKUPS of everything on your K2000 — RAM Programs, Setups, Samples/Keymaps,
  Effects, Master/MIDI settings, and any SCSI media — so you can restore after a
  reset. See DISCLAIMER.md for the full terms.

  Kurzweil is a trademark of Young Chang Co. Ltd.; this project is not affiliated
  with or endorsed by them.
"""


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="k2kremote",
        description="Terminal remote for the Kurzweil K2000 / K2000R — mirrors the "
                    "hardware LCD over MIDI SysEx and drives the front panel from the "
                    "keyboard.",
        epilog="Run with --long-help for a full prose user manual (setup, terminals, "
               "controls, and safety). Inside the app, F1-F6 are the live soft keys; "
               "press Ctrl+r to refresh and Alt+x to panic.")
    conn = parser.add_argument_group("connection")
    conn.add_argument("--rig", choices=["auto", "standard"], default="standard",
                      help="how to find the K2000: 'standard' (default) uses one "
                           "bidirectional MIDI port; 'auto' probes every port for a "
                           "K2000 that answers SysEx")
    conn.add_argument("--port", metavar="NAME",
                      help="exact MIDI port name to use (implies --rig standard); "
                           "list names with: python -m k2kremote.midi_bridge ports")
    conn.add_argument("--config", default="config.toml", metavar="FILE",
                      help="TOML file remembering the port/rig selection "
                           "(default: config.toml; ignored if absent)")
    conn.add_argument("--save-config", action="store_true",
                      help="write the effective port/rig selection to --config, so "
                           "later runs need no flags")
    conn.add_argument("-i", "--sysex-interval", type=float, metavar="MS",
                      help="minimum delay between outgoing SysEx messages in "
                           "milliseconds (default 150, like 'amidi -i'; clamped to "
                           "the RE'd 120 ms floor). Lower = snappier UI but more "
                           "risk of garbling the K2000's LCD; raise it to 500 for "
                           "unattended runs")

    disp = parser.add_argument_group("display")
    disp.add_argument("--text", action="store_true",
                      help="start in fast text (ALLTEXT) mode instead of auto; clean "
                           "for text-heavy pages like Disk. Cycle modes live with F10")
    disp.add_argument("--image-protocol", choices=["auto", "tgp", "sixel", "halfcell"],
                      default="auto",
                      help="terminal graphics protocol for image mode (default: auto-"
                           "detect). Force 'tgp' for kitty, 'sixel' for WezTerm/Windows "
                           "Terminal, 'halfcell' for a universal text fallback")
    disp.add_argument("--image-cols", type=int, default=120, metavar="N",
                      help="cap the pixel image at N columns so it isn't huge on wide "
                           "monitors (default 120; height follows the LCD's aspect)")
    disp.add_argument("--model", default="K2000R", metavar="NAME",
                      help="model label shown in the title bar (default: K2000R)")

    misc = parser.add_argument_group("behaviour")
    misc.add_argument("--settle", type=float, metavar="MS",
                      help="delay after a keypress before reading the redrawn LCD in "
                           "milliseconds (default 150; lower = snappier. Too low just "
                           "costs one cheap re-read — the mirror takes a second look "
                           "when the screen comes back unchanged)")
    misc.add_argument("--heartbeat", type=float, metavar="MS",
                      help="idle refresh cadence in milliseconds (default 1200). The "
                           "idle poll reads only the 321-byte text plane and stops "
                           "there when nothing changed, so it is ~8x cheaper than a "
                           "full frame; lower = front-panel changes appear sooner")
    misc.add_argument("--alt-keys", action="store_true",
                      help="show the terminal-safe key alternates (a-h soft keys, "
                           "Ctrl+e/x/n/v/g) in the legend and soft-key bar — for "
                           "terminals that intercept the F-keys (Alt-chords stay)")
    misc.add_argument("--super-alt-keys", action="store_true",
                      help="everything --alt-keys does, plus move the mode buttons "
                           "to the 'm' leader (press m, then p/s/q/m/i/d/g/e) — for "
                           "terminals that also grab the Alt+letter mode chords")
    misc.add_argument("--no-panel-mirror", action="store_true",
                      help="ignore the K2000's own front-panel presses. The unit "
                           "only sends them when MIDI XMIT 'Bttns' is On; each one "
                           "costs a screen read, so turn this off if the mirror "
                           "feels heavy while you work at the hardware")
    misc.add_argument("--manual-refresh", action="store_true",
                      help="disable the periodic heartbeat entirely; refresh the "
                           "mirror only on front-panel events and explicit Ctrl+r. "
                           "Strongest guard against polling the K2000 during a "
                           "delete/save (the heartbeat can lock up the unit there)")
    misc.add_argument("--demo", action="store_true",
                      help="run against a static synthetic frame with no MIDI — try "
                           "the UI and render modes without any hardware")
    misc.add_argument("--print-size", action="store_true",
                      help="print the terminal size to open at as COLSxROWS and "
                           "exit — the size the app was last closed at, or the "
                           "smallest that shows the mirror uncompromised. Use it "
                           "to launch a right-sized window: "
                           "kitty -o initial_window_width=$(...)c …")
    misc.add_argument("--long-help", action="store_true",
                      help="print a full prose user manual and exit")

    args = parser.parse_args(argv)
    if args.print_size:
        cols, rows = startup_size()
        print(f"{cols}x{rows}")
        return
    if args.long_help:
        print(LONG_HELP.strip())
        return

    bridge = None if args.demo else _build_bridge(args)
    settle = args.settle / 1000.0 if args.settle is not None else None
    heartbeat = args.heartbeat / 1000.0 if args.heartbeat is not None else None
    app = K2KRemoteApp(bridge=bridge, demo=args.demo, model=args.model,
                       text_mode=args.text, settle=settle, heartbeat=heartbeat,
                       image_protocol=args.image_protocol, image_cols=args.image_cols,
                       alt_keys=args.alt_keys, super_alt_keys=args.super_alt_keys,
                       manual_refresh=args.manual_refresh,
                       mirror_panel=not args.no_panel_mirror)
    try:
        app.run()
    finally:
        if bridge is not None:
            bridge.close()


if __name__ == "__main__":
    main()
