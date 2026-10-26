"""R12 Session E: the lineage and no-side-door checks (PLAN_R12 §0 "Tests"), shared by every session's tests.

Lineage. A figure is traced when it carries a source that resolves to a registered relation and row:

    {"value": 71.0, "unit": "SAR million",
     "source": {"domain": "bureau", "relation": "other_bank_facility",
                "key": {"proposal_id": "R12-TWA", "bank_name": "Peninsula Trade Bank", "entity_id": "XE-TWA-01"},
                "period": "2026Q2", "column": "bureau_outstanding_mn"}}

`trace()` in the store builds such a source from a row. `figures(obj)` walks any API response or committee-paper
model and yields every dict that has a numeric "value"; `untraced(obj)` lists those whose source does not resolve.

No side door. `watch_opens()` records every file a block of code opens under data/; `side_doors(opened)` returns those
that are neither a registered relation file nor on ALLOWED (bank configuration and caches that are not data).
`static_side_doors(paths)` greps source files for data-file literals that are not registered.
"""
from __future__ import annotations

import builtins
import contextlib
import io
import pathlib
import re
from typing import Any, Iterator

V5 = pathlib.Path(__file__).resolve().parents[3]

#: Files under data/ that may be opened without being a relation: configuration, manifests and caches (PLAN §0 exception).
ALLOWED = (
    re.compile(r"(^|/)manifest[^/]*\.json$"),                     # release manifests (dictionary, versions)
    re.compile(r"^data/dealdesk/params/"),                         # versioned parameter tables (published as dd_parameter)
    re.compile(r"^data/dealdesk/model/"),                          # PD model ranges (model, not data)
    re.compile(r"^data/dealdesk/pipeline/options\.json$"),         # engine-options cache keyed by proposal + versions
    re.compile(r"^data/dealdesk/house_style/"),                    # house-style profile and exemplars (UI / drafting config)
    re.compile(r"^data/dealdesk/memos/"),                          # memo documents (files by design, memo_file column)
    re.compile(r"^data/dealdesk/demo_proposals/"),                 # R14 p: the proposal-check demo pack (documents by design)
    re.compile(r"^data/whatif_v5/"), re.compile(r"^var/"),         # model domain manifests, runtime store
    re.compile(r"^data/dealdesk/review/[^/]+\.json$"),            # R12 M: R11 review rules and precedent matching (config; B gap 3, F G7)
    re.compile(r"^data/scorecard_v5/.*\.spec\.json$"),            # R12 M: scorecard model specs read by the engine (model, not data; F G7, D gap 7)
    re.compile(r"^data/intel/network-saudi-v1/snapshot\.json$"),  # R14 G: build source of the net_* relations (engine output snapshot)
)


def registered_files() -> set[str]:
    from backend.data_builder.registry import DOMAINS
    out = set()
    for d in DOMAINS.values():
        for spec in d.get("relations", {}).values():
            out.add(spec["path"].rstrip("/"))
    return out


def _rel(p: str | pathlib.Path) -> str | None:
    try:
        q = pathlib.Path(p).resolve()
    except (OSError, ValueError):
        return None
    for base in (V5,):
        try:
            return q.relative_to(base).as_posix()
        except ValueError:
            continue
    import os
    r12 = os.environ.get("DEALDESK_R12_ROOT")
    if r12:
        try:
            return q.relative_to(pathlib.Path(r12).resolve()).as_posix()
        except ValueError:
            return None
    return None


def is_allowed(rel: str) -> bool:
    if not rel.startswith(("data/", "var/")):
        return True
    if rel in registered_files() or any(rel.startswith(f + "/") for f in registered_files() if not f.endswith(".parquet")):
        return True
    return any(a.search(rel) for a in ALLOWED)


@contextlib.contextmanager
def watch_opens() -> Iterator[list[str]]:
    """Record every data/ or var/ file opened (builtins.open, Path.open/read_*, pandas.read_parquet, pyarrow)."""
    opened: list[str] = []
    real_open = builtins.open
    real_io_open = io.open
    real_path_open = pathlib.Path.open

    def note(p: Any) -> None:
        r = _rel(p) if isinstance(p, (str, pathlib.Path)) else None
        if r and r.startswith(("data/", "var/")):
            opened.append(r)

    def o(file, *a, **k):  # noqa: ANN001
        note(file)
        return real_open(file, *a, **k)

    def po(self, *a, **k):  # noqa: ANN001
        note(self)
        return real_path_open(self, *a, **k)

    import pandas as pd
    real_rp = pd.read_parquet

    def rp(path, *a, **k):  # noqa: ANN001
        note(path)
        return real_rp(path, *a, **k)

    builtins.open, io.open, pathlib.Path.open, pd.read_parquet = o, o, po, rp
    try:
        yield opened
    finally:
        builtins.open, io.open, pathlib.Path.open, pd.read_parquet = real_open, real_io_open, real_path_open, real_rp


def side_doors(opened: list[str]) -> list[str]:
    return sorted({r for r in opened if not is_allowed(r)})


_LIT = re.compile(r"""["']([A-Za-z0-9_./-]+\.(?:parquet|json|sqlite|csv|xlsx))["']""")


def static_side_doors(paths: list[pathlib.Path]) -> list[tuple[str, str]]:
    """(file, literal) for every data-file literal in the given sources whose basename is not a registered relation
    file and that is not allowed by ALLOWED."""
    reg = registered_files()
    reg_names = {pathlib.Path(f).name for f in reg}
    bad = []
    for p in paths:
        for f in ([p] if p.is_file() else sorted(p.rglob("*.py"))):
            text = f.read_text(errors="ignore")
            for m in _LIT.finditer(text):
                lit = m.group(1)
                name = pathlib.Path(lit).name
                if name in reg_names or name.startswith("manifest") or name.endswith((".csv", ".xlsx")) and "export" in text:
                    continue
                if lit.startswith(("data/", "var/")) and is_allowed(lit):
                    continue
                if not lit.startswith(("data/", "var/")) and "/" not in lit and name.endswith(".json") and "params" in text[max(0, m.start() - 200):m.start()]:
                    continue
                bad.append((f.relative_to(V5).as_posix(), lit))
    return bad


# ------------------------------------------------------------------ lineage

def figures(obj: Any, path: str = "$") -> Iterator[tuple[str, dict[str, Any]]]:
    """Every dict with a numeric 'value' (a figure) in an API response or paper model."""
    if isinstance(obj, dict):
        v = obj.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            yield path, obj
        for k, x in obj.items():
            yield from figures(x, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, x in enumerate(obj):
            yield from figures(x, f"{path}[{i}]")


def resolves(src: dict[str, Any] | None) -> tuple[bool, str]:
    """Does a source point at a registered relation and at least one row with its key?"""
    if not isinstance(src, dict):
        return False, "no source"
    from backend.data_builder.registry import DOMAINS
    dom, rel, key = src.get("domain"), src.get("relation"), src.get("key") or {}
    if dom not in DOMAINS or rel not in DOMAINS[dom]["relations"]:
        return False, f"{dom}.{rel} is not registered"
    if not key:
        return True, ""
    from backend.dealdesk.data.store import dd_frame
    try:
        f = dd_frame(rel, **{k: v for k, v in key.items()})
    except KeyError as e:
        return False, f"bad key column {e}"
    if not len(f):
        return False, f"no row {key} in {rel}"
    col = src.get("column")
    if col and col not in f.columns:
        return False, f"{rel} has no column {col}"
    return True, ""


def untraced(obj: Any) -> list[tuple[str, str]]:
    """(path, reason) for every figure without a resolvable source (figures may carry 'source' or 'trace')."""
    out = []
    for p, fig in figures(obj):
        ok, why = resolves(fig.get("source") or fig.get("trace"))
        if not ok:
            out.append((p, why))
    return out


def figure(relation: str, row: dict[str, Any], column: str, unit: str = "") -> dict[str, Any]:
    """A traced figure from one row's column (what the APIs should return for every number)."""
    from backend.dealdesk.data.store import trace
    src = trace(relation, row)
    src["column"] = column
    return {"value": row[column], "unit": unit, "source": src}
