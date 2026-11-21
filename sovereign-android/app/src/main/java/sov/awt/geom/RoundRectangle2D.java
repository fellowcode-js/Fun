package sov.awt.geom;
public abstract class RoundRectangle2D implements sov.awt.Shape {
    public static class Double extends RoundRectangle2D {
        public double x, y, width, height, arcwidth, archeight;
        public Double(double x, double y, double w, double h, double aw, double ah) { this.x = x; this.y = y; width = w; height = h; arcwidth = aw; archeight = ah; }
        public android.graphics.Path toPath() {
            android.graphics.Path p = new android.graphics.Path();
            p.addRoundRect(new android.graphics.RectF((float) x, (float) y, (float) (x + width), (float) (y + height)), (float) arcwidth / 2, (float) archeight / 2, android.graphics.Path.Direction.CW);
            return p;
        }
    }
}
