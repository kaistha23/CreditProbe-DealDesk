"""R12 Session E: the shared readers and the versioned publisher over the R12 relations (PLAN_R12 §0).

    from backend.dealdesk.data import dd_read, dd_frame, publish, trace

    dd_read("dd_document", proposal_id="R12-TWA", status=["pending", "expired"])   # -> list[dict]
    dd_frame("bureau_cbrbr", proposal_id="R12-TWB")                               # -> DataFrame
    publish("dd_review_finding", rows, mode="upsert", actor="B")                 # -> {"version": n, ...}
    trace("dd_document", row)  # -> {"domain", "relation", "key", "period", "version"}  (lineage)

Reads also cover the registered existing relations Deal Desk needs (rel_*, dep_*, col_*, dd_proposal …):
`dd_read` accepts any relation id registered in the Data Builder registry.

Where files live: under the v5 checkout (`data/…`), or under DEALDESK_R12_ROOT when set (tests point it at a
scratch copy so they never touch the committed data). A publish writes the relation's parquet atomically,
updates its folder manifest (rows, columns, version, sha, history) and archives the previous file under
var/dealdesk/r12_history/<relation>/v<n>.parquet (git-ignored).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import pathlib
import threading
from typing import Any, Iterable

import pandas as pd

from backend.dealdesk.data import schema as S

V5 = pathlib.Path(__file__).resolve().parents[3]
_LOCK = threading.RLock()
_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}


class SchemaError(ValueError):
    pass


def root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("DEALDESK_R12_ROOT") or V5).resolve()


def history_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("DEALDESK_R12_HISTORY") or (root() / "var" / "dealdesk" / "r12_history")).resolve()


# ------------------------------------------------------------------ registry lookup

def _registered() -> dict[str, dict[str, Any]]:
    """relation id -> {domain, path, keys, period} for every relation in the Data Builder registry."""
    from backend.data_builder.registry import DOMAINS
    out: dict[str, dict[str, Any]] = {}
    for dom, d in DOMAINS.items():
        for rid, spec in d.get("relations", {}).items():
            out.setdefault(rid, {"domain": dom, "path": spec["path"], "keys": spec.get("key_columns") or [],
                                 "period": spec.get("period_column")})
    return out


def relation_path(relation: str) -> pathlib.Path:
    if relation in S.RELATIONS:
        return root() / S.RELATIONS[relation]["folder"] / f"{relation}.parquet"
    reg = _registered()
    if relation not in reg:
        raise KeyError(f"relation {relation!r} is not registered in Data Domains")
    return root() / reg[relation]["path"]


def domain_of(relation: str) -> str:
    if relation in S.RELATIONS:
        return S.RELATIONS[relation]["domain"]
    return _registered()[relation]["domain"]


def keys_of(relation: str) -> list[str]:
    if relation in S.RELATIONS:
        return list(S.RELATIONS[relation]["keys"])
    return list(_registered()[relation]["keys"])


# ------------------------------------------------------------------ typed empty frames

def empty(relation: str) -> pd.DataFrame:
    return pd.DataFrame({n: pd.Series([], dtype=S.PY_TYPE[t] if t != "float" else "float64")
                         for n, t, _, _ in S.columns(relation)}).astype(_dtypes(relation))


def _dtypes(relation: str) -> dict[str, str]:
    return {n: ("Int64" if t in ("int", "flag") else "float64" if t == "float" else "string")
            for n, t, _, _ in S.columns(relation)}


def _na(v: Any) -> bool:
    if v is None or v is pd.NA:
        return True
    if isinstance(v, float) and v != v:
        return True
    return False


def conform(relation: str, rows: Iterable[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    """Rows -> a frame with exactly the contract's columns and types. Unknown columns are an error."""
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    names = S.column_names(relation)
    unknown = [c for c in df.columns if c not in names]
    if unknown:
        raise SchemaError(f"{relation}: columns not in the contract: {unknown}")
    for n, t, _, _ in S.columns(relation):
        if n not in df.columns:
            df[n] = None
        if t == "json":
            df[n] = df[n].map(lambda v: None if _na(v) or v == "" else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
        if t in ("int", "flag"):
            df[n] = pd.to_numeric(df[n].map(lambda v: None if _na(v) else v), errors="raise").round().astype("Int64")
        elif t == "float":
            df[n] = pd.to_numeric(df[n].map(lambda v: None if _na(v) else v), errors="raise").astype("float64")
        else:
            df[n] = df[n].astype(object).map(lambda v: None if _na(v) else str(v)).astype("string")
    return df[names].reset_index(drop=True)


# ------------------------------------------------------------------ reading

def _load(relation: str) -> pd.DataFrame:
    p = relation_path(relation)
    if not p.exists():
        if relation in S.RELATIONS:
            return empty(relation)
        raise FileNotFoundError(p)
    mt = p.stat().st_mtime
    key = str(p)
    hit = _CACHE.get(key)
    if hit and hit[0] == mt:
        return hit[1]
    df = pd.read_parquet(p)
    _CACHE[key] = (mt, df)
    return df


def dd_frame(relation: str, columns: list[str] | None = None, **filters: Any) -> pd.DataFrame:
    """The relation as a DataFrame, filtered by equality (scalar) or membership (list / tuple / set)."""
    df = _load(relation)
    m = pd.Series(True, index=df.index)
    for col, val in filters.items():
        if col not in df.columns:
            raise KeyError(f"{relation} has no column {col!r}")
        if isinstance(val, (list, tuple, set, frozenset)):
            m &= df[col].isin(list(val))
        elif val is None:
            m &= df[col].isna()
        else:
            m &= df[col] == val
    out = df[m]
    if columns:
        out = out[columns]
    return out.reset_index(drop=True).copy()


def _py(v: Any) -> Any:
    if v is None or v is pd.NA:
        return None
    if isinstance(v, float) and v != v:
        return None
    if hasattr(v, "item"):
        try:
            return v.item()
        except (ValueError, AttributeError):
            pass
    return v


def dd_read(relation: str, columns: list[str] | None = None, parse_json: bool = True, **filters: Any) -> list[dict[str, Any]]:
    """The relation's rows as JSON-ready dicts (NA -> None; json columns parsed unless parse_json=False)."""
    df = dd_frame(relation, columns=columns, **filters)
    jcols = {n for n, t, _, _ in S.columns(relation) if t == "json"} if (parse_json and relation in S.RELATIONS) else set()
    out = []
    for rec in df.to_dict(orient="records"):
        r = {k: _py(v) for k, v in rec.items()}
        for c in jcols & r.keys():
            if isinstance(r[c], str) and r[c]:
                try:
                    r[c] = json.loads(r[c])
                except ValueError:
                    pass
        out.append(r)
    return out


def trace(relation: str, row: dict[str, Any]) -> dict[str, Any]:
    """Lineage of one row: the domain, relation, key (col -> value), period and version it came from."""
    keys = [k for k in keys_of(relation) if k in row]
    return {"domain": domain_of(relation), "relation": relation, "key": {k: _py(row[k]) for k in keys},
            "period": _py(row.get(S.PERIOD)), "version": _py(row.get("rel_version"))}


# ------------------------------------------------------------------ manifest

def manifest_path(folder: str) -> pathlib.Path:
    return root() / folder / S.MANIFEST[folder]


def read_manifest(folder: str) -> dict[str, Any]:
    p = manifest_path(folder)
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _content_hash(df: pd.DataFrame) -> str:
    d = df.drop(columns=["published_at"], errors="ignore").copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(9)
    return hashlib.sha256(d.to_csv(index=False).encode()).hexdigest()


_RELEASE = {S.DD_DIR: "dd-saudi-v1 (R12 relations)", S.B360_DIR: "b360-saudi-v1", S.BUR_DIR: "bureau-r12-v1", S.GOV_DIR: "gov-saudi-v1 (R13 IE)"}
_DOMAIN_LABEL = {S.DD_DIR: "Deal Desk and Deal Desk products", S.B360_DIR: "Borrower 360", S.BUR_DIR: "Bureau", S.GOV_DIR: "Governance"}
# folders added later by a schema block declare (release id, domain label) in S.FOLDER_TEXT (R14 G: network-saudi-v1)
_RELEASE.update({f: v[0] for f, v in getattr(S, "FOLDER_TEXT", {}).items()})
_DOMAIN_LABEL.update({f: v[1] for f, v in getattr(S, "FOLDER_TEXT", {}).items()})


def _write_manifest(folder: str, relation: str, df: pd.DataFrame, version: int, at: str, actor: str, mode: str) -> None:
    m = read_manifest(folder)
    m.update({
        "release_id": _RELEASE[folder], "domain_label": _DOMAIN_LABEL[folder], "origin": "FICTIONAL",
        "not_client_data": "Fictional demonstration data generated by CreditProbe v5 (R12 Session E). It describes no real "
                           "bank, company, family, person, developer, consultant or project.",
        "contract": "docs/v5/R12_DATA_CONTRACT.md (backend/dealdesk/data/schema.py)",
        "as_of": S.AS_OF, "period_column": S.PERIOD})
    m.setdefault("relations", {})
    spec = S.RELATIONS[relation]
    rel = m["relations"].get(relation, {})
    hist = rel.get("history", [])
    entry = {"version": version, "published_at": at, "by": actor, "mode": mode, "rows": int(len(df)), "content_sha256": _content_hash(df)}
    hist = (hist + [entry])[-50:]
    m["relations"][relation] = {"label": spec["label"], "domain": spec["domain"], "key_columns": spec["keys"], "grain": spec["grain"],
                                "period_column": S.PERIOD, "owner": spec["owner"], "writers": spec["writers"],
                                "rows": int(len(df)), "columns": list(df.columns), "version": version, "published_at": at,
                                "content_sha256": entry["content_sha256"], "history": hist}
    m["dictionary"] = S.dictionary(folder)
    m["relations"] = dict(sorted(m["relations"].items()))
    p = manifest_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(p)


def version_of(relation: str) -> int:
    folder = S.RELATIONS[relation]["folder"]
    return int(read_manifest(folder).get("relations", {}).get(relation, {}).get("version", 0))


# ------------------------------------------------------------------ publishing

def publish(relation: str, rows: Iterable[dict[str, Any]] | pd.DataFrame, mode: str = "upsert", actor: str = "system",
            at: str | None = None, where: dict[str, Any] | None = None) -> dict[str, Any]:
    """Publish rows to an R12 relation as a new version.

    mode  upsert   replace rows with the same key, add the others (default; what the app's decisions use)
          append   add rows (key collisions are an error)
          replace  the rows become the whole relation (demo builds)
          replace_where  drop the rows matching `where` (e.g. {"proposal_id": "R12-TWA"}), then add the rows: how a
                   writer recomputes one deal's findings, SWOT or stress results (seeded rows of that deal go too)
    Rows are conformed to the contract (unknown columns raise SchemaError); reporting_quarter defaults to the
    Deal Desk as-of; rel_version and published_at are stamped on the rows this version writes.
    """
    if relation not in S.RELATIONS:
        raise KeyError(f"{relation!r} is not an R12 relation (publish only writes the contract's relations)")
    if mode not in ("upsert", "append", "replace", "replace_where"):
        raise ValueError("mode must be upsert, append, replace or replace_where")
    if mode == "replace_where" and not where:
        raise ValueError("replace_where needs where={column: value}")
    spec = S.RELATIONS[relation]
    at = at or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with _LOCK:
        new = conform(relation, rows)
        new[S.PERIOD] = new[S.PERIOD].fillna(S.AS_OF)
        version = version_of(relation) + 1
        new["rel_version"] = pd.array([version] * len(new), dtype="Int64")
        new["published_at"] = pd.array([at] * len(new), dtype="string")
        keys = spec["keys"]
        if new.duplicated(subset=keys).any():
            raise SchemaError(f"{relation}: duplicate keys in the rows published: "
                              f"{new[new.duplicated(subset=keys, keep=False)][keys].head(5).to_dict('records')}")
        path = relation_path(relation)
        old = conform(relation, pd.read_parquet(path)) if path.exists() else empty(relation)
        if mode == "replace":
            out = new
        elif mode == "replace_where":
            drop = pd.Series(True, index=old.index)
            for c, v in (where or {}).items():
                drop &= old[c].isin(list(v)) if isinstance(v, (list, tuple, set)) else (old[c] == v)
            keep = old[~drop.fillna(False).astype(bool)]
            k_keep = keep[keys].astype(str).agg("\x1f".join, axis=1) if len(keep) else pd.Series([], dtype=str)
            k_new = set(new[keys].astype(str).agg("\x1f".join, axis=1)) if len(new) else set()
            out = pd.concat([keep[~k_keep.isin(k_new).values] if len(keep) else keep, new], ignore_index=True)
        else:
            k_old = old[keys].astype(str).agg("\x1f".join, axis=1) if len(old) else pd.Series([], dtype=str)
            k_new = set(new[keys].astype(str).agg("\x1f".join, axis=1)) if len(new) else set()
            clash = k_old.isin(k_new)
            if mode == "append" and clash.any():
                raise SchemaError(f"{relation}: append would duplicate {int(clash.sum())} existing keys")
            out = pd.concat([old[~clash.values] if len(old) else old, new], ignore_index=True)
        out = conform(relation, out).sort_values(keys, kind="stable").reset_index(drop=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            h = history_root() / relation
            h.mkdir(parents=True, exist_ok=True)
            (h / f"v{version - 1:04d}.parquet").write_bytes(path.read_bytes())
        tmp = path.with_suffix(".parquet.tmp")
        out.to_parquet(tmp, index=False)
        tmp.replace(path)
        _CACHE.pop(str(path), None)
        _write_manifest(spec["folder"], relation, out, version, at, actor, mode)
    return {"relation": relation, "domain": spec["domain"], "version": version, "rows": int(len(out)),
            "written": int(len(new)), "published_at": at}


def write_empty(relation: str) -> None:
    """The SCHEMA READY state: a valid empty parquet with the contract's columns (version 1)."""
    publish(relation, empty(relation).drop(columns=[c[0] for c in S.LINEAGE]), mode="replace", actor="E:schema")
