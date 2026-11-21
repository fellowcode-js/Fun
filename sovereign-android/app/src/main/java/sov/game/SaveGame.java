package sov.game;

import sov.core.*;
import sov.core.Nation.Relation;

import java.io.*;
import java.util.*;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

/** Saves only what can't be regenerated: seed, nations, cities and tile changes. */
public final class SaveGame {
    private SaveGame() {}

    private static final int MAGIC = 0x534F5631;
    private static final int VERSION = 1;

    public static File dir() {
        File d = new File(System.getProperty("user.home"), ".sovereign/saves");
        d.mkdirs();
        return d;
    }

    public static File slot(String name) {
        return new File(dir(), name + ".sav");
    }

    public static void save(World w, File f) throws IOException {
        try (DataOutputStream o = new DataOutputStream(new BufferedOutputStream(new GZIPOutputStream(new FileOutputStream(f))))) {
            o.writeInt(MAGIC);
            o.writeInt(VERSION);
            o.writeLong(w.seed);
            o.writeInt(w.size.ordinal());
            o.writeInt(w.turn);
            o.writeInt(w.nextNationId);
            o.writeInt(w.nextCityId);
            o.writeInt(w.nextArmyId);
            o.writeInt(w.playerNation);
            o.writeBoolean(w.gameOver);
            o.writeLong(System.currentTimeMillis());

            o.writeInt(w.nations.size());
            for (Nation n : w.nations.values()) {
                o.writeInt(n.id);
                o.writeUTF(n.name);
                o.writeUTF(n.gov);
                o.writeUTF(n.leader);
                o.writeInt(n.color);
                o.writeBoolean(n.player);
                o.writeBoolean(n.alive);
                o.writeDouble(n.aggression);
                o.writeDouble(n.expansion);
                o.writeDouble(n.builder);
                o.writeDouble(n.diplomat);
                o.writeDouble(n.trader);
                o.writeDouble(n.gold);
                o.writeDouble(n.wood);
                o.writeDouble(n.stone);
                o.writeDouble(n.science);
                o.writeInt(n.era);
                o.writeDouble(n.tax);
                o.writeDouble(n.military);
                o.writeDouble(n.sciencePolicy);
                o.writeInt(n.focus);
                o.writeDouble(n.soldiers);
                o.writeInt(n.founded);
                o.writeInt(n.startX);
                o.writeInt(n.startY);
                o.writeInt(n.roofStyle);
                o.writeInt(n.droughtUntil);
                o.writeInt(n.boomUntil);
                o.writeInt(n.lastCityTurn);
                o.writeBoolean(n.autoExpand);
            }
            ArrayList<Relation> rels = new ArrayList<>();
            for (Nation n : w.nations.values()) for (Relation r : n.rel.values()) if (r.a == n.id) rels.add(r);
            o.writeInt(rels.size());
            for (Relation r : rels) {
                o.writeInt(r.a);
                o.writeInt(r.b);
                o.writeDouble(r.opinion);
                o.writeInt(r.state);
                o.writeInt(r.since);
                o.writeInt(r.truceUntil);
            }
            o.writeInt(w.cities.size());
            for (City c : w.cities.values()) {
                o.writeInt(c.id);
                o.writeInt(c.nation);
                o.writeInt(c.x);
                o.writeInt(c.y);
                o.writeUTF(c.name);
                o.writeDouble(c.pop);
                o.writeBoolean(c.capital);
                o.writeDouble(c.food);
                o.writeDouble(c.happiness);
                o.writeDouble(c.buildPoints);
                o.writeDouble(c.garrison);
                o.writeInt(c.founded);
                o.writeInt(c.unrest);
                o.writeDouble(c.farmYield);
                o.writeDouble(c.lumberYield);
                o.writeInt(c.blds.size());
                for (int[] b : c.blds) {
                    o.writeInt(b[0]);
                    o.writeInt(b[1]);
                    o.writeInt(b[2]);
                }
            }
            // tile changes versus pristine generation
            ArrayList<int[]> diffs = new ArrayList<>();
            for (Chunk c : w.claimedChunks()) {
                Chunk p = w.pristine(c.cx, c.cy);
                for (int i = 0; i < Chunk.N; i++) {
                    if (c.feat[i] != p.feat[i] || c.aux[i] != p.aux[i])
                        diffs.add(new int[]{c.cx * 32 + (i & 31), c.cy * 32 + (i >> 5), c.feat[i] & 0xff, c.aux[i]});
                }
            }
            o.writeInt(diffs.size());
            for (int[] d : diffs) {
                o.writeInt(d[0]);
                o.writeInt(d[1]);
                o.writeByte(d[2]);
                o.writeByte(d[3]);
            }
            int armies = 0;
            for (Army a : w.armies) if (!a.dead) armies++;
            o.writeInt(armies);
            for (Army a : w.armies) {
                if (a.dead) continue;
                o.writeInt(a.id);
                o.writeInt(a.nation);
                o.writeInt(a.targetCity);
                o.writeDouble(a.x);
                o.writeDouble(a.y);
                o.writeDouble(a.strength);
                o.writeInt(a.startTurn);
            }
            int logN = Math.min(60, w.log.size());
            o.writeInt(logN);
            for (int i = w.log.size() - logN; i < w.log.size(); i++) {
                World.LogEntry e = w.log.get(i);
                o.writeInt(e.turn);
                o.writeInt(e.nation);
                o.writeUTF(e.text);
                o.writeBoolean(e.important);
            }
        }
    }

    public static final class Info {
        public String name;
        public long time;
        public int year;
        public WorldSize size;
        public String nation;
        public File file;
    }

    public static Info peek(File f) {
        try (DataInputStream in = new DataInputStream(new BufferedInputStream(new GZIPInputStream(new FileInputStream(f))))) {
            if (in.readInt() != MAGIC) return null;
            in.readInt();
            long seed = in.readLong();
            int size = in.readInt();
            int turn = in.readInt();
            in.readInt();
            in.readInt();
            in.readInt();
            int pn = in.readInt();
            in.readBoolean();
            long time = in.readLong();
            int nc = in.readInt();
            String pname = "";
            for (int i = 0; i < nc; i++) {
                int id = in.readInt();
                String name = in.readUTF();
                in.readUTF();
                in.readUTF();
                in.readInt();
                in.readBoolean();
                in.readBoolean();
                for (int k = 0; k < 9; k++) in.readDouble();
                in.readInt();
                for (int k = 0; k < 3; k++) in.readDouble();
                in.readInt();
                in.readDouble();
                for (int k = 0; k < 7; k++) in.readInt();
                in.readBoolean();
                if (id == pn) pname = name;
            }
            Info inf = new Info();
            inf.name = f.getName().replace(".sav", "");
            inf.time = time;
            inf.year = 1 + turn / 12;
            inf.size = WorldSize.values()[size];
            inf.nation = pname;
            inf.file = f;
            return inf;
        } catch (Exception e) {
            return null;
        }
    }

    public static World load(File f) throws IOException {
        try (DataInputStream in = new DataInputStream(new BufferedInputStream(new GZIPInputStream(new FileInputStream(f))))) {
            if (in.readInt() != MAGIC) throw new IOException("Not a Sovereign save");
            in.readInt();
            long seed = in.readLong();
            WorldSize size = WorldSize.values()[in.readInt()];
            World w = new World(seed, size);
            w.turn = in.readInt();
            w.nextNationId = in.readInt();
            int nextCity = in.readInt();
            w.nextArmyId = in.readInt();
            w.playerNation = in.readInt();
            w.gameOver = in.readBoolean();
            in.readLong();
            int nc = in.readInt();
            for (int i = 0; i < nc; i++) {
                Nation n = new Nation();
                n.id = in.readInt();
                n.name = in.readUTF();
                n.gov = in.readUTF();
                n.leader = in.readUTF();
                n.color = in.readInt();
                n.player = in.readBoolean();
                n.alive = in.readBoolean();
                n.aggression = in.readDouble();
                n.expansion = in.readDouble();
                n.builder = in.readDouble();
                n.diplomat = in.readDouble();
                n.trader = in.readDouble();
                n.gold = in.readDouble();
                n.wood = in.readDouble();
                n.stone = in.readDouble();
                n.science = in.readDouble();
                n.era = in.readInt();
                n.tax = in.readDouble();
                n.military = in.readDouble();
                n.sciencePolicy = in.readDouble();
                n.focus = in.readInt();
                n.soldiers = in.readDouble();
                n.founded = in.readInt();
                n.startX = in.readInt();
                n.startY = in.readInt();
                n.roofStyle = in.readInt();
                n.droughtUntil = in.readInt();
                n.boomUntil = in.readInt();
                n.lastCityTurn = in.readInt();
                n.autoExpand = in.readBoolean();
                w.nations.put(n.id, n);
            }
            int rc = in.readInt();
            for (int i = 0; i < rc; i++) {
                Relation r = new Relation(in.readInt(), in.readInt());
                r.opinion = in.readDouble();
                r.state = in.readInt();
                r.since = in.readInt();
                r.truceUntil = in.readInt();
                Nation a = w.nation(r.a), b = w.nation(r.b);
                if (a != null && b != null) {
                    a.rel.put(b.id, r);
                    b.rel.put(a.id, r);
                }
            }
            int cc = in.readInt();
            for (int i = 0; i < cc; i++) {
                City c = new City();
                c.id = in.readInt();
                c.nation = in.readInt();
                c.x = in.readInt();
                c.y = in.readInt();
                c.name = in.readUTF();
                c.pop = in.readDouble();
                c.capital = in.readBoolean();
                c.food = in.readDouble();
                c.happiness = in.readDouble();
                c.buildPoints = in.readDouble();
                c.garrison = in.readDouble();
                c.founded = in.readInt();
                c.unrest = in.readInt();
                c.farmYield = in.readDouble();
                c.lumberYield = in.readDouble();
                int bn = in.readInt();
                for (int k = 0; k < bn; k++) {
                    int[] b = {in.readInt(), in.readInt(), in.readInt()};
                    c.blds.add(b);
                    switch (b[2]) {
                        case Terrain.HOUSE: c.houses++; break;
                        case Terrain.FARM: c.farms++; break;
                        case Terrain.LUMBER: c.lumbers++; break;
                        case Terrain.MINE: c.mines++; break;
                        case Terrain.DOCK: c.docks++; break;
                        case Terrain.TOWER: c.towers++; break;
                        default: break;
                    }
                }
                c.updateLevel();
                w.registerCity(c);
            }
            w.nextCityId = Math.max(w.nextCityId, nextCity);
            int dn = in.readInt();
            for (int i = 0; i < dn; i++) {
                int x = in.readInt(), y = in.readInt();
                int ft = in.readByte() & 0xff, ax = in.readByte();
                w.setFeat(x, y, ft, ax);
            }
            int an = in.readInt();
            for (int i = 0; i < an; i++) {
                Army a = new Army();
                a.id = in.readInt();
                a.nation = in.readInt();
                a.targetCity = in.readInt();
                a.x = in.readDouble();
                a.y = in.readDouble();
                a.strength = in.readDouble();
                a.startTurn = in.readInt();
                w.armies.add(a);
            }
            int ln = in.readInt();
            for (int i = 0; i < ln; i++) {
                int t = in.readInt(), n = in.readInt();
                String s = in.readUTF();
                boolean imp = in.readBoolean();
                int old = w.turn;
                w.turn = t;
                w.log(s, n, imp);
                w.turn = old;
            }
            return w;
        }
    }
}
