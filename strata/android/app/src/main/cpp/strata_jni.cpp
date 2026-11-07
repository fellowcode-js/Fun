// JNI bridge between the Kotlin app and the C++ engine.
// All text crosses the boundary as UTF-8 byte arrays so non-ASCII layer names are safe.
#include <jni.h>

#include <string>
#include <vector>

#include "strata.hpp"

using namespace strata;

namespace {

std::string toStr(JNIEnv* env, jbyteArray a) {
    if (!a) return std::string();
    jsize n = env->GetArrayLength(a);
    std::string s((size_t)n, '\0');
    if (n) env->GetByteArrayRegion(a, 0, n, reinterpret_cast<jbyte*>(&s[0]));
    return s;
}
jbyteArray toBytes(JNIEnv* env, const std::string& s) {
    jbyteArray a = env->NewByteArray((jsize)s.size());
    if (a && !s.empty()) env->SetByteArrayRegion(a, 0, (jsize)s.size(), reinterpret_cast<const jbyte*>(s.data()));
    return a;
}
jbyteArray toBytes(JNIEnv* env, const std::vector<uint8_t>& v) {
    jbyteArray a = env->NewByteArray((jsize)v.size());
    if (a && !v.empty()) env->SetByteArrayRegion(a, 0, (jsize)v.size(), reinterpret_cast<const jbyte*>(v.data()));
    return a;
}

thread_local std::string g_error;

}  // namespace

#define JNI(ret, name) extern "C" JNIEXPORT ret JNICALL Java_com_strata_sfx_Native_##name

JNI(jbyteArray, schema)(JNIEnv* env, jclass) { return toBytes(env, schemaJson()); }
JNI(jbyteArray, aiPrompt)(JNIEnv* env, jclass) { return toBytes(env, strata::aiPrompt()); }

JNI(jbyteArray, generate)(JNIEnv* env, jclass, jbyteArray category, jlong seed, jdouble size, jdouble energy,
                          jdouble hardness, jdouble space, jdouble chaos) {
    GenOptions o;
    o.category = toStr(env, category);
    o.seed = (int64_t)seed;
    o.size = size; o.energy = energy; o.hardness = hardness; o.space = space; o.chaos = chaos;
    return toBytes(env, recipeToString(strata::generate(o), 1));
}

// Returns the normalized recipe JSON, or a string starting with "ERR:" when the text is not valid JSON.
JNI(jbyteArray, normalize)(JNIEnv* env, jclass, jbyteArray json) {
    try {
        Recipe r = normRecipe(Json::parse(toStr(env, json)));
        return toBytes(env, recipeToString(r, 1));
    } catch (const std::exception& e) {
        return toBytes(env, std::string("ERR:") + e.what());
    }
}

JNI(jbyteArray, mutate)(JNIEnv* env, jclass, jbyteArray json, jdouble amount, jlong seed) {
    try {
        Recipe r = normRecipe(Json::parse(toStr(env, json)));
        return toBytes(env, recipeToString(strata::mutate(r, amount, (int64_t)seed), 1));
    } catch (const std::exception& e) {
        return toBytes(env, std::string("ERR:") + e.what());
    }
}

JNI(jlong, render)(JNIEnv* env, jclass, jbyteArray json) {
    try {
        Recipe r = normRecipe(Json::parse(toStr(env, json)));
        Audio* a = new Audio(strata::render(r));
        return (jlong)(intptr_t)a;
    } catch (const std::exception& e) {
        g_error = e.what();
        return 0;
    }
}
JNI(jbyteArray, lastError)(JNIEnv* env, jclass) { return toBytes(env, g_error); }
JNI(void, release)(JNIEnv*, jclass, jlong h) { delete reinterpret_cast<Audio*>((intptr_t)h); }

// [sampleRate, duration, peak, rms, renderMs, frames]
JNI(jdoubleArray, info)(JNIEnv* env, jclass, jlong h) {
    Audio* a = reinterpret_cast<Audio*>((intptr_t)h);
    jdouble v[6] = {(double)a->sr, a->duration, a->peak, a->rms, a->renderMs, (double)a->L.size()};
    jdoubleArray out = env->NewDoubleArray(6);
    env->SetDoubleArrayRegion(out, 0, 6, v);
    return out;
}

// Interleaved stereo float samples for AudioTrack.
JNI(jfloatArray, pcm)(JNIEnv* env, jclass, jlong h) {
    Audio* a = reinterpret_cast<Audio*>((intptr_t)h);
    std::vector<float> x(a->L.size() * 2);
    for (size_t i = 0; i < a->L.size(); i++) { x[2 * i] = a->L[i]; x[2 * i + 1] = a->R[i]; }
    jfloatArray out = env->NewFloatArray((jsize)x.size());
    env->SetFloatArrayRegion(out, 0, (jsize)x.size(), x.data());
    return out;
}
JNI(jfloatArray, envelope)(JNIEnv* env, jclass, jlong h, jint width) {
    Audio* a = reinterpret_cast<Audio*>((intptr_t)h);
    std::vector<float> e = strata::envelope(*a, width);
    jfloatArray out = env->NewFloatArray((jsize)e.size());
    env->SetFloatArrayRegion(out, 0, (jsize)e.size(), e.data());
    return out;
}
JNI(jintArray, spectrogram)(JNIEnv* env, jclass, jlong h, jint cols, jint rows) {
    Audio* a = reinterpret_cast<Audio*>((intptr_t)h);
    std::vector<uint32_t> s = strata::spectrogram(*a, cols, rows);
    jintArray out = env->NewIntArray((jsize)s.size());
    env->SetIntArrayRegion(out, 0, (jsize)s.size(), reinterpret_cast<const jint*>(s.data()));
    return out;
}
JNI(jbyteArray, wav)(JNIEnv* env, jclass, jlong h, jint bits) {
    Audio* a = reinterpret_cast<Audio*>((intptr_t)h);
    return toBytes(env, encodeWav(a->L, a->R, a->sr, bits));
}

// Mix plus one aligned stem per active layer, as a zip.
JNI(jbyteArray, stemsZip)(JNIEnv* env, jclass, jbyteArray json, jint bits) {
    try {
        Recipe r = normRecipe(Json::parse(toStr(env, json)));
        Audio mix = strata::render(r);
        std::vector<ZipEntry> files;
        files.push_back({"mix.wav", encodeWav(mix.L, mix.R, mix.sr, bits)});
        int k = 1;
        for (size_t i = 0; i < r.layers.size(); i++) {
            if (r.layers[i].mute) continue;
            RenderOptions o;
            o.only = {(int)i};
            o.minLength = mix.duration;
            o.raw = true;
            Audio s = strata::render(r, o);
            std::string nm = r.layers[i].name.empty() ? r.layers[i].type : r.layers[i].name;
            for (auto& c : nm) if (!isalnum((unsigned char)c)) c = '-';
            char pre[16];
            snprintf(pre, sizeof pre, "%02d-", k++);
            files.push_back({std::string("stems/") + pre + nm + ".wav", encodeWav(s.L, s.R, s.sr, bits)});
        }
        return toBytes(env, zipStore(files));
    } catch (const std::exception& e) {
        g_error = e.what();
        return nullptr;
    }
}
