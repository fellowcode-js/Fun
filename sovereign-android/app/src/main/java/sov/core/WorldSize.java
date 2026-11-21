package sov.core;

public enum WorldSize {
    EXTRA_SMALL("Extra Small", 128, 3),
    SMALL("Small", 192, 4),
    SMALL_PLUS("Small Plus", 256, 5),
    MEDIUM("Medium", 384, 6),
    MEDIUM_PLUS_PLUS("Medium Plus Plus", 512, 8),
    HUGE("Huge", 768, 10),
    HUGE_PLUS_PLUS("Huge Plus Plus", 1024, 13),
    GIGANTIC("Gigantic", 1536, 17),
    TITANIC("Titanic", 2048, 22),
    COLOSSOMANTIC("Colossomantic", 4096, 34),
    INFINITE("Infinite", 0, 7);

    public final String label;
    /** Tiles per side, 0 means unbounded. */
    public final int tiles;
    public final int startNations;

    WorldSize(String label, int tiles, int startNations) {
        this.label = label;
        this.tiles = tiles;
        this.startNations = startNations;
    }

    public boolean infinite() {
        return tiles == 0;
    }
}
