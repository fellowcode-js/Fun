"""Replay buffer: new shards are mixed with a reservoir sample of older records to avoid forgetting."""
from __future__ import annotations

import json
import random
from pathlib import Path


class Replay:
    def __init__(self, path: Path, capacity: int = 4000, seed: int = 0):
        self.path = Path(path)
        self.capacity = capacity
        self.rng = random.Random(seed)
        self.items: list[dict] = []
        self.seen = 0
        if self.path.exists():
            d = json.loads(self.path.read_text())
            self.items, self.seen = d["items"], d["seen"]

    def add(self, recs: list[dict]) -> None:
        for r in recs:
            self.seen += 1
            if len(self.items) < self.capacity:
                self.items.append(r)
            else:
                j = self.rng.randrange(self.seen)
                if j < self.capacity:
                    self.items[j] = r

    def sample(self, n: int) -> list[dict]:
        return self.rng.sample(self.items, min(n, len(self.items)))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": self.items, "seen": self.seen}))
        tmp.replace(self.path)
