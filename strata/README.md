# Strata SFX (native)

Procedural sound-effects synthesizer. C++ DSP engine, Kotlin Android UI, one CMake build.

## Get the APK
1. Push this folder to a GitHub repo.
2. Open the Actions tab, run "Build APK", download `Strata-SFX-debug-apk`.
3. Unzip, open the APK on the phone, allow "install unknown apps".

Alternative: open `android/` in Android Studio and press Run.

## Desktop CLI (for testing)
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j
    ./build/strata selftest
    ./build/strata gen explosion --seed 7 > r.json
    ./build/strata render r.json out.wav
    ./build/strata analyze r.json out.ppm

## Layout
- `engine/` DSP, recipe schema, generator, WAV and zip IO
- `cli/` desktop tool
- `android/app/src/main/cpp/` JNI bridge
- `android/app/src/main/java/com/strata/sfx/` UI, player, analyzer view

Exports land in Downloads/Strata.
