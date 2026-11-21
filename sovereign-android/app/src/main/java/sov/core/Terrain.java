package sov.core;

/** Terrain and feature ids plus their gameplay properties. */
public final class Terrain {
    private Terrain() {}

    public static final byte DEEP = 0, SHALLOW = 1, RIVER = 2, SAND = 3, GRASS = 4, SAVANNA = 5, JUNGLE = 6,
            DESERT = 7, TUNDRA = 8, SNOW = 9, SWAMP = 10, ROCK = 11, PEAK = 12;

    // Features: natural
    public static final byte NONE = 0, TREE = 1, PINE = 2, PALM = 3, CACTUS = 4, ROCKS = 5, ORE = 6;
    // Features: built by nations
    public static final byte FARM = 10, HOUSE = 11, MINE = 12, LUMBER = 13, ROAD = 14, DOCK = 15, TOWER = 16,
            CITY = 17, BRIDGE = 18;

    public static boolean isWater(int t) {
        return t <= RIVER;
    }

    public static boolean isLand(int t) {
        return t > RIVER;
    }

    /** Land a nation can build on (not water, not peaks). */
    public static boolean buildable(int t) {
        return t > RIVER && t != PEAK;
    }

    public static double fertility(int t) {
        switch (t) {
            case GRASS: return 1.0;
            case JUNGLE: return 0.75;
            case SAVANNA: return 0.65;
            case SWAMP: return 0.35;
            case TUNDRA: return 0.25;
            case SAND: return 0.15;
            case DESERT: return 0.10;
            case SNOW: return 0.03;
            default: return 0;
        }
    }

    public static boolean isNaturalFeature(int f) {
        return f >= TREE && f <= ORE;
    }

    public static boolean isBuilt(int f) {
        return f >= FARM;
    }

    public static String name(int t) {
        switch (t) {
            case DEEP: return "Deep Ocean";
            case SHALLOW: return "Shallows";
            case RIVER: return "River";
            case SAND: return "Beach";
            case GRASS: return "Grassland";
            case SAVANNA: return "Savanna";
            case JUNGLE: return "Jungle";
            case DESERT: return "Desert";
            case TUNDRA: return "Tundra";
            case SNOW: return "Snowfield";
            case SWAMP: return "Swamp";
            case ROCK: return "Mountains";
            case PEAK: return "High Peaks";
            default: return "?";
        }
    }

    /** Base RGB per terrain (used by renderer and minimap). */
    public static int color(int t) {
        switch (t) {
            case DEEP: return 0x1b3f7a;
            case SHALLOW: return 0x2f78b8;
            case RIVER: return 0x3f8fd0;
            case SAND: return 0xe0cf8c;
            case GRASS: return 0x5fa844;
            case SAVANNA: return 0xbdb25a;
            case JUNGLE: return 0x2f8a3a;
            case DESERT: return 0xe3c070;
            case TUNDRA: return 0x93a58a;
            case SNOW: return 0xeef3f8;
            case SWAMP: return 0x4a6f48;
            case ROCK: return 0x8a8378;
            case PEAK: return 0xd8dde4;
            default: return 0xff00ff;
        }
    }
}
