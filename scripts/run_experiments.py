#!/usr/bin/env python3
"""Run isolated, cold-start direction-prediction experiments on sorted traces.

Requires Python 3.8+, a C++17 compiler, make, and the trace decompressor.
No third-party Python packages are used. Each (predictor, trace) pair is run
in a new process. The 100,000,000-instruction denominator is the supplied
benchmark's documented trace length, not a count of branch records.
"""
import argparse
import concurrent.futures
import csv
import datetime
import hashlib
import json
import math
import os
import pathlib
import platform
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREDICTORS = ("pm2", "pm4", "bimodal", "gshare", "taken")
DETAIL_FIELDS = (
    "trace", "predictor", "instructions", "branch_count", "conditional_count",
    "direction_misses", "accuracy_pct", "misprediction_rate_pct", "mpki",
    "logical_storage_bits", "global_hits", "global_misses", "allocations",
    "replacements", "host_elapsed_seconds",
)
SUMMARY_FIELDS = (
    "predictor", "trace_count", "total_instructions", "branch_count",
    "conditional_count", "direction_misses", "accuracy_pct",
    "misprediction_rate_pct", "aggregate_mpki", "mean_trace_mpki",
    "mean_trace_accuracy_pct", "logical_storage_bits", "global_hits",
    "global_misses", "allocations", "replacements",
)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def positive_integer(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def command_version(command):
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        lines = (completed.stdout or completed.stderr).splitlines()
        return lines[0] if lines else "unavailable"
    except OSError:
        return "unavailable"


def validate_metrics(data, predictor, instructions):
    if data["predictor"] != predictor or data["instructions"] != instructions:
        raise ValueError("driver returned the wrong predictor or instruction count")
    for key in ("instructions", "branch_count", "conditional_count", "direction_misses",
                "logical_storage_bits", "global_hits", "global_misses",
                "allocations", "replacements"):
        if not isinstance(data[key], int) or data[key] < 0:
            raise ValueError("invalid nonnegative integer metric: " + key)
    conditional = data["conditional_count"]
    misses = data["direction_misses"]
    if not 0 <= misses <= conditional <= data["branch_count"]:
        raise ValueError("inconsistent branch/miss counts")
    expected_error = 100.0 * misses / conditional if conditional else 0.0
    expected_accuracy = 100.0 - expected_error if conditional else 0.0
    expected_mpki = 1000.0 * misses / instructions
    for key, expected in (("accuracy_pct", expected_accuracy),
                          ("misprediction_rate_pct", expected_error),
                          ("mpki", expected_mpki)):
        if not math.isclose(data[key], expected, rel_tol=1e-12, abs_tol=1e-10):
            raise ValueError("incorrect derived metric: " + key)
    if predictor.startswith("pm"):
        if data["global_hits"] + data["global_misses"] != conditional:
            raise ValueError("PM global-table probes do not sum to conditional branches")


def run_one(binary, trace_path, trace_label, predictor, instructions, output, raw_index):
    command = [str(binary), "--predictor", predictor, "--instructions", str(instructions),
               "--json", str(trace_path)]
    started = utc_now()
    start = time.perf_counter()
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    elapsed = time.perf_counter() - start
    record = {
        "command": command,
        "started_utc": started,
        "finished_utc": utc_now(),
        "returncode": completed.returncode,
        "host_elapsed_seconds": elapsed,
        "host_timing_note": "Host process runtime only; not simulated hardware latency or IPC.",
        "stderr": completed.stderr,
        "stdout": completed.stdout,
    }
    raw_path = output / "raw" / predictor / ("%02d_%s.json" % (raw_index, trace_path.parent.name))
    try:
        if completed.returncode:
            raise RuntimeError("driver exited with status %d: %s" %
                               (completed.returncode, completed.stderr.strip()))
        data = json.loads(completed.stdout)
        validate_metrics(data, predictor, instructions)
        record["metrics"] = data
        data = dict(data)
        data["trace"] = trace_label
        data["host_elapsed_seconds"] = elapsed
    except (KeyError, ValueError, TypeError, RuntimeError) as error:
        record["error"] = str(error)
        write_json(raw_path, record)
        raise RuntimeError("%s / %s: %s" % (trace_label, predictor, error)) from error
    write_json(raw_path, record)
    return data


def summarize(rows, predictor):
    selected = [row for row in rows if row["predictor"] == predictor]
    result = {"predictor": predictor, "trace_count": len(selected)}
    for key in ("branch_count", "conditional_count", "direction_misses", "global_hits",
                "global_misses", "allocations", "replacements"):
        result[key] = sum(row[key] for row in selected)
    instructions = sum(row["instructions"] for row in selected)
    conditional = result["conditional_count"]
    result["total_instructions"] = instructions
    result["misprediction_rate_pct"] = (100.0 * result["direction_misses"] / conditional
                                          if conditional else 0.0)
    result["accuracy_pct"] = (100.0 - result["misprediction_rate_pct"]
                              if conditional else 0.0)
    result["aggregate_mpki"] = 1000.0 * result["direction_misses"] / instructions
    result["mean_trace_mpki"] = sum(row["mpki"] for row in selected) / len(selected)
    result["mean_trace_accuracy_pct"] = sum(row["accuracy_pct"] for row in selected) / len(selected)
    storage_values = {row["logical_storage_bits"] for row in selected}
    if len(storage_values) != 1:
        raise ValueError("storage changes between traces for " + predictor)
    result["logical_storage_bits"] = storage_values.pop()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace-dir", type=pathlib.Path, default=ROOT / "traces")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "results")
    parser.add_argument("--jobs", type=positive_integer, default=2,
                        help="concurrent isolated driver processes (default: 2)")
    parser.add_argument("--instructions", type=positive_integer, default=100000000,
                        help="known instructions per trace (default: 100000000)")
    parser.add_argument("--predictors", nargs="+", choices=PREDICTORS, default=list(PREDICTORS))
    parser.add_argument("--no-build", action="store_true", help="use an already-built src/predict")
    arguments = parser.parse_args()
    trace_dir = arguments.trace_dir.resolve()
    output = arguments.output.resolve()
    predictors = list(dict.fromkeys(arguments.predictors))
    traces = sorted(path for path in trace_dir.rglob("*.trace*")
                    if path.is_file() and (path.name.endswith(".trace") or
                                          path.name.endswith(".trace.bz2") or
                                          path.name.endswith(".trace.gz")))
    if not traces:
        parser.error("no .trace, .trace.bz2, or .trace.gz files found under " + str(trace_dir))
    binary = ROOT / "src" / "predict"
    output.mkdir(parents=True, exist_ok=True)
    build_command = ["make", "-C", str(ROOT / "src"), "predict"]
    if not arguments.no_build:
        build = subprocess.run(build_command, text=True, capture_output=True, check=False)
        (output / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
        if build.returncode:
            print(build.stdout + build.stderr, file=sys.stderr)
            return build.returncode
    if not binary.is_file():
        parser.error("missing executable: " + str(binary))

    manifest = {
        "schema_version": 1,
        "status": "running",
        "started_utc": utc_now(),
        "invocation": [sys.executable] + sys.argv,
        "working_directory": str(pathlib.Path.cwd()),
        "source_root": str(ROOT),
        "environment": {
            "platform": platform.platform(), "machine": platform.machine(),
            "python": sys.version, "cpu_count": os.cpu_count(),
            "compiler": command_version([os.environ.get("CXX", "g++"), "--version"]),
            "make": command_version(["make", "--version"]),
            "bzip2": command_version(["bzip2", "--version"]),
        },
        "build_command": build_command if not arguments.no_build else None,
        "executable_sha256": sha256(binary),
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path)
                          for path in sorted((ROOT / "src").glob("*"))
                          if path.suffix in (".h", ".cc") or path.name == "Makefile"},
        "runner_sha256": sha256(pathlib.Path(__file__)),
        "predictors": predictors,
        "jobs": arguments.jobs,
        "trace_count": len(traces),
        "experiment_count": len(traces) * len(predictors),
        "instructions_per_trace": arguments.instructions,
        "instruction_count_source": "User-specified fixed denominator; default is the distributed benchmark's documented 100 million instructions per trace.",
        "process_isolation": "Fresh driver process and cold predictor state for every predictor/trace pair.",
        "trace_order": [str(path.relative_to(trace_dir)) for path in traces],
        "traces": [{"path": str(path.relative_to(trace_dir)), "bytes": path.stat().st_size,
                    "sha256": sha256(path)} for path in traces],
        "metric_formulas": {
            "accuracy_pct": "100 * (sum(conditional_count) - sum(direction_misses)) / sum(conditional_count)",
            "misprediction_rate_pct": "100 * sum(direction_misses) / sum(conditional_count)",
            "aggregate_mpki": "1000 * sum(direction_misses) / sum(instructions)",
            "mean_trace_mpki": "arithmetic mean of per-trace MPKI; equals aggregate MPKI when all trace instruction counts are equal",
            "mean_trace_accuracy_pct": "unweighted arithmetic mean of per-trace accuracy; differs from branch-weighted aggregate accuracy",
        },
        "timing_note": "Recorded elapsed seconds are host software process runtimes only; this is not a cycle-accurate simulation.",
    }
    write_json(output / "manifest.json", manifest)
    print("Running %d traces x %d predictors = %d isolated experiments (%d jobs)." %
          (len(traces), len(predictors), manifest["experiment_count"], arguments.jobs), flush=True)
    rows, failures = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=arguments.jobs) as executor:
        futures = []
        for index, path in enumerate(traces, 1):
            for predictor in predictors:
                futures.append(executor.submit(run_one, binary, path, str(path.relative_to(trace_dir)),
                                               predictor, arguments.instructions, output, index))
        for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                row = future.result()
                rows.append(row)
                print("[%3d/%d] %-9s %-35s %10.5f MPKI" %
                      (done, len(futures), row["predictor"], row["trace"], row["mpki"]), flush=True)
            except Exception as error:
                failures.append(str(error))
                print("[%3d/%d] FAILED %s" % (done, len(futures), error), file=sys.stderr, flush=True)
    rows.sort(key=lambda row: (row["trace"], predictors.index(row["predictor"])))
    write_csv(output / "detailed.csv", DETAIL_FIELDS, rows)
    write_json(output / "detailed.json", rows)
    manifest["finished_utc"] = utc_now()
    manifest["completed_experiments"] = len(rows)
    if failures:
        manifest["status"] = "failed"
        manifest["failures"] = failures
        write_json(output / "manifest.json", manifest)
        return 1
    # Every predictor must have read exactly the same branch records per trace.
    for trace in manifest["trace_order"]:
        counts = {(row["branch_count"], row["conditional_count"]) for row in rows if row["trace"] == trace}
        if len(counts) != 1:
            manifest["status"] = "failed"
            manifest["failures"] = ["cross-predictor branch counts differ for " + trace]
            write_json(output / "manifest.json", manifest)
            return 1
    summaries = [summarize(rows, predictor) for predictor in predictors]
    write_csv(output / "summary.csv", SUMMARY_FIELDS, summaries)
    write_json(output / "summary.json", summaries)
    manifest["status"] = "complete"
    write_json(output / "manifest.json", manifest)
    print("\nPredictor   Aggregate MPKI   Weighted accuracy   Logical bits")
    for summary in summaries:
        print("%-9s   %12.6f   %15.6f%%   %12d" %
              (summary["predictor"], summary["aggregate_mpki"], summary["accuracy_pct"],
               summary["logical_storage_bits"]))
    print("\nResults: " + str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
