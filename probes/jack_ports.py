# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.
"""Resolve a legacy ``system:capture_N`` name against the live port list.

This machine moved from jackd to PipeWire on 2026-09-26.  The JACK API still
works through the ``pipewire-jack`` shim, but **the ``system:*`` ports are
gone**: the Scarlett 18i8's inputs now appear under the card's own node, e.g.

    system:capture_17   ->   Scarlett 18i8 3rd Gen Mehrkanal:capture_AUX16

Every audio probe here hard-coded ``system:capture_17/18``, so every one of
them would fail to connect.

Two things this deliberately does NOT do:

* **It does not hard-code the new name.**  That string is a German-locale
  device description ("Mehrkanal"); a locale change would break it just as
  the transition broke ``system:*``.  Matching on the ``:capture_AUXn``
  suffix is locale-proof and survives the card being renamed.
* **It does not assume the transition has happened.**  If a real
  ``system:capture_N`` is present -- another machine, or a rollback per
  ``~/Dokumente/jack2pipewire_transition/RUNBOOK.md`` -- that is used
  unchanged.

Failure is loud and names what was looked for, because the alternative is a
probe that records two channels of silence and reports a number about it.

**The physical input is unchanged -- checked, not assumed.**  A resolved *name*
is not a resolved *channel*, and the K2000R sits on specific Scarlett inputs.
``jack_lsp -A`` shows each port's hw alias and capture is identity-mapped::

    Scarlett ...:capture_AUX16   ->  alsa:pcm:2:hw:2:capture:capture_16
    Scarlett ...:capture_AUX17   ->  alsa:pcm:2:hw:2:capture:capture_17

jackd's ``system:capture_N`` was hw channel N-1 (ALSA counts from 0), so
``system:capture_17/18`` and ``capture_AUX16/17`` are the same two jacks.  The
node opens ``hw:2`` directly with no route plugin.  **Only the playback side was
reordered** (it goes through ALSA's USB surround71 route, so FC/LFE land on hw
2/3 and RL/RR on hw 4/5) -- these probes only capture, so that does not reach
them.

**Why the presence test uses a listing and nothing else.** ``pipewire-jack``
*aliases* ``system:*`` onto the current default source by port index, so several
obvious ways of asking "is the legacy port there?" answer **yes** and hand back a
different device.  Verified live here:

    {p.name for p in client.get_ports(...)} contains "system:capture_17"  ->  False
    client.get_port_by_name("system:capture_17").name
        -> 'Scarlett 18i8 3rd Gen Mehrkanal:capture_AUX16'     <- alias resolved!
    client.get_ports("system:.*")  -> all 36 Scarlett ports
    jack_lsp                       -> no "system:" line at all

Only the **listing** tells the truth.  So: never use ``get_port_by_name``, never
a ``system:`` regex filter, and never "``connect`` did not raise" as a presence
test.  Today the capture alias happens to land on the right physical input
because the Scarlett multichannel node is the default source — if that default
ever changes, a probe would silently record a different device with no error.
(Alias behaviour found by ``s3ked``, relayed and independently confirmed here.)

``connect_capture`` therefore also reads the connection back after making it,
because resolving the right *name* is not evidence that the *connection* landed.
"""
import re
from typing import List

_LEGACY = re.compile(r"system:capture_(\d+)$")


def resolve_capture(client, name: str) -> str:
    """Return the live port matching `name`, which may be a legacy name.

    `client` is an active ``jack.Client``.  Raises RuntimeError naming the
    candidates it looked for rather than returning something plausible.
    """
    live = {p.name for p in client.get_ports(is_audio=True, is_output=True)}
    if name in live:
        return name

    m = _LEGACY.match(name)
    if not m:
        raise RuntimeError(
            f"capture port {name!r} not found and not a system:capture_N name; "
            f"live audio sources: {sorted(live)}")

    # system:capture_N is 1-based, the AUX index is 0-based
    suffix = f":capture_AUX{int(m.group(1)) - 1}"
    hits: List[str] = sorted(p for p in live if p.endswith(suffix))
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise RuntimeError(
            f"neither {name!r} nor any port ending {suffix!r} is live. "
            f"Audio sources present: {sorted(live)}. "
            f"Old->new map: ~/Dokumente/jack2pipewire_transition/state/"
            f"system-port-map.txt")
    raise RuntimeError(
        f"{name!r} is ambiguous after the PipeWire move: {hits}. "
        f"Name the port explicitly.")


def connect_capture(client, name: str, dest) -> str:
    """Resolve `name`, connect it to `dest`, and **read the connection back**.

    Returns the resolved source name.  Raises if the connection is not present
    afterwards -- `connect` not raising is not evidence that anything is wired,
    and a probe whose input is unconnected records silence and then measures it.
    (Read-back guard from ``s3ked``.)
    """
    src = resolve_capture(client, name)
    client.connect(src, dest)
    wired = {p.name for p in client.get_all_connections(dest)}
    if src not in wired:
        raise RuntimeError(
            f"connected {src!r} -> {dest} but the connection is not there; "
            f"{dest} reports {sorted(wired) or 'nothing'}")
    return src
