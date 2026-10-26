"""R14 E (K18 #5): the verdict line names the critical and major findings behind it."""
from __future__ import annotations

from typing import Any


def _short(t: str, n: int = 70) -> str:
    t = str(t)
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def _pct(x: Any) -> str:
    return f"{float(x) * 100:.1f}%" if isinstance(x, (int, float)) else "n/a"


def _reason(f: dict[str, Any]) -> str:
    """One finding as a short reason inside the story sentence (lower-case start, no trailing period)."""
    if f.get("code") == "CAPACITY" and isinstance(f.get("ask"), (int, float)) and isinstance(f.get("capacity"), (int, float)):
        if f["capacity"] <= 0:
            return "its cash flow can carry no new debt"
        return f"the ask is {f['ask'] / f['capacity']:.1f}× what its cash flow can carry"
    t = str(f.get("title") or "").rstrip(".")
    if t.startswith("Bureau not clear: SIMAH flag "):
        t = "SIMAH flag " + t.split("SIMAH flag ", 1)[1].replace(" on the proposal record", "")
    return (t[:1].lower() + t[1:]) if t[:2] != t[:2].upper() else t


def story(findings: list[dict[str, Any]], metrics: dict[str, Any] | None) -> str:
    """R15 b (L13 (1)): the ONE sentence that reconciles price and verdict, read by the banner and the RAROC tile.

    "Profitable (19.6% vs 16.0%) but not approvable: the ask is 1.6× what its cash flow can carry, SIMAH flag adverse,
    connected party classified, 8 documents missing."
    """
    m = metrics or {}
    r, h = m.get("lifetime_raroc"), m.get("hurdle")
    clears = bool(m.get("clears_hurdle")) if "clears_hurdle" in m else (isinstance(r, (int, float)) and isinstance(h, (int, float)) and r >= h)
    price = f"Profitable ({_pct(r)} vs {_pct(h)} hurdle)" if clears else f"Not profitable enough ({_pct(r)} vs {_pct(h)} hurdle)"
    open_ = [f for f in findings if f.get("status", "open") == "open"]
    crit = [f for f in open_ if f.get("severity") == "critical"]
    maj = [f for f in open_ if f.get("severity") == "major" and f.get("category") != "documents"]
    docs = [f for f in open_ if f.get("category") == "documents"]
    reasons = [_reason(f) for f in crit[:3]] + [_reason(f) for f in maj[: max(0, 3 - len(crit[:3]))]]
    reasons = list(dict.fromkeys(x for x in reasons if x))
    if docs:
        reasons.append(f"{len(docs)} document{'s' if len(docs) != 1 else ''} missing")
    if crit:
        link = "but not approvable as proposed" if clears else "and not approvable as proposed"
    elif maj:
        link = "and approvable with conditions" if clears else "; approvable only with conditions and better pricing"
    else:
        return f"{price} and approvable as proposed." + ("" if clears else " Pricing must reach the hurdle first.")
    return f"{price} {link}: {', '.join(reasons)}." if reasons else f"{price} {link}."


def verdict(pid: str, findings: list[dict[str, Any]], cap: dict[str, Any] | None = None,
            metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    open_ = [f for f in findings if f.get("status", "open") == "open"]
    crit = [f for f in open_ if f["severity"] == "critical"]
    maj = [f for f in open_ if f["severity"] == "major"]
    not_cur = [f for f in crit + maj if (f.get("cure") or {}).get("kind") == "not_curable"]
    if crit:
        decision, tone = "Do not approve as proposed", "negative"
    elif maj:
        decision, tone = "Approve with conditions", "warning"
    else:
        decision, tone = "Approve as proposed", "positive"
    named = "; ".join(_short(f["title"], 120) for f in crit[:4])
    if len(crit) > 4:
        named += f"; and {len(crit) - 4} more critical"
    maj_named = "; ".join(_short(f["title"], 60) for f in maj[:2])
    head = decision
    if crit:
        head += f": {len(crit)} critical — {named}"
        if maj:
            head += f". {len(maj)} major, incl. {maj_named}"
    elif maj:
        head += f": {len(maj)} major — {maj_named}" + (f" and {len(maj) - 2} more" if len(maj) > 2 else "")
    else:
        head += ": no critical or major finding"
    if not_cur:
        head += f". {len(not_cur)} not curable by structure"
    return {"decision": decision, "tone": tone, "headline": head + ".", "critical": [f["id"] for f in crit], "major": [f["id"] for f in maj],
            "not_curable": [f["id"] for f in not_cur],
            "story": story(findings, metrics),
            "price_only": "RAROC measures price only: whether the deal earns the hurdle on its capital. Approval also needs "
                          "capacity, bureau, connected parties and documents to pass; the verdict reads every finding.",
            "rule": "Any open critical finding: do not approve as proposed; any major: approve with conditions; otherwise approve."}
