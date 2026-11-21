package sov.awt.geom;
public abstract class Path2D implements sov.awt.Shape {
    final android.graphics.Path p = new android.graphics.Path();
    public void moveTo(double x, double y) { p.moveTo((float) x, (float) y); }
    public void lineTo(double x, double y) { p.lineTo((float) x, (float) y); }
    public void quadTo(double a, double b, double x, double y) { p.quadTo((float) a, (float) b, (float) x, (float) y); }
    public void curveTo(double a, double b, double c, double d, double x, double y) { p.cubicTo((float) a, (float) b, (float) c, (float) d, (float) x, (float) y); }
    public void closePath() { p.close(); }
    public void reset() { p.reset(); }
    public android.graphics.Path toPath() { return p; }
    public static class Double extends Path2D { public Double() {} }
    public static class Float extends Path2D { public Float() {} }
}
