// Assignment implementation author: Ahmed Ahmed
// The supplied gshare example and optional extra-credit stub retain their origin.
#ifndef AHMED_AHMED_MY_PREDICTOR_H
#define AHMED_AHMED_MY_PREDICTOR_H
#include <cstring>
#include <cstdint>
#include <stdexcept>
#include <vector>

// my_predictor.h
// This file contains a sample gshare_predictor class.
// It is a simple 32,768-entry gshare with a history length of 15.

class gshare_update : public branch_update {
public:
	unsigned int index;
};

class gshare_predictor : public branch_predictor {
public:
#define HISTORY_LENGTH	15
#define TABLE_BITS	15
	gshare_update u;
	branch_info bi;
	unsigned int history;
	unsigned char tab[1<<TABLE_BITS];

	gshare_predictor (void) : history(0) { 
		memset (tab, 0, sizeof (tab));
	}

	branch_update *predict (branch_info & b) {
		bi = b;
		if (b.br_flags & BR_CONDITIONAL) {
			u.index = 
				  (history << (TABLE_BITS - HISTORY_LENGTH)) 
				^ (b.address & ((1<<TABLE_BITS)-1));
			u.direction_prediction (tab[u.index] >> 1);
		} else {
			u.direction_prediction (true);
		}
		u.target_prediction (0);
		return &u;
	}

	void update (branch_update *u, bool taken, unsigned int /*target*/) {
		if (bi.br_flags & BR_CONDITIONAL) {
			unsigned char *c = &tab[((gshare_update*)u)->index];
			if (taken) {
				if (*c < 3) (*c)++;
			} else {
				if (*c > 0) (*c)--;
			}
			history <<= 1;
			history |= taken;
			history &= (1<<HISTORY_LENGTH)-1;
		}
	}
};

// Prediction-time lookup information; the driver resolves one branch at a time.
class pm_update : public branch_update {
public:
    bool conditional = false;
    unsigned int index = 0;   // bimodal index
    unsigned int row = 0;
    unsigned int tag = 0;
    int way = -1;             // -1 means the global lookup missed
};

// A simplified Pentium M-style hybrid direction predictor.
// Default mapping follows the assignment diagram: raw IP bits, not IP >> 2.
class pm_predictor : public branch_predictor {
public:
    struct global_entry {
        bool valid = false;
        unsigned int tag = 0;
        unsigned char counter = 1;
    };
    struct global_set { global_entry ways[2]; };

    pm_update u;
    unsigned int history = 0;
    unsigned int bimodal_mask, row_mask, tag_mask, history_mask;
    unsigned int tag_bits, pc_shift;
    std::vector<unsigned char> bimodal;
    std::vector<global_set> global;
    std::vector<unsigned char> lru; // next victim if both ways are valid

    explicit pm_predictor(unsigned int bimodal_bits = 12,
                          unsigned int set_bits = 9,
                          unsigned int tag_bits_arg = 6,
                          unsigned int pc_shift_arg = 0) {
        if (bimodal_bits < 1 || bimodal_bits > 16 ||
            set_bits < 1 || set_bits > 16 ||
            tag_bits_arg < 1 || tag_bits_arg > 8 || pc_shift_arg > 31)
            throw std::invalid_argument("invalid predictor configuration");
        tag_bits = tag_bits_arg;
        pc_shift = pc_shift_arg;
        bimodal_mask = (1u << bimodal_bits) - 1;
        row_mask = (1u << set_bits) - 1;
        tag_mask = (1u << tag_bits) - 1;
        history_mask = (1u << (set_bits + tag_bits)) - 1;
        bimodal.assign(1u << bimodal_bits, 1); // weakly not taken
        global.resize(1u << set_bits);       // all entries invalid
        lru.assign(1u << set_bits, 0);
    }

    static void train(unsigned char &counter, bool taken) {
        if (taken && counter < 3) ++counter;
        if (!taken && counter > 0) --counter;
    }

    branch_update *predict(branch_info &b) override {
        u = pm_update();
        u.conditional = (b.br_flags & BR_CONDITIONAL) != 0;
        u.target_prediction(0); // target prediction is outside the assignment
        if (!u.conditional) {
            u.direction_prediction(true);
            return &u;
        }
        const unsigned int pc = b.address >> pc_shift;
        u.index = pc & bimodal_mask;
        const unsigned int hash = (pc ^ history) & history_mask;
        u.row = (hash >> tag_bits) & row_mask;
        u.tag = hash & tag_mask;
        for (int way = 0; way < 2; ++way) {
            const global_entry &entry = global[u.row].ways[way];
            if (entry.valid && entry.tag == u.tag) {
                u.way = way;
                break;
            }
        }
        const unsigned char counter = (u.way >= 0)
            ? global[u.row].ways[u.way].counter : bimodal[u.index];
        u.direction_prediction(counter >= 2);
        return &u;
    }

    void update(branch_update *result, bool taken,
                unsigned int /*target*/) override {
        const pm_update &lookup = *static_cast<pm_update *>(result);
        if (!lookup.conditional) return;
        train(bimodal[lookup.index], taken);
        int way = lookup.way;
        if (way < 0) {
            // Fill an invalid way first; otherwise evict the least recent way.
            if (!global[lookup.row].ways[0].valid) way = 0;
            else if (!global[lookup.row].ways[1].valid) way = 1;
            else way = lru[lookup.row];
            global_entry &entry = global[lookup.row].ways[way];
            entry.valid = true;
            entry.tag = lookup.tag;
            entry.counter = taken ? 2 : 1; // fresh weak state, no stale bias
        } else {
            train(global[lookup.row].ways[way].counter, taken);
        }
        lru[lookup.row] = static_cast<unsigned char>(1 - way);
        history = ((history << 1) | static_cast<unsigned int>(taken))
                  & history_mask;
    }
};

// Controls used only for the comparison experiments.
class always_taken_predictor : public branch_predictor {
    branch_update u;
public:
    branch_update *predict(branch_info &) override {
        u.direction_prediction(true);
        u.target_prediction(0);
        return &u;
    }
};

class bimodal_predictor : public branch_predictor {
    pm_update u;
    unsigned char counters[4096];
public:
    bimodal_predictor() { std::memset(counters, 1, sizeof(counters)); }
    branch_update *predict(branch_info &b) override {
        u.conditional = (b.br_flags & BR_CONDITIONAL) != 0;
        u.index = b.address & 4095u;
        u.direction_prediction(!u.conditional || counters[u.index] >= 2);
        u.target_prediction(0);
        return &u;
    }
    void update(branch_update *result, bool taken, unsigned int) override {
        const pm_update &lookup = *static_cast<pm_update *>(result);
        if (lookup.conditional) pm_predictor::train(counters[lookup.index], taken);
    }
};

//
// Optional extra-credit starter placeholder - not implemented in this submission
// Complete Pentium M branch predictors for extra credit
// This class implements the complete Pentium M branch prediction units. 
// It implements both branch target prediction and branch outcome predicton. 
class cpm_update : public branch_update {
public:
        unsigned int index;
};

class cpm_predictor : public branch_predictor {
public:
        cpm_update u;

        cpm_predictor (void) {
        }

        branch_update *predict (branch_info & /*b*/) {
            u.direction_prediction (true);
            u.target_prediction (0);
            return &u;
        }

        void update (branch_update *, bool, unsigned int) {
        }

};



#endif
