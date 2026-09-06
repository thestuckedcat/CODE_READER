cmake_minimum_required(VERSION 3.16)
project(atlas_fixture C CXX)
add_library(sdk STATIC sdk.c other.c cpp.cpp)
target_include_directories(sdk PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
