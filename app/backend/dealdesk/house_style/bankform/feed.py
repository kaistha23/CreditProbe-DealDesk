"""R14 session p: what the bank-form proposal is fed by (K26): the **selected structure** and the one engine per fact (N2).

    F = feed(pid, structure=None)     # structure: None (the deal's selected structure), "ask", "recommended", "counter:<id>" or a terms dict
    F.structure        {key, label, source, terms, changes, default_note}
    F.economics        session e's economics(pid, structure)            (RAROC / SVA on one labelled basis)
    F.approval         session e's approval_authority(pid, structure)   (level, rule, reasons)
    F.capacity         session e's capacity(pid, structure)
    F.counter          session e's counter_offer(pid)                    (cures per finding)
    F.findings         session e's deal_findings(pid)                    (one count source)
    F.stress_proof     session f's stress-proof result on the deal (severity proofed to), when present
    F.regime           session m's current regime block (dated Brent, change, percentile, label), when present

Every adapter falls back to what the base branch has (the Deal Desk engine, dd_result, the MEV files) and says so in `source`;
a missing engine never takes the paper down. Results are cached per (pid, structure) for one process.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

_CACHE: dict[str, "Feed"] = {}


def _try(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception:  # noqa: BLE001 - an engine that is not merged or cannot price this deal
        return None


def _f_structure_set(pid: str) -> dict[str, Any] | None:
    try:
        from backend.dealdesk.stressproof import structures as ST  # session f
    except Exception:  # noqa: BLE001
        return None
    return _try(ST.structure_set, pid)


def _selected(pid: str, want: Any) -> dict[str, Any]:
    """The structure the proposal is written on."""
    if isinstance(want, dict):
        return {"key": "custom", "label": "Your structure", "source": "terms passed to the writer", "terms": want, "changes": [], "default_note": ""}
    ss = _f_structure_set(pid)
    if ss and ss.get("rows"):
        key = want or ss.get("selected") or ss.get("selected_key")
        row = next((r for r in ss["rows"] if str(r.get("key")) == str(key)), None) or next((r for r in ss["rows"] if r.get("selected")), None)
        if row is not None:
            ask = next((r for r in ss["rows"] if str(r.get("key")) == "ask"), None) or {}
            at, rt = ask.get("terms") or {}, row.get("terms") or {}
            changes = row.get("changes") or [{"field": k, "ask": at.get(k), "value": v} for k, v in rt.items()
                                              if isinstance(v, (int, float)) and not isinstance(v, bool) and at.get(k) != v
                                              and k in ("amount", "margin_bps", "tenor_years", "upfront_fee_bps", "cash_margin_pct", "guarantee_coverage_pct",
                                                        "commission_bps", "balloon_pct", "receivables_assignment_pct", "grace_years")]
            from backend.dealdesk.deposit_requirement.docs import change_entry  # Round D: the deposit requirement's change
            changes = changes + [x for x in [change_entry(at, rt)] if x and not row.get("changes")]
            note = "" if ss.get("selected_by_user") else "As per the Deal Desk flow, no structure is selected by the user yet: " + str(ss.get("default_note") or
                                                            "No structure selected on the structure set yet: the Review counter-proposal is used by default, as per the Deal Desk flow.")
            return {"key": str(row.get("key")), "label": str(row.get("label") or row.get("key")), "source": "session f structure set (dd_structure_set)",
                    "terms": rt, "changes": changes, "row": row, "default_note": note}
    if want in (None, "recommended") or str(want).startswith("counter:"):
        try:
            from backend.dealdesk import findings  # session e
            co = findings.counter_offer(pid)
            st = co.get("structure") or {}
            return {"key": "recommended", "label": "Recommended (Review counter-proposal)", "source": "session e counter_offer",
                    "terms": st.get("terms") or {}, "changes": st.get("changes") or [], "counter": co,
                    "default_note": "" if want else "No structure selected on the structure set yet: the Review counter-proposal is used by default, as per the Deal Desk flow."}
        except Exception:  # noqa: BLE001
            pass
    return {"key": "ask", "label": "As asked", "source": "dd_deal proposal record", "terms": {}, "changes": [],
            "default_note": "" if want == "ask" else "No structure selected and no counter-proposal available (not provided): the ask is used."}


def _engine_arg(st: dict[str, Any]) -> Any:
    if st["key"] in ("ask", "recommended") or str(st["key"]).startswith("counter:"):
        return st["key"]
    return st.get("terms") or "ask"


def _economics(pid: str, arg: Any) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import economics as E  # session e
    except Exception:  # noqa: BLE001
        return None
    r = _try(E.economics, pid, arg)
    if r is not None:
        r["source"] = "session e economics engine"
    return r


def _approval(pid: str, arg: Any) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import approval as A  # session e
    except Exception:  # noqa: BLE001
        return None
    r = _try(A.approval_authority, pid, arg)
    if r is not None:
        r["source"] = "session e approval authority (DoA engine)"
    return r


def _capacity(pid: str, arg: Any) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import capacity as Cp  # session e
    except Exception:  # noqa: BLE001
        return None
    return _try(Cp.capacity, pid, arg)


def _findings(pid: str) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import findings  # session e
    except Exception:  # noqa: BLE001
        return None
    return _try(findings.deal_findings, pid)


def _counter(pid: str) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import findings  # session e
    except Exception:  # noqa: BLE001
        return None
    return _try(findings.counter_offer, pid)


def _bridge(pid: str, arg: Any) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import economics as E  # session e
    except Exception:  # noqa: BLE001
        return None
    return _try(E.raroc_bridge, pid, arg)


def _pipeline(pid: str, st: dict[str, Any]) -> dict[str, Any] | None:
    """Session f's pipeline test on the selected structure. It runs the whole pipeline optimiser (15-50 s), so its result is kept
    by backend/dealdesk/house_style/pipeline_cache.py (a runtime cache under var/, not data; `ops/r14_p_warm.py` fills it)."""
    try:
        from backend.dealdesk.stressproof import pipeline_lines as PL  # session f
    except Exception:  # noqa: BLE001
        return None
    from backend.dealdesk.house_style import pipeline_cache as PC
    return PC.get_or_run(pid, st, lambda: _try(PL.run, pid, None if st.get("key") in ("custom",) else st.get("key")))


def _stress_proof(pid: str) -> dict[str, Any] | None:
    """f's latest stress-proof row for the deal (dd_stress_proof) through the papers' source door."""
    from backend.dealdesk.house_style.bankform import source as S
    rows = S.read("dd_stress_proof", proposal_id=pid)
    if not rows:
        return None
    r = max(rows, key=lambda r: str(r.get("created_at") or r.get("run_at") or r.get("published_at") or ""))
    for k in ("changes_json", "changes", "result_json"):
        if isinstance(r.get(k), str) and r[k][:1] in "[{":
            r[k] = _try(json.loads, r[k]) or r[k]
    return r


def _regime() -> dict[str, Any] | None:
    try:
        from backend.scenarios import regime as RG  # session m
        r = RG.current()
        return {"lines": RG.lines(r), "label": r.get("label") or r.get("regime"), "raw": r, "source": "session m current regime (backend/scenarios/regime.py)"}
    except Exception:  # noqa: BLE001
        pass
    try:
        from backend.whatif_v5.domain import mev
        s = mev.brent_monthly().dropna()
        last, prev12 = float(s.iloc[-1]), float(s.iloc[-13]) if len(s) > 12 else None
        when = str(s.index[-1])[:7]
        ch = f"{(last / prev12 - 1) * 100:+.0f}% on 12 months earlier" if prev12 else "12-month change not available"
        return {"lines": [f"Brent averaged USD {last:,.1f}/bbl in {when} ({ch}), per the EIA monthly series (whatif.brent_monthly_eia)."],
                "label": "", "raw": {}, "source": "EIA monthly Brent (data/whatif_v5/mev); session m's regime block not merged"}
    except Exception:  # noqa: BLE001
        return None


@dataclass
class Feed:
    pid: str
    structure: dict[str, Any]
    economics: dict[str, Any] | None = None
    economics_ask: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    capacity: dict[str, Any] | None = None
    counter: dict[str, Any] | None = None
    findings: dict[str, Any] | None = None
    stress_proof: dict[str, Any] | None = None
    regime: dict[str, Any] | None = None
    bridge: dict[str, Any] | None = None
    pipeline: dict[str, Any] | None = None
    sources: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        e, a = self.economics or {}, self.approval or {}
        return {"structure": {k: v for k, v in self.structure.items() if k not in ("row", "counter")},
                "raroc": (e.get("raroc") or {}).get("lifetime"), "hurdle": (e.get("raroc") or {}).get("hurdle"),
                "sva": (e.get("sva") or {}).get("lifetime"), "basis": (e.get("basis") or {}).get("label"),
                "approval": a.get("level"), "approval_rule": a.get("rule"), "capacity": (self.capacity or {}).get("capacity_sar_mn"),
                "stress_proofed_to": (self.stress_proof or {}).get("target") or (self.stress_proof or {}).get("target_severity"),
                "regime": (self.regime or {}).get("label"), "sources": self.sources}


def feed(pid: str, structure: Any = None) -> Feed:
    ck = f"{pid}|{json.dumps(structure, sort_keys=True, default=str)}"
    if ck in _CACHE:
        return _CACHE[ck]
    st = _selected(pid, structure)
    arg = _engine_arg(st)
    F = Feed(pid=pid, structure=st, economics=_economics(pid, arg), economics_ask=_economics(pid, "ask") if arg != "ask" else None,
             approval=_approval(pid, arg), capacity=_capacity(pid, arg), counter=st.get("counter") or _counter(pid), findings=_findings(pid),
             stress_proof=_stress_proof(pid), regime=_regime(), bridge=_bridge(pid, arg), pipeline=_pipeline(pid, st))
    if F.economics_ask is None and arg == "ask":
        F.economics_ask = F.economics
    F.sources = {"structure": st["source"], "economics": (F.economics or {}).get("source", "not available"),
                 "approval": (F.approval or {}).get("source", "not available"), "regime": (F.regime or {}).get("source", "not available"),
                 "stress_proof": "dd_stress_proof (session f)" if F.stress_proof else "not available"}
    _CACHE[ck] = F
    return F


def clear() -> None:
    _CACHE.clear()
