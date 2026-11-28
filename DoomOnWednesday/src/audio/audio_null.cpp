// Desktop/headless: no audio device. The synth still compiles and can be rendered offline.
#include "synth.h"
namespace dow { bool audioStart(Synth*) { return false; } void audioStop() {} }
