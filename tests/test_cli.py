#!/usr/bin/env python3
"""Author: Ahmed Ahmed. Driver, metrics, and safe trace-path integration tests."""
import bz2
import json
import pathlib
import struct
import subprocess
import sys
import tempfile
exe=str(pathlib.Path(sys.argv[1]).resolve())
def run(*args):
    return subprocess.run([exe,*map(str,args)],capture_output=True,text=True)
with tempfile.TemporaryDirectory() as td:
    root=pathlib.Path(td)
    trace=root/"case with space and ' apostrophe.trace.bz2"
    # Four explicit CBP records: T, NT, NT, unconditional.
    payload=b''.join(struct.pack('<BII',code,0x44,0x80) for code in [0x10,0x20,0x20,0x30])
    trace.write_bytes(bz2.compress(payload))
    r=run(trace,'always_taken','--stats'); assert r.returncode==0,r.stderr
    data=json.loads(r.stdout.splitlines()[0])
    assert (data['branches'],data['conditional'],data['misses'])==(4,3,2)
    assert abs(data['accuracy_pct']-100/3)<1e-7
    assert abs(data['mpki']-0.00002)<1e-12
    print('PASS compressed trace with spaces/apostrophe and exact conditional metrics')
    r=run(trace); assert r.returncode==0 and r.stdout.strip().endswith('MPKI')
    assert len(r.stdout.splitlines())==1
    print('PASS original one-trace command and MPKI output format')
    assert run().returncode!=0
    assert run(trace,'unknown').returncode!=0
    assert run(trace,'--invalid').returncode!=0
    assert run(root/'missing.trace').returncode!=0
    print('PASS argument and missing-file errors')
    bad=root/'broken.bz2'; bad.write_bytes(b'BZnot-a-valid-bzip-stream')
    r=run(bad); assert r.returncode!=0 and 'MPKI' not in r.stdout
    print('PASS decompression failure is not reported as a zero-miss result')
print('PASS 4 CLI integration groups')
