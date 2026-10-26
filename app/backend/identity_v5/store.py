"""Core store: users, sessions, audit log (and, via backend.mail_v5, mail).

One sqlite file (see paths.store_path). Passwords are scrypt-hashed. Session
tokens are random, shown to the browser once, and kept only as a SHA-256.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.identity_v5 import directory, paths

LOCK = threading.RLock()
_READY: set[str] = set()
SESSION_HOURS = 12
LOCKOUT_FAILS = 5
LOCKOUT_MINUTES = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users(
  username TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, title TEXT NOT NULL,
  department TEXT NOT NULL, initials TEXT NOT NULL, books TEXT NOT NULL, team TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0, password_hash TEXT NOT NULL, position INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, view_as TEXT, created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_failures(
  id INTEGER PRIMARY KEY, username TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT, effective_user TEXT, action TEXT NOT NULL,
  target TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS audit_at ON audit(id);
"""


class NotFound(LookupError):
    pass


class NotPermitted(PermissionError):
    pass


class Invalid(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _later(minutes: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r),
                                p=int(p), dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _new_password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(14))


def _test_password() -> str | None:
    """CP_TEST_PASSWORD gives every seeded user one password. Honoured only for a store under a `var/` directory."""
    pw = os.environ.get("CP_TEST_PASSWORD")
    if pw and "var" in paths.store_path().parts:
        return pw
    return None


def _demo_password(username: str) -> str | None:
    """R14 x (R13_FEEDBACK K3, standing rule for Mac demo builds): with CP_DEMO_PASSWORD_IS_USERNAME=1 each seeded user's
    password is their username. Same guard as CP_TEST_PASSWORD: honoured only for a store under a `var/` directory
    (the local demo store served on 127.0.0.1); hosted or bank deployments keep random passwords and the reset flow."""
    if os.environ.get("CP_DEMO_PASSWORD_IS_USERNAME") == "1" and "var" in paths.store_path().parts:
        return username
    return None


# -------------------------------------------------------------- connection


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def db():
    """One connection for one request, committed on success. Creates and seeds the store on first use."""
    path = paths.store_path()
    ensure(path)
    with LOCK:
        con = _open(path)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def ensure(path: Path | None = None) -> dict[str, Any]:
    path = path or paths.store_path()
    key = str(path)
    with LOCK:
        if key in _READY and path.exists():
            return {"store": key, "created": False}
        con = _open(path)
        created = False
        try:
            con.executescript(SCHEMA)
            from backend.mail_v5 import store as mail_store

            con.executescript(mail_store.SCHEMA)
            row = con.execute("SELECT value FROM meta WHERE key='users_seeded'").fetchone()
            if row is None:
                created = True
                _seed_users(con)
                con.execute("INSERT INTO meta(key, value) VALUES('users_seeded', ?)", (now(),))
            dir_row = con.execute("SELECT value FROM meta WHERE key='directory_version'").fetchone()
            if not created and (dir_row is None or dir_row["value"] != directory.DIRECTORY_VERSION):
                _seed_missing_users(con)
            con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('directory_version', ?)",
                        (directory.DIRECTORY_VERSION,))
            mail_row = con.execute("SELECT value FROM meta WHERE key='mail_seed_version'").fetchone()
            mail_version = mail_store.seed_version()
            if mail_row is None or mail_row["value"] != mail_version:
                if mail_version == mail_store.SEED_VERSION_DEALDESK:
                    from backend.mail_v5 import seed_dealdesk as mail_seed
                else:
                    from backend.mail_v5 import seed as mail_seed

                mail_seed.apply(con)
                con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('mail_seed_version', ?)",
                            (mail_version,))
            con.commit()
        finally:
            con.close()
        _READY.add(key)
        return {"store": key, "created": created}


def reset_ready() -> None:
    """For tests that swap CORE_STORE."""
    _READY.clear()


def _seed_users(con: sqlite3.Connection) -> None:
    test_pw = _test_password()
    issued: list[tuple[str, str, str]] = []
    for u in directory.seed_users():
        pw = test_pw or _demo_password(u["username"]) or _new_password()
        con.execute(
            "INSERT OR IGNORE INTO users(username, name, role, title, department, initials, books, team, is_admin,"
            " password_hash, position) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (u["username"], u["name"], u["role"], u["title"], u["department"], u["initials"],
             json.dumps(u["books"]), u["team"], 1 if u["is_admin"] else 0, hash_password(pw), u["position"]))
        issued.append((u["username"], u["name"], pw))
    if not test_pw:
        write_users_local(issued)


def _seed_missing_users(con: sqlite3.Connection) -> None:
    """Directory users a store seeded earlier does not have yet (PLAN_R5): added with new passwords, which are
    appended to the local users file (the existing passwords are kept)."""
    have = {r[0] for r in con.execute("SELECT username FROM users")}
    test_pw = _test_password()
    issued = []
    for u in directory.seed_users():
        if u["username"] in have:
            continue
        pw = test_pw or _demo_password(u["username"]) or _new_password()
        con.execute(
            "INSERT OR IGNORE INTO users(username, name, role, title, department, initials, books, team, is_admin,"
            " password_hash, position) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (u["username"], u["name"], u["role"], u["title"], u["department"], u["initials"],
             json.dumps(u["books"]), u["team"], 1 if u["is_admin"] else 0, hash_password(pw), u["position"]))
        issued.append((u["username"], u["name"], pw))
    if issued and not test_pw:
        path = paths.users_local_path()
        try:
            old = path.read_text(encoding="utf-8") if path.exists() else ""
        except OSError:
            old = ""
        add = "\n".join(f"| `{u}` | {n} | `{pw}` |" for u, n, pw in issued)
        if old and "| Username |" in old:
            text = old.rstrip("\n") + "\n" + add + "\n"
            path.write_text(text, encoding="utf-8")
        else:
            write_users_local(issued)


def write_users_local(issued: list[tuple[str, str, str]]) -> Path:
    """Initial passwords, outside the repository. Never printed or committed."""
    path = paths.users_local_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CreditProbe v5 local users (generated; never commit, never share)", "",
        f"Generated {now()} by the Core service on first start. Sign in at http://127.0.0.1:5500/login.", "",
        "| Username | Name | Password |", "|---|---|---|",
    ]
    lines += [f"| `{u}` | {n} | `{pw}` |" for u, n, pw in issued]
    lines += ["", "To issue new passwords: `.venv/bin/python -m backend.identity_v5.reset_passwords`.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


# ----------------------------------------------------------------- users


def _user_row(r: sqlite3.Row) -> dict[str, Any]:
    return {"username": r["username"], "name": r["name"], "role": r["role"], "title": r["title"],
            "department": r["department"], "initials": r["initials"], "books": json.loads(r["books"]),
            "team": r["team"], "is_admin": bool(r["is_admin"])}


def users(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [_user_row(r) for r in con.execute("SELECT * FROM users ORDER BY position")]


def user_map(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {u["username"]: u for u in users(con)}


def get_user(con: sqlite3.Connection, username: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if r is None:
        raise NotFound(f"No user '{username}'.")
    return _user_row(r)


def find_user(con: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    r = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return _user_row(r) if r else None


# ----------------------------------------------------------------- audit


def audit(con: sqlite3.Connection, actor: str | None, effective: str | None, action: str, target: str = "",
          detail: dict[str, Any] | None = None) -> int:
    cur = con.execute("INSERT INTO audit(at, actor, effective_user, action, target, detail) VALUES(?,?,?,?,?,?)",
                      (now(), actor, effective, action, target, json.dumps(detail or {}, ensure_ascii=False)))
    return int(cur.lastrowid)


def audit_list(con: sqlite3.Connection, actor: str = "", action: str = "", limit: int = 100,
               offset: int = 0) -> dict[str, Any]:
    where, args = [], []
    if actor:
        where.append("(actor=? OR effective_user=?)")
        args += [actor, actor]
    if action:
        where.append("action=?")
        args.append(action)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = int(con.execute(f"SELECT COUNT(*) FROM audit {clause}", args).fetchone()[0])
    rows = con.execute(f"SELECT * FROM audit {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                       args + [max(1, min(limit, 500)), max(0, offset)]).fetchall()
    return {"events": [{"id": r["id"], "at": r["at"], "actor": r["actor"], "effective_user": r["effective_user"],
                        "action": r["action"], "target": r["target"], "detail": json.loads(r["detail"])}
                       for r in rows], "total": total}


# -------------------------------------------------------------- sessions


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def login(con: sqlite3.Connection, username: str, password: str) -> tuple[str, dict[str, Any]]:
    username = (username or "").strip().lower()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fails = int(con.execute("SELECT COUNT(*) FROM login_failures WHERE username=? AND at>=?",
                            (username, cutoff)).fetchone()[0])
    if fails >= LOCKOUT_FAILS:
        audit(con, username, None, "login_locked", username)
        raise NotPermitted(f"Too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes.")
    row = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    # Verify against a dummy hash for an unknown user so timing does not reveal which names exist.
    stored = row["password_hash"] if row else hash_password("not-a-user")
    ok = verify_password(password or "", stored)
    if not row or not ok:
        con.execute("INSERT INTO login_failures(username, at) VALUES(?,?)", (username, now()))
        audit(con, username, None, "login_failed", username)
        con.commit()
        raise NotPermitted("Wrong username or password.")
    con.execute("DELETE FROM login_failures WHERE username=?", (username,))
    token = secrets.token_urlsafe(32)
    con.execute("INSERT INTO sessions(token_hash, username, view_as, created_at, expires_at) VALUES(?,?,?,?,?)",
                (_hash_token(token), username, None, now(), _later(SESSION_HOURS * 60)))
    audit(con, username, username, "login", username)
    return token, _user_row(row)


def session_info(con: sqlite3.Connection, token: str | None) -> dict[str, Any] | None:
    """The signed-in user, the user the data is shown for, and whether a view-as is active."""
    if not token:
        return None
    r = con.execute("SELECT * FROM sessions WHERE token_hash=?", (_hash_token(token),)).fetchone()
    if r is None or r["expires_at"] < now():
        return None
    real = find_user(con, r["username"])
    if real is None:
        return None
    viewing = find_user(con, r["view_as"]) if r["view_as"] and real["is_admin"] else None
    return {"user": real, "viewing_as": viewing, "effective_user": viewing or real, "is_admin": real["is_admin"]}


def logout(con: sqlite3.Connection, token: str | None) -> None:
    if not token:
        return
    info = session_info(con, token)
    con.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))
    if info:
        audit(con, info["user"]["username"], info["effective_user"]["username"], "logout",
              info["user"]["username"])


def set_view_as(con: sqlite3.Connection, token: str, username: str | None) -> dict[str, Any]:
    info = session_info(con, token)
    if info is None:
        raise NotPermitted("not signed in")
    if not info["is_admin"]:
        raise NotPermitted("Only the Administrator can view as another user.")
    if username and username == info["user"]["username"]:
        username = None
    if username:
        get_user(con, username)
    con.execute("UPDATE sessions SET view_as=? WHERE token_hash=?", (username, _hash_token(token)))
    audit(con, info["user"]["username"], username or info["user"]["username"], "view_as", username or "(self)")
    return session_info(con, token) or info


def purge_expired(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM sessions WHERE expires_at<?", (now(),))


def reset_passwords(con: sqlite3.Connection) -> Path:
    issued = []
    for u in users(con):
        pw = _new_password()
        con.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(pw), u["username"]))
        issued.append((u["username"], u["name"], pw))
    con.execute("DELETE FROM sessions")
    return write_users_local(issued)


# -------------------------------------------------------------- preferences (PLAN_R6 B4)
#: Per-user preferences the UI keeps on the server so they survive sign-out and sign-in.
#: Only known keys are stored; each value is a short string ('' clears it).
PREFERENCE_KEYS = {"presenter_name": 60}

_PREFS_SCHEMA = ("CREATE TABLE IF NOT EXISTS user_preferences("
                 "username TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, updated_at TEXT NOT NULL, "
                 "PRIMARY KEY(username, key))")


def preferences(con: sqlite3.Connection, username: str) -> dict[str, str]:
    con.execute(_PREFS_SCHEMA)
    rows = con.execute("SELECT key, value FROM user_preferences WHERE username=?", (username,)).fetchall()
    out = {k: "" for k in PREFERENCE_KEYS}
    out.update({r[0]: r[1] for r in rows if r[0] in PREFERENCE_KEYS})
    return out


def set_preferences(con: sqlite3.Connection, username: str, values: dict[str, Any]) -> dict[str, str]:
    con.execute(_PREFS_SCHEMA)
    for key, raw in values.items():
        if key not in PREFERENCE_KEYS:
            raise Invalid(f"Unknown preference: {key}")
        value = " ".join(str(raw or "").split())
        if len(value) > PREFERENCE_KEYS[key]:
            raise Invalid(f"{key} is longer than {PREFERENCE_KEYS[key]} characters")
        if value:
            con.execute("INSERT INTO user_preferences(username, key, value, updated_at) VALUES(?,?,?,?) "
                        "ON CONFLICT(username, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                        (username, key, value, now()))
        else:
            con.execute("DELETE FROM user_preferences WHERE username=? AND key=?", (username, key))
    return preferences(con, username)
