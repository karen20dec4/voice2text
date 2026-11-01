cmake_minimum_required(VERSION 3.19)
project(voice2text_whisper CXX)

set(CMAKE_CXX_STANDARD 17)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN ON CACHE BOOL "" FORCE)
# vcomp140.dll is not guaranteed on the target PC.
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
# Fixed instruction set, so the DLL does not depend on the build machine's CPU.
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_AVX ON CACHE BOOL "" FORCE)
set(GGML_AVX2 ON CACHE BOOL "" FORCE)
set(GGML_FMA ON CACHE BOOL "" FORCE)
set(GGML_F16C ON CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_SERVER OFF CACHE BOOL "" FORCE)

add_subdirectory(${WHISPER_SOURCE} whisper EXCLUDE_FROM_ALL)

add_library(voice2text_whisper SHARED voice2text_whisper.cpp)
target_link_libraries(voice2text_whisper PRIVATE whisper)
