package sov.awt;
public class BasicStroke implements Stroke {
    public static final int CAP_BUTT = 0, CAP_ROUND = 1, CAP_SQUARE = 2, JOIN_MITER = 0, JOIN_ROUND = 1, JOIN_BEVEL = 2;
    final float w; final int cap, join; final float[] dash;
    public BasicStroke() { this(1f); }
    public BasicStroke(float w) { this(w, CAP_SQUARE, JOIN_MITER); }
    public BasicStroke(float w, int cap, int join) { this(w, cap, join, 10f, null, 0f); }
    public BasicStroke(float w, int cap, int join, float miter) { this(w, cap, join, miter, null, 0f); }
    public BasicStroke(float w, int cap, int join, float miter, float[] dash, float phase) { this.w = w; this.cap = cap; this.join = join; this.dash = dash; }
    public float getLineWidth() { return w; }
}
