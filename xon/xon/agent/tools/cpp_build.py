from xon.agent.sandbox import run_cpp

SPEC = {"name": "cpp_build", "description": "Compile (g++/clang++, -Wall -Wextra) and run C++ from a file or snippet; "
        "sanitize=true adds AddressSanitizer + UBSan.", "params": {"path": "str?", "code": "str?", "sanitize": "bool?", "std": "str?"}}


def run(ctx, path: str = "", code: str = "", sanitize: bool = False, std: str = "c++17") -> dict:
    src = ctx.path(path).read_text() if path else code
    if not src.strip():
        return {"ok": False, "error": "give path or code"}
    flags = ("-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g") if sanitize else ()
    if path:
        flags = flags + (f"-I{ctx.path(path).parent}",)  # local #include "x.hpp" / "x.cpp"
    r = run_cpp(src, timeout=20, std=std, extra_flags=flags, mem_mb=4096 if sanitize else 1024)
    warnings = [l for l in r.get("stderr", "").splitlines() if "warning:" in l]
    return {**r, "warnings": warnings[:20]}
