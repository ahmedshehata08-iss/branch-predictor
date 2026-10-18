// Deterministic algorithm tests. No external framework or trace files required.
// Build from the project root:
//   g++ -std=c++17 -O2 -Wall -Wextra -pedantic -Isrc tests/test_predictor.cc -o test_predictor
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

#include "branch.h"
#include "predictor.h"
#include "my_predictor.h"

namespace {
std::uint64_t checks = 0;
unsigned groups = 0;
void check(bool condition, const char *expression, unsigned line) {
    ++checks;
    if (!condition) {
        throw std::runtime_error("line " + std::to_string(line) + ": " + expression);
    }
}
#define CHECK(expression) check(bool(expression), #expression, __LINE__)

branch_info branch(unsigned pc, unsigned flags = BR_CONDITIONAL) {
    branch_info b{};
    b.address = pc;
    b.br_flags = flags;
    return b;
}

bool step(branch_predictor &predictor, unsigned pc, bool outcome,
          unsigned flags = BR_CONDITIONAL) {
    branch_info b = branch(pc, flags);
    branch_update *u = predictor.predict(b);
    bool prediction = u->direction_prediction();
    predictor.update(u, outcome, 0);
    return prediction;
}

// Make the next PM lookup address a selected set/tag under the current GHR.
bool context_step(pm_predictor &p, unsigned set, unsigned tag, bool outcome) {
    return step(p, ((set << 6) | tag) ^ p.history(), outcome);
}

int find_tag(const pm_predictor &p, unsigned set, unsigned tag) {
    for (unsigned w = 0; w < p.ways(); ++w) {
        const auto &e = p.global_entry(set, w);
        if (e.valid && e.tag == tag) return static_cast<int>(w);
    }
    return -1;
}

void test_counters_and_cold_fallback() {
    ++groups;
    for (unsigned initial = 0; initial < 4; ++initial) {
        for (unsigned outcome = 0; outcome < 2; ++outcome) {
            std::uint8_t value = static_cast<std::uint8_t>(initial);
            train_counter(value, outcome != 0);
            unsigned expected = outcome ? (initial == 3 ? 3 : initial + 1)
                                        : (initial == 0 ? 0 : initial - 1);
            CHECK(value == expected);
        }
    }
    pm_predictor p;
    branch_info b = branch(7);
    auto *u = static_cast<pm_update *>(p.predict(b));
    CHECK(u->hit_way == -1);
    CHECK(!u->direction_prediction());
    CHECK(!u->bimodal_prediction);
    CHECK(p.stats().global_hits == 0 && p.stats().global_misses == 0);
    p.update(u, true, 0);
    CHECK(p.bimodal_counter(7) == 2);
    CHECK(p.global_entry(0, 0).counter == 2);
    CHECK(p.stats().allocations == 1);
    for (unsigned i = 0; i < 32; ++i) step(p, 7, true);
    CHECK(p.bimodal_counter(7) == 3);
    for (unsigned i = 0; i < 32; ++i) step(p, 7, false);
    CHECK(p.bimodal_counter(7) == 0);

    pm_predictor q;
    for (unsigned i = 0; i < 16; ++i) context_step(q, 20, 11, true);
    int way = find_tag(q, 20, 11);
    CHECK(way >= 0);
    CHECK(q.global_entry(20, unsigned(way)).counter == 3);
    for (unsigned i = 0; i < 16; ++i) context_step(q, 20, 11, false);
    CHECK(q.global_entry(20, unsigned(way)).counter == 0);
}

void test_global_override() {
    ++groups;
    pm_predictor p;
    CHECK(!step(p, 0, true)); // Train global context 0 toward taken.
    branch_info b = branch(1); // GHR=1: still context 0, untouched bimodal slot 1.
    auto *u = static_cast<pm_update *>(p.predict(b));
    CHECK(u->hit_way >= 0);
    CHECK(!u->bimodal_prediction);
    CHECK(u->direction_prediction());
    p.update(u, false, 0);
    context_step(p, 0, 0, false); // Global context 0 is now strongly not taken.
    // Restore GHR=0 without changing bimodal slot 0 or global set 0.
    for (unsigned i = 0; i < 15; ++i) context_step(p, 511, 62, false);
    CHECK(p.history() == 0);
    b = branch(0);
    u = static_cast<pm_update *>(p.predict(b));
    CHECK(u->hit_way >= 0);
    CHECK(u->bimodal_prediction);
    CHECK(!u->direction_prediction());
    p.update(u, false, 0);
}

void test_prediction_indices_and_history() {
    ++groups;
    pm_predictor p;
    branch_info b = branch(0x1234);
    auto *u = static_cast<pm_update *>(p.predict(b));
    const unsigned old_set = u->global_set;
    const unsigned old_tag = u->tag;
    CHECK(old_set == (0x1234u >> 6));
    CHECK(old_tag == (0x1234u & 63));
    CHECK(u->bimodal_index == 0x234);
    p.update(u, true, 0);
    CHECK(p.history() == 1);
    CHECK(find_tag(p, old_set, old_tag) >= 0);
    CHECK(find_tag(p, old_set, old_tag ^ 1) < 0);
    CHECK(p.bimodal_counter(0x234) == 2);

    const auto before = p.stats();
    const auto saved = p.global_entry(old_set, 0);
    for (unsigned flag : {0u, unsigned(BR_CALL), unsigned(BR_RETURN), unsigned(BR_INDIRECT)}) {
        CHECK(step(p, 0x1234, false, flag));
        CHECK(step(p, 0xFFFF, true, flag));
        CHECK(p.history() == 1);
        CHECK(p.bimodal_counter(0x234) == 2);
        CHECK(p.global_entry(old_set, 0).counter == saved.counter);
        CHECK(p.global_entry(old_set, 0).rank == saved.rank);
    }
    CHECK(p.stats().global_hits == before.global_hits);
    CHECK(p.stats().global_misses == before.global_misses);
    CHECK(p.stats().allocations == before.allocations);
    CHECK(p.stats().replacements == before.replacements);
    // Conditional branches remain conditional even when another flag is set.
    step(p, 12, true, BR_CONDITIONAL | BR_INDIRECT);
    CHECK(p.history() == 3);
}

void test_invalid_way_preference_and_lru(unsigned ways) {
    ++groups;
    pm_predictor p(ways);
    constexpr unsigned set = 57;
    for (unsigned tag = 0; tag < ways; ++tag) {
        context_step(p, set, tag, tag % 2 != 0);
        CHECK(find_tag(p, set, tag) == static_cast<int>(tag));
        CHECK(p.stats().replacements == 0);
        for (unsigned earlier = 0; earlier <= tag; ++earlier)
            CHECK(find_tag(p, set, earlier) >= 0);
        for (unsigned unused = tag + 1; unused < ways; ++unused)
            CHECK(!p.global_entry(set, unused).valid);
    }
    // Touch the oldest entry, so the second inserted entry becomes the LRU.
    context_step(p, set, 0, true);
    context_step(p, set, ways, false);
    CHECK(find_tag(p, set, 0) >= 0);
    CHECK(find_tag(p, set, 1) == -1);
    CHECK(find_tag(p, set, ways) == 1);
    CHECK(p.global_entry(set, 1).counter == 1); // Fresh NT initialization.
    CHECK(p.stats().replacements == 1);
    if (ways == 4) {
        context_step(p, set, 2, true);
        context_step(p, set, 5, true);
        CHECK(find_tag(p, set, 3) == -1);
        CHECK(find_tag(p, set, 5) == 3);
        CHECK(p.global_entry(set, 3).counter == 2); // Fresh T initialization.
    } else {
        context_step(p, set, 0, true);
        context_step(p, set, 3, true);
        CHECK(find_tag(p, set, 2) == -1);
        CHECK(find_tag(p, set, 3) == 1);
        CHECK(p.global_entry(set, 1).counter == 2);
    }
    CHECK(p.stats().replacements == 2);
}

void test_defaults_mask_mapping_and_storage() {
    ++groups;
    pm_predictor p;
    CHECK(p.ways() == 2);
    branch_info b = branch(0x8003);
    auto *u = static_cast<pm_update *>(p.predict(b));
    CHECK(u->bimodal_index == 3);
    CHECK(u->global_set == 0);
    CHECK(u->tag == 3); // Raw PC bits, without shifting off low address bits.
    p.update(u, true, 0);
    for (unsigned i = 0; i < 50; ++i) {
        step(p, 0xFEDCBA98, true);
        CHECK(p.history() <= 32767);
    }
    CHECK(p.history() == 32767);
    b = branch(0xFEDCBA98);
    u = static_cast<pm_update *>(p.predict(b));
    unsigned expected_hash = (0xFEDCBA98u ^ 32767u) & 32767u;
    CHECK(u->global_set == expected_hash / 64);
    CHECK(u->tag == expected_hash % 64);
    p.update(u, false, 0);
    for (unsigned i = 0; i < 14; ++i) step(p, 0x22, false);
    CHECK(p.history() == 0);
    CHECK(p.logical_storage_bits() == 17935);
    CHECK(pm_predictor(4).logical_storage_bits() == 30735);
    CHECK(bimodal_predictor().logical_storage_bits() == 8192);
    CHECK(gshare_predictor().logical_storage_bits() == 65551);
    CHECK(taken_predictor().logical_storage_bits() == 0);
    bool threw = false;
    try { pm_predictor invalid(3); } catch (const std::invalid_argument &) { threw = true; }
    CHECK(threw);
}

// Independent oracle: LRU is represented by monotonic access timestamps,
// not by the production implementation's ranks and touch() algorithm.
struct Reference {
    struct Slot {
        bool valid = false;
        unsigned tag = 0;
        int counter = 1;
        std::uint64_t last_access = 0;
    };
    unsigned ways;
    unsigned history = 0;
    std::uint64_t clock = 0;
    std::array<int, 4096> bimodal{};
    std::array<std::array<Slot, 4>, 512> sets{};
    pm_statistics stats{};

    explicit Reference(unsigned associativity) : ways(associativity) { bimodal.fill(1); }
    static void train(int &counter, bool taken) {
        counter += taken ? 1 : -1;
        if (counter < 0) counter = 0;
        if (counter > 3) counter = 3;
    }
    int locate(unsigned set, unsigned tag) const {
        for (unsigned w = 0; w < ways; ++w)
            if (sets[set][w].valid && sets[set][w].tag == tag) return int(w);
        return -1;
    }
    bool predict(unsigned address, bool conditional) const {
        if (!conditional) return true;
        unsigned key = (address ^ history) % 32768;
        int way = locate(key / 64, key % 64);
        int counter = way < 0 ? bimodal[address % 4096]
                             : sets[key / 64][unsigned(way)].counter;
        return counter >= 2;
    }
    void update(unsigned address, bool conditional, bool outcome) {
        if (!conditional) return;
        ++clock;
        unsigned key = (address ^ history) % 32768;
        auto &set = sets[key / 64];
        int way = locate(key / 64, key % 64);
        train(bimodal[address % 4096], outcome);
        if (way >= 0) {
            ++stats.global_hits;
            train(set[unsigned(way)].counter, outcome);
        } else {
            ++stats.global_misses;
            ++stats.allocations;
            for (unsigned w = 0; w < ways; ++w) {
                if (!set[w].valid) { way = int(w); break; }
            }
            if (way < 0) {
                ++stats.replacements;
                way = 0;
                for (unsigned w = 1; w < ways; ++w)
                    if (set[w].last_access < set[unsigned(way)].last_access) way = int(w);
            }
            set[unsigned(way)].valid = true;
            set[unsigned(way)].tag = key % 64;
            set[unsigned(way)].counter = outcome ? 2 : 1;
        }
        set[unsigned(way)].last_access = clock;
        history = (history * 2 + unsigned(outcome)) % 32768;
    }
};

void compare_set(const pm_predictor &p, const Reference &r, unsigned set) {
    for (unsigned w = 0; w < r.ways; ++w) {
        const auto &actual = p.global_entry(set, w);
        const auto &expected = r.sets[set][w];
        CHECK(actual.valid == expected.valid);
        if (!expected.valid) continue;
        CHECK(actual.tag == expected.tag);
        CHECK(actual.counter == expected.counter);
        unsigned newer = 0;
        for (unsigned other = 0; other < r.ways; ++other)
            if (r.sets[set][other].valid &&
                r.sets[set][other].last_access > expected.last_access) ++newer;
        CHECK(actual.rank == newer);
    }
}

std::uint32_t random_word(std::uint32_t &state) {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return state;
}

void test_pm_reference(unsigned ways) {
    ++groups;
    pm_predictor p(ways);
    Reference r(ways);
    std::uint32_t random = 0xC0FFEEu + ways;
    for (unsigned i = 0; i < 12000; ++i) {
        unsigned word = random_word(random);
        unsigned address;
        if (i % 3 != 0) {
            // Frequent collisions and repeated hits exercise replacement order.
            unsigned set = (word >> 8) % 9;
            unsigned tag = (word >> 17) % 7;
            address = ((set * 64 + tag) ^ r.history) | (word & 0xFFFF8000u);
        } else {
            address = word;
        }
        unsigned flags = i % 11 == 0 ? BR_CALL : BR_CONDITIONAL;
        if (i % 17 == 0) flags |= BR_INDIRECT;
        bool conditional = (flags & BR_CONDITIONAL) != 0;
        bool outcome = (random_word(random) % 100) < (i % 200 < 100 ? 73 : 31);
        unsigned before_key = (address ^ r.history) % 32768;
        branch_info b = branch(address, flags);
        auto *u = static_cast<pm_update *>(p.predict(b));
        CHECK(u->direction_prediction() == r.predict(address, conditional));
        CHECK(u->conditional == conditional);
        if (conditional) {
            CHECK(u->bimodal_index == address % 4096);
            CHECK(u->global_set == before_key / 64);
            CHECK(u->tag == before_key % 64);
            CHECK(u->hit_way == r.locate(before_key / 64, before_key % 64));
            CHECK(u->bimodal_prediction == (r.bimodal[address % 4096] >= 2));
        }
        p.update(u, outcome, 0);
        r.update(address, conditional, outcome);
        CHECK(p.history() == r.history);
        CHECK(p.bimodal_counter(address % 4096) == unsigned(r.bimodal[address % 4096]));
        CHECK(p.stats().global_hits == r.stats.global_hits);
        CHECK(p.stats().global_misses == r.stats.global_misses);
        CHECK(p.stats().allocations == r.stats.allocations);
        CHECK(p.stats().replacements == r.stats.replacements);
        compare_set(p, r, before_key / 64);
        if (i % 128 == 0 || i == 11999) {
            for (unsigned set = 0; set < 512; ++set) compare_set(p, r, set);
            for (unsigned index = 0; index < 4096; ++index)
                CHECK(p.bimodal_counter(index) == unsigned(r.bimodal[index]));
        }
    }
    CHECK(r.stats.global_hits > 1000);
    CHECK(r.stats.replacements > 1000);
    CHECK(r.stats.allocations == r.stats.global_misses);
}

void test_original_gshare_and_baselines() {
    ++groups;
    gshare_predictor g;
    std::array<int, 32768> reference{}; // Original is strongly NT initially.
    unsigned history = 0;
    std::uint32_t random = 0x12345678;
    for (unsigned i = 0; i < 16000; ++i) {
        unsigned address = i < 3 ? history : random_word(random);
        if (i >= 3 && i % 3 != 0)
            address = (random_word(random) % 32) ^ history;
        unsigned flags = i >= 3 && i % 13 == 0 ? BR_RETURN : BR_CONDITIONAL;
        bool conditional = (flags & BR_CONDITIONAL) != 0;
        bool outcome = i < 3 || (random_word(random) & 1);
        unsigned index = (address ^ history) & 32767;
        branch_info b = branch(address, flags);
        auto *u = static_cast<simple_update *>(g.predict(b));
        bool expected = !conditional || reference[index] >= 2;
        CHECK(u->direction_prediction() == expected);
        CHECK(u->index == index);
        CHECK(u->conditional == conditional);
        if (i < 3) CHECK(u->direction_prediction() == (i == 2));
        g.update(u, outcome, 0);
        if (conditional) {
            Reference::train(reference[index], outcome);
            history = (history * 2 + unsigned(outcome)) % 32768;
        }
    }
    bimodal_predictor bimodal;
    CHECK(!step(bimodal, 12, true));
    CHECK(step(bimodal, 12 + 4096, true)); // Same raw-PC table slot.
    CHECK(step(bimodal, 12, false, BR_CALL)); // Unconditional does not train.
    CHECK(step(bimodal, 12, false));
    CHECK(step(bimodal, 12, false));
    CHECK(!step(bimodal, 12, false));
    taken_predictor taken;
    CHECK(step(taken, 12, false));
    CHECK(step(taken, 13, true, BR_CALL));
}
} // namespace

int main() {
    try {
        test_counters_and_cold_fallback();
        test_global_override();
        test_prediction_indices_and_history();
        test_invalid_way_preference_and_lru(2);
        test_invalid_way_preference_and_lru(4);
        test_defaults_mask_mapping_and_storage();
        test_pm_reference(2);
        test_pm_reference(4);
        test_original_gshare_and_baselines();
        std::cout << "PASS: " << groups << " test groups; " << checks
                  << " assertions; 24,000 PM reference events; 16,000 gshare reference events.\n";
        return EXIT_SUCCESS;
    } catch (const std::exception &e) {
        std::cerr << "FAIL after " << checks << " assertions: " << e.what() << '\n';
        return EXIT_FAILURE;
    }
}
