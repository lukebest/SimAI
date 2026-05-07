cmake_minimum_required(VERSION 3.16)

project(calendar_scheduler LANGUAGES CXX)

add_library(calendar_scheduler STATIC
  src/bvn_scheduler.cc
  src/round_robin_scheduler.cc
  src/solstice_scheduler.cc
)

target_include_directories(calendar_scheduler
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(calendar_scheduler PUBLIC cxx_std_17)
