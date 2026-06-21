# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 20: drive the real Textual app against the hardware (headless)."""
import sys, asyncio; sys.path.insert(0, ".")
from probes.hw import connect
from k2kremote.app import K2KRemoteApp

async def go():
    bridge = connect()
    app = K2KRemoteApp(bridge=bridge, model="K2000R")
    async with app.run_test(size=(130, 40)) as pilot:
        # Wait for the worker to deliver a live frame.
        for _ in range(40):
            await pilot.pause(0.25)
            if app.last_render and set(app.last_render) != {"\n", chr(0x2800)}:
                break
        rows = app.last_render.split("\n")
        nonblank = sum(1 for r in rows if set(r) - {chr(0x2800)})
        print("title  :", app._titlebar_text().strip())
        print("braille rows with content:", nonblank, "/ 16")
        await pilot.press("alt+s")            # Setup mode
        await pilot.pause(0.5)
        print("after Alt+S status:", app.last_status.strip())
        await pilot.press("alt+p")            # back to Program
        await pilot.pause(0.5)
    bridge.close()

asyncio.run(go())
