#!/usr/bin/env python3
"""Replay the assignment's illustrative Appendix B example, not the production predictor.

The handout toy uses PC bits [5:2], a four-bit GHR, four global sets,
two ways, two tag bits, and unusual patterned initial counters. Its global
replacement changes the tag but retains and trains the victim's counter.
These toy-only conventions are intentionally separate from pm_predictor's
production configuration and allocation initialization.

The input history contains 23 branches; the handout's main final-prediction
table contains only the first 22. This script checks those 22 predictions
and emits all 23 steps. It does not use the inconsistent prediction labels
on some miss rows of the separate Global Predictor state table.
"""

import argparse
import csv
from pathlib import Path


ADDRESSES = {"b1": 0x44, "b2": 0x6C, "b3": 0x90}
HISTORY = [
    ("b1", 1), ("b3", 1), ("b1", 0), ("b2", 0), ("b3", 1),
    ("b1", 1), ("b3", 1), ("b1", 0), ("b2", 0), ("b3", 1),
    ("b1", 0), ("b2", 1), ("b1", 0), ("b2", 0), ("b3", 1),
    ("b1", 1), ("b3", 1), ("b1", 0), ("b2", 0), ("b3", 1),
    ("b1", 1), ("b3", 1), ("b1", 0),
]
EXPECTED_FINAL = (
    "NT NT T T NT T T T T T T NT NT NT T T T NT NT T T T".split()
)


def direction(taken):
    return "T" if taken else "NT"


def train(counter, taken):
    return min(3, counter + 1) if taken else max(0, counter - 1)


def replay():
    ghr = 0
    bimodal = [index % 4 for index in range(16)]
    global_table = [
        [
            {"valid": False, "tag": 0, "counter": row, "last_use": -2},
            {"valid": False, "tag": 0, "counter": 3 - row, "last_use": -1},
        ]
        for row in range(4)
    ]
    records = []
    for step, (branch, taken) in enumerate(HISTORY, start=1):
        pc = ADDRESSES[branch]
        local_index = (pc >> 2) & 0xF
        key = local_index ^ ghr
        row_index, tag = key >> 2, key & 3
        ways = global_table[row_index]
        hit_way = next(
            (way for way, entry in enumerate(ways)
             if entry["valid"] and entry["tag"] == tag),
            None,
        )
        local_prediction = bimodal[local_index] >= 2
        global_prediction = (
            ways[hit_way]["counter"] >= 2 if hit_way is not None else None
        )
        final_prediction = (
            global_prediction if hit_way is not None else local_prediction
        )
        expected = EXPECTED_FINAL[step - 1] if step <= len(EXPECTED_FINAL) else ""
        if expected and direction(final_prediction) != expected:
            raise AssertionError(
                f"Step {step}: expected {expected}, got {direction(final_prediction)}"
            )

        # Use invalid ways first, then exact LRU; deterministic way-zero tie break.
        if hit_way is not None:
            selected_way = hit_way
        else:
            selected_way = next(
                (way for way, entry in enumerate(ways) if not entry["valid"]),
                min(range(2), key=lambda way: ways[way]["last_use"]),
            )
        selected_entry = ways[selected_way]
        counter_before = selected_entry["counter"]
        bimodal_before = bimodal[local_index]
        ghr_before = ghr

        bimodal[local_index] = train(bimodal_before, taken)
        selected_entry["valid"] = True
        selected_entry["tag"] = tag
        selected_entry["counter"] = train(counter_before, taken)
        selected_entry["last_use"] = step
        ghr = ((ghr << 1) | taken) & 0xF

        records.append({
            "step": step,
            "branch": branch,
            "pc_hex": f"0x{pc:02X}",
            "actual": direction(taken),
            "ghr_before": f"{ghr_before:04b}",
            "local_index": local_index,
            "xor_key": f"{key:04b}",
            "global_set": row_index,
            "global_tag": f"{tag:02b}",
            "global_hit": int(hit_way is not None),
            "global_hit_way": hit_way if hit_way is not None else "",
            "bimodal_prediction": direction(local_prediction),
            "global_prediction": direction(global_prediction) if hit_way is not None else "No hit",
            "final_prediction": direction(final_prediction),
            "handout_final_prediction": expected,
            "matches_handout": int(direction(final_prediction) == expected) if expected else "",
            "correct": int(final_prediction == bool(taken)),
            "updated_way": selected_way,
            "global_counter_before": counter_before,
            "global_counter_after": selected_entry["counter"],
            "bimodal_counter_before": bimodal_before,
            "bimodal_counter_after": bimodal[local_index],
            "ghr_after": f"{ghr:04b}",
        })
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] / "results" / "handout_replay.csv",
        help="CSV destination (default: results/handout_replay.csv under project root)",
    )
    args = parser.parse_args()
    records = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    misses = sum(not record["correct"] for record in records)
    print("PASS: all 22 published final predictions match the handout.")
    print(f"Full 23-branch history: {misses} misses, {len(records) - misses} correct.")
    print("Branch 23 is absent from the handout result table; replay predicts NT correctly.")
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
