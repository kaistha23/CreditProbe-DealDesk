"""Build the `queries` and `brf` data domains (PLAN_R9 Session F).

    .venv/bin/python -m ops.build_queries_domains          write data/queries_v5/queries-brf-v1/
    .venv/bin/python -m ops.build_queries_domains --check  exit 1 if the committed release differs from a rebuild

Relations (all keyed to the corporate book at its as-of quarter):
  query_case     one row per prepared case: sender, article, question count, file
  query_answer   one row per case × question: headline figure, rule, article, sources, period
  brf_return     one row per credit return: title, frequency, article, field count, totals of the as-of run
  brf_field      one row per return × field: dataset, fields, filters, calculation
  brf_line       one row per return × grid line at the as-of: EAD, ECL, share (so BRF totals reconcile with the book)
Deterministic: a rebuild writes identical bytes.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

import pandas as pd

from backend.queries_v5 import brf as B
from backend.queries_v5 import engine as E

V5 = pathlib.Path(__file__).resolve().parents[1]
RELEASE = "queries-brf-v1"
OUT = V5 / "data" / "queries_v5" / RELEASE
KEYS = {"query_case": ["case_id"], "query_answer": ["case_id", "question_no"], "brf_return": ["return_id"],
        "brf_field": ["return_id", "field_id"], "brf_line": ["return_id", "line_no"]}
DICTIONARY = {
    "case_id": "Prepared query case (Q1–Q5).", "title": "What the case asks about.", "sender": "Who sent the letter (auditor, CBUAE, internal audit).",
    "article": "The CBUAE CRM article the answer rests on.", "questions": "Number of questions in the letter.", "file": "The letter in demo_inputs/queries.",
    "question_no": "Question number in the letter.", "question": "The question as written.", "rule": "The rule ID behind the answer.",
    "sources": "Relations the answer reads.", "period": "Book period the answer is computed at.", "headline": "The draft answer's first sentence.",
    "return_id": "Credit return (R1–R4).", "frequency": "Reporting frequency.", "fields": "Number of mapped fields.", "field_id": "Field code in the return.",
    "label": "Field label.", "domain": "Domain the field reads.", "dataset": "Relation the field reads.", "columns": "Columns the field reads.",
    "filters": "Filter applied.", "calc": "Calculation.", "line_no": "Line number in the return grid.", "line": "Grid line label.",
    "ead_sar_mn": "Exposure at default on the line (SAR million).", "ecl_sar_mn": "Provisions (ECL) on the line (SAR million), where the return has them.",
    "count": "Facilities on the line.", "total_ead_sar_mn": "Total EAD of the return at the as-of (SAR million).",
}


def frames() -> dict[str, pd.DataFrame]:
    files = {p.name[:2]: p.name for p in (V5 / "demo_inputs" / "queries").glob("Q*_*.docx")}
    case, ans = [], []
    from backend.queries_v5.api import letter_text, questions
    for k, c in E.CASES.items():
        qs = questions(letter_text(files[k], (V5 / "demo_inputs" / "queries" / files[k]).read_bytes())) if k in files else []
        out = E.run_case(k, qs)
        case.append({"case_id": k, "title": c["title"], "sender": c["from"], "article": c["article"], "questions": len(out), "file": files.get(k, ""), "period": E.as_of()})
        for a in out:
            ans.append({"case_id": k, "question_no": a["n"], "question": a["question"] or c["title"], "rule": a["powered_by"]["rule"],
                        "article": a["trace"]["article"], "sources": ",".join(a["trace"]["sources"]), "period": a["trace"]["period"],
                        "headline": a["draft"].split(". ")[0].replace("**", "")})
    ret, fld, line = [], [], []
    for rid, r in B.RETURNS.items():
        run = B.run(rid)
        fm = B.field_map(rid)
        ret.append({"return_id": rid, "title": r["title"], "frequency": r["frequency"], "article": r["article"], "fields": len(fm),
                    "period": run["period"], "total_ead_sar_mn": round(float(E.book()["ead_sar_mn"].sum()), 6)})
        for f in fm:
            fld.append({"return_id": rid, "field_id": f["id"], "label": f["label"], "domain": f["domain"], "dataset": f["dataset"],
                        "columns": ",".join(f["fields"]), "filters": f["filters"], "calc": f["calc"], "period": run["period"]})
        for i, row in enumerate(run["grid"]["rows"], 1):
            line.append({"return_id": rid, "line_no": i, "line": str(row["line"]), "count": int(row.get("count") or row.get("members") or 0),
                         "ead_sar_mn": round(float(row.get("ead") or 0.0), 6), "ecl_sar_mn": round(float(row["ecl"]), 6) if "ecl" in row else None,
                         "period": run["period"]})
    return {"query_case": pd.DataFrame(case), "query_answer": pd.DataFrame(ans), "brf_return": pd.DataFrame(ret),
            "brf_field": pd.DataFrame(fld), "brf_line": pd.DataFrame(line)}


def _bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="zstd")
    return buf.getvalue()


def manifest(fr: dict[str, pd.DataFrame]) -> dict:
    return {"release_id": RELEASE, "origin": "BOOK_DERIVED", "as_of": E.as_of(), "book": "corporate",
            "built_from": ["data/cockpit_v4_lake/v4-saudi-corporate-20q-v4", "data/regulatory/cbuae-crm-v1", "demo_inputs/queries"],
            "relations": {k: {"rows": len(v), "keys": KEYS[k], "columns": list(v.columns)} for k, v in fr.items()},
            "dictionary": DICTIONARY}


def build() -> None:
    fr = frames()
    OUT.mkdir(parents=True, exist_ok=True)
    for k, df in fr.items():
        (OUT / f"{k}.parquet").write_bytes(_bytes(df))
    (OUT / "manifest.json").write_text(json.dumps(manifest(fr), indent=2, default=str) + "\n")


def check() -> int:
    fr = frames()
    bad = [k for k, df in fr.items() if not (OUT / f"{k}.parquet").exists()
           or not pd.read_parquet(OUT / f"{k}.parquet").equals(df.reset_index(drop=True))]
    for k in bad:
        print(f"differs: {k}")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    build()
    print(f"wrote {OUT.relative_to(V5)}")
