#!/usr/bin/env python3
"""Author: Ahmed Ahmed. Independent dictionary/LRU model vs. C++ predictions."""
import collections
import pathlib
import random
import subprocess
import sys

def reference(events, bb, sb, tb, shift):
    bimodal = collections.defaultdict(lambda: 1)
    # OrderedDict keeps MRU ordering separately from physical way numbers.
    sets = collections.defaultdict(collections.OrderedDict)
    victim = collections.defaultdict(int)
    history = 0
    outputs = []
    for pc, flags, taken in events:
        if not flags & 1:
            outputs.append((1, 0, 0, -1, history, bimodal[0], victim[0]))
            continue
        address = pc >> shift
        index = address % (2**bb)
        mixed = (address ^ history) % (2**(sb+tb))
        row, tag = divmod(mixed, 2**tb)
        entries = sets[row]
        hit = tag in entries
        way = entries[tag][0] if hit else -1
        count = entries[tag][1] if hit else bimodal[index]
        prediction = int(count >= 2)
        bimodal[index] = max(0, min(3, bimodal[index] + (1 if taken else -1)))
        if hit:
            slot, value = entries.pop(tag)
            value = max(0, min(3, value + (1 if taken else -1)))
        else:
            used = {v[0] for v in entries.values()}
            if len(used) < 2:
                slot = min({0,1} - used)
            else:
                _, (slot, _) = entries.popitem(last=False)
            value = 2 if taken else 1
        entries[tag] = (slot, value)
        victim[row] = 1-slot
        history = (history*2 + taken) % (2**(sb+tb))
        outputs.append((prediction,row,tag,way,history,bimodal[index],victim[row]))
    return outputs

def main():
    executable = str(pathlib.Path(sys.argv[1]).resolve())
    total=0
    for config in [(12,9,6,0),(4,2,2,2),(2,1,1,0),(8,4,3,1)]:
        rng = random.Random(20261025)
        events=[]
        for i in range(10000):
            pc = rng.choice([rng.getrandbits(32),rng.randrange(256),0,0x44,0x90,0x6c])
            flags = rng.choice([1,1,1,1,0,4,8,2])
            events.append((pc,flags,rng.randrange(2)))
        payload=''.join(f'{pc} {flags} {taken}\n' for pc,flags,taken in events)
        result=subprocess.run([executable,*map(str,config)],input=payload,text=True,
                              capture_output=True,check=True)
        actual=[tuple(map(int,line.split())) for line in result.stdout.splitlines()]
        expected=reference(events,*config)
        assert len(actual)==len(expected)
        for i,(a,e) in enumerate(zip(actual,expected)):
            assert a==e, (config,i,events[i],a,e)
        total+=len(events)
        print(f'PASS independent reference: {config}, {len(events)} events')
    print(f'PASS {total} differential events in 4 configurations (seed 20261025)')
if __name__=='__main__': main()
