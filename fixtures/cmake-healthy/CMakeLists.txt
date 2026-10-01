cmake_minimum_required(VERSION 3.20)
project(perfpilot_healthy_fixture LANGUAGES CXX)

include(CTest)

add_library(integer_sum src/integer_sum.cpp)
target_include_directories(integer_sum PUBLIC include)
target_compile_features(integer_sum PUBLIC cxx_std_17)

add_executable(integer_sum_test tests/integer_sum_test.cpp)
target_link_libraries(integer_sum_test PRIVATE integer_sum)
add_test(NAME integer_sum_test COMMAND integer_sum_test)

# This is a deterministic pipeline fixture, not a scientifically valid benchmark harness.
add_executable(integer_sum_benchmark benchmarks/integer_sum_benchmark.cpp)
target_link_libraries(integer_sum_benchmark PRIVATE integer_sum)

