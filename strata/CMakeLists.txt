cmake_minimum_required(VERSION 3.18)
project(strata LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

# Engine sources are shared by the desktop CLI and the Android library.
set(STRATA_ENGINE_SOURCES
  ${CMAKE_CURRENT_LIST_DIR}/engine/schema.cpp
  ${CMAKE_CURRENT_LIST_DIR}/engine/dsp.cpp
  ${CMAKE_CURRENT_LIST_DIR}/engine/generate.cpp
  ${CMAKE_CURRENT_LIST_DIR}/engine/io.cpp)

add_library(strata_engine STATIC ${STRATA_ENGINE_SOURCES})
target_include_directories(strata_engine PUBLIC ${CMAKE_CURRENT_LIST_DIR}/engine)
target_compile_options(strata_engine PRIVATE -O2 -Wall -Wextra -Wno-unused-parameter)
find_package(Threads REQUIRED)
target_link_libraries(strata_engine PUBLIC Threads::Threads)

if(ANDROID)
  # Built by Gradle through externalNativeBuild. Produces libstrata.so for each ABI.
  add_library(strata SHARED ${CMAKE_CURRENT_LIST_DIR}/android/app/src/main/cpp/strata_jni.cpp)
  target_link_libraries(strata strata_engine log)
  # Required for 16 KB page size devices.
  target_link_options(strata PRIVATE -Wl,-z,max-page-size=16384)
else()
  add_executable(strata_cli ${CMAKE_CURRENT_LIST_DIR}/cli/main.cpp)
  target_link_libraries(strata_cli strata_engine)
  set_target_properties(strata_cli PROPERTIES OUTPUT_NAME strata)
endif()
