"""An analyst's instruction (or a typed rule) -> a rule: kind, parameters, the rule's wording.

Kinds the deterministic path applies by itself (apply.py), each testable:
    wording          say A, not B                          {"use": A, "instead_of": B}
    avoid            never write B                         {"phrase": B}
    units            money in "mn" / "m" / "million"; per cent as "%" or "per cent"   {"money_suffix": .., "percent": ..}
    include_section  always include a section X            {"heading": X}
    section_order    X before / after Y, or X first / last {"section": X, "before" | "after": Y} or {"section": X, "position": ..}
    heading          call section X "Y"                    {"section": X, "heading": Y}
    table            tabulate risks and mitigants          {"section": X, "header": [..]}
    must_mention     always state X                        {"phrase": X}
    instruction      anything else (tone, emphasis): passed to the model as an instruction; listed, not applied, without it

The model path (one call through backend.convo.provider, purpose `dealdesk_rule_classify`) is accepted only when its kind is
one of the above and every quoted phrase it returns is in the analyst's own words; otherwise the parser's reading stands.
"""
from __future__ import annotations

import json
import re
from typing import Any

KINDS = ("wording", "avoid", "units", "include_section", "section_order", "heading", "table", "must_mention", "instruction")
KIND_LABEL = {"wording": "Wording", "avoid": "Avoid a word", "units": "Units", "include_section": "Always include a section",
              "section_order": "Section order", "heading": "Heading", "table": "Table", "must_mention": "Always mention",
              "instruction": "Instruction (tone, emphasis)"}

Q = r"[\"'“”‘’]"
_PH = r"[\"'“”‘’]?([^\"'“”‘’;,.]{1,60}?)[\"'“”‘’]?"


def _an(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", (s or "").strip())).strip(" .,;:")


def _sec(s: str) -> str:
    s = _clean(re.sub(r"^(?:the|a|an)\s+", "", _clean(s), flags=re.I))
    return re.sub(r"\s+(?:section|part|heading|paragraph)$", "", s, flags=re.I).strip()


WORDING = [
    re.compile(rf"\b(?:always\s+)?say\s+{_PH}\s*,?\s+(?:and\s+)?not\s+{_PH}\s*(?:[.;]|$)", re.I),
    re.compile(rf"\buse\s+{_PH}\s+(?:instead of|rather than|in place of|not)\s+{_PH}\s*(?:[.;]|$)", re.I),
    re.compile(rf"\bwrite\s+{_PH}\s*,?\s+(?:instead of|rather than|not)\s+{_PH}\s*(?:[.;]|$)", re.I),
    re.compile(rf"\bcall (?:it|them|the \w+)\s+{_PH}\s*,?\s+not\s+{_PH}\s*(?:[.;]|$)", re.I),
]
WORDING_REV = [  # (B, A): the word to drop comes first
    re.compile(rf"\breplace\s+{_PH}\s+(?:with|by)\s+{_PH}\s*(?:[.;]|$)", re.I),
    re.compile(rf"\bchange\s+{_PH}\s+to\s+{_PH}\s*(?:[.;]|$)", re.I),
    re.compile(rf"\b(?:don'?t|do not|never)\s+(?:say|use|write)\s+{_PH}\s*[,;]\s*(?:say|use|write)\s+{_PH}\s*(?:[.;]|$)", re.I),
    re.compile(rf"\bnot\s+{_PH}\s*,?\s+but\s+{_PH}\s*(?:[.;]|$)", re.I),
]
AVOID = re.compile(rf"\b(?:don'?t|do not|never|avoid)\s+(?:ever\s+)?(?:use|say|write|using|saying|writing)?\s*(?:the word\s+)?{_PH}\s*(?:in\b.*)?(?:[.;]|$)", re.I)
INCLUDE = [re.compile(r"\b(?:always\s+)?(?:include|add|have|keep)\s+(?:a|an|the)\s+(.{2,60}?)\s+section\b", re.I),
           re.compile(r"\b(?:always\s+)?(?:include|add)\s+a\s+section\s+(?:on|for|about|called|named|titled)\s+(.{2,60}?)\s*(?:[.;]|$)", re.I),
           re.compile(r"\bmust\s+have\s+(?:a|an)\s+(.{2,60}?)\s+section\b", re.I)]
ORDER = [re.compile(r"\b(?:put|place|move|keep)\s+(?:the\s+)?(.{2,50}?)\s+(before|after|above|below)\s+(?:the\s+)?(.{2,50}?)\s*(?:[.;]|$)", re.I),
         re.compile(r"\b(?:the\s+)?(.{2,50}?)\s+(?:section\s+)?(?:should|must|always)\s+(?:come|go|be|appear)\s+(?:right\s+|directly\s+|immediately\s+)?(before|after|above|below)\s+(?:the\s+)?(.{2,50}?)\s*(?:[.;]|$)", re.I)]
ORDER_POS = re.compile(r"\b(?:put|place|move|start with)\s+(?:the\s+)?(.{2,50}?)\s+(?:section\s+)?(first|last|at the top|at the end|at the start)\b", re.I)
HEADING = [re.compile(rf"\b(?:call|title|name|head)\s+the\s+(.{{2,50}}?)\s+section\s+{_PH}\s*(?:[.;]|$)", re.I),
           re.compile(rf"\brename\s+(?:the\s+)?(.{{2,50}}?)\s+(?:section\s+)?(?:to|as)\s+{_PH}\s*(?:[.;]|$)", re.I),
           re.compile(rf"\bthe\s+(.{{2,50}}?)\s+heading\s+(?:should|must)\s+(?:be|read)\s+{_PH}\s*(?:[.;]|$)", re.I)]
TABLE = re.compile(r"\b(?:tabulate|table|tabular|in a table|as a table|two-column)\b", re.I)
MENTION = re.compile(r"\balways\s+(?:mention|state|show|give|disclose|include|cite|quote)\s+(?:the\s+)?(.{3,80}?)\s*(?:\bin\s+(?:the\s+)?(.{2,50}?)(?:\s+section)?)?\s*(?:[.;]|$)", re.I)
MONEY = re.compile(r"\b(?:mn|million|millions|m)\b", re.I)


def _units(t: str) -> dict[str, Any] | None:
    low = t.lower()
    out: dict[str, Any] = {}
    if re.search(r"\bmillions?\b|\bmn\b|\bsar\s*m\b|amounts?|figures in", low) and re.search(r"\b(?:write|show|express|use|state|put|give)\b|\bas\b|\bin\b", low):
        m = re.search(r"(?:as|in|use|write)\s+[\"'“‘]?(?:sar\s*)?(?:\d[\d.,]*\s*)?(mn|million|m)\b[\"'”’]?", low)
        if m and re.search(r"million|mn|\bm\b", low):
            out["money_suffix"] = {"mn": "mn", "million": "million", "m": "m"}[m.group(1)]
    if re.search(r"per ?cent|percent|%", low) and re.search(r"\b(?:write|use|show|as)\b", low):
        if re.search(r"(?:as|use|write)\s+[\"'“‘]?per ?cent", low) and not re.search(r"(?:as|use|write)\s+[\"'“‘]?%", low):
            out["percent"] = "per cent"
        elif re.search(r"(?:as|use|write)\s+[\"'“‘]?%|percent sign|the % sign", low):
            out["percent"] = "%"
    return out or None


def parse(text: str, section: str = "") -> dict[str, Any]:
    """The deterministic reading of an instruction. Returns {kind, params, section}."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    figures = bool(re.search(r"\d", t))  # "change the amount to SAR 50m" is about this deal, not a wording rule
    for rx in ([] if figures else WORDING):
        m = rx.search(t)
        if m and _clean(m.group(1)) and _clean(m.group(2)) and _clean(m.group(1)).lower() != _clean(m.group(2)).lower():
            return {"kind": "wording", "params": {"use": _clean(m.group(1)), "instead_of": _clean(m.group(2))}, "section": section}
    for rx in ([] if figures else WORDING_REV):
        m = rx.search(t)
        if m and _clean(m.group(1)) and _clean(m.group(2)) and _clean(m.group(1)).lower() != _clean(m.group(2)).lower():
            return {"kind": "wording", "params": {"use": _clean(m.group(2)), "instead_of": _clean(m.group(1))}, "section": section}
    u = _units(t)
    if u:
        return {"kind": "units", "params": u, "section": section}
    if TABLE.search(t) and re.search(r"risk", t, re.I):
        header = ["Risk", "Mitigant"]
        return {"kind": "table", "params": {"section": "risks", "header": header}, "section": section or "risks"}
    for rx in HEADING:
        m = rx.search(t)
        if m:
            return {"kind": "heading", "params": {"section": _sec(m.group(1)), "heading": _clean(m.group(2))}, "section": _sec(m.group(1))}
    m = ORDER_POS.search(t)
    if m:
        pos = "first" if m.group(2).lower() in ("first", "at the top", "at the start") else "last"
        return {"kind": "section_order", "params": {"section": _sec(m.group(1)), "position": pos}, "section": ""}
    for rx in ORDER:
        m = rx.search(t)
        if m and not re.search(r"\b(?:figure|number|amount|word)\b", m.group(1), re.I):
            rel = "before" if m.group(2).lower() in ("before", "above") else "after"
            return {"kind": "section_order", "params": {"section": _sec(m.group(1)), rel: _sec(m.group(3))}, "section": ""}
    for rx in INCLUDE:
        m = rx.search(t)
        if m:
            h = _sec(m.group(1))
            return {"kind": "include_section", "params": {"heading": h[:1].upper() + h[1:]}, "section": ""}
    m = MENTION.search(t)
    if m:
        sec = _sec(m.group(2)) if m.group(2) else section
        return {"kind": "must_mention", "params": {"phrase": _clean(m.group(1))}, "section": sec}
    m = AVOID.search(t)
    if m and _clean(m.group(1)) and len(_clean(m.group(1)).split()) <= 4:
        return {"kind": "avoid", "params": {"phrase": _clean(m.group(1))}, "section": section}
    return {"kind": "instruction", "params": {}, "section": section}


def rule_text(kind: str, params: dict[str, Any], instruction: str, section_label: str = "") -> str:
    """The rule as the analyst will read it in their list."""
    where = f" in {section_label}" if section_label else ""
    if kind == "wording":
        return f"Say “{params['use']}”, not “{params['instead_of']}”{where}."
    if kind == "avoid":
        return f"Never write “{params['phrase']}”{where}."
    if kind == "units":
        bits = []
        if params.get("money_suffix"):
            bits.append({"mn": "amounts in millions as SAR 12.5 mn", "m": "amounts in millions as SAR 12.5m",
                         "million": "amounts in millions as SAR 12.5 million"}[params["money_suffix"]])
        if params.get("percent"):
            bits.append("percentages as 12.5 per cent" if params["percent"] == "per cent" else "percentages as 12.5%")
        return "Write " + " and ".join(bits) + "."
    if kind == "include_section":
        return f"Always include {_an(params['heading'])} “{params['heading']}” section."
    if kind == "section_order":
        if params.get("position"):
            return f"Put {params['section']} {params['position']}."
        rel = "before" if params.get("before") else "after"
        return f"Put {params['section']} {rel} {params.get(rel)}."
    if kind == "heading":
        return f"Head the {params['section']} section “{params['heading']}”."
    if kind == "table":
        return f"Tabulate {params.get('section', 'risks')}: {' | '.join(params.get('header') or ['Risk', 'Mitigant'])}, one row each."
    if kind == "must_mention":
        return f"Always state {params['phrase']}{where}."
    t = re.sub(r"\s+", " ", instruction.strip())
    return (t[:1].upper() + t[1:]).rstrip(".") + "." if t else ""


# ------------------------------------------------------------------ model path

TOOL = {"name": "save_rule", "description": "Turn an analyst's instruction into a reusable writing rule.",
        "input_schema": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "rule": {"type": "string", "description": "The rule in one short imperative sentence, general (not about this deal)."},
            "use": {"type": "string"}, "instead_of": {"type": "string"}, "phrase": {"type": "string"},
            "heading": {"type": "string"}, "section": {"type": "string"}, "before": {"type": "string"}, "after": {"type": "string"},
            "money_suffix": {"type": "string", "enum": ["mn", "m", "million"]}, "percent": {"type": "string", "enum": ["%", "per cent"]}},
            "required": ["kind", "rule"]}}
SYSTEM = ("An analyst gave CreditProbe an instruction while editing a credit document. Decide whether it can be a rule for "
          "their future documents and classify it. Quote phrases exactly as the analyst wrote them. A rule never contains a "
          "figure or a name of this deal; if the instruction is only about this deal, use kind 'instruction' and generalise it.")


def _model(instruction: str, section: str) -> dict[str, Any] | None:
    try:
        from backend.convo import provider as prov
        from backend.convo import telemetry
    except Exception:  # noqa: BLE001
        return None
    p = prov.default()
    if p is None:
        return None
    try:
        with telemetry.use(module="dealdesk", request_path="/api/v1/dealdesk/rules/suggest"):
            reply = p.step("dealdesk_rule_classify", SYSTEM,
                           [{"role": "user", "content": json.dumps({"instruction": instruction, "section": section})}], [TOOL])
    except Exception:  # noqa: BLE001 - the parser reads it
        return None
    use = next((u for u in reply.tool_uses() if u.get("name") == "save_rule"), None)
    if not use:
        return None
    x = use.get("input") or {}
    kind = x.get("kind")
    if kind not in KINDS:
        return None
    low = instruction.lower()
    keys = {"wording": ("use", "instead_of"), "avoid": ("phrase",), "include_section": ("heading",), "heading": ("section", "heading"),
            "must_mention": ("phrase",)}.get(kind, ())
    params = {k: str(x.get(k) or "").strip() for k in keys}
    if any(not v for v in params.values()):
        return None
    if kind in ("wording", "avoid") and any(v.lower() not in low for v in params.values()):
        return None  # a phrase the analyst never wrote is not their rule
    if kind == "units":
        params = {k: x[k] for k in ("money_suffix", "percent") if x.get(k)}
        if not params:
            return None
    if kind == "section_order":
        params = {k: str(x[k]) for k in ("section", "before", "after") if x.get(k)}
        if "section" not in params or not ({"before", "after"} & params.keys()):
            return None
    if kind == "table":
        params = {"section": str(x.get("section") or "risks"), "header": ["Risk", "Mitigant"]}
    if re.search(r"\d", str(x.get("rule") or "")) and kind == "instruction":
        return None  # a deal's figure in a general rule
    return {"kind": kind, "params": params, "section": str(x.get("section") or section or ""), "rule": str(x.get("rule") or "")}


def classify(instruction: str, section: str = "", section_label: str = "", use_model: bool = True) -> dict[str, Any]:
    """{kind, kind_label, params, section, text, method}: the model's reading when it validates, else the parser's."""
    got = _model(instruction, section) if use_model else None
    method = "model" if got else "rules"
    if not got:
        got = parse(instruction, section)
    text = rule_text(got["kind"], got["params"], instruction, section_label if got["kind"] in ("wording", "avoid", "must_mention") else "")
    if got["kind"] == "instruction" and got.get("rule"):
        text = got["rule"]
    return {"kind": got["kind"], "kind_label": KIND_LABEL[got["kind"]], "params": got["params"], "section": got.get("section") or section,
            "text": text, "method": method,
            "deterministic": got["kind"] != "instruction"}
