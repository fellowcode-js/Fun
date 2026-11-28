// Quest audio output via AAudio (low-latency float stereo stream, callback-driven).
#include "synth.h"
#include <aaudio/AAudio.h>
#include <android/log.h>

namespace dow {

static AAudioStream* gStream = nullptr;

static aaudio_data_callback_result_t cb(AAudioStream* s, void* user, void* data, int32_t frames) {
  static_cast<Synth*>(user)->render(static_cast<float*>(data), frames, AAudioStream_getSampleRate(s));
  return AAUDIO_CALLBACK_RESULT_CONTINUE;
}

bool audioStart(Synth* synth) {
  AAudioStreamBuilder* b = nullptr;
  if (AAudio_createStreamBuilder(&b) != AAUDIO_OK) return false;
  AAudioStreamBuilder_setFormat(b, AAUDIO_FORMAT_PCM_FLOAT);
  AAudioStreamBuilder_setChannelCount(b, 2);
  AAudioStreamBuilder_setSampleRate(b, 48000);
  AAudioStreamBuilder_setPerformanceMode(b, AAUDIO_PERFORMANCE_MODE_LOW_LATENCY);
  AAudioStreamBuilder_setDataCallback(b, cb, synth);
  aaudio_result_t r = AAudioStreamBuilder_openStream(b, &gStream);
  AAudioStreamBuilder_delete(b);
  if (r != AAUDIO_OK) { __android_log_print(ANDROID_LOG_WARN, "DOW", "AAudio open failed: %d", r); gStream = nullptr; return false; }
  AAudioStream_requestStart(gStream);
  return true;
}

void audioStop() { if (gStream) { AAudioStream_requestStop(gStream); AAudioStream_close(gStream); gStream = nullptr; } }

}  // namespace dow
