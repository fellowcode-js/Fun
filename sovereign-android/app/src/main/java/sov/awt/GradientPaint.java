package sov.awt;
public class GradientPaint implements Paint {
    final float x1, y1, x2, y2; final Color c1, c2;
    public GradientPaint(float x1, float y1, Color c1, float x2, float y2, Color c2) { this.x1 = x1; this.y1 = y1; this.c1 = c1; this.x2 = x2; this.y2 = y2; this.c2 = c2; }
}
