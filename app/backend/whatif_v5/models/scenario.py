"""A What-If scenario: an ordered list of steps, each with its own scope and shocks.

A step keeps the user's words verbatim and the restatement the assistant
gave; it never stores results (every run recomputes from the steps). Each
step keeps its OWN scope: a Construction PD shock and a Real Estate LGD shock
in one scenario shock only their own sectors (5318 merged them; v5 does not).

Shock kinds and units
  pd        mode relative (%), pp, bps          "increase PD by 30%", "PD +2pp", "+50bps"
  lgd       mode pp, relative (%)               "LGD +5pp", "LGD up 10%"
  ccf       mode pp, relative (%), ead_pct      "CCF +10pp", "EAD +5%"
  collateral  % change in collateral market value  "reduce collateral by 20%"
  haircut   pp change in the collateral haircut  "haircuts +10pp"
            (both flow through the collateral LGD channel: LGD + unsecured LGD x lost secured share)
  rating    notches (+ = downgrade)             "downgrade by 2 notches"
  sector    severity in cycle-index sd (> 0 = stress)   "Construction sector stress", "severe sector stress"
  mev       {series: move} in the series unit   "oil price -40%", "repo +200bps", "unemployment +2pp"
  stage     share of a stage moved (%), from -> to   "move 10% of Stage 1 to Stage 2"
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from backend.whatif_v5.domain import mev

DRIVERS = ("pd", "lgd", "collateral", "ccf", "staging", "rating", "sector", "mev")
DRIVER_LABELS = {"pd": "PD", "lgd": "LGD", "collateral": "Collateral", "ccf": "CCF / EAD", "staging": "Staging",
                 "rating": "Rating", "sector": "Sector", "mev": "Macro (MEV)"}
LIMITS = {"pd_relative": (-90.0, 1000.0), "pd_pp": (-50.0, 50.0), "pd_bps": (-5000.0, 5000.0),
          "lgd_pp": (-60.0, 60.0), "lgd_relative": (-90.0, 200.0), "ccf_pp": (-100.0, 100.0),
          "ccf_relative": (-90.0, 300.0), "ead_pct": (-90.0, 300.0), "rating": (-10, 10),
          "sector": (-4.0, 4.0), "stage_share": (0.0, 100.0), "collateral": (-100.0, 200.0), "haircut": (-50.0, 90.0)}
MEV_LIMITS = {"pp": (-30.0, 30.0), "bps": (-2000.0, 2000.0), "pct": (-95.0, 300.0)}


class ShockError(ValueError):
    pass


@dataclass
class Scope:
    segments: list[str] = field(default_factory=list)
    subsegments: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    exposures: list[str] = field(default_factory=list)
    stages: list[int] = field(default_factory=list)
    grades: list[str] = field(default_factory=list)

    def is_book(self) -> bool:
        return not any((self.segments, self.subsegments, self.products, self.owners, self.exposures,
                        self.stages, self.grades))

    def to_dict(self) -> dict[str, Any]:
        return {k: list(v) for k, v in self.__dict__.items() if v}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Scope":
        d = dict(d or {})
        return cls(segments=[str(x) for x in d.get("segments", [])],
                   subsegments=[str(x) for x in d.get("subsegments", [])],
                   products=[str(x) for x in d.get("products", [])],
                   owners=[str(x).upper() for x in d.get("owners", [])],
                   exposures=[str(x).upper() for x in d.get("exposures", [])],
                   stages=[int(x) for x in d.get("stages", [])],
                   grades=[str(x) for x in d.get("grades", [])])

    def describe(self, labels: dict[str, str]) -> str:
        if self.is_book():
            return "the whole book in scope"
        parts = []
        if self.segments:
            parts.append(", ".join(self.segments))
        if self.subsegments:
            parts.append(", ".join(self.subsegments))
        if self.products and self.products != self.segments:
            parts.append(", ".join(self.products))
        if self.owners:
            parts.append(f"{labels.get('owner', 'owner').lower()} " + ", ".join(self.owners))
        if self.exposures:
            parts.append(f"{labels.get('exposure', 'exposure').lower()} " + ", ".join(self.exposures))
        if self.stages:
            parts.append("Stage " + "/".join(str(s) for s in self.stages))
        if self.grades:
            parts.append("grades " + ", ".join(self.grades))
        return "; ".join(parts)


@dataclass
class Shocks:
    pd: dict[str, float] | None = None          # {"mode": relative|pp|bps, "value": x}
    lgd: dict[str, float] | None = None         # {"mode": pp|relative, "value": x}
    ccf: dict[str, float] | None = None         # {"mode": pp|relative, "value": x}
    ead: float = 0.0                            # EAD % change
    collateral: float = 0.0                     # collateral market value % change
    haircut: float = 0.0                        # haircut pp change
    rating: int = 0
    sector: float = 0.0
    mev: dict[str, float] = field(default_factory=dict)
    stage: list[dict[str, Any]] = field(default_factory=list)   # [{"from":1,"to":2,"share":10}]
    horizon: int = 0                            # R10 C1: years the macro shock lasts on the 5-year path (0 = all 5)

    def drivers(self) -> set[str]:
        out = set()
        if self.pd and self.pd.get("value"):
            out.add("pd")
        if self.lgd and self.lgd.get("value"):
            out.add("lgd")
        if (self.ccf and self.ccf.get("value")) or self.ead:
            out.add("ccf")
        if self.collateral or self.haircut:
            out.add("collateral")
        if self.rating:
            out.add("rating")
        if self.sector:
            out.add("sector")
        if any(self.mev.values()):
            out.add("mev")
        if self.stage:
            out.add("staging")
        return out

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for k in ("pd", "lgd", "ccf"):
            v = getattr(self, k)
            if v and v.get("value"):
                d[k] = {"mode": v["mode"], "value": float(v["value"])}
        if self.ead:
            d["ead"] = float(self.ead)
        if self.collateral:
            d["collateral"] = float(self.collateral)
        if self.haircut:
            d["haircut"] = float(self.haircut)
        if self.rating:
            d["rating"] = int(self.rating)
        if self.sector:
            d["sector"] = float(self.sector)
        if any(self.mev.values()):
            d["mev"] = {k: float(v) for k, v in sorted(self.mev.items()) if v}
        if self.stage:
            d["stage"] = [dict(s) for s in self.stage]
        if self.horizon:
            d["horizon"] = int(self.horizon)
        return d

    def scaled(self, factor: float) -> "Shocks":
        """Intensity: every shock times `factor` (notches rounded, at least one notch kept)."""
        s = copy.deepcopy(self)
        for k in ("pd", "lgd", "ccf"):
            v = getattr(s, k)
            if v:
                v["value"] = float(v["value"]) * factor
        s.ead = s.ead * factor
        s.collateral = max(-100.0, s.collateral * factor)
        s.haircut = s.haircut * factor
        if s.rating:
            r = int(round(s.rating * factor))
            s.rating = r if r else (1 if s.rating > 0 else -1)
        s.sector = s.sector * factor
        s.mev = {k: v * factor for k, v in s.mev.items()}
        s.stage = [{**m, "share": min(100.0, float(m["share"]) * factor)} for m in s.stage]
        return s


def parse_shocks(d: dict[str, Any] | None) -> Shocks:
    d = dict(d or {})
    s = Shocks()
    for k, modes in (("pd", ("relative", "pp", "bps")), ("lgd", ("pp", "relative")), ("ccf", ("pp", "relative", "ead_pct"))):
        v = d.get(k)
        if v:
            mode = str(v.get("mode", "")).lower()
            if mode not in modes:
                raise ShockError(f"{k.upper()} shock mode '{mode}' is not one of {', '.join(modes)}.")
            value = float(v.get("value", 0))
            lim = LIMITS[f"{k}_{mode}"] if f"{k}_{mode}" in LIMITS else LIMITS["ead_pct"]
            if not lim[0] <= value <= lim[1]:
                raise ShockError(f"{k.upper()} {value:+g} ({mode}) is outside the allowed range {lim[0]:g} to {lim[1]:g}.")
            setattr(s, k, {"mode": mode, "value": value})
    if d.get("ead"):
        v = float(d["ead"])
        if not LIMITS["ead_pct"][0] <= v <= LIMITS["ead_pct"][1]:
            raise ShockError(f"EAD {v:+g}% is outside -90% to +300%.")
        s.ead = v
    for k, word in (("collateral", "Collateral value"), ("haircut", "Haircut")):
        if d.get(k):
            v = float(d[k])
            lo, hi = LIMITS[k]
            if not lo <= v <= hi:
                raise ShockError(f"{word} {v:+g}{'%' if k == 'collateral' else 'pp'} is outside {lo:g} to {hi:g}.")
            setattr(s, k, v)
    if d.get("rating"):
        r = int(d["rating"])
        if not LIMITS["rating"][0] <= r <= LIMITS["rating"][1]:
            raise ShockError(f"{r} notches is outside -10 to +10.")
        s.rating = r
    if d.get("sector"):
        v = float(d["sector"])
        if not LIMITS["sector"][0] <= v <= LIMITS["sector"][1]:
            raise ShockError("Sector stress is between -4 and +4 standard deviations of the cycle index.")
        s.sector = v
    for k, v in (d.get("mev") or {}).items():
        if k not in mev.BY_KEY:
            raise ShockError(f"'{k}' is not one of the MEVs: {', '.join(mev.BY_KEY)}.")
        unit = mev.BY_KEY[k].shock_unit
        lo, hi = MEV_LIMITS[unit]
        if not lo <= float(v) <= hi:
            raise ShockError(f"{mev.BY_KEY[k].name} {float(v):+g} {unit} is outside {lo:g} to {hi:g}.")
        s.mev[k] = float(v)
    for m in d.get("stage") or []:
        frm, to, share = int(m.get("from", 1)), int(m.get("to", 2)), float(m.get("share", 0))
        if (frm, to) not in ((1, 2), (2, 3), (1, 3), (2, 1)):
            raise ShockError(f"Stage {frm} to Stage {to} is not a migration What-If applies.")
        if not 0 < share <= 100:
            raise ShockError("A stage migration share is between 0 and 100%.")
        s.stage.append({"from": frm, "to": to, "share": share})
    if d.get("horizon"):
        h = int(d["horizon"])
        if not 1 <= h <= 5:
            raise ShockError("The scenario horizon is 1 to 5 years (the length of the macro paths).")
        s.horizon = h
    return s


@dataclass
class Step:
    instruction: str
    restatement: str
    shocks: Shocks
    scope: Scope

    def to_dict(self) -> dict[str, Any]:
        return {"instruction": self.instruction, "restatement": self.restatement,
                "shocks": self.shocks.to_dict(), "scope": self.scope.to_dict()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Step":
        return cls(instruction=str(d.get("instruction", "")), restatement=str(d.get("restatement", "")),
                   shocks=parse_shocks(d.get("shocks")), scope=Scope.from_dict(d.get("scope")))


@dataclass
class Scenario:
    domain: str
    period: str
    steps: list[Step]
    name: str = ""
    cohort_id: str = ""        # an Early Warning cohort: the population in scope

    def drivers(self) -> set[str]:
        out: set[str] = set()
        for s in self.steps:
            out |= s.shocks.drivers()
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"domain": self.domain, "period": self.period, "name": self.name, "cohort_id": self.cohort_id,
                "steps": [s.to_dict() for s in self.steps]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Scenario":
        return cls(domain=str(d["domain"]), period=str(d["period"]), name=str(d.get("name", "")),
                   cohort_id=str(d.get("cohort_id", "")), steps=[Step.from_dict(s) for s in d.get("steps", [])])

    def key(self) -> str:
        body = {k: v for k, v in self.to_dict().items() if k != "name"}
        for s in body["steps"]:
            s.pop("instruction", None)
            s.pop("restatement", None)
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def describe_shocks(sh: Shocks, labels: dict[str, str]) -> list[str]:
    out = []
    if sh.pd:
        m, v = sh.pd["mode"], sh.pd["value"]
        out.append(f"PD {v:+g}%" if m == "relative" else f"PD {v:+g}pp" if m == "pp" else f"PD {v:+g}bps")
    if sh.lgd:
        out.append(f"LGD {sh.lgd['value']:+g}pp" if sh.lgd["mode"] == "pp" else f"LGD {sh.lgd['value']:+g}%")
    if sh.ccf:
        m, v = sh.ccf["mode"], sh.ccf["value"]
        out.append(f"CCF {v:+g}pp" if m == "pp" else f"CCF {v:+g}%" if m == "relative" else f"EAD {v:+g}%")
    if sh.ead:
        out.append(f"EAD {sh.ead:+g}%")
    if sh.collateral:
        out.append(f"collateral value {sh.collateral:+g}%")
    if sh.haircut:
        out.append(f"collateral haircut {sh.haircut:+g}pp")
    if sh.rating:
        word = labels.get("grade_notch", "notch")
        n = abs(sh.rating)
        out.append(f"{'downgrade' if sh.rating > 0 else 'upgrade'} {n} {word}{'es' if n != 1 and word.endswith('ch') else 's' if n != 1 else ''}")
    if sh.sector:
        out.append(f"{labels.get('segment', 'sector').lower()} stress {sh.sector:+.1f} sd of the cycle index")
    for k, v in sorted(sh.mev.items()):
        s = mev.BY_KEY[k]
        unit = {"pp": "pp", "bps": "bps", "pct": "%"}[s.shock_unit]
        out.append(f"{s.name} {v:+g}{unit}")
    for m in sh.stage:
        out.append(f"{m['share']:g}% of Stage {m['from']} to Stage {m['to']}")
    if sh.horizon:
        out.append(f"horizon {sh.horizon} year{'s' if sh.horizon != 1 else ''}")
    return out
