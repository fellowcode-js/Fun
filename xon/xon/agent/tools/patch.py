import subprocess
import tempfile

SPEC = {"name": "patch", "description": "Apply a unified diff to the project (checked first with git apply --check).",
        "params": {"diff": "str"}}


def run(ctx, diff: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
        f.write(diff if diff.endswith("\n") else diff + "\n")
    chk = subprocess.run(["git", "apply", "--check", "--whitespace=nowarn", f.name], cwd=ctx.root, capture_output=True, text=True)
    if chk.returncode != 0:
        return {"ok": False, "error": chk.stderr.strip()[:2000]}
    for line in diff.splitlines():
        if line.startswith(("+++ b/", "--- a/")):
            ctx.path(line[6:])  # jail + secret-file check on every touched path
    r = subprocess.run(["git", "apply", "--whitespace=nowarn", f.name], cwd=ctx.root, capture_output=True, text=True)
    return {"ok": r.returncode == 0, "error": r.stderr.strip()[:2000] or None}
