"""Round G: the "Counterparty exposure" section, in the bank form's block model, for the two writers that include it:

    w_counterparty_request(w)      the RM's business request (backend/dealdesk/rm_request/writers.SECTIONS)
    w_counterparty_proposal(D)     credit's bank-form proposal (backend/dealdesk/house_style/bankform/registry.SECTIONS)

Both read the graph's signals for the deal's borrower (signals.for_node) and print, per counterparty in difficulty or in another
deal: who, its role, its standing, the other deal, and where the link and the standing were read (document and page, or the
Data Domains relation). Every sentence names its source (the proposal voice, house_style/bankform/voice.py). Deterministic.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.graph import signals as SG
from backend.dealdesk.graph import store as G
from backend.dealdesk.graph.text import dmy

HEAD = ["Counterparty", "Role", "Standing", "Other deal", "Link shown by", "Standing per"]
WIDTHS = [4.2, 2.2, 2.6, 2.2, 4.4, 4.0]
MAX_ROWS = 12


def locate(pid: str = "", cif: str = "", name: str = "", cr: str = "") -> tuple[str | None, str]:
    """(the borrower's node, the deal it is focal in) from a deal id, a CIF, a CR or a name."""
    from backend.dealdesk.graph import build
    try:
        build.ensure()
    except Exception:  # noqa: BLE001 - no graph: the section says so
        return None, pid
    if pid:
        d = G.deal(pid)
        if d:
            return d["node_id"], pid
    if cif:
        n = G.by_cif(cif)
        if n:
            return n["node_id"], pid
    with G.conn() as c:
        n = G.find(c, name, "company", cr=cr) if (name or cr) else None
    return (n["node_id"] if n else None), pid


def content(pid: str = "", cif: str = "", name: str = "", cr: str = "") -> dict[str, Any]:
    node, focal = locate(pid, cif, name, cr)
    if not node:
        return {"node": None, "signals": [], "counterparties": 0, "built_at": G.meta_get("built_at") if G.db_path().exists() else None}
    sig = SG.for_node(node, focal)
    cps = {e["dst"] for e in G.edges_of([node]) if e["src"] == node and e["rel"] in SG.OUT_ROLE}
    return {"node": node, "name": (G.node(node) or {}).get("name") or name, "signals": sig, "counterparties": len(cps),
            "built_at": G.meta_get("built_at")}


def _standing(s: dict[str, Any]) -> str:
    if not s["standing"]:
        return "No difficulty known"
    st = s["standing"][0]
    return st["label"][:1].upper() + st["label"][1:]


def _deal(s: dict[str, Any]) -> str:
    return ", ".join(f"{o['proposal_id']} ({o.get('status') or 'open'})" for o in s["other_deals"][:2]) or "–"


def rows(sig: list[dict[str, Any]]) -> list[list[str]]:
    out = []
    for s in sig[:MAX_ROWS]:
        link = SG.where(s["evidence"][0], short=True) if s["evidence"] else "–"
        per = SG.where(s["standing"][0], short=True) if s["standing"] else (f"Deal Desk register ({s['other_deals'][0]['proposal_id']})" if s["other_deals"] else "–")
        role = s["counterparty"]["role_label"] if s["rule"] != "borrower_is_counterparty" else f"{s['focal']['name']} is its {s['counterparty']['role']}"
        out.append([s["counterparty"]["name"], role, _standing(s), _deal(s), link, per])
    return out


def blocks(pid: str = "", cif: str = "", name: str = "", cr: str = "", voice: str = "business",
           optional: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    """The section's blocks; optional=True returns no block when the graph holds no signal for the customer (the writer leaves the
    section out)."""
    from backend.dealdesk.house_style.bankform.blocks import P, T
    c = content(pid, cif, name, cr)
    if optional and not c["signals"]:
        return [], []
    who = c.get("name") or name or "the customer"
    when = dmy((c.get("built_at") or "")[:10]) or "this date"
    if not c["node"]:
        return [P(f"Counterparty exposure of {who}: not available; CreditProbe's counterparty graph holds no entry for the customer as at {when} "
                  "(source: CreditProbe counterparty graph).")], ["no counterparty graph entry"]
    sig = c["signals"]
    hard = [s for s in sig if s["severity"] in ("high", "medium")]
    joined = [s for s in sig if s["severity"] == "low"]
    out = [P(f"As per CreditProbe's counterparty graph ({when}), {c['counterparties']} counterparties of {who} (buyers, suppliers, guarantors, "
             f"owners and related parties) are known from the documents and the Bank's data; {len(hard)} "
             f"{'is' if len(hard) == 1 else 'are'} in difficulty and {len(joined)} {'is' if len(joined) == 1 else 'are'} in another deal on the desk.")]
    if not sig:
        out.append(P(f"No counterparty of {who} is in default, classified, past due, restructured or on watch, and none is the borrower in another deal "
                     f"(source: CreditProbe counterparty graph, {when})."))
        return out, []
    for s in hard[:4]:
        lead = ("We note that " if voice == "credit" else "") + s["title"]
        src = SG.where(s["evidence"][0], short=True) if s["evidence"] else "the Bank's data"
        out.append(P(f"{lead} (source: {src}).".replace("..", ".")))
    out.append(T(HEAD, rows(sig), source="CreditProbe counterparty graph: the documents read and Data Domains (borrower_360, bureau, deal_desk, "
                                         "network_intel); a seeded link is marked in the graph", widths=WIDTHS))
    if any(s["synthetic"] for s in sig):
        out.append(P(f"Some links above were seeded for the trial and are fictional (source: data/dealdesk/graph/seed_links.json, {when})."))
    return out, []


def w_counterparty_request(w: Any) -> tuple[list[dict[str, Any]], list[str]]:
    c = w.c
    try:
        return blocks(pid=str(c.get("proposal_id") or ""), cif=str(c.get("cif") or ""), name=str(c.get("name") or ""), cr=str(c.get("cr_number") or ""),
                      voice="business", optional=True)
    except Exception:  # noqa: BLE001 - an optional section never takes the request down
        return [], []


def w_counterparty_proposal(D: Any) -> tuple[list[dict[str, Any]], list[str]]:
    ob = (D.p or {}) if hasattr(D, "p") else {}
    return blocks(pid=str(getattr(D, "pid", "") or ""), cif=str(ob.get("obligor_id") or ob.get("cif") or ""), name=str(getattr(D, "name", "") or ""),
                  voice="credit")
