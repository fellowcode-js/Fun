package com.strata.sfx

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.text.InputType
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.math.BigDecimal
import java.math.MathContext
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

class MainActivity : Activity() {
    private companion object {
        const val BG = "#0F1316"
        const val PANEL = "#161C20"
        const val PANEL2 = "#1D252B"
        const val LINE = "#27323A"
        const val FG = "#E7EDF0"
        const val DIM = "#8C9BA4"
        const val ACCENT = "#F2A65A"
        const val ON_ACCENT = "#1A1208"
        const val DANGER = "#F07A6A"
        const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
        const val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT
        val TYPE_COLORS = mapOf(
            "noise" to "#6BB8D6", "osc" to "#C39BF0", "modal" to "#F2A65A", "string" to "#8FD18A",
            "grain" to "#E88FB4", "debris" to "#E3D36A", "wind" to "#86D6C4", "bubble" to "#7DA4F7",
            "motor" to "#EF8F7A", "voice" to "#B5A7FF", "friction" to "#C9C1A4"
        )
        // key, label, low word, high word
        val MACRO_DEFS = arrayOf(
            arrayOf("Size", "small", "huge"),
            arrayOf("Energy", "gentle", "violent"),
            arrayOf("Hardness", "soft", "hard"),
            arrayOf("Space", "dry", "cavernous"),
            arrayOf("Chaos", "controlled", "messy")
        )
    }

    private lateinit var schema: Schema
    private var recipe = JSONObject()
    private val open = HashSet<Int>()
    private val hist = ArrayList<String>()
    private val handler = Handler(Looper.getMainLooper())
    private val exec = Executors.newSingleThreadExecutor()
    private val token = AtomicInteger(0)
    private val player = Player()
    private var last: Rendered? = null
    private var firstRender = true
    private var recipeCardOpen = false
    private var jsonDirty = true

    private lateinit var analyzer: AnalyzerView
    private lateinit var infoText: TextView
    private lateinit var seedEdit: EditText
    private lateinit var jsonEdit: EditText
    private lateinit var layersHost: LinearLayout
    private lateinit var masterHost: LinearLayout
    private lateinit var undoBtn: Button
    private lateinit var genLabel: TextView
    private lateinit var catSpinner: Spinner
    private lateinit var mutSpinner: Spinner
    private lateinit var bitsSpinner: Spinner
    private lateinit var loopBox: CheckBox
    private lateinit var autoBox: CheckBox
    private lateinit var ioStatus: TextView
    private lateinit var exStatus: TextView
    private val macros = doubleArrayOf(0.5, 0.5, 0.5, 0.4, 0.4)
    private val macroSeeks = ArrayList<SeekBar>()
    private val macroTexts = ArrayList<TextView>()

    private val renderRun = Runnable { doRender() }
    private val tick = object : Runnable {
        override fun run() {
            val f = player.fraction()
            analyzer.setPlayhead(f)
            if (f >= 0f) handler.postDelayed(this, 33)
        }
    }

    // ---------- helpers ----------
    private fun dp(v: Int): Int = (v * resources.displayMetrics.density + 0.5f).toInt()

    private fun lp(w: Int, h: Int, weight: Float = 0f, l: Int = 0, t: Int = 0, r: Int = 0, b: Int = 0): LinearLayout.LayoutParams {
        val p = LinearLayout.LayoutParams(w, h, weight)
        p.setMargins(dp(l), dp(t), dp(r), dp(b))
        return p
    }

    private fun roundBg(color: String, radius: Int, stroke: String? = null): GradientDrawable {
        val d = GradientDrawable()
        d.setColor(Color.parseColor(color))
        d.cornerRadius = dp(radius).toFloat()
        if (stroke != null) d.setStroke(dp(1), Color.parseColor(stroke))
        return d
    }

    private fun label(s: String, size: Float = 14f, color: String = FG, bold: Boolean = false): TextView {
        val t = TextView(this)
        t.text = s
        t.textSize = size
        t.setTextColor(Color.parseColor(color))
        if (bold) t.setTypeface(t.typeface, Typeface.BOLD)
        return t
    }

    private fun button(s: String, primary: Boolean = false, small: Boolean = false, color: String? = null, onClick: () -> Unit): Button {
        val b = Button(this)
        b.text = s
        b.isAllCaps = false
        b.textSize = if (small) 12f else 14f
        b.setTextColor(Color.parseColor(if (primary) ON_ACCENT else (color ?: FG)))
        b.background = roundBg(if (primary) ACCENT else PANEL2, 7, if (primary) ACCENT else LINE)
        b.minHeight = 0
        b.minimumHeight = dp(if (small) 32 else 42)
        b.minWidth = 0
        b.minimumWidth = 0
        b.setPadding(dp(if (small) 8 else 14), 0, dp(if (small) 8 else 14), 0)
        b.setOnClickListener { onClick() }
        return b
    }

    private fun card(): LinearLayout {
        val c = LinearLayout(this)
        c.orientation = LinearLayout.VERTICAL
        c.background = roundBg(PANEL, 10, LINE)
        c.setPadding(dp(12), dp(12), dp(12), dp(12))
        return c
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_SHORT).show()

    private fun optText(o: Any): String {
        if (o is Number) {
            val d = o.toDouble()
            return if (d == Math.floor(d)) d.toLong().toString() else d.toString()
        }
        return o.toString()
    }

    private fun fmt(p: ParamDef, v: Double): String {
        val us = Locale.US
        return when (p.unit) {
            "dB" -> String.format(us, "%.1f dB", v)
            "Hz" -> if (v >= 1000) String.format(us, "%.2f kHz", v / 1000) else "${Math.round(v)} Hz"
            "s" -> if (v < 1) "${Math.round(v * 1000)} ms" else String.format(us, "%.2f s", v)
            "ms" -> if (v < 10) String.format(us, "%.1f ms", v) else "${Math.round(v)} ms"
            "ct" -> "${Math.round(v)} ct"
            "/s" -> if (v < 10) String.format(us, "%.1f/s", v) else "${Math.round(v)}/s"
            else -> if (p.isInt) "${Math.round(v)}" else if (Math.abs(v) >= 10) String.format(us, "%.1f", v) else String.format(us, "%.2f", v)
        }
    }

    private fun toPos(p: ParamDef, v: Double): Int {
        val x = if (p.log) 1000 * Math.log(v / p.min) / Math.log(p.max / p.min) else 1000 * (v - p.min) / (p.max - p.min)
        return Math.round(x).toInt().coerceIn(0, 1000)
    }

    private fun fromPos(p: ParamDef, pos: Int): Double {
        val t = pos / 1000.0
        var v = if (p.log) p.min * Math.pow(p.max / p.min, t) else p.min + (p.max - p.min) * t
        v = if (p.isInt) Math.round(v).toDouble() else BigDecimal(v).round(MathContext(3)).toDouble()
        return v.coerceIn(p.min, p.max)
    }

    // ---------- lifecycle ----------
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.parseColor(BG)
        window.navigationBarColor = Color.parseColor(BG)
        schema = loadSchema()
        recipe = JSONObject(Native.generate("explosion".utf8(), 20261105L, 0.55, 0.7, 0.5, 0.5, 0.4).utf8())
        open.add(0)
        buildUi()
        buildLayers()
        buildMaster()
        refreshSeed()
        scheduleRender(0)
    }

    override fun onPause() {
        super.onPause()
        player.stop()
    }

    override fun onDestroy() {
        super.onDestroy()
        player.stop()
        handler.removeCallbacksAndMessages(null)
        exec.shutdownNow()
    }

    // ---------- UI ----------
    private fun buildUi() {
        val scroll = ScrollView(this)
        scroll.setBackgroundColor(Color.parseColor(BG))
        scroll.fitsSystemWindows = true
        val root = LinearLayout(this)
        root.orientation = LinearLayout.VERTICAL
        root.setPadding(dp(14), dp(10), dp(14), dp(60))
        scroll.addView(root, ViewGroup.LayoutParams(MATCH, WRAP))

        // header + seed
        root.addView(label("Strata", 28f, FG, true))
        root.addView(label("Procedural sound effects. Stack layers of noise, FM, resonant bodies, strings, grains, debris, wind, bubbles, motors, voices and friction. Rendered natively.", 13f, DIM), lp(MATCH, WRAP, 0f, 0, 2, 0, 8))
        val seedRow = LinearLayout(this)
        seedRow.gravity = Gravity.CENTER_VERTICAL
        seedRow.addView(label("SEED", 11f, DIM), lp(WRAP, WRAP, 0f, 0, 0, 8, 0))
        seedEdit = EditText(this)
        seedEdit.inputType = InputType.TYPE_CLASS_NUMBER
        seedEdit.setTextColor(Color.parseColor(FG))
        seedEdit.typeface = Typeface.MONOSPACE
        seedEdit.textSize = 14f
        seedEdit.setSingleLine(true)
        seedEdit.imeOptions = EditorInfo.IME_ACTION_DONE
        seedEdit.background = roundBg(PANEL, 6, LINE)
        seedEdit.setPadding(dp(10), dp(6), dp(10), dp(6))
        seedEdit.setOnEditorActionListener { _, _, _ -> applySeed(); true }
        seedRow.addView(seedEdit, lp(dp(130), WRAP, 0f, 0, 0, 8, 0))
        seedRow.addView(button("Vary", false, true) {
            pushHist()
            recipe.put("seed", (Math.random() * 999999999).toLong())
            refreshSeed()
            changed()
        })
        root.addView(seedRow, lp(MATCH, WRAP, 0f, 0, 0, 0, 10))

        // analyzer + transport
        val stage = card()
        stage.setPadding(0, 0, 0, 0)
        analyzer = AnalyzerView(this)
        stage.addView(analyzer, LinearLayout.LayoutParams(MATCH, dp(220)))
        val tr = LinearLayout(this)
        tr.gravity = Gravity.CENTER_VERTICAL
        tr.setPadding(dp(10), dp(10), dp(10), dp(4))
        tr.addView(button("Play", true) { playNow() })
        tr.addView(button("Stop") { player.stop(); analyzer.setPlayhead(-1f) }, lp(WRAP, WRAP, 0f, 8, 0, 8, 0))
        infoText = label("Rendering...", 11f, DIM)
        infoText.typeface = Typeface.MONOSPACE
        tr.addView(infoText, lp(0, WRAP, 1f))
        stage.addView(tr)
        val opts = LinearLayout(this)
        opts.setPadding(dp(10), 0, dp(10), dp(8))
        loopBox = CheckBox(this)
        loopBox.text = "Loop"
        loopBox.setTextColor(Color.parseColor(DIM))
        loopBox.setOnCheckedChangeListener { _, checked -> player.loop = checked }
        autoBox = CheckBox(this)
        autoBox.text = "Auto-preview"
        autoBox.isChecked = true
        autoBox.setTextColor(Color.parseColor(DIM))
        opts.addView(loopBox, lp(WRAP, WRAP, 0f, 0, 0, 16, 0))
        opts.addView(autoBox)
        stage.addView(opts)
        root.addView(stage, lp(MATCH, WRAP, 0f, 0, 0, 0, 12))

        root.addView(buildGeneratorCard(), lp(MATCH, WRAP, 0f, 0, 0, 0, 14))

        root.addView(label("LAYERS", 12f, DIM, true), lp(MATCH, WRAP, 0f, 0, 0, 0, 6))
        layersHost = LinearLayout(this)
        layersHost.orientation = LinearLayout.VERTICAL
        root.addView(layersHost)
        root.addView(buildAdders(), lp(MATCH, WRAP, 0f, 0, 8, 0, 14))

        masterHost = LinearLayout(this)
        masterHost.orientation = LinearLayout.VERTICAL
        root.addView(collapsible("Master bus", masterHost, false, null), lp(MATCH, WRAP, 0f, 0, 0, 0, 12))

        root.addView(buildRecipeCard(), lp(MATCH, WRAP, 0f, 0, 0, 0, 12))
        root.addView(buildExportCard())

        setContentView(scroll)
    }

    private fun collapsible(title: String, content: View, startOpen: Boolean, onToggle: ((Boolean) -> Unit)?): View {
        val c = card()
        val head = label("", 12f, DIM, true)
        fun setHead(o: Boolean) { head.text = title.uppercase(Locale.US) + (if (o) "   −" else "   +") }
        content.visibility = if (startOpen) View.VISIBLE else View.GONE
        setHead(startOpen)
        head.setOnClickListener {
            val o = content.visibility != View.VISIBLE
            content.visibility = if (o) View.VISIBLE else View.GONE
            setHead(o)
            onToggle?.invoke(o)
        }
        head.setPadding(0, dp(4), 0, dp(4))
        c.addView(head)
        c.addView(content)
        return c
    }

    private fun buildGeneratorCard(): View {
        val c = card()
        catSpinner = Spinner(this)
        val names = ArrayList<String>()
        names.add("Any (random type)")
        for (p in schema.categories) names.add(p.second)
        val ad = ArrayAdapter(this, android.R.layout.simple_spinner_item, names)
        ad.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        catSpinner.adapter = ad
        catSpinner.setSelection(2)
        c.addView(label("Sound type", 13f, DIM))
        c.addView(catSpinner, lp(MATCH, WRAP, 0f, 0, 0, 0, 6))
        for (i in MACRO_DEFS.indices) {
            val d = MACRO_DEFS[i]
            val top = LinearLayout(this)
            val name = label(d[0], 13f)
            val value = label("", 12f, DIM)
            value.typeface = Typeface.MONOSPACE
            top.addView(name, lp(0, WRAP, 1f))
            top.addView(value)
            val sb = SeekBar(this)
            sb.max = 100
            sb.progress = Math.round(macros[i] * 100).toInt()
            sb.progressTintList = android.content.res.ColorStateList.valueOf(Color.parseColor(ACCENT))
            sb.thumbTintList = android.content.res.ColorStateList.valueOf(Color.parseColor(ACCENT))
            val show = { v: Int -> value.text = if (v < 34) d[1] else if (v > 66) d[2] else "medium" }
            show(sb.progress)
            sb.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(s: SeekBar?, p: Int, fromUser: Boolean) {
                    macros[i] = p / 100.0
                    show(p)
                }
                override fun onStartTrackingTouch(s: SeekBar?) {}
                override fun onStopTrackingTouch(s: SeekBar?) {}
            })
            macroSeeks.add(sb)
            macroTexts.add(value)
            c.addView(top, lp(MATCH, WRAP, 0f, 0, 4, 0, 0))
            c.addView(sb, lp(MATCH, WRAP))
        }
        val row = LinearLayout(this)
        row.addView(button("Generate", true) { runGenerate(selectedCategory()) }, lp(0, WRAP, 1f, 0, 0, 6, 0))
        row.addView(button("Surprise me") {
            for (i in macros.indices) {
                macros[i] = Math.round(Math.random() * 100) / 100.0
                macroSeeks[i].progress = Math.round(macros[i] * 100).toInt()
            }
            catSpinner.setSelection(0)
            runGenerate("any")
        }, lp(0, WRAP, 1f))
        c.addView(row, lp(MATCH, WRAP, 0f, 0, 10, 0, 0))
        genLabel = label("", 12f, DIM)
        c.addView(genLabel, lp(MATCH, WRAP, 0f, 0, 6, 0, 6))

        val row2 = LinearLayout(this)
        row2.gravity = Gravity.CENTER_VERTICAL
        mutSpinner = Spinner(this)
        val ma = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("Subtle", "Medium", "Wild"))
        ma.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        mutSpinner.adapter = ma
        mutSpinner.setSelection(1)
        row2.addView(mutSpinner, lp(0, WRAP, 1f, 0, 0, 6, 0))
        row2.addView(button("Mutate") {
            pushHist()
            val amt = doubleArrayOf(0.12, 0.3, 0.7)[mutSpinner.selectedItemPosition]
            val s = Native.mutate(recipe.toString().utf8(), amt, -1L).utf8()
            loadRecipe(s, true)
        }, lp(WRAP, WRAP, 0f, 0, 0, 6, 0))
        undoBtn = button("Undo") { undo() }
        undoBtn.isEnabled = false
        row2.addView(undoBtn)
        c.addView(row2)
        c.addView(label("Every generation samples new parameters. The same recipe and seed always render the same sound.", 11f, DIM), lp(MATCH, WRAP, 0f, 0, 6, 0, 0))
        return c
    }

    private fun selectedCategory(): String {
        val i = catSpinner.selectedItemPosition
        return if (i <= 0) "any" else schema.categories[i - 1].first
    }

    private fun buildAdders(): View {
        val col = LinearLayout(this)
        col.orientation = LinearLayout.VERTICAL
        val ts = schema.types
        var i = 0
        while (i < ts.size) {
            val row = LinearLayout(this)
            for (j in i until minOf(i + 3, ts.size)) {
                val t = ts[j]
                val b = button("+ " + t.label, false, false, TYPE_COLORS[t.id]) { addLayer(t.id) }
                row.addView(b, lp(0, WRAP, 1f, 0, 0, 6, 6))
            }
            col.addView(row)
            i += 3
        }
        return col
    }

    private fun buildRecipeCard(): View {
        val body = LinearLayout(this)
        body.orientation = LinearLayout.VERTICAL
        body.addView(label("The whole sound is one JSON recipe. Paste one from any AI, or copy the brief below so an AI can write recipes for you.", 12f, DIM), lp(MATCH, WRAP, 0f, 0, 6, 0, 8))
        jsonEdit = EditText(this)
        jsonEdit.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        jsonEdit.typeface = Typeface.MONOSPACE
        jsonEdit.textSize = 11f
        jsonEdit.setTextColor(Color.parseColor(FG))
        jsonEdit.gravity = Gravity.TOP
        jsonEdit.minLines = 8
        jsonEdit.maxLines = 14
        jsonEdit.background = roundBg(PANEL2, 8, LINE)
        jsonEdit.setPadding(dp(10), dp(10), dp(10), dp(10))
        body.addView(jsonEdit, lp(MATCH, WRAP))
        val r1 = LinearLayout(this)
        r1.addView(button("Apply JSON", true) { applyJson() }, lp(0, WRAP, 1f, 0, 8, 6, 0))
        r1.addView(button("Copy recipe") {
            syncJson()
            copyText("Strata recipe", jsonEdit.text.toString(), "Recipe copied.")
        }, lp(0, WRAP, 1f, 0, 8, 0, 0))
        body.addView(r1)
        val r2 = LinearLayout(this)
        r2.addView(button("Copy AI brief") { copyText("Strata AI brief", Native.aiPrompt().utf8(), "AI brief copied. Paste it into any AI chat, then describe the sound you want.") }, lp(0, WRAP, 1f, 0, 6, 6, 0))
        r2.addView(button("Save .json") { saveRecipeJson() }, lp(0, WRAP, 1f, 0, 6, 0, 0))
        body.addView(r2)
        ioStatus = label("", 12f, DIM)
        body.addView(ioStatus, lp(MATCH, WRAP, 0f, 0, 6, 0, 0))
        return collapsible("Recipe and AI", body, false) { o ->
            recipeCardOpen = o
            if (o) syncJson()
        }
    }

    private fun buildExportCard(): View {
        val c = card()
        bitsSpinner = Spinner(this)
        val ba = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("24-bit WAV", "16-bit WAV", "32-bit float WAV"))
        ba.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        bitsSpinner.adapter = ba
        c.addView(bitsSpinner, lp(MATCH, WRAP, 0f, 0, 0, 0, 6))
        val row = LinearLayout(this)
        row.addView(button("Export WAV", true) { exportWav() }, lp(0, WRAP, 1f, 0, 0, 6, 0))
        row.addView(button("Export stems") { exportStems() }, lp(0, WRAP, 1f))
        c.addView(row)
        c.addView(label("Files go to Downloads/Strata. Stems are one aligned WAV per layer, with the room and master applied, inside a .zip.", 11f, DIM), lp(MATCH, WRAP, 0f, 0, 6, 0, 0))
        exStatus = label("", 12f, DIM)
        c.addView(exStatus, lp(MATCH, WRAP, 0f, 0, 4, 0, 0))
        return c
    }

    // ---------- parameter controls ----------
    private fun paramView(p: ParamDef, obj: JSONObject, onChanged: () -> Unit): View {
        val w = LinearLayout(this)
        w.orientation = LinearLayout.VERTICAL
        w.setPadding(0, dp(4), 0, dp(4))
        val top = LinearLayout(this)
        top.addView(label(p.label, 13f), lp(0, WRAP, 1f))
        val value = label("", 12f, DIM)
        value.typeface = Typeface.MONOSPACE
        top.addView(value)
        w.addView(top)
        val opts = p.options
        if (opts != null) {
            val names = opts.map { optText(it) }
            val cur: String = if (opts[0] is Number) optText(obj.optDouble(p.key, (p.defOption as Number).toDouble())) else obj.optString(p.key, p.defOption.toString())
            var idx = names.indexOf(cur)
            if (idx < 0) idx = 0
            val sp = Spinner(this)
            val ad = ArrayAdapter(this, android.R.layout.simple_spinner_item, names)
            ad.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            sp.adapter = ad
            sp.setSelection(idx, false)
            var currentIdx = idx
            sp.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: AdapterView<*>?, v: View?, pos: Int, id: Long) {
                    if (pos == currentIdx) return
                    currentIdx = pos
                    if (opts[0] is Number) obj.put(p.key, names[pos].toDouble()) else obj.put(p.key, names[pos])
                    onChanged()
                }
                override fun onNothingSelected(parent: AdapterView<*>?) {}
            }
            w.addView(sp, lp(MATCH, WRAP))
        } else {
            val v0 = obj.optDouble(p.key, p.def)
            value.text = fmt(p, v0)
            val sb = SeekBar(this)
            sb.max = 1000
            sb.progress = toPos(p, v0)
            sb.progressTintList = android.content.res.ColorStateList.valueOf(Color.parseColor(ACCENT))
            sb.thumbTintList = android.content.res.ColorStateList.valueOf(Color.parseColor(ACCENT))
            sb.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(s: SeekBar?, pr: Int, fromUser: Boolean) {
                    if (!fromUser) return
                    val v = fromPos(p, pr)
                    value.text = fmt(p, v)
                    putNumber(obj, p, v)
                }
                override fun onStartTrackingTouch(s: SeekBar?) {}
                override fun onStopTrackingTouch(s: SeekBar?) {
                    val v = fromPos(p, s?.progress ?: 0)
                    putNumber(obj, p, v)
                    onChanged()
                }
            })
            w.addView(sb, lp(MATCH, WRAP))
        }
        return w
    }

    private fun putNumber(obj: JSONObject, p: ParamDef, v: Double) {
        if (p.isInt) obj.put(p.key, v.toInt()) else obj.put(p.key, v)
    }

    private fun groupView(title: String, params: List<ParamDef>, obj: JSONObject, startOpen: Boolean, onChanged: () -> Unit): View {
        val g = LinearLayout(this)
        g.orientation = LinearLayout.VERTICAL
        val head = label("", 11f, DIM, true)
        val body = LinearLayout(this)
        body.orientation = LinearLayout.VERTICAL
        for (p in params) body.addView(paramView(p, obj, onChanged))
        fun setHead(o: Boolean) { head.text = (if (o) "▾  " else "▸  ") + title.uppercase(Locale.US) }
        body.visibility = if (startOpen) View.VISIBLE else View.GONE
        setHead(startOpen)
        head.setPadding(0, dp(10), 0, dp(6))
        head.setOnClickListener {
            val o = body.visibility != View.VISIBLE
            body.visibility = if (o) View.VISIBLE else View.GONE
            setHead(o)
        }
        g.addView(head)
        g.addView(body)
        return g
    }

    // ---------- layers ----------
    private fun summaryText(l: JSONObject): String {
        val us = Locale.US
        val dur = l.optDouble("dur", 1.0)
        val gain = l.optDouble("gain", -6.0)
        val rep = l.optInt("repeat", 1)
        return String.format(us, "%.2fs +", l.optDouble("start", 0.0)) +
            (if (dur < 1) "${Math.round(dur * 1000)}ms" else String.format(us, "%.2fs", dur)) +
            " · " + (if (gain > 0) "+" else "") + String.format(us, "%.0f dB", gain) +
            (if (rep > 1) " · ×$rep" else "")
    }

    private fun layerList(): MutableList<JSONObject> {
        val a = recipe.getJSONArray("layers")
        val l = ArrayList<JSONObject>()
        for (i in 0 until a.length()) l.add(a.getJSONObject(i))
        return l
    }

    private fun setLayerList(l: List<JSONObject>) {
        val a = JSONArray()
        for (o in l) a.put(o)
        recipe.put("layers", a)
    }

    private fun shiftOpen(at: Int, delta: Int) {
        val n = HashSet<Int>()
        for (j in open) {
            if (delta < 0 && j == at) continue
            n.add(if (j > at) j + delta else j)
        }
        open.clear()
        open.addAll(n)
    }

    private fun buildLayers() {
        layersHost.removeAllViews()
        val layers = layerList()
        if (layers.isEmpty()) {
            layersHost.addView(label("No layers yet. Add one below or generate a stack.", 13f, DIM))
            return
        }
        val anySolo = layers.any { it.optBoolean("solo") }
        for (i in layers.indices) layersHost.addView(layerCard(i, layers[i], anySolo), lp(MATCH, WRAP, 0f, 0, 0, 0, 10))
    }

    private fun layerCard(i: Int, l: JSONObject, anySolo: Boolean): View {
        val id = l.getString("type")
        val t = schema.type(id) ?: return View(this)
        val card = LinearLayout(this)
        card.orientation = LinearLayout.VERTICAL
        card.background = roundBg(PANEL, 10, LINE)
        val muted = l.optBoolean("mute") || (anySolo && !l.optBoolean("solo"))
        card.alpha = if (muted) 0.55f else 1f

        val head = LinearLayout(this)
        head.orientation = LinearLayout.VERTICAL
        head.setPadding(dp(12), dp(10), dp(12), dp(10))
        val line1 = LinearLayout(this)
        line1.gravity = Gravity.CENTER_VERTICAL
        val chipColor = Color.parseColor(TYPE_COLORS[id] ?: ACCENT)
        val chip = label(t.label.uppercase(Locale.US), 11f, TYPE_COLORS[id] ?: ACCENT, true)
        val cd = GradientDrawable()
        cd.setColor(Color.TRANSPARENT)
        cd.cornerRadius = dp(5).toFloat()
        cd.setStroke(dp(2), chipColor)
        chip.background = cd
        chip.setPadding(dp(6), dp(2), dp(6), dp(2))
        line1.addView(chip, lp(WRAP, WRAP, 0f, 0, 0, 10, 0))
        val col = LinearLayout(this)
        col.orientation = LinearLayout.VERTICAL
        val nm = l.optString("name", "")
        val title = label(if (nm.isEmpty()) "${t.label} ${i + 1}" else nm, 15f, FG, true)
        title.maxLines = 1
        title.ellipsize = TextUtils.TruncateAt.END
        val sum = label(summaryText(l), 11f, DIM)
        sum.typeface = Typeface.MONOSPACE
        col.addView(title)
        col.addView(sum)
        line1.addView(col, lp(0, WRAP, 1f))
        line1.addView(label(if (open.contains(i)) "−" else "+", 18f, DIM))
        head.addView(line1)

        val btns = LinearLayout(this)
        btns.gravity = Gravity.END
        btns.addView(button(if (l.optBoolean("solo")) "Unsolo" else "Solo", false, true) {
            pushHist(); l.put("solo", !l.optBoolean("solo")); buildLayers(); changed()
        }, lp(WRAP, WRAP, 0f, 0, 8, 6, 0))
        btns.addView(button(if (l.optBoolean("mute")) "Unmute" else "Mute", false, true) {
            pushHist(); l.put("mute", !l.optBoolean("mute")); buildLayers(); changed()
        }, lp(WRAP, WRAP, 0f, 0, 8, 6, 0))
        btns.addView(button("Copy", false, true) {
            if (layerList().size < 16) {
                pushHist()
                val list = layerList()
                list.add(i + 1, JSONObject(l.toString()))
                shiftOpen(i, 1)
                open.add(i + 1)
                setLayerList(list)
                buildLayers()
                changed()
            }
        }, lp(WRAP, WRAP, 0f, 0, 8, 6, 0))
        btns.addView(button("Delete", false, true, DANGER) {
            pushHist()
            val list = layerList()
            list.removeAt(i)
            shiftOpen(i, -1)
            setLayerList(list)
            buildLayers()
            changed()
        }, lp(WRAP, WRAP, 0f, 0, 8, 0, 0))
        head.addView(btns)
        head.setOnClickListener {
            if (open.contains(i)) open.remove(i) else open.add(i)
            buildLayers()
        }
        card.addView(head)

        if (open.contains(i)) {
            val body = LinearLayout(this)
            body.orientation = LinearLayout.VERTICAL
            body.setPadding(dp(12), 0, dp(12), dp(12))
            val about = label(t.about, 11f, DIM)
            body.addView(about, lp(MATCH, WRAP, 0f, 0, 0, 0, 2))
            val onChanged = { sum.text = summaryText(l); changed() }
            body.addView(groupView("Source", t.params, l, true, onChanged))
            for (g in t.common) body.addView(groupView(g.name, g.params, l, g.name == "Level and timing", onChanged))
            card.addView(body)
        }
        return card
    }

    private fun newLayer(type: String): JSONObject {
        val s = Native.normalize("{\"layers\":[{\"type\":\"$type\"}]}".utf8()).utf8()
        return JSONObject(s).getJSONArray("layers").getJSONObject(0)
    }

    private fun addLayer(type: String) {
        val list = layerList()
        if (list.size >= 16) { toast("A recipe holds up to 16 layers."); return }
        pushHist()
        list.add(newLayer(type))
        setLayerList(list)
        open.add(list.size - 1)
        buildLayers()
        changed()
    }

    private fun buildMaster() {
        masterHost.removeAllViews()
        val m = recipe.getJSONObject("master")
        for (g in schema.master) masterHost.addView(groupView(g.name, g.params, m, g.name == schema.master[0].name, { changed() }))
    }

    // ---------- recipe state ----------
    private fun refreshSeed() { seedEdit.setText(recipe.optLong("seed", 1L).toString()) }

    private fun applySeed() {
        val v = seedEdit.text.toString().toLongOrNull() ?: return
        pushHist()
        recipe.put("seed", v.coerceIn(0L, 999999999L))
        refreshSeed()
        changed()
    }

    private fun syncJson() {
        jsonDirty = false
        jsonEdit.setText(recipe.toString(1))
    }

    private fun pushHist() {
        hist.add(recipe.toString())
        if (hist.size > 40) hist.removeAt(0)
        undoBtn.isEnabled = true
    }

    private fun undo() {
        if (hist.isEmpty()) return
        val h = hist.removeAt(hist.size - 1)
        undoBtn.isEnabled = hist.isNotEmpty()
        loadRecipe(h, true)
    }

    private fun loadRecipe(json: String, keepOpen: Boolean) {
        val norm = Native.normalize(json.utf8()).utf8()
        if (norm.startsWith("ERR:")) { toast(norm.substring(4)); return }
        recipe = JSONObject(norm)
        if (!keepOpen) { open.clear(); open.add(0) }
        open.removeAll(open.filter { it >= recipe.getJSONArray("layers").length() }.toSet())
        refreshSeed()
        buildLayers()
        buildMaster()
        changed()
    }

    private fun runGenerate(category: String) {
        pushHist()
        val s = Native.generate(category.utf8(), -1L, macros[0], macros[1], macros[2], macros[3], macros[4]).utf8()
        loadRecipe(s, false)
        val n = recipe.getJSONArray("layers").length()
        val name = schema.categories.firstOrNull { it.first == category }?.second ?: "random type"
        genLabel.text = "Generated $name · $n layers"
    }

    private fun applyJson() {
        val txt = jsonEdit.text.toString()
        try {
            JSONObject(txt)
        } catch (e: Exception) {
            setStatus(ioStatus, "Could not read that recipe: ${e.message}", true)
            return
        }
        val norm = Native.normalize(txt.utf8()).utf8()
        if (norm.startsWith("ERR:")) { setStatus(ioStatus, "Could not read that recipe: ${norm.substring(4)}", true); return }
        val n = JSONObject(norm).getJSONArray("layers").length()
        if (n == 0) {
            setStatus(ioStatus, "No valid layers found. Each layer needs a \"type\": noise, osc, modal, string, grain, debris, wind, bubble, motor, voice or friction.", true)
            return
        }
        pushHist()
        loadRecipe(norm, false)
        setStatus(ioStatus, "Applied $n layers.", false)
    }

    private fun setStatus(t: TextView, msg: String, err: Boolean) {
        t.text = msg
        t.setTextColor(Color.parseColor(if (err) DANGER else DIM))
    }

    private fun copyText(label: String, text: String, ok: String) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText(label, text))
        setStatus(ioStatus, ok, false)
    }

    // ---------- render and playback ----------
    private fun changed() {
        jsonDirty = true
        if (recipeCardOpen) syncJson()
        scheduleRender(90)
    }

    private fun scheduleRender(delay: Long) {
        handler.removeCallbacks(renderRun)
        handler.postDelayed(renderRun, delay)
    }

    private fun doRender() {
        val json = recipe.toString()
        val my = token.incrementAndGet()
        infoText.text = "Rendering..."
        exec.execute {
            val r: Rendered? = try { renderRecipe(json) } catch (e: Throwable) { null }
            val err: String = if (r == null) Native.lastError().utf8() else ""
            runOnUiThread {
                if (my == token.get()) {
                    if (r == null) {
                        infoText.text = "Render error: $err"
                    } else {
                        last = r
                        analyzer.setData(r)
                        val pk = if (r.peak > 0) 20 * Math.log10(r.peak) else Double.NEGATIVE_INFINITY
                        val rm = if (r.rms > 0) 20 * Math.log10(r.rms) else Double.NEGATIVE_INFINITY
                        infoText.text = String.format(
                            Locale.US, "%.2f s · %.1f kHz · peak %.1f dB · rms %.1f dB · %d ms",
                            r.duration, r.sampleRate / 1000.0, pk, rm, Math.round(r.renderMs)
                        )
                        if (firstRender) firstRender = false
                        else if (autoBox.isChecked) playNow()
                    }
                }
            }
        }
    }

    private fun playNow() {
        val r = last ?: return
        player.play(r.pcm, r.sampleRate, loopBox.isChecked)
        handler.removeCallbacks(tick)
        handler.post(tick)
    }

    // ---------- export ----------
    private fun bitsOf(): Int = intArrayOf(24, 16, 32)[bitsSpinner.selectedItemPosition]

    private fun exportWav() {
        val bits = bitsOf()
        val json = recipe.toString()
        val seed = recipe.optLong("seed", 1L)
        setStatus(exStatus, "Rendering...", false)
        exec.execute {
            try {
                val wav = renderWav(json, bits) ?: throw IOException("render failed")
                val where = saveFile("strata-sfx-$seed.wav", "audio/wav", wav)
                runOnUiThread { setStatus(exStatus, "Saved $where", false) }
            } catch (e: Throwable) {
                runOnUiThread { setStatus(exStatus, "Could not save: ${e.message}", true) }
            }
        }
    }

    private fun exportStems() {
        val bits = bitsOf()
        val json = recipe.toString()
        val seed = recipe.optLong("seed", 1L)
        setStatus(exStatus, "Rendering stems...", false)
        exec.execute {
            try {
                val z = Native.stemsZip(json.utf8(), bits) ?: throw IOException("render failed")
                val where = saveFile("strata-stems-$seed.zip", "application/zip", z)
                runOnUiThread { setStatus(exStatus, "Saved $where", false) }
            } catch (e: Throwable) {
                runOnUiThread { setStatus(exStatus, "Could not save: ${e.message}", true) }
            }
        }
    }

    private fun saveRecipeJson() {
        val seed = recipe.optLong("seed", 1L)
        val bytes = recipe.toString(1).utf8()
        try {
            val where = saveFile("strata-recipe-$seed.json", "application/json", bytes)
            setStatus(ioStatus, "Saved $where", false)
        } catch (e: Throwable) {
            setStatus(ioStatus, "Could not save: ${e.message}", true)
        }
    }

    /** Writes to Downloads/Strata through MediaStore on modern Android, no storage permission needed. */
    private fun saveFile(name: String, mime: String, bytes: ByteArray): String {
        if (Build.VERSION.SDK_INT >= 29) {
            val values = ContentValues()
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            values.put(MediaStore.MediaColumns.MIME_TYPE, mime)
            values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Strata")
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IOException("could not create the file")
            val out = contentResolver.openOutputStream(uri) ?: throw IOException("could not open the file")
            out.use { it.write(bytes) }
            return "Downloads/Strata/$name"
        }
        val dir = getExternalFilesDir(null) ?: filesDir
        val f = File(dir, name)
        f.writeBytes(bytes)
        return f.absolutePath
    }
}
