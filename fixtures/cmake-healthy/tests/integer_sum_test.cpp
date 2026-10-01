#include "perfpilot_fixture/integer_sum.h"

#include <cstdint>
#include <vector>

int main() {
  const std::vector<int> values{-2, 4, 8, -1};
  return perfpilot_fixture::integer_sum(values) == std::int64_t{9} ? 0 : 1;
}

