package sov.awt;
public class FontMetrics {
    final android.graphics.Paint p; final android.graphics.Paint.FontMetricsInt m;
    FontMetrics(Font f) {
        p = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
        p.setTypeface(f.tf); p.setTextSize(f.size); m = p.getFontMetricsInt();
    }
    public int stringWidth(String s) { return s == null ? 0 : Math.round(p.measureText(s)); }
    public int charWidth(char c) { return Math.round(p.measureText(String.valueOf(c))); }
    public int getAscent() { return -m.ascent; }
    public int getDescent() { return m.descent; }
    public int getLeading() { return m.leading; }
    public int getHeight() { return -m.ascent + m.descent + m.leading; }
}
