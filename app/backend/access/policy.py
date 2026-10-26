"""Effective data-access policy of a user (PLAN_R5 A1).

A policy (Admin -> Workflow -> Data access) says, for the users, roles and teams it is assigned to:
  books      corporate / retail
  scope      per book: sectors, sub_sectors, regions, branches, rm_ids ("own" = the user's own RM portfolio),
             segments, business_units (an empty list means every value)
  modules    the v5 modules the user may open ("*" = all)
  actions    export, send, approve, run_model
  mask       obligor_name, obligor_id (column masking)

A user with several policies gets their union (rows any policy allows; modules and actions any policy grants);
masking applies only when every policy masks. A user with no policy sees the books on their Core profile, every
module and action. The Administrator (not viewing as someone) is unrestricted.

Policies are read from the Admin service's store (live, approved versions only), read-only, cached a few seconds.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from backend.access import dims

V5 = Path(__file__).resolve().parents[2]

MODULES: dict[str, str] = {
    "cockpit": "Cockpit", "early_warning": "Early Warning", "borrower_360": "Customer 360", "what_if": "What-If",
    "scorecard": "Scorecard Validation", "deal_desk": "Deal Desk", "lenses": "Lenses", "playbook": "Playbook",
    "policy_docs": "Policy Docs", "projects": "Projects, analyses and investigations", "mail": "Mail",
    "data_builder": "Data Domains", "admin": "Admin",
}
DEALDESK_EDITION_MODULES = ("cockpit", "deal_desk", "playbook", "policy_docs", "projects", "mail", "data_builder", "admin")


def modules() -> dict[str, str]:
    """The modules the Admin screens list and policies grant: the whole map in the full product, the modules in the
    product in the Deal Desk edition (V5_EDITION, read at call time). A policy row naming another module still parses."""
    if (os.environ.get("V5_EDITION") or "dealdesk").strip().lower() == "full":
        return dict(MODULES)
    return {k: v for k, v in MODULES.items() if k in DEALDESK_EDITION_MODULES}
ACTIONS: dict[str, str] = {"export": "Export (Excel, Word, CSV)", "send": "Send and share through Mail",
                           "approve": "Approve in workflows", "run_model": "Run models and scenarios"}
TTL = 3.0


def admin_store_path() -> Path:
    return Path(os.environ.get("ADMIN_STORE") or V5 / "var" / "admin" / "admin.sqlite").expanduser().resolve()


def core_store_path() -> Path:
    return Path(os.environ.get("CORE_STORE") or V5 / "var" / "core" / "core.sqlite").expanduser().resolve()


@dataclass(frozen=True)
class Scope:
    """One policy's row scope in one book: field -> allowed values (missing field = any)."""
    filters: tuple[tuple[str, frozenset[str]], ...] = ()

    def as_dict(self) -> dict[str, list[str]]:
        return {k: sorted(v) for k, v in self.filters}


@dataclass(frozen=True)
class Policy:
    username: str
    unrestricted: bool = False
    books: frozenset[str] = frozenset({"corporate", "retail"})
    scopes: tuple[tuple[str, tuple[Scope, ...]], ...] = ()      # book -> scopes (union); missing book = all rows
    modules: frozenset[str] | None = None                         # None = every module
    actions: frozenset[str] = frozenset(ACTIONS)
    mask_names: bool = False
    mask_ids: bool = False
    policies: tuple[tuple[str, str], ...] = ()                     # (id, name) applied
    user: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    # ------------------------------------------------------------ questions
    @property
    def fingerprint(self) -> str:
        if self.unrestricted:
            return "all"
        raw = json.dumps([sorted(self.books), [(b, [s.as_dict() for s in ss]) for b, ss in self.scopes],
                          self.mask_names, self.mask_ids], sort_keys=True)
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    @property
    def row_restricted(self) -> bool:
        if self.unrestricted:
            return False
        return (self.books != frozenset({"corporate", "retail"}) or self.mask_names or self.mask_ids
                or any(any(s.filters for s in ss) for _, ss in self.scopes))

    def allows_book(self, book: str) -> bool:
        return self.unrestricted or book in self.books

    def allows_module(self, module: str) -> bool:
        return self.unrestricted or self.modules is None or module in self.modules

    def allows_action(self, action: str) -> bool:
        return self.unrestricted or action in self.actions

    def scopes_for(self, book: str) -> tuple[Scope, ...] | None:
        for b, ss in self.scopes:
            if b == book:
                return ss
        return None

    def allowed_ids(self, book: str) -> frozenset[str] | None:
        """The customer IDs (borrower_id / customer_id) the user may see in a book; None = all of them."""
        if self.unrestricted:
            return None
        if book not in self.books:
            return frozenset()
        ss = self.scopes_for(book)
        if ss is None or any(not s.filters for s in ss):
            return None
        return _allowed(book, ss)

    def allows_id(self, owner_id: str) -> bool:
        s = str(owner_id)
        book = dims.book_of(s)
        if book is None:
            return True
        if book == "corporate" and s.startswith("CF"):
            s = dims.facility_owner().get(s, s)
        if book == "corporate" and s.startswith("CG"):
            ids = self.allowed_ids(book)
            return ids is None or bool(dims.group_members().get(s, set()) & ids)
        if book == "retail" and s.startswith("RA"):
            s = "RC" + s[2:8]
        ids = self.allowed_ids(book)
        return ids is None or s in ids

    def describe(self) -> dict[str, Any]:
        return {"username": self.username, "unrestricted": self.unrestricted, "books": sorted(self.books),
                "scopes": {b: [s.as_dict() for s in ss] for b, ss in self.scopes},
                "modules": sorted(self.modules) if self.modules is not None else ["*"],
                "actions": sorted(self.actions), "mask": {"obligor_name": self.mask_names, "obligor_id": self.mask_ids},
                "policies": [{"id": i, "name": n} for i, n in self.policies], "fingerprint": self.fingerprint,
                "row_restricted": self.row_restricted}


_ALLOWED: dict[tuple[str, tuple], frozenset[str]] = {}


def _allowed(book: str, scopes: tuple[Scope, ...]) -> frozenset[str]:
    key = (book, scopes)
    hit = _ALLOWED.get(key)
    if hit is not None:
        return hit
    df = dims.frame(book)
    mask = pd.Series(False, index=df.index)
    for s in scopes:
        m = pd.Series(True, index=df.index)
        for f, vals in s.filters:
            col = dims.FIELDS[book].get(f)
            if col is None:
                continue
            m &= df[col].astype(str).isin(vals)
        mask |= m
    out = frozenset(df.index[mask].astype(str))
    if len(_ALLOWED) > 256:
        _ALLOWED.clear()
    _ALLOWED[key] = out
    return out


UNRESTRICTED = Policy(username="", unrestricted=True)


# ------------------------------------------------------------------ reading the stores
def _ro(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        return con
    except sqlite3.Error:
        return None


def _live(kind: str) -> list[dict[str, Any]]:
    con = _ro(admin_store_path())
    if con is None:
        return []
    try:
        return [json.loads(r["body"]) for r in con.execute("SELECT body FROM live WHERE kind=? ORDER BY id", (kind,))]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def core_user(username: str) -> dict[str, Any] | None:
    con = _ro(core_store_path())
    if con is None:
        return None
    try:
        r = con.execute("SELECT username, name, role, team, books, is_admin FROM users WHERE username=?",
                        (username,)).fetchone()
        if r is None:
            return None
        return {"username": r["username"], "name": r["name"], "role": r["role"], "team": r["team"],
                "books": json.loads(r["books"] or "[]"), "is_admin": bool(r["is_admin"])}
    except sqlite3.Error:
        return None
    finally:
        con.close()


def admin_profile(username: str) -> dict[str, Any]:
    return next((u for u in _live("user") if u.get("username") == username), {})


def policies_for(username: str, profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    prof = profile if profile is not None else admin_profile(username)
    role, team = prof.get("role", ""), prof.get("team", "")
    out = []
    for p in _live("policy"):
        if p.get("status", "active") != "active":
            continue
        a = p.get("assignees") or {}
        if username in (a.get("users") or []) or (role and role in (a.get("roles") or [])) \
                or (team and team in (a.get("teams") or [])):
            out.append(p)
    return out


def build(username: str, user: dict[str, Any] | None = None, profile: dict[str, Any] | None = None,
          policies: list[dict[str, Any]] | None = None) -> Policy:
    """The effective policy for a username. `user` is the Core user (books, is_admin); read when not given."""
    if not username:
        return UNRESTRICTED
    user = user if user is not None else (core_user(username) or {})
    prof = profile if profile is not None else admin_profile(username)
    if user.get("is_admin") and not prof.get("policy_applies_to_admin"):
        return Policy(username=username, unrestricted=True, user=user)
    if prof.get("status") == "deactivated":
        return Policy(username=username, books=frozenset(), modules=frozenset(), actions=frozenset(), user=user,
                      policies=(("deactivated", "Deactivated user"),))
    pols = policies if policies is not None else policies_for(username, prof)
    base_books = frozenset(user.get("books") or prof.get("books") or ["corporate", "retail"])
    if not pols:
        return Policy(username=username, books=base_books, user=user)
    books: set[str] = set()
    scopes: dict[str, list[Scope]] = {}
    modules: set[str] | None = set()
    actions: set[str] = set()
    mask_n, mask_i = True, True
    for p in pols:
        pb = set(p.get("books") or ["corporate", "retail"]) & set(base_books)
        books |= pb
        for b in pb:
            sc = (p.get("scope") or {}).get(b) or {}
            filters = []
            for f, vals in sc.items():
                if f not in dims.FIELDS[b]:
                    continue
                vals = list(vals or [])
                if f == "rm_ids" and "own" in vals:
                    vals = [v for v in vals if v != "own"] + ([prof["rm_id"]] if prof.get("rm_id") else ["(none)"])
                if f == "branches" and "own" in vals:
                    vals = [v for v in vals if v != "own"] + ([prof["branch_id"]] if prof.get("branch_id") else ["(none)"])
                if vals:
                    filters.append((f, frozenset(str(v) for v in vals)))
            scopes.setdefault(b, []).append(Scope(tuple(sorted(filters, key=lambda x: x[0]))))
        mods = p.get("modules") or ["*"]
        if "*" in mods:
            modules = None
        elif modules is not None:
            modules |= set(mods)
        acts = p.get("actions")
        actions |= set(ACTIONS) if acts is None else {a for a in ACTIONS if acts.get(a, True)}
        mask = p.get("mask") or {}
        mask_n &= bool(mask.get("obligor_name"))
        mask_i &= bool(mask.get("obligor_id"))
    return Policy(username=username, books=frozenset(books),
                  scopes=tuple(sorted((b, tuple(ss)) for b, ss in scopes.items())),
                  modules=frozenset(modules) if modules is not None else None, actions=frozenset(actions),
                  mask_names=mask_n, mask_ids=mask_i, policies=tuple((p.get("id", ""), p.get("name", "")) for p in pols),
                  user=user)


_CACHE: dict[str, tuple[float, Policy]] = {}
_LOCK = threading.Lock()


def for_user(user: dict[str, Any] | str | None) -> Policy:
    """The effective policy for a Core user dict (as `current_user` returns it) or a username. Cached briefly."""
    if not user:
        return UNRESTRICTED
    username = user if isinstance(user, str) else str(user.get("username") or "")
    if not username:
        return UNRESTRICTED
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(username)
    if hit and now - hit[0] < TTL:
        return hit[1]
    core = core_user(username)
    if core is None and isinstance(user, dict):
        core = {k: user.get(k) for k in ("username", "name", "role", "team", "books", "is_admin")}
    pol = build(username, core or {})
    with _LOCK:
        _CACHE[username] = (now, pol)
    return pol


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()
    _ALLOWED.clear()
