"""R14 G: dump trimmed API responses for the plain-words writer tests (frontend/src/lib/v5/plain-words-g/fixtures/).

Usage: .venv/bin/python ops/r14_g_fixtures.py <name> <METHOD> <path> [json-body]
   or: .venv/bin/python ops/r14_g_fixtures.py --all     (the set this script knows)
Runs the Deal Desk / Borrower 360 apps in process (TestClient); services need not be running. Lists are cut to
the first 6 items and bulky keys (grid, lineage, sources, network) dropped so each fixture stays small.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
OUT = pathlib.Path(__file__).resolve().parents[1] / "frontend/src/lib/v5/plain-words-g/fixtures"
DROP = {"grid", "lineage", "sources", "network", "trade_off", "transition_table", "steps", "method_doc"}
DROP_OBJ = {"source", "evidence", "inputs", "trace", "terms"}  # dropped only when the value is an object or a list


def trim(x, depth=0):
    if isinstance(x, dict):
        return {k: trim(v, depth + 1) for k, v in x.items()
                if k not in DROP and not (k in DROP_OBJ and isinstance(v, (dict, list)))}
    if isinstance(x, list):
        return [trim(v, depth + 1) for v in x[:6]]
    if isinstance(x, str) and len(x) > 1200:
        return x[:1200]
    return x


def client(path: str):
    from fastapi.testclient import TestClient
    if path.startswith("/api/v1/intel/network") or path.startswith("/api/v1/b360"):
        from backend.b360.api import app
    else:
        from backend.dealdesk.api import app
    return TestClient(app)


def dump(name: str, method: str, path: str, body=None) -> None:
    c = client(path)
    r = c.request(method, path, json=body) if body is not None else c.request(method, path)
    if r.status_code != 200:
        raise SystemExit(f"{name}: {r.status_code} {r.text[:300]}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(trim(r.json()), indent=1, default=str))
    print(name, (OUT / f"{name}.json").stat().st_size)


if __name__ == "__main__":
    a = sys.argv[1:]
    dump(a[0], a[1], a[2], json.loads(a[3]) if len(a) > 3 else None)
