"""R11 Session L: the exact pipeline solver (PLAN_R11 L4). Pure Python and numpy.

Choose one option per deal (decline, as asked, recommended, a reduced amount) to maximise

    total SVA  -  penalty for soft limits taken past their trigger

subject to every hard limit across the selection (single obligor, connected group, large exposure, sector
policy, the real estate and construction cap) and the RWA and EL budgets, all linear in the selected
options' vectors: H @ agg <= b (risk_appetite_view.Space).

Depth-first branch-and-bound over deals (largest EAD first), options in descending value net of the dual prices:
  * upper bounds, the minimum of: Lagrangian relaxations with multipliers nu >= 0 on the hard rows and 0 <= mu <= 1
    on the soft penalties (max(0, z) >= mu z), from a ladder on the RWA budget, one soft row at a time, the rows active
    at the incumbent, and the root dual found by projected subgradient (with cutting-plane minorants of the top-20
    penalty: for any fixed set Q of 20 obligors, top-20 EAD >= EAD of Q); and the plain SVA bound less the least
    penalty any completion can still carry (each soft row can fall at most by the remaining deals' most favourable
    contribution; the top-20 EAD never falls);
  * feasibility: a node is cut when even the most favourable remaining choices (each row's minimum
    contribution, decline counted as 0) cannot bring every hard row back within its bound.
Every bound is valid for every completion, so nothing better is ever cut.
The search is exhaustive up to these valid cuts, so the result is the exact optimum (verified against brute
force in tests/v5/dealdesk/test_r11_pipeline.py). A node cap guards the service; if it is ever hit the
result says `exact: false` and carries the gap to the bound.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.dealdesk.risk_appetite_view import Space, penalty_rate, table

def min_sva() -> float:
    """An option is approvable in the pipeline only if it clears the hurdle by this much SVA (risk_appetite.optimiser)."""
    return float(table().get("optimiser", {}).get("min_sva_sar_mn", 0.0))


EPS = 1e-9
NODE_CAP = 3_000_000


@dataclass
class Result:
    choice: list[int]                 # per deal: option index, or -1 = decline
    objective: float
    sva: float
    penalty: float
    agg: np.ndarray
    feasible: bool
    exact: bool = True
    nodes: int = 0
    seconds: float = 0.0
    bound: float | None = None
    soft: list[dict[str, Any]] = field(default_factory=list)


class Solver:
    def __init__(self, space: Space, forced: set[int] | None = None, b: np.ndarray | None = None,
                 allowed: dict[int, list[int]] | None = None, free: set[int] | None = None):
        """`forced`: deals that must be approved; `free`: deals whose options are eligible without the SVA
        materiality floor (the structure a user is testing)."""
        self.S = space
        self.forced = forced or set()
        self.free = (free or set()) | self.forced
        self.b = space.b.copy() if b is None else np.asarray(b, dtype=float)
        self.H = space.H
        n = len(space.deals)
        self.min_sva = min_sva()
        self.opts: list[list[int]] = []
        for k in range(n):
            os_ = [j for j, o in enumerate(space.deals[k]["options"])
                   if o["available"] and (k in self.free or float(o["sva"]) >= self.min_sva)]
            if allowed is not None and k in allowed:
                os_ = [j for j in os_ if j in allowed[k]]
            self.opts.append(os_)
        self.sva = [[float(o["sva"]) for o in d["options"]] for d in space.deals]
        self.soft_ead = [[float(o["ead"]) * len(o.get("deal_soft_breaches", [])) for o in d["options"]] for d in space.deals]
        self.HV = [[self.H @ v for v in vs] for vs in space.V] if len(self.H) else [[np.zeros(0) for _ in vs] for vs in space.V]
        self.i_rwa = space.idx["rwa"]
        self.r_rwa = next(i for i, m in enumerate(space.hard_meta) if m["name"] == "bu_rwa_budget")

    def objective(self, choice: list[int]) -> tuple[float, float, float, np.ndarray, list[dict[str, Any]]]:
        agg = np.zeros(self.S.n)
        sva = 0.0
        soft = 0.0
        for k, j in enumerate(choice):
            if j >= 0:
                agg += self.S.V[k][j]
                sva += self.sva[k][j]
                soft += self.soft_ead[k][j]
        pen, listed = self.S.penalty(agg, soft)
        return sva - pen, sva, pen, agg, listed

    def feasible(self, choice: list[int]) -> bool:
        if any(j < 0 for k, j in enumerate(choice) if k in self.forced):
            return False
        if any(j >= 0 and j not in self.opts[k] for k, j in enumerate(choice)):
            return False
        u = np.zeros(len(self.b))
        for k, j in enumerate(choice):
            if j >= 0:
                u += self.HV[k][j]
        return bool(np.all(u <= self.b + 1e-7))

    # ---------------------------------------------------------------- branch and bound

    def _dual(self, lb: float, G: np.ndarray, cvec: np.ndarray, rate: float, iters: int = 300) -> list[tuple[np.ndarray, float]]:
        """Projected subgradient on the Lagrangian upper bound
            L(nu, mu) = nu.b - rate mu.c + sum_k max(0 | forced, max_j (s_kj - (nu H + rate mu G) v_kj)),
        valid for every nu >= 0 and 0 <= mu <= 1 (max(0, z) >= mu z). Returns the best multipliers found."""
        S = self.S
        n = len(S.deals)
        H, b = self.H, self.b
        R = len(cvec)
        nu = np.zeros(len(b))
        mu = np.zeros(R)
        vals = [[(self.sva[k][j] - rate * self.soft_ead[k][j], S.V[k][j]) for j in self.opts[k]] for k in range(n)]
        if not any(vals):
            return []
        best_L, best = np.inf, None
        theta = 1.0
        stall = 0
        for _ in range(iters):
            Wv = nu @ H + (rate * (mu @ G) if R else 0.0)
            L = float(nu @ b) - (rate * float(mu @ cvec) if R else 0.0)
            agg = np.zeros(S.n)
            for k in range(n):
                top, arg = (0.0, None) if k not in self.forced else (-np.inf, None)
                for sv, v in vals[k]:
                    a = sv - float(Wv @ v)
                    if a > top:
                        top, arg = a, v
                if k in self.forced and arg is None and vals[k]:
                    top, arg = max(((sv - float(Wv @ v), v) for sv, v in vals[k]), key=lambda x: x[0])
                L += top if np.isfinite(top) else 0.0
                if arg is not None:
                    agg += arg
            if L < best_L - 1e-9:
                best_L, best = L, (Wv.copy(), float(nu @ b) - (rate * float(mu @ cvec) if R else 0.0))
                self.dual_agg = agg.copy()
                stall = 0
            else:
                stall += 1
                if stall >= 15:
                    theta *= 0.5
                    stall = 0
            g_nu = b - H @ agg
            g_mu = -rate * (cvec + G @ agg) if R else np.zeros(0)
            # descent direction (projected): only components that can move
            d_nu = np.where((nu > 0) | (g_nu < 0), g_nu, 0.0)
            d_mu = np.where(((mu > 0) | (g_mu < 0)) & ((mu < 1) | (g_mu > 0)), g_mu, 0.0) if R else g_mu
            norm = float(d_nu @ d_nu + (d_mu @ d_mu if R else 0.0))
            if norm < 1e-12 or theta < 1e-4:
                break
            gap = max(L - (lb if np.isfinite(lb) else L - 1.0), 1e-6)
            step = theta * gap / norm
            nu = np.maximum(0.0, nu - step * g_nu)
            if R:
                mu = np.clip(mu - step * g_mu, 0.0, 1.0)
        return [best] if best is not None else []

    def _greedy(self) -> list[int]:
        """A quick incumbent: add each deal's best option, densest first, when the objective improves and the limits hold."""
        n = len(self.S.deals)
        choice = [-1] * n
        for k in self.forced:
            if self.opts[k]:
                choice[k] = max(self.opts[k], key=lambda j: self.sva[k][j])
        if not self.feasible(choice):
            return [-1] * n
        cur = self.objective(choice)[0]
        order = sorted(range(n), key=lambda k: -max([self.sva[k][j] / max(self.S.V[k][j][self.i_rwa], 1e-6) for j in self.opts[k]] or [-1e9]))
        for k in order:
            for j in sorted(self.opts[k], key=lambda j: -self.sva[k][j]):
                old = choice[k]
                choice[k] = j
                if self.feasible(choice):
                    o = self.objective(choice)[0]
                    if o > cur + EPS:
                        cur = o
                        break
                choice[k] = old
        return choice

    extra_mus: list[np.ndarray] | None = None
    extra_aggs: list[np.ndarray] | None = None
    dual_agg: np.ndarray | None = None
    order_mode: str = "ead"

    def solve(self, node_cap: int = NODE_CAP) -> Result:
        """Exact search; a short first pass finds a strong incumbent whose active soft rows tighten the bound of the full pass."""
        if node_cap > 20_000 and self.extra_mus is None:
            first = self._solve(20_000)
            if first.exact:
                return first
            self.extra_mus = []
            self.extra_aggs = [first.agg] if first.feasible else []
            res = self._solve(node_cap)
            res.nodes += first.nodes
            return res
        return self._solve(node_cap)

    def _solve(self, node_cap: int = NODE_CAP) -> Result:
        t0 = time.time()
        S = self.S
        n = len(S.deals)
        m = len(self.b)
        if any(not self.opts[k] for k in self.forced):
            return Result([-1] * n, float("-inf"), 0.0, 0.0, np.zeros(S.n), False, nodes=0)
        rate = penalty_rate()
        G, cvec, _ = S.soft_linear
        G0, c0 = G, cvec
        # incumbent and the soft rows active there (their multipliers mu = 1 tighten the bound)
        inc = self._greedy()
        inc_ok = self.feasible(inc)
        inc_obj = self.objective(inc)[0] if inc_ok else float("-inf")
        # top-20 minorants: Q = the 20 largest with every deal at its largest option, and at the incumbent
        big = np.zeros(S.n)
        for k in range(n):
            if self.opts[k]:
                big += S.V[k][max(self.opts[k], key=lambda j: S.V[k][j][S.idx["ead"]])]
        cands = [big]
        if inc_ok:
            cands.append(sum((S.V[k][j] for k, j in enumerate(inc) if j >= 0), np.zeros(S.n)))
        if self.extra_aggs:
            cands.extend(self.extra_aggs)
        G2, c2 = S.top20_minorants(cands)
        G = np.vstack([G, G2]) if len(cvec) else G2
        cvec = np.concatenate([cvec, c2])
        mus = [np.zeros(len(cvec))]
        if len(cvec):
            # every soft row that some selection could push past its reference, one at a time
            reach = cvec + sum(np.max(np.stack([np.zeros(len(cvec))] + [G @ S.V[k][j] for j in self.opts[k]]), axis=0)
                               for k in range(n))
            for r in np.flatnonzero(reach > 0):
                e = np.zeros(len(cvec))
                e[r] = 1.0
                mus.append(e)
            for extra in (self.extra_aggs or []):
                act = (G @ extra + cvec > 0).astype(float)
                if act.any():
                    mus.append(act)
            if inc_ok:
                agg = np.zeros(S.n)
                for k, j in enumerate(inc):
                    if j >= 0:
                        agg += S.V[k][j]
                act = (G @ agg + cvec > 0).astype(float)
                if act.sum() > 1:
                    mus.append(act)
        ratios = sorted({self.sva[k][j] / max(S.V[k][j][self.i_rwa], 1e-6) for k in range(n) for j in self.opts[k] if self.sva[k][j] > 0})
        lams = [0.0] + (list(ratios) if len(ratios) <= 12 else list(np.quantile(ratios, np.linspace(0, 1, 12))))
        e_rwa = np.zeros(S.n)
        e_rwa[self.i_rwa] = 1.0
        Ws, consts = [], []
        for mu in mus:
            for lam in lams:
                Ws.append(rate * (mu @ G if len(cvec) else np.zeros(S.n)) + lam * e_rwa)
                consts.append((-rate * float(mu @ cvec) if len(cvec) else 0.0) + lam * self.b[self.r_rwa])
        # the root Lagrangian dual over every hard row (nu >= 0) and every linear soft penalty (0 <= mu <= 1),
        # minimised by projected subgradient: its multipliers give the tightest single bound
        # cutting planes: the top-20 minorant at the dual's own argmax, re-solved a few rounds
        for _ in range(4):
            self.dual_agg = None
            dual = self._dual(inc_obj, G, cvec, rate)
            if self.dual_agg is None:
                break
            G3, c3 = S.top20_minorants([self.dual_agg])
            if np.any(np.all(np.isclose(G, G3[0]), axis=1) & np.isclose(cvec, c3[0])):
                break
            G = np.vstack([G, G3])
            cvec = np.concatenate([cvec, c3])
        for Wd, cd in dual:
            Ws.append(Wd)
            consts.append(cd)
        W = np.array(Ws)
        const = np.array(consts)
        C = len(consts)
        # adjusted option values per combo: sva - rate*deal_soft - W @ v
        adj = [[np.array([self.sva[k][j] - rate * self.soft_ead[k][j]]) - W @ S.V[k][j]
                if j in self.opts[k] else None for j in range(len(S.deals[k]["options"]))] for k in range(n)]
        best = [max([self.sva[k][j] for j in self.opts[k]] or [0.0]) for k in range(n)]
        bigead = [max([S.V[k][j][S.idx["ead"]] for j in self.opts[k]] or [0.0]) for k in range(n)]
        if self.order_mode == "ead":
            order = sorted(range(n), key=lambda k: (-bigead[k], k))
        elif self.order_mode == "dual":
            dv = [max([float(adj[k][j][-1]) for j in self.opts[k]] or [0.0]) for k in range(n)]
            order = sorted(range(n), key=lambda k: (-abs(dv[k]), k))
        else:
            order = sorted(range(n), key=lambda k: (-best[k], k))
        branches = []
        for k in order:
            # options in descending value net of the dual's prices (the last combo), so good incumbents come early
            cand = list(self.opts[k]) + ([-1] if k not in self.forced else [])
            bs = sorted(cand, key=lambda j: (-(float(adj[k][j][-1]) if j >= 0 else 0.0), -(self.sva[k][j] if j >= 0 else 0.0), j))
            branches.append(bs)
        suf = np.zeros((n + 1, C))
        mins = np.zeros((n + 1, m))
        R0 = len(c0)
        smin = np.zeros((n + 1, R0))     # suffix of the most each soft row can still fall
        eadmax = np.zeros(n + 1)         # suffix of the largest EAD still to come
        Lm = len(lams)                   # the first Lm combos carry no soft multipliers
        i_ead = S.idx["ead"]
        for pos in range(n - 1, -1, -1):
            k = order[pos]
            js = self.opts[k]
            if k in self.forced:
                rowv = np.full(C, -np.inf)
                lo = np.full(m, np.inf)
            else:
                rowv = np.zeros(C)
                lo = np.zeros(m)
            for j in js:
                rowv = np.maximum(rowv, adj[k][j])
                lo = np.minimum(lo, self.HV[k][j])
            if not js:
                rowv, lo = np.zeros(C), np.zeros(m)
            suf[pos] = suf[pos + 1] + rowv
            mins[pos] = mins[pos + 1] + lo
            slo = np.zeros(R0) if k not in self.forced or not js else np.full(R0, np.inf)
            emax = 0.0
            for j in js:
                if R0:
                    slo = np.minimum(slo, G0 @ S.V[k][j])
                emax = max(emax, float(S.V[k][j][i_ead]))
            smin[pos] = smin[pos + 1] + (slo if R0 else 0.0)
            eadmax[pos] = eadmax[pos + 1] + emax
        b = self.b
        choice = [-1] * n
        self.best_obj = inc_obj
        self.best_choice = list(inc) if inc_ok else None
        self.nodes = 0
        self.capped = False
        u = np.zeros(m)
        fixed = np.zeros(C)
        agg = np.zeros(S.n)
        ref20 = S.top20_ref
        T0 = S.B["T"]

        def pen_lb(pos: int) -> float:
            """The least penalty any completion can carry: each soft row can fall at most by the remaining deals'
            most favourable contribution; the top-20 EAD never falls, its denominator grows at most by the remaining EAD."""
            pl = 0.0
            if R0:
                pl = rate * float(np.maximum(0.0, G0 @ agg + c0 + smin[pos]).sum())
            z = S.top20(agg) - ref20 * (T0 + agg[i_ead] + eadmax[pos])
            return pl + (rate * z if z > 0 else 0.0)

        def dfs(pos: int) -> None:
            nonlocal fixed
            self.nodes += 1
            if self.nodes > node_cap:
                self.capped = True
                return
            if np.any(u + mins[pos] > b + 1e-7):
                return
            if pos == n:
                obj = self.objective(choice)[0]
                if obj > self.best_obj + EPS:
                    self.best_obj = obj
                    self.best_choice = list(choice)
                return
            if float(np.min(fixed + suf[pos] + const)) <= self.best_obj + EPS:
                return
            if float(np.min(fixed[:Lm] + suf[pos, :Lm] + const[:Lm])) - pen_lb(pos) <= self.best_obj + EPS:
                return
            k = order[pos]
            for j in branches[pos]:
                if j < 0:
                    choice[k] = -1
                    dfs(pos + 1)
                else:
                    hv = self.HV[k][j]
                    a = adj[k][j]
                    u[:] += hv
                    agg[:] += S.V[k][j]
                    fixed = fixed + a
                    choice[k] = j
                    dfs(pos + 1)
                    fixed = fixed - a
                    agg[:] -= S.V[k][j]
                    u[:] -= hv
                    choice[k] = -1
                if self.capped:
                    return

        dfs(0)
        secs = time.time() - t0
        if self.best_choice is None:
            return Result([-1] * n, float("-inf"), 0.0, 0.0, np.zeros(S.n), False, exact=not self.capped, nodes=self.nodes, seconds=secs)
        obj, sva, pen, agg, listed = self.objective(self.best_choice)
        return Result(self.best_choice, obj, sva, pen, agg, True, exact=not self.capped, nodes=self.nodes, seconds=secs,
                      bound=float(np.min(suf[0] + const)) if self.capped else None, soft=listed)

    # ---------------------------------------------------------------- brute force (tests)

    def brute_force(self) -> Result:
        n = len(self.S.deals)
        spaces = [([-1] if k not in self.forced else []) + self.opts[k] for k in range(n)]
        best: tuple[float, list[int]] | None = None
        for c in itertools.product(*spaces):
            c = list(c)
            if not self.feasible(c):
                continue
            obj = self.objective(c)[0]
            if best is None or obj > best[0] + EPS:
                best = (obj, c)
        if best is None:
            return Result([-1] * n, float("-inf"), 0.0, 0.0, np.zeros(self.S.n), False)
        obj, sva, pen, agg, listed = self.objective(best[1])
        return Result(best[1], obj, sva, pen, agg, True, soft=listed)
