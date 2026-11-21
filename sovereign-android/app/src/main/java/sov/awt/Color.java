package sov.awt;
public class Color implements Paint {
    public static final Color WHITE = new Color(255, 255, 255), BLACK = new Color(0, 0, 0),
        RED = new Color(255, 0, 0), GREEN = new Color(0, 255, 0), BLUE = new Color(0, 0, 255),
        YELLOW = new Color(255, 255, 0), GRAY = new Color(128, 128, 128), DARK_GRAY = new Color(64, 64, 64),
        LIGHT_GRAY = new Color(192, 192, 192), ORANGE = new Color(255, 200, 0);
    final int v;
    static int c(int x) { return x < 0 ? 0 : x > 255 ? 255 : x; }
    public Color(int r, int g, int b) { this(r, g, b, 255); }
    public Color(int r, int g, int b, int a) { v = (c(a) << 24) | (c(r) << 16) | (c(g) << 8) | c(b); }
    public Color(int rgb) { v = 0xff000000 | rgb; }
    public Color(int argb, boolean hasAlpha) { v = hasAlpha ? argb : 0xff000000 | argb; }
    public Color(float r, float g, float b) { this((int) (r * 255 + .5), (int) (g * 255 + .5), (int) (b * 255 + .5)); }
    public Color(float r, float g, float b, float a) { this((int) (r * 255 + .5), (int) (g * 255 + .5), (int) (b * 255 + .5), (int) (a * 255 + .5)); }
    public int getRed() { return (v >> 16) & 255; }
    public int getGreen() { return (v >> 8) & 255; }
    public int getBlue() { return v & 255; }
    public int getAlpha() { return (v >>> 24); }
    public int getRGB() { return v; }
    public Color brighter() {
        int r = getRed(), g = getGreen(), b = getBlue(), a = getAlpha(); int i = 3;
        if (r == 0 && g == 0 && b == 0) return new Color(i, i, i, a);
        if (r > 0 && r < i) r = i; if (g > 0 && g < i) g = i; if (b > 0 && b < i) b = i;
        return new Color(Math.min((int) (r / .7), 255), Math.min((int) (g / .7), 255), Math.min((int) (b / .7), 255), a);
    }
    public Color darker() { return new Color((int) (getRed() * .7), (int) (getGreen() * .7), (int) (getBlue() * .7), getAlpha()); }
    @Override public boolean equals(Object o) { return o instanceof Color && ((Color) o).v == v; }
    @Override public int hashCode() { return v; }
}
