"""R11 Session L: the book against every risk-appetite limit, before and after a pipeline selection (PLAN_R11 L3).

Every limit row of `risk_appetite.json` has three levels -- appetite, trigger and limit -- and a status:
green up to the trigger (flagged "above appetite" past the appetite), amber from the trigger to the limit,
red beyond the limit (reversed for floors). Values are measured on the live corporate book at the as-of
quarter (`portfolio.snapshot`, `portfolio.frames`) plus the engine's year-1 figures of each selected option.

`Space` turns a set of pipeline deals into one additive vector per option, so the optimiser and this view
measure a selection the same way: the aggregate vector is the sum of the chosen options' vectors, and every
limit value (shares, HHI, top-20, cost of risk, RAROC, budgets) is a function of the book plus that aggregate.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np

from backend.dealdesk import params, portfolio
from backend.dealdesk.seed import bucket
from backend.v5common.ratings import rank

BUCKETS = ("IG", "BB", "B", "CCC-C")
SUB_IG = ("BB", "B", "CCC-C")
UNSECURED_BOOK = ("none", "corporate_guarantee")
FIXED = ("ead", "rwa", "el", "pv_rap", "pv_cap", "unsecured", "stage2", "long", "islamic", "connected", "re_coll", "sub_ig", "rc")
DEAL_ROWS = ("min_rating", "max_tenor", "ltv", "dscr", "debt_ebitda", "balloon")

DEFINITIONS = {
    "single_name": "Largest obligor EAD (book plus selected new business) against the single obligor limit.",
    "group_connected": "Largest connected group EAD against the connected group limit.",
    "group_large_exposure": "Largest connected group EAD against 25% of Tier 1.",
    "sector_policy": "Largest sector share of the corporate book.",
    "sector_appetite": "Sector share against the sector's risk-appetite cap.",
    "rating_bucket": "Share of the book in each rating bucket.",
    "collateral_type": "Share of book EAD secured by real estate.",
    "min_rating": "Applies to each deal: the obligor's rating against the minimum for new money.",
    "max_tenor": "Applies to each deal: tenor against the matrix by rating bucket.",
    "ltv": "Applies to each real-estate deal: funded amount / market value.",
    "dscr": "Applies to each deal: EBITDA / (existing + new debt service).",
    "debt_ebitda": "Applies to each deal: (total debt + funded amount) / EBITDA.",
    "balloon": "Applies to each term loan: share repaid at maturity.",
    "bu_rwa_budget": "Year-1 RWA of the selected new business against the RWA budget.",
    "bu_el_budget": "Year-1 expected loss of the selected new business against the EL budget.",
    "top20_obligor_share": "EAD of the 20 largest obligors / book EAD.",
    "sector_hhi": "Sum of squared sector shares of the book (Herfindahl index).",
    "sub_ig_share": "EAD rated BB+ or worse / book EAD.",
    "unsecured_share": "EAD with no tangible collateral, cash margin or eligible guarantee / book EAD.",
    "re_construction_share": "(Real estate + construction EAD) / book EAD.",
    "long_tenor_share": "New-business EAD with tenor over 7 years / new-business EAD.",
    "stage2_share": "Stage 2 EAD / book EAD; a new deal counts by its Stage 2 weight.",
    "cost_of_risk_bps": "12-month expected loss on the performing book / book EAD, in bps.",
    "raroc_floor": "PV risk-adjusted profit / PV capital of the selected new business.",
    "region_share": "Largest region share of the book.",
    "connected_lending_share": "EAD to obligors in connected groups of two or more companies / book EAD.",
    "islamic_share": "Shariah-compliant new-business EAD / new-business EAD.",
}


def table() -> dict[str, Any]:
    return params.table("risk_appetite")


def limits() -> dict[str, dict[str, Any]]:
    return {x["name"]: x for x in params.rows("risk_appetite")}


def penalty_rate() -> float:
    return float(table().get("optimiser", {}).get("soft_penalty_rate", 0.02))


def levels(x: dict[str, Any], key: str | None = None) -> tuple[Any, Any, Any]:
    """(appetite, trigger, limit) of a row, for one key of a dict row."""
    if key is not None and "limits" in x:
        lim = x["limits"].get(key)
        return x.get("appetites", {}).get(key, lim), x.get("triggers", {}).get(key, lim), lim
    if "headroom_sar_mn" in x:
        return x.get("appetite_sar_mn", x["headroom_sar_mn"]), x.get("trigger_sar_mn", x["headroom_sar_mn"]), x["headroom_sar_mn"]
    if "limit_pct_tier1" in x:
        t1 = float(params.rows("capital")["tier1_sar_mn"])
        return (x.get("appetite_pct_tier1", x["limit_pct_tier1"]) * t1, x.get("trigger_pct_tier1", x["limit_pct_tier1"]) * t1,
                x["limit_pct_tier1"] * t1)
    lim = x.get("limit")
    return x.get("appetite", lim), x.get("trigger", lim), lim


def status(value: Any, appetite: Any, trigger: Any, limit: Any, direction: str = "max") -> str:
    if value is None or limit is None:
        return "n/a"
    if direction == "rating":
        v, t, lm = rank(value), rank(trigger), rank(limit)
        return "red" if v > lm else "amber" if v > t else "green"
    s = 1.0 if direction == "max" else -1.0
    v, t, lm = s * float(value), s * float(trigger), s * float(limit)
    return "red" if v > lm + 1e-12 else "amber" if v > t + 1e-12 else "green"


def above_appetite(value: Any, appetite: Any, direction: str = "max") -> bool:
    if value is None or appetite is None or direction == "rating":
        return False
    return float(value) > float(appetite) + 1e-12 if direction == "max" else float(value) < float(appetite) - 1e-12


# ------------------------------------------------------------------ the book

@functools.lru_cache(maxsize=1)
def book() -> dict[str, Any]:
    s = portfolio.snapshot()
    fr = portfolio.frames()
    f, b, c = fr["facility"], fr["borrower"], fr["collateral"]
    m = f.merge(c[["facility_id", "collateral_type"]], on="facility_id", how="left")
    m["ckey"] = m["collateral_type"].map(portfolio.COLLATERAL_KEY).fillna("none")
    size = b.groupby("connected_group_id")["borrower_id"].transform("nunique")
    connected = set(b.loc[size >= 2, "borrower_id"])
    T = float(s["total_ead"])
    ob = s["by_obligor"]
    return {
        "T": T, "el": float(s["el_12m_performing"]),
        "sector": {k: float(v) for k, v in s["by_sector"].items()},
        "bucket": {k: float(s["by_bucket"].get(k, 0.0)) for k in BUCKETS},
        "region": {k: float(v) for k, v in m.groupby("region")["ead_sar_mn"].sum().items()},
        "re_coll": float(s["by_collateral"].get("real_estate", 0.0)),
        "unsecured": float(m.loc[m["ckey"].isin(UNSECURED_BOOK), "ead_sar_mn"].sum()),
        "stage2": float(m.loc[m["stage"] == 2, "ead_sar_mn"].sum()),
        "connected": float(m.loc[m["borrower_id"].isin(connected), "ead_sar_mn"].sum()),
        "obligor": {k: float(v) for k, v in ob.items()}, "group": {k: float(v) for k, v in s["by_group"].items()},
        "group_names": s["group_names"], "as_of": s["as_of"], "release": s["release"],
    }


# ------------------------------------------------------------------ the selection space

class Space:
    """Additive vectors for the options of a set of deals (each deal: `deal` dict and `options` list)."""

    def __init__(self, deals: list[dict[str, Any]], rwa_budget: float | None = None, el_budget: float | None = None):
        self.B = book()
        self.L = limits()
        self.deals = deals
        bk = self.B
        self.sectors = sorted(set(bk["sector"]) | {d["deal"]["sector"] for d in deals})
        self.regions = sorted(set(bk["region"]) | {d["deal"]["region"] for d in deals if d["deal"]["region"]})
        self.obligors = sorted({d["deal"]["obligor_id"] for d in deals})
        self.groups = sorted({d["deal"]["group_id"] for d in deals if d["deal"]["group_id"]})
        names = list(FIXED) + [f"sec:{x}" for x in self.sectors] + [f"bk:{x}" for x in BUCKETS] + \
            [f"reg:{x}" for x in self.regions] + [f"ob:{x}" for x in self.obligors] + [f"gr:{x}" for x in self.groups]
        self.idx = {n: i for i, n in enumerate(names)}
        self.n = len(names)
        self.obligor_book = {}
        self.group_book = {}
        for d in deals:
            dd = d["deal"]
            self.obligor_book[dd["obligor_id"]] = float(bk["obligor"].get(dd["obligor_id"], 0.0)) if dd["existing"] else 0.0
            if dd["group_id"]:
                self.group_book[dd["group_id"]] = float(dd.get("group_book_ead", 0.0))
        rest = sorted((v for k, v in bk["obligor"].items() if k not in self.obligor_book), reverse=True)[:20]
        self.book_top = np.array(rest + [0.0] * (20 - len(rest)))
        self.rwa_budget = float(self.L["bu_rwa_budget"]["headroom_sar_mn"] if rwa_budget is None else rwa_budget)
        self.el_budget = float(self.L["bu_el_budget"]["headroom_sar_mn"] if el_budget is None else el_budget)
        self.V = [[self.vector(d["deal"], o) for o in d["options"]] for d in deals]
        self._hard()

    def vector(self, deal: dict[str, Any], o: dict[str, Any]) -> np.ndarray:
        v = np.zeros(self.n)
        i = self.idx
        e = float(o["ead"])
        long_years = int(self.L["long_tenor_share"].get("tenor_over_years", 7))
        v[i["ead"]], v[i["rwa"]], v[i["el"]] = e, float(o["rwa"]), float(o["el"])
        v[i["pv_rap"]], v[i["pv_cap"]] = float(o["pv_rap"]), float(o["pv_capital"])
        v[i["unsecured"]] = 0.0 if o["secured"] else e
        v[i["stage2"]] = e * float(o["stage2_weight"])
        v[i["long"]] = e if int(o["tenor_years"]) > long_years else 0.0
        v[i["islamic"]] = e if o["islamic"] else 0.0
        v[i["connected"]] = e if deal.get("connected") else 0.0
        v[i["re_coll"]] = e if "real_estate" in o["collateral_types"] else 0.0
        v[i["sub_ig"]] = e if deal["bucket"] in SUB_IG else 0.0
        v[i["rc"]] = e if deal["sector"] in self.L["re_construction_share"].get("sectors", ()) else 0.0
        v[i[f"sec:{deal['sector']}"]] = e
        v[i[f"bk:{deal['bucket']}"]] = e
        if deal["region"]:
            v[i[f"reg:{deal['region']}"]] = e
        v[i[f"ob:{deal['obligor_id']}"]] = e
        if deal["group_id"]:
            v[i[f"gr:{deal['group_id']}"]] = e
        return v

    # ---------------------------------------------------------------- hard limits as H @ agg <= b

    def _hard(self) -> None:
        bk, L, i = self.B, self.L, self.idx
        T = bk["T"]
        H, b, meta = [], [], []

        def add(coef: dict[str, float], bound: float, name: str, label: str, scope: str, unit: str, kind: str = "hard"):
            row = np.zeros(self.n)
            for k, c in coef.items():
                row[i[k]] += c
            H.append(row)
            b.append(bound)
            meta.append({"name": name, "label": label, "scope": scope, "unit": unit, "kind": kind})

        sn = float(L["single_name"]["limit"])
        for ob in self.obligors:
            before = self.obligor_book[ob]
            add({f"ob:{ob}": 1.0}, max(sn - before, 0.0), "single_name", L["single_name"]["label"], ob, "SAR m")
        gl = float(L["group_connected"]["limit"])
        le = levels(L["group_large_exposure"])[2]
        for g in self.groups:
            before = self.group_book[g]
            add({f"gr:{g}": 1.0}, max(gl - before, 0.0), "group_connected", L["group_connected"]["label"], g, "SAR m")
            add({f"gr:{g}": 1.0}, max(le - before, 0.0), "group_large_exposure", L["group_large_exposure"]["label"], g, "SAR m")
        sp = float(L["sector_policy"]["limit"])
        for sec in self.sectors:
            S = bk["sector"].get(sec, 0.0)
            lim = max(sp, S / T)  # a sector already past the limit may not get worse
            add({f"sec:{sec}": 1.0, "ead": -lim}, lim * T - S, "sector_policy", L["sector_policy"]["label"], sec, "share")
        rc = L["re_construction_share"]
        if rc["kind"] == "hard":
            S = sum(bk["sector"].get(s, 0.0) for s in rc["sectors"])
            lim = max(float(rc["limit"]), S / T)
            add({"rc": 1.0, "ead": -lim}, lim * T - S, "re_construction_share", rc["label"], "book", "share")
        add({"rwa": 1.0}, self.rwa_budget, "bu_rwa_budget", L["bu_rwa_budget"]["label"], "new business", "SAR m")
        add({"el": 1.0}, self.el_budget, "bu_el_budget", L["bu_el_budget"]["label"], "new business", "SAR m")
        self.H = np.array(H)
        self.b = np.array(b)
        self.hard_meta = meta

    # ---------------------------------------------------------------- measures

    @functools.cached_property
    def _ob_idx(self) -> tuple[np.ndarray, np.ndarray]:
        return (np.array([self.idx[f"ob:{o}"] for o in self.obligors], dtype=int),
                np.array([self.obligor_book[o] for o in self.obligors], dtype=float))

    def top20(self, agg: np.ndarray) -> float:
        ix, base = self._ob_idx
        allv = np.concatenate([self.book_top, base + agg[ix]])
        return float(np.partition(allv, len(allv) - 20)[-20:].sum()) if len(allv) > 20 else float(allv.sum())

    def measures(self, agg: np.ndarray) -> dict[str, Any]:
        """Every portfolio metric after the selection whose aggregate vector is `agg`."""
        bk, i = self.B, self.idx
        Tn = bk["T"] + agg[i["ead"]]
        nb = agg[i["ead"]]
        sec = {s: bk["sector"].get(s, 0.0) + agg[i[f"sec:{s}"]] for s in self.sectors}
        reg = {r: bk["region"].get(r, 0.0) + agg[i[f"reg:{r}"]] for r in self.regions}
        bkt = {k: bk["bucket"][k] + agg[i[f"bk:{k}"]] for k in BUCKETS}
        rc_s = self.L["re_construction_share"].get("sectors", [])
        return {
            "T": Tn, "nb_ead": nb, "rwa": agg[i["rwa"]], "el_nb": agg[i["el"]],
            "sector": {k: v / Tn for k, v in sec.items()}, "region": {k: v / Tn for k, v in reg.items()},
            "bucket": {k: v / Tn for k, v in bkt.items()},
            "hhi": float(sum((v / Tn) ** 2 for v in sec.values())),
            "top20": self.top20(agg) / Tn,
            "sub_ig": (sum(bk["bucket"][k] for k in SUB_IG) + agg[i["sub_ig"]]) / Tn,
            "unsecured": (bk["unsecured"] + agg[i["unsecured"]]) / Tn,
            "rc": (sum(bk["sector"].get(s, 0.0) for s in rc_s) + agg[i["rc"]]) / Tn,
            "re_coll": (bk["re_coll"] + agg[i["re_coll"]]) / Tn,
            "stage2": (bk["stage2"] + agg[i["stage2"]]) / Tn,
            "cor_bps": (bk["el"] + agg[i["el"]]) / Tn * 1e4,
            "connected": (bk["connected"] + agg[i["connected"]]) / Tn,
            "long": agg[i["long"]] / nb if nb > 0 else None,
            "islamic": agg[i["islamic"]] / nb if nb > 0 else None,
            "raroc": agg[i["pv_rap"]] / agg[i["pv_cap"]] if agg[i["pv_cap"]] > 0 else None,
            "pv_cap": agg[i["pv_cap"]],
            "obligor_max": max([self.obligor_book[o] + agg[i[f"ob:{o}"]] for o in self.obligors] + [float(self.book_top[0])]),
            "group": {g: self.group_book[g] + agg[i[f"gr:{g}"]] for g in self.groups},
        }

    def _soft_items(self, m: dict[str, Any]) -> list[tuple[str, str, float | None, dict[str, Any], str | None, float]]:
        """(name, scope, value, row, key, base) for every soft limit with a penalty."""
        L = self.L
        T = m["T"]
        out = []
        for s, lim in L["sector_appetite"]["limits"].items():
            out.append(("sector_appetite", s, m["sector"].get(s, 0.0), L["sector_appetite"], s, T))
        for k in BUCKETS:
            out.append(("rating_bucket", k, m["bucket"][k], L["rating_bucket"], k, T))
        out.append(("collateral_type", "real estate", m["re_coll"], L["collateral_type"], "real_estate", T))
        out.append(("top20_obligor_share", "book", m["top20"], L["top20_obligor_share"], None, T))
        out.append(("sector_hhi", "book", m["hhi"], L["sector_hhi"], None, T))
        out.append(("sub_ig_share", "book", m["sub_ig"], L["sub_ig_share"], None, T))
        out.append(("unsecured_share", "book", m["unsecured"], L["unsecured_share"], None, T))
        if L["re_construction_share"]["kind"] == "soft":
            out.append(("re_construction_share", "book", m["rc"], L["re_construction_share"], None, T))
        out.append(("long_tenor_share", "new business", m["long"], L["long_tenor_share"], None, m["nb_ead"]))
        out.append(("stage2_share", "book", m["stage2"], L["stage2_share"], None, T))
        out.append(("cost_of_risk_bps", "book", m["cor_bps"], L["cost_of_risk_bps"], None, T / 1e4))
        out.append(("raroc_floor", "new business", m["raroc"], L["raroc_floor"], None, m["pv_cap"]))
        for r, v in m["region"].items():
            out.append(("region_share", r, v, L["region_share"], None, T))
        out.append(("connected_lending_share", "book", m["connected"], L["connected_lending_share"], None, T))
        out.append(("islamic_share", "new business", m["islamic"], L["islamic_share"], None, m["nb_ead"]))
        return out

    @functools.cached_property
    def before(self) -> dict[str, Any]:
        return self.measures(np.zeros(self.n))

    @functools.cached_property
    def _before_soft(self) -> dict[tuple[str, str], float | None]:
        return {(n, s): v for n, s, v, *_ in self._soft_items(self.before)}

    @functools.cached_property
    def soft_linear(self) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """The soft-limit penalties that are linear inside max(0, .): penalty_r = rate * max(0, G[r] @ agg + c[r]).
        Every soft row except the HHI and the top-20 share (which are non-linear and >= 0) -- the solver's bound."""
        bk, L, i = self.B, self.L, self.idx
        T = bk["T"]
        G, c, names = [], [], []
        bs = self._before_soft

        def ref_of(name: str, scope: str, row: dict[str, Any], key: str | None) -> tuple[float | None, str]:
            a, t, lim = levels(row, key)
            d = row.get("direction", "max")
            b0 = bs.get((name, scope))
            if t is None:
                return None, d
            if d == "max":
                return (max(float(t), float(b0)) if b0 is not None else float(t)), d
            return (min(float(t), float(b0)) if b0 is not None else float(t)), d

        def share(name: str, scope: str, row: dict[str, Any], key: str | None, num: dict[str, float], S: float):
            ref, _ = ref_of(name, scope, row, key)
            if ref is None:
                return
            g = np.zeros(self.n)
            for k, w in num.items():
                g[i[k]] += w
            g[i["ead"]] -= ref
            G.append(g)
            c.append(S - ref * T)
            names.append(f"{name}|{scope}")

        for s in L["sector_appetite"]["limits"]:
            share("sector_appetite", s, L["sector_appetite"], s, {f"sec:{s}": 1.0} if f"sec:{s}" in i else {}, bk["sector"].get(s, 0.0))
        for k in BUCKETS:
            share("rating_bucket", k, L["rating_bucket"], k, {f"bk:{k}": 1.0}, bk["bucket"][k])
        share("collateral_type", "real estate", L["collateral_type"], "real_estate", {"re_coll": 1.0}, bk["re_coll"])
        share("sub_ig_share", "book", L["sub_ig_share"], None, {"sub_ig": 1.0}, sum(bk["bucket"][k] for k in SUB_IG))
        share("unsecured_share", "book", L["unsecured_share"], None, {"unsecured": 1.0}, bk["unsecured"])
        if L["re_construction_share"]["kind"] == "soft":
            share("re_construction_share", "book", L["re_construction_share"], None, {"rc": 1.0},
                  sum(bk["sector"].get(s, 0.0) for s in L["re_construction_share"].get("sectors", [])))
        share("stage2_share", "book", L["stage2_share"], None, {"stage2": 1.0}, bk["stage2"])
        for r in self.regions:
            share("region_share", r, L["region_share"], None, {f"reg:{r}": 1.0}, bk["region"].get(r, 0.0))
        share("connected_lending_share", "book", L["connected_lending_share"], None, {"connected": 1.0}, bk["connected"])
        # cost of risk (bps): (EL_book + el) - ref/1e4 * (T + ead)
        ref, _ = ref_of("cost_of_risk_bps", "book", L["cost_of_risk_bps"], None)
        if ref is not None:
            g = np.zeros(self.n)
            g[i["el"]] += 1.0
            g[i["ead"]] -= ref / 1e4
            G.append(g)
            c.append(bk["el"] - ref / 1e4 * T)
            names.append("cost_of_risk_bps|book")
        # new business: long tenor (max), Islamic share and RAROC floor (min), measured on the selection only
        for name, num, den, d in (("long_tenor_share", "long", "ead", "max"), ("islamic_share", "islamic", "ead", "min"),
                                  ("raroc_floor", "pv_rap", "pv_cap", "min")):
            ref, _ = ref_of(name, "new business", L[name], None)
            if ref is None:
                continue
            g = np.zeros(self.n)
            if d == "max":
                g[i[num]] += 1.0
                g[i[den]] -= ref
            else:
                g[i[den]] += ref
                g[i[num]] -= 1.0
            G.append(g)
            c.append(0.0)
            names.append(f"{name}|new business")
        return (np.array(G) if G else np.zeros((0, self.n))), np.array(c), names

    @functools.cached_property
    def top20_ref(self) -> float:
        _, t, _ = levels(self.L["top20_obligor_share"])
        b0 = self._before_soft.get(("top20_obligor_share", "book"))
        return max(float(t), float(b0)) if b0 is not None else float(t)

    def top20_minorants(self, aggs: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        """Linear minorants of the top-20 penalty for the solver's bound: for any fixed set Q of 20 obligors,
        top-20 EAD >= the EAD of Q, so rate * max(0, sum_Q - ref * (T + ead)) >= rate * mu * (sum_Q - ref * (T + ead)).
        One row per candidate selection `aggs` (Q = the 20 largest under that selection)."""
        L, i = self.L, self.idx
        x = L["top20_obligor_share"]
        _, t, _ = levels(x)
        b0 = self._before_soft.get(("top20_obligor_share", "book"))
        ref = max(float(t), float(b0)) if b0 is not None else float(t)
        T = self.B["T"]
        G, c = [], []
        for agg in aggs:
            pip = [(self.obligor_book[o] + agg[i[f"ob:{o}"]], o) for o in self.obligors]
            allv = [(v, None) for v in self.book_top] + pip
            top = sorted(allv, key=lambda z: -z[0])[:20]
            g = np.zeros(self.n)
            const = 0.0
            for v, o in top:
                if o is None:
                    const += v
                else:
                    g[i[f"ob:{o}"]] += 1.0
                    const += self.obligor_book[o]
            g[i["ead"]] -= ref
            G.append(g)
            c.append(const - ref * T)
        return np.array(G) if G else np.zeros((0, self.n)), np.array(c)

    def penalty(self, agg: np.ndarray, deal_soft_ead: float = 0.0) -> tuple[float, list[dict[str, Any]]]:
        """SAR m of SVA charged for soft limits taken past their trigger by the selection (beyond where the
        book already stood), and the soft breaches it lists."""
        m = self.measures(agg)
        rate = penalty_rate()
        pen = rate * deal_soft_ead
        listed = []
        bs = self._before_soft
        for name, scope, v, row, key, base in self._soft_items(m):
            if v is None:
                continue
            a, t, lim = levels(row, key)
            if t is None:
                continue
            d = row.get("direction", "max")
            b0 = bs.get((name, scope))
            if d == "max":
                ref = max(float(t), float(b0)) if b0 is not None else float(t)
                exc = max(0.0, float(v) - ref)
            else:
                ref = min(float(t), float(b0)) if b0 is not None else float(t)
                exc = max(0.0, ref - float(v))
            if exc > 1e-12:
                pen += rate * exc * float(base)
            st = status(v, a, t, lim, d)
            if st != "green" and (b0 is None or status(b0, a, t, lim, d) != st or exc > 1e-12):
                listed.append({"name": name, "scope": scope, "value": float(v), "status": st, "penalty": rate * exc * float(base)})
        return pen, listed

    # ---------------------------------------------------------------- the view

    def rows(self, agg: np.ndarray | None = None, selected: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Every risk-appetite limit: before (the book) and after the selection (book + agg)."""
        L = self.L
        mb = self.before
        ma = mb if agg is None else self.measures(agg)
        sel = selected or []
        out: list[dict[str, Any]] = []

        def add(name: str, scope: str, vb: Any, va: Any, key: str | None = None, direction: str | None = None, value_unit: str | None = None):
            x = L[name]
            a, t, lim = levels(x, key)
            d = direction or x.get("direction", "max")
            out.append({"name": name, "label": x["label"], "scope": scope, "kind": x["kind"], "unit": value_unit or x["unit"],
                        "direction": d, "appetite": a, "trigger": t, "limit": lim,
                        "before": _num(vb), "after": _num(va), "status_before": status(vb, a, t, lim, d),
                        "status": status(va, a, t, lim, d), "above_appetite": above_appetite(va, a, d),
                        "headroom": None if va is None or lim is None or d == "rating" else
                        (float(lim) - float(va)) if d == "max" else (float(va) - float(lim)),
                        "basis": x["basis"], "definition": DEFINITIONS.get(name, ""), "r11": bool(x.get("r11"))})

        bk = self.B
        ob_b = max(bk["obligor"].values())
        add("single_name", "largest obligor", ob_b, max(ob_b, ma["obligor_max"]))
        gb = max(bk["group"].values())
        ga = max([gb] + list(ma["group"].values()))
        gname = max(bk["group"], key=bk["group"].get)
        add("group_connected", f"largest group ({bk['group_names'].get(gname, gname)})" if ga == gb else "largest group", gb, ga)
        add("group_large_exposure", "largest group", gb, ga)
        sb = max(mb["sector"], key=mb["sector"].get)
        sa = max(ma["sector"], key=ma["sector"].get)
        add("sector_policy", f"largest sector ({sa})", mb["sector"][sb], ma["sector"][sa])
        for s in L["sector_appetite"]["limits"]:
            add("sector_appetite", s, mb["sector"].get(s, 0.0), ma["sector"].get(s, 0.0), key=s)
        for k in BUCKETS:
            if k == "IG":
                continue
            add("rating_bucket", k, mb["bucket"][k], ma["bucket"][k], key=k)
        add("collateral_type", "real estate", mb["re_coll"], ma["re_coll"], key="real_estate")
        for name in DEAL_ROWS:
            x = L[name]
            n_hard = sum(1 for s in sel if name in s.get("deal_hard_breaches", []))
            n_soft = sum(1 for s in sel if name in s.get("deal_soft_breaches", []))
            a, t, lim = levels(x, None) if "limits" not in x else (None, None, None)
            if name == "min_rating":
                lim = x["new_to_bank"]
            out.append({"name": name, "label": x["label"], "scope": "each deal", "kind": x["kind"], "unit": "deals",
                        "direction": "deal", "appetite": a, "trigger": t, "limit": lim if "limits" not in x else x["limits"],
                        "before": None, "after": n_hard + n_soft if sel else None, "status_before": "n/a",
                        "status": ("red" if n_hard else "amber" if n_soft else "green") if sel else "n/a",
                        "above_appetite": False, "headroom": None, "basis": x["basis"], "definition": DEFINITIONS.get(name, ""),
                        "r11": False})
        add("bu_rwa_budget", "new business", 0.0, float(ma["rwa"]) if agg is not None else 0.0)
        out[-1]["limit"] = self.rwa_budget
        add("bu_el_budget", "new business", 0.0, float(ma["el_nb"]) if agg is not None else 0.0)
        out[-1]["limit"] = self.el_budget
        add("top20_obligor_share", "book", mb["top20"], ma["top20"])
        add("sector_hhi", "book", mb["hhi"], ma["hhi"])
        add("sub_ig_share", "book", mb["sub_ig"], ma["sub_ig"])
        add("unsecured_share", "book", mb["unsecured"], ma["unsecured"])
        add("re_construction_share", "book", mb["rc"], ma["rc"])
        add("long_tenor_share", "new business", None, ma["long"])
        add("stage2_share", "book", mb["stage2"], ma["stage2"])
        add("cost_of_risk_bps", "book", mb["cor_bps"], ma["cor_bps"])
        add("raroc_floor", "new business", None, ma["raroc"])
        rb = max(mb["region"], key=mb["region"].get)
        ra = max(ma["region"], key=ma["region"].get)
        add("region_share", f"largest region ({ra})", mb["region"][rb], ma["region"][ra])
        add("connected_lending_share", "book", mb["connected"], ma["connected"])
        add("islamic_share", "new business", None, ma["islamic"])
        return out


def _num(v: Any) -> Any:
    if v is None or isinstance(v, str):
        return v
    return float(v)


def book_view() -> dict[str, Any]:
    """GET /risk-appetite: the book today against every limit."""
    sp = Space([])
    rows = sp.rows()
    for r in rows:
        r["value"] = r["before"]
        r["status"] = r["status_before"]
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("green", "amber", "red")}
    bk = book()
    return {"as_of": bk["as_of"], "release": bk["release"], "book_ead": bk["T"], "rows": rows, "counts": counts,
            "levels": table().get("levels", ""), "owner": table()["owner"], "version": table()["version"],
            "penalty_rate": penalty_rate()}


_ = bucket
