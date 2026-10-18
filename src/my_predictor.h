#ifndef MY_PREDICTOR_H
#define MY_PREDICTOR_H

#include <algorithm>
#include <array>
#include <cstdint>
#include <stdexcept>

// Included after branch.h and predictor.h, as in the supplied CBP2 driver.
// The CBP2 interface is sequential: predict(b) is immediately followed by
// update(u, actual, target). This simulator does not model speculative state.
inline void train_counter(std::uint8_t &counter, bool taken) {
    if (taken) { if (counter < 3) ++counter; }
    else { if (counter > 0) --counter; }
}

struct simple_update : public branch_update {
    bool conditional = false;
    unsigned index = 0;
};

class taken_predictor : public branch_predictor {
    branch_update u_;
public:
    std::uint64_t logical_storage_bits() const { return 0; }
    branch_update *predict(branch_info &) override {
        u_.direction_prediction(true);
        u_.target_prediction(0);
        return &u_;
    }
};

// Bimodal baseline: exactly the same table/index/initialization as pm_predictor.
class bimodal_predictor : public branch_predictor {
    std::array<std::uint8_t, 4096> counters_{};
    simple_update u_;
public:
    std::uint64_t logical_storage_bits() const { return 4096ull * 2; }
    bimodal_predictor() { counters_.fill(1); }  // weakly not taken
    branch_update *predict(branch_info &b) override {
        u_.conditional = (b.br_flags & BR_CONDITIONAL) != 0;
        u_.index = b.address & 4095u;
        u_.direction_prediction(!u_.conditional || counters_[u_.index] >= 2);
        u_.target_prediction(0);
        return &u_;
    }
    void update(branch_update *u, bool taken, unsigned int) override {
        auto &s = *static_cast<simple_update *>(u);
        if (s.conditional) train_counter(counters_[s.index], taken);
    }
};

// Supplied gshare algorithm retained: 15-bit history, 32768 counters, all 0.
// Formatting and types are modernized; its prediction/training rules are unchanged.
class gshare_predictor : public branch_predictor {
    std::array<std::uint8_t, 32768> counters_{};
    std::uint32_t history_ = 0;
    simple_update u_;
public:
    std::uint64_t logical_storage_bits() const { return 32768ull * 2 + 15; }
    branch_update *predict(branch_info &b) override {
        u_.conditional = (b.br_flags & BR_CONDITIONAL) != 0;
        u_.index = (b.address ^ history_) & 32767u;
        u_.direction_prediction(!u_.conditional || counters_[u_.index] >= 2);
        u_.target_prediction(0);
        return &u_;
    }
    void update(branch_update *u, bool taken, unsigned int) override {
        auto &s = *static_cast<simple_update *>(u);
        if (!s.conditional) return;
        train_counter(counters_[s.index], taken);
        history_ = ((history_ << 1) | unsigned(taken)) & 32767u;
    }
};

struct pm_statistics {
    std::uint64_t global_hits = 0;
    std::uint64_t global_misses = 0;
    std::uint64_t allocations = 0;
    std::uint64_t replacements = 0;
};

struct pm_update : public branch_update {
    bool conditional = false;
    unsigned bimodal_index = 0;
    unsigned global_set = 0;
    unsigned tag = 0;
    int hit_way = -1;
    bool bimodal_prediction = false;
};

// Assignment's Pentium M style hybrid, not an exact hardware reconstruction.
// Diagram: bimodal IP[11:0]; global 512 sets, 6-bit tags, 2-bit counters.
// Allowed simplification: GHR replaces PIR, no undocumented hash is emulated.
// hash=(IP XOR GHR)[14:0]; set=hash[14:6]; tag=hash[5:0].
// Global hit overrides bimodal unconditionally. No chooser or loop predictor.
class pm_predictor : public branch_predictor {
public:
    static constexpr unsigned BIMODAL_ENTRIES = 4096;
    static constexpr unsigned GLOBAL_SETS = 512;
    static constexpr unsigned HISTORY_BITS = 15;
    static constexpr unsigned TAG_BITS = 6;
    struct entry {
        bool valid = false;
        std::uint8_t tag = 0;
        std::uint8_t counter = 1;
        std::uint8_t rank = 0;  // 0=MRU, larger=older, among valid ways
    };
private:
    unsigned ways_;
    std::array<std::uint8_t, BIMODAL_ENTRIES> bimodal_{};
    std::array<std::array<entry, 4>, GLOBAL_SETS> global_{};
    std::uint32_t history_ = 0;
    pm_update u_;
    pm_statistics stats_;

    void touch(unsigned set, unsigned way, bool newly_valid) {
        auto &entries = global_[set];
        const unsigned old_rank = entries[way].rank;
        for (unsigned w = 0; w < ways_; ++w) {
            if (w != way && entries[w].valid &&
                (newly_valid || entries[w].rank < old_rank))
                ++entries[w].rank;
        }
        entries[way].rank = 0;
    }
public:
    explicit pm_predictor(unsigned ways = 2) : ways_(ways) {
        if (ways != 2 && ways != 4)
            throw std::invalid_argument("pm_predictor supports 2 or 4 ways");
        bimodal_.fill(1);
    }

    branch_update *predict(branch_info &b) override {
        u_.conditional = (b.br_flags & BR_CONDITIONAL) != 0;
        u_.hit_way = -1;
        u_.direction_prediction(true);
        u_.target_prediction(0);  // target prediction is outside assignment scope
        if (!u_.conditional) return &u_;

        u_.bimodal_index = b.address & (BIMODAL_ENTRIES - 1);
        const unsigned hash = (b.address ^ history_) & 32767u;
        u_.global_set = hash >> TAG_BITS;
        u_.tag = hash & 63u;
        u_.bimodal_prediction = bimodal_[u_.bimodal_index] >= 2;
        bool prediction = u_.bimodal_prediction;
        for (unsigned w = 0; w < ways_; ++w) {
            const entry &e = global_[u_.global_set][w];
            if (e.valid && e.tag == u_.tag) {
                u_.hit_way = static_cast<int>(w);
                prediction = e.counter >= 2;
                break;
            }
        }
        u_.direction_prediction(prediction);
        return &u_;
    }

    void update(branch_update *u, bool taken, unsigned int) override {
        const auto &s = *static_cast<pm_update *>(u);
        if (!s.conditional) return;

        // Always train the fallback, using the prediction-time index.
        train_counter(bimodal_[s.bimodal_index], taken);
        auto &entries = global_[s.global_set];
        if (s.hit_way >= 0) {
            ++stats_.global_hits;
            const unsigned w = static_cast<unsigned>(s.hit_way);
            train_counter(entries[w].counter, taken);
            touch(s.global_set, w, false);
        } else {
            ++stats_.global_misses;
            ++stats_.allocations;
            unsigned victim = ways_;
            for (unsigned w = 0; w < ways_; ++w) {
                if (!entries[w].valid) { victim = w; break; }
            }
            const bool replacing = victim == ways_;
            if (replacing) {
                victim = 0;
                for (unsigned w = 1; w < ways_; ++w)
                    if (entries[w].rank > entries[victim].rank) victim = w;
                ++stats_.replacements;
            }
            // New contexts begin weakly biased toward the observed outcome.
            // Never reuse the old victim's counter for a different tag.
            touch(s.global_set, victim, !replacing);
            entries[victim].valid = true;
            entries[victim].tag = static_cast<std::uint8_t>(s.tag);
            entries[victim].counter = taken ? 2 : 1;
        }
        // Train before shifting history; the current outcome cannot affect
        // its own prediction. Unconditional branches do not enter this GHR.
        history_ = ((history_ << 1) | unsigned(taken)) & 32767u;
    }

    const pm_statistics &stats() const { return stats_; }
    // Ideal packed hardware bits, excluding C++ padding and simulator metadata.
    std::uint64_t logical_storage_bits() const {
        const unsigned lru_bits_per_set = ways_ == 2 ? 1 : 8;
        return 4096ull * 2 + 512ull * ways_ * (1 + 6 + 2)
             + 512ull * lru_bits_per_set + 15;
    }
    // Read-only inspection for deterministic algorithm tests.
    unsigned history() const { return history_; }
    unsigned ways() const { return ways_; }
    unsigned bimodal_counter(unsigned index) const { return bimodal_.at(index); }
    const entry &global_entry(unsigned set, unsigned way) const {
        if (way >= ways_) throw std::out_of_range("inactive way");
        return global_.at(set).at(way);
    }
};

#endif
