package sov.sim;

import sov.core.*;
import sov.core.Nation.Relation;

import java.util.*;

import static sov.core.Terrain.*;

/** The living world: economy, growth, AI, diplomacy, war. One call to step() is one month. */
public final class Sim {
    public final World w;
    private final Random r;
    private final HashSet<String> usedNames = new HashSet<>();
    private final HashMap<Integer, ArrayList<City>> byNation = new HashMap<>();
    private final ArrayList<Nation> alive = new ArrayList<>();
    public final ArrayList<Offer> offers = new ArrayList<>();

    public static final class Offer {
        public final int from, to, type; // type: 0 peace, 1 alliance
        public final int expires;

        Offer(int from, int to, int type, int expires) {
            this.from = from;
            this.to = to;
            this.type = type;
            this.expires = expires;
        }
    }

    public Sim(World w) {
        this.w = w;
        this.r = w.rng;
        for (City c : w.cities.values()) usedNames.add(c.name);
        for (Nation n : w.nations.values()) usedNames.add(n.name);
        rebuildIndex();
    }

    // ================= costs =================
    public static double[] buildCost(int type) {
        switch (type) {
            case HOUSE: return new double[]{0, 4, 0};
            case FARM: return new double[]{0, 3, 0};
            case LUMBER: return new double[]{0, 4, 0};
            case MINE: return new double[]{0, 6, 2};
            case DOCK: return new double[]{0, 8, 0};
            case TOWER: return new double[]{5, 6, 10};
            case ROAD: return new double[]{0, 1, 0};
            default: return new double[]{0, 0, 0};
        }
    }

    public double[] foundCost(Nation n) {
        return new double[]{80 + 16 * n.cityCount, 55, 8};
    }

    private boolean afford(Nation n, double[] c) {
        return n.gold >= c[0] && n.wood >= c[1] && n.stone >= c[2];
    }

    private void pay(Nation n, double[] c) {
        n.gold -= c[0];
        n.wood -= c[1];
        n.stone -= c[2];
    }

    // ================= nations =================
    private String uniqueNationName() {
        for (int i = 0; i < 30; i++) {
            String s = Names.nation(r);
            if (usedNames.add(s)) return s;
        }
        return Names.nation(r) + "ia";
    }

    private String uniqueCityName() {
        for (int i = 0; i < 30; i++) {
            String s = Names.city(r);
            if (usedNames.add(s)) return s;
        }
        return Names.city(r) + " " + (1 + r.nextInt(99));
    }

    private int pickColor() {
        boolean[] used = new boolean[Names.COLORS.length];
        for (Nation n : w.nations.values()) {
            if (!n.alive) continue;
            for (int i = 0; i < Names.COLORS.length; i++) if (Names.COLORS[i] == n.color) used[i] = true;
        }
        ArrayList<Integer> free = new ArrayList<>();
        for (int i = 0; i < used.length; i++) if (!used[i]) free.add(Names.COLORS[i]);
        if (!free.isEmpty()) return free.get(r.nextInt(free.size()));
        float h = r.nextFloat();
        return hsv(h, 0.6 + r.nextDouble() * 0.3, 0.75 + r.nextDouble() * 0.2);
    }

    private static int hsv(double h, double s, double v) {
        double hh = (h - Math.floor(h)) * 6;
        int i = (int) hh;
        double f = hh - i, p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
        double rr, gg, bb;
        switch (i) {
            case 0: rr = v; gg = t; bb = p; break;
            case 1: rr = q; gg = v; bb = p; break;
            case 2: rr = p; gg = v; bb = t; break;
            case 3: rr = p; gg = q; bb = v; break;
            case 4: rr = t; gg = p; bb = v; break;
            default: rr = v; gg = p; bb = q; break;
        }
        return ((int) (rr * 255) << 16) | ((int) (gg * 255) << 8) | (int) (bb * 255);
    }

    private String pickGov(Nation n) {
        double[] wgt = new double[Names.GOVS.length];
        for (int i = 0; i < wgt.length; i++) wgt[i] = 0.4;
        wgt[0] += 1.0;
        wgt[1] += n.diplomat + n.trader;
        wgt[2] += n.aggression * 1.5;
        wgt[5] += n.aggression;
        wgt[6] += n.trader;
        wgt[4] += n.diplomat;
        double sum = 0;
        for (double v : wgt) sum += v;
        double x = r.nextDouble() * sum;
        for (int i = 0; i < wgt.length; i++) {
            x -= wgt[i];
            if (x <= 0) return Names.GOVS[i];
        }
        return "Kingdom";
    }

    public Nation newNation(boolean player, String name, String gov, int color, int era) {
        Nation n = new Nation();
        n.id = w.nextNationId++;
        n.player = player;
        n.aggression = r.nextDouble();
        n.expansion = 0.25 + r.nextDouble() * 0.75;
        n.builder = r.nextDouble();
        n.diplomat = r.nextDouble();
        n.trader = r.nextDouble();
        if (player) n.aggression = n.expansion = n.builder = n.diplomat = n.trader = 0.5;
        n.name = name != null ? name : uniqueNationName();
        if (name != null) usedNames.add(name);
        n.gov = gov != null ? gov : pickGov(n);
        n.leader = Names.person(r);
        n.color = color >= 0 ? color : pickColor();
        n.roofStyle = r.nextInt(6);
        n.era = era;
        n.science = Nation.ERA_COST[era];
        n.founded = w.turn;
        n.lastCityTurn = w.turn;
        n.military = player ? 0.25 : 0.15 + n.aggression * 0.3;
        n.sciencePolicy = player ? 0.4 : 0.25 + n.builder * 0.35;
        n.tax = 0.5;
        w.nations.put(n.id, n);
        for (Nation o : w.nations.values()) {
            if (o == n) continue;
            Relation rl = new Relation(n.id, o.id);
            rl.opinion = (r.nextDouble() - 0.5) * 30;
            n.rel.put(o.id, rl);
            o.rel.put(n.id, rl);
        }
        return n;
    }

    public City foundCityAt(Nation n, int x, int y, boolean capital, double pop) {
        City c = w.addCity(n, x, y, uniqueCityName(), capital);
        c.pop = pop;
        c.updateLevel();
        n.lastCityTurn = w.turn;
        w.fx(x, y, 2, n.color);
        return c;
    }

    /** Give a brand new city a handful of starting buildings, free of charge. */
    private void seed(City c, Nation n, int farms, int houses) {
        for (int i = 0; i < farms; i++) {
            int[] t = findTile(c, FARM);
            if (t != null) place(c, n, FARM, t[0], t[1], false);
        }
        for (int i = 0; i < houses; i++) {
            int[] t = findTile(c, HOUSE);
            if (t != null) place(c, n, HOUSE, t[0], t[1], false);
        }
    }

    /** Create the starting world. Returns the player nation (or null for a pure spectator world). */
    public Nation setupNewWorld(int startX, int startY, String playerName, String gov, int color, boolean withPlayer) {
        Nation player = null;
        ArrayList<int[]> sites = new ArrayList<>();
        if (withPlayer) {
            int[] s = findSiteNear(startX, startY, 40, 30);
            if (s == null) s = new int[]{startX, startY};
            player = newNation(true, playerName, gov, color, 0);
            City c = foundCityAt(player, s[0], s[1], true, 140);
            seed(c, player, 2, 4);
            player.startX = s[0];
            player.startY = s[1];
            w.playerNation = player.id;
            sites.add(s);
        }
        int want = w.size.startNations - (withPlayer ? 1 : 0);
        int attempts = 0;
        double minSep = w.bounded ? Math.max(35, w.N / (Math.sqrt(w.size.startNations) * 1.7)) : 110;
        while (want > 0 && attempts++ < 600) {
            int x, y;
            if (w.bounded) {
                x = (int) (w.N * (0.08 + 0.84 * r.nextDouble()));
                y = (int) (w.N * (0.08 + 0.84 * r.nextDouble()));
            } else {
                double ang = r.nextDouble() * Math.PI * 2, d = 120 + r.nextDouble() * 260;
                x = startX + (int) (Math.cos(ang) * d);
                y = startY + (int) (Math.sin(ang) * d);
            }
            boolean far = true;
            for (int[] s : sites) if (World.dist(s[0], s[1], x, y) < minSep) far = false;
            if (!far) continue;
            int[] s = findSiteNear(x, y, 14, 18);
            if (s == null) continue;
            for (int[] o : sites) if (World.dist(s[0], s[1], o[0], o[1]) < minSep * 0.8) far = false;
            if (!far) continue;
            Nation n = newNation(false, null, null, -1, 0);
            City c = foundCityAt(n, s[0], s[1], true, 110 + r.nextInt(60));
            seed(c, n, 2, 3);
            n.startX = s[0];
            n.startY = s[1];
            sites.add(s);
            want--;
        }
        rebuildIndex();
        return player;
    }

    // ================= site search =================
    /** Score a place for a city, or -1 if impossible. */
    public double siteScore(int x, int y, int nationId) {
        if (!w.inBounds(x, y)) return -1;
        byte t = w.terrainAt(x, y);
        if (!buildable(t) || t == ROCK || t == SNOW) return -1;
        int own = w.ownerAt(x, y);
        if (own != 0 && own != nationId) return -1;
        if (!w.citiesNear(x, y, 7).isEmpty()) return -1;
        double s = 0;
        int water = 0, rock = 0, trees = 0;
        for (int dy = -4; dy <= 4; dy += 2)
            for (int dx = -4; dx <= 4; dx += 2) {
                byte tt = w.terrainAt(x + dx, y + dy);
                s += fertility(tt);
                if (tt == RIVER || tt == SHALLOW) water++;
                if (tt == ROCK) rock++;
            }
        if (w.touchesSea(x, y) || w.isCoastalTile(x, y)) s += 2;
        if (water > 0) s += 1.2;
        if (rock > 0) s += 0.8;
        if (fertility(t) < 0.3) s -= 2;
        return s;
    }

    public int[] findSiteNear(int cx, int cy, int radius, int attempts) {
        double best = 3.0;
        int[] res = null;
        for (int i = 0; i < attempts; i++) {
            int x = cx + r.nextInt(radius * 2 + 1) - radius, y = cy + r.nextInt(radius * 2 + 1) - radius;
            double s = siteScore(x, y, 0);
            if (s > best) {
                best = s;
                res = new int[]{x, y};
            }
        }
        return res;
    }

    // ================= building =================
    private boolean natural(int f) {
        return f == TREE || f == PINE || f == PALM || f == CACTUS || f == ROCKS;
    }

    private boolean canBuildOn(int x, int y, City c, int type) {
        if (!w.inBounds(x, y)) return false;
        if (w.ownerCityAt(x, y) != c.id) return false;
        byte t = w.terrainAt(x, y);
        byte f = w.featAt(x, y);
        if (isBuilt(f)) return false;
        if (type == MINE) return t == ROCK && (f == NONE || f == ORE || f == ROCKS);
        if (!buildable(t) || t == ROCK || f == ORE) return false;
        if (type == DOCK) return w.touchesSea(x, y);
        if (type == FARM) return fertility(t) >= 0.2;
        return true;
    }

    private int[] findTile(City c, int type) {
        int R = Math.min(c.buildRadius(), c.claimRadius() - 1);
        if (type == TOWER) R = c.claimRadius() - 2;
        double best = -1e9;
        int bx = 0, by = 0;
        boolean found = false;
        for (int dy = -R; dy <= R; dy++)
            for (int dx = -R; dx <= R; dx++) {
                double d = Math.sqrt(dx * dx + dy * dy);
                if (d > R || d < 0.9) continue;
                int x = c.x + dx, y = c.y + dy;
                if (!canBuildOn(x, y, c, type)) continue;
                byte t = w.terrainAt(x, y);
                byte f = w.featAt(x, y);
                double s = 0;
                switch (type) {
                    case HOUSE: {
                        int adj = 0;
                        int[][] nb = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
                        for (int[] o : nb) {
                            int ff = w.featAt(x + o[0], y + o[1]);
                            if (ff == HOUSE || ff == ROAD || ff == CITY) adj++;
                        }
                        s = 10 - d + adj * 1.6;
                        if (natural(f)) s -= 2.5;
                        if (isWater(w.terrainAt(x + 1, y)) || isWater(w.terrainAt(x - 1, y))) s += 0.4;
                        break;
                    }
                    case FARM: {
                        double fert = fertility(t);
                        boolean wet = isWater(w.terrainAt(x + 1, y)) || isWater(w.terrainAt(x - 1, y)) || isWater(w.terrainAt(x, y + 1)) || isWater(w.terrainAt(x, y - 1));
                        int adjF = 0;
                        if (w.featAt(x + 1, y) == FARM) adjF++;
                        if (w.featAt(x - 1, y) == FARM) adjF++;
                        if (w.featAt(x, y + 1) == FARM) adjF++;
                        if (w.featAt(x, y - 1) == FARM) adjF++;
                        s = fert * 8 + (wet ? 2.5 : 0) + adjF * 1.2 - d * 0.5;
                        if (natural(f)) s -= 3;
                        break;
                    }
                    case LUMBER: {
                        int trees = 0;
                        for (int oy = -2; oy <= 2; oy++)
                            for (int ox = -2; ox <= 2; ox++) {
                                int ff = w.featAt(x + ox, y + oy);
                                if (ff == TREE || ff == PINE || ff == PALM) trees++;
                            }
                        s = trees * 0.8 - d * 0.25;
                        if (trees < 3) s -= 8;
                        break;
                    }
                    case MINE:
                        s = 5 - d * 0.2 + (f == ORE ? 6 : 0);
                        break;
                    case DOCK:
                        s = 5 - d * 0.3;
                        for (int[] b : c.blds) if (b[2] == DOCK && Math.abs(b[0] - x) + Math.abs(b[1] - y) < 4) s -= 6;
                        break;
                    case TOWER:
                        s = d * 0.9;
                        for (int[] b : c.blds) if (b[2] == TOWER && Math.abs(b[0] - x) + Math.abs(b[1] - y) < 6) s -= 8;
                        break;
                    default:
                        break;
                }
                s += r.nextDouble() * 1.5;
                if (s > best) {
                    best = s;
                    bx = x;
                    by = y;
                    found = true;
                }
            }
        if (!found) return null;
        if (type == LUMBER && best < -4) return null;
        return new int[]{bx, by};
    }

    private void place(City c, Nation n, int type, int x, int y, boolean clearBonus) {
        byte f = w.featAt(x, y);
        byte t = w.terrainAt(x, y);
        if (clearBonus && (f == TREE || f == PINE || f == PALM)) n.wood += 1.5;
        int aux = 0;
        switch (type) {
            case HOUSE:
                aux = (houseStyle(c) << 3) | (n.roofStyle % 6);
                c.houses++;
                break;
            case FARM:
                aux = (Noise.randInt(x, y, 5) >>> 4) % 3;
                c.farms++;
                boolean wet = isWater(w.terrainAt(x + 1, y)) || isWater(w.terrainAt(x - 1, y)) || isWater(w.terrainAt(x, y + 1)) || isWater(w.terrainAt(x, y - 1));
                c.farmYield += fertility(t) * (wet ? 1.25 : 1.0) * 0.85 + 0.1;
                break;
            case LUMBER:
                c.lumbers++;
                c.lumberYield += 1.0;
                break;
            case MINE:
                c.mines++;
                break;
            case DOCK:
                c.docks++;
                break;
            case TOWER:
                c.towers++;
                break;
            default:
                break;
        }
        w.setFeat(x, y, type, aux);
        c.blds.add(new int[]{x, y, type});
    }

    private int houseStyle(City c) {
        return c.level >= 4 ? 2 : c.level >= 3 ? 1 : 0;
    }

    private void upgradeHouses(City c, Nation n) {
        int style = houseStyle(c);
        for (int[] b : c.blds) {
            if (b[2] != HOUSE) continue;
            int cur = w.auxAt(b[0], b[1]) >> 3;
            if (cur < style && r.nextDouble() < 0.75) w.setFeat(b[0], b[1], HOUSE, (style << 3) | (w.auxAt(b[0], b[1]) & 7));
        }
    }

    /** Place something chosen by the AI. Returns false if nothing affordable/possible. */
    private boolean autoBuild(City c, Nation n) {
        double need = c.pop * 0.04;
        double ratio = c.food;
        double wFarm = ratio < 1.15 ? 7 : ratio < 1.5 ? 2.2 : 0.4;
        if (n.focus == 1) wFarm *= 1.8;
        double wHouse = c.pop > c.housingCap() * 0.75 ? 6 : 0.6;
        double wLumber = (n.wood < 120 ? 3.5 : n.wood < 400 ? 1.2 : 0.2) * (c.lumbers < 1 + c.level * 1.2 ? 1 : 0.1);
        double wMine = (n.stone < 60 ? 3 : n.stone < 300 ? 1.2 : 0.3) * (c.mines < c.level ? 1 : 0.05);
        double wDock = c.coastal && c.docks < c.level ? 1.2 + n.trader * 2 : 0;
        double wTower = (c.towers < c.level / 2 + (n.neighbors.isEmpty() ? 0 : 1)) ? 0.25 + n.aggression * 0.6 + warCount(n) * 0.8 : 0;
        if (n.focus == 2) {
            wLumber *= 1.4;
            wMine *= 1.5;
        }
        if (n.focus == 3) wDock *= 2;
        double[] wt = {wFarm, wHouse, wLumber, wMine, wDock, wTower};
        int[] types = {FARM, HOUSE, LUMBER, MINE, DOCK, TOWER};
        for (int attempt = 0; attempt < 3; attempt++) {
            double sum = 0;
            for (double v : wt) sum += v;
            if (sum <= 0) return false;
            double x = r.nextDouble() * sum;
            int pick = 0;
            for (int i = 0; i < wt.length; i++) {
                x -= wt[i];
                if (x <= 0) {
                    pick = i;
                    break;
                }
            }
            int type = types[pick];
            double[] cost = buildCost(type);
            if (!afford(n, cost)) {
                wt[pick] = 0;
                continue;
            }
            int[] t = findTile(c, type);
            if (t == null) {
                wt[pick] = 0;
                continue;
            }
            pay(n, cost);
            place(c, n, type, t[0], t[1], true);
            return true;
        }
        return false;
    }

    /** Spend gold on mercenaries (2 gold each). */
    public String recruit(Nation n, double gold) {
        if (n.gold < gold) return "Not enough gold";
        n.gold -= gold;
        n.soldiers += gold / 2.0;
        return null;
    }

    /** Spend gold on research (2 gold per science point). */
    public String fundScience(Nation n, double gold) {
        if (n.gold < gold) return "Not enough gold";
        n.gold -= gold;
        n.science += gold / 2.0;
        return null;
    }

    // ---- player-driven construction ----
    /** Dry run of a build order: returns an error message, or null if it would succeed. */
    public String checkBuild(Nation n, int type, int x, int y) {
        if (!w.inBounds(x, y)) return "Out of bounds";
        int oc = w.ownerCityAt(x, y);
        City c = w.cities.get(oc);
        if (c == null || c.nation != n.id) return "Build inside your own borders";
        if (type == ROAD) {
            byte t = w.terrainAt(x, y);
            if (isWater(t) && t != RIVER) return "Can't build a road on open water";
            if (t == PEAK) return "Too steep for a road";
            byte f = w.featAt(x, y);
            if (isBuilt(f) && f != ROAD) return "Tile is occupied";
            if (!afford(n, buildCost(ROAD))) return "Not enough wood";
            return null;
        }
        if (!canBuildOn(x, y, c, type)) {
            switch (type) {
                case MINE: return "Mines need a mountain tile";
                case DOCK: return "Docks must touch the sea";
                case FARM: return "Farms need fertile land";
                default: return "Can't build here";
            }
        }
        if (!afford(n, buildCost(type))) return "Not enough resources";
        return null;
    }

    public String tryBuild(Nation n, int type, int x, int y) {
        String err = checkBuild(n, type, x, y);
        if (err != null) return err;
        int oc = w.ownerCityAt(x, y);
        City c = w.cities.get(oc);
        pay(n, buildCost(type));
        if (type == ROAD) {
            byte t = w.terrainAt(x, y);
            w.setFeat(x, y, t == RIVER ? BRIDGE : ROAD, 0);
        } else {
            place(c, n, type, x, y, true);
        }
        return null;
    }

    public String tryFoundCity(Nation n, int x, int y) {
        double[] cost = foundCost(n);
        double s = siteScore(x, y, n.id);
        if (s < 0) {
            byte t = w.terrainAt(x, y);
            if (!buildable(t) || t == ROCK) return "Can't settle on " + Terrain.name(t).toLowerCase();
            int own = w.ownerAt(x, y);
            if (own != 0 && own != n.id) return "That land belongs to another nation";
            return "Too close to another city";
        }
        if (!afford(n, cost)) return String.format("Need %d gold, %d wood, %d stone", (int) cost[0], (int) cost[1], (int) cost[2]);
        City src = null;
        double bd = 1e9;
        for (City c : byNation.getOrDefault(n.id, new ArrayList<>())) {
            double d = World.dist(c.x, c.y, x, y);
            if (d < bd) {
                bd = d;
                src = c;
            }
        }
        if (src == null) return "You have no cities";
        if (bd > 34) return "Too far from your nearest city (max 34 tiles)";
        pay(n, cost);
        src.pop = Math.max(20, src.pop - 40);
        City c = foundCityAt(n, x, y, false, 45);
        seed(c, n, 1, 2);
        connect(n, src, c);
        n.cityCount++;
        byNation.computeIfAbsent(n.id, k -> new ArrayList<>()).add(c);
        w.log(n.name + " founded " + c.name + ".", n.id, n.player);
        return null;
    }

    // ================= roads =================
    private double roadCost(int x, int y) {
        byte t = w.terrainAt(x, y);
        if (t == DEEP || t == SHALLOW || t == PEAK) return -1;
        byte f = w.featAt(x, y);
        if (f == ROAD || f == BRIDGE) return 0.35;
        if (f == CITY) return 0.5;
        if (f == HOUSE) return 5;
        if (f == FARM) return 3.5;
        if (isBuilt(f)) return -1;
        double c;
        switch (t) {
            case RIVER: c = 3.5; break;
            case ROCK: c = 5; break;
            case SWAMP: c = 2.2; break;
            case SNOW: c = 2; break;
            case JUNGLE: c = 1.6; break;
            default: c = 1;
        }
        if (f == TREE || f == PINE || f == PALM) c += 0.8;
        if (f == ORE) c += 2;
        return c;
    }

    private static final class Node {
        int x, y;
        double g, f;
        Node parent;
    }

    private ArrayList<int[]> findPath(int x0, int y0, int x1, int y1, int maxNodes) {
        PriorityQueue<Node> open = new PriorityQueue<>((a, b) -> Double.compare(a.f, b.f));
        HashMap<Long, Node> seen = new HashMap<>();
        Node s = new Node();
        s.x = x0;
        s.y = y0;
        s.f = Math.abs(x1 - x0) + Math.abs(y1 - y0);
        open.add(s);
        seen.put(Chunk.key(x0, y0), s);
        int[][] dirs = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
        int expanded = 0;
        HashSet<Long> closed = new HashSet<>();
        while (!open.isEmpty() && expanded < maxNodes) {
            Node cur = open.poll();
            long ck = Chunk.key(cur.x, cur.y);
            if (!closed.add(ck)) continue;
            expanded++;
            if (Math.abs(cur.x - x1) + Math.abs(cur.y - y1) <= 1) {
                ArrayList<int[]> path = new ArrayList<>();
                for (Node p = cur; p != null; p = p.parent) path.add(new int[]{p.x, p.y});
                Collections.reverse(path);
                return path;
            }
            for (int[] d : dirs) {
                int nx = cur.x + d[0], ny = cur.y + d[1];
                double c = roadCost(nx, ny);
                if (c < 0) continue;
                long k = Chunk.key(nx, ny);
                if (closed.contains(k)) continue;
                double g = cur.g + c;
                Node ex = seen.get(k);
                if (ex != null && ex.g <= g) continue;
                Node nn = ex != null ? ex : new Node();
                nn.x = nx;
                nn.y = ny;
                nn.g = g;
                nn.f = g + (Math.abs(x1 - nx) + Math.abs(y1 - ny)) * 1.05;
                nn.parent = cur;
                seen.put(k, nn);
                open.add(nn);
            }
        }
        return null;
    }

    private void connect(Nation n, City a, City b) {
        ArrayList<int[]> p = findPath(a.x, a.y, b.x, b.y, 2600);
        if (p == null) return;
        for (int[] t : p) {
            if ((t[0] == a.x && t[1] == a.y) || (t[0] == b.x && t[1] == b.y)) continue;
            n.roadQueue.add(t);
        }
    }

    /** A road replaces a house or field: take it off its city's books. */
    private void demolish(int x, int y, int f) {
        City c = w.cities.get(w.ownerCityAt(x, y));
        if (c == null) return;
        for (java.util.Iterator<int[]> it = c.blds.iterator(); it.hasNext(); ) {
            int[] b = it.next();
            if (b[0] == x && b[1] == y) {
                it.remove();
                if (f == HOUSE) c.houses = Math.max(0, c.houses - 1);
                else {
                    c.farms = Math.max(0, c.farms - 1);
                    c.farmYield = Math.max(0, c.farmYield - 0.8);
                }
                return;
            }
        }
    }

    private void buildRoads(Nation n) {
        for (int i = 0; i < 3 && !n.roadQueue.isEmpty(); i++) {
            int[] t = n.roadQueue.peek();
            if (n.wood < 0.4) return;
            n.roadQueue.poll();
            byte f = w.featAt(t[0], t[1]);
            byte ter = w.terrainAt(t[0], t[1]);
            if (ter == DEEP || ter == SHALLOW) continue;
            if (isBuilt(f) && f != ROAD && f != BRIDGE && f != HOUSE && f != FARM) continue;
            if (f == ROAD || f == BRIDGE || f == CITY) continue;
            if (f == HOUSE || f == FARM) demolish(t[0], t[1], f);
            n.wood -= 0.4;
            w.setFeat(t[0], t[1], ter == RIVER ? BRIDGE : ROAD, 0);
        }
    }

    // ================= relations =================
    public Relation rel(Nation a, Nation b) {
        Relation rl = a.rel.get(b.id);
        if (rl == null) {
            rl = new Relation(a.id, b.id);
            a.rel.put(b.id, rl);
            b.rel.put(a.id, rl);
        }
        return rl;
    }

    public int warCount(Nation n) {
        int c = 0;
        for (Relation rl : n.rel.values()) if (rl.state == Relation.WAR) {
            Nation o = w.nation(rl.a == n.id ? rl.b : rl.a);
            if (o != null && o.alive) c++;
        }
        return c;
    }

    public boolean atWar(Nation a, Nation b) {
        return rel(a, b).state == Relation.WAR;
    }

    public String declareWar(Nation a, Nation b) {
        if (a == b || !b.alive) return "Invalid target";
        Relation rl = rel(a, b);
        if (rl.state == Relation.WAR) return "Already at war";
        if (rl.state == Relation.ALLY) rl.state = Relation.PEACE;
        rl.state = Relation.WAR;
        rl.since = w.turn;
        rl.opinion = Math.min(rl.opinion, -40);
        w.log(a.name + " declared war on " + b.name + "!", a.player || b.player ? (a.player ? a.id : b.id) : a.id, true);
        // allies are dragged in
        for (Relation o : new ArrayList<>(b.rel.values())) {
            if (o.state != Relation.ALLY) continue;
            Nation ally = w.nation(o.a == b.id ? o.b : o.a);
            if (ally == null || !ally.alive || ally == a || ally.player) continue;
            if (rel(ally, a).state == Relation.ALLY) continue;
            if (r.nextDouble() < 0.7) declareWar(ally, a);
        }
        for (Relation o : new ArrayList<>(a.rel.values())) {
            if (o.state != Relation.ALLY) continue;
            Nation ally = w.nation(o.a == a.id ? o.b : o.a);
            if (ally == null || !ally.alive || ally == b || ally.player) continue;
            if (rel(ally, b).state == Relation.ALLY) continue;
            if (r.nextDouble() < 0.5) declareWar(ally, b);
        }
        return null;
    }

    public void makePeace(Nation a, Nation b) {
        Relation rl = rel(a, b);
        if (rl.state != Relation.WAR) return;
        rl.state = Relation.PEACE;
        rl.truceUntil = w.turn + 36;
        rl.opinion = Math.max(rl.opinion, -10);
        for (Army ar : w.armies) {
            if (ar.dead) continue;
            City t = w.cities.get(ar.targetCity);
            if (t == null) continue;
            if ((ar.nation == a.id && t.nation == b.id) || (ar.nation == b.id && t.nation == a.id)) recall(ar);
        }
        w.log(a.name + " and " + b.name + " signed a peace treaty.", a.player ? a.id : b.id, true);
    }

    private void recall(Army ar) {
        ar.dead = true;
        Nation n = w.nation(ar.nation);
        if (n != null) n.soldiers += ar.strength;
    }

    /** Player proposes peace. */
    public String proposePeace(Nation a, Nation b) {
        Relation rl = rel(a, b);
        if (rl.state != Relation.WAR) return "You are not at war";
        int dur = w.turn - rl.since;
        double want = (b.power > a.power * 1.5 ? -0.4 : 0.3) + dur / 36.0 + b.diplomat * 0.5 - b.aggression * 0.5;
        if (want > 0.45 || dur > 60) {
            makePeace(a, b);
            return null;
        }
        return b.name + " refuses to make peace yet";
    }

    public String proposeAlliance(Nation a, Nation b) {
        Relation rl = rel(a, b);
        if (rl.state == Relation.WAR) return "Can't ally while at war";
        if (rl.state == Relation.ALLY) return "Already allies";
        if (rl.opinion > 30 + (1 - b.diplomat) * 15) {
            rl.state = Relation.ALLY;
            w.log(a.name + " and " + b.name + " formed an alliance.", a.player ? a.id : b.id, true);
            return null;
        }
        return b.name + " doesn't trust you enough";
    }

    public String giftGold(Nation a, Nation b, double amt) {
        if (a.gold < amt) return "Not enough gold";
        a.gold -= amt;
        b.gold += amt;
        rel(a, b).opinion = Math.min(100, rel(a, b).opinion + amt / 6);
        return null;
    }

    public String breakAlliance(Nation a, Nation b) {
        Relation rl = rel(a, b);
        if (rl.state != Relation.ALLY) return "Not allied";
        rl.state = Relation.PEACE;
        rl.opinion -= 25;
        return null;
    }

    // ================= armies =================
    private boolean pathClear(double x0, double y0, double x1, double y1) {
        double d = World.dist(x0, y0, x1, y1);
        int steps = (int) Math.ceil(d);
        for (int i = 0; i <= steps; i += 1) {
            double t = steps == 0 ? 0 : i / (double) steps;
            int x = (int) Math.floor(x0 + (x1 - x0) * t), y = (int) Math.floor(y0 + (y1 - y0) * t);
            if (w.terrainAt(x, y) == DEEP) return false;
        }
        return true;
    }

    public double cityDefense(City c) {
        Nation d = w.nation(c.nation);
        double cities = Math.max(1, d == null ? 1 : d.cityCount);
        double def = c.garrison + c.pop * 0.035 + c.towers * 28 + (d != null ? d.soldiers / cities * 0.6 : 0);
        if (c.capital) def *= 1.25;
        def *= d != null ? d.warMult() : 1;
        return def;
    }

    public String sendArmy(Nation n, City target, double fraction) {
        Nation d = w.nation(target.nation);
        if (d == null || !atWar(n, d)) return "You are not at war with that nation";
        double str = n.soldiers * fraction;
        if (str < 20) return "Not enough soldiers available (raise military spending)";
        City from = null;
        double bd = 1e9;
        for (City c : byNation.getOrDefault(n.id, new ArrayList<>())) {
            double dist = World.dist(c.x, c.y, target.x, target.y);
            if (dist < bd && pathClear(c.x, c.y, target.x, target.y)) {
                bd = dist;
                from = c;
            }
        }
        if (from == null) return "No overland route (deep water in the way)";
        if (bd > 120) return "Target is too far away";
        launch(n, from, target, str);
        return null;
    }

    private void launch(Nation n, City from, City target, double str) {
        n.soldiers -= str;
        Army a = new Army();
        a.id = w.nextArmyId++;
        a.nation = n.id;
        a.x = from.x;
        a.y = from.y;
        a.fromX = from.x;
        a.fromY = from.y;
        a.strength = str;
        a.targetCity = target.id;
        a.startTurn = w.turn;
        w.armies.add(a);
    }

    private void moveArmies() {
        for (Army a : w.armies) {
            if (a.dead) continue;
            Nation n = w.nation(a.nation);
            City t = w.cities.get(a.targetCity);
            if (n == null || !n.alive) {
                a.dead = true;
                continue;
            }
            if (t == null) {
                recall(a);
                continue;
            }
            Nation d = w.nation(t.nation);
            if (d == null || !atWar(n, d)) {
                recall(a);
                continue;
            }
            double dx = t.x - a.x, dy = t.y - a.y;
            double dist = Math.sqrt(dx * dx + dy * dy);
            double speed = 1.5 + n.era * 0.15;
            if (dist <= 1.3) {
                battle(a, t, n, d);
                continue;
            }
            double nx = a.x + dx / dist * speed, ny = a.y + dy / dist * speed;
            if (dist < speed) {
                nx = t.x;
                ny = t.y;
            }
            if (w.terrainAt((int) Math.floor(nx), (int) Math.floor(ny)) == DEEP) {
                // try sliding along the coast
                double px = -dy / dist, py = dx / dist;
                boolean moved = false;
                for (int sgn = -1; sgn <= 1 && !moved; sgn += 2) {
                    double sx2 = a.x + px * sgn * speed, sy2 = a.y + py * sgn * speed;
                    if (w.terrainAt((int) Math.floor(sx2), (int) Math.floor(sy2)) != DEEP) {
                        a.x = sx2;
                        a.y = sy2;
                        moved = true;
                    }
                }
                if (!moved && ++a.stuck > 6) recall(a);
                else if (!moved) a.stuck++;
            } else {
                a.x = nx;
                a.y = ny;
            }
            if (w.turn - a.startTurn > 200) recall(a);
        }
        w.armies.removeIf(a -> a.dead);
    }

    private void battle(Army a, City t, Nation att, Nation def) {
        w.fx(t.x, t.y, 0, att.color);
        double atk = a.strength * att.warMult() * (0.85 + r.nextDouble() * 0.3);
        double dfn = cityDefense(t) * (0.85 + r.nextDouble() * 0.3);
        a.dead = true;
        if (atk > dfn) {
            double lost = Math.max(a.strength * 0.12, dfn / att.warMult() * 0.55);
            double survivors = Math.max(5, a.strength - lost);
            def.soldiers *= 0.85;
            capture(t, att, def, survivors);
        } else {
            double ratio = atk / Math.max(1, dfn);
            att.soldiers += a.strength * 0.1;
            def.soldiers = Math.max(0, def.soldiers - atk / def.warMult() * 0.25);
            t.garrison = Math.max(0, t.garrison - atk * 0.3);
            t.pop = Math.max(20, t.pop * 0.97);
            if (att.player || def.player) w.log(att.name + "'s assault on " + t.name + " was repelled.", att.player ? att.id : def.id, false);
        }
    }

    private void capture(City t, Nation att, Nation def, double survivors) {
        boolean wasCapital = t.capital;
        t.capital = false;
        w.transferCity(t, att);
        t.pop = Math.max(25, t.pop * 0.72);
        t.happiness = 30;
        t.unrest = 0;
        t.garrison = survivors * 0.5;
        att.soldiers += survivors * 0.5;
        w.fx(t.x, t.y, 1, att.color);
        w.log(att.name + " captured " + t.name + " from " + def.name + "!", att.player || !def.player ? att.id : def.id, true);
        ArrayList<City> rest = byNation.get(def.id);
        if (rest != null) rest.remove(t);
        def.cityCount--;
        att.cityCount++;
        byNation.computeIfAbsent(att.id, k -> new ArrayList<>()).add(t);
        if (def.cityCount <= 0 || rest == null || rest.isEmpty()) {
            destroyNation(def, att);
        } else if (wasCapital) {
            City best = null;
            for (City c : rest) if (best == null || c.pop > best.pop) best = c;
            if (best != null) {
                best.capital = true;
                w.reclaim(best);
                w.log(def.name + " moved its capital to " + best.name + ".", def.id, false);
            }
        }
        t.updateLevel();
        w.reclaim(t);
    }

    public void destroyNation(Nation n, Nation by) {
        if (!n.alive) return;
        n.alive = false;
        for (Army a : w.armies) if (a.nation == n.id) a.dead = true;
        for (Relation rl : n.rel.values()) rl.state = Relation.PEACE;
        w.log("The " + n.fullName() + " has fallen" + (by != null ? " to " + by.name : "") + ".", n.id, true);
        if (n.player) {
            w.gameOver = true;
        }
    }

    // ================= events =================
    private void rebel(City c, Nation parent) {
        Nation nn = newNation(false, null, "Republic", -1, Math.max(0, parent.era - (r.nextBoolean() ? 1 : 0)));
        nn.gold = 60;
        nn.wood = 60;
        nn.stone = 15;
        nn.soldiers = c.pop * 0.06;
        c.capital = true;
        w.transferCity(c, nn);
        c.happiness = 55;
        c.unrest = 0;
        byNation.computeIfAbsent(nn.id, k -> new ArrayList<>()).add(c);
        ArrayList<City> pl = byNation.get(parent.id);
        if (pl != null) pl.remove(c);
        parent.cityCount--;
        nn.cityCount = 1;
        Relation rl = rel(nn, parent);
        rl.state = Relation.WAR;
        rl.since = w.turn;
        rl.opinion = -60;
        w.fx(c.x, c.y, 1, nn.color);
        w.log(c.name + " rose in revolt against " + parent.name + " and became the " + nn.fullName() + "!", parent.id, true);
        w.reclaim(c);
    }

    private void events(ArrayList<City> all) {
        if (all.isEmpty()) return;
        // plague
        if (r.nextDouble() < 0.12) {
            City c = all.get(r.nextInt(all.size()));
            if (c.pop > 300 && r.nextDouble() < 0.12) {
                c.pop *= 0.68;
                Nation n = w.nation(c.nation);
                w.fx(c.x, c.y, 3, 0);
                if (n != null && (n.player || c.pop > 800)) w.log("A plague struck " + c.name + ".", n.id, n.player);
            }
        }
        for (Nation n : alive) {
            if (r.nextDouble() < 0.0016 && n.droughtUntil < w.turn) {
                n.droughtUntil = w.turn + 10;
                if (n.player) w.log("Drought: harvests fail in " + n.name + " for the next months.", n.id, true);
            }
            if (r.nextDouble() < 0.0016 && n.boomUntil < w.turn) {
                n.boomUntil = w.turn + 14;
                if (n.player) w.log("A golden age begins in " + n.name + "!", n.id, true);
            }
        }
    }

    private void spawnFrontier() {
        int target;
        if (w.bounded) target = Math.max(w.size.startNations, (int) (w.size.startNations * (1 + w.year() / 40.0)));
        else target = Math.min(70, w.size.startNations + w.year() / 5);
        if (alive.size() >= target || w.cities.isEmpty()) return;
        ArrayList<City> all = new ArrayList<>(w.cities.values());
        for (int tries = 0; tries < 12; tries++) {
            City o = all.get(r.nextInt(all.size()));
            double ang = r.nextDouble() * Math.PI * 2, d = 55 + r.nextDouble() * 150;
            int x = o.x + (int) (Math.cos(ang) * d), y = o.y + (int) (Math.sin(ang) * d);
            if (w.bounded && (x < 6 || y < 6 || x >= w.N - 6 || y >= w.N - 6)) continue;
            double md = 1e9;
            for (City c : w.citiesNear(x, y, 60)) md = Math.min(md, World.dist(c.x, c.y, x, y));
            if (md < 50) continue;
            int[] s = findSiteNear(x, y, 12, 16);
            if (s == null) continue;
            int era = 0;
            for (Nation n : alive) era = Math.max(era, n.era);
            Nation nn = newNation(false, null, null, -1, Math.max(0, era - 2));
            City c = foundCityAt(nn, s[0], s[1], true, 90);
            seed(c, nn, 2, 3);
            nn.cityCount = 1;
            byNation.computeIfAbsent(nn.id, k -> new ArrayList<>()).add(c);
            alive.add(nn);
            w.log("A new people has appeared: the " + nn.fullName() + ".", nn.id, false);
            return;
        }
    }

    // ================= AI =================
    private void refreshNeighbors(Nation n, ArrayList<City> cs) {
        n.neighbors.clear();
        for (City c : cs) {
            for (City o : w.citiesNear(c.x, c.y, 55)) if (o.nation != n.id) n.neighbors.add(o.nation);
        }
    }

    private void aiThink(Nation n, ArrayList<City> cs) {
        int wars = warCount(n);
        // policies
        n.military += ((wars > 0 ? 0.55 : 0.15 + n.aggression * 0.3) - n.military) * 0.3;
        n.tax += ((n.gold < 60 ? 0.7 : n.gold > 600 ? 0.35 : 0.5) - n.tax) * 0.3;
        n.sciencePolicy += ((0.25 + n.builder * 0.35) - n.sciencePolicy) * 0.3;
        double foodSum = 0;
        for (City c : cs) foodSum += c.food;
        double avgFood = foodSum / Math.max(1, cs.size());
        n.focus = avgFood < 1.1 ? 1 : n.wood < 100 || n.stone < 40 ? 2 : n.trader > 0.65 ? 3 : 0;

        tryExpand(n, cs);
        if (n.gold > 1500) {
            double spend = n.gold * 0.25;
            if (wars > 0 || n.aggression > 0.55) recruit(n, spend * 0.5);
            fundScience(n, spend * 0.5);
        }
        aiDiplomacy(n, cs, wars);
        if (wars > 0) aiWar(n, cs);
    }

    private void tryExpand(Nation n, ArrayList<City> cs) {
        if (cs.isEmpty()) return;
        if (w.turn - n.lastCityTurn < 10 + (int) (26 * (1 - n.expansion))) return;
        double[] cost = foundCost(n);
        if (!afford(n, cost)) return;
        City src = null;
        for (int i = 0; i < 4; i++) {
            City c = cs.get(r.nextInt(cs.size()));
            if (c.pop >= 160 && (src == null || c.pop > src.pop)) src = c;
        }
        if (src == null) return;
        double best = 4.0;
        int[] res = null;
        for (int i = 0; i < 22; i++) {
            double ang = r.nextDouble() * Math.PI * 2, d = 9 + r.nextDouble() * 12;
            int x = src.x + (int) (Math.cos(ang) * d), y = src.y + (int) (Math.sin(ang) * d);
            double s = siteScore(x, y, n.id);
            if (s > best) {
                best = s;
                res = new int[]{x, y};
            }
        }
        if (res == null) return;
        pay(n, cost);
        src.pop = Math.max(20, src.pop - 40);
        City c = foundCityAt(n, res[0], res[1], false, 45);
        seed(c, n, 1, 2);
        connect(n, src, c);
        n.cityCount++;
        byNation.computeIfAbsent(n.id, k -> new ArrayList<>()).add(c);
        cs.add(c);
        if (n.player) w.log(n.name + " founded " + c.name + ".", n.id, false);
    }

    private void aiDiplomacy(Nation n, ArrayList<City> cs, int wars) {
        for (int oid : new ArrayList<>(n.neighbors)) {
            Nation o = w.nation(oid);
            if (o == null || !o.alive) continue;
            Relation rl = rel(n, o);
            if (rl.state == Relation.PEACE && w.turn >= rl.truceUntil) {
                // war declaration
                double ratio = (n.power + 1) / (o.power + 1);
                double desire = n.aggression * 0.045 * (rl.opinion < -10 ? 1.8 : 0.5) * (ratio > 1.15 ? 1.4 : ratio > 0.85 ? 0.5 : 0.05);
                if (wars >= 2) desire *= 0.2;
                if (o.player && w.turn < 36) desire = 0;
                if (n.soldiers < 25) desire = 0;
                if (r.nextDouble() < desire) {
                    declareWar(n, o);
                    wars++;
                } else if (rl.opinion > 38 && r.nextDouble() < 0.03 + n.diplomat * 0.05) {
                    if (o.player) {
                        if (offers.stream().noneMatch(of -> of.from == n.id && of.type == 1))
                            offers.add(new Offer(n.id, o.id, 1, w.turn + 14));
                        w.log(n.name + " proposes an alliance.", o.id, true);
                    } else {
                        rl.state = Relation.ALLY;
                        w.log(n.name + " and " + o.name + " formed an alliance.", n.id, false);
                    }
                }
            } else if (rl.state == Relation.WAR) {
                int dur = w.turn - rl.since;
                double chance = 0.01 + dur / 36.0 * 0.02 + (n.power < o.power * 0.7 ? 0.05 : 0) + n.diplomat * 0.01;
                if (r.nextDouble() < chance) {
                    if (o.player) {
                        if (offers.stream().noneMatch(of -> of.from == n.id && of.type == 0)) {
                            offers.add(new Offer(n.id, o.id, 0, w.turn + 14));
                            w.log(n.name + " proposes peace.", o.id, true);
                        }
                    } else if (r.nextDouble() < 0.5 + o.diplomat * 0.3) makePeace(n, o);
                }
            }
        }
    }

    private void aiWar(Nation n, ArrayList<City> cs) {
        if (n.soldiers < 45) return;
        int active = 0;
        for (Army a : w.armies) if (a.nation == n.id && !a.dead) active++;
        if (active >= 1 + cs.size() / 3) return;
        City bestT = null, bestFrom = null;
        double bestScore = 1e9;
        for (City mine : cs) {
            for (City o : w.citiesNear(mine.x, mine.y, 75)) {
                if (o.nation == n.id) continue;
                Nation on = w.nation(o.nation);
                if (on == null || !atWar(n, on)) continue;
                double d = World.dist(mine.x, mine.y, o.x, o.y);
                double def = cityDefense(o);
                double score = d * 1.0 + def * 0.15 - (o.capital ? 10 : 0);
                if (n.soldiers * n.warMult() * 0.8 < def * 0.8) continue;
                if (score < bestScore && pathClear(mine.x, mine.y, o.x, o.y)) {
                    bestScore = score;
                    bestT = o;
                    bestFrom = mine;
                }
            }
        }
        if (bestT == null) return;
        double def = cityDefense(bestT);
        double str = Math.min(n.soldiers * 0.85, Math.max(def / n.warMult() * 1.5, n.soldiers * 0.5));
        if (str < 30) return;
        launch(n, bestFrom, bestT, str);
    }

    // ================= economy & turn =================
    private void rebuildIndex() {
        byNation.clear();
        alive.clear();
        for (Nation n : w.nations.values()) if (n.alive) alive.add(n);
        for (City c : w.cities.values()) byNation.computeIfAbsent(c.nation, k -> new ArrayList<>()).add(c);
        for (Nation n : alive) {
            ArrayList<City> cs = byNation.get(n.id);
            n.cityCount = cs == null ? 0 : cs.size();
            double pop = 0;
            if (cs != null) for (City c : cs) pop += c.pop;
            n.pop = pop;
        }
    }

    private void economy(Nation n, ArrayList<City> cs) {
        int wars = warCount(n);
        double gold = 0, wood = 0, stone = 0, sci = 0, bld = 0, food = 0;
        double techF = n.techMult() * (n.droughtUntil > w.turn ? 0.5 : 1) * (n.boomUntil > w.turn ? 1.25 : 1);
        for (City c : cs) {
            double foodProd = 3 + c.farmYield * 6.5 * techF * (n.focus == 1 ? 1.2 : 1);
            double need = c.pop * 0.04;
            double ratio = foodProd / Math.max(0.5, need);
            c.food = ratio;
            food += foodProd - need;
            double cap = c.housingCap();
            if (ratio >= 1) {
                double g = c.pop * 0.017 * Math.min(1.5, ratio) * Math.max(0, 1 - c.pop / cap);
                c.pop += g + (c.happiness > 55 ? 0.25 : 0);
            } else {
                c.pop -= c.pop * 0.025 * (1 - ratio);
            }
            if (c.pop > cap) c.pop -= (c.pop - cap) * 0.06;
            if (c.pop < 15) c.pop = 15;
            int old = c.level;
            c.updateLevel();
            if (c.level > old) {
                w.reclaim(c);
                upgradeHouses(c, n);
                w.fx(c.x, c.y, 2, n.color);
                if (n.player) w.log(c.name + " has grown into a " + c.levelName() + ".", n.id, c.level >= 4);
            }
            double target = 80 - (n.tax - 0.5) * 55 - (wars > 0 ? 8 : 0) + (c.capital ? 6 : 0) + (n.boomUntil > w.turn ? 8 : 0)
                    - (ratio < 1 ? 18 * (1 - ratio) + 6 : 0) - (c.pop > cap ? 8 : 0) - (n.gold <= 0 ? 10 : 0);
            c.happiness += (target - c.happiness) * 0.08;
            if (c.happiness < 22) c.unrest++;
            else c.unrest = Math.max(0, c.unrest - 1);
            if (c.unrest > 14 && !c.capital && cs.size() > 1 && r.nextDouble() < 0.08) {
                rebel(c, n);
                continue;
            }
            gold += c.pop * 0.012 * (0.4 + n.tax * 1.2) + c.docks * 2.5 * (1 + n.trader * 0.5) * (n.focus == 3 ? 1.3 : 1) + c.level * 0.4 + c.mines * 0.8;
            wood += c.lumbers * 3.6 * Math.min(1.4, c.lumberYield / Math.max(1, c.lumbers)) * techF * (n.focus == 2 ? 1.25 : 1) + 0.4;
            stone += c.mines * 2.6 * techF * (n.focus == 2 ? 1.25 : 1);
            sci += c.pop * 0.0035 * (n.sciencePolicy * 2);
            bld += c.blds.size() * 0.02 + c.towers * 0.2;
            // deforestation around lumber camps
            if (c.lumbers > 0 && r.nextDouble() < 0.06 * c.lumbers) clearTree(c);
        }
        double deployed = 0;
        for (Army a : w.armies) if (a.nation == n.id && !a.dead) deployed += a.strength;
        double totalTarget = n.pop * n.military * 0.1;
        n.soldiers += (Math.max(0, totalTarget - deployed) - n.soldiers) * 0.08;
        n.power = (n.soldiers + deployed) * n.warMult() + n.pop * 0.03;
        double upkeep = (n.soldiers + deployed) * 0.010 + bld;
        n.income = gold - upkeep;
        n.foodBalance = food;
        n.gold += n.income;
        n.wood = Math.min(2500, n.wood + wood);
        n.stone = Math.min(2500, n.stone + stone);
        n.science += sci;
        if (n.gold < 0) {
            n.gold = 0;
            n.soldiers *= 0.96;
        }
        if (n.gold > 99999) n.gold = 99999;
        if (n.era < Nation.ERAS.length - 1 && n.science >= Nation.ERA_COST[n.era + 1]) {
            n.era++;
            w.log(n.name + " entered the " + n.eraName() + " age.", n.id, n.player);
        }
        double garr = n.soldiers / Math.max(1, cs.size()) * 0.7;
        for (City c : cs) c.garrison = Math.min(garr, c.pop * 0.5);
    }

    private void clearTree(City c) {
        for (int[] b : c.blds) {
            if (b[2] != LUMBER) continue;
            for (int oy = -3; oy <= 3; oy++)
                for (int ox = -3; ox <= 3; ox++) {
                    int f = w.featAt(b[0] + ox, b[1] + oy);
                    if (f == TREE || f == PINE || f == PALM) {
                        w.setFeat(b[0] + ox, b[1] + oy, NONE, 0);
                        return;
                    }
                }
        }
        c.lumberYield = Math.max(0.3 * c.lumbers, c.lumberYield * 0.97);
    }

    public void step() {
        w.turn++;
        rebuildIndex();
        ArrayList<City> all = new ArrayList<>(w.cities.values());
        for (int i = 0; i < alive.size(); i++) {
            Nation n = alive.get(i);
            ArrayList<City> cs = byNation.get(n.id);
            if (cs == null || cs.isEmpty()) {
                destroyNation(n, null);
                continue;
            }
            economy(n, new ArrayList<>(cs));
            cs = byNation.get(n.id);
            if (cs == null) continue;
            for (City c : new ArrayList<>(cs)) {
                if (c.nation != n.id) continue;
                c.buildPoints = Math.min(3, c.buildPoints + 0.45 + c.pop * 0.003 + c.level * 0.25);
                int guard = 0;
                while (c.buildPoints >= 1 && guard++ < 2) {
                    if (!autoBuild(c, n)) break;
                    c.buildPoints -= 1;
                }
            }
            buildRoads(n);
            if ((w.turn + n.id) % 8 == 0) refreshNeighbors(n, cs);
            if (!n.player && (w.turn + n.id) % 3 == 0) aiThink(n, cs);
            else if (n.player && n.autoExpand && (w.turn + n.id) % 3 == 0) tryExpand(n, cs);
        }
        relationsDrift();
        moveArmies();
        events(all);
        if (w.turn % 6 == 0) spawnFrontier();
        offers.removeIf(o -> o.expires < w.turn);
        if (w.turn % 24 == 0) {
            // connect close neighbouring cities of the same nation with roads
            for (Nation n : alive) connectNearby(n);
        }
    }

    private void connectNearby(Nation n) {
        ArrayList<City> cs = byNation.get(n.id);
        if (cs == null || cs.size() < 2 || !n.roadQueue.isEmpty()) return;
        City a = cs.get(r.nextInt(cs.size()));
        City best = null;
        double bd = 1e9;
        for (City o : w.citiesNear(a.x, a.y, 32)) {
            if (o == a || o.nation != n.id) continue;
            double d = World.dist(a.x, a.y, o.x, o.y);
            if (d < bd && !roadBetween(a, o)) {
                bd = d;
                best = o;
            }
        }
        if (best != null) connect(n, a, best);
    }

    private boolean roadBetween(City a, City b) {
        int mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        for (int dy = -2; dy <= 2; dy++)
            for (int dx = -2; dx <= 2; dx++) {
                byte f = w.featAt(mx + dx, my + dy);
                if (f == ROAD || f == BRIDGE) return true;
            }
        return false;
    }

    private void relationsDrift() {
        for (Nation n : alive) {
            for (Relation rl : n.rel.values()) {
                if (rl.a != n.id) continue; // handle each pair once
                Nation o = w.nation(rl.b);
                if (o == null || !o.alive) continue;
                if (rl.state == Relation.WAR) rl.opinion = Math.max(-100, rl.opinion - 0.4);
                else if (rl.state == Relation.ALLY) rl.opinion = Math.min(100, rl.opinion + 0.25);
                else {
                    rl.opinion += -rl.opinion * 0.01;
                    if (n.neighbors.contains(o.id)) rl.opinion -= 0.10 * (n.aggression + o.aggression) / 2 + 0.02;
                    if (n.diplomat > 0.6 && o.diplomat > 0.6) rl.opinion += 0.12;
                    rl.opinion = Math.max(-100, Math.min(100, rl.opinion));
                }
            }
        }
    }

    // ---- UI helpers ----
    public ArrayList<City> citiesOf(Nation n) {
        ArrayList<City> l = byNation.get(n.id);
        return l == null ? new ArrayList<>() : l;
    }

    public ArrayList<Nation> aliveNations() {
        return alive;
    }

    public String acceptOffer(Offer o) {
        Nation a = w.nation(o.from), b = w.nation(o.to);
        offers.remove(o);
        if (a == null || b == null || !a.alive || !b.alive) return "Offer expired";
        if (o.type == 0) makePeace(a, b);
        else {
            rel(a, b).state = Relation.ALLY;
            w.log(a.name + " and " + b.name + " formed an alliance.", b.id, true);
        }
        return null;
    }
}
