"""Decision consistency (R14 backlog #20, R13 Session IA).

Similar deals (sector, rating, size, structure) decided differently, by committee, desk or RM, with the differences
that explain the different decision or fail to explain it.

Method
  * Decisions (Data Domains): the final decision is dd_deal.status (approved, declined, counter_offered) at the
    deal's approval authority; the SME lane's decision is dd_sme_application.decision; the desk recommendation is
    dd_result.decision (view "recommended", else "ask"). Order: approve 2, counter-offer / refer / escalate 1,
    decline 0. A deal with neither is pending and shows the decision its engine run implies.
  * Similarity (0-1): sector 0.35, rating 0.25 x (1 - notches / 4), size 0.20 x (1 - |ln ratio| / ln 4), facility
    type 0.10, Islamic structure 0.10. Deals scoring at least 0.55 are similar.
  * Factors (engine.analyse on the ask, plus Data Domains): rating, RAROC less hurdle, hard and soft limit breaches,
    SIMAH flag, DSCR and Debt/EBITDA after the deal, LGD, open high or critical review findings, and the stress
    ladder's mildest breaking severity (dd_stress_result). A factor counts when the gap is material (1 notch,
    1 pp RAROC, one breach, 0.15x DSCR, 0.5x leverage, 5 pp LGD, two findings, one stress severity step).
  * Explained: every material factor favours the deal with the better decision. Partly explained: factors point
    both ways. Not explained: no material factor favours the better-decided deal.
"""
from __future__ import annotations

import functools
import json
import math
from typing import Any

from backend.dealdesk.intel.approval import common as C

ORDER = {"approve": 2, "approve_as_asked": 2, "approved": 2, "counter_offer": 1, "counter_offered": 1, "refer": 1, "escalate": 1,
         "decline": 0, "declined": 0}
WORD = {2: "approve", 1: "counter-offer", 0: "decline"}
STRESS_RANK = {"none": 3, "severe": 2, "moderate": 1, "mild": 0, None: None}
SIMAH_RANK = {"clear": 2, "watch": 1, "adverse": 0}
THRESHOLD = 0.55


def _decisions() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in C.rows("dd_deal", columns=["proposal_id", "status", "approval_authority", "rm", "committee_date", "reporting_quarter", "rel_version"]):
        st = r.get("status")
        if st in ("approved", "declined", "counter_offered"):
            out.setdefault(r["proposal_id"], {})["final"] = {
                "decision": ORDER[st], "by": "committee", "authority": r.get("approval_authority") or "committee",
                "figure": C.fig(ORDER[st], "decision rank", C.row_source("dd_deal", r, "status"), "Final decision"), "raw": st}
    for r in C.rows("dd_sme_application"):
        d = r.get("decision")
        if d in ORDER:
            out.setdefault(r["proposal_id"], {})["sme"] = {
                "decision": ORDER[d], "by": "SME lane", "authority": r.get("doa_level") or "",
                "figure": C.fig(ORDER[d], "decision rank", C.row_source("dd_sme_application", r, "decision"), "SME lane decision"), "raw": d}
    res = C.rows("dd_result")
    for view in ("ask", "recommended"):  # recommended overrides ask
        for r in res:
            if r.get("view") == view and r.get("decision") in ORDER:
                out.setdefault(r["proposal_id"], {})["desk"] = {
                    "decision": ORDER[r["decision"]], "by": "desk", "authority": r.get("approval_level") or "",
                    "figure": C.fig(ORDER[r["decision"]], "decision rank", C.row_source("dd_result", r, "decision"), "Desk recommendation"),
                    "raw": r["decision"]}
    return out


@functools.lru_cache(maxsize=4)
def _features_all(pv: str) -> str:
    regs = {r["proposal_id"]: r for r in C.rows("dd_deal", columns=["proposal_id", "rm", "reporting_quarter", "rel_version", "product"])}
    fnd: dict[str, int] = {}
    for f in C.rows("dd_review_finding"):
        if f.get("status") == "open" and f.get("severity") in ("high", "critical"):
            fnd[f["proposal_id"]] = fnd.get(f["proposal_id"], 0) + 1
    out = {}
    for pid in C.all_ids():
        try:
            p = C.proposal(pid)
            a = C.analysis(pid)
        except Exception:  # noqa: BLE001 - a deal the engine cannot price is left out (listed as such)
            out[pid] = None
            continue
        m, t, ob = a["metrics"], a["terms"], p["obligor"]
        st = C.latest_stress(pid)
        out[pid] = {"proposal_id": pid, "obligor": ob["name"], "sector": ob["sector"], "rating": ob["internal_rating"],
                    "amount_sar_mn": float(m["amount_sar_mn"]), "facility_type": t["facility_type"], "structure": t["structure"],
                    "rm": (regs.get(pid) or {}).get("rm") or p.get("rm"), "product": (regs.get(pid) or {}).get("product"),
                    "raroc": m["lifetime_raroc"], "hurdle": m["hurdle"], "raroc_gap": (m["lifetime_raroc"] or 0) - m["hurdle"],
                    "hard": len(C.hard_breaches(a)), "hard_names": [c["label"] for c in C.hard_breaches(a)],
                    "soft": len(C.soft_breaches(a)), "simah": ob.get("simah_flag") or "clear",
                    "dscr": m["dscr_post"] if m["dscr_post"] is not None and math.isfinite(m["dscr_post"]) else None,
                    "leverage": m["debt_ebitda_post"] if m["debt_ebitda_post"] is not None and math.isfinite(m["debt_ebitda_post"]) else None,
                    "lgd": m["lgd_y1"], "findings": fnd.get(pid, 0), "stress": st["worst_breaking_severity"],
                    "implied": 2 if C.approvable(a) else (0 if any(c["name"] == "min_rating" for c in C.hard_breaches(a)) or len(C.hard_breaches(a)) > 1 else 1)}
    return json.dumps(out)


def features() -> dict[str, dict[str, Any] | None]:
    from backend.dealdesk import params
    return json.loads(_features_all(json.dumps(params.versions(), sort_keys=True)))


def similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    s = 0.35 * (a["sector"] == b["sector"])
    g = C.notch_gap(a["rating"], b["rating"])
    s += 0.25 * max(0.0, 1 - (g if g is not None else 4) / 4)
    if a["amount_sar_mn"] > 0 and b["amount_sar_mn"] > 0:
        s += 0.20 * max(0.0, 1 - abs(math.log(a["amount_sar_mn"] / b["amount_sar_mn"])) / math.log(4))
    s += 0.10 * (a["facility_type"] == b["facility_type"]) + 0.10 * (a["structure"] == b["structure"])
    return round(s, 4)


def _factors(x: dict[str, Any], y: dict[str, Any]) -> list[dict[str, Any]]:
    """Material differences; 'favours' is the deal id the factor speaks for."""
    from backend.v5common.ratings import rank
    out = []

    def add(name: str, better: str | None, text: str) -> None:
        if better:
            out.append({"factor": name, "favours": better, "text": text})

    try:
        rx, ry = rank(x["rating"]), rank(y["rating"])
        if abs(rx - ry) >= 1:
            add("rating", x["proposal_id"] if rx < ry else y["proposal_id"], f"rating {x['rating']} vs {y['rating']}")
    except Exception:  # noqa: BLE001
        pass
    if abs(x["raroc_gap"] - y["raroc_gap"]) >= 0.01:
        add("raroc", x["proposal_id"] if x["raroc_gap"] > y["raroc_gap"] else y["proposal_id"],
            f"RAROC less hurdle {x['raroc_gap'] * 100:+.1f} pp vs {y['raroc_gap'] * 100:+.1f} pp")
    if x["hard"] != y["hard"]:
        add("hard_limits", x["proposal_id"] if x["hard"] < y["hard"] else y["proposal_id"],
            f"hard limit breaches {x['hard']} ({', '.join(x['hard_names']) or 'none'}) vs {y['hard']} ({', '.join(y['hard_names']) or 'none'})")
    if x["soft"] != y["soft"]:
        add("policy", x["proposal_id"] if x["soft"] < y["soft"] else y["proposal_id"], f"policy breaches {x['soft']} vs {y['soft']}")
    sx, sy = SIMAH_RANK.get(x["simah"], 2), SIMAH_RANK.get(y["simah"], 2)
    if sx != sy:
        add("simah", x["proposal_id"] if sx > sy else y["proposal_id"], f"SIMAH {x['simah']} vs {y['simah']}")
    if x["dscr"] is not None and y["dscr"] is not None and abs(x["dscr"] - y["dscr"]) >= 0.15:
        add("dscr", x["proposal_id"] if x["dscr"] > y["dscr"] else y["proposal_id"], f"DSCR after the deal {x['dscr']:.2f}x vs {y['dscr']:.2f}x")
    if x["leverage"] is not None and y["leverage"] is not None and abs(x["leverage"] - y["leverage"]) >= 0.5:
        add("leverage", x["proposal_id"] if x["leverage"] < y["leverage"] else y["proposal_id"],
            f"Debt/EBITDA after the deal {x['leverage']:.2f}x vs {y['leverage']:.2f}x")
    if abs(x["lgd"] - y["lgd"]) >= 0.05:
        add("lgd", x["proposal_id"] if x["lgd"] < y["lgd"] else y["proposal_id"], f"LGD {x['lgd']:.0%} vs {y['lgd']:.0%}")
    if abs(x["findings"] - y["findings"]) >= 2:
        add("findings", x["proposal_id"] if x["findings"] < y["findings"] else y["proposal_id"],
            f"open high/critical findings {x['findings']} vs {y['findings']}")
    kx, ky = STRESS_RANK.get(x["stress"]), STRESS_RANK.get(y["stress"])
    if kx is not None and ky is not None and kx != ky:
        add("stress", x["proposal_id"] if kx > ky else y["proposal_id"], f"stress breaks first at {x['stress']} vs {y['stress']}")
    return out


def _decision_of(pid: str, dec: dict[str, Any], feats: dict[str, Any]) -> dict[str, Any]:
    d = dec.get(pid) or {}
    pick = d.get("final") or d.get("sme") or d.get("desk")
    if pick:
        return {"decision": WORD[pick["decision"]], "rank": pick["decision"], "by": pick["by"], "authority": pick["authority"],
                "figure": pick["figure"], "pending": False}
    f = feats.get(pid) or {}
    imp = f.get("implied")
    return {"decision": WORD.get(imp, "n/a"), "rank": imp, "by": "engine (pending)", "authority": "",
            "figure": C.efig(pid, imp, "decision rank", "Engine-implied decision") if imp is not None else None, "pending": True}


def _pair(x: dict[str, Any], y: dict[str, Any], dx: dict[str, Any], dy: dict[str, Any]) -> dict[str, Any]:
    better, worse = (x, y) if dx["rank"] > dy["rank"] else (y, x)
    db, dw = (dx, dy) if dx["rank"] > dy["rank"] else (dy, dx)
    fs = _factors(better, worse)
    pro = [f for f in fs if f["favours"] == better["proposal_id"]]
    con = [f for f in fs if f["favours"] == worse["proposal_id"]]
    status = "explained" if pro and not con else "partly explained" if pro else "not explained"
    lead = (f"{better['proposal_id']} ({better['obligor']}, {better['rating']}, SAR {better['amount_sar_mn']:,.0f}m) got {db['decision']} "
            f"({db['by']}) and {worse['proposal_id']} ({worse['obligor']}, {worse['rating']}, SAR {worse['amount_sar_mn']:,.0f}m) got "
            f"{dw['decision']} ({dw['by']}).")
    if status == "explained":
        why = "The difference is explained by " + "; ".join(f["text"] for f in pro) + "."
    elif status == "partly explained":
        why = ("Partly explained by " + "; ".join(f["text"] for f in pro) + ", but " + "; ".join(f["text"] for f in con)
               + f" favour {worse['proposal_id']}.")
    else:
        why = ("Nothing in the data explains it: " + ("; ".join(f["text"] for f in con) + f" all favour {worse['proposal_id']}."
                                                      if con else "no material difference in rating, returns, limits, SIMAH, cover, LGD, findings or stress."))
    return {"better": better["proposal_id"], "worse": worse["proposal_id"], "status": status, "text": f"{lead} {why}",
            "for_better": pro, "for_worse": con, "rms": sorted({better.get("rm") or "", worse.get("rm") or ""} - {""}),
            "decided_by": sorted({db["by"], dw["by"]})}


def _card(pid: str, f: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    return {"proposal_id": pid, "obligor": f["obligor"], "sector": f["sector"], "rating": f["rating"], "rm": f["rm"],
            "facility_type": f["facility_type"], "structure": f["structure"],
            "amount": C.efig(pid, f["amount_sar_mn"], "SAR m", "Amount"),
            "raroc": C.efig(pid, f["raroc"], "share", "Lifetime RAROC"), "hurdle": C.efig(pid, f["hurdle"], "share", "Hurdle"),
            "decision": d}


def consistency(pid: str) -> dict[str, Any]:
    pid = C.resolve_id(pid)
    C.register_row(pid)
    feats = features()
    me = feats.get(pid)
    if me is None:
        raise C.UnknownDeal(pid)
    dec = _decisions()
    dme = _decision_of(pid, dec, feats)
    sims = []
    for q, f in feats.items():
        if q == pid or f is None:
            continue
        dq = _decision_of(q, dec, feats)
        if dq["pending"]:
            continue
        s = similarity(me, f)
        if s >= THRESHOLD:
            sims.append((s, q, f, dq))
    sims.sort(key=lambda x: (-x[0], x[1]))
    similar = []
    diffs = []
    for s, q, f, dq in sims[:10]:
        card = _card(q, f, dq)
        card["similarity"] = s
        similar.append(card)
        if dme["rank"] is not None and dq["rank"] != dme["rank"]:
            pr = _pair(me, f, dme, dq)
            pr["similarity"] = s
            diffs.append(pr)
    # the deal's own decisions disagreeing (desk vs committee)
    own = dec.get(pid) or {}
    internal = None
    if own.get("final") and own.get("desk") and own["final"]["decision"] != own["desk"]["decision"]:
        f, d = own["final"], own["desk"]
        fs = [x for x in _own_reasons(me)]
        internal = {"text": f"The desk recommended {WORD[d['decision']]} ({d['raw']}) and the {f['authority']} decided {WORD[f['decision']]}. "
                            + ("Data that supports the committee: " + "; ".join(fs) + "." if fs and f["decision"] < d["decision"] else
                               "Nothing in the engine run or the review findings records why." if f["decision"] < d["decision"] else
                               "The committee went further than the desk."),
                    "desk": d["figure"], "final": f["figure"]}
    n_un = sum(1 for d in diffs if d["status"] == "not explained")
    head = (f"{len(similar)} similar decided deal{'s' if len(similar) != 1 else ''}; {len(diffs)} decided differently from "
            f"{pid} ({dme['decision']}, {dme['by']})" + (f", {n_un} with no explanation in the data" if n_un else "") + ".")
    if internal:
        head += " " + internal["text"]
    thin = len(similar) < 3
    return {"proposal_id": pid, "obligor": me["obligor"], "headline": head, "decision": dme, "deal": _card(pid, me, dme),
            "similar": similar, "decided_differently": sorted(diffs, key=lambda d: ({"not explained": 0, "partly explained": 1, "explained": 2}[d["status"]], -d["similarity"])),
            "desk_vs_committee": internal, "prior_committee": _prior(pid),
            "data_note": ("Few decided deals are similar to this one (fewer than 3); read the comparison as indicative." if thin else None),
            "decided_in_book": sum(1 for q in feats if not _decision_of(q, dec, feats)["pending"]),
            "method": __doc__.split("Method", 1)[1].strip()}


def _own_reasons(f: dict[str, Any]) -> list[str]:
    out = []
    if f["simah"] != "clear":
        out.append(f"SIMAH {f['simah']}")
    if f["hard"]:
        out.append("hard limit breaches: " + ", ".join(f["hard_names"]))
    if f["raroc_gap"] < 0:
        out.append(f"RAROC {f['raroc_gap'] * 100:+.1f} pp against the hurdle")
    if f["findings"]:
        out.append(f"{f['findings']} open high/critical review findings")
    if f["stress"] in ("mild", "moderate"):
        out.append(f"stress breaks at {f['stress']} severity")
    return out


def _prior(pid: str) -> list[dict[str, Any]]:
    out = []
    for r in C.rows("dd_reference", proposal_id=pid):
        if r.get("kind") == "committee_decision":
            out.append({"ref_no": r["ref_no"], "date": r["ref_date"], "authority": r["authority"], "text": r["text"],
                        "amount": C.rfig("dd_reference", r, "amount_mn", "SAR m", "Approved amount") if r.get("amount_mn") is not None else None})
    return out


def book() -> dict[str, Any]:
    """Every pair of similar decided deals with different decisions, worst-explained first, and the count by RM and decider."""
    feats = features()
    dec = _decisions()
    decided = [(q, f, _decision_of(q, dec, feats)) for q, f in feats.items() if f is not None]
    decided = [x for x in decided if not x[2]["pending"]]
    pairs = []
    for i in range(len(decided)):
        for j in range(i + 1, len(decided)):
            (q1, f1, d1), (q2, f2, d2) = decided[i], decided[j]
            if d1["rank"] == d2["rank"]:
                continue
            s = similarity(f1, f2)
            if s >= THRESHOLD:
                pr = _pair(f1, f2, d1, d2)
                pr["similarity"] = s
                pairs.append(pr)
    pairs.sort(key=lambda d: ({"not explained": 0, "partly explained": 1, "explained": 2}[d["status"]], -d["similarity"]))
    by_rm: dict[str, int] = {}
    for pr in pairs:
        if pr["status"] != "explained":
            for rm in pr["rms"]:
                by_rm[rm] = by_rm.get(rm, 0) + 1
    n_un = sum(1 for p in pairs if p["status"] == "not explained")
    return {"pairs": pairs, "decided": len(decided), "not_explained": n_un, "by_rm": by_rm,
            "headline": f"{len(pairs)} pairs of similar deals decided differently across {len(decided)} decided deals; {n_un} not explained by the data.",
            "method": __doc__.split("Method", 1)[1].strip()}
