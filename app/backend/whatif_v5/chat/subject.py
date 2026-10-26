"""R16 m (M4): the context answer a What-If thread opens with, before the proposed scenario.

A thread opened from a starter chip, a card or a library item first shows the facts of its subject: the
sector or product the scenario is scoped to (Construction: EAD, share of the book, Stage 2 and Stage 3 EAD and
share, ECL and coverage, Early Warning warned names, the trend over recent periods and the largest exposures), or
the whole book for a book-wide scenario (with the largest sectors or products instead of names).

Deterministic (PLAN_R14 N1): every figure is a sum over the What-If domain (`store.frame`, equal to the books)
at the thread's period, joined to the Early Warning release read-only for the warned count
(`summary.profile`, the same reader as the thread header). No model, no estimate.

    subject_context(thread, scopes)   -> {"type": "context", ...}   (scopes None = the whole book)
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.whatif_v5 import summary
from backend.whatif_v5.chat.commentary import money
from backend.whatif_v5.domain import store
from backend.whatif_v5.models import runner
from backend.whatif_v5.models.engine import scope_mask
from backend.whatif_v5.models.scenario import Scenario, Scope

TREND_PERIODS = 5
TOP_N = 5


def scopes_of(sc: Scenario | dict | None) -> list[Scope] | None:
    """The subject of a scenario: the union of its steps' scopes; None = the whole book."""
    if sc is None:
        return None
    steps = sc.steps if isinstance(sc, Scenario) else [Scope.from_dict(s.get("scope")) for s in (sc.get("steps") or [])]
    scopes = [s.scope if hasattr(s, "scope") else s for s in steps]
    if not scopes or any(s.is_book() for s in scopes):
        return None
    return scopes


def _mask(f: pd.DataFrame, scopes: list[Scope] | None) -> np.ndarray:
    if not scopes:
        return np.ones(len(f), dtype=bool)
    m = np.zeros(len(f), dtype=bool)
    for s in scopes:
        m |= np.asarray(scope_mask(f, s), dtype=bool)
    return m


def _label(domain: str, scopes: list[Scope] | None) -> str:
    lab = runner.LABELS[domain]
    if not scopes:
        return f"the {lab['book'].lower()} book"
    out: list[str] = []
    for s in scopes:
        d = s.describe(lab)
        if d not in out:
            out.append(d)
    return " and ".join(out)


def _pct(a: float, b: float) -> float:
    return a / b * 100 if b else 0.0


def trend(domain: str, period: str, scopes: list[Scope] | None, n: int = TREND_PERIODS) -> list[dict[str, Any]]:
    """The subject over the last `n` periods up to `period`: EAD, share of the book, Stage 2/3 share, ECL, coverage."""
    ps = store.periods(domain)
    end = ps.index(period) + 1 if period in ps else len(ps)
    rows = []
    for p in ps[max(0, end - n):end]:
        f = store.frame(domain, p)
        m = _mask(f, scopes)
        g = f[m]
        ead, book = float(g["ead"].sum()), float(f["ead"].sum())
        s23 = float(g.loc[g["stage"].isin([2, 3]), "ead"].sum())
        ecl = float(g["ecl_final"].sum())
        rows.append({"period": p, "ead": round(ead, 4), "share_pct": round(_pct(ead, book), 2),
                     "stage23_pct": round(_pct(s23, ead), 2), "ecl": round(ecl, 4), "coverage_pct": round(_pct(ecl, ead), 2)})
    return rows


def subject_context(thread: dict[str, Any], scopes: list[Scope] | None) -> dict[str, Any]:
    """The context block about the thread's subject (a sector / product scope, or the whole book)."""
    domain = thread["domain"]
    lab = runner.LABELS[domain]
    period = store.resolve_period(domain, thread.get("period") or "")
    full = store.frame(domain, period)
    m = _mask(full, scopes)
    f = full[m]
    label = _label(domain, scopes)
    title = label[:1].upper() + label[1:]
    book_ead = float(full["ead"].sum())
    prof = summary.profile(f.copy(), domain, period, top_n=TOP_N)
    c = prof["cards"]
    st = {s["stage"]: s for s in prof["stages"]}
    kind = "scope" if scopes else "book"
    share = _pct(c["ead"], book_ead)
    figures = [
        {"key": "ead", "label": "EAD", "value": c["ead"], "unit": "sar_mn", "text": money(c["ead"])},
        {"key": "share_pct", "label": f"Share of the {lab['book'].lower()} book (EAD)", "value": round(share, 2), "unit": "pct",
         "text": f"{share:.1f}%"},
        {"key": "owners", "label": lab["owners"], "value": c["owners"], "unit": "count", "text": f"{c['owners']:,}"},
        {"key": "exposures", "label": lab["exposures"], "value": c["exposures"], "unit": "count", "text": f"{c['exposures']:,}"},
        {"key": "stage2_ead", "label": "Stage 2 EAD", "value": st[2]["ead"], "unit": "sar_mn",
         "text": f"{money(st[2]['ead'])} ({st[2]['ead_pct']:.1f}%)"},
        {"key": "stage2_pct", "label": "Stage 2 share of EAD", "value": round(st[2]["ead_pct"], 2), "unit": "pct",
         "text": f"{st[2]['ead_pct']:.1f}%"},
        {"key": "stage3_ead", "label": "Stage 3 EAD", "value": st[3]["ead"], "unit": "sar_mn",
         "text": f"{money(st[3]['ead'])} ({st[3]['ead_pct']:.1f}%)"},
        {"key": "stage3_pct", "label": "Stage 3 share of EAD", "value": round(st[3]["ead_pct"], 2), "unit": "pct",
         "text": f"{st[3]['ead_pct']:.1f}%"},
        {"key": "ecl", "label": "ECL", "value": c["ecl"], "unit": "sar_mn", "text": money(c["ecl"])},
        {"key": "coverage_pct", "label": "Coverage (ECL / EAD)", "value": round(c["coverage_pct"], 2), "unit": "pct",
         "text": f"{c['coverage_pct']:.2f}%"},
        {"key": "warned_owners", "label": f"Warned {lab['owners'].lower()} (Early Warning moderate or worse)",
         "value": c["ews_warned_owners"], "unit": "count",
         "text": f"{c['ews_warned_owners']:,} ({money(c['ews_warned_ead'])} EAD)"},
    ]
    if kind == "book":
        figures = [x for x in figures if x["key"] != "share_pct"]
    tr = trend(domain, period, scopes)
    if kind == "book":
        top = [{"name": r["name"], "ead": r["ead"], "share_pct": round(r["ead_pct"], 2), "ecl": r["ecl"],
                "coverage_pct": round(r["coverage_pct"], 2), "owners": r["owners"]} for r in prof["split"]["rows"][:TOP_N]]
        top_title = f"Largest {prof['split']['plural'].lower()} by EAD"
        top_cols = [{"key": "name", "label": prof["split"]["label"]}, {"key": "ead", "label": "EAD (SAR mn)"},
                    {"key": "share_pct", "label": "Share of book (%)"}, {"key": "ecl", "label": "ECL (SAR mn)"},
                    {"key": "coverage_pct", "label": "Coverage (%)"}, {"key": "owners", "label": lab["owners"]}]
    else:
        top = [{"name": r["owner_name"] or r["owner_id"], "owner_id": r["owner_id"], "grade": r["grade"], "stage": r["stage"],
                "ead": r["ead"], "ecl": r["ecl"], "ews_band": r["ews_band_label"],
                "share_pct": round(r["share_pct"], 2), "href": r["href"]} for r in prof["top"]["rows"]]
        top_title = f"Largest {lab['owners'].lower()} by EAD"
        top_cols = [{"key": "name", "label": lab["owner"]}, {"key": "grade", "label": lab["grade"]},
                    {"key": "stage", "label": "Stage"}, {"key": "ead", "label": "EAD (SAR mn)"},
                    {"key": "share_pct", "label": f"Share of {label} (%)"}, {"key": "ecl", "label": "ECL (SAR mn)"},
                    {"key": "ews_band", "label": "Early Warning"}]

    # the words (N4): headline, trend sentence, plain-words lines
    s2, s3 = st[2]["ead_pct"], st[3]["ead_pct"]
    head = (f"**{title}** carries {money(c['ead'])} of EAD"
            + (f", {share:.1f}% of the {lab['book'].lower()} book" if kind == "scope" else "")
            + f"; {s2:.1f}% of it is in Stage 2 and {s3:.1f}% in Stage 3, ECL is {money(c['ecl'])} "
            f"({c['coverage_pct']:.2f}% coverage) and Early Warning flags {c['ews_warned_owners']:,} "
            f"{lab['owners'].lower()} at {period}.")
    trend_line = ""
    if len(tr) >= 2:
        a, b = tr[0], tr[-1]
        word = "rose" if b["stage23_pct"] > a["stage23_pct"] + 0.05 else "fell" if b["stage23_pct"] < a["stage23_pct"] - 0.05 else "held"
        trend_line = (f"Over {len(tr) - 1} {lab['period'].lower()}s ({a['period']} to {b['period']}) EAD went from "
                      f"{money(a['ead'])} to {money(b['ead'])}, ECL from {money(a['ecl'])} to {money(b['ecl'])}, and the "
                      f"Stage 2+3 share {word} from {a['stage23_pct']:.1f}% to {b['stage23_pct']:.1f}%.")
    if top:
        lead = top[0]
        top_line = (f"Largest {lab['owner'].lower() if kind == 'scope' else lab['segment'].lower()}: {lead['name']} "
                    f"({money(lead['ead'])}).")
    else:
        top_line = ""
    plain = [f"{title}: {money(c['ead'])} lent" + (f", {share:.0f}% of the book." if kind == "scope" else "."),
             f"{s2 + s3:.0f}% is in Stage 2 or 3 (showing stress); ECL {money(c['ecl'])}.",
             f"Early Warning flags {c['ews_warned_owners']:,} {lab['owners'].lower()}."]
    if len(tr) >= 2:
        plain.append(f"Stage 2+3 share {word} from {tr[0]['stage23_pct']:.0f}% to {tr[-1]['stage23_pct']:.0f}% since {tr[0]['period']}.")
    rel_ews = summary.EWS_FILES[domain][0]
    source = (f"What-If domain, relation exposures ({lab['book'].lower()} book, {period}, "
              f"{'scope ' + label if kind == 'scope' else 'all rows'}) joined to the Early Warning release {rel_ews} at "
              f"{period}; trend: the same relation at each of the last {len(tr)} periods.")
    return {"type": "context", "kind": kind, "domain": domain, "period": period, "subject": label, "title": title,
            "scope": [s.to_dict() for s in scopes] if scopes else [],
            "headline": head, "trend_line": trend_line, "top_line": top_line, "plain_words": plain,
            "figures": figures, "trend": tr,
            "top": {"title": top_title, "columns": top_cols, "rows": top},
            "source": source, "labels": lab}


__all__ = ["scopes_of", "subject_context", "trend"]
