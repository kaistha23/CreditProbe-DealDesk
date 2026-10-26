"""Binning, Weight of Evidence and Information Value (deterministic, no model).

WoE is ln(share of goods / share of bads) with a 0.5 smoothing count, so a higher WoE is a safer bin.
Numeric variables get quantile bins that are merged until every bin holds at least `MIN_SHARE` of the
development sample and the bad rate is monotone in the direction the data shows; a missing value is its
own bin. Categorical variables get one bin per category, with the small ones pooled into "Other".
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

MIN_SHARE = 0.05
MIN_CAT_SHARE = 0.03
START_BINS = 10
SMOOTH = 0.5


def _woe(good: float, bad: float, g_tot: float, b_tot: float) -> float:
    return math.log(((good + SMOOTH) / (g_tot + SMOOTH)) / ((bad + SMOOTH) / (b_tot + SMOOTH)))


def _fill(bins: list[dict[str, Any]], y: np.ndarray, idx: np.ndarray) -> None:
    g_tot, b_tot = float((y == 0).sum()), float((y == 1).sum())
    n = len(y)
    iv = 0.0
    for k, b in enumerate(bins):
        sel = idx == k
        bad, good = float(y[sel].sum()), float((y[sel] == 0).sum())
        b.update({"n": int(sel.sum()), "good": int(good), "bad": int(bad), "share": (good + bad) / n,
                  "bad_rate": bad / max(good + bad, 1.0), "woe": _woe(good, bad, g_tot, b_tot)})
        iv += (((good + SMOOTH) / (g_tot + SMOOTH)) - ((bad + SMOOTH) / (b_tot + SMOOTH))) * b["woe"]
    for b in bins:
        b["iv"] = None
    bins[0]["_iv_total"] = iv


def assign(spec: dict[str, Any], values: pd.Series) -> np.ndarray:
    """The bin index of every value under a variable's spec (missing / unseen -> the 'Missing' or 'Other' bin)."""
    bins = spec["bins"]
    out = np.full(len(values), -1, dtype=np.int16)
    if spec["type"] == "categorical":
        cat_to_bin = {}
        other = next((k for k, b in enumerate(bins) if b.get("other")), None)
        for k, b in enumerate(bins):
            for c in b.get("cats", []):
                cat_to_bin[c] = k
        s = values.astype(object).where(values.notna(), "__missing__")
        out = s.map(lambda c: cat_to_bin.get(c, other if other is not None else 0)).to_numpy(dtype=np.int16)
        return out
    miss = next((k for k, b in enumerate(bins) if b.get("missing")), None)
    num = [(k, b) for k, b in enumerate(bins) if not b.get("missing")]
    edges = [b["hi"] for _, b in num[:-1]]
    x = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    pos = np.searchsorted(np.asarray(edges, dtype=float), x, side="right") if edges else np.zeros(len(x), dtype=int)
    ks = np.asarray([k for k, _ in num], dtype=np.int16)
    out = ks[np.clip(pos, 0, len(ks) - 1)]
    isnan = np.isnan(x)
    if isnan.any():
        if miss is not None:
            out[isnan] = miss
        else:  # no missing bin was learned: the middle bin, WoE closest to neutral
            woes = np.asarray([b["woe"] for _, b in num])
            out[isnan] = ks[int(np.argmin(np.abs(woes)))]
    return out


def _label(b: dict[str, Any], first: bool, last: bool, name: str) -> str:
    if b.get("missing"):
        return "Missing"
    if b.get("other"):
        return "Other"
    if "cats" in b:
        return ", ".join(map(str, b["cats"]))
    lo, hi = b["lo"], b["hi"]
    f = lambda v: f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}".rstrip("0").rstrip(".")  # noqa: E731
    if first:
        return f"< {f(hi)}"
    if last:
        return f"≥ {f(lo)}"
    return f"{f(lo)} to < {f(hi)}"


def fit_numeric(x: pd.Series, y: np.ndarray, name: str) -> dict[str, Any] | None:
    xv = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float)
    ok = ~np.isnan(xv)
    if ok.sum() < 200 or len(np.unique(xv[ok])) < 2:
        return None
    q = np.unique(np.quantile(xv[ok], np.linspace(0, 1, START_BINS + 1)[1:-1]))
    cuts = list(q)
    n = len(y)
    # direction of the relationship (the sign of the rank correlation with the bad flag)
    rho = pd.Series(xv[ok]).rank().corr(pd.Series(y[ok]))
    direction = 1 if (rho or 0) >= 0 else -1

    def build(cs: list[float]) -> list[dict[str, Any]]:
        e = [-np.inf, *cs, np.inf]
        out = []
        for i in range(len(e) - 1):
            sel = ok & (xv >= e[i]) & (xv < e[i + 1])
            out.append({"lo": e[i], "hi": e[i + 1], "bad": float(y[sel].sum()), "n": float(sel.sum())})
        return out

    while True:
        bs = build(cuts)
        if len(bs) <= 2:
            break
        rates = [b["bad"] / max(b["n"], 1) for b in bs]
        small = [i for i, b in enumerate(bs) if b["n"] / n < MIN_SHARE]
        viol = [i for i in range(len(bs) - 1) if direction * (rates[i + 1] - rates[i]) < 0]
        if small:
            i = min(small, key=lambda j: bs[j]["n"])
            merge = i if i < len(bs) - 1 and (i == 0 or bs[i + 1]["n"] <= bs[i - 1]["n"]) else i - 1
        elif viol:
            merge = min(viol, key=lambda j: abs(rates[j + 1] - rates[j]))
        else:
            break
        cuts.pop(merge)
    bs = build(cuts)
    if len(bs) < 2:
        return None
    bins: list[dict[str, Any]] = [{"lo": float(b["lo"]), "hi": float(b["hi"])} for b in bs]
    idx = np.full(len(xv), -1, dtype=int)
    for k, b in enumerate(bins):
        idx[ok & (xv >= b["lo"]) & (xv < b["hi"])] = k
    if (~ok).any():
        bins.append({"missing": True, "lo": None, "hi": None})
        idx[~ok] = len(bins) - 1
    _fill(bins, y, idx)
    iv = bins[0].pop("_iv_total")
    nb = [b for b in bins if not b.get("missing")]
    for k, b in enumerate(bins):
        b["label"] = _label(b, k == 0, b is nb[-1], name)
    return {"type": "numeric", "bins": _scrub(bins), "iv": iv, "direction": direction}


def fit_categorical(x: pd.Series, y: np.ndarray, name: str) -> dict[str, Any] | None:
    s = x.astype(object).where(x.notna(), "__missing__")
    n = len(s)
    freq = s.value_counts()
    keep = [c for c, k in freq.items() if k / n >= MIN_CAT_SHARE]
    if not keep:
        return None
    rest = [c for c in freq.index if c not in keep]
    groups: list[dict[str, Any]] = [{"cats": [c]} for c in keep]
    if rest:
        groups.append({"cats": rest, "other": True})
    if len(groups) < 2:
        return None
    idx = np.zeros(n, dtype=int)
    for k, g in enumerate(groups):
        idx[s.isin(g["cats"]).to_numpy()] = k
    _fill(groups, y, idx)
    iv = groups[0].pop("_iv_total")
    for g in groups:
        g["label"] = "Other" if g.get("other") else ", ".join("Missing" if c == "__missing__" else str(c) for c in g["cats"])
    return {"type": "categorical", "bins": _scrub(groups), "iv": iv, "direction": 0}


def _scrub(bins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for b in bins:
        d = {k: (None if isinstance(v, float) and (math.isinf(v) or math.isnan(v)) else v) for k, v in b.items() if k != "iv"}
        for k in ("lo", "hi"):
            if k in d and d[k] is None and not b.get("missing"):
                d[k] = None
        out.append(d)
    return out


def edges_ok(spec: dict[str, Any]) -> dict[str, Any]:
    """After a JSON round trip the open ends are None; restore them for `assign`."""
    if spec["type"] == "numeric":
        for b in spec["bins"]:
            if b.get("missing"):
                continue
            b["lo"] = -math.inf if b["lo"] is None else b["lo"]
            b["hi"] = math.inf if b["hi"] is None else b["hi"]
    return spec
