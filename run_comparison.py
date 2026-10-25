#!/usr/bin/env python3
"""Author: Ahmed Ahmed. Run every supplied benchmark and preserve exact metrics."""
import csv
import json
import pathlib
import platform
import subprocess
import time
root=pathlib.Path(__file__).resolve().parent
out=root/'results'; out.mkdir(exist_ok=True)
subprocess.run(['make','-C',str(root/'src')],check=True)
rows=[]; raw=[]
for trace in sorted((root/'traces').rglob('*.trace.bz2')):
    for mode in ['always_taken','bimodal','gshare','pm']:
        start=time.perf_counter()
        command=[str(root/'src/predict'),str(trace),mode,'--stats']
        result=subprocess.run(command,capture_output=True,text=True,check=True)
        data=json.loads(result.stdout.splitlines()[0])
        assert data['conditional']>0 and data['misses']<=data['conditional']
        if mode=='pm':
            assert data['global_hits']+data['global_misses']==data['conditional']
            assert data['hit_mispredictions']+data['fallback_mispredictions']==data['misses']
        data={'benchmark':trace.parent.name,**data}
        rows.append(data)
        raw.append({'command':['./src/predict',str(trace.relative_to(root)),mode,'--stats'],
                    'stdout':result.stdout,'stderr':result.stderr,
                    'elapsed_seconds':round(time.perf_counter()-start,4)})
        print(f"{data['benchmark']:14s} {mode:12s} {data['mpki']:.5f} MPKI",flush=True)
with (out/'benchmark_results.csv').open('w',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
(out/'raw_runs.json').write_text(json.dumps(raw,indent=2)+'\n')
summary={}
for mode in ['always_taken','bimodal','gshare','pm']:
    selected=[r for r in rows if r['predictor']==mode]
    misses=sum(r['misses'] for r in selected); conditional=sum(r['conditional'] for r in selected)
    summary[mode]={'traces':len(selected),'misses':misses,'conditional':conditional,
                   'mean_mpki':sum(r['mpki'] for r in selected)/len(selected),
                   'pooled_accuracy_pct':100*(1-misses/conditional)}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
compiler=subprocess.run(['g++','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
(out/'environment.txt').write_text('Author: Ahmed Ahmed\nRun date: 2026-10-25\n'+platform.platform()+'\n'+compiler+'\nPython '+platform.python_version()+'\n')
print(json.dumps(summary,indent=2))
