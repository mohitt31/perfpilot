#pragma once

#include <cstdint>
#include <vector>

namespace perfpilot_fixture {

int fixture_measurement_marker();
std::int64_t integer_sum(const std::vector<int>& values);

}  // namespace perfpilot_fixture
