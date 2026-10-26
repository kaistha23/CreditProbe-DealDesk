"""R11 R2: the configurable review rules (data/dealdesk/review/rules.json) and their evaluation.

Every check is a rule: id, category (data, consistency, policy, connected), what it tests, its inputs (dotted
paths into review_facts.facts), the test (an expression compared with a threshold, or a boolean assertion),
the policy clause and CBUAE CRM article, the Delegation of Authority rank it needs when it fails, its
severity, the finding and evidence wording, and the condition or lever it implies. The bank adds a rule by
adding a row; no code changes.

Verdicts per check:
  supported      the claim is backed by the data, or the test passes
  contradicted   the data contradicts what the memo states or relies on
  exception      a departure from policy that needs approval at the DoA level shown
  unverifiable   an input the test needs is not available

Expressions are evaluated by a small safe evaluator (arithmetic, comparisons, boolean logic, list
comprehensions and a whitelist of functions over the rule's named inputs); nothing else is reachable.
"""
from __future__ import annotations

import ast
import datetime as dt
import functools
import json
import math
import re
from typing import Any

from backend.dealdesk import desk_params, params
from backend.dealdesk.review_facts import resolve
from backend.dealdesk.review_ledger import REVIEW_DIR

VERDICTS = ("supported", "contradicted", "exception", "unverifiable")
SEVERITIES = ("critical", "major", "minor")
CATEGORIES = ("data", "consistency", "policy", "connected")


@functools.lru_cache(maxsize=1)
def rulebook() -> dict[str, Any]:
    return json.loads((REVIEW_DIR / "rules.json").read_text())


def reload() -> None:
    rulebook.cache_clear()


def rules() -> list[dict[str, Any]]:
    return [r for r in rulebook()["rules"] if r.get("enabled", True)]


# ------------------------------------------------------------------ safe expressions

def _d(x: Any) -> dt.date:
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x)[:10])


def _days(a: Any, b: Any) -> float:
    return float((_d(b) - _d(a)).days)


def _months(a: Any, b: Any) -> float:
    return round(_days(a, b) / 30.4375, 1)


FUNCS = {"days": _days, "months": _months, "min": min, "max": max, "abs": abs, "sum": sum, "len": len, "any": any, "all": all,
         "round": round, "lower": lambda s: str(s or "").lower(), "contains": lambda s, sub: str(sub).lower() in str(s or "").lower(),
         "year": lambda d: _d(d).year, "float": float, "bool": bool, "isnull": lambda x: x is None or x == "" or x == [],
         "sqrt": math.sqrt, "str": str, "sorted": sorted, "join": lambda sep, xs: str(sep).join(str(x) for x in xs)}

_ALLOWED = (ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call, ast.Name, ast.Load, ast.Constant,
            ast.And, ast.Or, ast.Not, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.FloorDiv,
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
            ast.List, ast.Tuple, ast.Subscript, ast.Attribute, ast.ListComp, ast.GeneratorExp, ast.comprehension, ast.Store,
            ast.Dict, ast.Slice)


class ExprError(ValueError):
    pass


@functools.lru_cache(maxsize=512)
def _compile(expr: str):
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExprError(f"Not allowed in a rule expression: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr not in ("get", "values", "keys", "items", "strip")):
            raise ExprError(f"Attribute not allowed: {node.attr}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in FUNCS
                                               or isinstance(node.func, ast.Attribute)):
            raise ExprError("Only whitelisted functions may be called")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ExprError("Private names are not allowed")
    return compile(tree, "<rule>", "eval")


def evaluate(expr: str, names: dict[str, Any]) -> Any:
    return eval(_compile(expr), {"__builtins__": {}}, {**FUNCS, **names})  # noqa: S307 - AST-whitelisted above


# ------------------------------------------------------------------ thresholds and templates

def threshold_value(t: Any) -> Any:
    """A number, or 'param:<table>.<key>' read from the Deal Desk parameters in force ('param:desk.<key>' = Admin desk params)."""
    if isinstance(t, str) and t.startswith("param:"):
        table, key = t[6:].split(".", 1)
        rows = desk_params.rows() if table == "desk" else params.rows(table)
        cur: Any = rows
        for k in key.split("."):
            cur = cur[k]
        return cur
    return t


class _Fmt(dict):
    def __missing__(self, key: str) -> str:
        return "n/a"


def _fmt_val(v: Any) -> Any:
    return v


def render(template: str | None, names: dict[str, Any]) -> str:
    if not template:
        return ""
    try:
        return template.format_map(_Fmt({k: _fmt_val(v) for k, v in names.items()}))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return re.sub(r"\{[^}]*\}", "n/a", template)


OPS = {"<=": lambda a, b: a <= b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b, ">": lambda a, b: a > b,
       "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


def doa_level(rank: int | None) -> dict[str, Any] | None:
    if not rank:
        return None
    rows = params.rows("doa")
    row = next((r for r in rows if int(r["rank"]) == int(rank)), rows[-1])
    return {"rank": int(row["rank"]), "level": row["level"]}


# ------------------------------------------------------------------ evaluation

def _scope_ok(rule: dict[str, Any], f: dict[str, Any]) -> bool:
    sc = rule.get("scope") or ["case", "dd"]
    return f["subject"]["kind"] in sc


def _lines_for(rule: dict[str, Any], f: dict[str, Any], names: dict[str, Any]) -> tuple[list[str], list[str]]:
    led = f["ledger"]
    claim_ids, line_ids = [], []
    keys = set(rule.get("claims") or [])
    pat = rule.get("line_match")
    for c in led["claims"]:
        if c["key"] in keys:
            claim_ids.append(c["claim_id"])
            line_ids.append(c["line_id"])
    if pat:
        p = render(pat, names) if "{" in pat else pat
        for ln in led["lines"]:
            if re.search(p, ln["text"], re.I):
                line_ids.append(ln["line_id"])
    return list(dict.fromkeys(claim_ids)), list(dict.fromkeys(line_ids))


def _check(rule: dict[str, Any], f: dict[str, Any], names: dict[str, Any], verdict: str, value: Any, thr: Any,
           extra: dict[str, Any] | None = None) -> dict[str, Any]:
    names = {**names, "value": value, "threshold": thr}
    claim_ids, line_ids = _lines_for(rule, f, names)
    failed = verdict in ("contradicted", "exception")
    srcs = rule.get("sources") or []
    src_names = f.get("ev", {}).get("sources", {}) if isinstance(f.get("ev"), dict) else {}
    out = {"rule_id": rule["id"], "category": rule["category"], "title": rule["title"], "tests": rule.get("tests", ""),
           "verdict": verdict, "severity": rule.get("severity", "minor") if failed else None,
           "value": value, "threshold": thr, "op": rule.get("op"), "unit": rule.get("unit", ""),
           "finding": render(rule.get("finding"), names) if failed else render(rule.get("pass_text") or rule.get("title"), names),
           "evidence": [{"source": src_names.get(s, s), "text": render(rule.get("evidence"), names)} for s in srcs] or
                       ([{"source": "Memo", "text": render(rule.get("evidence"), names)}] if rule.get("evidence") else []),
           "policy_ref": rule.get("policy_ref", ""), "crm_article": rule.get("crm_article", ""),
           "doa": doa_level(rule.get("doa_rank")) if failed else None,
           "claim_ids": claim_ids, "line_ids": line_ids,
           "condition": ({**rule["condition"], "what": render(rule["condition"].get("what"), names)} if failed and rule.get("condition") else None),
           "lever": rule.get("lever") if failed else None,
           "issue": rule.get("issue")}
    if extra:
        out.update(extra)
    return out


def _names(rule: dict[str, Any], f: dict[str, Any]) -> dict[str, Any]:
    names = {"as_of": f.get("as_of"), "subject": f["subject"]}
    opt = set(rule.get("optional") or [])
    for k, path in (rule.get("inputs") or {}).items():
        try:
            names[k] = resolve(f, path)
        except KeyError:
            if k not in opt:
                raise
            names[k] = None
    return names


def run_rule(rule: dict[str, Any], f: dict[str, Any]) -> list[dict[str, Any]]:
    if not _scope_ok(rule, f):
        return []
    if rule.get("type") == "ledger":
        return _run_ledger(rule, f)
    try:
        names = _names(rule, f)
    except KeyError as e:
        if rule.get("when"):
            return []  # the precondition's data is absent: the rule does not apply
        return [_check(rule, f, {}, "unverifiable", None, None, {"finding": f"Not verifiable: {e.args[0]} is not available."})]
    if any(v is None for k, v in names.items() if k in (rule.get("inputs") or {}) and k not in (rule.get("optional") or [])):
        if rule.get("when"):
            return []
        missing = [k for k, v in names.items() if v is None and k in (rule.get("inputs") or {})]
        return [_check(rule, f, names, "unverifiable", None, None, {"finding": f"Not verifiable: no data for {', '.join(missing)}."})]
    try:
        if rule.get("when") and not evaluate(rule["when"], names):
            return []
        for k, e in (rule.get("derive") or {}).items():
            names[k] = evaluate(e, names)
        thr = names[rule["threshold_input"]] if rule.get("threshold_input") else threshold_value(rule.get("threshold"))
        if rule.get("expr"):
            value = evaluate(rule["expr"], names)
            names["value"] = value
            ok = OPS[rule["op"]](value, thr)
        else:
            value = None
            ok = bool(evaluate(rule["assert"], names))
    except (ZeroDivisionError, TypeError, ValueError, KeyError, IndexError) as e:
        return [_check(rule, f, names, "unverifiable", None, None, {"finding": f"Not verifiable: {type(e).__name__}."})]
    verdict = "supported" if ok else rule.get("on_fail", "contradicted")
    out = _check(rule, f, names, verdict, value, thr)
    if not ok:
        for sw in rule.get("severity_when") or []:  # graduated severity: the first condition that holds sets it
            try:
                if evaluate(sw["if"], {**names, "value": value, "threshold": thr}):
                    out["severity"] = sw["severity"]
                    break
            except (ZeroDivisionError, TypeError, ValueError, KeyError, IndexError):
                continue
    return [out]


def _run_ledger(rule: dict[str, Any], f: dict[str, Any]) -> list[dict[str, Any]]:
    """Each memo figure that maps to a record: supported when within tolerance, contradicted when not."""
    out = []
    tol = float(rule.get("tolerance", 0.005))
    for c in f["ledger"]["claims"]:
        if c["kind"] != "figure":
            continue
        for mp in rule["map"]:
            m = re.match(mp["claim"], c["key"])
            if not m:
                continue
            path = mp["fact"].format(*m.groups())
            try:
                rec = resolve(f, path)
            except KeyError:
                continue
            if rec is None:
                continue
            memo_v = c["value"]
            if isinstance(rec, (int, float)) and isinstance(memo_v, (int, float)):
                scale = float(mp.get("scale", 1.0))
                rec_v = float(rec) * scale
                ok = abs(memo_v - rec_v) <= max(tol * abs(rec_v), float(mp.get("abs_tol", 0.006)))
            else:
                rec_v = rec
                ok = str(memo_v).strip().lower() == str(rec).strip().lower()
            names = {"label": c["label"] + (f" ({c['column']})" if c["column"] else ""), "memo": memo_v, "record": rec_v,
                     "source": mp.get("source", "")}
            chk = _check(rule, f, names, "supported" if ok else rule.get("on_fail", "contradicted"), memo_v, rec_v,
                         {"claim_ids": [c["claim_id"]], "line_ids": [c["line_id"]],
                          "evidence": [{"source": mp.get("source", "Record"), "text": render(rule.get("evidence"), names)}],
                          "rule_id": rule["id"], "check_id": f"{rule['id']}:{c['claim_id']}"})
            out.append(chk)
            break
    return out


def run(f: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in rules():
        for chk in run_rule(r, f):
            chk.setdefault("check_id", r["id"])
            out.append(chk)
    return out


def required_doa(f: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    """R14 E: the approval level from the one approval-authority engine (backend.dealdesk.approval.core). A Deal Desk
    deal is analysed on its ask with these checks (so the Review, the tiles and the papers agree); a prepared case uses
    the DoA core on its group exposure, rating and failed rules."""
    from backend.dealdesk.approval import core as AC  # R14 E
    if f["subject"]["kind"] == "dd":
        from backend.dealdesk import engine
        p = f["dd"]
        tok = AC._GUARD.set(True)
        try:
            a = engine.analyse(p, None, validate=False)
        finally:
            AC._GUARD.reset(tok)
        d = AC.for_proposal(p, a, checks=checks)
    else:
        sar = float(f["subject"]["amount_sar"])
        g = (f["case"].get("group_cap") or {}).get("group_exposure_after")
        sar = max(sar, float(g) * float(desk_params.rows()["aed_sar"])) if g else sar
        exc = [{"code": c["rule_id"], "label": f"{c['rule_id']} {c['title']}", "rank": (c.get("doa") or {}).get("rank")}
               for c in checks if c["verdict"] == "exception" or (c.get("doa") and c["verdict"] == "contradicted")]
        d = AC.decide(sar, f["subject"]["rating"], exceptions=exc, exposure_detail=f"Group exposure after the deal SAR {sar:,.1f}m")
    reasons = [{"basis": r["basis"], "rank": r["rank"], "level": r["level"], "detail": r["detail"]} for r in d["reasons"]]
    top = {"basis": d["binding"]["basis"], "rank": d["binding"]["rank"], "level": d["binding"]["level"], "detail": d["binding"]["detail"]}
    return {"rank": d["rank"], "level": d["level"], "exposure_sar_mn": d["exposure_after_sar_mn"], "binding": top, "reasons": reasons,
            "rule": d["rule"], "exceptions": d["exceptions"], "hard_breaches": d["hard_breaches"],
            "basis": "Delegation of Authority (data/dealdesk/params/v1/doa.json) through the one approval-authority engine "
                     "(backend.dealdesk.approval): the highest level any of exposure after the deal, rating, the number of "
                     "exceptions, a policy exception, a hard limit or SIMAH needs."}
