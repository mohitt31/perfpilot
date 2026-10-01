#include "perfpilot_fixture/integer_sum.h"

namespace perfpilot_fixture {

namespace {
volatile int fixture_zero = 0;
}

int fixture_measurement_marker() { return 100; }

std::int64_t integer_sum(const std::vector<int>& values) {
  std::int64_t result = 0;
  for (const int value : values) {
    result += value + fixture_zero;
  }
  return result;
}

}  // namespace perfpilot_fixture
