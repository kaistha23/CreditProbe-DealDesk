"""A What-If message that mixes questions and a scenario (PLAN_R5 T3, screen 08).

"Increase PD by 15% with stage implication. Reduce collateral. What should be a decent collateral drop? What is the
average increment in PDs between quarters?" holds two questions AND a scenario. The planner must never drop a part:
each question becomes its own answer part, from the What-If domain, and the statements become one proposed scenario
(sized by what the answers found when the user left a size open), which runs only on Execute after the user picks
Delta or XGBoost.

`split()` is deterministic (the same on the Mac with the model key and in the cloud without it); each question is then
answered by a domain answerer when it is one of the known history questions, or by the forked Cockpit agent alone.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backend.whatif_v5.domain import mev
from backend.whatif_v5.domain import store as dstore

QUESTION_START = re.compile(
    r"^(what|what's|whats|why|how|which|who|where|when|is|are|does|do|did|can|could|should|would|will|tell me|show me|"
    r"give me|list|compare|explain)\b", re.I)
LEVER_WORDS = re.compile(
    r"\b(pd|probabilit\w* of default|lgd|loss given|ccf|ead|collateral|haircut|downgrad\w*|upgrad\w*|notch\w*|rating|"
    r"stage|staging|sicr|oil|brent|gdp|inflation|interest rate|rates?|unemployment|real estate|property|shock|stress|"
    r"increase|decrease|reduce|raise|cut|drop|fall|rise|shift|migrat\w*|\+\d|-\d|\d+\s*%|\d+\s*(bps|pp|notch))", re.I)
COLLATERAL_Q = re.compile(r"collateral|haircut|security value|secured", re.I)
SIZE_Q = re.compile(r"decent|reasonable|realistic|plausible|how much|how big|what size|drop|fall|declin|reduc|shock|severe", re.I)
PD_Q = re.compile(r"\bpds?\b|probabilit\w* of default|default rate", re.I)
QOQ_Q = re.compile(r"quarter|qoq|between periods|period[- ]on[- ]period|increment|increase|change|move|trend", re.I)
STAGING_WORDS = re.compile(r"\b(stage|staging|sicr|re-?stag\w*|migrat\w*)\b", re.I)
SIZE_IN = re.compile(r"\d")
STAGING_PHRASE = re.compile(r",?\s*(and\s+)?(have|has|with|including|include)\s+(the\s+|a\s+|its\s+)?"
                            r"(stage|staging|sicr|re-?stag\w*)\b[^,.;]*", re.I)


@dataclass
class Part:
    kind: str                  # question | statement
    text: str
    topic: str = ""            # collateral_size | pd_qoq | "" (the agent answers)


@dataclass
class Message:
    parts: list[Part] = field(default_factory=list)

    @property
    def questions(self) -> list[Part]:
        return [p for p in self.parts if p.kind == "question"]

    @property
    def statements(self) -> list[Part]:
        return [p for p in self.parts if p.kind == "statement"]

    @property
    def mixed(self) -> bool:
        """True when the message must be answered part by part: a question plus a scenario, or several questions."""
        scen = [p for p in self.statements if LEVER_WORDS.search(p.text)]
        return (bool(self.questions) and bool(scen)) or len(self.questions) >= 2


def topic_of(q: str) -> str:
    if COLLATERAL_Q.search(q) and SIZE_Q.search(q):
        return "collateral_size"
    if PD_Q.search(q) and QOQ_Q.search(q):
        return "pd_qoq"
    return ""


def split(text: str) -> Message:
    """Sentences, each a question or a statement. A question ends in '?' or opens with a question word."""
    raw = re.split(r"(?<=[?!])\s+|(?<=\.)\s+(?=[A-Za-z])|\n+|;\s*", (text or "").strip())
    parts: list[Part] = []
    for chunk in raw:
        c = chunk.strip().strip(".").strip()
        if not c or c.startswith("::"):
            continue
        is_q = c.endswith("?") or bool(QUESTION_START.match(c))
        parts.append(Part("question" if is_q else "statement", c, topic_of(c) if is_q else ""))
    return Message(parts)


def scenario_text(msg: Message, collateral_pct: float | None) -> str:
    """The statements as one scenario sentence; an open-sized collateral cut gets the recommended size."""
    out = []
    for p in msg.statements:
        # "and have stage implication" / "with the staging effect": the engine always re-stages; not a lever to read.
        t = STAGING_PHRASE.sub("", p.text).strip(" ,")
        if not t:
            continue
        if collateral_pct is not None and COLLATERAL_Q.search(t):
            # Per clause: "cut collateral and raise PD by 10%" sizes the collateral clause, not the PD one.
            bits = re.split(r"(\s+and\s+|,\s*)", t)
            for i, b in enumerate(bits):
                if COLLATERAL_Q.search(b) and not SIZE_IN.search(b):
                    nb = re.sub(r"(?i)\b(reduce|cut|lower|drop|decrease|shock)\s+(the\s+)?collateral(\s+values?)?",
                                f"reduce collateral by {abs(collateral_pct):g}%", b)
                    bits[i] = nb if SIZE_IN.search(nb) else f"{b} (collateral -{abs(collateral_pct):g}%)"
            t = "".join(bits)
        out.append(t)
    return ". ".join(out)


def open_collateral(text: str) -> bool:
    """A collateral cut with no size of its own (clause by clause)."""
    return any(COLLATERAL_Q.search(b) and not SIZE_IN.search(b) for b in re.split(r"\s+and\s+|,\s*", text))


def wants_staging(msg: Message) -> bool:
    return any(STAGING_WORDS.search(p.text) for p in msg.statements)


# ------------------------------------------------------------------ the history answerers

def _quarter_periods(book: str) -> list[str]:
    """The book's periods at a quarterly step (corporate is quarterly; retail monthly: every third month back from as-of)."""
    ps = dstore.periods(book)
    if book == "corporate":
        return ps
    return ps[::-1][::3][::-1]


def _scoped(book: str, cols: list[str], cohort_ids: set[str] | None) -> pd.DataFrame:
    h = dstore.history(book, ["exposure_id", "segment", *cols])
    if cohort_ids:
        h = h[h["exposure_id"].isin(cohort_ids)]
    return h[h["period"].isin(_quarter_periods(book))]


def _round_up(x: float, step: float = 5.0) -> float:
    return float(step * math.ceil(abs(x) / step)) if x else 0.0


def collateral_history(book: str, cohort_ids: set[str] | None = None) -> dict[str, Any]:
    """Quarter-on-quarter change of collateral value by segment (same exposures in both quarters), its distribution,
    and a recommended shock size: the 5th percentile of 4-quarter changes, rounded up to 5%, kept within 10–40%
    (and no milder than the worst annual fall of Saudi real estate prices when that is the larger)."""
    h = _scoped(book, ["collateral_value"], cohort_ids)
    h = h[h["collateral_value"] > 0]
    ps = sorted(h["period"].unique())
    rows: list[dict[str, Any]] = []
    for a, b in zip(ps, ps[1:]):
        x = h[h["period"] == a].set_index("exposure_id")[["segment", "collateral_value"]]
        y = h[h["period"] == b].set_index("exposure_id")["collateral_value"]
        both = x.join(y.rename("after"), how="inner")
        for seg, g in both.groupby("segment"):
            v0 = float(g["collateral_value"].sum())
            if v0 > 0:
                rows.append({"segment": seg, "period": b, "change_pct": (float(g["after"].sum()) / v0 - 1) * 100})
    qq = pd.DataFrame(rows, columns=["segment", "period", "change_pct"])
    table: list[dict[str, Any]] = []
    annual: list[float] = []
    for seg, g in qq.groupby("segment"):
        s = g.sort_values("period")["change_pct"]
        yr = ((1 + s / 100).rolling(4).apply(np.prod, raw=True) - 1) * 100
        annual.extend(float(v) for v in yr.dropna())
        table.append({"segment": seg, "quarters": int(len(s)), "avg_qoq_change_pct": float(s.mean()),
                      "worst_qoq_change_pct": float(s.min()), "best_qoq_change_pct": float(s.max()),
                      "worst_4q_change_pct": float(yr.min()) if yr.notna().any() else float(s.min())})
    table.sort(key=lambda r: r["worst_4q_change_pct"])
    allq = qq["change_pct"].to_numpy()
    dist = {k: float(np.percentile(allq, q)) for k, q in (("p5", 5), ("p25", 25), ("median", 50), ("p75", 75), ("p95", 95))} \
        if len(allq) else {}
    p5_annual = float(np.percentile(annual, 5)) if annual else (dist.get("p5", 0.0) * 4)
    re_worst = _worst_re_price_fall()
    base = min(p5_annual, 0.0)
    rec = _round_up(base)
    note = f"the 5th percentile of 4-quarter collateral changes in the book ({p5_annual:+.1f}%)"
    if re_worst is not None and re_worst < 0 and _round_up(re_worst) > rec:
        rec = _round_up(re_worst)
        note = (f"the worst annual fall of Saudi real estate prices on record ({re_worst:+.1f}%, {_RE_YEAR[0]}), "
                f"harsher than the book's own 4-quarter 5th percentile ({p5_annual:+.1f}%)")
    rec = float(min(max(rec, 10.0), 40.0))
    return {"book": book, "periods": ps, "by_segment": table, "distribution": dist, "p5_4q_pct": p5_annual,
            "re_price_worst_pct": re_worst, "recommended_pct": -rec, "basis": note,
            "observations": int(len(allq))}


_RE_YEAR: list[str] = [""]


def _worst_re_price_fall() -> float | None:
    try:
        t = mev.annual_table()
        s = t[(t["series"] == "re_price") & (t["kind"] == "history")].sort_values("year")
        if len(s) < 2:
            return None
        ch = s["value"].pct_change() * 100
        i = ch.idxmin()
        _RE_YEAR[0] = str(int(s.loc[i, "year"]))
        return float(ch.min())
    except Exception:  # noqa: BLE001 - the MEV table is optional for this answer
        return None


def pd_quarterly(book: str, cohort_ids: set[str] | None = None) -> dict[str, Any]:
    """EAD-weighted 12-month PD by segment and quarter (performing exposures), its quarter-on-quarter change:
    the average relative change (%) and the average absolute change (bps), by segment and for the book."""
    h = _scoped(book, ["pd_12m", "ead", "stage"], cohort_ids)
    h = h[(h["stage"] < 3) & (h["ead"] > 0)].copy()
    h["w"] = h["pd_12m"] * h["ead"]
    seg = h.groupby(["segment", "period"]).agg(w=("w", "sum"), ead=("ead", "sum")).reset_index()
    seg["pd"] = seg["w"] / seg["ead"]
    book_pd = h.groupby("period").agg(w=("w", "sum"), ead=("ead", "sum"))
    book_pd["pd"] = book_pd["w"] / book_pd["ead"]

    def moves(s: pd.Series) -> tuple[pd.Series, pd.Series]:
        s = s.sort_index()
        return (s / s.shift(1) - 1).dropna() * 100, (s - s.shift(1)).dropna() * 10000

    rows = []
    for name, g in seg.groupby("segment"):
        rel, bp = moves(g.set_index("period")["pd"])
        if not len(rel):
            continue
        rows.append({"segment": name, "pd_latest_pct": float(g.sort_values("period")["pd"].iloc[-1] * 100),
                     "avg_qoq_change_pct": float(rel.mean()), "avg_qoq_change_bps": float(bp.mean()),
                     "latest_qoq_change_pct": float(rel.iloc[-1]), "worst_qoq_change_pct": float(rel.max()),
                     "quarters": int(len(rel))})
    rows.sort(key=lambda r: -r["avg_qoq_change_pct"])
    rel, bp = moves(book_pd["pd"])
    overall = {"segment": "Whole book", "pd_latest_pct": float(book_pd["pd"].sort_index().iloc[-1] * 100),
               "avg_qoq_change_pct": float(rel.mean()) if len(rel) else 0.0,
               "avg_qoq_change_bps": float(bp.mean()) if len(bp) else 0.0,
               "latest_qoq_change_pct": float(rel.iloc[-1]) if len(rel) else 0.0,
               "worst_qoq_change_pct": float(rel.max()) if len(rel) else 0.0, "quarters": int(len(rel))}
    return {"book": book, "periods": sorted(book_pd.index), "by_segment": rows, "overall": overall,
            "positive_quarters": int((rel > 0).sum()), "series": [{"period": p, "pd_pct": float(v * 100)}
                                                                  for p, v in book_pd["pd"].sort_index().items()]}


__all__ = ["Part", "Message", "split", "topic_of", "scenario_text", "wants_staging", "collateral_history",
           "pd_quarterly"]
