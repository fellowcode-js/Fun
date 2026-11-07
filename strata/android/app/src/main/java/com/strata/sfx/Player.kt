package com.strata.sfx

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack

/** Streams a rendered stereo float buffer through AudioTrack, with optional looping. */
class Player {
    @Volatile private var track: AudioTrack? = null
    @Volatile private var stopFlag = false
    @Volatile private var totalFrames = 0
    @Volatile var loop = false

    fun isPlaying(): Boolean = track != null && !stopFlag

    fun play(pcm: FloatArray, sampleRate: Int, loop: Boolean) {
        stop()
        val frames = pcm.size / 2
        if (frames == 0) return
        this.loop = loop
        totalFrames = frames
        val minBuf = AudioTrack.getMinBufferSize(
            sampleRate, AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_FLOAT
        )
        val bufBytes = maxOf(minBuf, 16384 * 8)
        val t: AudioTrack
        try {
            t = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                        .setSampleRate(sampleRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                        .build()
                )
                .setBufferSizeInBytes(bufBytes)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()
        } catch (e: Exception) {
            return
        }
        stopFlag = false
        track = t
        Thread {
            try {
                t.play()
                var pos = 0
                var writtenFrames = 0L
                val chunk = 8192 * 2
                while (!stopFlag) {
                    if (pos >= pcm.size) {
                        if (this.loop) pos = 0 else break
                    }
                    val n = minOf(chunk, pcm.size - pos)
                    val w = t.write(pcm, pos, n, AudioTrack.WRITE_BLOCKING)
                    if (w <= 0) break
                    pos += w
                    writtenFrames += (w / 2).toLong()
                }
                // let the tail finish before releasing
                while (!stopFlag && !this.loop && t.playbackHeadPosition.toLong() < writtenFrames) {
                    Thread.sleep(10)
                }
            } catch (e: Exception) {
                // playback ended or the track was released
            } finally {
                try { t.stop() } catch (e: Exception) { }
                try { t.release() } catch (e: Exception) { }
                if (track === t) {
                    stopFlag = true
                    track = null
                }
            }
        }.start()
    }

    fun stop() {
        stopFlag = true
        val t = track
        if (t != null) {
            try { t.pause(); t.flush() } catch (e: Exception) { }
        }
        track = null
    }

    /** Playhead position as 0..1, or -1 when nothing is playing. */
    fun fraction(): Float {
        val t = track ?: return -1f
        if (stopFlag || totalFrames <= 0) return -1f
        return try {
            val head = t.playbackHeadPosition.toLong()
            if (loop) ((head % totalFrames).toFloat() / totalFrames)
            else minOf(1f, head.toFloat() / totalFrames)
        } catch (e: Exception) {
            -1f
        }
    }
}
