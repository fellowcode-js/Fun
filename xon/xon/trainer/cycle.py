"""The learning cycle: pull -> clean/label -> train increment (+replay) -> evaluate (frozen) -> promote/rollback."""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

from PIL import Image

from xon import config
from xon.datasets import shapes, synth_ui
from xon.lm import data as lmdata
from xon.lm.model import LMConfig
from xon.pipeline.store import iter_records
from xon.tokenizer import BPETokenizer
from xon.trainer.promote import COMPONENTS, Registry, decide_components
from xon.trainer.replay import Replay
from xon.workstation.governor import Governor

log = config.log("cycle")


def status_write(cfg: dict, **kw) -> None:
    p = config.path(cfg, "exchange") / "status.json"
    try:
        cur = json.loads(p.read_text())
    except Exception:
        cur = {}
    cur.update(kw)
    cur["updated"] = time.time()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1, default=str))
    tmp.replace(p)


class Cycle:
    def __init__(self, cfg: dict | None = None, quick: bool = False):
        self.cfg = cfg or config.load()
        self.quick = quick
        self.root = Path(self.cfg["_root"])
        self.ck = config.path(self.cfg, "checkpoints")
        self.data = config.path(self.cfg, "data")
        self.ex = config.path(self.cfg, "exchange")
        self.evalsets = config.path(self.cfg, "evalsets")
        self.logs = config.path(self.cfg, "logs")
        self.gov = Governor(self.cfg, "trainer")
        self.reg = Registry(self.ck)
        self.state_f = self.ck / "cycle_state.json"
        self.state = json.loads(self.state_f.read_text()) if self.state_f.exists() else {"cycle": 0, "consumed": []}
        self.replay = Replay(self.ck / "replay.json", capacity=3000)
        self.plan = self.cfg.get("plan", {})

    def save_state(self):
        self.state_f.write_text(json.dumps(self.state, indent=1))

    # ---------- 1. pull
    def pull(self) -> list[dict]:
        from xon.nodes.transport import make_transport
        shard_dir = self.data / "shards"
        tr = make_transport(self.cfg)
        tr.pull("shards", shard_dir)
        man = json.loads((shard_dir / "manifest.json").read_text()) if (shard_dir / "manifest.json").exists() else {"shards": []}
        new = [s["name"] for s in man["shards"] if s["name"] not in self.state["consumed"]]
        recs = list(iter_records(shard_dir, names=new)) if new else []
        self.state["consumed"] += new
        self.state["last_pulled"] = new
        log.info(f"pulled {len(new)} new shards, {len(recs)} records")
        return recs

    def synth_batch(self, n_ui: int, n_shapes: int, cycle: int):
        out = self.data / "synth" / f"cycle-{cycle:03d}"
        start = 100_000 * cycle
        rows = synth_ui.load_index(out)
        if not rows:  # 40% v1 pages, 60% v2 app/settings/window/pricing GUIs
            n1 = int(n_ui * 0.4)
            rows = synth_ui.generate(out, n1, start_seed=start, gov=self.gov) + \
                synth_ui.generate(out, n_ui - n1, start_seed=start + 50_000, gov=self.gov, version=2)
        ui = [{"kind": "ui", "description": r["description"], "html": r["html"], "image_path": str(out / r["image"]),
               "boxes": r["boxes"], "license": r["license"], "source": r["source"]} for r in rows]
        pairs = []
        for s in range(start, start + n_shapes):
            img, sh, col, cap = shapes.make(s)
            pairs.append({"kind": "shape", "seed": s, "caption": cap, "label": shapes.SHAPES.index(sh)})
        return ui, pairs

    # ---------- 3. train
    def tokenizer(self, recs: list[dict]) -> BPETokenizer:
        p = self.ck / "tokenizer.json"
        if p.exists():
            return BPETokenizer.load(p)
        vocab = self.plan.get("lm", {}).get("vocab_size", 4096)
        tok = lmdata.build_tokenizer(recs, vocab, max_chars=2_000_000 if not self.quick else 300_000)
        tok.save(p)
        return tok

    def train_lm(self, tok, recs, cycle) -> dict:
        from xon.lm import train as lmtrain
        lmcfg_d = dict(self.plan.get("lm") or {})
        lmcfg_d["vocab_size"] = tok.vocab_size
        lmcfg = LMConfig.from_dict(lmcfg_d) if lmcfg_d.get("d_model") else LMConfig(vocab_size=tok.vocab_size, d_model=128, n_layers=4, n_heads=2, n_kv_heads=1, seq_len=256)
        lmcfg.vocab_size = tok.vocab_size
        train_ids, val_ids = lmdata.tokenize(recs, tok, seed=cycle, repeat={"ui": 1, "instruct": 2},
                                             lang_repeat={"python": 2, "cpp": 2})
        minutes = self.cfg["lm"]["minutes"] if not self.quick else 0.5
        batch = 16
        steps = int(self.plan.get("tokens", 20 * lmcfg.n_params()) / (batch * lmcfg.seq_len) / max(1, self.cfg.get("cycles", 1)))
        prom = self.ck / "promoted" / "lm.pt"
        # incremental cycles: cap at 3 epochs over this cycle's data and fine-tune at a lower LR (avoids the
        # overfit/forgetting that made cycle 2 regress)
        epochs_cap = int(3 * len(train_ids) / (batch * lmcfg.seq_len))
        if prom.exists():
            steps = min(steps, epochs_cap)
        steps = max(50, min(steps, 100_000)) if not self.quick else 60
        lr = self.cfg["lm"].get("lr", 3e-3) * (0.3 if prom.exists() else 1.0)
        out = self.ck / f"cycle-{cycle:03d}" / "lm"
        r = lmtrain.train(lmcfg, train_ids, val_ids, out, max_steps=steps, max_minutes=minutes, batch=batch,
                          lr=lr, warmup=min(100, steps // 10 + 1), eval_every=max(50, steps // 8),
                          init_from=prom if prom.exists() else None, resume=True, seed=self.cfg["xon"]["seed"] + cycle,
                          log_path=self.logs / "lm_train.jsonl", gov=self.gov)
        r.update({"train_tokens": int(len(train_ids)), "val_tokens": int(len(val_ids)), "path": str(out / "model.pt")})
        return r

    def train_vision(self, image_recs, ui, pairs, cycle) -> dict:
        from xon.pipeline.clean_images import from_b64
        from xon.vision import train as vtrain
        tr_pairs = [{"image": shapes.make(p["seed"])[0], "caption": p["caption"], "label": p["label"]} for p in pairs]
        weak = 0
        for r in image_recs:
            lab = (r.get("weak") or {}).get("class") or (r.get("pseudo") or {}).get("class")
            tr_pairs.append({"image": from_b64(r["image_b64"]), "caption": r["caption"],
                             "label": shapes.SHAPES.index(lab) if lab in shapes.SHAPES else None})
            weak += lab is not None
        tr_ui = [{"image": Image.open(u["image_path"]).convert("RGB"), "boxes": u["boxes"]} for u in ui if Path(u["image_path"]).exists()]
        out = self.ck / f"cycle-{cycle:03d}" / "vision"
        prom = self.ck / "promoted" / "vision.pt"
        r = vtrain.train(tr_pairs, tr_ui, out, minutes=self.cfg["vision"]["minutes"] if not self.quick else 0.4,
                         init_from=prom if prom.exists() else None, seed=cycle, gov=self.gov, log_path=self.logs / "vision_train.jsonl")
        r.update({"path": str(out / "vision.pt"), "web_images": len(image_recs), "web_labeled": weak})
        return r

    def pseudo_label(self, image_recs):
        prom = self.ck / "promoted" / "vision.pt"
        unl = [r for r in image_recs if not (r.get("weak") or {}).get("class")]
        if not prom.exists() or not unl:
            return 0
        from xon.pipeline.clean_images import from_b64
        from xon.vision import predict, train as vtrain
        m = vtrain.load_model(prom)
        labs = predict.pseudo_labels(m, [from_b64(r["image_b64"]) for r in unl], threshold=0.8)
        n = 0
        for r, l in zip(unl, labs):
            if l:
                r["pseudo"] = l
                n += 1
        return n

    def practice_round(self, recs) -> list[dict]:
        """Verified solutions from the warm-start coder (rejection sampling); cached across cycles."""
        f = self.data / "practice.jsonl"
        try:
            from xon.lm.pretrained import load
            coder = load(self.cfg) if not self.quick else None
        except Exception:
            coder = None
        if coder is not None:
            from xon.trainer import practice
            tasks = [r for r in recs if r.get("kind") == "instruct" and "xon-practice" not in (r.get("source") or "")]
            stats = practice.run(coder, tasks, f, self.evalsets, limit=self.cfg.get("practice", {}).get("limit", 60), log=log)
            log.info(f"practice round: {stats}")
        if not f.exists():
            return []
        return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]

    # ---------- 4. evaluate
    def evaluate(self, lm_path: Path, vision_path: Path, tok) -> dict:
        from xon.design import eval as deval
        from xon.design.render import Renderer
        from xon.lm import eval as leval
        from xon.lm import train as lmtrain
        from xon.vision import eval as veval
        from xon.vision import train as vtrain
        m = lmtrain.load_model(lm_path)
        res = {}
        ppl = leval.perplexity(m, tok, self.evalsets)
        pk = leval.code_pass_k(m, tok, self.evalsets, n_samples=5 if not self.quick else 2, limit=None if not self.quick else 10)
        bf = leval.bugfix(m, tok, self.evalsets)
        bfb = leval.bugfix(m, tok, self.evalsets, fname="bugfix_blind.jsonl")
        cpp = leval.cpp_pass_k(m, tok, self.evalsets, n_samples=5 if not self.quick else 1, limit=None if not self.quick else 5) \
            if (self.evalsets / "cpp_problems.jsonl").exists() else {"pass@1": 0.0, "pass@5": 0.0}
        vm = vtrain.load_model(vision_path)
        rec = veval.recognition(vm, self.evalsets)
        cache = self.data / "eval_cache" / "ui_heldout"
        with Renderer() as r:
            ui = veval.ui_detection(vm, self.evalsets, cache, renderer=r)
            ui2 = veval.ui_detection(vm, self.evalsets, cache, renderer=r, version=2) if (self.evalsets / "ui_heldout_v2.jsonl").exists() else {"f1@0.5": 0.0}
            fid = deval.fidelity_eval(vm, self.evalsets, cache, r, limit=12 if not self.quick else 3, steps=8 if not self.quick else 3)
            crit = deval.critique_sanity(r)
        con = deval.contrast_accuracy(self.evalsets)
        res.update({"code_ppl": ppl["ppl"], "code_bpc": ppl["bits_per_char"], "code_pass@1": pk["pass@1"],
                    "code_pass@5": pk["pass@5"], "bugfix_rate": bf["repair_rate"], "bugfix_lm_only": bf["lm_only_rate"],
                    "bugfix_blind_rate": bfb["repair_rate"], "bugfix_blind_lm_only": bfb["lm_only_rate"],
                    "recog_top1": rec["top1"], "recog_top5": rec["top5"], "recog_zero_shot": rec["zero_shot_top1"],
                    "ui_f1": ui["f1@0.5"], "ui_f1_v2": ui2["f1@0.5"], "cpp_pass@1": cpp["pass@1"], "cpp_pass@5": cpp["pass@5"], "ui_precision": ui["precision"], "ui_recall": ui["recall"],
                    "design_fidelity": fid["fidelity_final"], "design_fidelity_baseline": fid["fidelity_bg_only_baseline"],
                    "design_fidelity_initial": fid["fidelity_initial"], "contrast_accuracy": con["accuracy"],
                    "critique_recall": crit["recall"], "critique_generated_score": crit["generated_page_score"]})
        res["_detail"] = {"ppl": ppl, "pass_k": pk, "bugfix": bf, "bugfix_blind": bfb, "recognition": rec, "ui": ui, "ui_v2": ui2, "cpp_pass_k": cpp,
                          "fidelity": fid, "contrast": con, "critique": crit}
        return res

    # ---------- the cycle
    def run(self, n_ui: int = 300, n_shapes: int = 3000) -> dict:
        self.gov.tick()
        c = self.state["cycle"] + 1
        t0 = time.time()
        status_write(self.cfg, cycle=c, phase="pull")
        recs = self.pull()
        status_write(self.cfg, phase="synth")
        ui, pairs = self.synth_batch(n_ui if not self.quick else 40, n_shapes if not self.quick else 600, c)
        image_recs = [r for r in recs if r.get("kind") == "image"]
        status_write(self.cfg, phase="label")
        n_pseudo = self.pseudo_label(image_recs)
        status_write(self.cfg, phase="practice")
        practice = self.practice_round(recs + self.replay.items)
        text_recs = [r for r in recs if r.get("kind") in ("code", "text", "instruct")] + practice + [
            {k: v for k, v in u.items() if k in ("kind", "description", "html", "license", "source")} for u in ui]
        replay = self.replay.sample(len(self.replay.items))  # full replay buffer mixed with new data
        status_write(self.cfg, phase="tokenizer")
        tok = self.tokenizer(text_recs + replay)
        status_write(self.cfg, phase="train_lm")
        lm = self.train_lm(tok, text_recs + replay, c)
        status_write(self.cfg, phase="train_vision")
        vis = self.train_vision(image_recs, ui, pairs, c)
        status_write(self.cfg, phase="evaluate")
        metrics = self.evaluate(Path(lm["path"]), Path(vis["path"]), tok)
        detail = metrics.pop("_detail")
        best = self.reg.best_metrics()
        dc = decide_components(metrics, best, self.cfg["promote"]["noise_margin"], self.cfg["promote"]["max_regression"])
        files = {}
        if dc["lm"]["promote"]:
            files.update({"lm.pt": Path(lm["path"]), "tokenizer.json": self.ck / "tokenizer.json"})
        if dc["vision"]["promote"]:
            files["vision.pt"] = Path(vis["path"])
        merged = dict(best or {})
        for comp, keys in COMPONENTS.items():
            if dc[comp]["promote"]:
                merged.update({k: metrics[k] for k in keys if k in metrics})
        for k, v in metrics.items():  # tool-level metrics (contrast, critique...) follow the latest run
            if not any(k in keys for keys in COMPONENTS.values()):
                merged[k] = v
        if files:
            self.reg.promote(files, merged, c)
        d = {"promote": bool(files), "reason": "; ".join(f"{k}: {'PROMOTED' if v['promote'] else 'rolled back'} ({v['reason']})"
                                                       for k, v in dc.items())}
        self.replay.add([r for r in text_recs if r.get("kind") != "ui"][:2000] + [
            {k: v for k, v in u.items() if k in ("kind", "description", "html", "license", "source")} for u in ui[:200]])
        self.replay.save()
        rec = {"cycle": c, "promoted": d["promote"], "reason": d["reason"], "metrics": metrics,
               "components": {k: v["promote"] for k, v in dc.items()},
               "lm": {k: v for k, v in lm.items() if k != "events"}, "lm_events": lm["events"],
               "vision": {k: v for k, v in vis.items() if k != "events"}, "vision_events": vis["events"],
               "data": {"new_records": len(recs), "web_images": len(image_recs), "pseudo_labeled": n_pseudo,
                        "ui_synth": len(ui), "shapes": len(pairs), "replay": len(replay)},
               "minutes": round((time.time() - t0) / 60, 2)}
        self.reg.log(rec)
        (self.ck / f"cycle-{c:03d}" / "eval_detail.json").write_text(json.dumps(detail, indent=1, default=str))
        self.state["cycle"] = c
        self.save_state()
        status_write(self.cfg, phase="idle", last_cycle=rec)
        log.info(f"cycle {c} done in {rec['minutes']} min: promoted={d['promote']} ({d['reason']})")
        return rec
