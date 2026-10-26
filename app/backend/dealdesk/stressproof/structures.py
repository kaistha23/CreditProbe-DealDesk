"""The structure set (K23 (2), K25 (1)): Ask, Recommended, Alternatives and Your structures, each measured once.

Recommended is the Review counter-proposal (the R11 review workspace's first counter-proposal, priced by the
optimiser), else the optimiser's closest structure. Alternatives are the optimiser's other offers (up to two).
Your structures are the ones saved on the deal (role user) and the stress-proofed ones (role stress_proofed), read
from dd_structure_set. Every row carries base RAROC against the hurdle, SVA on one basis, DSCR after the deal,
the smallest covenant headroom, the capacity check and the approval authority (adapters, N2), and whether it can
be recommended, with the reason when it cannot.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import threading
import time
from typing import Any

from backend.dealdesk import engine, optimizer, params
from backend.dealdesk import stress_lab as sl
from backend.dealdesk.stressproof import adapters as AD

ROLE_ORDER = {"ask": 0, "recommended": 1, "alternative": 2, "user": 3, "stress_proofed": 4}
ROLE_GROUP = {"ask": "Ask", "recommended": "Recommended", "alternative": "Alternatives", "user": "Your structures",
              "stress_proofed": "Your structures"}
_LOCK = threading.Lock()
_CACHE: dict[tuple, tuple[float, Any]] = {}
TTL = 900.0


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cached(key: tuple, fn):
    with _LOCK:
        hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    v = fn()
    with _LOCK:
        _CACHE[key] = (time.time(), v)
    return v


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def deal(pid: str) -> dict[str, Any]:
    """The engine proposal for any deal Deal Desk can open (DD, PL and the R12 dd_deal deals)."""
    from backend.dealdesk.stress2 import store
    return store.deal(pid)


def review(pid: str) -> dict[str, Any] | None:
    """The R11 review workspace answer for the deal (findings, DoA, counter-proposals), or None when not reviewable."""
    from backend.dealdesk import review_facts as RF
    from backend.dealdesk import review_workspace as RW
    try:
        if not RF.known(pid):
            return None
        return RW.review(pid)
    except Exception:  # noqa: BLE001 - the flow never fails because the review cannot run
        return None


def with_covenants(p: dict[str, Any], covenants: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not covenants:
        return p
    q = copy.deepcopy(p)
    q["security"]["covenants"] = [dict(c) for c in covenants]
    return q


# ------------------------------------------------------------------ the candidate structures

def _terms_from_changes(p: dict[str, Any], changes: list[dict[str, Any]], structure: dict[str, Any] | None = None) -> dict[str, Any]:
    t = engine.merge_terms(p, None)
    for c in changes or []:
        if c.get("field") in t or c.get("field") in engine.TERM_KEYS:
            t[c["field"]] = c["value"]
    for k in ("amount", "tenor_years", "margin_bps", "commission_bps", "funded_share_pct", "cash_margin_pct", "covenant_package"):
        if structure and structure.get(k) is not None and k in t and k not in {c.get("field") for c in changes or []}:
            if k == "amount" and structure.get("currency") and structure["currency"] != t["currency"]:
                continue
            t[k] = structure[k]
    return t


def _optimiser(pid: str, p: dict[str, Any]) -> dict[str, Any] | None:
    def run():
        try:
            return optimizer.optimize(p)
        except Exception:  # noqa: BLE001
            return None
    return _cached(("opt", pid, params.version_tag()), run)


def candidates(pid: str, p: dict[str, Any] | None = None, rv: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """[{key, label, role, origin, terms, covenants}] in the order Ask, Recommended, Alternatives, Your structures."""
    p = p or deal(pid)
    ask = engine.merge_terms(p, None)
    out = [{"key": "ask", "label": "Ask", "role": "ask", "origin": "As the client requested (the RM's proposal)", "terms": ask, "covenants": None}]
    seen = {json.dumps(ask, sort_keys=True, default=str)}
    cps = ((rv or {}).get("counter") or {}).get("counter_proposals") or []
    opt = _optimiser(pid, p)
    offers: list[tuple[str, dict[str, Any]]] = []
    if opt:
        for title, s in ([("Closest to the ask", opt.get("closest")), ("Maximum value", opt.get("max_sva"))]
                         + [(a.get("label") or "Alternative", a) for a in (opt.get("alternatives") or [])]
                         + [(c.get("label") or "Counter-offer", c) for c in (opt.get("counter_offers") or [])]):
            if s and s.get("terms"):
                offers.append((title, engine.merge_terms(p, s["terms"])))
    co = AD.counter_offer(pid)
    if co:
        out.append({"key": "recommended", "label": "Recommended", "role": "recommended",
                    "origin": f"Review counter-proposal, cured by the findings engine: {co['headline']}", "terms": engine.merge_terms(p, co["terms"]),
                    "covenants": None, "conditions_precedent": [c["cure"] for c in co["cures"] if c.get("cure_kind") == "cp" and c.get("cure")]})
    elif cps:
        cp = cps[0]
        t = _terms_from_changes(p, cp.get("changes") or [], cp.get("structure"))
        out.append({"key": "recommended", "label": "Recommended", "role": "recommended",
                    "origin": f"Review counter-proposal {cp['id']}: {cp['title']}", "terms": t, "covenants": None,
                    "conditions_precedent": cp.get("conditions_precedent") or []})
    elif offers:
        out.append({"key": "recommended", "label": "Recommended", "role": "recommended",
                    "origin": f"Optimiser: {offers[0][0].lower()} (no Review counter-proposal on file)", "terms": offers[0][1], "covenants": None})
    for o in out[1:]:
        seen.add(json.dumps(o["terms"], sort_keys=True, default=str))
    n = 0
    for title, t in offers:
        k = json.dumps(t, sort_keys=True, default=str)
        if k in seen or n >= 4:
            continue
        seen.add(k)
        n += 1
        out.append({"key": f"alternative_{n}", "label": f"Alternative {n}", "role": "alternative", "origin": f"Optimiser: {title}",
                    "terms": t, "covenants": None})
    out = _dedupe(p, out)
    for r in saved(pid):
        if r["role"] in ("user", "stress_proofed"):
            out.append({"key": r["structure_key"], "label": r["label"], "role": r["role"], "origin": r.get("origin") or "",
                        "terms": engine.merge_terms(p, r["terms_json"]), "covenants": r.get("covenants_json") or None})
    return out


def _dedupe(p: dict[str, Any], cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop an alternative that prices the same as a structure above it (same RAROC, SVA and amount)."""
    seen: list[tuple[float, float, float]] = []
    out = []
    for c in cands:
        m = engine.analyse(p, c["terms"])["metrics"]
        sig = (round(m["lifetime_raroc"], 5), round(m["sva"], 4), round(m["amount_sar_mn"], 4))
        if c["role"] == "alternative" and (sig in seen or sum(1 for x in out if x["role"] == "alternative") >= 2):
            continue
        seen.append(sig)
        out.append(c)
    n = 0
    for c in out:
        if c["role"] == "alternative":
            n += 1
            c["key"], c["label"] = f"alternative_{n}", f"Alternative {n}"
    return out


# ------------------------------------------------------------------ measuring one structure

def _hurdle_text(m: dict[str, Any]) -> str:
    return f"RAROC {m['lifetime_raroc'] * 100:.2f}% < {m['hurdle'] * 100:.1f}% hurdle"


def measure(p: dict[str, Any], c: dict[str, Any], rv: dict[str, Any] | None = None) -> dict[str, Any]:
    """One row of the structure set (memoised per deal, structure and parameter version: the engines are deterministic)."""
    key = ("measure", p["proposal_id"], c["key"], c["label"], c["role"], c.get("origin", ""),
           json.dumps([c["terms"], c.get("covenants"), c.get("conditions_precedent")], sort_keys=True, default=str),
           bool(rv), params.version_tag())
    return copy.deepcopy(_cached(key, lambda: _measure(p, c, rv)))


def _measure(p: dict[str, Any], c: dict[str, Any], rv: dict[str, Any] | None = None) -> dict[str, Any]:
    q = with_covenants(p, c.get("covenants"))
    lab = sl.Lab(q, c["terms"], label=c["label"])
    a = lab.base
    m = a["metrics"]
    covs = lab._covenants({"dscr": m["dscr_post"], "debt_ebitda": m["debt_ebitda_post"], "interest_cover": lab.base_r["interest_cover"]})
    heads = [x for x in covs if x.get("headroom") is not None]
    tight = min(heads, key=lambda x: x["headroom"]) if heads else None
    s = AD.sva(a, p["proposal_id"])
    capy = AD.capacity(q, a)
    ap = AD.approval(q, a, rv)
    hard = [x for x in a["constraints"] if x["status"] == "breach" and x["kind"] == "hard"]
    reasons = []
    if not m["clears_hurdle"]:
        reasons.append(_hurdle_text(m))
    for h in hard:
        reasons.append(f"Hard limit breached: {h['label']}")
    if tight and tight["headroom"] < 0:
        reasons.append(f"{tight['type']} covenant breached at base ({_v(tight['value'])} against {_v(tight['threshold'])})")
    if not capy["passes"]:
        reasons.append(f"Ask SAR {capy['ask_sar_mn']:,.1f}m above capacity SAR {capy['capacity_sar_mn']:,.1f}m ({capy['method'].lower()})")
    return {
        "key": c["key"], "label": c["label"], "role": c["role"], "group": ROLE_GROUP[c["role"]], "origin": c.get("origin", ""),
        "terms": a["terms"], "covenants": c.get("covenants"), "conditions_precedent": c.get("conditions_precedent") or [],
        "raroc": m["lifetime_raroc"], "hurdle": m["hurdle"], "clears_hurdle": bool(m["clears_hurdle"]),
        "sva": s["value"], "sva_basis": s["basis"], "sva_label": s["label"], "sva_lifetime": s["lifetime"], "sva_one_year": s["one_year"],
        "dscr": m["dscr_post"], "debt_ebitda": m["debt_ebitda_post"],
        "covenants_base": covs, "covenant_headroom": None if tight is None else tight["headroom"],
        "covenant_tightest": None if tight is None else f"{tight['type']} {_v(tight['value'])} against {_v(tight['threshold'])}",
        "capacity": capy, "approval": ap, "hard_breaches": [h["label"] for h in hard],
        "rwa_y1": m["rwa_y1"], "el_y1": m["el_y1"], "amount_sar_mn": m["amount_sar_mn"],
        "recommendable": not reasons, "not_recommendable_reason": "; ".join(reasons),
        "fails_before_stress": bool(reasons),
        "sources": {"sva": s["source"], "capacity": capy["source"], "approval": ap["source"]},
    }


def _v(x: Any) -> str:
    try:
        return f"{float(x):.2f}x"
    except (TypeError, ValueError):
        return "–"


# ------------------------------------------------------------------ the set, saved structures and the selection

def saved(pid: str) -> list[dict[str, Any]]:
    from backend.dealdesk.data import store
    try:
        return sorted(store.dd_read("dd_structure_set", proposal_id=pid), key=lambda r: (ROLE_ORDER.get(r["role"], 9), r["structure_key"]))
    except Exception:  # noqa: BLE001 - an empty relation reads as no saved structures
        return []


def selected_key(pid: str) -> str | None:
    for r in saved(pid):
        if r.get("selected_flag"):
            return r["structure_key"]
    return None


def structure_set(pid: str) -> dict[str, Any]:
    p = deal(pid)
    rv = review(pid)
    rows = [measure(p, c, rv) for c in candidates(pid, p, rv)]
    sel = selected_key(pid)
    keys = [r["key"] for r in rows]
    default = "recommended" if "recommended" in keys else "ask"
    chosen = sel if sel in keys else default
    for r in rows:
        r["selected"] = r["key"] == chosen
    cur = next(r for r in rows if r["selected"])
    groups = []
    for g in ("Ask", "Recommended", "Alternatives", "Your structures"):
        gr = [r["key"] for r in rows if r["group"] == g]
        groups.append({"group": g, "keys": gr})
    return {"proposal_id": pid, "obligor": p["obligor"]["name"], "rows": rows, "groups": groups, "selected": chosen,
            "selected_by_user": sel == chosen, "default_note": None if sel == chosen else
            ("Recommended (the Review counter-proposal) is selected by default." if chosen == "recommended" else "The ask is selected by default."),
            "bar": bar(cur), "plain_words": plain_words(rows, cur), "regime": AD.regime(),
            "sva_basis": cur["sva_label"]}


def bar(cur: dict[str, Any]) -> dict[str, Any]:
    """The sticky bar: 'Selected: <name> → Recommend', disabled with the reason."""
    return {"label": f"Selected: {cur['label']}", "key": cur["key"], "enabled": cur["recommendable"],
            "reason": "" if cur["recommendable"] else cur["not_recommendable_reason"]}


def plain_words(rows: list[dict[str, Any]], cur: dict[str, Any]) -> list[str]:
    ok = [r for r in rows if r["recommendable"]]
    ask = rows[0]
    out = ["These are the ways this deal could be done: the client's ask, our recommended structure and the alternatives, "
           "each measured the same way."]
    if ask["recommendable"]:
        out.append(f"The ask works as it stands: RAROC {ask['raroc'] * 100:.1f}% against a {ask['hurdle'] * 100:.1f}% hurdle (RAROC = return on the capital the deal uses).")
    else:
        out.append(f"The ask cannot be recommended: {ask['not_recommendable_reason'].split('; ')[0]}.")
    if ok:
        out.append(f"{len(ok)} of {len(rows)} structures can be recommended; {cur['label']} is selected"
                   + ("." if cur["recommendable"] else f" but cannot be recommended ({cur['not_recommendable_reason'].split('; ')[0]})."))
    else:
        out.append("No structure on the list can be recommended yet: stress-proof one, or build your own in Structure it yourself.")
    out.append("Select one row, then Stress it or Recommend it.")
    return out


def _row_out(pid: str, r: dict[str, Any], selected: bool, by: str, at: str) -> dict[str, Any]:
    return {"structure_id": f"{pid}:{r['key']}", "proposal_id": pid, "structure_key": r["key"], "label": r["label"], "role": r["role"],
            "origin": r.get("origin", ""), "terms_json": r["terms"], "covenants_json": r.get("covenants"),
            "raroc_pct": round(r["raroc"] * 100, 6), "hurdle_pct": round(r["hurdle"] * 100, 6), "sva_mn": r["sva"], "sva_basis": r["sva_basis"],
            "dscr_x": None if r["dscr"] is None or r["dscr"] == float("inf") else r["dscr"],
            "covenant_headroom_pct": None if r["covenant_headroom"] is None else r["covenant_headroom"] * 100,
            "capacity_method": r["capacity"]["method"], "capacity_mn": r["capacity"]["capacity_sar_mn"],
            "capacity_pass_flag": int(bool(r["capacity"]["passes"])), "approval_level": r["approval"]["level"],
            "approval_rule": r["approval"].get("rule", ""), "clears_hurdle_flag": int(r["clears_hurdle"]),
            "hard_breaches": ";".join(r["hard_breaches"]), "recommendable_flag": int(r["recommendable"]),
            "not_recommendable_reason": r["not_recommendable_reason"], "selected_flag": int(selected), "created_by": by, "created_at": at}


def publish_set(pid: str, rows: list[dict[str, Any]], selected: str, by: str = "deal desk") -> dict[str, Any]:
    from backend.dealdesk.data import store
    at = now()
    return store.publish("dd_structure_set", [_row_out(pid, r, r["key"] == selected, by, at) for r in rows], mode="replace_where",
                         where={"proposal_id": pid}, actor=by or "deal desk")


def select(pid: str, key: str, by: str = "") -> dict[str, Any]:
    s = structure_set(pid)
    if key not in {r["key"] for r in s["rows"]}:
        raise KeyError(key)
    publish_set(pid, s["rows"], key, by or "deal desk")
    for r in s["rows"]:
        r["selected"] = r["key"] == key
    cur = next(r for r in s["rows"] if r["selected"])
    s.update(selected=key, selected_by_user=True, default_note=None, bar=bar(cur), plain_words=plain_words(s["rows"], cur),
             sva_basis=cur["sva_label"])
    return s


def add(pid: str, label: str, role: str, terms: dict[str, Any], covenants: list[dict[str, Any]] | None = None, origin: str = "",
        by: str = "", select_it: bool = False) -> dict[str, Any]:
    """Save a structure (user or stress-proofed) on the deal; returns the new set with the new row."""
    if role not in ("user", "stress_proofed"):
        raise ValueError("role must be user or stress_proofed")
    p = deal(pid)
    engine.analyse(with_covenants(p, covenants), terms)  # bad terms are a TermsError (422)
    have = [r["structure_key"] for r in saved(pid) if r["role"] == role]
    prefix = "user" if role == "user" else "proofed"
    n = 1 + max([int(k.rsplit("_", 1)[-1]) for k in have if k.rsplit("_", 1)[-1].isdigit()] or [0])
    key = f"{prefix}_{n}"
    s = structure_set(pid)
    rv = review(pid)
    row = measure(p, {"key": key, "label": label or f"Your structure {n}", "role": role, "origin": origin or "Built on the deal",
                      "terms": engine.merge_terms(p, terms), "covenants": covenants}, rv)
    rows = s["rows"] + [row]
    sel = key if select_it else s["selected"]
    publish_set(pid, rows, sel, by or "deal desk")
    return {**structure_set(pid), "added": key}

