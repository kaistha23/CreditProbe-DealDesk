"""Round G: Noor's brief source "counterparty_exposure" (registered in backend/agents_v5/brief/sources.COLLECTORS).

One line per pending deal whose borrower has a high or medium counterparty signal: the first signal in words, the count, the
link's document and the standing's source in the trace, and "Open" to the deal's Borrower 360 panel. Deals already decided
(approved, declined) are left out unless the signal is high. Reads the graph only (no model).
"""
from __future__ import annotations

from typing import Any

PENDING = ("new", "in_review", "counter_offered", "submitted", "draft", "queries")

#: how much each persona cares about this source (backend/agents_v5/brief/rank.PERSONA_W), registered on import
WEIGHTS = {"analyst": 0.95, "reviewer": 0.95, "rm": 0.9, "cro": 0.8}


def register_weights() -> None:
    from backend.agents_v5.brief import rank
    for persona, w in WEIGHTS.items():
        rank.PERSONA_W.setdefault(persona, {}).setdefault("counterparty_exposure", w)


register_weights()


def collect(ctx: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    from backend.agents_v5.brief.items import Item, num
    from backend.dealdesk.graph import build, signals as SG, store as G
    try:
        build.ensure()
    except Exception as e:  # noqa: BLE001
        return [], {"status": "not_built", "note": f"The counterparty graph is not built: {type(e).__name__}"}
    sig = SG.all_signals("medium")
    deals = {d["proposal_id"]: d for d in G.deals()}
    try:
        from backend.dealdesk import deal_list
        asked = {r["proposal_id"]: r.get("amount_sar_mn") for r in deal_list.all_rows()}
    except Exception:  # noqa: BLE001
        asked = {}
    by: dict[str, list[dict[str, Any]]] = {}
    for s in sig:
        by.setdefault(s["focal"]["proposal_id"], []).append(s)
    out = []
    for pid, ss in sorted(by.items()):
        d = deals.get(pid) or {}
        high = [s for s in ss if s["severity"] == "high"]
        if str(d.get("status") or "") not in PENDING and not high:
            continue
        top = (high or ss)[0]
        ev = top["evidence"][0] if top["evidence"] else {}
        st = top["standing"][0] if top["standing"] else {}
        title = (f"{d.get('name') or top['focal']['name']} ({pid}): {top['title']}"
                 + (f"; {len(ss) - 1} more counterparty signal{'s' if len(ss) - 1 != 1 else ''}" if len(ss) > 1 else ""))
        # the graph is Deal Desk's live store: no book period (the eyebrow reads "Deal Desk today"); the document's date is kept
        trace = [{"domain": "deal_desk", "relation": "dd_graph_edge", "keys": {"edge_id": ev.get("edge_id")}, "period": "", "date": str(ev.get("date") or ""),
                  "status": "synthetic" if ev.get("synthetic") else "published", "document": ev.get("doc_label") or ev.get("source_label")}]
        if st:
            trace.append({"domain": "deal_desk", "relation": "dd_graph_status", "keys": {"node_id": top["counterparty"]["node_id"]},
                          "period": "", "date": str(st.get("date") or ""), "status": "published", "document": st.get("doc_label") or st.get("source_label")})
        out.append(Item(
            id=f"cpx:{pid}", source="counterparty_exposure", source_label="Counterparty exposure", module="dealdesk", title=title,
            detail=top["sentence"], severity="high" if high else "medium", materiality_sar_mn=asked.get(pid), since=str(ev.get("date") or "") or None,
            audiences=("analyst", "reviewer", "rm", "cro"), kind="counterparty",
            numbers=[num("Signals", len(ss)), num("High", len(high))],
            trace=trace, show_me={"href": f"/deal-desk/{pid}?b360=1", "label": "Show the counterparty exposure"},
            open={"href": f"/deal-desk/{pid}?b360=1", "label": f"Open {pid}"},
            entity={"kind": "deal", "id": pid, "counterparty": top["counterparty"]["name"], "rule": top["rule"]},
        ))
    return out, {"status": "ok", "rows": len(out), "signals": len(sig)}
