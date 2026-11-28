cmake_minimum_required(VERSION 3.22)
project(DoomOnWednesday CXX C)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(DOW_CORE
  src/core/mesh.cpp src/core/assets.cpp src/render/model_asset.cpp
  src/game/world.cpp src/game/maps.cpp src/game/nav.cpp src/game/rounds.cpp src/game/locomotion.cpp src/game/gore.cpp src/game/game.cpp src/game/sha256.cpp
  src/game/models.cpp src/game/textures.cpp
  src/render/renderer.cpp src/render/scene.cpp
  src/audio/synth.cpp)

if(ANDROID)
  # Quest standalone build: NativeActivity + OpenXR (Khronos loader from Maven, via prefab) + GLES3 + AAudio
  find_package(OpenXR REQUIRED CONFIG)
  add_library(native_app_glue STATIC ${ANDROID_NDK}/sources/android/native_app_glue/android_native_app_glue.c)
  target_include_directories(native_app_glue PUBLIC ${ANDROID_NDK}/sources/android/native_app_glue)
  add_library(dow SHARED ${DOW_CORE} src/platform/android_main.cpp src/audio/audio_aaudio.cpp)
  target_compile_options(dow PRIVATE -O2 -ffast-math -Wall -Wno-unused-parameter)
  target_link_options(dow PRIVATE -u ANativeActivity_onCreate)
  target_link_libraries(dow native_app_glue OpenXR::openxr_loader OpenXR::headers android log EGL GLESv3 aaudio)
else()
  # Desktop: headless test host (EGL pbuffer) + unit tests. Same game and renderer code as the Quest build.
  add_executable(dow_desktop ${DOW_CORE} src/platform/desktop_main.cpp src/audio/audio_null.cpp)
  target_compile_options(dow_desktop PRIVATE -O2 -Wall -Wextra -Wno-unused-parameter)
  target_link_libraries(dow_desktop EGL GLESv2 m)
  add_executable(dow_tests tests/loco_test.cpp tests/game_test.cpp src/core/mesh.cpp src/core/assets.cpp src/game/world.cpp src/game/maps.cpp src/game/nav.cpp src/game/rounds.cpp src/game/locomotion.cpp src/game/gore.cpp src/game/game.cpp src/game/sha256.cpp src/game/models.cpp src/game/textures.cpp)
  target_compile_options(dow_tests PRIVATE -O2 -Wall)
  enable_testing()
  add_test(NAME dow_tests COMMAND dow_tests)
endif()
