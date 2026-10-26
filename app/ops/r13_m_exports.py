"""PLAN_R13 Session M: house-style checks on every export (R12 exports + R13: the §S methodology memo, the renewal
autopilot one-page note, the inspection pack in Word and Excel, the governance workbooks), from the running services.

  python ops/r13_m_exports.py [--api http://127.0.0.1:8508] [--whatif http://127.0.0.1:8503]

Word and Excel files go through backend.house_style.check (the R11 house-style checker); PDFs must open as PDF;
the bank-form proposals and committee papers also report coverage, voice, density and page counts.
Writes docs/v5/r13_review/m/exports.json. No secret is read or printed.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
from backend.house_style import check  # noqa: E402

OUT = V5 / "docs" / "v5" / "r13_review" / "m" / "exports.json"
P = "/api/v1/dealdesk"


def get(api: str, path: str, method: str = "GET", body: dict | None = None) -> bytes:
    req = urllib.request.Request(api + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def pages(data: bytes) -> int | None:
    try:
        from backend.dealdesk.house_style.bankform.pages import docx_pages
        return docx_pages(data)
    except Exception:  # noqa: BLE001 - no LibreOffice here
        return None


def main(api: str, whatif: str = "http://127.0.0.1:8503") -> int:
    rows: list[dict] = []

    def add(name: str, path: str, kind: str, method: str = "GET", body: dict | None = None, count_pages: bool = False) -> None:
        try:
            data = get(whatif if kind == "docx_whatif" else api, path, method, body)
            if kind in ("docx", "docx_whatif"):
                probs = check.docx(data)
            elif kind == "xlsx":
                probs = check.xlsx(data)
            else:
                probs = [] if data[:4] == b"%PDF" else ["not a PDF"]
            row = {"export": name, "path": path, "bytes": len(data), "problems": probs}
            if count_pages and kind == "docx":
                row["pages"] = pages(data)
        except Exception as e:  # noqa: BLE001 - recorded
            row = {"export": name, "path": path, "error": str(e)[:200], "problems": ["fetch failed"]}
        rows.append(row)
        print(name, "OK" if not row["problems"] else row["problems"], row.get("pages", ""), flush=True)

    for pid in ("R12-TWA", "R12-TWB", "R12-ESC", "R12-SYN", "DD-01", "PL-03"):
        add(f"{pid} credit proposal (Word)", f"{P}/proposals/{pid}/bank-form.docx", "docx", count_pages=pid.startswith("R12-TW"))
        add(f"{pid} committee paper (Word)", f"{P}/proposals/{pid}/committee-paper.docx", "docx", count_pages=pid.startswith("R12-TW"))
    for pid in ("R12-TWA", "R12-TWB"):
        add(f"{pid} credit proposal (PDF)", f"{P}/proposals/{pid}/bank-form.pdf", "pdf")
        add(f"{pid} committee paper (PDF)", f"{P}/proposals/{pid}/committee-paper.pdf", "pdf")
        try:
            bf = json.loads(get(api, f"{P}/proposals/{pid}/bank-form"))
            cp = json.loads(get(api, f"{P}/proposals/{pid}/committee-paper"))
            rows.append({"export": f"{pid} validators", "sections": len(bf.get("sections", [])), "coverage": bf.get("coverage"),
                         "voice": bf.get("voice"), "gaps": bf.get("gaps"), "density": cp.get("density"),
                         "problems": list(bf.get("coverage") or []) + list(bf.get("voice") or []) + list(cp.get("density") or [])})
            print(pid, "validators", rows[-1]["problems"] or "OK", flush=True)
        except Exception as e:  # noqa: BLE001
            rows.append({"export": f"{pid} validators", "error": str(e)[:200], "problems": ["fetch failed"]})
    add("Parameters workbook (Excel)", f"{P}/parameters/export.xlsx", "xlsx")
    try:
        pols = json.loads(get(api, f"{P}/policies")).get("policies") or []
        if pols:
            p0 = pols[0]
            add(f"Policy {p0.get('policy_id')} v{p0.get('version')} (Word)", f"{P}/policies/{p0['policy_id']}/{p0['version']}/document.docx", "docx")
    except Exception as e:  # noqa: BLE001
        rows.append({"export": "policy library", "error": str(e)[:200], "problems": ["fetch failed"]})
    # ---------------------------------------------------------------- R13 exports
    add("§S methodology memo (Word)", "/api/v1/whatif/scenario-engine/memo.docx", "docx_whatif")
    try:
        q = json.loads(get(api, "/api/v1/dealdesk/intel/renewals?cls=clean&limit=1"))
        rows_ = q.get("rows") or q.get("items") or []
        if rows_:
            fid = rows_[0].get("facility_id") or rows_[0].get("fid") or rows_[0].get("id")
            add(f"Renewal autopilot one-page note {fid} (Word)", f"/api/v1/dealdesk/intel/renewals/{fid}/note.docx", "docx")
    except Exception as e:  # noqa: BLE001
        rows.append({"export": "renewal note", "error": str(e)[:200], "problems": ["fetch failed"]})
    ask = {"request": "The auditor wants approvals, conditions and stage for CB00039 and R12-TWA", "sample": []}
    add("Inspection pack (Word)", "/api/v1/intel/governance/inspection/export?fmt=docx", "docx", "POST", ask)
    add("Inspection pack (Excel)", "/api/v1/intel/governance/inspection/export?fmt=xlsx", "xlsx", "POST", ask)
    for eng in ("exceptions", "rm-track", "doa"):
        add(f"Governance {eng} (Excel)", f"/api/v1/intel/governance/{eng}/export", "xlsx")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, default=str))
    bad = [r for r in rows if r["problems"]]
    print(f"{len(rows) - len(bad)} of {len(rows)} exports clean")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8508")
    ap.add_argument("--whatif", default="http://127.0.0.1:8503")
    a = ap.parse_args()
    sys.exit(main(a.api, a.whatif))
