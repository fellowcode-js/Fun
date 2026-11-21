package sov.game;

import sov.core.Terrain;
import sov.render.Pix;
import sov.render.Sprites;

import sov.awt.*;
import sov.awt.geom.Path2D;
import sov.awt.image.BufferedImage;

/** Small UI icons, drawn in code. */
public final class Icons {
    private Icons() {}

    public static BufferedImage select, found, farm, lumber, mine, dock, tower, road, policy, diplo, gold, wood, stone, pop, sword,
            science, menu, flag, houses, speed0, speed1, speed2, speed3, speed4;

    private static BufferedImage sprite(int[] p, int w, int h) {
        Pix px = new Pix(w, h);
        System.arraycopy(p, 0, px.p, 0, w * h);
        return px.toImage();
    }

    private static BufferedImage canvas(int s, java.util.function.Consumer<Graphics2D> f) {
        BufferedImage im = new BufferedImage(s, s, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = im.createGraphics();
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        f.accept(g);
        g.dispose();
        return im;
    }

    static {
        select = canvas(32, g -> {
            Path2D p = new Path2D.Double();
            p.moveTo(8, 4);
            p.lineTo(8, 24);
            p.lineTo(13, 19);
            p.lineTo(17, 28);
            p.lineTo(20, 26.5);
            p.lineTo(16, 18);
            p.lineTo(23, 18);
            p.closePath();
            g.setColor(Color.WHITE);
            g.fill(p);
            g.setColor(new Color(0x22304f));
            g.setStroke(new BasicStroke(1.8f));
            g.draw(p);
        });
        found = new BufferedImage(32, 32, BufferedImage.TYPE_INT_ARGB);
        {
            Graphics2D g = found.createGraphics();
            g.drawImage(Sprites.CITY[3], 1, 0, 30, 32, null);
            g.setColor(new Color(0x40c060));
            g.fillOval(18, 18, 14, 14);
            g.setColor(Color.WHITE);
            g.setStroke(new BasicStroke(2.2f));
            g.drawLine(25, 21, 25, 29);
            g.drawLine(21, 25, 29, 25);
            g.dispose();
        }
        farm = sprite(Sprites.FARM[1], 16, 16);
        lumber = sprite(Sprites.LUMBER, 16, 16);
        mine = sprite(Sprites.MINE, 16, 16);
        dock = sprite(Sprites.DOCK[0], 16, 16);
        tower = sprite(Sprites.TOWER, 16, 16);
        road = canvas(32, g -> {
            g.setColor(new Color(0x5a8a40));
            g.fillRoundRect(2, 2, 28, 28, 6, 6);
            g.setColor(new Color(0x8a7244));
            g.setStroke(new BasicStroke(10f, BasicStroke.CAP_BUTT, BasicStroke.JOIN_ROUND));
            Path2D p = new Path2D.Double();
            p.moveTo(2, 24);
            p.curveTo(12, 24, 10, 8, 30, 8);
            g.draw(p);
            g.setColor(new Color(0xc4a874));
            g.setStroke(new BasicStroke(6f, BasicStroke.CAP_BUTT, BasicStroke.JOIN_ROUND));
            g.draw(p);
        });
        policy = canvas(32, g -> {
            Path2D p = new Path2D.Double();
            p.moveTo(4, 24);
            p.lineTo(2, 10);
            p.lineTo(10, 16);
            p.lineTo(16, 6);
            p.lineTo(22, 16);
            p.lineTo(30, 10);
            p.lineTo(28, 24);
            p.closePath();
            g.setColor(new Color(0xf5c842));
            g.fill(p);
            g.setColor(new Color(0x8a6a10));
            g.setStroke(new BasicStroke(1.6f));
            g.draw(p);
            g.setColor(new Color(0xd04040));
            g.fillOval(13, 15, 6, 6);
            g.setColor(new Color(0x8a6a10));
            g.fillRect(4, 24, 24, 3);
        });
        diplo = canvas(32, g -> {
            g.setColor(new Color(0x2f78b8));
            g.fillOval(3, 3, 26, 26);
            g.setColor(new Color(0x5fa844));
            g.fillOval(8, 7, 9, 8);
            g.fillOval(15, 16, 9, 9);
            g.fillOval(6, 18, 5, 5);
            g.setColor(new Color(255, 255, 255, 120));
            g.drawOval(3, 3, 26, 26);
            g.drawArc(10, 3, 12, 26, 0, 360);
            g.drawLine(3, 16, 29, 16);
        });
        gold = canvas(20, g -> {
            g.setColor(new Color(0xb8860b));
            g.fillOval(1, 1, 18, 18);
            g.setColor(new Color(0xffd23a));
            g.fillOval(2, 2, 16, 16);
            g.setColor(new Color(0xfff0a0));
            g.fillOval(4, 3, 8, 6);
            g.setColor(new Color(0xb8860b));
            g.setStroke(new BasicStroke(2f));
            g.drawLine(10, 6, 10, 14);
        });
        wood = canvas(20, g -> {
            g.setColor(new Color(0x6a4429));
            g.fillRoundRect(1, 5, 18, 10, 4, 4);
            g.setColor(new Color(0xb98a52));
            g.fillOval(1, 5, 8, 10);
            g.setColor(new Color(0xe0c08a));
            g.fillOval(3, 7, 4, 6);
        });
        stone = canvas(20, g -> {
            Path2D p = new Path2D.Double();
            p.moveTo(2, 15);
            p.lineTo(5, 6);
            p.lineTo(12, 3);
            p.lineTo(18, 9);
            p.lineTo(17, 16);
            p.closePath();
            g.setColor(new Color(0x8a8378));
            g.fill(p);
            g.setColor(new Color(0xc4beb2));
            g.fillPolygon(new int[]{5, 12, 9}, new int[]{6, 3, 10}, 3);
            g.setColor(new Color(0x3a3631));
            g.draw(p);
        });
        pop = canvas(20, g -> {
            g.setColor(new Color(0xe8c49a));
            g.fillOval(6, 1, 8, 8);
            g.setColor(new Color(0x6fa8d8));
            g.fillRoundRect(3, 10, 14, 9, 6, 6);
        });
        sword = canvas(20, g -> {
            g.setColor(new Color(0xd8dde4));
            g.setStroke(new BasicStroke(2.6f));
            g.drawLine(3, 17, 16, 4);
            g.drawLine(17, 17, 4, 4);
            g.setColor(new Color(0x8a5a2a));
            g.setStroke(new BasicStroke(2f));
            g.drawLine(2, 14, 7, 19);
            g.drawLine(18, 14, 13, 19);
        });
        science = canvas(20, g -> {
            Path2D p = new Path2D.Double();
            p.moveTo(7, 2);
            p.lineTo(13, 2);
            p.lineTo(13, 8);
            p.lineTo(18, 17);
            p.lineTo(2, 17);
            p.lineTo(7, 8);
            p.closePath();
            g.setColor(new Color(0x60e0a0));
            g.fill(p);
            g.setColor(new Color(0xe8f4ff));
            g.setStroke(new BasicStroke(1.6f));
            g.draw(p);
        });
        menu = canvas(20, g -> {
            g.setColor(Color.WHITE);
            for (int i = 0; i < 3; i++) g.fillRoundRect(3, 4 + i * 5, 14, 3, 2, 2);
        });
        flag = canvas(20, g -> {
            g.setColor(new Color(0x5a3b22));
            g.fillRect(4, 2, 2, 17);
            g.setColor(new Color(0xd94141));
            g.fillRect(6, 2, 11, 8);
        });
        houses = sprite(Sprites.HOUSE[1][0], 16, 16);
        speed0 = canvas(20, g -> {
            g.setColor(Color.WHITE);
            g.fillRect(5, 4, 4, 12);
            g.fillRect(11, 4, 4, 12);
        });
        speed1 = tri(1);
        speed2 = tri(2);
        speed3 = tri(3);
        speed4 = tri(4);
    }

    private static BufferedImage tri(int n) {
        return canvas(20, g -> {
            g.setColor(Color.WHITE);
            for (int i = 0; i < n; i++) {
                int x = 2 + i * (n == 4 ? 4 : n == 3 ? 5 : 7);
                g.fillPolygon(new int[]{x, x, x + (n == 4 ? 6 : 8)}, new int[]{4, 16, 10}, 3);
            }
        });
    }
}
