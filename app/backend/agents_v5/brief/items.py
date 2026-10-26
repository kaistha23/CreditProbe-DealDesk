"""One brief line, whatever its source, and the personas that read the brief.

A line is a fact with its number, its source and where to act on it. Nothing here calls a model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SEVERITIES = ("critical", "high", "medium", "low")

#: The four "Viewing as" personas (I17) and what each brief is about (I13 point 4).
PERSONAS: dict[str, dict[str, str]] = {
    "cro": {"label": "CRO", "brief_title": "The bank",
            "voice": "what moved across the bank and what needs a decision"},
    "reviewer": {"label": "Credit reviewer", "brief_title": "Your review desk today",
                 "voice": "deals waiting for credit, queries and decisions due"},
    "rm": {"label": "Relationship manager", "brief_title": "Your clients today",
           "voice": "your deals, credit's queries, conditions and renewals"},
    "analyst": {"label": "Analyst", "brief_title": "Your work today",
                "voice": "assigned names, overdue reviews, data issues before the ECL run, RM questions"},
}

#: Identity roles (backend/identity_v5/directory.py) to personas. Unknown roles read the analyst brief.
ROLE_PERSONA: dict[str, str] = {
    "administrator": "cro", "head of risk": "cro", "head of credit": "cro", "chief risk officer": "cro",
    "chief credit officer": "cro", "cro": "cro", "cco": "cro",
    "corporate credit manager": "reviewer", "retail credit manager": "reviewer", "credit reviewer": "reviewer",
    "credit officer": "reviewer",
    "relationship manager": "rm", "rm": "rm",
    "credit analyst": "analyst", "credit analyst (corporate)": "analyst", "credit analyst (retail)": "analyst",
    "risk manager": "analyst", "model validation analyst": "analyst", "internal auditor": "analyst",
    "analyst": "analyst",
}


def persona_for(role: str | None, override: str | None = None) -> str:
    if override and override in PERSONAS:
        return override
    return ROLE_PERSONA.get(str(role or "").strip().lower(), "analyst")


@dataclass
class Item:
    id: str
    source: str            # machine key of the source (never shown)
    source_label: str      # banker words for the source
    module: str            # cockpit | ews | lenses | dealdesk | whatif | queries | regulatory | ecl | watch
    title: str             # the line itself: a fact with its number
    detail: str = ""
    severity: str = "medium"
    materiality_sar_mn: float | None = None
    due: str | None = None         # ISO date the action is due
    since: str | None = None       # period or date the fact appeared
    audiences: tuple[str, ...] = ("cro", "analyst", "reviewer", "rm")
    owner: str | None = None       # a person (display name) the item is assigned to
    kind: str = ""                 # sector_appetite | deal | breach | ... (decides the options)
    numbers: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    show_me: dict[str, str] = field(default_factory=dict)
    open: dict[str, str] = field(default_factory=dict)
    entity: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["audiences"] = list(self.audiences)
        return d


def num(label: str, value: float | int | None, unit: str = "", display: str = "",
        source: dict[str, Any] | None = None) -> dict[str, Any]:
    """A figure. `source` is its lineage (PLAN_R12 §0): {domain, relation, key (column -> value or list), period, column},
    the shape `backend.dealdesk.data.lineage.resolves` checks."""
    out = {"label": label, "value": value, "unit": unit, "display": display or fmt(value, unit)}
    if source:
        out["source"] = source
    return out


def src(domain: str, relation: str, key: dict[str, Any] | None = None, column: str = "", period: str = "") -> dict[str, Any]:
    return {"domain": domain, "relation": relation, "key": dict(key or {}), "period": period, "column": column}


def fmt(v: float | int | None, unit: str = "") -> str:
    """House format: SAR millions shown as m or bn; percentages to one decimal; counts with separators."""
    if v is None:
        return "–"
    if unit == "SAR mn":
        a = abs(float(v))
        sign = "−" if float(v) < -0.005 else ""
        if a >= 1000:
            return f"{sign}SAR {a / 1000:,.2f}bn"
        return f"{sign}SAR {a:,.2f}m" if a < 10 else f"{sign}SAR {a:,.1f}m"
    if unit == "%":
        return f"{float(v):.1f}%"
    if unit == "pp":
        return f"{float(v):+.1f}pp"
    if isinstance(v, float) and not float(v).is_integer():
        return f"{v:,.2f}"
    return f"{int(v):,}"


def fdate(v: str | None) -> str:
    """A date as a banker writes it: 29 Oct 2026 (the year dropped when it is this year's)."""
    from datetime import date
    try:
        d = date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return str(v or "")
    return d.strftime("%-d %b") if d.year == date.today().year else d.strftime("%-d %b %Y")
