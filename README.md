# Pentium M Style Branch Direction Predictor

**Author: Ahmed Ahmed**

This project completes `pm_predictor` in the supplied CBP2 infrastructure. It combines a 4,096-entry bimodal table with a 512-set tagged global predictor. The default has two ways; a four-way configuration is included for comparison. The package contains source, the 20 supplied traces, correctness checks, recorded experiment results, and a one-page report.

## Build and run

Requirements: Linux or another POSIX environment, a C++17 compiler (`g++`), `make`, Python 3, `bzip2`, and `gzip`. On Windows use WSL. The code has no third-party C++ dependencies. Python scripts use the standard library.

From this directory:

```bash
make -C src
./src/predict traces/164.gzip/gzip.trace.bz2
./src/predict traces/164.gzip/gzip.trace.bz2 --predictor pm4 --json
make -C src test
python3 scripts/replay_handout.py --output results/handout_replay.csv
python3 scripts/run_experiments.py --jobs 2 --output results
```

The last command runs all five predictors on all 20 traces. Each run starts a fresh process and fresh predictor state. The portable `./run traces` wrapper supports the original assignment workflow without `csh` or `dc`. See `python3 scripts/run_experiments.py --help` for options. To preserve the included results, choose a different output directory when rerunning.

Predictor names:

| Name | Design |
|---|---|
| `pm2` | Default hybrid, 512 sets and 2 ways |
| `pm4` | Same hybrid with 4 ways |
| `bimodal` | Same 4,096-counter fallback used by the hybrid |
| `gshare` | Supplied 32,768-counter, 15-bit gshare algorithm |
| `taken` | Always predict taken |

## Implementation

The assignment-facing class is `pm_predictor` in `src/my_predictor.h`, derived from `branch_predictor`. The implementation uses:

- Bimodal index: `PC & 0xFFF`; 2-bit counters start at 1 (weakly not taken).
- Global key: `(PC ^ GHR) & 0x7FFF`; set is `key >> 6`, tag is `key & 63`.
- 15-bit GHR of resolved conditional outcomes, initially zero.
- Global entries with valid bit, 6-bit tag, 2-bit saturating counter, and LRU state.
- A matching global entry overrides the bimodal prediction. A miss uses the bimodal prediction.
- Every conditional branch trains the bimodal counter and the matching global counter, or allocates a global entry on a miss. Allocation uses an invalid way first, then the least recently used way. A new counter is 2 if taken and 1 if not taken.
- Prediction-time index/tag/way are saved in `pm_update`; history changes only after training.
- Unconditional branches predict taken and do not train direction tables or GHR. Target prediction returns zero and is not evaluated.

This is the simplified predictor requested by the assignment, not an exact Pentium M hardware reconstruction. PIR, the undocumented hardware hash, loop prediction, target prediction, speculative state, and pipeline timing are outside scope. The main diagram implies a 15-bit key, while Appendix B's large drawing labels a 14-bit BHR; this implementation explicitly uses 15 bits. Raw PC bits follow the main diagram; the separate toy replay uses `PC >> 2` as in the toy diagram.

`gshare` preserves the starter algorithm's strong-not-taken initialization (counter 0). It has more logical storage than either hybrid and is a reference, not an equal-budget comparison. The hybrid's C++ array reserves up to four ways even in two-way mode; reported storage is ideal packed hardware state, not process memory.

## Results and reproducibility

`REPORT.md` and the one-page `report/Branch_Predictor_Report.docx` summarize what I implemented, the testing, and the results. `results/` contains detailed CSV/JSON outputs, summary metrics, exact commands, source/trace hashes, and environment information. Mispredictions are counted before updating the predictor.

Each provided trace represents 100 million instructions according to `doc/index.html`. MPKI is conditional direction misses divided by 100,000. Accuracy uses the number of conditional branches as its denominator. For another trace with a known instruction count, pass `--instructions N`; do not reuse the 100-million default without verifying that trace's provenance.

`tests/test_predictor.cc` checks the algorithm against an independent reference with timestamp-based LRU, as well as directed edge cases. `tests/test_driver.py` checks real trace decoding and metric/error handling. `scripts/replay_handout.py` reproduces the handout's 22 published final predictions and the omitted 23rd event using the handout's toy-specific rules. Those toy rules deliberately retain a victim counter on replacement; the production hybrid initializes new contexts from their observed outcome instead.

## Files and attribution

- `src/my_predictor.h`: implemented hybrid, bimodal and static baselines, modernized supplied gshare.
- `src/predict.cc`: command-line driver and exact metrics.
- `src/trace.cc`: original custom CBP2 decoder; file opening, shell quoting, decompressor status, and truncated-record checks hardened.
- `src/predictor.h`: supplied interface, with target getter return type corrected from `bool` to `unsigned int`.
- `doc/index.html`, `doc/README.original`, `src/compress/`, and `traces/`: supplied infrastructure and documentation, attributed to Daniel A. Jimenez. Their original notices are retained. Optional unimplemented extra-credit driver was excluded.
- No external cache implementation was used. Global cache and replacement code were written directly for this assignment.

Sources: the supplied *Assignment 1: Branch Predictor Implementation*, especially pages 2 and 5-11; supplied CBP2 documentation; and Milena Milenkovic, Aleksandar Milenkovic, and Jeffrey Kulick, *Demystifying Intel Branch Predictors* (the attached `milenkovic_WDDD02.pdf`). That attached paper studies Pentium III/Pentium 4 and is not the 2009 Pentium M paper cited by the assignment. The report does not attribute Pentium M dimensions to it.

This repository contains the assignment implementation, reproducible experiments, and a concise report.
