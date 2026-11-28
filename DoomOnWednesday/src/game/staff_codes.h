// Staff keypad codes. Only sha256(sha256(code)) is stored here, never the code itself.
// Default codes — CHANGE THEM before you share a build:   owner = 246810    mod = 135790
// Make a new hash with:  ./build-desktop/dow_tool hash <your code>
// This is client-side gating for an offline build: it stops casual players, not a determined hacker.
#pragma once
namespace dow {
static const char* kOwnerHashes[] = {"11e93fc185898cfffeaa6ff898117703a181c01bffaf672af57781a1428777a8"};
static const char* kModHashes[] = {"23455a3959bbc3b95633c547a335b47f25ae8b4addee79d1794109a74543554f"};
}  // namespace dow
