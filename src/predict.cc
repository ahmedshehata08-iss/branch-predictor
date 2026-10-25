// Assignment implementation author: Ahmed Ahmed
// CBP2 driver extended with selectable baselines and exact statistics.
#include <cstdio>
#include <cstring>
#include <memory>
#include "branch.h"
#include "trace.h"
#include "predictor.h"
#include "my_predictor.h"

int main(int argc, char *argv[]) {
    if (argc < 2 || argc > 4) {
        std::fprintf(stderr, "Usage: %s TRACE [pm|bimodal|gshare|always_taken] [--stats]\n", argv[0]);
        return 1;
    }
    const char *mode = "pm";
    bool detailed = false, mode_set = false;
    for (int i = 2; i < argc; ++i) {
        if (std::strcmp(argv[i], "--stats") == 0 && !detailed) detailed = true;
        else if (!mode_set && argv[i][0] != '-') { mode = argv[i]; mode_set = true; }
        else { std::fprintf(stderr, "Invalid argument: %s\n", argv[i]); return 1; }
    }
    std::unique_ptr<branch_predictor> predictor;
    if (std::strcmp(mode, "pm") == 0) predictor.reset(new pm_predictor());
    else if (std::strcmp(mode, "bimodal") == 0) predictor.reset(new bimodal_predictor());
    else if (std::strcmp(mode, "gshare") == 0) predictor.reset(new gshare_predictor());
    else if (std::strcmp(mode, "always_taken") == 0) predictor.reset(new always_taken_predictor());
    else { std::fprintf(stderr, "Unknown predictor: %s\n", mode); return 1; }
    const bool is_pm = std::strcmp(mode, "pm") == 0;
    unsigned long long branches = 0, conditional = 0, misses = 0;
    unsigned long long hits = 0, hit_misses = 0, fallback_misses = 0;
    init_trace(argv[1]);
    while (trace *t = read_trace()) {
        branch_update *result = predictor->predict(t->bi);
        ++branches;
        if (t->bi.br_flags & BR_CONDITIONAL) {
            ++conditional;
            const bool wrong = result->direction_prediction() != t->taken;
            misses += wrong;
            if (is_pm) {
                const bool hit = static_cast<pm_update *>(result)->way >= 0;
                hits += hit;
                if (hit) hit_misses += wrong;
                else fallback_misses += wrong;
            }
        }
        predictor->update(result, t->taken, t->target);
    }
    end_trace();
    // The supplied CBP2 traces each represent 100 million instructions.
    const double mpki = 1000.0 * static_cast<double>(misses) / 100000000.0;
    const double accuracy = conditional
        ? 100.0 * (1.0 - static_cast<double>(misses) / conditional) : 0.0;
    if (detailed) {
        std::printf("{\"predictor\":\"%s\",\"branches\":%llu,"
                    "\"conditional\":%llu,\"misses\":%llu,"
                    "\"accuracy_pct\":%.9f,\"mpki\":%.9f,"
                    "\"global_hits\":%llu,\"global_misses\":%llu,"
                    "\"hit_mispredictions\":%llu,\"fallback_mispredictions\":%llu}\n",
                    mode, branches, conditional, misses, accuracy, mpki,
                    hits, is_pm ? conditional - hits : 0,
                    hit_misses, fallback_misses);
    }
    std::printf("%.3f MPKI\n", mpki);
    return 0;
}
