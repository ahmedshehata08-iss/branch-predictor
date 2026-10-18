#!/usr/bin/env python3
"""Integration checks for decoding, conditional-only metrics, and I/O errors."""
import bz2
import json
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'src' / 'predict'


def run(path, *args):
    return subprocess.run([str(EXE), str(path), *args], capture_output=True, text=True)


def main():
    # Full nine-byte records are valid inputs to the original CBP2 decoder.
    # Two conditional branches (one taken) and one unconditional branch.
    data = b''.join(struct.pack('<BII', code, pc, target) for code, pc, target in [
        (0x10, 0x100, 0x200), (0x20, 0x104, 0x106), (0x30, 0x108, 0x100)])
    with tempfile.TemporaryDirectory() as temp:
        # Exercise shell quoting without embedding a shell command in the filename.
        trace = Path(temp) / "a trace's input.bz2"
        trace.write_bytes(bz2.compress(data))
        r = run(trace, '--predictor', 'taken', '--json', '--instructions', '100')
        assert r.returncode == 0, r.stderr
        m = json.loads(r.stdout)
        assert m['conditional_count'] == 2, m
        assert m['direction_misses'] == 1, m
        assert m['accuracy_pct'] == 50.0, m
        assert m['mpki'] == 10.0, m
        plain = Path(temp) / 'plain.trace'
        plain.write_bytes(data)
        r = run(plain, '--predictor', 'taken', '--instructions', '100')
        assert r.returncode == 0 and r.stdout.strip().endswith('10.000 MPKI'), r
        assert run(Path(temp) / 'missing.trace').returncode != 0
        empty = Path(temp) / 'empty.trace'
        empty.write_bytes(b'')
        assert run(empty).returncode != 0
        truncated = Path(temp) / 'truncated.trace'
        truncated.write_bytes(data[:-1])
        assert run(truncated).returncode != 0
        damaged = Path(temp) / 'damaged.bz2'
        damaged.write_bytes(bz2.compress(data)[:-6])
        assert run(damaged).returncode != 0
    print('PASS: 7 driver integration checks (metrics, plain/compressed input, quoting, missing/empty/truncated/damaged files)')


if __name__ == '__main__':
    main()
