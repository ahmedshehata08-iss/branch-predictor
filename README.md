# Branch Predictor Implementation

**Author: Ahmed Ahmed**  
Computer Architecture - Assignment 1  
Date: October 25, 2026

**Repository:** https://github.com/ahmedshehata08-iss/branch-predictor

This submission implements the required Pentium M-style hybrid **direction** predictor in `src/my_predictor.h`, using the supplied CBP2 infrastructure. Read the [19-page report](report/Ahmed_Ahmed_Branch_Prediction_Report.pdf) for eight before-and-after code snapshot pairs, tests, and measured results.

## Build and run

Requirements: Linux/WSL or a Unix-like environment, GNU Make, a C++17 compiler, Python 3, gzip, and bzip2. The supplied decoder uses `/bin/gzip`, `/usr/bin/bzip2`, and `/bin/cat`; change `src/trace.h` if these programs are elsewhere.

```sh
make -C src
./src/predict traces/164.gzip/gzip.trace.bz2
./src/predict traces/164.gzip/gzip.trace.bz2 pm --stats
./run traces
```

`predict TRACE` defaults to the completed hybrid predictor and prints `N.NNN MPKI`. `--stats` adds a JSON line with exact branch/miss counts, conditional accuracy, and global-hit/fallback accounting. Predictor choices: `pm`, `bimodal`, `gshare`, `always_taken`.

## Reproduce validation and benchmark results

```sh
make -C src test
make -C src sanitize
python3 run_comparison.py
```

The tests include 16 directed cases, 40,000 comparisons against an independent Python dictionary/LRU model in four configurations, and four CLI integration groups. AddressSanitizer and UndefinedBehaviorSanitizer check the directed tests. Leak detection is disabled in the sanitizer target because the execution container blocks the required process inspection; leak checking is not claimed.

The benchmark script runs all 20 supplied traces with each of the four predictors (80 runs) and recreates `results/benchmark_results.csv`, `results/raw_runs.json`, and `results/summary.json`. Each supplied trace represents 100 million instructions; the 20-trace suite therefore represents 2 billion instructions **per predictor**. This instruction denominator must be changed if different traces are used. Synthetic unit tests use miss counts/accuracy, not benchmark MPKI.

| Predictor | Mean MPKI | Pooled conditional accuracy |
|---|---:|---:|
| always_taken | 86.311688 | 37.3331% |
| bimodal | 10.298609 | 92.5227% |
| gshare | 6.305859 | 95.4216% |
| pm | 7.259603 | 94.7291% |

The hybrid reduces mean MPKI by 91.59% relative to the starter always-taken behavior and by 29.51% relative to bimodal. It improves on bimodal in 19 of 20 traces, but its mean MPKI is 15.12% higher than the supplied gshare. This is not an equal-storage comparison: gshare has 32,768 two-bit counters, whereas the hybrid uses a 4,096-counter bimodal table and 1,024 tagged global counters.

## Implementation choices

- Bimodal: 4,096 two-bit counters, index `PC & 0xfff`.
- Global: 512 sets, two ways per set, six-bit tags, one valid bit per way, two-bit counter per way, one LRU victim bit per set.
- History: 15 actual conditional outcomes, initially zero. `hash = (PC ^ history) & 0x7fff`, `row = hash >> 6`, `tag = hash & 0x3f`.
- The default uses raw PC bits as in the main assignment diagram. The small Appendix B address example uses a two-bit PC shift; `pm_predictor(4, 2, 2, 2)` supports that separate teaching configuration.
- Bimodal counters start at 1 (weakly not taken); global entries start invalid. A counter of 2 or 3 predicts taken.
- A valid matching global tag overrides bimodal. A global miss falls back to bimodal.
- Every conditional branch trains bimodal. Global hits train their matched counter; global misses allocate an invalid way first, otherwise the LRU way. New/replaced entries start at 2 for a taken result or 1 for a not-taken result, rather than inheriting the old entry's counter.
- Resolved global accesses refresh LRU. History shifts once, after training, using the actual outcome. Unconditional branches predict taken and do not train these direction tables or history.
- One prediction may be outstanding, matching the supplied serial `predict`/`update` driver. The model does not simulate speculative rollback.

The assignment does not prescribe every reset/allocation policy. These choices are documented and tested. They differ from the mixed initial counters and reused replacement counters in Appendix B, so that example is used to check address/hash arithmetic, not to claim identical predictions under different initial state.

## Required scope and limits

Implemented: `pm_predictor` constructor, prediction, update, bimodal, tagged two-way global predictor, hit priority, counters, replacement, history, tests, results, and report.

PIR/path hashing, loop prediction, target prediction, BTB, indirect target cache, and the complete `cpm_predictor` extra-credit design are excluded as allowed by the assignment. The original extra-credit stub is retained for provenance and is built only with `make -C src extra-credit`; it is not a completed predictor and is not used in results. Target prediction remains zero and target accuracy is not reported.

The model is educational and is not claimed to reproduce every detail of a commercial Pentium M. Six-bit tags permit intentional aliasing of different PC/history combinations. No speedup, power saving, or cycle timing is inferred from MPKI alone. The inherited decoder remains intended for the supplied valid CBP2 trace format; it is not a general corrupted-input validator.

## Files and provenance

- `src/my_predictor.h`: hybrid implementation, supplied gshare control, new bimodal/always-taken controls.
- `src/predict.cc`: selectable predictors and exact statistics.
- `src/trace.cc`: inherited trace decoding with file-open, filename-quoting, and subprocess-completion fixes.
- `src/Makefile`, `run`, `run_comparison.py`: build, tests, portable suite execution, and experiments.
- `tests/`: directed, differential, and CLI tests plus the C++ test adapter.
- `results/`: earlier recorded results; rerun `run_comparison.py` to regenerate outputs for the current implementation. Current measured tables are included in the PDF.
- `report/Ahmed_Ahmed_Branch_Prediction_Report.pdf`: current report, including embedded source snapshots and measured results.
- `traces/`: all 20 supplied compressed traces, unchanged.
- `doc/index.html` and `doc/README.original`: supplied CBP2 documentation; original attribution retained.

The new assignment implementation and report are attributed to Ahmed Ahmed. The underlying CBP2 infrastructure and gshare example are supplied course material; the CBP2 documentation credits Daniel A. Jimenez. No third-party cache implementation was copied.

## Report

The linked PDF contains eight before-and-after snapshot pairs, the worked branch sequence, validation evidence, and results for all 20 traces. The source snapshots were generated from actual source excerpts with their line numbers.

## GitHub submission

The code, README, PDF report, existing traces, and required test sources are maintained together at https://github.com/ahmedshehata08-iss/branch-predictor. Build products are excluded by `.gitignore`.

The current report is [Ahmed_Ahmed_Branch_Prediction_Report.pdf](report/Ahmed_Ahmed_Branch_Prediction_Report.pdf), and its tables contain the current measured benchmark evidence. Earlier repository reports, scripts, test files, and logs are retained as historical material; use the commands above to test and reproduce this version. Running `run_comparison.py` creates `results/benchmark_results.csv`, `results/raw_runs.json`, and an updated `results/summary.json`.
