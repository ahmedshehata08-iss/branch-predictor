# Branch Predictor Report

Author: Ahmed Ahmed

## What I did

I implemented the pm_predictor class in C++ using the supplied CBP2 framework. The predictor decides whether a conditional branch will be taken or not taken. It combines a bimodal table with 4,096 entries and a global table with 512 sets and two ways per set. A 15-bit history register records recent conditional branch outcomes.

When the global table finds a matching entry, I use its prediction. Otherwise, I use the bimodal prediction. Both tables use 2-bit counters that are updated after the actual outcome is known. If a global set is full, I replace its least recently used entry using LRU. I followed the assignment’s simplified design and did not implement loop or branch target prediction.

## Testing

I ran five predictor configurations on all 20 supplied traces, giving 100 complete runs. Each trace represents 100 million instructions. I measured conditional-branch prediction accuracy and MPKI, which means mispredictions per 1,000 instructions. I also tested counter updates, history tracking, and LRU replacement; the correctness checks passed.

## Results

| Predictor | Accuracy | MPKI |
| --- | --- | --- |
| Always taken | 37.33% | 86.312 |
| Bimodal | 92.52% | 10.299 |
| Hybrid with 2 ways | 94.73% | 7.260 |
| Hybrid with 4 ways | 95.20% | 6.605 |
| Gshare | 95.42% | 6.306 |

Higher accuracy and lower MPKI are better.

The two-way hybrid achieved 94.73% accuracy and reduced mispredictions by 29.51% compared with bimodal alone. It improved results on 19 of the 20 traces. Using four ways increased accuracy to 95.20%. Gshare achieved the best overall accuracy, but it used more predictor storage, so the comparison was not at an equal storage budget.

Overall, combining global history with the bimodal table improved prediction accuracy. The four-way version provided an additional improvement over the default two-way design.

Sources: Supplied Branch Predictor Implementation assignment and CBP2 infrastructure. I reused the supplied trace decoder and gshare algorithm; I wrote the hybrid table and LRU logic directly.
