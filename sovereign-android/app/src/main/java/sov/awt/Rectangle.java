package sov.awt;
public class Rectangle implements Shape {
    public int x, y, width, height;
    public Rectangle() {}
    public Rectangle(int x, int y, int w, int h) { setBounds(x, y, w, h); }
    public void setBounds(int x, int y, int w, int h) { this.x = x; this.y = y; width = w; height = h; }
    public boolean contains(int px, int py) { return px >= x && py >= y && px < x + width && py < y + height; }
    public boolean contains(double px, double py) { return px >= x && py >= y && px < x + width && py < y + height; }
    public boolean intersects(Rectangle r) { return r.x < x + width && r.x + r.width > x && r.y < y + height && r.y + r.height > y; }
    public android.graphics.Path toPath() { android.graphics.Path p = new android.graphics.Path(); p.addRect(x, y, x + width, y + height, android.graphics.Path.Direction.CW); return p; }
}
