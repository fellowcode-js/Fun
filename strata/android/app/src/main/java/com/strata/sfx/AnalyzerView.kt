package com.strata.sfx

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.view.View
import kotlin.math.ln

/** Waveform on top, spectrogram below, with a playhead. All pixels come from the C++ engine. */
class AnalyzerView(context: Context) : View(context) {
    private var env: FloatArray? = null
    private var bmp: Bitmap? = null
    private var sampleRate = 48000
    private var playhead = -1f

    private val bg = Paint().apply { color = Color.parseColor("#0A0E11") }
    private val mid = Paint().apply { color = Color.parseColor("#1C262D"); strokeWidth = 1f }
    private val wave = Paint().apply { color = Color.parseColor("#D9F3EF"); strokeWidth = 1f }
    private val head = Paint().apply { color = Color.parseColor("#F2A65A"); strokeWidth = 3f }
    private val text = Paint().apply {
        color = Color.argb(140, 255, 255, 255)
        textSize = 26f
        isAntiAlias = true
    }
    private val bmpPaint = Paint().apply { isFilterBitmap = true }

    fun setData(r: Rendered) {
        val old = bmp
        bmp = Bitmap.createBitmap(r.spectrogram, r.specCols, r.specRows, Bitmap.Config.ARGB_8888)
        old?.recycle()
        env = r.envelope
        sampleRate = r.sampleRate
        invalidate()
    }

    fun setPlayhead(f: Float) {
        if (f != playhead) {
            playhead = f
            invalidate()
        }
    }

    override fun onDraw(c: Canvas) {
        val w = width
        val h = height
        c.drawRect(0f, 0f, w.toFloat(), h.toFloat(), bg)
        val wh = (h * 0.34f)
        c.drawLine(0f, wh / 2, w.toFloat(), wh / 2, mid)
        val e = env
        if (e != null && w > 0) {
            val cols = e.size / 2
            for (x in 0 until w) {
                val i = minOf(cols - 1, x * cols / w)
                val y1 = (0.5f - e[i * 2 + 1] * 0.48f) * wh
                var y2 = (0.5f - e[i * 2] * 0.48f) * wh
                if (y2 - y1 < 1f) y2 = y1 + 1f
                c.drawLine(x.toFloat(), y1, x.toFloat(), y2, wave)
            }
        }
        val b = bmp
        if (b != null) {
            val sh = h - wh
            c.drawBitmap(b, Rect(0, 0, b.width, b.height), RectF(0f, wh, w.toFloat(), h.toFloat()), bmpPaint)
            val fmin = 30.0
            val fmax = sampleRate / 2.0 * 0.95
            for (f in intArrayOf(100, 1000, 10000)) {
                val y = wh + (1 - ln(f / fmin) / ln(fmax / fmin)).toFloat() * sh
                if (y > wh + 8 && y < h - 8) {
                    c.drawLine(0f, y, 14f, y, text)
                    c.drawText(if (f >= 1000) "${f / 1000}k" else "$f", 20f, y + 9f, text)
                }
            }
        }
        if (playhead in 0f..1f) c.drawLine(playhead * w, 0f, playhead * w, h.toFloat(), head)
    }
}
