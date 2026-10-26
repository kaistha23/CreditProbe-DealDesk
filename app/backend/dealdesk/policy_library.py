"""PLAN_R12 Session G (R11_FEEDBACK I2–I5): the policy library, upload-and-review, provenance and the Excel export.

Session O's P6 learner (`house_style.onboarding`) reads the uploaded policy; this module turns what it learned into a
review table over every Deal Desk parameter:

    found      the policy sets this parameter: the proposed value, the clause and its quote, the change against the value
               in force (same / tighter / looser / changed). Default: accept (or edit the value).
    not found  the policy is silent: keep the value in force (default) or define a value now.
    new        the policy states a threshold or condition that is not a Deal Desk parameter yet: skip (default), add it as a
               parameter (the `policy_params` table) or as a review rule (P6's accepted rule book).

Approve writes one new version per changed table through the owners' own writers (`params.edit`, `desk_params.edit`),
records provenance for every value it set (`provenance.jsonl`: policy, version, clause, quote, approved by), marks the
policy active (the previous active version of the same policy superseded) and publishes `dd_policy` and `dd_parameter`.
Reject marks the upload rejected; no parameter file changes (tested byte for byte).

Store (git-ignored, under DEALDESK_VAR):
    policies/index.json                        every upload: id, title, version, dates, uploader, status, review, decisions
    policies/<policy_id>/v<n>/original.<ext>   the uploaded file, kept as uploaded
    params/provenance.jsonl                    one line per value a policy (or a policy review) set
    params/policy_params/v<n>.json             parameters that came from a policy and had no Deal Desk table before
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re
import threading
from datetime import UTC, datetime
from typing import Any

from backend.dealdesk import desk_params, params, paths

_LOCK = threading.RLock()
SAMPLE_MAKER = "maker (sample policy)"
FORMATS = (".docx", ".pdf", ".md", ".txt")
GROUP_PARAM, GROUP_APPETITE, GROUP_DOA, GROUP_MARKET, GROUP_EXTRA = (
    "Deal Desk parameters", "Risk appetite", "Delegation of authority", "Market bounds", "Added from policy")


class NotFound(KeyError):
    pass


class Conflict(ValueError):
    pass


# ------------------------------------------------------------------ store

#: the library's own runtime store (operational, git-ignored), in the default layout; it moves with DEALDESK_VAR
INDEX_FILE = "var/dealdesk/policies/index.json"
#: P6's pointer to its latest learning session (house_style.onboarding.service), restored after a policy upload
P6_LATEST = "var/dealdesk/house_style/onboarding/latest.json"


def root():
    return paths.VAR / "policies"


def _index_path():
    return paths.VAR / pathlib.PurePosixPath(INDEX_FILE).relative_to("var/dealdesk")


def _ledger():
    return paths.VAR / "params" / "provenance.jsonl"


def _extra_dir():
    return paths.VAR / "params" / "policy_params"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(d: datetime | None = None) -> str:
    return (d or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _w(p, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))
    tmp.replace(p)


def _index() -> list[dict[str, Any]]:
    f = _index_path()
    return json.loads(f.read_text()) if f.exists() else []


def _save_index(rows: list[dict[str, Any]]) -> None:
    _w(_index_path(), rows)


# ------------------------------------------------------------------ value display (the screen and the Excel use the same)

def _pc(x: float, d: int = 2) -> str:
    return f"{x * 100:.{d}f}%"


def display(v: Any, unit: str = "") -> str:
    """One value in the words the Parameters page uses: shares and rates in %, multiples with x, money in SAR m."""
    u = (unit or "").lower()
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (int, float)):
        if u in ("share", "rate", "rate_map", "ccf", "pct"):
            return _pc(float(v))
        if u == "x":
            return f"{float(v):.2f}x"
        if u in ("sar m", "money"):
            return f"SAR {float(v):,.1f}m"
        if u == "bps":
            return f"{float(v):,.0f} bps"
        if u in ("years", "years_map"):
            return f"{float(v):g} year" + ("" if float(v) == 1 else "s")
        return f"{float(v):,.4g}" if isinstance(v, float) else f"{v:,}"
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        if v and isinstance(v[0], dict) and "level" in v[0]:  # DoA
            return " · ".join(f"{r['level']} {('up to SAR ' + format(float(r['max_exposure']), ',.1f') + 'm') if r.get('max_exposure') not in (None, 1e9) and float(r['max_exposure']) < 1e8 else 'above'}"
                              f"{(', ' + r['min_rating'] + ' or better') if r.get('min_rating') else ''}" for r in v)
        if len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
            return f"{display(v[0], unit)}–{display(v[1], unit)}"
        return f"{len(v)} rows"
    if isinstance(v, dict):
        if "regulatory" in v:
            return f"regulatory {_pc(float(v['regulatory']))}"
        if "tenors" in v and "base" in v:
            return " · ".join(f"{t}y {_pc(b)}" for t, b in zip(v["tenors"], v["base"], strict=False))
        sub = {"rate_map": "rate", "number_map": "", "text_map": "", "years_map": "years"}.get(u, u)
        parts = []
        for k, x in v.items():
            if isinstance(x, list) and x and all(isinstance(y, (int, float)) for y in x):
                parts.append(f"{k} {display(x[0], sub)}–{display(x[-1], sub)}" if u != "bps_map" else f"{k} {x[0]:g}–{x[-1]:g} bps")
            elif isinstance(x, dict):
                parts.append(f"{k} ({len(x)})")
            else:
                parts.append(f"{k} {display(x, sub)}")
        return " · ".join(parts)
    return str(v)


# ------------------------------------------------------------------ the parameter universe

#: risk-appetite row → the field that holds its limit, and the unit words for the display
_LIMIT_FIELDS = ("limit", "limits", "limit_pct_tier1", "new_to_bank", "headroom_sar_mn")


def _appetite_field(row: dict[str, Any]) -> str:
    return next((f for f in _LIMIT_FIELDS if f in row), "limit")


def _appetite_unit(row: dict[str, Any], field: str) -> str:
    if field == "limit_pct_tier1":
        return "share"
    if field == "limits" and row.get("unit") == "years":
        return "years_map"
    return {"SAR m": "sar m"}.get(row.get("unit", ""), row.get("unit", ""))


def _table_meta(table: str) -> dict[str, Any]:
    return desk_params.table() if table == desk_params.NAME else params.table(table)


def universe() -> list[dict[str, Any]]:
    """Every parameter the policy review can set: the Parameters page catalogue, the risk-appetite limits, the DoA
    matrix, the market bounds and the parameters a policy added. One row each, with its value in force."""
    out: list[dict[str, Any]] = []
    for r in desk_params.catalogue():
        key = r["key"] or "*"
        out.append({"id": f"{r['table']}.{key}", "group": GROUP_PARAM, "table": r["table"], "key": r["key"], "field": "",
                    "label": r["label"], "unit": r["kind"], "value": r["value"], "display": display(r["value"], r["kind"]),
                    "version": r["version"], "effective_from": r["effective_from"], "owner": r["owner"], "why": r["why"],
                    "where": r["where"], "editable": r["editable"]})
    ra = params.table("risk_appetite")
    for row in ra["rows"]:
        f = _appetite_field(row)
        unit = _appetite_unit(row, f)
        out.append({"id": f"risk_appetite.{row['name']}", "group": GROUP_APPETITE, "table": "risk_appetite", "key": row["name"],
                    "field": f, "label": row.get("label", row["name"]), "unit": unit, "value": row.get(f),
                    "display": display(row.get(f), unit), "version": ra["version"], "effective_from": ra["effective_from"],
                    "owner": ra["owner"], "kind": row.get("kind", ""), "appetite": _levels(row, "appetite"),
                    "trigger": _levels(row, "trigger"), "basis": row.get("basis", ""),
                    "why": f"A {row.get('kind', 'hard')} risk-appetite limit the Deal Desk tests every deal against.",
                    "where": row.get("basis", "Risk appetite statement, approved by the Board."), "editable": True})
    doa = params.table("doa")
    dv = [{"level": r["level"], "max_exposure": r["max_exposure"], "min_rating": r.get("min_rating")} for r in doa["rows"]]
    out.append({"id": "doa.rows", "group": GROUP_DOA, "table": "doa", "key": "rows", "field": "", "label": "Delegation of Authority matrix",
                "unit": "doa", "value": dv, "display": display(dv), "version": doa["version"], "effective_from": doa["effective_from"],
                "owner": doa["owner"], "why": "Who approves a deal, by aggregate exposure and rating.",
                "where": "Credit policy appendix, approved by the Board.", "editable": False})
    mb = params.table("market_bounds")
    mv = {b: v["margin_bps"] for b, v in mb["rows"]["by_bucket"].items()}
    out.append({"id": "market_bounds.by_bucket", "group": GROUP_MARKET, "table": "market_bounds", "key": "by_bucket", "field": "margin_bps",
                "label": "Margin bounds by rating bucket", "unit": "bps_map", "value": mv, "display": display(mv, "bps_map"),
                "version": mb["version"], "effective_from": mb["effective_from"], "owner": mb["owner"],
                "why": "The margin range the optimiser may offer per rating bucket.", "where": "Pricing policy (Treasury and Risk).",
                "editable": False})
    ex = extra_table()
    for k, r in ex["rows"].items():
        out.append({"id": f"policy_params.{k}", "group": GROUP_EXTRA, "table": "policy_params", "key": k, "field": "", "label": r["label"],
                    "unit": r.get("unit", ""), "value": r.get("value"), "display": r.get("display") or display(r.get("value"), r.get("unit", "")),
                    "version": ex["version"], "effective_from": ex["effective_from"], "owner": "Risk",
                    "why": "A threshold the bank's credit policy states; added as a parameter at the policy review.",
                    "where": r.get("source", ""), "editable": False})
    return out


def _levels(row: dict[str, Any], lvl: str) -> Any:
    for k in (lvl, f"{lvl}s", f"{lvl}_pct_tier1", f"{lvl}_sar_mn"):
        if k in row:
            return row[k]
    return None


def extra_table() -> dict[str, Any]:
    d = _extra_dir()
    vs = sorted(d.glob("v*.json"), key=lambda q: int(q.stem[1:])) if d.exists() else []
    if vs:
        return json.loads(vs[-1].read_text())
    return {"name": "policy_params", "owner": "Risk", "version": "v0", "effective_from": "", "rows": {}}


# ------------------------------------------------------------------ provenance (I4)

def _ledger_rows() -> list[dict[str, Any]]:
    f = _ledger()
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()]


def _field_value(table: str, key: str, field: str) -> Any:
    for u in universe():
        if u["table"] == table and (u["key"] or "") == (key or ""):
            v = u["value"]
            if field and isinstance(v, dict) and field in v and u["field"] != field:
                return v[field]
            return v
    return None


def _norm(x: Any) -> Any:
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, (int, float)):
        return round(float(x), 9)
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_norm(v) for v in x]
    return x


def _same(a: Any, b: Any) -> bool:
    """Equal as values: 1 and 1.0 are the same tenor; key order does not matter."""
    return json.dumps(_norm(a), sort_keys=True, default=str) == json.dumps(_norm(b), sort_keys=True, default=str)


def provenance(row: dict[str, Any], ledger: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Where the value in force came from: the policy clause that set it, or the person who set it by hand."""
    led = _ledger_rows() if ledger is None else ledger
    mine = [e for e in led if e["table"] == row["table"] and (e["key"] or "") == (row["key"] or "")]
    if mine:
        e = mine[-1]
        cur = row["value"]
        if e.get("subfield") and isinstance(cur, dict):
            cur = cur.get(e["subfield"])
        if e.get("version") == row["version"] or _same(cur, e.get("value")):
            if e["source"] == "policy":
                ed = (f"; {e['by']} set {display(e['value'], e.get('unit', ''))} at approval instead of the policy's "
                      f"{display(e['edited_from'], e.get('unit', ''))}"
                      if e.get("edited_from") is not None else "")
                return {"kind": "policy", "edited_from": e.get("edited_from"), "policy_id": e["policy_id"], "policy": e["policy_title"], "policy_version": e["policy_version"],
                        "clause": e["clause"], "quote": e["quote"], "approved_by": e["by"], "approved_on": e["at"][:10],
                        "text": f"Set by {e['policy_title']} v{e['policy_version']}, clause {e['clause']}: ‘{e['quote']}’{ed}"}
            return {"kind": "manual", "owner": row["owner"], "by": e["by"], "date": e["at"][:10],
                    "note": e.get("note", ""), "text": f"Set manually by {e['by']} on {e['at'][:10]} ({e.get('note') or 'policy review'})"}
    by, date = _last_change(row)
    return {"kind": "manual", "owner": row["owner"], "by": by, "date": date,
            "text": f"Set manually by {row['owner']}{'' if by in ('', row['owner']) else ' (' + by + ')'} on {date}"}


_VCACHE: dict[str, tuple[Any, list[dict[str, Any]]]] = {}


def _cached_versions(table: str) -> list[dict[str, Any]]:
    d = paths.VAR / "params" / table if table != "policy_params" else _extra_dir()
    stamp = tuple(sorted((q.name, q.stat().st_mtime_ns) for q in d.glob("v*.json"))) if d.exists() else ()
    hit = _VCACHE.get(table)
    if hit and hit[0] == stamp:
        return hit[1]
    vs = _versions_of(table)
    _VCACHE[table] = (stamp, vs)
    return vs


def _pick(table: str, rows: Any, key: str) -> Any:
    if table == "risk_appetite":
        r = next((x for x in rows if x.get("name") == key), None)
        return r.get(_appetite_field(r)) if r else None
    if table == "doa":
        return [{"level": r["level"], "max_exposure": r["max_exposure"], "min_rating": r.get("min_rating")} for r in rows]
    if table == "market_bounds":
        return {b: v["margin_bps"] for b, v in rows["by_bucket"].items()}
    if table == "pd_master_scale" or not key:
        return rows
    return rows.get(key) if isinstance(rows, dict) else None


def _last_change(row: dict[str, Any]) -> tuple[str, str]:
    """Who set the value in force and when: the version where it last changed (the seed's approver for a seeded value)."""
    vs = _cached_versions(row["table"])
    if not vs:
        return row["owner"], row["effective_from"]
    cur = _pick(row["table"], vs[-1]["rows"], row["key"])
    at = vs[-1]
    for v in reversed(vs):
        if _same(_pick(row["table"], v["rows"], row["key"]), cur):
            at = v
        else:
            break
    ed = at.get("edited") or {}
    return ed.get("by") or at.get("approved_by") or row["owner"], at.get("effective_from") or row["effective_from"]


def parameter_rows() -> list[dict[str, Any]]:
    """Every parameter with its provenance: what the Parameters page shows and the Excel's first sheets hold."""
    led = _ledger_rows()
    out = []
    for u in universe():
        p = provenance(u, led)
        out.append({**u, "provenance": p})
    return out


# ------------------------------------------------------------------ upload and review (I2)

def _lines_of(name: str, data: bytes) -> list[str]:
    from backend.dealdesk.house_style.onboarding import learn as L
    try:
        if name.lower().endswith(".docx"):
            return [x[0] for k, x in L._docx_blocks(data) if k == "p"]
        return [ln.strip().lstrip("# ").strip() for ln in L.text_of_bytes(name, data).splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001 - an unreadable file is refused by the learner with its own message
        return []


def _title_of(name: str, lines: list[str]) -> str:
    """The policy's title: the first short line naming a policy (with the bank's name before it), else the file name."""
    head = [ln for ln in lines[:8] if 4 <= len(ln) <= 90 and not re.match(r"^\d", ln)]
    for ln in head:
        if re.search(r"\bpolicy\b", ln, re.I):
            return ln
    stem = re.sub(r"\.[^.]+$", "", name)
    return re.sub(r"[_-]+", " ", stem).strip() or "Credit policy"


def _doc_version(lines: list[str]) -> str:
    for ln in lines[:12]:
        m = re.search(r"\bVersion\s+(\d+(?:\.\d+)*)", ln, re.I)
        if m:
            return m.group(1)
    return ""


def _issuer(lines: list[str], title: str) -> str:
    for ln in lines[:4]:
        if ln != title and 4 <= len(ln) <= 80 and re.search(r"\b(Bank|PJSC|PSC|Ltd|LLC)\b", ln):
            return ln
    return ""


def _effective(text: str) -> str:
    m = re.search(r"[Ee]ffective(?: from| date|:)?\s*(?:on\s*)?(\d{1,2} [A-Z][a-z]+ \d{4}|\d{4}-\d{2}-\d{2})", text)
    if not m:
        return ""
    s = m.group(1)
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _slug(title: str, issuer: str = "") -> str:
    """The policy's id: issuer and title, so two banks' "Credit Policy" files never share a version history."""
    words = re.sub(r"\b(PJSC|PSC|LLC|LTD|SAOG|QPSC|BSC)\b", "", f"{issuer} {title}".upper())
    return "POL-" + (re.sub(r"[^A-Z0-9]+", "-", words).strip("-")[:48].strip("-") or "POLICY")


_P6_TABLE = {"desk": desk_params.NAME}


def _target(p: dict[str, Any]) -> str:
    t = _P6_TABLE.get(p["table"], p["table"])
    if t == "doa":
        return "doa.rows"
    if t == "market_bounds":
        return "market_bounds.by_bucket"
    return f"{t}.{p['row']}"


def _proposal_unit(u: dict[str, Any], p: dict[str, Any]) -> str:
    if u["unit"] == "number_map" and p["row"] == "tenor_cap_years":
        return "years"
    return u["unit"]


def review(session: dict[str, Any]) -> list[dict[str, Any]]:
    """The review table: one row per parameter (found / not found) plus one per new threshold or condition."""
    uni = {u["id"]: u for u in universe() if u["group"] != GROUP_EXTRA}
    found: dict[str, list[dict[str, Any]]] = {}
    new = []
    for it in session["items"]:
        p = it.get("param")
        if p and _target(p) in uni:
            u = uni[_target(p)]
            sub = p["field"] if (p["table"] == "desk" and isinstance(u["value"], dict) and p["field"] not in ("value", "")) else ""
            change = p.get("change", "")
            if u["table"] in ("doa", "market_bounds", desk_params.NAME, "risk_appetite"):
                # what approving would really do: apply the proposal to the rows in force (a DoA level the policy leaves
                # open keeps its value, so the matrix can be "same" although the lists differ)
                try:
                    cur = _table_meta(u["table"])["rows"]
                    if _same(_apply(u["table"], cur, u["key"], p["field"], sub, p.get("proposed")), cur):
                        change = "same"
                    elif change == "same":
                        change = "changed"
                except (KeyError, StopIteration, TypeError, AttributeError):
                    pass
            found.setdefault(u["id"], []).append({
                "item_id": it["id"], "field": p["field"], "subfield": sub, "proposed": p.get("proposed"), "in_force": p.get("in_force"),
                "display": display(p.get("proposed"), _proposal_unit(u, p) if sub else u["unit"]),
                "in_force_display": display(p.get("in_force"), _proposal_unit(u, p) if sub else u["unit"]),
                "change": change, "conversion": p.get("conversion", ""), "clause": it["clause"], "quote": it["quote"],
                "label": it["label"], "conflict": it.get("conflict")})
        elif it["type"] in ("threshold", "condition"):
            new.append(it)
    rows = []
    for uid, u in uni.items():
        base = {k: u[k] for k in ("id", "group", "table", "key", "field", "label", "unit", "display", "version", "effective_from", "owner", "value")}
        if uid in found:
            props = found[uid]
            changed = any(x["change"] not in ("same",) for x in props)
            rows.append({**base, "status": "found", "proposals": props, "change": "same" if not changed else
                         next(x["change"] for x in props if x["change"] != "same"), "decision": "accept",
                         "options": ["accept", "edit", "keep"] if len(props) == 1 and isinstance(props[0]["proposed"], (int, float)) else ["accept", "keep"]})
        else:
            rows.append({**base, "status": "not_found", "proposals": [], "change": "", "decision": "keep",
                         "options": ["keep", "define"] if u["editable"] else ["keep"]})
    for it in new:
        rows.append({"id": f"new.{it['id']}", "group": GROUP_EXTRA, "table": "policy_params", "key": it["metric"], "field": "",
                     "label": it["label"], "unit": it.get("unit", ""), "display": it.get("value_text") or display(it.get("value"), it.get("unit", "")),
                     "version": "", "effective_from": "", "owner": "Risk", "status": "new", "change": "new", "decision": "skip",
                     "item_id": it["id"], "clause": it["clause"], "quote": it["quote"], "has_rule": bool(it.get("rule")),
                     "checkability": it.get("checkability", ""), "value": it.get("value"),
                     "options": ["skip", "add_parameter"] + (["add_rule"] if it.get("rule") else []), "proposals": []})
    order = {"found": 0, "new": 1, "not_found": 2}
    rows.sort(key=lambda r: (order[r["status"]], r["group"] != GROUP_APPETITE, r["label"]))
    return rows


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    f = [r for r in rows if r["status"] == "found"]
    n = [r for r in rows if r["status"] == "not_found"]
    w = [r for r in rows if r["status"] == "new"]
    ch = [r for r in f if r["change"] != "same"]
    text = (f"The policy sets {len(f)} of {len(f) + len(n)} parameters ({len(ch)} would change, {len(f) - len(ch)} already match); "
            f"{len(n)} are not in the policy and keep their value unless you define one; {len(w)} thresholds or conditions are new. "
            "Nothing changes until you approve.")
    return {"found": len(f), "changes": len(ch), "same": len(f) - len(ch), "not_found": len(n), "new": len(w), "text": text}


def upload(name: str, data: bytes, by: str = "") -> dict[str, Any]:
    """Learn a policy (P6) and prepare its review. Nothing in the parameter tables changes."""
    from backend.dealdesk.house_style.onboarding import service as svc
    if not name.lower().endswith(FORMATS):
        raise ValueError(f"{name}: upload .docx, .pdf, .md or .txt.")
    latest = paths.VAR / pathlib.PurePosixPath(P6_LATEST).relative_to("var/dealdesk")
    before = latest.read_bytes() if latest.exists() else None
    sha = hashlib.sha256(data).hexdigest()
    same = next((r for r in _index() if r.get("sha256") == sha and r["status"] == "pending"), None)
    if same is not None:  # the same file is already awaiting approval: one review, not two
        return same
    try:
        s = svc.learn((name, data), [], by=by or "", save=True)
    except ValueError:
        raise
    except Exception as e:  # noqa: BLE001 - a corrupt or unreadable file is the uploader's to fix: a message, not a 500
        raise ValueError(f"{name} could not be read as a policy ({type(e).__name__}). Upload a .docx, a text PDF, .md or .txt.") from None
    # the session is kept (P6's maker-checker and "add as review rule" use it), but "Learn from documents" keeps showing
    # its own latest session: a policy uploaded here is not a memo-learning run
    if before is not None:
        latest.write_bytes(before)
    elif latest.exists():
        latest.unlink()
    lines = _lines_of(name, data)
    title = _title_of(name, lines)
    text = " ".join(lines[:40])
    rows = review(s)
    with _LOCK:
        idx = _index()
        pid = _slug(title, _issuer(lines, title))
        prev = [r for r in idx if r["policy_id"] == pid]
        ver = (max(r["version"] for r in prev) + 1) if prev else 1
        ext = name.rsplit(".", 1)[-1].lower()
        orig = root() / pid / f"v{ver}" / f"original.{ext}"
        orig.parent.mkdir(parents=True, exist_ok=True)
        orig.write_bytes(data)
        rec = {"policy_id": pid, "version": ver, "title": title, "original_name": name, "format": ext,
               "sha256": sha, "document_version": _doc_version(lines),
               "issuer": _issuer(lines, title), "effective_date": _effective(text) or _now().date().isoformat(),
               "uploaded_by": by or "", "uploaded_at": _iso(), "status": "pending", "session_id": s["session_id"],
               "clauses": sum(d.get("clauses", 0) for d in s["documents"] if d["kind"] == "policy"),
               "tables": sum(d.get("tables", 0) for d in s["documents"] if d["kind"] == "policy"),
               "conflicts": len(s["conflicts"]), "review": rows, "summary": summary(rows), "decided_by": "", "decided_at": "",
               "param_versions": [], "note": ""}
        idx.append(rec)
        _save_index(idx)
    _publish_policies(rec)
    return rec


def upload_sample() -> dict[str, Any]:
    """Session O's fictional policy (Sandstone Harbour Bank PJSC), uploaded by the sample maker so a person can check it."""
    from backend.dealdesk.house_style.onboarding import demo_policy
    if not demo_policy.OUT.exists():
        demo_policy.write()
    return upload(demo_policy.OUT.name, demo_policy.OUT.read_bytes(), by=SAMPLE_MAKER)


def _external() -> list[dict[str, Any]]:
    """Policies Data Domains holds that were not uploaded here (Session E's seed, a trial version from "Try it on your
    documents"): read through E's reader, shown in the library read-only (no review, nothing to approve)."""
    try:
        from backend.dealdesk.data import dd_read
        rows = dd_read("dd_policy")
    except Exception:  # noqa: BLE001 - without E's data layer the library is the uploads alone
        return []
    mine = {(r["policy_id"], int(r["version"])) for r in _index()}
    out = []
    for r in rows:
        if (r["policy_id"], int(r["version"])) in mine:
            continue
        src = str(r.get("source_file") or "")
        out.append({"policy_id": r["policy_id"], "version": int(r["version"]), "title": r.get("title") or r["policy_id"],
                    "original_name": src.rsplit("/", 1)[-1] or f"{r['policy_id']}.docx", "format": (src.rsplit(".", 1)[-1] or "docx").lower(),
                    "sha256": "", "effective_date": r.get("effective_date") or "", "uploaded_by": r.get("uploaded_by") or "",
                    "uploaded_at": r.get("uploaded_at") or "", "status": r.get("status") or "", "session_id": "",
                    "clauses": int(r.get("clauses_n") or 0), "tables": 0, "conflicts": 0, "review": [], "issuer": "", "document_version": "",
                    "summary": {"found": 0, "changes": 0, "same": 0, "not_found": 0, "new": 0, "text": r.get("summary") or ""},
                    "decided_by": "", "decided_at": "", "param_versions": [], "note": "", "external": True, "source_file": src})
    return out


def listing() -> list[dict[str, Any]]:
    """The library, newest first: every upload here plus the policies Data Domains holds from elsewhere."""
    rows = _index() + _external()
    return [{k: v for k, v in r.items() if k != "review"} for r in sorted(rows, key=lambda r: r["uploaded_at"], reverse=True)]


def get(policy_id: str, version: int) -> dict[str, Any]:
    for r in _index() + _external():
        if r["policy_id"] == policy_id and int(r["version"]) == int(version):
            return r
    raise NotFound(f"No policy {policy_id} v{version}.")


def viewer(policy_id: str, version: int) -> dict[str, Any]:
    """The policy's text for the viewer: its numbered clauses by section and its tables, as read from the upload."""
    from backend.dealdesk.house_style.onboarding import learn as L
    rec = get(policy_id, version)
    data = original(policy_id, version)[1]
    d = L.read_document(rec["original_name"], data)
    sections: list[dict[str, Any]] = []
    for c in d["clauses"]:
        key = c.get("section") or ""
        if not sections or sections[-1]["section"] != key:
            sections.append({"section": key, "title": c.get("section_title") or "", "clauses": []})
        sections[-1]["clauses"].append({"clause": c["clause"], "text": c["text"]})
    return {"policy_id": policy_id, "version": int(version), "title": rec["title"], "sections": sections,
            "tables": [{"table": t["table"], "caption": t["caption"], "header": t["header"], "rows": t["rows"]} for t in d["tables"]]}


def original(policy_id: str, version: int) -> tuple[str, bytes]:
    rec = get(policy_id, version)
    if rec.get("external"):
        f = (paths.V5 / rec["source_file"]).resolve()
        allowed = [(paths.V5 / d).resolve() for d in ("data", "demo_inputs")]
        if not any(a in f.parents for a in allowed) or not f.is_file():
            raise NotFound(f"The original of {policy_id} v{version} is not in this deployment.")
        return rec["original_name"], f.read_bytes()
    f = root() / policy_id / f"v{int(version)}" / f"original.{rec['format']}"
    if not f.exists():
        raise NotFound(f"The original of {policy_id} v{version} is missing.")
    return rec["original_name"], f.read_bytes()


def document_docx(policy_id: str, version: int, generated_by: str = "") -> tuple[str, bytes]:
    """The .docx download: a Word upload as uploaded; a PDF, Markdown or text upload rebuilt as Word in house style."""
    rec = get(policy_id, version)
    name, data = original(policy_id, version)
    base = re.sub(r"\.[^.]+$", "", name)
    if rec["format"] == "docx":
        return f"{base}.docx", data
    from backend.house_style import Meta
    from backend.house_style import docx as hd
    v = viewer(policy_id, version)
    meta = Meta(rec["title"], book="corporate", subject=f"Version {rec['version']} · effective {rec['effective_date']}",
                generated_by=generated_by, reference=f"{policy_id} v{rec['version']}")
    doc = hd.document(meta, kind="Credit policy", subtitle=f"Converted from {name} (the original is kept in the policy library)",
                      details=[("Uploaded by", rec["uploaded_by"] or "–"), ("Uploaded", rec["uploaded_at"][:10]), ("Status", rec["status"])])
    hd.heading(doc, "About this copy", 1)
    hd.table(doc, ["Item", "Value"], [["Policy", rec["title"]], ["Issuer", rec.get("issuer") or "–"],
                                      ["Document version", rec.get("document_version") or "–"], ["Library version", f"v{rec['version']}"],
                                      ["Effective", rec["effective_date"]], ["Original file", name], ["Numbered clauses", str(rec["clauses"])]])
    hd.note(doc, "Converted from the uploaded file: numbered clauses and tables as read; layout, images and signatures are in the original.")
    for s in v["sections"]:
        hd.heading(doc,f"{s['section']}. {s['title']}".strip(". ") if s["section"] else (s["title"] or "Clauses"), 1)
        for c in s["clauses"]:
            hd.para(doc, f"**{c['clause']}** {c['text']}")
    for t in v["tables"]:
        hd.heading(doc, t["caption"] or t["table"], 2)
        hd.table(doc, t["header"], t["rows"])
    return f"{base}.docx", hd.to_bytes(doc)


# ------------------------------------------------------------------ approve / reject

def _apply(table: str, rows: Any, key: str, field: str, subfield: str, value: Any) -> Any:
    """`rows` with one value set, in the live schema of each table."""
    r = copy.deepcopy(rows)
    if table == desk_params.NAME:
        if subfield and isinstance(r.get(key), dict):
            r[key][subfield] = value
        else:
            r[key] = value
    elif table == "risk_appetite":
        row = next(x for x in r if x["name"] == key)
        row[field or _appetite_field(row)] = value
    elif table == "doa":
        for lv in value:
            row = next((x for x in r if x["level"].lower() == str(lv["level"]).lower()), None)
            if row is not None and lv.get("max_exposure") is not None:
                row["max_exposure"] = lv["max_exposure"]
            if row is not None and lv.get("min_rating"):
                row["min_rating"] = lv["min_rating"]
    elif table == "market_bounds":
        for b, rng in value.items():
            if b in r["by_bucket"]:
                r["by_bucket"][b]["margin_bps"] = list(rng)
    else:
        r[key] = value
    return r


def _check_desk(rows: dict[str, Any]) -> None:
    """desk_params.edit's own checks, before anything is written."""
    errs = []
    if not 0 <= float(rows.get("corporate_tax", -1)) < 0.5:
        errs.append("corporate_tax must be in [0, 50%)")
    if any(not (0 <= float(v) < 0.3) for v in rows.get("deposit_ftp_credit", {}).values()):
        errs.append("deposit FTP credit rates must be in [0, 30%)")
    if float(rows.get("max_leverage", 0)) <= 0:
        errs.append("max_leverage must be positive")
    if errs:
        raise params.ParamError(desk_params.NAME, errs)


def _coerce_define(u: dict[str, Any], value: Any) -> Any:
    """A value defined at the review, checked against the shape of the value in force: a number for a number, a rating
    for a rating, and for a map only its own keys (merged into the map in force, so no key is dropped)."""
    cur = u["value"]
    label = u["label"]

    def num(x: Any) -> float:
        if isinstance(x, bool):
            raise ValueError(f"{label}: {x!r} is not a number.")
        try:
            return float(x)
        except (TypeError, ValueError):
            raise ValueError(f"{label}: {x!r} is not a number.") from None

    if isinstance(cur, bool) or cur is None:
        raise ValueError(f"{label} cannot be defined here.")
    if isinstance(cur, (int, float)):
        return num(value)
    if isinstance(cur, str):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label}: type a value such as {cur!r}.")
        return value.strip()
    if isinstance(cur, dict) and "regulatory" in cur:
        v = value.get("regulatory") if isinstance(value, dict) else value
        r = num(v)
        if not 0 <= r <= 1:
            raise ValueError(f"{label}: a CCF is between 0% and 100%.")
        return {"regulatory": r, "economic": r}
    if isinstance(cur, dict) and all(not isinstance(v, (dict, list)) for v in cur.values()):
        if not isinstance(value, dict) or not value:
            raise ValueError(f"{label}: give one “name: value” per line.")
        bad = [k for k in value if k not in cur]
        if bad:
            raise ValueError(f"{label}: {', '.join(map(str, bad))} not in this parameter (it has {', '.join(map(str, cur))}).")
        out = dict(cur)
        for k, v in value.items():
            out[k] = v.strip() if isinstance(cur[k], str) and isinstance(v, str) else num(v)
        return out
    raise ValueError(f"{label} is a table; change it in its owner's settings.")


def _number(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{v!r} is not a number.") from None


def approve(policy_id: str, version: int, decisions: dict[str, dict[str, Any]] | None = None, by: str = "",
            role: str = "") -> dict[str, Any]:
    """Apply the reviewed policy: one new version per changed table, with provenance. Returns the updated record."""
    from backend.dealdesk.house_style.onboarding import service as svc
    decisions = decisions or {}
    with _LOCK:
        idx = _index()
        rec = next((r for r in idx if r["policy_id"] == policy_id and int(r["version"]) == int(version)), None)
        if rec is None:
            raise NotFound(f"No policy {policy_id} v{version}.")
        if rec["status"] != "pending":
            raise Conflict(f"{rec['title']} v{version} is already {rec['status']}.")
        newer = [r for r in idx if r["policy_id"] == policy_id and int(r["version"]) > int(version) and r["status"] in ("active", "superseded")]
        if newer:
            raise Conflict(f"{rec['title']} v{max(int(r['version']) for r in newer)} is already approved; v{version} cannot replace it. "
                           "Reject this upload, or upload the policy again.")
        by = by or "checker"
        admin = role.lower() in ("admin", "administrator")
        if rec["uploaded_by"] and by == rec["uploaded_by"] and not admin:
            raise Conflict("Maker-checker: the person who uploaded the policy cannot approve it.")
        live = {u["id"]: u for u in universe()}
        changes: dict[str, list[dict[str, Any]]] = {}
        added_params, added_rules, kept, notes = [], [], [], []
        for row in rec["review"]:
            d = decisions.get(row["id"]) or {}
            act = d.get("action") or row["decision"]
            if act not in row["options"]:
                raise ValueError(f"{row['label']}: '{act}' is not one of {row['options']}.")
            row["decision"] = act
            if row["status"] == "found" and act in ("accept", "edit"):
                u = live[row["id"]]
                for p in row["proposals"]:
                    val = p["proposed"]
                    edited_from = None
                    if act == "edit":
                        val = _number(d.get("value"))
                        row["edited_value"] = val
                        edited_from = p["proposed"]
                    changes.setdefault(u["table"], []).append({"row": row, "u": u, "field": p["field"], "subfield": p["subfield"], "value": val,
                                                               "source": "policy", "clause": p["clause"], "quote": p["quote"],
                                                               "edited_from": edited_from, "unit": u["unit"]})
            elif row["status"] == "not_found" and act == "define":
                if "value" not in d:
                    raise ValueError(f"{row['label']}: define needs a value.")
                u = live[row["id"]]
                d = {**d, "value": _coerce_define(u, d["value"])}
                changes.setdefault(u["table"], []).append({"row": row, "u": u, "field": u["field"], "subfield": "", "value": d["value"],
                                                           "source": "manual", "clause": "", "quote": "", "edited_from": None,
                                                           "unit": u["unit"]})
                row["defined_value"] = d["value"]
            elif row["status"] == "new" and act == "add_parameter":
                added_params.append(row)
            elif row["status"] == "new" and act == "add_rule":
                added_rules.append(row)
            else:
                kept.append(row["id"])
        # build and check every table first, then write: an error leaves every table and the policy as they were
        reason = f"{rec['title']} v{rec['version']} approved by {by}"
        before = {t: copy.deepcopy(_table_meta(t)["rows"]) for t in changes}
        built: dict[str, Any] = {}
        for t, chs in changes.items():
            rows = copy.deepcopy(before[t])
            for c in chs:
                try:
                    rows = _apply(t, rows, c["u"]["key"], c["field"], c["subfield"], c["value"])
                except (TypeError, KeyError, StopIteration, AttributeError, ValueError) as e:
                    raise ValueError(f"{c['row']['label']}: the value does not fit this parameter ({e}).") from None
                if t == "risk_appetite" and c["source"] == "policy" and not _same(_pick(t, rows, c["u"]["key"]), _pick(t, before[t], c["u"]["key"])):
                    row = next(x for x in rows if x["name"] == c["u"]["key"])  # a value the policy changed now cites it
                    row["basis"] = f"{rec['title']} v{rec['version']}, clause {c['clause']}: {c['quote']}"[:240]
            if t != desk_params.NAME:
                errs = params.validate(t, {**_table_meta(t), "rows": rows})
                if errs:
                    raise params.ParamError(t, errs)
            else:
                _check_desk(rows)
            built[t] = rows
        created, ledger = [], []
        for t, chs in changes.items():
            rows = built[t]
            ver = _table_meta(t)["version"]
            if not _same(rows, before[t]):
                tab = desk_params.edit(rows, by, reason) if t == desk_params.NAME else params.edit(t, rows, by, reason)
                ver = tab["version"]
                created.append({"table": t, "version": tab["version"], "effective_from": tab["effective_from"]})
            for c in chs:
                applied = _pick(t, rows, c["u"]["key"])  # the value as stored, so later reads compare like with like
                if c["subfield"] and isinstance(applied, dict):
                    applied = applied.get(c["subfield"])
                ledger.append({"table": t, "key": c["u"]["key"], "field": c["field"], "subfield": c["subfield"], "value": applied,
                               "version": ver, "source": c["source"], "policy_id": policy_id,
                               "policy_title": rec["title"], "policy_version": rec["version"], "clause": c["clause"],
                               "quote": c["quote"], "by": by, "at": _iso(),
                               "note": "" if c["source"] == "policy" else f"defined at the review of {rec['title']} v{rec['version']}; not in the policy",
                               "label": c["row"]["label"], "edited_from": c["edited_from"], "unit": c["unit"]})
        if added_params:
            ex = extra_table()
            n = int(ex["version"][1:]) + 1
            ex = copy.deepcopy(ex)
            for row in added_params:
                ex["rows"][row["key"]] = {"label": row["label"], "value": row.get("value"), "unit": row.get("unit", ""), "display": row["display"],
                                          "clause": row["clause"], "quote": row["quote"],
                                          "source": f"{rec['title']} v{rec['version']}, clause {row['clause']}"}
            ex.update({"version": f"v{n}", "effective_from": _now().date().isoformat(), "approved_by": by,
                       "edited": {"by": by, "at": _iso(), "reason": reason}})
            _w(_extra_dir() / f"v{n}.json", ex)
            created.append({"table": "policy_params", "version": ex["version"], "effective_from": ex["effective_from"]})
            for row in added_params:
                ledger.append({"table": "policy_params", "key": row["key"], "field": "", "subfield": "", "value": row.get("value"),
                               "version": ex["version"], "source": "policy", "policy_id": policy_id, "policy_title": rec["title"],
                               "policy_version": rec["version"], "clause": row["clause"], "quote": row["quote"], "by": by, "at": _iso(),
                               "label": row["label"]})
        for row in added_rules:
            try:
                out = svc.decide(rec["session_id"], row["item_id"], "accept", by=by, note=reason)
                row["rule_version"] = (out.get("version") or {}).get("version")
            except svc.Conflict as e:  # P6's own maker-checker (same person); recorded, never silent
                notes.append(f"{row['label']}: rule not added ({e})")
        if ledger:
            _ledger().parent.mkdir(parents=True, exist_ok=True)
            with _ledger().open("a") as fh:
                for e in ledger:
                    fh.write(json.dumps(e, default=str, ensure_ascii=False) + "\n")
        for r in idx:
            if r["policy_id"] == policy_id and r is not rec and (r["status"] == "active" or (r["status"] == "pending" and int(r["version"]) < int(version))):
                r["status"] = "superseded"
                r["superseded_by"] = rec["version"]
        rec.update({"status": "active", "decided_by": by, "decided_at": _iso(), "param_versions": created,
                    "rules_added": [r["item_id"] for r in added_rules if r.get("rule_version")], "note": "; ".join(notes),
                    "self_approved": bool(admin and rec["uploaded_by"] and by == rec["uploaded_by"])})
        _save_index(idx)
    _publish_policies()
    _publish_parameters()
    return rec


def reject(policy_id: str, version: int, by: str = "", note: str = "") -> dict[str, Any]:
    with _LOCK:
        idx = _index()
        rec = next((r for r in idx if r["policy_id"] == policy_id and int(r["version"]) == int(version)), None)
        if rec is None:
            raise NotFound(f"No policy {policy_id} v{version}.")
        if rec["status"] != "pending":
            raise Conflict(f"{rec['title']} v{version} is already {rec['status']}.")
        rec.update({"status": "rejected", "decided_by": by or "checker", "decided_at": _iso(), "note": note})
        _save_index(idx)
    _publish_policies()
    return rec


# ------------------------------------------------------------------ the change log (every version of every table)

def _versions_of(table: str) -> list[dict[str, Any]]:
    if table == desk_params.NAME:
        seed, d = copy.deepcopy(desk_params.SEED), paths.VAR / "params" / desk_params.NAME
    elif table == "policy_params":
        seed, d = None, _extra_dir()
    else:
        f = paths.params_dir() / "v1" / f"{table}.json"
        seed, d = json.loads(f.read_text()), paths.VAR / "params" / table
    out = [seed] if seed else []
    if d.exists():
        out += [json.loads(q.read_text()) for q in sorted(d.glob("v*.json"), key=lambda q: int(q.stem[1:]))]
    return out


def change_log() -> list[dict[str, Any]]:
    """Every value that changed between two versions of a parameter table, with who, when, why and the source."""
    led = {(e["table"], e["key"], e["version"]): e for e in _ledger_rows()}
    labels = {(u["table"], u["key"]): (u["label"], u["unit"]) for u in universe()}
    out = []
    for t in sorted({u["table"] for u in universe()} | {desk_params.NAME}):
        vs = _versions_of(t)
        for a, b in zip(vs, vs[1:], strict=False):
            ra, rb = a["rows"], b["rows"]
            if isinstance(rb, list):
                keyf = "name" if rb and "name" in rb[0] else "level"
                pa = {x.get(keyf): x for x in ra}
                pairs = [(x.get(keyf), pa.get(x.get(keyf)), x) for x in rb]
                if t == "doa":
                    pairs = [("rows", ra, rb)] if not _same(ra, rb) else []
            else:
                if t == "market_bounds":
                    pairs = [("by_bucket", {k: v["margin_bps"] for k, v in ra["by_bucket"].items()},
                              {k: v["margin_bps"] for k, v in rb["by_bucket"].items()})]
                else:
                    pairs = [(k, ra.get(k), rb.get(k)) for k in rb]
            ed = b.get("edited") or {}
            for k, old, new in pairs:
                if _same(old, new):
                    continue
                lab, unit = labels.get((t, k), (str(k), ""))
                if t == "risk_appetite" and isinstance(new, dict):
                    f = _appetite_field(new)
                    old, new = (old or {}).get(f), new.get(f)
                    if _same(old, new):
                        continue
                e = led.get((t, k, b["version"]))
                out.append({"at": ed.get("at") or b.get("effective_from", ""), "table": t, "parameter": lab, "key": k,
                            "from": display(old, unit), "to": display(new, unit), "version": b["version"], "previous": a["version"],
                            "effective_from": b.get("effective_from", ""), "by": ed.get("by") or b.get("approved_by", ""),
                            "reason": ed.get("reason", ""),
                            "source": (f"{e['policy_title']} v{e['policy_version']}, clause {e['clause']}" if e and e["source"] == "policy"
                                       else "Manual" + (f" ({e['note']})" if e and e.get("note") else ""))})
    out.sort(key=lambda r: r["at"], reverse=True)
    return out


# ------------------------------------------------------------------ publish to Data Domains (§0, through E's publisher)

def register_rows() -> list[dict[str, Any]]:
    """The policy register (the Excel's sheet 3): every library entry with what its review found and decided."""
    out = []
    for r in listing():
        sm = r.get("summary") or {}
        out.append({"policy_id": r["policy_id"], "policy_version": int(r["version"]), "title": r["title"], "effective_date": r["effective_date"],
                    "uploaded_by": r["uploaded_by"], "uploaded_at": r["uploaded_at"], "status": r["status"], "original_format": r["format"],
                    "original_name": r["original_name"], "clauses": int(r.get("clauses") or 0),
                    "params_found": int(sm.get("found") or 0), "params_changed": int(sm.get("changes") or 0),
                    "params_not_found": int(sm.get("not_found") or 0), "new_items": int(sm.get("new") or 0),
                    "decided_by": r.get("decided_by") or "", "decided_at": r.get("decided_at") or "",
                    "param_versions": ", ".join(f"{x['table']} {x['version']}" for x in r.get("param_versions") or [])})
    return out


def _api_path(pid: str, v: int, what: str) -> str:
    return f"/api/v1/dealdesk/policies/{pid}/{v}/{what}"


def policy_relation_rows() -> list[dict[str, Any]]:
    """`dd_policy` rows in the contract's columns, for every upload in the library."""
    return [{"policy_id": r["policy_id"], "version": int(r["version"]), "title": r["title"], "effective_date": r["effective_date"],
             "uploaded_by": r["uploaded_by"], "uploaded_at": r["uploaded_at"], "status": r["status"],
             "source_file": f"{INDEX_FILE.rsplit('/', 1)[0]}/{r['policy_id']}/v{int(r['version'])}/original.{r['format']}",
             "docx_file": _api_path(r["policy_id"], int(r["version"]), "document.docx"), "clauses_n": int(r["clauses"]),
             "summary": r["summary"]["text"][:400]} for r in _index()]


def clause_relation_rows(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """`dd_policy_clause` rows for one upload: every numbered clause and table, with the parameter it sets (when one)."""
    sets: dict[str, tuple[str, str, str]] = {}
    for row in rec.get("review") or []:
        for pr in row.get("proposals") or []:
            key = f"{row['key']}.{pr['subfield'] or pr['field']}" if (pr["subfield"] or pr["field"]) and row["table"] != "doa" else row["key"]
            val = pr["proposed"] if isinstance(pr["proposed"], str) else json.dumps(pr["proposed"], default=str)
            sets.setdefault(pr["clause"], (row["table"], key, val[:400]))
    v = viewer(rec["policy_id"], rec["version"])
    out, seen = [], set()
    for sec in v["sections"]:
        for c in sec["clauses"]:
            if c["clause"] in seen:
                continue
            seen.add(c["clause"])
            t, k, val = sets.get(c["clause"], ("", "", ""))
            out.append({"policy_id": rec["policy_id"], "version": int(rec["version"]), "clause": c["clause"],
                        "heading": f"{sec['section']}. {sec['title']}".strip(". ") if sec["section"] else sec["title"],
                        "quote": c["text"][:400], "sets_table": t, "sets_key": k, "sets_value": val})
    for tb in v["tables"]:
        if tb["table"] in seen:
            continue
        seen.add(tb["table"])
        t, k, val = sets.get(tb["table"], ("", "", ""))
        body = "; ".join(" ".join(x for x in r if x) for r in tb["rows"])
        out.append({"policy_id": rec["policy_id"], "version": int(rec["version"]), "clause": tb["table"], "heading": tb["caption"][:200],
                    "quote": body[:400], "sets_table": t, "sets_key": k, "sets_value": val})
    return out


def _dd_parameters() -> list[dict[str, Any]]:
    try:
        from backend.dealdesk.data import dd_read
        return dd_read("dd_parameter", columns=["table_name", "param_key", "version"])
    except Exception:  # noqa: BLE001 - before E's readers: the universe rows alone
        return []


def _flat_owner(rows_by_table: dict[str, list[dict[str, Any]]], table: str, param_key: str) -> dict[str, Any] | None:
    """The universe row a flattened dd_parameter key belongs to ("dscr.limit" -> risk_appetite.dscr; "hurdle.SME" -> returns.hurdle)."""
    cand = rows_by_table.get(table) or []
    if table == "doa":
        return cand[0] if cand else None
    best = None
    for u in cand:
        k = u["key"] or ""
        if not k or param_key == k or param_key.startswith(k + "."):
            if best is None or len(k) > len(best["key"] or ""):
                best = u
    return best


_MISSING = object()


def _flat(obj: Any, prefix: str = "") -> dict[str, Any]:
    """A parameter table's rows flattened the way dd_parameter names its keys: dicts by key, rows by name / level / rating,
    lists of numbers as one value ("by_bucket.IG.margin_bps", "dscr.limit", "Chief Risk Officer.max_exposure")."""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flat(v, f"{prefix}{k}."))
    elif isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        idk = next((k for k in ("name", "level", "rating", "from", "key", "id") if all(k in x for x in obj)), None)
        for i, x in enumerate(obj):
            out.update(_flat(x, f"{prefix}{x[idk] if idk else i}."))
    else:
        out[prefix[:-1]] = obj
    return out


def provenance_relation_rows() -> list[dict[str, Any]]:
    """`dd_parameter_provenance` rows: one per dd_parameter value (joins on table_name + param_key), plus the UAE desk
    table and the parameters a policy added (not in the R11 dd_parameter)."""
    rows = parameter_rows()
    by_table: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_table.setdefault(r["table"], []).append(r)
    out, seen = [], set()

    def add(table: str, key: str, u: dict[str, Any] | None, version: str, limit_field: bool) -> None:
        if (table, key) in seen:
            return
        seen.add((table, key))
        p = (u or {}).get("provenance") if limit_field else None
        meta_v = (u or {}).get("version") or version
        if p and p["kind"] == "policy":
            out.append({"table_name": table, "param_key": key, "param_version": meta_v, "source_kind": "policy", "policy_id": p["policy_id"],
                        "policy_version": int(p["policy_version"]), "clause": p["clause"], "quote": (p["quote"] or "")[:400],
                        "set_by": p.get("approved_by") or "", "set_on": (p.get("approved_on") or "")[:10]})
            return
        try:
            vs = _cached_versions(table)
        except (KeyError, FileNotFoundError):
            vs = []
        cur = vs[-1] if vs else {"version": version, "approved_by": (u or {}).get("owner", ""), "effective_from": "", "rows": {}}
        # the version where this value last changed (flattened as dd_parameter names it); unchanged since the seed -> "seed"
        at = cur
        if vs:
            now = _flat(vs[-1]["rows"]).get(key, _MISSING)
            for v in reversed(vs):
                if _same(_flat(v["rows"]).get(key, _MISSING), now):
                    at = v
                else:
                    break
        seed = bool(vs) and at is vs[0] and table != "policy_params"
        ed = at.get("edited") or {}
        out.append({"table_name": table, "param_key": key, "param_version": str(cur.get("version") or version),
                    "source_kind": "seed" if seed else "manual", "policy_id": None, "policy_version": None, "clause": None, "quote": None,
                    "set_by": ed.get("by") or at.get("approved_by") or (u or {}).get("owner", ""), "set_on": str(at.get("effective_from") or "")[:10]})

    for d in _dd_parameters():
        u = _flat_owner(by_table, d["table_name"], d["param_key"])
        lf = bool(u) and (d["table_name"] in ("doa", "market_bounds") and (d["param_key"].endswith((".max_exposure", ".min_rating")) or ".margin_bps" in d["param_key"])
                          or d["table_name"] not in ("risk_appetite", "doa", "market_bounds")
                          or d["param_key"].startswith(f"{u['key']}.{u['field']}"))
        add(d["table_name"], d["param_key"], u, str(d.get("version") or "v1"), lf)
    for r in rows:
        if r["table"] in (desk_params.NAME, "policy_params"):
            add(r["table"], r["key"], r, r["version"], True)
    return out


def _publisher():
    try:
        from backend.dealdesk import data as dd_data  # Session E's readers and publisher
        return dd_data.publish
    except Exception:  # noqa: BLE001 - without E's data layer the rows wait in var/dealdesk/policies/pending
        return None


def _publish(relation: str, rows: list[dict[str, Any]], **kw: Any) -> str:
    """Publish through E's publisher (versioned, manifest updated). A failure never blocks a parameter decision: the rows
    are kept under var/dealdesk/policies/pending/ and the next decision publishes again."""
    pub = _publisher()
    if pub is not None:
        try:
            pub(relation, rows, actor="G", **kw)
            p = root() / "pending" / f"{relation}.json"
            if p.exists():
                p.unlink()
            return "published"
        except Exception as e:  # noqa: BLE001
            _w(root() / "pending" / f"{relation}.json", {"error": str(e), "rows": rows})
            return f"pending ({e})"
    _w(root() / "pending" / f"{relation}.json", {"rows": rows})
    return "pending"


def _publish_policies(rec: dict[str, Any] | None = None) -> dict[str, str]:
    out = {"dd_policy": _publish("dd_policy", policy_relation_rows())} if _index() else {}
    if rec is not None:
        out["dd_policy_clause"] = _publish("dd_policy_clause", clause_relation_rows(rec), mode="replace_where",
                                           where={"policy_id": rec["policy_id"], "version": int(rec["version"])})
    return out


def _publish_parameters() -> str:
    return _publish("dd_parameter_provenance", provenance_relation_rows())


# ------------------------------------------------------------------ the Excel export (I5)

def export_xlsx(generated_by: str = "") -> bytes:
    from backend.house_style import Meta
    from backend.house_style import xlsx as hx
    from backend.house_style.xlsx import Col
    meta = Meta("Deal Desk parameters", book="corporate", period=paths.AS_OF, subject="Parameters, risk appetite, policies and changes",
                generated_by=generated_by)
    wb = hx.workbook(meta)
    rows = parameter_rows()
    pol = [r for r in rows]

    def src(r: dict[str, Any]) -> dict[str, Any]:
        p = r["provenance"]
        return {"source": "Policy" if p["kind"] == "policy" else "Manual", "policy": p.get("policy", ""),
                "policy_version": f"v{p['policy_version']}" if p.get("policy_version") else "", "clause": p.get("clause", ""),
                "quote": p.get("quote", "") or p.get("text", "")}

    hx.table_sheet(wb, "Parameters", meta, [
        Col("label", "Parameter"), Col("group", "Group"), Col("display", "Value(s)"), Col("unit_words", "Unit"), Col("version", "Version"),
        Col("effective_from", "Effective date"), Col("owner", "Owner"), Col("source", "Source"), Col("policy", "Source policy"),
        Col("policy_version", "Policy version"), Col("clause", "Clause"), Col("quote", "Quote or set by", width=70)],
        [{**r, "unit_words": UNIT_WORDS.get(r["unit"], r["unit"]), **src(r)} for r in pol if r["group"] != GROUP_APPETITE],
        title="Parameters in force", note="Every Deal Desk parameter with the source that set it: a policy clause, or the person who set it.")
    ra = [r for r in rows if r["group"] == GROUP_APPETITE]
    hx.table_sheet(wb, "Risk appetite", meta, [
        Col("label", "Limit"), Col("kind", "Hard or soft"), Col("appetite_d", "Appetite (green)"), Col("trigger_d", "Trigger (amber)"),
        Col("display", "Limit (red)"), Col("unit_words", "Unit"), Col("version", "Version"), Col("effective_from", "Effective date"),
        Col("source", "Source"), Col("policy", "Source policy"), Col("policy_version", "Policy version"), Col("clause", "Clause"),
        Col("basis", "Basis", width=70)],
        [{**r, "kind": r.get("kind", "").capitalize(), "appetite_d": display(r.get("appetite"), r["unit"]),
          "trigger_d": display(r.get("trigger"), r["unit"]), "unit_words": UNIT_WORDS.get(r["unit"], r["unit"]), **src(r)} for r in ra],
        title="Risk-appetite levels", note="Each limit with its appetite, trigger and limit levels.")
    hx.table_sheet(wb, "Policy register", meta, [
        Col("title", "Policy"), Col("version_d", "Version"), Col("effective_date", "Effective date"), Col("uploaded_by", "Uploaded by"),
        Col("uploaded_on", "Uploaded on"), Col("status_d", "Status"), Col("format_d", "Original format"), Col("params_found", "Parameters found", "int"),
        Col("params_changed", "Parameters changed", "int"), Col("params_not_found", "Not in the policy", "int"),
        Col("new_items", "New thresholds", "int"), Col("decided_by", "Approved or rejected by"), Col("decided_on", "On"),
        Col("param_versions", "Versions created")],
        [{**r, "version_d": f"v{r['policy_version']}", "uploaded_on": r["uploaded_at"][:10], "decided_on": (r["decided_at"] or "")[:10],
          "status_d": r["status"].capitalize(), "format_d": r["original_format"].upper()} for r in register_rows()],
        title="Policy register", empty="(no policy uploaded yet)")
    hx.table_sheet(wb, "Change log", meta, [
        Col("at_d", "When"), Col("parameter", "Parameter"), Col("from", "From"), Col("to", "To"), Col("version", "Version"),
        Col("effective_from", "Effective date"), Col("by", "By"), Col("source", "Source"), Col("reason", "Reason", width=50)],
        [{**r, "at_d": str(r["at"]).replace("T", " ")[:16]} for r in change_log()], title="Change log", empty="(no change since the seed)")
    hx.about_sheet(wb, meta, [("Sheets", "Parameters · Risk appetite · Policy register · Change log"),
                              ("Parameters", len([r for r in rows if r["group"] != GROUP_APPETITE])),
                              ("Risk-appetite limits", len(ra)), ("Policies", len(_index())),
                              ("Parameter version tag", params.version_tag())], index=0)
    return hx.to_bytes(wb)


UNIT_WORDS = {"rate": "%", "rate_map": "% by key", "ccf": "%", "share": "%", "x": "times", "sar m": "SAR m", "bps": "bps",
              "bps_map": "bps by bucket", "years": "years", "years_map": "years by bucket", "number": "number",
              "number_map": "by key", "text_map": "by key", "curve": "% by tenor", "curve_map": "% by tenor", "table": "table",
              "rating": "rating", "index": "index", "doa": "SAR m by level"}


def clause_quote_ok(rec: dict[str, Any]) -> bool:
    """Every found row's quote appears in the uploaded document (a test helper and a UAT check)."""
    from backend.dealdesk.house_style.onboarding import learn as L
    name, data = original(rec["policy_id"], rec["version"])
    txt = " ".join(c["text"] for c in L.read_document(name, data)["clauses"])
    return all(p["quote"][:40] in txt or p["clause"].startswith(("Table", "Appendix")) for r in rec["review"] for p in r["proposals"])
