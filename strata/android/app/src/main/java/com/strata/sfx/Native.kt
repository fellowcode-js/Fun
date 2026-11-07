package com.strata.sfx

import org.json.JSONArray
import org.json.JSONObject

/** Thin wrapper over the C++ engine. Text crosses the boundary as UTF-8 bytes. */
object Native {
    init {
        System.loadLibrary("strata")
    }

    @JvmStatic external fun schema(): ByteArray
    @JvmStatic external fun aiPrompt(): ByteArray
    @JvmStatic external fun generate(
        category: ByteArray, seed: Long, size: Double, energy: Double,
        hardness: Double, space: Double, chaos: Double
    ): ByteArray

    @JvmStatic external fun normalize(json: ByteArray): ByteArray
    @JvmStatic external fun mutate(json: ByteArray, amount: Double, seed: Long): ByteArray
    @JvmStatic external fun render(json: ByteArray): Long
    @JvmStatic external fun lastError(): ByteArray
    @JvmStatic external fun release(handle: Long)
    @JvmStatic external fun info(handle: Long): DoubleArray
    @JvmStatic external fun pcm(handle: Long): FloatArray
    @JvmStatic external fun envelope(handle: Long, width: Int): FloatArray
    @JvmStatic external fun spectrogram(handle: Long, cols: Int, rows: Int): IntArray
    @JvmStatic external fun wav(handle: Long, bits: Int): ByteArray
    @JvmStatic external fun stemsZip(json: ByteArray, bits: Int): ByteArray?
}

fun ByteArray.utf8(): String = String(this, Charsets.UTF_8)
fun String.utf8(): ByteArray = toByteArray(Charsets.UTF_8)

/** One rendered result, copied out of native memory so the native buffer can be freed immediately. */
class Rendered(
    val sampleRate: Int,
    val duration: Double,
    val peak: Double,
    val rms: Double,
    val renderMs: Double,
    val pcm: FloatArray,
    val envelope: FloatArray,
    val spectrogram: IntArray,
    val specCols: Int,
    val specRows: Int
)

const val SPEC_COLS = 520
const val SPEC_ROWS = 200
const val ENV_COLS = 1000

fun renderRecipe(json: String): Rendered? {
    val h = Native.render(json.utf8())
    if (h == 0L) return null
    try {
        val i = Native.info(h)
        return Rendered(
            i[0].toInt(), i[1], i[2], i[3], i[4],
            Native.pcm(h), Native.envelope(h, ENV_COLS), Native.spectrogram(h, SPEC_COLS, SPEC_ROWS),
            SPEC_COLS, SPEC_ROWS
        )
    } finally {
        Native.release(h)
    }
}

fun renderWav(json: String, bits: Int): ByteArray? {
    val h = Native.render(json.utf8())
    if (h == 0L) return null
    try {
        return Native.wav(h, bits)
    } finally {
        Native.release(h)
    }
}

// ---------- schema model ----------
class ParamDef(
    val key: String,
    val label: String,
    val min: Double,
    val max: Double,
    val def: Double,
    val log: Boolean,
    val isInt: Boolean,
    val unit: String,
    val options: List<Any>?,
    val defOption: Any?
)

class GroupDef(val name: String, val params: List<ParamDef>)

class TypeSchema(
    val id: String,
    val label: String,
    val about: String,
    val params: List<ParamDef>,
    val common: List<GroupDef>
)

class Schema(
    val types: List<TypeSchema>,
    val master: List<GroupDef>,
    val categories: List<Pair<String, String>>
) {
    fun type(id: String): TypeSchema? = types.firstOrNull { it.id == id }
}

private fun parseParam(o: JSONObject): ParamDef {
    val opts: List<Any>? = if (o.has("options")) {
        val a: JSONArray = o.getJSONArray("options")
        val l = ArrayList<Any>()
        for (i in 0 until a.length()) l.add(a.get(i))
        l
    } else null
    return ParamDef(
        o.getString("key"), o.getString("label"),
        o.optDouble("min", 0.0), o.optDouble("max", 1.0),
        if (opts == null) o.optDouble("def", 0.0) else 0.0,
        o.optBoolean("log", false), o.optBoolean("int", false), o.optString("unit", ""),
        opts, if (opts != null) o.get("def") else null
    )
}

private fun parseGroups(a: JSONArray): List<GroupDef> {
    val out = ArrayList<GroupDef>()
    for (i in 0 until a.length()) {
        val g = a.getJSONObject(i)
        val ps = g.getJSONArray("params")
        val list = ArrayList<ParamDef>()
        for (j in 0 until ps.length()) list.add(parseParam(ps.getJSONObject(j)))
        out.add(GroupDef(g.getString("group"), list))
    }
    return out
}

fun loadSchema(): Schema {
    val root = JSONObject(Native.schema().utf8())
    val types = ArrayList<TypeSchema>()
    val ta = root.getJSONArray("types")
    for (i in 0 until ta.length()) {
        val t = ta.getJSONObject(i)
        val ps = t.getJSONArray("params")
        val plist = ArrayList<ParamDef>()
        for (j in 0 until ps.length()) plist.add(parseParam(ps.getJSONObject(j)))
        types.add(TypeSchema(t.getString("id"), t.getString("label"), t.getString("about"), plist, parseGroups(t.getJSONArray("common"))))
    }
    val cats = ArrayList<Pair<String, String>>()
    val ca = root.getJSONArray("categories")
    for (i in 0 until ca.length()) {
        val c = ca.getJSONArray(i)
        cats.add(Pair(c.getString(0), c.getString(1)))
    }
    return Schema(types, parseGroups(root.getJSONArray("master")), cats)
}
