# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe 13: does bridge.panic() actually silence a held note? (JACK audio)

CLOSED as an open question 2026-08-16 — kept as a record of the method, not as
something anyone needs to run. panic() sends CC 120 + CC 123 on all 16 channels
and that is unit-tested; whether the K2000 honours them is a ten-second by-ear
check (hold a note, press panic, listen), and automating it needs a physical
audio path no CI machine has. CAPTURE below points at ports the K2000 is not
routed to; repoint it at live ones before expecting anything. See
RESOLUTION_NOTES §4.
"""
import sys, time, threading; sys.path.insert(0, ".")
import numpy as np
from probes.hw import connect

CAPTURE = ("system:capture_17", "system:capture_18")
def record(seconds, out):
    import jack
    c = jack.Client("k2kpanic"); ins=[c.inports.register(f"in{i}") for i in range(2)]
    chunks=[[],[]]
    @c.set_process_callback
    def _p(_n):
        for i,p in enumerate(ins): chunks[i].append(p.get_array().copy())
    sr=c.samplerate; c.activate()
    for s,d in zip(CAPTURE, ins):
        try: c.connect(s,d)
        except Exception: pass
    time.sleep(seconds); c.deactivate(); c.close()
    L=np.concatenate(chunks[0]) if chunks[0] else np.zeros(1)
    out['sr']=sr; out['L']=L

b = connect()
mout = b.client.midi_out
ch = 8  # channel 9 (0-based 8)
rec={}; t=threading.Thread(target=record, args=(3.6, rec)); t.start()
time.sleep(0.5); mout.send_message([0x90|ch, 60, 110])   # note on (held)
time.sleep(1.3); b.panic()                                # panic mid-sustain
time.sleep(1.8); t.join()
mout.send_message([0x80|ch, 60, 0]); b.close()

L, sr = rec['L'], rec['sr']
def rms(t0,t1): 
    seg=L[int(t0*sr):int(t1*sr)]; return float(np.sqrt(np.mean(seg**2))) if len(seg) else 0.0
before = rms(0.8, 1.7)   # note sounding, before panic (~1.8s)
after  = rms(2.3, 3.4)   # after panic
print(f"samplerate={sr}  RMS sounding={before:.5f}  RMS after panic={after:.5f}")
print("PANIC SILENCED NOTE" if before > 5*max(after,1e-9) and before > 1e-4 else "INCONCLUSIVE")
