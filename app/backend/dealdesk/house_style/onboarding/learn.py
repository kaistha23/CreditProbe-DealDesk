"""P6: learn from documents. Read a credit policy (and an optional DoA matrix or risk appetite statement) and the bank's
memos; return every learned item as PROPOSED, never live.

  read_document  -> clauses (number, text, section) and tables (caption, header, rows), whatever the format
  extract        -> threshold and condition items: the metric, the value, the clause and its words, the target rule
                    (Session R's rules.json schema) and/or parameter (risk_appetite / doa / market_bounds / desk),
                    the data fields and whether the bank's data can check it (auto) or a person must (manual)
  conflicts      -> policy clauses weaker than the CBUAE CRM Standards, rules with no data, required memo sections the
                    memos skip
  committee      -> the questions committees raise again and again, from conditions, comments and queries in past memos
  structure      -> the memos' sections per type and the house language through Session P's profile

Deterministic: the same documents give the same items and ids (no model key is needed; none is used).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from typing import Any

from backend.dealdesk.house_style.onboarding import metrics as M

WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "eleven": 11, "twelve": 12}
N = r"(\d+(?:[.,]\d+)*|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
RATING = r"(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC|CC|C)(?![A-Za-z])"
UNITS: dict[str, str] = {
    "money": r"(AED|SAR|USD)\s*" + N + r"\s*(million|m\b|bn|billion)?",
    "pct": N + r"\s*(?:%|per\s?cent)",
    "x": N + r"\s*x\b",
    "times": N + r"\s*times\b",
    "count": N + r"\s+(?:or more\s+)?(?:times|financial years)\b",
    "days": N + r"\s+(?:business\s+)?days\b",
    "months": N + r"\s+months?\b",
    "years": N + r"\s+(?<!financial )years?\b",
    "rating": r"below\s+" + RATING,
}
#: numbers that are references, not thresholds
REF = re.compile(r"\b(Table|clause|Clause|Article|Art\.|Appendix|section|Section)\s+[\dA-Z][\d.]*")
CLAUSE_NO = re.compile(r"^\s*(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s+(.+)$", re.S)
HEADING_NO = re.compile(r"^\s*(\d{1,2})\.\s+([A-Z].{2,80})$")


def num(s: str) -> float:
    s = s.strip().lower()
    return float(WORDNUM[s]) if s in WORDNUM else float(s.replace(",", ""))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ reading

def _docx_blocks(data: bytes) -> list[tuple[str, Any]]:
    """Paragraphs and tables in document order: ("p", text, style) / ("t", rows)."""
    from docx import Document
    d = Document(io.BytesIO(data))
    out: list[tuple[str, Any]] = []
    body = d.element.body
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for el in body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(el, d)
            if p.text.strip():
                out.append(("p", (p.text.strip(), p.style.name if p.style is not None else "")))
        elif tag == "tbl":
            t = Table(el, d)
            out.append(("t", [[c.text.strip() for c in r.cells] for r in t.rows]))
    return out


def _text_blocks(text: str) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    rows: list[list[str]] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                rows.append(cells)
            continue
        if rows:
            out.append(("t", rows))
            rows = []
        if s:
            out.append(("p", (s.lstrip("#").strip(), "Heading 1" if s.startswith("#") else "")))
    if rows:
        out.append(("t", rows))
    return out


def text_of_bytes(name: str, data: bytes) -> str:
    low = name.lower()
    if low.endswith(".pdf"):
        import pypdf  # in the locked requirements (the regulatory extractor uses it too)
        text = "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(data)).pages)
        if not text.strip():
            raise ValueError(f"{name} has no text layer (a scan): it needs OCR before it can be read.")
        return text
    return data.decode("utf-8", errors="replace")


def read_document(name: str, data: bytes) -> dict[str, Any]:
    """Clauses and tables of a policy-like document (.docx, .pdf, .md, .txt)."""
    blocks = _docx_blocks(data) if name.lower().endswith(".docx") else _text_blocks(text_of_bytes(name, data))
    clauses: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    section, title, last_para = "", "", ""
    for kind, x in blocks:
        if kind == "p":
            text, style = x
            m = CLAUSE_NO.match(text)
            h = HEADING_NO.match(text)
            if style.lower().startswith(("heading", "title")) or (h and len(text) < 90 and not m):
                section = h.group(1) if h else section
                title = h.group(2) if h else text
                last_para = text
                continue
            if m:
                clauses.append({"clause": m.group(1), "text": " ".join(m.group(2).split()), "section": section, "section_title": title})
            elif clauses and last_para is clauses[-1].get("_last") and not last_para.rstrip().endswith((".", ":", ";")):
                # a clause wrapped over several lines (PDF and plain text): the line continues it
                clauses[-1]["text"] += " " + " ".join(text.split())
                text = clauses[-1]["text"]
            if clauses and (m or text is clauses[-1]["text"]):
                clauses[-1]["_last"] = text
            last_para = text
        else:
            if len(x) < 2:
                continue
            cap = last_para if (last_para.lower().startswith(("table", "appendix")) or len(last_para) < 120) else title
            ref = re.match(r"(Table\s+[\d.]+|Appendix\s+[A-Z])", cap)
            tables.append({"table": ref.group(1) if ref else (cap[:40] or f"Table {len(tables) + 1}"), "caption": cap, "title": title,
                           "header": x[0], "rows": x[1:], "section": section})
    for c in clauses:
        c.pop("_last", None)
    return {"name": name, "sha256": sha(data), "clauses": clauses, "tables": tables}


# ------------------------------------------------------------------ extraction

def _parts(text: str) -> list[str]:
    return [p for p in re.split(r";\s+|,\s+and\s+(?=at least|no |not )", text) if p.strip()]


def _quantities(part: str, unit: str) -> list[tuple[re.Match[str], float | str]]:
    clean = REF.sub(lambda m: "#" * len(m.group(0)), part)
    out = []
    for m in re.finditer(UNITS[unit], clean, re.I):
        if unit == "rating":
            out.append((m, m.group(1).upper()))
        elif unit == "money":
            v = num(m.group(2))
            if (m.group(3) or "").lower() in ("bn", "billion"):
                v *= 1000
            out.append((m, v))
        else:
            out.append((m, num(m.group(1))))
    return out


def any_quantity(text: str) -> list[tuple[str, str]]:
    """Every quantity in a clause (any unit), for the unmapped-threshold check and the tests."""
    seen: list[tuple[int, int]] = []
    out = []
    for unit in ("money", "pct", "x", "count", "times", "days", "months", "years", "rating"):
        for m, _ in _quantities(text, unit):
            if any(a <= m.start() < b for a, b in seen):
                continue
            seen.append((m.start(), m.end()))
            out.append((unit, m.group(0)))
    return out


def _item_id(doc_sha: str, clause: str, key: str) -> str:
    return "ONB-" + hashlib.sha1(f"{doc_sha[:12]}|{clause}|{key}".encode()).hexdigest()[:8].upper()


def _ccy_value(v: float, unit_text: str, target_ccy: str | None, aed_sar: float) -> tuple[float, str]:
    src = unit_text.upper()[:3] if unit_text[:3].upper() in ("AED", "SAR", "USD") else "AED"
    if not target_ccy or src == target_ccy:
        return v, ""
    if src == "AED" and target_ccy == "SAR":
        return round(v * aed_sar, 2), f"AED {v:,.0f}m × {aed_sar} (AED/SAR in the Deal Desk parameters) = SAR {v * aed_sar:,.1f}m"
    return v, f"{src} kept: no rate to {target_ccy}"


def extract(doc: dict[str, Any], kind: str = "policy", aed_sar: float = 1.021, bank: str = "") -> list[dict[str, Any]]:
    """Threshold and condition items of one document, in clause order."""
    items: list[dict[str, Any]] = []
    src = {"document": doc["name"], "sha256": doc["sha256"], "kind": kind}
    for c in doc["clauses"]:
        claimed: list[tuple[int, int, int]] = []  # (part index, start, end)
        parts = _parts(c["text"])
        for met in M.METRICS:
            if met["unit"].startswith("table_") or not re.search(met["kw"], c["text"], re.I):
                continue
            for pi, part in enumerate(parts):
                q = met.get("qualifier")
                if q and not re.search(q, part, re.I):
                    continue
                if not q and any(m2.get("qualifier") and re.search(m2["qualifier"], part, re.I)
                                 and re.search(m2["kw"], c["text"], re.I) and m2["unit"] == met["unit"]
                                 for m2 in M.METRICS if m2 is not met and m2["key"].startswith(met["key"])):
                    continue  # a qualified variant (Stage 3, "or worse") owns this part
                for m, v in _quantities(part, met["unit"]):
                    if any(pi == p and s <= m.start() < e for p, s, e in claimed):
                        continue
                    claimed.append((pi, m.start(), m.end()))
                    items.append(_threshold_item(met, c, part, m.group(0), v, src, aed_sar, bank))
                    break
                else:
                    continue
                break
        # quantities no metric claimed: unmapped thresholds (a person configures them)
        for pi, part in enumerate(parts):
            for unit in ("money", "pct", "x", "count", "times", "days", "months", "years"):
                for m, v in _quantities(part, unit):
                    if any(pi == p and (s <= m.start() < e or m.start() <= s < m.end()) for p, s, e in claimed):
                        continue
                    claimed.append((pi, m.start(), m.end()))
                    items.append(_unmapped_item(c, part, m.group(0), v, unit, src))
        for cond in M.CONDITIONS:
            if re.search(cond["kw"], c["text"], re.I):
                items.append(_condition_item(cond, c, src, bank))
    for t in doc["tables"]:
        items.extend(_table_items(t, src, aed_sar, bank))
    return items


def _base(key: str, label: str, c: dict[str, Any], quote: str, src: dict[str, Any], kind: str) -> dict[str, Any]:
    return {"id": _item_id(src["sha256"], c.get("clause") or c.get("table", ""), key), "type": kind, "metric": key, "label": label,
            "clause": c.get("clause") or c.get("table"), "section": c.get("section_title") or c.get("title", ""),
            "quote": quote, "clause_text": c.get("text") or c.get("caption", ""), "status": "proposed",
            "learned_from": {**src, "clause": c.get("clause") or c.get("table"), "quote": quote}}


def _check(met: dict[str, Any]) -> dict[str, Any]:
    if met.get("manual"):
        return {"checkability": "manual", "data_fields": met.get("data", []), "why": met["manual"]}
    if not met.get("data"):
        return {"checkability": "manual", "data_fields": [], "why": "no data field holds it"}
    return {"checkability": "auto", "data_fields": met["data"], "why": met.get("auto_note") or "the review evidence holds every input"}


def _threshold_item(met: dict[str, Any], c: dict[str, Any], part: str, qtext: str, v: Any, src: dict[str, Any],
                    aed_sar: float, bank: str) -> dict[str, Any]:
    it = _base(met["key"], met["label"], c, part.strip().rstrip(".") + ".", src, "threshold")
    unit = {"pct": "%", "x": "x", "times": "x", "count": "times", "days": "days", "months": "months", "years": "years",
            "rating": "rating", "money": qtext.split()[0].upper() + " m"}[met["unit"]]
    if met["unit"] == "count" and "year" in qtext.lower():
        unit = "years"
    it.update({"value": v, "unit": unit, "value_text": qtext, "stricter": met["stricter"], **_check(met)})
    if met.get("param"):
        it["param"] = _param_change(met["param"], v, qtext, aed_sar)
    if met.get("rule"):
        it["rule"] = _rule(met, met["rule"], c, v, it, bank)
    if met.get("same_as"):
        it["same_as"] = met["same_as"]
    return it


def _unmapped_item(c: dict[str, Any], part: str, qtext: str, v: float, unit: str, src: dict[str, Any]) -> dict[str, Any]:
    it = _base(f"unmapped:{unit}:{qtext}", "Threshold with no rule template", c, part.strip().rstrip(".") + ".", src, "threshold")
    it.update({"value": v, "unit": unit, "value_text": qtext, "stricter": "", "checkability": "manual", "data_fields": [],
               "why": "no rule template matches this clause: a person decides how to check it", "unmapped": True})
    return it


def _condition_item(cond: dict[str, Any], c: dict[str, Any], src: dict[str, Any], bank: str) -> dict[str, Any]:
    it = _base(cond["key"], cond["label"], c, c["text"], src, "condition")
    met = {"data": cond.get("data", []), "manual": cond.get("manual")}
    it.update(_check(met))
    if cond.get("rule"):
        it["rule"] = _rule({"key": cond["key"], "label": cond["label"]}, cond["rule"], c, None, it, bank)
    if cond.get("same_as"):
        it["same_as"] = cond["same_as"]
    return it


def _table_items(t: dict[str, Any], src: dict[str, Any], aed_sar: float, bank: str) -> list[dict[str, Any]]:
    hay = " ".join([t["caption"], t["title"], *t["header"]])
    head = [h.lower() for h in t["header"]]
    rows = [r for r in t["rows"] if r and r[0]]
    quote = f"{t['caption']}: " + "; ".join(" ".join(x for x in r if x) for r in rows)
    c = {"table": t["table"], "caption": t["caption"], "title": t["title"]}
    out = []
    for met in M.METRICS:
        if not met["unit"].startswith("table_") or not re.search(met["kw"], hay, re.I):
            continue
        it = _base(met["key"], met["label"], c, quote, src, "threshold")
        it.update({"stricter": met["stricter"], **_check(met)})
        if met["unit"] == "table_years":
            vals = {r[0].strip(): num(re.findall(r"[\d.]+", r[1])[0]) for r in rows if re.findall(r"[\d.]+", r[1])}
            it.update({"value": vals, "unit": "years"})
            it["param"] = _param_change(met["param"], vals, "", aed_sar)
            rule = dict(met["rule"])
            rule["derive"] = {"cap": M._bucket_expr(vals)}
            it["rule"] = _rule(met, {**rule, "expr": "tenor", "op": "<=", "threshold_input": "cap", "when": f"rating in {_rated(vals)!r}"},
                               c, vals, it, bank)
        elif met["unit"] == "table_bps":
            lo_i = next(i for i, h in enumerate(head) if "min" in h)
            hi_i = next(i for i, h in enumerate(head) if "max" in h)
            vals = {r[0].strip(): [num(r[lo_i]), num(r[hi_i])] for r in rows}
            it.update({"value": vals, "unit": "bps"})
            it["param"] = _param_change(met["param"], vals, "", aed_sar)
            rule = dict(met["rule"])
            rule["derive"] = {"lo": M._bucket_expr({k: v[0] for k, v in vals.items()}),
                              "hi": M._bucket_expr({k: v[1] for k, v in vals.items()})}
            it["rule"] = _rule(met, {**rule, "assert": "m >= lo and m <= hi", "when": f"rating in {_rated(vals)!r}"}, c, vals, it, bank)
        elif met["unit"] == "table_doa":
            exp_i = next(i for i, h in enumerate(head) if "exposure" in h)
            rat_i = next((i for i, h in enumerate(head) if "rating" in h), None)
            ccy = "AED" if "aed" in head[exp_i] else ("SAR" if "sar" in head[exp_i] else "AED")
            levels = []
            for r in rows:
                nums = re.findall(r"[\d,.]+", r[exp_i])
                above = "above" in r[exp_i].lower()
                v = None if (above or not nums) else num(nums[0])
                conv = round(v * aed_sar, 2) if (v is not None and ccy == "AED") else v
                levels.append({"level": r[0].strip(), "max_exposure_policy": v, "max_exposure": conv,
                               "min_rating": r[rat_i].strip() if rat_i is not None else None})
            it.update({"value": levels, "unit": f"{ccy} m", "conversion": f"AED × {aed_sar} (AED/SAR in the Deal Desk parameters)" if ccy == "AED" else ""})
            it["param"] = {"table": "doa", "row": "rows", "field": "levels", "proposed": levels}
        out.append(it)
    return out


def _rated(vals: dict[str, Any]) -> list[str]:
    return [r for b in vals for r in M.BUCKETS.get(b, [])]


def _param_change(p: dict[str, Any], v: Any, qtext: str, aed_sar: float) -> dict[str, Any]:
    out = {"table": p["table"], "row": p["row"], "field": p["field"]}
    if isinstance(v, (int, float)):
        val, note = _ccy_value(float(v), qtext, p.get("ccy"), aed_sar) if p.get("ccy") else (float(v), "")
        factor = (val / float(v)) if float(v) else 1.0
        if p.get("scale"):
            val = round(val * p["scale"], 6)
            factor *= p["scale"]
        out.update({"proposed": val, "conversion": note, "factor": round(factor, 8)})
    else:
        out["proposed"] = v
    return out


def _rule(met: dict[str, Any], tpl: dict[str, Any], c: dict[str, Any], v: Any, it: dict[str, Any], bank: str) -> dict[str, Any]:
    """A rule in Session R's rules.json schema (data/dealdesk/review/README.md), proposed: enabled false."""
    clause = c.get("clause") or c.get("table")
    rule: dict[str, Any] = {
        "id": f"POL-{met['key'].upper().replace('_', '-')[:18]}-{str(clause).replace('.', '-').replace(' ', '')}",
        "category": "policy", "title": met["label"],
        "tests": f"{bank or 'Bank'} Credit Policy {clause}: {it['quote']}",
        "scope": tpl.get("scope", ["case", "dd"]), "inputs": tpl["inputs"], "severity": "major", "on_fail": "exception",
        "policy_ref": f"{bank or 'Bank'} Credit Policy {clause}", "crm_article": "", "doa_rank": 4,
        "finding": tpl["finding"], "evidence": tpl["finding"], "pass_text": tpl["pass_text"],
        "sources": ["Learned from the bank's credit policy"], "enabled": False, "status": "proposed"}
    for k in ("optional", "derive", "when", "threshold_input"):
        if tpl.get(k):
            rule[k] = tpl[k]
    if tpl.get("unit"):
        rule["unit"] = tpl["unit"]
    if tpl.get("assert_fn") == "rating_floor":
        rule["assert"] = f"rating in {M.ratings_at_or_above(str(v))!r}"
        rule["threshold"] = v
    elif tpl.get("assert"):
        rule["assert"] = tpl["assert"]
    elif tpl.get("threshold_input"):
        rule["expr"], rule["op"] = tpl["expr"], tpl["op"]
    else:
        thr = float(v)
        if tpl.get("ccy") == "SAR" and it.get("param", {}).get("proposed") is not None and str(it.get("unit", "")).startswith("AED"):
            thr = it["param"]["proposed"]  # converted to SAR at the desk rate
        rule["expr"], rule["op"], rule["threshold"] = tpl["expr"], tpl["op"], thr
    reg = M.REG.get(met["key"])
    if reg:
        rule["crm_article"] = reg[0]
    rule["learned_from"] = it["learned_from"]
    return rule


# ------------------------------------------------------------------ conflicts and gaps

def _crm_text() -> dict[str, str]:
    from backend.dealdesk import paths
    f = paths.V5 / "backend" / "playbook_v5" / "data" / "cbuae_crm.json"
    return {c["clause"]: c["rule"] for c in json.loads(f.read_text())["clauses"]}


def regulatory(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Each policy number the CBUAE CRM Standards also state: weaker (a conflict) or consistent."""
    crm = _crm_text()
    weaker, consistent = [], []
    for it in items:
        reg = M.REG.get(it["metric"])
        if not reg or not isinstance(it.get("value"), (int, float)):
            continue
        art, rv, unit, says = reg
        pv = float(it["value"])
        weak = pv > rv if it["stricter"] == "lower" else pv < rv
        quote = M.REG_QUOTE[it["metric"]]
        found = quote in crm.get(art, "")
        row = {"id": f"REG-{it['id']}", "item_id": it["id"], "metric": it["metric"], "label": it["label"], "clause": it["clause"],
               "quote": it["quote"], "policy_value": pv, "unit": it["unit"], "regulation": art, "regulation_value": rv,
               "regulation_quote": quote, "quote_verified": found, "says": says, "href": "/policy-docs?doc=pd_cbuae_crm"}
        if weak:
            row.update({"kind": "weaker_than_regulation", "severity": "critical",
                        "message": f"Policy {it['clause']} allows {pv:g} {it['unit']}; {art} requires {rv:g} {unit}: "
                                   f"the stricter (the regulation) applies and the policy should be amended."})
            weaker.append(row)
        else:
            row.update({"kind": "consistent", "message": f"Policy {it['clause']} ({pv:g} {it['unit']}) is at least as strict as {art} ({rv:g} {unit})."})
            consistent.append(row)
    return {"weaker": weaker, "consistent": consistent}


def in_force(items: list[dict[str, Any]]) -> None:
    """Compare each parameter proposal with the value in force (in place): same, tighter or looser."""
    from backend.dealdesk import desk_params, params
    for it in items:
        p = it.get("param")
        if not p:
            continue
        try:
            if p["table"] == "desk":
                cur = desk_params.rows().get(p["row"])
                cur = cur.get(p["field"]) if isinstance(cur, dict) else cur
            elif p["table"] == "doa":
                cur = [{"level": r["level"], "max_exposure": r["max_exposure"], "min_rating": r["min_rating"]} for r in params.rows("doa")]
            elif p["table"] == "market_bounds":
                cur = {b: v["margin_bps"] for b, v in params.rows("market_bounds")["by_bucket"].items()}
            else:
                row = next(r for r in params.rows(p["table"]) if r["name"] == p["row"])
                cur = row.get(p["field"])
                p["unit_in_force"] = row.get("unit")
        except Exception:  # noqa: BLE001 - a table not in this deployment: the proposal stands alone
            cur = None
        p["in_force"] = cur
        p["version_in_force"] = _version(p["table"])
        p["change"] = _change(cur, p.get("proposed"), it.get("stricter", ""))


def _version(table: str) -> str:
    from backend.dealdesk import desk_params, params
    try:
        return str(desk_params.table().get("version")) if table == "desk" else str(params.table(table)["version"])
    except Exception:  # noqa: BLE001
        return ""


def _change(cur: Any, new: Any, stricter: str) -> str:
    if cur is None:
        return "new"
    if isinstance(cur, (int, float)) and isinstance(new, (int, float)):
        if abs(float(cur) - float(new)) < 1e-9:
            return "same"
        tighter = new < cur if stricter == "lower" else new > cur
        return "tighter" if tighter else "looser"
    if isinstance(cur, str) and isinstance(new, str):
        if cur == new:
            return "same"
        from backend.v5common.ratings import RATING_ORDER as R
        if cur in R and new in R:
            return "tighter" if R.index(new) < R.index(cur) else "looser"
        return "changed"
    return "same" if json.dumps(cur, sort_keys=True) == json.dumps(new, sort_keys=True) else "changed"


def required_sections(doc: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    for c in doc["clauses"]:
        m = re.search(r"(?:shall|must) contain the following sections:\s*(.+)$", c["text"], re.I)
        if m:
            return c, [s.strip().rstrip(".") for s in re.split(r";", m.group(1)) if s.strip()]
    return None, []


STOP = {"and", "the", "of", "to", "a", "in", "for", "on", "or", "with", "analysis", "summary"}


def _tokens(s: str) -> set[str]:
    return {re.sub(r"s$", "", w) for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP and len(w) > 2}


def section_gaps(policy_doc: dict[str, Any], memos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sections the policy requires that the memos skip (n of N memos without it)."""
    from backend.dealdesk.house_style import corpus
    c, req = required_sections(policy_doc)
    if not c or not memos:
        return []
    keys = [corpus.section_key(r) for r in req]
    out = []
    for r, k in zip(req, keys):
        ambiguous = keys.count(k) > 1
        rt = _tokens(r)
        others = set().union(*[_tokens(r2) for r2, k2 in zip(req, keys) if k2 == k and r2 != r]) if ambiguous else set()
        dist = (rt - others) or rt
        missing, in_text = [], 0
        for d in memos:
            heads = [s for s in d["sections"] if s.get("key") == k and (not ambiguous or _tokens(s.get("heading", "")) & dist)]
            if not heads:
                missing.append(d["doc_id"])
                body = corpus.text_of(d).lower()
                if any(t in body for t in dist):
                    in_text += 1
        if missing:
            out.append({"id": f"SEC-{k}-{hashlib.sha1(r.encode()).hexdigest()[:6]}", "kind": "section_skipped", "section": r, "key": k,
                        "clause": c["clause"], "quote": c["text"], "missing": len(missing), "of": len(memos),
                        "memos": missing, "mentioned_in_text": in_text, "severity": "major" if len(missing) * 2 >= len(memos) else "minor",
                        "message": f"Policy {c['clause']} requires \"{r}\"; {len(missing)} of {len(memos)} memos have no such section"
                                   + (f" ({in_text} mention it in the text)" if in_text else "") + "."})
    return out


def data_gaps(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": f"DATA-{it['id']}", "kind": "rule_without_data", "item_id": it["id"], "label": it["label"], "clause": it["clause"],
             "quote": it["quote"], "why": it["why"], "severity": "minor",
             "message": f"Policy {it['clause']} ({it['label'].lower()}) cannot be checked from the data: {it['why']}. A person checks it."}
            for it in items if it.get("checkability") == "manual" and it["type"] in ("threshold", "condition")]


# ------------------------------------------------------------------ committee questions

#: (key, the question, regex over committee comments/conditions/queries, where a draft answers it)
TOPICS: list[tuple[str, str, str, str]] = [
    ("other_banks", "Are the facilities at other banks confirmed by facility letters and the bureau?",
     r"other banks?|facility letters|bureau|AECB|CBRBR|SIMAH", r"other banks?|bureau|AECB|SIMAH|CBRBR"),
    ("related_party", "How much is due from related parties, and is it subordinated or settled?",
     r"related[- ]part|group compan|shareholder (?:loan|withdraw)|due from", r"related[- ]part|due from|group compan"),
    ("backlog", "Is the backlog verified, and how concentrated is it by employer?", r"backlog|order book|employer",
     r"backlog|order book"),
    ("cash_margin", "What cash margin is held on the guarantees?", r"cash margin|margin on (?:the )?guarantee", r"cash margin"),
    ("perfection", "Is the security perfected before drawdown, and is the legal opinion current?",
     r"perfect|legal opinion|mortgage|pledge|assignment", r"perfect|legal opinion|mortgage|pledge|assign"),
    ("valuation", "Is the collateral valuation current and by an approved valuer?", r"valuation|valuer|revalu",
     r"valuation|valuer|valued"),
    ("audited", "Are audited standalone financials available, and is the opinion unqualified?",
     r"audited|qualif|standalone|auditor", r"audited|auditor|qualif"),
    ("routing", "Is the turnover routing undertaking met?", r"routing|turnover|undertaking", r"routing|turnover"),
    ("projects", "Are project delays and extensions of time formalised, and are certified payments collected?",
     r"extension of time|\bEOT\b|delay|certified payment", r"extension|delay|certified"),
    ("stress", "Does repayment survive the stress case?", r"stress|deficit|sensitivit", r"stress|sensitivit|deficit"),
    ("pricing", "Does the pricing clear the hurdle?", r"RAROC|hurdle|pric", r"RAROC|hurdle"),
    ("cro", "Has the CRO reviewed the proposal?", r"CRO (?:box|review)|sign-?off", r"\bCRO\b"),
    ("ownership", "Has the change of ownership been re-assessed (KYC)?", r"ownership|KYC|change of control", r"ownership|KYC"),
    ("dscr", "What is the debt service cover after the deal?", r"DSCR|debt service cover", r"DSCR|debt service"),
]
COMMITTEE_KEYS = {"conditions", "opinion", "gaps", "watch", "checks"}
COMMITTEE_HEAD = re.compile(r"committee|condition|comment|decision|queries|query|subject to", re.I)


def committee_sentences(doc: dict[str, Any]) -> list[str]:
    out = []
    for s in doc["sections"]:
        if s.get("key") in COMMITTEE_KEYS or COMMITTEE_HEAD.search(s.get("heading", "")):
            for x in [*s.get("paragraphs", []), *s.get("bullets", [])]:
                out.extend(p.strip() for p in re.split(r"(?<=[.?;])\s+", x) if len(p.strip()) > 12)
    return out


def committee(memos: list[dict[str, Any]], min_memos: int = 2) -> list[dict[str, Any]]:
    """The questions committees raise again and again: a topic raised in at least `min_memos` memos."""
    by: dict[str, dict[str, Any]] = {}
    with_comments = 0
    for d in memos:
        sents = committee_sentences(d)
        if sents:
            with_comments += 1
        for key, q, rx, _ in TOPICS:
            hit = next((s for s in sents if re.search(rx, s, re.I)), None)
            if hit:
                b = by.setdefault(key, {"memos": [], "quotes": []})
                b["memos"].append(d["doc_id"])
                b["quotes"].append({"doc_id": d["doc_id"], "quote": hit[:300]})
    out = []
    for key, q, rx, ans in TOPICS:
        b = by.get(key)
        if not b or len(b["memos"]) < min_memos:
            continue
        out.append({"id": f"CQ-{key}", "type": "committee_question", "metric": key, "label": q, "question": q,
                    "raised_in": len(b["memos"]), "of": with_comments, "memos": b["memos"], "quote": b["quotes"][0]["quote"],
                    "quotes": b["quotes"][:4], "answer_pattern": ans, "status": "proposed", "checkability": "auto",
                    "why": "the drafter answers it; the review flags a draft that leaves it open",
                    "learned_from": {"documents": b["memos"], "quote": b["quotes"][0]["quote"], "kind": "memo"}})
    out.sort(key=lambda x: (-x["raised_in"], x["id"]))
    return out


# ------------------------------------------------------------------ memos: structure and language

def read_memo(name: str, data: bytes, doc_id: str | None = None) -> dict[str, Any]:
    from backend.dealdesk.house_style import corpus
    parsed = corpus.read_docx(data) if name.lower().endswith(".docx") else corpus.read_text(text_of_bytes(name, data))
    stem = re.sub(r"[^A-Za-z0-9-]+", "-", name.rsplit(".", 1)[0])[:40].strip("-")
    return corpus.make_doc(doc_id or f"ONB-{stem}-{sha(data)[:6]}", parsed, "onboarding", "house-uae")


def structure(memos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sections per memo type (kind × segment): share of memos with each section, in the usual order."""
    from backend.dealdesk.house_style import corpus
    groups: dict[str, list[dict[str, Any]]] = {}
    for d in memos:
        groups.setdefault(f"{d['kind']}|{d['segment']}", []).append(d)
    out = []
    for g, docs in sorted(groups.items()):
        pos: dict[str, list[float]] = {}
        heads: dict[str, dict[str, int]] = {}
        for d in docs:
            secs = [s for s in d["sections"] if s.get("key") and s["key"] != "preamble"]
            seen = set()
            for i, s in enumerate(secs):
                if s["key"] in seen:
                    continue
                seen.add(s["key"])
                pos.setdefault(s["key"], []).append(i / max(1, len(secs) - 1))
                h = s.get("heading") or corpus.LABEL.get(s["key"], s["key"])
                heads.setdefault(s["key"], {}).setdefault(h, 0)
                heads[s["key"]][h] += 1
        secs = sorted(pos, key=lambda k: sum(pos[k]) / len(pos[k]))
        kind, seg = g.split("|")
        out.append({"id": f"STR-{kind}-{seg}", "type": "structure", "metric": g, "label": f"Memo structure: {kind}, {seg}",
                    "kind": kind, "segment": seg, "memos": len(docs),
                    "sections": [{"key": k, "label": corpus.LABEL.get(k, k), "heading": max(heads[k], key=heads[k].get),
                                  "share": round(len(pos[k]) / len(docs), 2), "required": len(pos[k]) * 2 > len(docs)} for k in secs],
                    "quote": "; ".join(max(heads[k], key=heads[k].get) for k in secs),
                    "status": "proposed", "checkability": "auto", "why": "the drafter follows it and the fidelity score checks it",
                    "learned_from": {"documents": [d["doc_id"] for d in docs], "kind": "memo"}})
    return out


def language(memos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The house language of the uploaded memos through Session P's profile (business unit and credit division apart)."""
    from backend.dealdesk.house_style import profile as prof
    if not memos:
        return []
    st = prof.build(memos)
    out = []
    for d0 in memos[:1]:
        v = prof.view(st, d0["bank"], d0["kind"], d0["segment"])
        bu = v.get("business") or {}
        phrases = [p.get("phrase") or p.get("text") or "" for p in (v.get("phrases") or bu.get("phrases") or [])][:8]
        openers = [p.get("opener") or p.get("text") or "" for p in (v.get("openers") or bu.get("openers") or [])][:6]
        out.append({"id": "LANG-house", "type": "language", "metric": "house_language", "label": "House language (Session P profile)",
                    "group": v.get("group"), "documents": v.get("documents"), "phrases": [p for p in phrases if p],
                    "openers": [o for o in openers if o], "guide": prof.guide(v)[:4000],
                    "quote": "; ".join([p for p in phrases if p][:4]), "status": "proposed", "checkability": "auto",
                    "why": "accepted, the memos join the house-style corpus and the drafter writes in this language",
                    "learned_from": {"documents": [d["doc_id"] for d in memos], "kind": "memo"}})
    return out
