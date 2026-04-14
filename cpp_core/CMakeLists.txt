cmake_minimum_required(VERSION 3.16)
project(bharat_alpha_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(MSVC)
  add_compile_options(/O2 /arch:AVX2)
else()
  add_compile_options(-O3 -mavx2 -mfma -march=native)
endif()

add_executable(bharat_alpha_core
  src/main.cpp
)

target_include_directories(bharat_alpha_core PRIVATE include)
