package sov.awt;
import android.graphics.Typeface;
public class Font {
    public static final int PLAIN = 0, BOLD = 1, ITALIC = 2;
    public static final String SANS_SERIF = "SansSerif", SERIF = "Serif", MONOSPACED = "Monospaced", DIALOG = "Dialog";
    final String name; final int style; final float size; final Typeface tf;
    public Font(String name, int style, int size) { this(name, style, (float) size); }
    Font(String name, int style, float size) {
        this.name = name; this.style = style; this.size = size;
        Typeface base = "Serif".equals(name) ? Typeface.SERIF : "Monospaced".equals(name) ? Typeface.MONOSPACE : Typeface.SANS_SERIF;
        tf = Typeface.create(base, style == 0 ? Typeface.NORMAL : style == 1 ? Typeface.BOLD : style == 2 ? Typeface.ITALIC : Typeface.BOLD_ITALIC);
    }
    public int getSize() { return Math.round(size); }
    public float getSize2D() { return size; }
    public int getStyle() { return style; }
    public Font deriveFont(float s) { return new Font(name, style, s); }
    public Font deriveFont(int st) { return new Font(name, st, size); }
    public Font deriveFont(int st, float s) { return new Font(name, st, s); }
}
