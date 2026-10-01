#include "perfpilot_fixture/integer_sum.h"

#include <chrono>
#include <cstdint>
#include <iostream>
#include <string_view>
#include <vector>

int main(int argc, char** argv) {
  const std::vector<int> values(4096, 7);
  if (argc == 2 && std::string_view(argv[1]) == "--fixture-deterministic-json") {
    std::cout << "{\"benchmark\":\"integer_sum\",\"elapsed_ns\":"
              << perfpilot_fixture::fixture_measurement_marker()
              << ",\"repetitions\":1,\"guard\":0}\n";
    return 0;
  }
  if (argc == 2 && std::string_view(argv[1]) == "--profile-json") {
    constexpr int profile_repetitions = 20000;
    std::int64_t profile_guard = 0;
    std::int64_t function_nanoseconds = 0;
    const auto profile_start = std::chrono::steady_clock::now();
    for (int i = 0; i < profile_repetitions; ++i) {
      const auto function_start = std::chrono::steady_clock::now();
      profile_guard ^= perfpilot_fixture::integer_sum(values);
      const auto function_stop = std::chrono::steady_clock::now();
      function_nanoseconds += std::chrono::duration_cast<std::chrono::nanoseconds>(
                                  function_stop - function_start)
                                  .count();
    }
    const auto profile_stop = std::chrono::steady_clock::now();
    const auto total_nanoseconds =
        std::chrono::duration_cast<std::chrono::nanoseconds>(profile_stop - profile_start).count();
    const auto overhead_nanoseconds = total_nanoseconds - function_nanoseconds;
    const double function_percent =
        total_nanoseconds > 0 ? 100.0 * function_nanoseconds / total_nanoseconds : 0.0;
    const double overhead_percent =
        total_nanoseconds > 0 ? 100.0 * overhead_nanoseconds / total_nanoseconds : 0.0;
    std::cout << "{\"backend\":\"instrumented_json\",\"hotspots\":["
              << "{\"symbol\":\"perfpilot_fixture::integer_sum\",\"percent_time\":"
              << function_percent
              << ",\"sample_count\":" << profile_repetitions
              << ",\"source_path\":\"src/integer_sum.cpp\",\"source_line\":11},"
              << "{\"symbol\":\"benchmark timing overhead\",\"percent_time\":"
              << overhead_percent << ",\"sample_count\":" << profile_repetitions
              << ",\"source_path\":\"benchmarks/integer_sum_benchmark.cpp\","
              << "\"source_line\":16}],\"total_nanoseconds\":" << total_nanoseconds
              << ",\"guard\":" << profile_guard << "}\n";
    return 0;
  }
  constexpr int repetitions = 20000;
  std::int64_t guard = 0;
  const auto start = std::chrono::steady_clock::now();
  for (int i = 0; i < repetitions; ++i) {
    guard ^= perfpilot_fixture::integer_sum(values);
  }
  const auto stop = std::chrono::steady_clock::now();
  const auto elapsed =
      std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
  std::cout << "{\"benchmark\":\"integer_sum\",\"elapsed_ns\":" << elapsed
            << ",\"repetitions\":" << repetitions << ",\"guard\":" << guard << "}\n";
  return 0;
}
