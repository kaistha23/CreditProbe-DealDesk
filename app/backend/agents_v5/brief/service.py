"""Noor's brief service: compose the role-based brief, the module briefs, Why?, What should we do?, Send to committee,
and the bank settings (name and voice). Every function here is deterministic unless `polish=True` and a key is set.

The last brief per (persona, module) is kept in memory for 10 minutes so that Why? and What should we do? answer on
exactly the line the reader saw; a line not in the cache is rebuilt from the sources by its id.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from backend.agents_v5.brief import answers, rank, sources, wording
from backend.agents_v5.brief.items import PERSONAS, persona_for

V5 = Path(__file__).resolve().parents[3]
TOP = 5
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LOCK = threading.RLock()

#: R16 m (M1): voice is OFF for the bank by default ("it speaks on login"). Noor never speaks on its own: speech
#: starts only from a click on a speaker button, and only with a voice chosen in Settings -> Voice. Each reader's own
#: on/off choice is still kept per user (`user_voice`).
DEFAULT_SETTINGS = {"name": "Noor", "voice": {"enabled": False, "gender": "male", "language": "en", "rate": 0.92,
                                         "pitch": 0.9},
                    "speak_first": True}
#: R14 n (K10): male voices only (Anne: "male, calm, soothing, genuine voice in Arabic and English").
VOICES = {"gender": ("male",), "language": ("en", "ar-gulf")}
#: R15 a (L2): the voice Anne chooses in Settings -> Voice, one per language, becomes the bank's default. None until
#: chosen: until then Noor stays silent, even on a speaker click, and says "Choose a voice in Settings -> Voice" (M1).
CHOSEN_LANGS = ("en", "ar-gulf")
RATE_RANGE, PITCH_RANGE = (0.5, 1.5), (0.5, 1.5)


def clean_chosen(v: Any, lang: str) -> dict[str, Any] | None:
    """One chosen voice: {name, lang, rate, pitch, label?}, validated; None clears the choice for that language."""
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError(f"voice.chosen.{lang}: an object {{name, lang, rate, pitch}} or null.")
    name = " ".join(str(v.get("name") or "").split())[:80]
    vlang = str(v.get("lang") or "").strip().replace("_", "-")[:16]
    if not name:
        raise ValueError(f"voice.chosen.{lang}: the voice needs its name.")
    want = "ar" if lang == "ar-gulf" else "en"
    if not vlang.lower().startswith(want):
        raise ValueError(f"voice.chosen.{lang}: needs {'an Arabic' if want == 'ar' else 'an English'} voice (lang {want}-…).")
    out: dict[str, Any] = {"name": name, "lang": vlang}
    # R16 v: a neural voice (the offline add-on, backend/agents_v5/voice) is chosen by its id, e.g. am_michael.
    if v.get("engine") not in (None, "", "browser", "neural"):
        raise ValueError(f"voice.chosen.{lang}.engine: browser or neural.")
    if v.get("engine") == "neural":
        from backend.agents_v5.voice.engine import BY_ID  # noqa: PLC0415
        nv = BY_ID.get(name)
        if not nv or nv.group != lang:
            raise ValueError(f"voice.chosen.{lang}: {name} is not a neural {'Arabic' if want == 'ar' else 'English'} voice.")
        out["engine"] = "neural"
        label = " ".join(str(v.get("label") or "").split())[:80]
        if label:
            out["label"] = label
    for k, (lo, hi), d in (("rate", RATE_RANGE, 0.92), ("pitch", PITCH_RANGE, 0.9)):
        try:
            x = float(v.get(k, d))
        except (TypeError, ValueError):
            raise ValueError(f"voice.chosen.{lang}.{k}: a number.") from None
        if not lo <= x <= hi:
            raise ValueError(f"voice.chosen.{lang}.{k}: between {lo} and {hi}.")
        out[k] = round(x, 2)
    return out


def home() -> Path:
    p = Path(os.environ.get("NOOR_HOME") or (V5 / "var" / "noor"))
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------ settings (bank-level)

def settings() -> dict[str, Any]:
    try:
        stored = json.loads((home() / "settings.json").read_text())
    except (OSError, ValueError):
        stored = {}
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    out.update({k: v for k, v in stored.items() if k in ("name", "speak_first")})
    out["voice"].update({k: v for k, v in (stored.get("voice") or {}).items() if k in out["voice"]})
    out["voice"]["gender"] = "male"  # a stored "female" from before R14 is not honoured
    out["voice"]["rate"], out["voice"]["pitch"] = 0.92, 0.9
    chosen = (stored.get("voice") or {}).get("chosen") or {}
    out["voice"]["chosen"] = {k: (chosen.get(k) if isinstance(chosen, dict) and isinstance(chosen.get(k), dict) else None)
                              for k in CHOSEN_LANGS}
    return out


def save_settings(body: dict[str, Any], *, by: str) -> dict[str, Any]:
    cur = settings()
    if "name" in body:
        name = " ".join(str(body["name"] or "").split())[:24]
        if not name:
            raise ValueError("The assistant needs a name.")
        cur["name"] = name
    if "speak_first" in body:
        cur["speak_first"] = bool(body["speak_first"])
    v = body.get("voice") or {}
    if "enabled" in v:
        cur["voice"]["enabled"] = bool(v["enabled"])
    for k, allowed in VOICES.items():
        if k in v:
            if v[k] not in allowed:
                raise ValueError(f"voice.{k}: one of {', '.join(allowed)}.")
            cur["voice"][k] = v[k]
    if "chosen" in v:
        ch = v["chosen"]
        if not isinstance(ch, dict) or any(k not in CHOSEN_LANGS for k in ch):
            raise ValueError("voice.chosen: {en?, ar-gulf?}, each a voice or null.")
        for k, x in ch.items():
            c = clean_chosen(x, k)
            if c is not None:
                c["chosen_by"], c["chosen_at"] = by, datetime.now().isoformat(timespec="seconds")
            cur["voice"]["chosen"][k] = c
    cur["updated_by"], cur["updated_at"] = by, datetime.now().isoformat(timespec="seconds")
    (home() / "settings.json").write_text(json.dumps(cur, indent=1))
    return cur


# ------------------------------------------------------------------ the reader's own voice choice (R13 H, J1)

def _voices_file() -> Path:
    return home() / "user_voice.json"


def user_voice(username: str) -> dict[str, Any]:
    """The reader's own voice choice: {on: bool | None, language: "en" | "ar-gulf" | None}. None = never chosen."""
    try:
        stored = json.loads(_voices_file().read_text())
    except (OSError, ValueError):
        stored = {}
    got = stored.get(username or "") or {}
    return {"on": got.get("on"), "language": got.get("language")}


def save_user_voice(username: str, body: dict[str, Any]) -> dict[str, Any]:
    if not username:
        raise ValueError("Sign in to keep a voice preference.")
    with _LOCK:
        try:
            stored = json.loads(_voices_file().read_text())
        except (OSError, ValueError):
            stored = {}
        cur = stored.get(username) or {}
        if "on" in body:
            cur["on"] = bool(body["on"])
        if "language" in body:
            if body["language"] not in VOICES["language"]:
                raise ValueError(f"language: one of {', '.join(VOICES['language'])}.")
            cur["language"] = body["language"]
        cur["updated_at"] = datetime.now().isoformat(timespec="seconds")
        stored[username] = cur
        _voices_file().write_text(json.dumps(stored, indent=1))
    return user_voice(username)


# ------------------------------------------------------------------ the brief

def brief(*, role: str = "", persona: str = "", user: dict[str, Any] | None = None, module: str = "",
          attention: list[dict[str, Any]] | None = None, today: date | None = None, hour: int | None = None,
          top: int = TOP, polish: bool = False) -> dict[str, Any]:
    t0 = time.monotonic()
    user = user or {}
    p = persona_for(role or user.get("role"), persona)
    today = today or date.today()
    hour = datetime.now().hour if hour is None else hour
    only = wording.MODULE_SOURCES.get(module) or None
    ctx = {"persona": p, "today": today, "attention": attention or [], "user": user}
    items, status = sources.collect(ctx, only=only)
    me = str(user.get("name") or "")
    ranked = rank.rank(items, p, today, me)
    top = max(3, min(int(top or TOP), 5))
    ranked = diversify(ranked, top)
    rows = [{**r, "evidence": evidence_of(r)} for r in rank.as_rows(ranked)]
    shown, more = rows[:top], rows[top:]
    cfg = settings()
    first = str(user.get("name") or "").split(" ")[0]
    if module:
        sentence = wording.module_opening(module, shown, len(rows))
    else:
        sentence = wording.opening(p, first, len(shown), len(rows), shown, hour, cfg["name"])
    sentence_ar = "" if module else wording.opening_ar(p, first, len(shown), len(rows), shown, hour)
    sentence, how = wording.polish(sentence, enabled=polish)
    # R14 n (K9): "new" only when the line's source refreshed since this reader's last visit (never on a first visit).
    fresh = mark_new(str(user.get("username") or ""), p, module, rows)
    for r in rows:
        r["new"] = r["source"] in fresh
    head = wording.headline(p, shown, len(rows), module)
    head_ar = wording.headline_ar(shown, module)
    from backend.agents_v5.brief import spoken
    out = {
        "assistant": cfg["name"], "persona": p, "persona_label": PERSONAS[p]["label"],
        "title": (wording.MODULE_LABEL.get(module, module).capitalize() + " brief") if module
        else PERSONAS[p]["brief_title"],
        "module": module or None, "date": today.isoformat(), "date_label": wording.when(today),
        "data_dates": wording.data_dates(rows),
        "headline": head, "headline_ar": head_ar, "opening": sentence, "opening_ar": sentence_ar,
        "script": spoken.brief_script(head, head_ar, shown),
        "wording": how, "items": shown, "more": more, "n_more": len(more), "n_total": len(rows),
        "sources": status, "ranking": "deterministic: severity × persona weight × materiality × urgency; ties by id",
        "ms": int((time.monotonic() - t0) * 1000),
    }
    with _LOCK:
        _CACHE[_key(p, module)] = (time.time(), out)
    return out


VISIT_GAP_S = 30 * 60


def _visits_file() -> Path:
    return home() / "brief_visits.json"


def source_fingerprints(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Per source, what "refreshed" means: the latest data period behind its lines (periodic sources), else a hash of
    its lines (live stores such as the deal queue)."""
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["source"], []).append(r)
    out = {}
    for src_name, rs in by.items():
        periods = sorted({str(t.get("period") or "") for r in rs for t in (r.get("trace") or []) if isinstance(t, dict)} - {""})
        if periods:
            out[src_name] = "period:" + periods[-1]
        else:
            out[src_name] = "lines:" + hashlib.sha1("|".join(sorted(r["title"] for r in rs)).encode()).hexdigest()[:12]
    return out


def mark_new(username: str, persona: str, module: str, rows: list[dict[str, Any]], now: float | None = None) -> set[str]:
    """Sources whose data refreshed since this reader's previous visit. A visit is a gap of 30 minutes or more between
    briefs, so reading the brief twice in one sitting keeps the same "new" marks. Nothing is new on a first visit."""
    if not username:
        return set()
    now = time.time() if now is None else now
    key = f"{username}|{persona}|{module or ''}"
    fps = source_fingerprints(rows)
    with _LOCK:
        try:
            stored = json.loads(_visits_file().read_text())
        except (OSError, ValueError):
            stored = {}
        rec = stored.get(key) or {}
        cur, prev = rec.get("current"), rec.get("previous")
        if cur is None:
            rec = {"current": {"at": now, "fps": fps}, "previous": None}
        elif now - float(cur.get("at") or 0) >= VISIT_GAP_S:
            rec = {"current": {"at": now, "fps": fps}, "previous": cur}
        else:
            rec["current"] = {"at": float(cur.get("at") or now), "fps": {**(cur.get("fps") or {}), **fps}}
        stored[key] = rec
        try:
            _visits_file().write_text(json.dumps(stored, indent=1))
        except OSError:
            pass
        prev = rec.get("previous")
    if not prev:
        return set()
    old = prev.get("fps") or {}
    return {s for s, fp in fps.items() if s in old and old[s] != fp}


def issue_script(item: dict[str, Any]) -> dict[str, Any]:
    """The spoken script for one brief line (K10): 40–70 seconds, English and Arabic."""
    from backend.agents_v5.brief import spoken
    return spoken.issue_script(item)


def evidence_of(row: dict[str, Any]) -> list[dict[str, str]]:
    """The deterministic Cockpit attention card behind a line (J2 (a)): what its Why? opens as evidence."""
    ids: list[str] = []
    if str(row.get("id", "")).startswith("cockpit:"):
        ids.append(str(row["id"]).split(":", 1)[1])
    extra = (row.get("entity") or {}).get("cockpit_item")
    if extra:
        ids.append(str(extra))
    for t in row.get("trace") or []:
        if isinstance(t, dict) and t.get("status") == "frozen_feed" and (t.get("keys") or {}).get("item_id"):
            ids.append(str(t["keys"]["item_id"]))
    out, seen = [], set()
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            out.append({"kind": "cockpit_attention", "item_id": i, "label": "Cockpit attention card",
                        "href": f"/?attention={i}"})
    return out


def diversify(ranked: list, top: int, per_source: int = 2) -> list:
    """At most `per_source` lines from one source in the top lines; the rest keep their order below."""
    head, tail, count = [], [], {}
    for it, sc in ranked:
        if len(head) < top and count.get(it.source, 0) < per_source:
            head.append((it, sc))
            count[it.source] = count.get(it.source, 0) + 1
        else:
            tail.append((it, sc))
    return head + tail


def _key(persona: str, module: str) -> str:
    return f"{persona}|{module or ''}"


def find_item(item_id: str, *, persona: str = "", module: str = "", attention: list[dict[str, Any]] | None = None,
              item: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if item and item.get("id") == item_id:
        return item
    with _LOCK:
        for k, (ts, b) in list(_CACHE.items()):
            if time.time() - ts > 600:
                _CACHE.pop(k, None)
                continue
            for row in b["items"] + b["more"]:
                if row["id"] == item_id:
                    return row
    ctx = {"persona": persona or "cro", "today": date.today(), "attention": attention or []}
    items, _ = sources.collect(ctx)
    for i in items:
        if i.id == item_id:
            return i.to_dict()
    return None


def why(item: dict[str, Any]) -> dict[str, Any]:
    from backend.agents_v5.brief import spoken
    t0 = time.monotonic()
    out = answers.why(item)
    # K10: the speaker on this answer reads the line's spoken script (the explanation), not the screen text.
    try:
        sc = spoken.issue_script(item, why=out, options=None)
        out["spoken"], out["spoken_ar"] = sc["en"], sc["ar"]
        out["plain_words"] = sc["plain_words"]
    except Exception:  # noqa: BLE001
        out["spoken"], out["spoken_ar"] = spoken.speakable(out.get("answer") or ""), ""
        out["plain_words"] = []
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


def what_to_do(item: dict[str, Any]) -> dict[str, Any]:
    t0 = time.monotonic()
    out = answers.options(item)
    from backend.agents_v5.brief import spoken
    out["spoken"] = spoken.answer_summary("options", out, item)
    out["plain_words"] = spoken.options_plain_words(out)
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


def who_drives(item: dict[str, Any]) -> dict[str, Any]:
    t0 = time.monotonic()
    out = answers.drivers(item)
    from backend.agents_v5.brief import spoken
    out["spoken"] = spoken.answer_summary("drivers", out, item)
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


# ------------------------------------------------------------------ Send to committee

def send_to_committee(item: dict[str, Any], option: dict[str, Any] | None, *, user: str, role: str = "") -> dict[str, Any]:
    """Create the committee item: a pending decision for the credit committee chair (CCO), with the option's numbers
    and the trace, in the agents' approvals queue (so it shows in Approvals and in the CRO's brief), plus the agenda
    entry Noor keeps (`var/noor/committee.jsonl`). Nothing is applied until the committee decides."""
    from backend.agents_v5.runtime import approvals
    opt = option or {}
    title = f"Committee: {item.get('entity', {}).get('name') or item.get('title', '')[:80]}"
    if opt.get("title"):
        title += f": {opt['title']}"
    reason = (f"{item.get('title', '')}. Proposed: {opt.get('title', 'decision needed')}. "
              + "; ".join(f"{n['label']} {n.get('display')}" for n in (opt.get("numbers") or [])[:5]))
    row = approvals.propose(
        {"kind": "committee_item", "item_id": item.get("id"), "option": opt.get("key"), "figures": opt.get("figures") or {},
         "deals": opt.get("deals") or (item.get("entity") or {}).get("deals") or []},
        "CCO", kind="committee_item", title=title[:300], reason=reason[:1200],
        evidence=[json.dumps(t, default=str) for t in (item.get("trace") or [])[:6] if t], agent="noor.brief",
        maker=user or "noor", scope="committee", expires_hours=24 * 14, risk="high" if item.get("severity") in ("critical", "high") else "medium")
    entry = {"committee_item_id": row["id"], "created_at": row["created_at"], "by": user, "role": role, "title": title,
             "item": {k: item.get(k) for k in ("id", "title", "source", "severity", "entity", "numbers", "trace")},
             "option": opt, "status": "on the agenda"}
    with _LOCK, open(home() / "committee.jsonl", "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return {"committee_item": entry, "approval": row,
            "message": f"Sent to the credit committee: {opt.get('title') or 'decision needed'}. Reference {row['id']}.",
            "open": {"href": "/agent-operations?tab=queue", "label": "Open the committee item"}}


def committee_items(limit: int = 20) -> list[dict[str, Any]]:
    try:
        lines = (home() / "committee.jsonl").read_text().splitlines()
    except OSError:
        return []
    return [json.loads(x) for x in reversed(lines[-limit:]) if x.strip()]
