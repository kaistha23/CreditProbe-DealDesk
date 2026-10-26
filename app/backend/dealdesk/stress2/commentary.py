"""The 100-200-word Stress Lab commentary above the grid (I22-1, O3): the verdict, what breaks first and at what
severity, the driver, how far the deal is from failure, and what to do.

Deterministic (N6): this writer produces the complete text from the run alone; the tests check this path. A model
may only polish it when ANTHROPIC_API_KEY is present (the Mac Keychain) and `polish=True`; any failure returns the
deterministic text unchanged.
"""
from __future__ import annotations

import os
import re
from typing import Any

from backend.dealdesk import stress_lab as sl

MIN_WORDS, MAX_WORDS = 100, 200

FIX = {
    "revenue": "a DSCR covenant with a cash sweep, a shorter tenor or a lower amount",
    "margin": "a margin-linked covenant and a cash sweep",
    "customer": "an assignment of the largest customer's receivables and a concentration covenant",
    "payment_delay": "a receivables-ageing covenant and a working-capital sub-limit",
    "project_delay": "drawdowns against certified payment certificates and a retention account",
    "rates": "a fixed rate or a hedge",
    "collateral": "more security, a lower LTV or a top-up clause",
    "rating": "a rating-linked margin ratchet and a review clause",
    "guarantee": "a clean legal opinion and an on-demand guarantee",
    "dscr": "a lower amount or a longer amortisation so DSCR clears its limit before any stress",
    "pricing": "a higher margin or fees, or security that lowers the capital charge",
}


def _cell(c: str) -> str:
    return {"covenants": "a covenant", "limits": "a limit", "stage": "Stage 1", "rating": "the minimum rating",
            "raroc": "the RAROC hurdle"}.get(c, sl.CELL_LABELS[c])


def _lc(s: str) -> str:
    """Lower-case the first letter unless the word is an acronym (EBITDA, DSCR, RAROC)."""
    return s if len(s) > 1 and s[1].isupper() else s[:1].lower() + s[1:]


def _and(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def words(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9−\-+.%]+", s))


def _p(v: Any) -> str:
    return "–" if v is None else sl._m(f"{float(v) * 100:.1f}%")


def _x(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "–"
    return "n/m" if f != f or abs(f) == float("inf") else f"{f:.2f}x"


def write(out: dict[str, Any], polish: bool = False) -> dict[str, Any]:
    v, tier, rv, base = out["verdict"], out["tier"], out.get("reverse"), out["base"]
    rows = [r for r in out["rows"] if r["applicable"]]
    bm = base["metrics"]
    s: list[tuple[str, bool]] = []  # (sentence, essential)
    s.append((f"Verdict: {v['verdict']}. {out['obligor']} on the {out['structure']['label'].lower()} structure was run through "
              f"{len(rows)} scenarios across {len(out['families'])} families; "
              f"{out['counts']['breaking']} break a test.", True))
    fb = v.get("first_break")
    if fb and fb["id"] == "base":
        s.append((f"Before any stress the structure already fails {_and([_cell(c) for c in fb['tests']])}, "
                  f"so it cannot be recommended as asked.", True))
    elif fb:
        s.append((f"What breaks first: {fb['label']}, a {fb['severity']} shock, breaks {_and([_cell(c) for c in fb['tests']])}.", True))
    else:
        s.append(("Nothing breaks: every applicable scenario, the combined severe case included, keeps DSCR, covenants, stage, "
                  "RAROC and limits inside their tests.", True))
    if v["driver_labels"]:
        dl = [_lc(d) for d in v["driver_labels"]]
        s.append((f"The driver{'s are' if len(dl) > 1 else ' is'} {_and(dl)}.", True))
    if rv and rv.get("headline"):
        s.append((rv["headline"], True))
    cs = next((r for r in rows if r["id"] == "combined_severe"), None)
    if cs:
        what = ("trade disruption: non-oil slowdown, revenue, margin, payment delays and funding cost, oil held at today's level"
                if "trade disruption" in str(cs.get("label", "")).lower()   # R14 m (K12): the regime's combined rows
                else "oil, rates, sector, collateral and revenue together")
        s.append((f"The combined severe case ({what}) gives DSCR {_x(cs['metrics']['dscr'])}, "
                  f"Stage {cs['metrics']['stage']} and RAROC {_p(cs['metrics']['lifetime_raroc'])} against {_p(bm['hurdle'])}.", False))
    n3 = next((r for r in rows if r["id"] == "notch_3"), None)
    if n3 and n3.get("raroc_check"):
        c = n3["raroc_check"]
        s.append((f"At three notches down the checked RAROC is {_p(c['raroc'])} (PD, capital, ECL and pricing re-priced at "
                  f"{c['rating']}), from {_p(bm['lifetime_raroc'])} today.", False))
    act = {"Restructure": "What to do: restructure before committee",
           "Approve with enhanced monitoring": "What to do: approve with enhanced monitoring",
           "Approve, standard monitoring": "What to do: approve with standard monitoring",
           "Approve": "What to do: approve"}[v["verdict"]]
    fixes = [FIX[d] for d in v["drivers"] if d in FIX][:2]
    tail = f"; protect it with {' and '.join(fixes)}" if fixes and v["verdict"] != "Approve" else ""
    s.append((f"{act}{tail}. Monitoring tier {tier['tier']}, review every {tier['review_frequency_months']} months"
              + (f", with {len(tier['triggers'])} named trigger{'s' if len(tier['triggers']) != 1 else ''} "
                 f"({'; '.join(t['label'] for t in tier['triggers'][:2])})" if tier["triggers"] else "") + ".", True))
    na = out["counts"]["not_applicable"]
    if na:
        s.append((f"{na} scenario{'s do' if na != 1 else ' does'} not apply to this deal and {'are' if na != 1 else 'is'} shown as such.", False))
    s.append((f"Base: DSCR {_x(bm['dscr'])}, rating {bm['rating']}, RAROC {_p(bm['lifetime_raroc'])}.", False))
    text = _fit([x for x in s])
    det = text
    polished = None
    if polish and os.environ.get("ANTHROPIC_API_KEY"):
        polished = _polish(det)
    final = polished or det
    return {"text": final, "deterministic": det, "polished": bool(polished), "words": words(final),
            "verdict": v["verdict"], "tier": tier["tier"], "writer": "stress2.commentary (deterministic)" if not polished else "model polish"}


def _fit(sents: list[tuple[str, bool]]) -> str:
    keep = list(sents)
    text = " ".join(x for x, _ in keep)
    # too long: drop optional sentences from the end; still too long: shorten trigger lists
    while words(text) > MAX_WORDS and any(not e for _, e in keep):
        i = max(i for i, (_, e) in enumerate(keep) if not e)
        keep.pop(i)
        text = " ".join(x for x, _ in keep)
    if words(text) > MAX_WORDS:
        text = " ".join(re.sub(r" \(([^)]{60,})\)", "", x) for x, _ in keep)
    if words(text) < MIN_WORDS:
        text += (" Each row runs through the Deal Desk engine: revenue with operating leverage, DSCR and leverage after the deal, "
                 "a rating overlay, PD at the stressed grade, IFRS 9 stage, ECL and RAROC with capital and pricing at the stressed "
                 "rating. Open any row for its chain of numbers and sources.")
    if words(text) > MAX_WORDS:
        ws = text.split(" ")
        text = " ".join(ws[:MAX_WORDS]).rstrip(",;") + "."
    return text


def _polish(text: str) -> str | None:  # pragma: no cover - needs a key (the Mac); never in the cloud tests
    try:
        import anthropic  # type: ignore
        c = anthropic.Anthropic()
        r = c.messages.create(model=os.environ.get("CREDITPROBE_MODEL", "claude-sonnet-4-5"), max_tokens=400,
                              messages=[{"role": "user", "content": "Polish this credit stress commentary for a credit committee. Keep every number, "
                                         "the verdict and the order; 100-200 words; banker language; no new facts.\n\n" + text}])
        out = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
        return out if MIN_WORDS <= words(out) <= MAX_WORDS else None
    except Exception:  # noqa: BLE001
        return None
