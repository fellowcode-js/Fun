import sqlite3

SPEC = {"name": "sqlite", "description": "Run SQL against a SQLite file inside the project (created if missing).",
        "params": {"db": "str", "sql": "str"}}


def run(ctx, db: str, sql: str) -> dict:
    p = ctx.path(db)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=10)
    try:
        cur = con.executescript(sql) if sql.count(";") > 1 else con.execute(sql)
        rows = cur.fetchmany(200) if cur.description else []
        cols = [d[0] for d in cur.description] if cur.description else []
        con.commit()
        return {"ok": True, "columns": cols, "rows": rows, "changes": con.total_changes}
    except sqlite3.Error as e:
        return {"ok": False, "error": str(e)}
    finally:
        con.close()
