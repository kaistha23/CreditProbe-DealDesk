"""R16 d: helpers shared by the customer specs (statements, proposal-side bank dict for new-to-bank customers)."""
from __future__ import annotations

import random

from ops.r16_customers import fin


def debit_items(credits, opening: float, closing: float, layout, rnd: random.Random):
    """Monthly debits that take the account from `opening` to `closing` given the monthly credits, split by layout
    [(label, share, day)] with a little noise; amounts to the SAR unit."""
    tot_c = [round(sum(a for _, a, _ in c), 6) for c in credits]
    n = len(credits)
    deltas = fin.series(opening - closing, n, rnd, noise=0.0, nd=6) if abs(opening - closing) > 1e-9 else [0.0] * n
    out = []
    for i in range(n):
        target = round(tot_c[i] + deltas[i], 6)
        shares = [s * (1 + 0.15 * (rnd.random() - 0.5)) for _, s, _ in layout]
        ws = sum(shares)
        parts = [round(target * s / ws, 6) for s in shares[:-1]]
        parts.append(round(target - sum(parts), 6))
        out.append([(lab, a, d) for (lab, _, d), a in zip(layout, parts)])
    return out


def credit_items(amounts, payers, rnd: random.Random, spread: float = 0.45):
    """Monthly credits: amount i split over payers [(label, day, weight)]."""
    out = []
    for a in amounts:
        ws = [w * (1 + spread * (rnd.random() - 0.5)) for _, _, w in payers]
        s = sum(ws)
        parts = [round(a * w / s, 6) for w in ws[:-1]]
        parts.append(round(a - sum(parts), 6))
        out.append([(lab, p, d) for (lab, d, _), p in zip(payers, parts)])
    return out


def limit_rows(pid: str, limits: list[tuple]) -> list[dict]:
    rows = []
    for seq, r in enumerate(limits):
        rows.append(dict(zip(("limit_id", "parent_limit_id", "level", "limit_name", "product_code", "funded_flag", "existing_mn", "outstanding_mn",
                              "proposed_mn", "cash_margin_pct", "commission_pct_pa", "benchmark", "spread_pct", "floor_pct", "tenor_text",
                              "repayment_text", "project_id", "particulars"), r)) | {"proposal_id": pid, "seq": seq, "currency": "SAR", "interchangeable_flag": 0})
    return rows
