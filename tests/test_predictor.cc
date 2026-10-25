// Author: Ahmed Ahmed. Directed checks of assignment behavior and corner cases.
#include <cstdio>
#include <stdexcept>
#include <string>
#include "branch.h"
#include "predictor.h"
#include "my_predictor.h"
#define CHECK(expr) do { if (!(expr)) throw std::runtime_error(\
    std::string(__func__) + ": " + #expr); } while (0)
branch_info branch(unsigned pc, bool conditional = true) {
    return {pc, OP_JNZ, static_cast<unsigned>(conditional ? BR_CONDITIONAL : BR_CALL)};
}
void step(pm_predictor &p, unsigned pc, bool taken, bool conditional = true) {
    auto b = branch(pc, conditional);
    auto *u = p.predict(b);
    p.update(u, taken, 0);
}
void initial_state() {
    pm_predictor p;
    CHECK(p.bimodal.size() == 4096 && p.global.size() == 512);
    CHECK(p.history == 0 && p.history_mask == 32767);
    for (auto c : p.bimodal) CHECK(c == 1);
    for (auto &s : p.global) for (auto &e : s.ways) CHECK(!e.valid);
}
void all_counter_transitions() {
    const int up[] = {1,2,3,3}, down[] = {0,0,1,2};
    for (int i=0; i<4; ++i) {
        unsigned char c = i; pm_predictor::train(c, true); CHECK(c == up[i]);
        c = i; pm_predictor::train(c, false); CHECK(c == down[i]);
    }
}
void hash_and_bit_fields() {
    pm_predictor p; p.history = 0x1234;
    auto b = branch(0x89abcdefu);
    p.predict(b);
    CHECK(p.u.index == 0xdef);
    CHECK(p.u.row == (((0xcdefu ^ 0x1234u) & 0x7fff) >> 6));
    CHECK(p.u.tag == ((0xcdefu ^ 0x1234u) & 63));
    CHECK(p.history == 0x1234); // prediction must not consume an outcome
}
void invalid_tag_is_not_a_hit() {
    pm_predictor p; auto b = branch(0);
    p.global[0].ways[0].counter = 3;
    p.predict(b); CHECK(p.u.way == -1); CHECK(!p.u.direction_prediction());
}
void tag_mismatch_is_a_miss() {
    pm_predictor p; p.global[0].ways[0] = {true, 7, 3};
    auto b = branch(0); p.predict(b); CHECK(p.u.way == -1);
}
void hit_overrides_bimodal_both_directions() {
    pm_predictor p; auto b = branch(0);
    p.global[0].ways[1] = {true, 0, 3}; p.bimodal[0] = 0;
    p.predict(b); CHECK(p.u.way == 1 && p.u.direction_prediction());
    p.global[0].ways[1].counter = 0; p.bimodal[0] = 3;
    p.predict(b); CHECK(!p.u.direction_prediction());
    CHECK(p.history == 0 && p.lru[0] == 0);
}
void both_components_train_on_hit() {
    pm_predictor p; p.global[0].ways[0] = {true,0,2};
    step(p, 0, false);
    CHECK(p.bimodal[0] == 0 && p.global[0].ways[0].counter == 1);
    CHECK(p.lru[0] == 1);
}
void invalid_first_and_fresh_allocation() {
    pm_predictor p; p.lru[0] = 1;
    p.global[0].ways[0].counter = 3;
    step(p, 0, false); CHECK(p.global[0].ways[0].valid);
    CHECK(!p.global[0].ways[1].valid && p.global[0].ways[0].counter == 1);
    step(p, 1, true); CHECK(p.global[0].ways[1].valid);
    CHECK(p.global[0].ways[1].tag == 1 && p.global[0].ways[1].counter == 2);
}
void lru_hit_refresh_and_replacement() {
    pm_predictor p;
    step(p, 0, false); step(p, 1, false); // fill ways 0 and 1
    step(p, 0, false); // refresh way 0, so way 1 must be evicted
    CHECK(p.lru[0] == 1);
    step(p, 2, false);
    CHECK(p.global[0].ways[0].tag == 0 && p.global[0].ways[1].tag == 2);
    CHECK(p.global[0].ways[1].counter == 1 && p.lru[0] == 0);
    step(p, 3, true); // now evict way 0
    CHECK(p.global[0].ways[0].tag == 3 && p.global[0].ways[0].counter == 2);
}
void actual_history_and_wraparound() {
    pm_predictor p; p.history = 32767;
    step(p, 0, false); CHECK(p.history == 32766);
    step(p, 0, true); CHECK(p.history == 32765);
    pm_predictor cold; step(cold, 7, true); CHECK(cold.history == 1);
}
void unconditional_isolation() {
    pm_predictor p; step(p,0,true);
    auto before = p.history; auto counter = p.bimodal[0]; auto lru = p.lru[0];
    auto b = branch(0, false); auto *u = p.predict(b);
    CHECK(u->direction_prediction() && !p.u.conditional && p.u.way == -1);
    p.update(u, false, 1234);
    CHECK(p.history == before && p.bimodal[0] == counter && p.lru[0] == lru);
}
void saved_prediction_indices() {
    pm_predictor p; auto b = branch(129); auto *u = p.predict(b);
    b.address = 9999; // update must not consult the caller's mutated branch_info
    p.update(u, true, 0);
    CHECK(p.bimodal[129] == 2 && p.global[2].ways[0].tag == 1);
}
void same_hash_aliases() {
    pm_predictor p; step(p,0,false);
    auto b = branch(0x8000); p.predict(b);
    CHECK(p.u.way == 0 && p.u.tag == 0 && p.u.row == 0);
}
void appendix_hash_sequence() {
    pm_predictor p(4,2,2,2);
    const unsigned pc[] = {0x44,0x90,0x44,0x6c,0x90,0x44};
    const bool outcome[] = {1,1,0,0,1,1};
    const unsigned hashes[] = {1,5,2,13,8,8};
    for (unsigned i=0; i<6; ++i) {
        auto b=branch(pc[i]); auto *u=p.predict(b);
        CHECK((p.u.row*4 + p.u.tag) == hashes[i]);
        p.update(u,outcome[i],0);
    }
}
void alternating_pattern_is_learned() {
    pm_predictor p; unsigned wrong=0;
    for (unsigned i=0; i<200; ++i) {
        auto b=branch(0x440); auto *u=p.predict(b); bool taken=i%2==0;
        if (i>=40) wrong += u->direction_prediction()!=taken;
        p.update(u,taken,0);
    }
    CHECK(wrong == 0);
}
void bad_configuration_is_rejected() {
    bool caught=false;
    try { pm_predictor p(0); } catch (const std::invalid_argument &) { caught=true; }
    CHECK(caught);
    caught=false;
    try { pm_predictor p(12,9,9); } catch (const std::invalid_argument &) { caught=true; }
    CHECK(caught);
}
int main() {
    unsigned passed=0;
    auto run=[&](const char *name, void (*f)()) { f(); ++passed; std::printf("PASS %s\n",name); };
#define RUN(f) run(#f, f)
    try {
        RUN(initial_state); RUN(all_counter_transitions); RUN(hash_and_bit_fields);
        RUN(invalid_tag_is_not_a_hit); RUN(tag_mismatch_is_a_miss);
        RUN(hit_overrides_bimodal_both_directions); RUN(both_components_train_on_hit);
        RUN(invalid_first_and_fresh_allocation); RUN(lru_hit_refresh_and_replacement);
        RUN(actual_history_and_wraparound); RUN(unconditional_isolation);
        RUN(saved_prediction_indices); RUN(same_hash_aliases); RUN(appendix_hash_sequence);
        RUN(alternating_pattern_is_learned); RUN(bad_configuration_is_rejected);
    } catch (const std::exception &e) { std::fprintf(stderr,"FAIL %s\n",e.what()); return 1; }
    std::printf("PASS %u directed predictor tests\n",passed);
}
