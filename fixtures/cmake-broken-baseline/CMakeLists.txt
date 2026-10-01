cmake_minimum_required(VERSION 3.20)
project(perfpilot_broken_baseline_fixture LANGUAGES CXX)

include(CTest)

add_executable(always_failing_test tests/always_failing_test.cpp)
target_compile_features(always_failing_test PRIVATE cxx_std_17)
add_test(NAME always_failing_test COMMAND always_failing_test)

add_executable(noop_benchmark src/noop_benchmark.cpp)
target_compile_features(noop_benchmark PRIVATE cxx_std_17)

