# Branch Predictor Report

**Author: Ahmed Ahmed**

Repository: https://github.com/ahmedshehata08-iss/branch-predictor

The current report is [Ahmed_Ahmed_Branch_Prediction_Report.pdf](report/Ahmed_Ahmed_Branch_Prediction_Report.pdf). Its 19 pages include eight before-and-after code snapshot pairs, design choices, a worked branch sequence, validation evidence, and results for all 20 supplied traces.

I implemented a 4,096-entry bimodal table and a tagged global predictor with 512 sets and two ways. A global hit supplies the prediction; a miss uses the bimodal result. Two-bit counters, actual-outcome history, and invalid-first/LRU replacement complete the required direction-prediction model.

| Predictor | Mean MPKI | Pooled conditional accuracy |
| --- | ---: | ---: |
| Always taken | 86.311688 | 37.3331% |
| Bimodal | 10.298609 | 92.5227% |
| Hybrid, two ways | 7.259603 | 94.7291% |
| Supplied gshare | 6.305859 | 95.4216% |

I compared four predictors on 20 traces, producing 80 benchmark runs. Validation includes 16 directed tests, 40,000 comparisons with an independent reference model, four CLI integration groups, and AddressSanitizer/UndefinedBehaviorSanitizer checks. Leak detection was disabled as documented in the full report.

See [README.md](README.md) for build and reproduction commands. The earlier Word report and differently named historical results remain available, but the linked PDF describes the current code. The current [benchmark CSV](results/benchmark_results.csv), [raw run JSON](results/raw_runs.json), [test log](results/test_output.txt), [toy trace](results/toy_trace.csv), [source patch](results/code_changes.patch), and [baseline source](baseline/) are committed alongside the PDF. Report snapshots and the builder are in [report/](report/). Run `python3 run_comparison.py` to regenerate the benchmark outputs.
