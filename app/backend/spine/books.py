"""Books, identities, calendars and units for every v5 module.

Corporate: quarterly, borrower CB#####, facility CF###### (supply-chain
finance CFN#####), group CG####. Retail: monthly, customer RC######, account
RA###### + slot (digit, or B#/M# for BNPL and additional mortgage lines). Money: SAR million in both books. Tenant: the lake's own.

As-of dates differ by design -- corporate at its latest quarter, retail at
its latest month -- as banks run them. A cross-domain comparison uses the
common quarter-end (2026Q2 = June 2026), which both books carry.
"""
from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.cockpit_v4 import domains as dom
from backend.cockpit_v4 import lake

ID_PATTERNS: dict[str, re.Pattern] = {
    "borrower_id": re.compile(r"^CB\d{5}$"),
    "facility_id": re.compile(r"^(CF\d{6}|CFN\d{5})$"),
    "group_id": re.compile(r"^CG\d{1,5}$"),
    "customer_id": re.compile(r"^RC\d{6}$"),
    "account_id": re.compile(r"^RA\d{6}(\d|[BM]\d)$"),  # RA + customer digits + slot (B=BNPL, M=mortgage)
}

#: The quarter-end both books hold: corporate's latest quarter and a month
#: inside retail's window. Cross-domain views compare here, never across
#: mismatched as-of dates.
COMMON_QUARTER_END = {"quarter": "2026Q2", "month": "2026-06", "date": "2026-06-30"}


@dataclass(frozen=True)
class Book:
    domain_id: str
    release_id: str
    frequency: str            # "quarterly" | "monthly"
    period_column: str        # "reporting_quarter" | "reporting_month"
    customer_key: str         # borrower_id | customer_id
    exposure_key: str         # facility_id | account_id
    exposure_relation: str    # corp_facility_quarter | retail_account_month
    customer_relation: str    # corp_borrower_quarter | retail_customer_month

    @property
    def directory(self) -> Path:
        return lake.release_dir(self.release_id)

    def manifest(self) -> dict:
        return lake.read_manifest(self.release_id)

    def path(self, relation: str) -> Path:
        return lake.relation_path(self.release_id, relation)

    @property
    def periods(self) -> list[str]:
        return list(self.manifest()["reporting_periods"])

    @property
    def as_of(self) -> str:
        return str(self.manifest()["latest_period"])

    @property
    def comparison(self) -> str:
        return self.periods[-2]

    @property
    def money_unit(self) -> str:
        m = self.manifest()
        return f"{m['reporting_currency']} {m['amount_scale']}"

    @property
    def tenant(self) -> str:
        return str((self.manifest().get("tenants") or [lake.DEFAULT_TENANT])[0])

    def as_of_label(self, period: str | None = None) -> str:
        period = period or self.as_of
        return quarter_label(period) if self.frequency == "quarterly" else month_label(period)


BOOKS: dict[str, Book] = {
    dom.CORPORATE: Book(dom.CORPORATE, dom.DEFAULT_RELEASES[dom.CORPORATE], "quarterly",
                        "reporting_quarter", "borrower_id", "facility_id",
                        "corp_facility_quarter", "corp_borrower_quarter"),
    dom.RETAIL: Book(dom.RETAIL, dom.DEFAULT_RELEASES[dom.RETAIL], "monthly",
                     "reporting_month", "customer_id", "account_id",
                     "retail_account_month", "retail_customer_month"),
}


def book(domain_id: str) -> Book:
    return BOOKS[dom.parse(domain_id)]


def month_to_quarter(month: str) -> str:
    year, mon = month.split("-")
    return f"{year}Q{(int(mon) - 1) // 3 + 1}"


def quarter_end_month(quarter: str) -> str:
    year, q = quarter.split("Q")
    return f"{year}-{int(q) * 3:02d}"


def quarter_label(quarter: str) -> str:
    """'2026Q2' -> 'Q2 2026 (30 Jun 2026)'."""
    year, q = quarter.split("Q")
    month = int(q) * 3
    day = calendar.monthrange(int(year), month)[1]
    return f"Q{q} {year} ({day} {calendar.month_abbr[month]} {year})"


def month_label(month: str) -> str:
    """'2026-08' -> 'Aug 2026 (31 Aug 2026)'."""
    year, mon = (int(x) for x in month.split("-"))
    day = calendar.monthrange(year, mon)[1]
    return f"{calendar.month_abbr[mon]} {year} ({day} {calendar.month_abbr[mon]} {year})"


@lru_cache(maxsize=1)
def rescale_record() -> dict:
    """What v5 did to the corporate book's magnitudes (empty if nothing)."""
    notes = book(dom.CORPORATE).manifest().get("notes") or {}
    return dict(notes.get("v5_rescale") or {})


def describe() -> dict:
    """Everything a module (or a screen) needs to state its as-of honestly."""
    out = {}
    for domain_id, b in BOOKS.items():
        out[domain_id] = {"release_id": b.release_id, "frequency": b.frequency,
                          "as_of": b.as_of, "as_of_label": b.as_of_label(),
                          "comparison": b.comparison, "money_unit": b.money_unit,
                          "tenant": b.tenant, "periods": b.periods}
    out["common_quarter_end"] = dict(COMMON_QUARTER_END)
    out["corporate_rescale"] = rescale_record()
    return json.loads(json.dumps(out))
