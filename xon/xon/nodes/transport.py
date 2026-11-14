"""Transport between nodes: a shared folder, rsync, or any S3-compatible bucket. Plain files only.

Layout under the exchange root: shards/ (crawler -> trainer), heartbeats/, status.json, commands/.
Writes are atomic (temp file + rename) and shards are immutable, so readers never see partial files.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from xon import config


class FolderTransport:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def push(self, local: Path, remote: str) -> int:
        dst = self.root / remote
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in sorted(Path(local).glob("*")):
            if f.is_file() and not f.name.endswith((".part", ".tmp")):
                target = dst / f.name
                if f.name == "manifest.json" or not target.exists():
                    if f.resolve() == target.resolve():
                        continue
                    tmp = target.with_name(target.name + ".tmp")
                    shutil.copy2(f, tmp)
                    os.replace(tmp, target)
                    n += 1
        return n

    def pull(self, remote: str, local: Path) -> int:
        src = self.root / remote
        local = Path(local)
        local.mkdir(parents=True, exist_ok=True)
        if not src.exists() or src.resolve() == local.resolve():
            return 0
        n = 0
        for f in sorted(src.glob("*")):
            if f.is_file() and not f.name.endswith((".part", ".tmp")):
                target = local / f.name
                if f.name == "manifest.json" or not target.exists():
                    tmp = target.with_name(target.name + ".tmp")
                    shutil.copy2(f, tmp)
                    os.replace(tmp, target)
                    n += 1
        return n


class RsyncTransport:
    def __init__(self, url: str):
        self.url = url.rstrip("/")  # user@host:/path

    def push(self, local: Path, remote: str) -> int:
        subprocess.run(["rsync", "-a", "--exclude=*.part", "--exclude=*.tmp", f"{local}/", f"{self.url}/{remote}/"], check=True)
        return -1

    def pull(self, remote: str, local: Path) -> int:
        Path(local).mkdir(parents=True, exist_ok=True)
        subprocess.run(["rsync", "-a", "--exclude=*.part", "--exclude=*.tmp", f"{self.url}/{remote}/", f"{local}/"], check=True)
        return -1


class S3Transport:
    """s3://bucket/prefix; endpoint from XON_S3_ENDPOINT for S3-compatible stores (MinIO, R2, B2...)."""

    def __init__(self, url: str):
        import boto3  # optional dependency: pip install xon[s3]
        rest = url[len("s3://"):]
        self.bucket, _, self.prefix = rest.partition("/")
        self.s3 = boto3.client("s3", endpoint_url=os.environ.get("XON_S3_ENDPOINT") or None)

    def push(self, local: Path, remote: str) -> int:
        n = 0
        for f in Path(local).glob("*"):
            if f.is_file() and not f.name.endswith((".part", ".tmp")):
                self.s3.upload_file(str(f), self.bucket, f"{self.prefix}/{remote}/{f.name}".lstrip("/"))
                n += 1
        return n

    def pull(self, remote: str, local: Path) -> int:
        Path(local).mkdir(parents=True, exist_ok=True)
        pre = f"{self.prefix}/{remote}/".lstrip("/")
        n = 0
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=pre):
            for o in page.get("Contents", []):
                name = o["Key"][len(pre):]
                t = Path(local) / name
                if name == "manifest.json" or not t.exists():
                    self.s3.download_file(self.bucket, o["Key"], str(t))
                    n += 1
        return n


def make_transport(cfg: dict):
    t = cfg.get("transport", {})
    kind, url = t.get("kind", "folder"), t.get("url", "")
    if kind == "rsync":
        return RsyncTransport(url)
    if kind == "s3":
        return S3Transport(url)
    return FolderTransport(Path(url) if url else config.path(cfg, "exchange"))
