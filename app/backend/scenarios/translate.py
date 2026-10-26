"""Translation: a joint scenario -> PD, LGD, EAD, ECL, stage and capital on the corporate book (PLAN_R13 §S.3).

Start: every facility of the corporate book at the as-of quarter (cockpit.corp_facility_quarter, 2026Q2).

PD      For sector s, dy_s = sum_k beta_k dx_k over the identified coefficients of the PD satellite model
        (`satellite.delta_y`); every performing facility moves along the probit:
            PD12' = Phi(Phi^-1(PD12) + dy_s)
        The lifetime PD keeps its term structure: with hazard h = -ln(1 - PD12),
            PDlt' = 1 - (1 - PDlt)^(h'/h)
Stage   The migration model gives the quarterly Stage 1 -> 2 rate m_s' = expit(logit(m_s) + dmig_s) against today's
        m_s (the sector's last four quarters' average); over the year the extra share moved is
            [1 - (1 - m_s')^4] - [1 - (1 - m_s)^4]
        of the sector's Stage 1 EAD, taking the facilities with the highest stressed PD first.
LGD     LGD' = min(LGD + add-on, 100%), the add-on is the severity's expert overlay (`calibrate`, driver lgd):
        downturn LGD cannot be estimated from the bank's resolved defaults.
EAD     EAD' = min(max(limit, EAD), EAD + du / 100 x limit), du the severity's utilisation rise (calibrated).
ECL     Stage 1: PD12' x LGD' x EAD'; Stage 2: PDlt' x LGD' x EAD'; Stage 3: ECL x LGD'/LGD (already defaulted).
        Each facility's start ECL is the reported one; the stressed ECL adds (formula at stressed inputs - formula at
        start inputs), so the start reconciles to the book exactly.
Capital IRB corporate risk weight (Basel ASRF, R from PD, maturity 2.5 years, PD floor 0.05%), as the What-If
        capital view (backend/whatif_v5/capital.py): capital impact = dECL + 15% x dRWA (CET1 at 15% of RWA).
RAROC   The deal-level RAROC under the same severities is computed by the Deal Desk Stress Lab (`ladder`), which
        reprices PD, capital, ECL and the margin ratchet; the book view reports ECL, Stage 2 and capital.
Bands   The 90% band of each identified coefficient is carried through (low and high dy), giving the ECL band.
"""
from __future__ import annotations

import functools
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import expit, logit, ndtr, ndtri

from backend.scenarios import calibrate, data, joint, satellite

CET1 = 0.15
PD_FLOOR = 0.0005
M = 2.5
G999 = float(ndtri(0.999))


@functools.lru_cache(maxsize=1)
def book() -> pd.DataFrame:
    f = data.facility()
    q = data.quarters()[-1]
    return f[f["reporting_quarter"] == q].reset_index(drop=True).copy()


def rwa(pd12: np.ndarray, lgd: np.ndarray, ead: np.ndarray) -> np.ndarray:
    p = np.clip(pd12, PD_FLOOR, 0.999)
    w = (1 - np.exp(-50 * p)) / (1 - math.exp(-50))
    r = 0.12 * w + 0.24 * (1 - w)
    b = (0.11852 - 0.05478 * np.log(p)) ** 2
    ma = (1 + (M - 2.5) * b) / (1 - 1.5 * b)
    k = lgd * (ndtr((ndtri(p) + np.sqrt(r) * G999) / np.sqrt(1 - r)) - p) * ma
    return 12.5 * np.clip(k, 0, None) * ead


def _ecl(pd12, pdlt, lgd, ead, stage) -> np.ndarray:
    return np.where(stage == 1, pd12 * lgd * ead, np.where(stage == 2, pdlt * lgd * ead, 0.0))


def _today_migration() -> dict[str, float]:
    s = data.sector_quarter()
    last = sorted(s["reporting_quarter"].unique(), key=data.quarter_index)[-4:]
    g = s[s["reporting_quarter"].isin(last)]
    return (g.groupby("sector")["to_s2"].sum() / g.groupby("sector")["n_s1"].sum()).to_dict()


def run(values: dict[str, float], severity: str, band: str = "mid") -> dict[str, Any]:
    fits = satellite.fit_all()
    cal = calibrate.calibrate_all()
    f = book()
    dx = satellite.dx_for(values)
    lgd_add = float(cal["lgd"]["values"][severity]) / 100.0 if severity in cal["lgd"]["values"] else 0.0
    du = float(cal["utilisation"]["values"][severity]) if severity in cal["utilisation"]["values"] else 0.0
    dy_pd = satellite.delta_y(fits["pd"], dx, band=band)
    dy_mig = satellite.delta_y(fits["migration"], dx, band=band)
    stage = f["stage"].to_numpy().copy()
    perf = stage < 3
    pd0 = f["pd_pit_12m"].clip(1e-6, 0.9999).to_numpy()
    lt0 = np.maximum(f["pd_lifetime"].clip(1e-6, 0.9999).to_numpy(), pd0)
    lgd0 = (f["lgd_pct"] / 100).clip(0, 1).to_numpy()
    ead0 = f["ead_sar_mn"].to_numpy()
    lim = f["limit_sar_mn"].fillna(0).to_numpy()
    pd1 = np.where(perf, ndtr(ndtri(pd0) + dy_pd), pd0)
    h0, h1 = -np.log1p(-pd0), -np.log1p(-pd1)
    lt1 = np.where(perf, 1 - (1 - lt0) ** (h1 / h0), lt0)
    lgd1 = np.clip(lgd0 + lgd_add, 0, 1)
    ead1 = np.where(perf, np.minimum(np.maximum(lim, ead0), ead0 + du / 100.0 * lim), ead0)
    # stage: the extra share of Stage 1 EAD that moves over the year, highest stressed PD first, by sector
    m0 = _today_migration()
    st1 = stage.copy()
    moved_ead = 0.0
    for sec, idx in f[stage == 1].groupby("sector").groups.items():
        m = float(m0.get(sec, 0.0))
        m = min(max(m, 1e-4), 0.999)
        m1 = float(expit(logit(m) + dy_mig))
        extra = max(0.0, (1 - (1 - m1) ** 4) - (1 - (1 - m) ** 4))
        if extra <= 0:
            continue
        ix = np.array(list(idx))
        order = ix[np.argsort(-pd1[ix])]
        target = extra * ead1[ix].sum()
        cum = np.cumsum(ead1[order])
        take = order[cum <= target + 1e-12]
        st1[take] = 2
        moved_ead += float(ead1[take].sum())
    ecl_rep = f["ecl_sar_mn"].to_numpy()
    f0 = _ecl(pd0, lt0, lgd0, ead0, stage)
    f1 = _ecl(pd1, lt1, lgd1, ead1, st1)
    s3 = stage == 3
    ecl1 = ecl_rep + (f1 - f0)
    ecl1[s3] = ecl_rep[s3] * np.where(lgd0[s3] > 0, lgd1[s3] / np.where(lgd0[s3] > 0, lgd0[s3], 1), 1)
    r0 = np.where(perf, rwa(pd0, lgd0, ead0), np.maximum(ead0 - ecl_rep, 0))
    r1 = np.where(perf, rwa(pd1, lgd1, ead1), np.maximum(ead1 - ecl1, 0))
    d_ecl = float(ecl1.sum() - ecl_rep.sum())
    d_rwa = float(r1.sum() - r0.sum())
    by = (pd.DataFrame({"sector": f["sector"], "ead": ead0, "ecl0": ecl_rep, "ecl1": ecl1, "s2_0": (stage == 2) * ead0,
                        "s2_1": (st1 == 2) * ead1, "pd0": pd0 * ead0 * perf, "pd1": pd1 * ead1 * perf, "pe0": ead0 * perf, "pe1": ead1 * perf})
          .groupby("sector").sum())
    sectors = [{"sector": s, "ead": float(r.ead), "ecl_start": float(r.ecl0), "ecl_stressed": float(r.ecl1),
                "ecl_change": float(r.ecl1 - r.ecl0), "pd_start": float(r.pd0 / r.pe0) if r.pe0 else None,
                "pd_stressed": float(r.pd1 / r.pe1) if r.pe1 else None, "stage2_share_start": float(r.s2_0 / r.ead) if r.ead else 0.0,
                "stage2_share_stressed": float(r.s2_1 / r.ead) if r.ead else 0.0} for s, r in by.iterrows()]
    sectors.sort(key=lambda r: -r["ecl_change"])
    tot_ead0, tot_ead1 = float(ead0.sum()), float(ead1.sum())
    return {"severity": severity, "band": band, "values": values, "dx": dx, "dy_pd": dy_pd, "dy_migration": dy_mig,
            "lgd_add_pp": lgd_add * 100, "utilisation_pp": du, "facilities": int(len(f)), "as_of": data.quarters()[-1],
            "ead_start": tot_ead0, "ead_stressed": tot_ead1, "ecl_start": float(ecl_rep.sum()), "ecl_stressed": float(ecl1.sum()),
            "ecl_change": d_ecl, "ecl_change_pct": d_ecl / float(ecl_rep.sum()) * 100,
            "pd_start": float((pd0 * ead0)[perf].sum() / ead0[perf].sum()), "pd_stressed": float((pd1 * ead1)[perf].sum() / ead1[perf].sum()),
            "stage2_ead_start": float(ead0[stage == 2].sum()), "stage2_ead_stressed": float(ead1[st1 == 2].sum()),
            "stage2_share_start": float(ead0[stage == 2].sum() / tot_ead0), "stage2_share_stressed": float(ead1[st1 == 2].sum() / tot_ead1),
            "stage2_moved_ead": moved_ead, "rwa_start": float(r0.sum()), "rwa_stressed": float(r1.sum()), "rwa_change": d_rwa,
            "capital_impact": d_ecl + CET1 * d_rwa, "sectors": sectors}


@functools.lru_cache(maxsize=1)
def by_severity() -> dict[str, Any]:
    j = joint.build()
    out = {}
    for sev in calibrate.SEVERITIES:
        v = j["joint"][sev]["values"]
        mid = run(v, sev)
        lo, hi = run(v, sev, "low"), run(v, sev, "high")
        e = sorted([lo["ecl_change"], hi["ecl_change"]])
        mid["ecl_band"] = [min(e[0], mid["ecl_change"]), max(e[1], mid["ecl_change"])]
        out[sev] = mid
    return out
