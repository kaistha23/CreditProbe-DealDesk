"""The Delta method: the What-If domain's own term structures, moved deterministically.

Start: the stored PD and LGD term structures, so the starting ECL recomputed
by this method IS the reported ECL (no model error by construction).

Transmission of the feature-level drivers:
  rating   every annual hazard x masterscale PD(new grade) / PD(old grade)
           (keeps the exposure's position inside its grade, moves its TTC anchor)
  sector   the cycle index of the exposure moves by -severity (sd units):
           hazard' = Phi(Phi^-1(hazard) - sqrt(rho/(1-rho)) * dZ)
  mev      the MEV shock moves each scenario path; the change in the
           segment's cycle index (cycle.mev_dz, estimated elasticities x
           segment beta) moves every hazard the same way; LGD moves with it
           (downturn LGD: x (1 - 0.10 dZ)) and real-estate collateral moves
           with the real-estate price shock (x (1 - secured share x move))
The engine then applies PD/LGD/CCF deltas and re-assesses staging.
"""
from __future__ import annotations

import numpy as np

from backend.whatif_v5.domain import build, cycle, store
from backend.whatif_v5.models.engine import PD_CAP, Context, Method, Start

METHOD_VERSION = "delta-1.0.0"


class Delta(Method):
    key = "delta"
    name = "Delta method"
    version = METHOD_VERSION

    def start(self, ctx: Context) -> Start:
        f = ctx.frame
        mpd = np.stack([f[store.pd_cols(s)].to_numpy(dtype=float) for s in store.SCENARIOS], axis=1)
        lgd = np.stack([f[store.lgd_cols(s)].to_numpy(dtype=float) for s in store.SCENARIOS], axis=1)
        return Start(mpd=mpd, lgd=lgd, label="the stored term structures (equal to the reported ECL)")

    def transmit(self, ctx: Context, on: frozenset[str]) -> tuple[np.ndarray, np.ndarray]:
        h = ctx.base_h.copy()
        lgd = ctx.start.lgd.copy()
        f = ctx.frame
        live = f["stage"].to_numpy() < 3
        dz = np.zeros(h.shape)
        if "sector" in on:
            dz += ctx.sector_dz[:, None, None]
        if "mev" in on:
            dz += ctx.mev_dz
        if dz.any():
            r = f["rho"].to_numpy(dtype=float)[:, None, None]
            moved = cycle.shift_pd(np.clip(h, cycle.PD_FLOOR, cycle.PD_CAP), r, dz)
            h = np.where(live[:, None, None] & (dz != 0), moved, h)
            lgd = lgd * np.clip(1.0 - build.LGD_DOWNTURN_PER_Z * dz, 0.5, 2.0)
        if "mev" in on and ctx.re_move.any():
            re_sec = (f["collateral_type"].isin(build.RE_COLLATERAL).to_numpy()
                      * f["secured_share"].to_numpy(dtype=float))[:, None, None]
            lgd = lgd * np.clip(1.0 - re_sec * ctx.re_move, 0.5, 2.0)
        if "rating" in on:
            h = np.where(live[:, None, None], np.minimum(PD_CAP, h * ctx.rating_factor[:, None, None]), h)
        return np.clip(h, 0.0, PD_CAP), np.clip(lgd, 0.0, max(1.0, float(ctx.start.lgd.max())))
