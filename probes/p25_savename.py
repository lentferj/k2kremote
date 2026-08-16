# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 25: capture the Save -> Name page, and say why keyboard entry fails there.

Reported from live use 2026-08-02: on the name page reached through a **Save**,
keyboard input does not reach the K2000. The rename dialog reached from the
*editor* is the one every naming test used, and it works.

Two candidates, and this probe settles both by dumping the page and running the
real predicates against it:

1. ``app.is_name_dialog()`` keys off the soft-key row containing both ``Delete``
   **and** ``Insert``. If the Save flow's name page labels its keys differently,
   the app never opens the software name cursor and never shows the F9 hint.
2. ``text_entry._find_name_field()`` locates the editable cell by the literal
   label ``"Name:"``, else falls back to the observed Program-rename position
   **row 3, col 16**. A page that labels the field differently silently gets
   that fallback, so the feedback loop reads back the wrong cell.

**Nothing is committed.** The edit is net-zero (wheel +1 then -1, which leaves
the data identical but marks the program dirty so Exit offers to save), and the
probe backs out with Cancel/Exit without ever pressing a Save/OK/Enter on a
write page. It also refuses to continue if a screen looks like a destructive
confirm. Safe to run unattended.

    .venv/bin/python probes/p25_savename.py [program_id]
"""
import sys; sys.path.insert(0, ".")
import time

from probes.hw import connect
from k2kremote.app import is_name_dialog, soft_labels
from k2kremote.refresh import is_destructive_screen
from k2kremote.text_entry import _find_name_field
from k2000.definitions import Button

SETTLE = 0.9
PROGRAM = int(sys.argv[1]) if len(sys.argv) > 1 else 205

_DIGITS = {str(d): getattr(Button, f"Number{d}") for d in range(10)}
# Never press these while walking the Save flow: they commit a write.
_COMMIT = {"save", "ok", "yes", "rename", "write"}


class Walk:
    def __init__(self, bridge):
        self.b = bridge
        self.steps = []

    def press(self, button, settle=SETTLE):
        self.b.press_button(button)
        time.sleep(settle)

    def dump(self, tag):
        """Print the full 8x40 text layer plus both predicates' verdicts."""
        rows = self.b.get_screen_text().split("\n")
        labels = soft_labels(rows)
        name_dialog = is_name_dialog(rows)
        field = _find_name_field(rows)
        explicit = any("Name:" in r for r in rows)

        print(f"\n=== {tag} ===")
        for i, row in enumerate(rows):
            print(f"  {i}| {row.rstrip()}")
        print(f"  soft keys : {labels}")
        print(f"  is_name_dialog()   -> {name_dialog}"
              f"   (needs both 'delete' and 'insert' in the soft row)")
        print(f"  _find_name_field() -> {field}"
              f"   ({'from a literal Name: label' if explicit else 'FALLBACK (3, 16) — guessed'})")
        self.steps.append((tag, rows, labels, name_dialog, field, explicit))
        return rows, labels

    def soft(self, wanted, rows_labels):
        """Press the soft key whose label matches ``wanted``; False if absent."""
        _, labels = rows_labels
        keys = [Button.SoftA, Button.SoftB, Button.SoftC,
                Button.SoftD, Button.SoftE, Button.SoftF]
        for i, label in enumerate(labels):
            if wanted.lower() in label.lower():
                print(f"  -> pressing soft {i+1} ({label!r})")
                self.press(keys[i])
                return True
        print(f"  -> no soft key matching {wanted!r} on this page")
        return False


def main():
    b = connect()
    b.client.midi_out._gap = 0.2
    w = Walk(b)
    try:
        print(f"walking the Save flow for program {PROGRAM} — nothing will be committed")
        w.press(Button.Program)
        for ch in str(PROGRAM):
            w.press(_DIGITS[ch], 0.4)
        w.press(Button.Enter)
        w.dump("1. program selected")

        w.press(Button.Edit)
        w.dump("2. editor")

        # Net-zero edit: the data ends identical, but the program is now dirty,
        # so Exit offers the Save dialog.
        b.alpha_wheel(1); time.sleep(0.7)
        b.alpha_wheel(-1); time.sleep(0.7)

        w.press(Button.Exit)
        state = w.dump("3. save dialog (Exit from a dirty editor)")
        if is_destructive_screen(state[0]):
            print("\n!! destructive-looking screen — stopping here")
            return

        if not w.soft("yes", state):
            print("\n!! no 'Yes' on the save dialog; stopping")
            return
        state = w.dump("4. after Yes — the save-as page")

        # The name step: either a soft key called Name, or we are already on it.
        if not is_name_dialog(state[0]) and not w.soft("name", state):
            print("\n!! could not reach a name step from here")
        else:
            state = w.dump("5. THE SAVE -> NAME PAGE")

        print("\n" + "=" * 60)
        print("VERDICT")
        print("=" * 60)
        ref = next((s for s in w.steps if s[0].startswith("5.")), None)
        if ref is None:
            print("  never reached the name page — see the dumps above")
        else:
            tag, rows, labels, nd, field, explicit = ref
            print(f"  soft-key row : {labels}")
            print(f"  is_name_dialog() = {nd}")
            if not nd:
                missing = [k for k in ("delete", "insert")
                           if k not in {l.lower() for l in labels}]
                print(f"    -> CANDIDATE 1 CONFIRMED: the row lacks {missing}.")
                print("       The app never treats this as a name dialog, so the")
                print("       software cursor and the F9 hint never appear.")
            print(f"  _find_name_field() = {field}, "
                  f"{'literal Name: label' if explicit else 'FALLBACK — no Name: on the page'}")
            if not explicit:
                print("    -> CANDIDATE 2 CONFIRMED: the field position is guessed,")
                print("       so feedback reads back the wrong cell.")
    finally:
        # Back out without committing anything.
        print("\nbacking out (Cancel/Exit only, never a commit key)...")
        for _ in range(5):
            rows = b.get_screen_text().split("\n")
            labels = [l.lower() for l in soft_labels(rows)]
            if rows and rows[0].strip().startswith("ProgramMode"):
                break
            cancel = next((i for i, l in enumerate(labels) if "cancel" in l), None)
            if cancel is not None:
                b.press_button([Button.SoftA, Button.SoftB, Button.SoftC,
                                Button.SoftD, Button.SoftE, Button.SoftF][cancel])
            else:
                b.press_button(Button.Exit)
            time.sleep(SETTLE)
        b.press_button(Button.Program)
        time.sleep(SETTLE)
        final = b.get_screen_text().split("\n")
        print("final screen:", final[0].rstrip())
        b.close()


if __name__ == "__main__":
    main()
