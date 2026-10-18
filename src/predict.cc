// Direction-predictor trace driver. Original CBP trace decoder is retained.
// Every distributed trace covers 100,000,000 instructions; override this only
// when supplying a different trace with a known instruction count.
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>

#include "branch.h"
#include "predictor.h"
#include "trace.h"
#include "my_predictor.h"

namespace {
void usage(const char *program) {
    std::cerr << "Usage: " << program
              << " [--predictor pm2|pm4|bimodal|gshare|taken] [--json]"
                 " [--instructions N] TRACE\n"
              << "Default: pm2, 100000000 instructions per distributed trace.\n";
}

std::string json_string(const std::string &s) {
    std::ostringstream out;
    out << '"';
    for (unsigned char c : s) {
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20) {
                    out << "\\u" << std::hex << std::setw(4)
                        << std::setfill('0') << static_cast<unsigned>(c)
                        << std::dec;
                } else {
                    out << c;
                }
        }
    }
    out << '"';
    return out.str();
}

std::uint64_t positive_integer(const char *value) {
    if (!value[0]) throw std::invalid_argument("empty instruction count");
    for (const char *p = value; *p; ++p) {
        if (*p < '0' || *p > '9')
            throw std::invalid_argument("instruction count must be a positive integer");
    }
    errno = 0;
    char *end = nullptr;
    const unsigned long long result = std::strtoull(value, &end, 10);
    if (errno == ERANGE || *end || result == 0)
        throw std::invalid_argument("instruction count is zero or out of range");
    return static_cast<std::uint64_t>(result);
}
} // namespace

int main(int argc, char **argv) {
    try {
        std::string name = "pm2";
        char *trace_path = nullptr;
        bool json = false;
        std::uint64_t instructions = 100000000ULL;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            if (arg == "--help" || arg == "-h") {
                usage(argv[0]);
                return 0;
            } else if (arg == "--json") {
                json = true;
            } else if (arg == "--predictor" || arg == "--instructions") {
                if (++i == argc) throw std::invalid_argument("missing value for " + arg);
                if (arg == "--predictor") name = argv[i];
                else instructions = positive_integer(argv[i]);
            } else if (!arg.empty() && arg[0] == '-') {
                throw std::invalid_argument("unknown option: " + arg);
            } else if (trace_path) {
                throw std::invalid_argument("only one trace file is accepted");
            } else {
                trace_path = argv[i];
            }
        }
        if (!trace_path) throw std::invalid_argument("a trace file is required");

        std::unique_ptr<branch_predictor> predictor;
        pm_predictor *pm = nullptr;
        std::uint64_t storage_bits = 0;
        if (name == "pm2" || name == "pm4") {
            pm = new pm_predictor(name == "pm2" ? 2 : 4);
            storage_bits = pm->logical_storage_bits();
            predictor.reset(pm);
        } else if (name == "bimodal") {
            auto *p = new bimodal_predictor();
            storage_bits = p->logical_storage_bits();
            predictor.reset(p);
        } else if (name == "gshare") {
            auto *p = new gshare_predictor();
            storage_bits = p->logical_storage_bits();
            predictor.reset(p);
        } else if (name == "taken") {
            auto *p = new taken_predictor();
            storage_bits = p->logical_storage_bits();
            predictor.reset(p);
        } else {
            throw std::invalid_argument("unknown predictor: " + name);
        }

        init_trace(trace_path);
        std::uint64_t branch_count = 0, conditional_count = 0, direction_misses = 0;
        while (trace *t = read_trace()) {
            ++branch_count;
            branch_update *u = predictor->predict(t->bi);
            if (t->bi.br_flags & BR_CONDITIONAL) {
                ++conditional_count;
                direction_misses += u->direction_prediction() != t->taken;
            }
            predictor->update(u, t->taken, t->target);
        }
        end_trace();

        const double error_pct = conditional_count
            ? 100.0 * static_cast<double>(direction_misses) / conditional_count : 0.0;
        const double accuracy_pct = conditional_count ? 100.0 - error_pct : 0.0;
        const double mpki = 1000.0 * static_cast<double>(direction_misses) / instructions;
        if (json) {
            std::uint64_t hits = 0, misses = 0, allocations = 0, replacements = 0;
            if (pm) {
                const auto &stats = pm->stats();
                hits = stats.global_hits;
                misses = stats.global_misses;
                allocations = stats.allocations;
                replacements = stats.replacements;
            }
            std::cout << std::setprecision(15)
                << "{\n  \"schema_version\": 1,\n"
                << "  \"predictor\": " << json_string(name) << ",\n"
                << "  \"trace\": " << json_string(trace_path) << ",\n"
                << "  \"instructions\": " << instructions << ",\n"
                << "  \"branch_count\": " << branch_count << ",\n"
                << "  \"conditional_count\": " << conditional_count << ",\n"
                << "  \"direction_misses\": " << direction_misses << ",\n"
                << "  \"accuracy_pct\": " << accuracy_pct << ",\n"
                << "  \"misprediction_rate_pct\": " << error_pct << ",\n"
                << "  \"mpki\": " << mpki << ",\n"
                << "  \"logical_storage_bits\": " << storage_bits << ",\n"
                << "  \"global_hits\": " << hits << ",\n"
                << "  \"global_misses\": " << misses << ",\n"
                << "  \"allocations\": " << allocations << ",\n"
                << "  \"replacements\": " << replacements << "\n}\n";
        } else {
            // Preserve the original command-line result format.
            std::cout << std::fixed << std::setprecision(3) << mpki << " MPKI\n";
        }
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "Error: " << e.what() << '\n';
        usage(argv[0]);
        return 1;
    }
}
