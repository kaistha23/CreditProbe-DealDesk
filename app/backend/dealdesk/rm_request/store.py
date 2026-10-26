"""Save and read business requests: Data Domains (dd_business_request, upsert) and a runtime cache under var/ (the API reads the
cache first, then the relation). Publishing is best-effort: a store problem never fails writing the request."""
from __future__ import annotations

import json
import os
import pathlib
import threading
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(os.environ.get("RM_REQUEST_STATE") or pathlib.Path(__file__).resolve().parents[3] / "var" / "rm_request")
_LOCK = threading.Lock()
PUBLISH = os.environ.get("RM_REQUEST_PUBLISH", "1") != "0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def quarter(d: str) -> str:
    try:
        y, m = int(d[:4]), int(d[5:7])
        return f"{y}Q{(m - 1) // 3 + 1}"
    except (ValueError, IndexError):
        return "2026Q4"


def row(p: dict[str, Any], status: str = "written", shared_with: str = "") -> dict[str, Any]:
    t, ck = p["totals"], p["checklist"]
    return {"request_id": p["request_id"], "proposal_id": p["proposal_id"], "customer_key": p.get("customer_key") or "", "customer_name": p["customer"],
            "cif": p.get("cif") or "", "cr_number": p.get("cr_number") or "", "rm": p.get("rm") or "", "ask_text": p["ask_text"], "notes_text": p["notes_text"],
            "items_n": len(p["ask"].get("items", [])), "total_existing_mn": t.get("existing"), "total_proposed_mn": t.get("proposed"),
            "figures_n": len(p["figures"]), "untraced_n": len(p.get("untraced") or []), "docs_received_n": ck["received"], "docs_missing_n": ck["missing"],
            "docs_expired_n": ck["expired"], "disclosures_n": len(p.get("disclosures") or []), "origin": p.get("origin") or "", "status": status,
            "shared_with": shared_with, "paper_json": json.dumps(p, ensure_ascii=False, default=str), "written_at": p.get("written_at") or now(),
            "reporting_quarter": None}  # the Deal Desk as-of (store.publish fills it), like every dd_ relation


def publish(rows: list[dict[str, Any]], actor: str = "R16-b:business-request") -> dict[str, Any]:
    if not PUBLISH:
        return {"skipped": len(rows)}
    try:
        from backend.dealdesk.data import store
        return store.publish("dd_business_request", rows, mode="upsert", actor=actor)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def save(p: dict[str, Any], status: str = "written", shared_with: str = "") -> dict[str, Any]:
    p = {**p, "status": status, "shared_with": shared_with}
    with _LOCK:
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT / f"{p['request_id']}.json").write_text(json.dumps(p, ensure_ascii=False, default=str))
    res = publish([row(p, status, shared_with)])
    return {"request_id": p["request_id"], "published": "error" not in res, "publish": res}


def get(rid: str) -> dict[str, Any] | None:
    f = ROOT / f"{rid}.json"
    if f.exists():
        return json.loads(f.read_text())
    try:
        from backend.dealdesk.house_style.bankform import source as S
        rows = S.read("dd_business_request", request_id=rid)
        if rows:
            pj = rows[-1].get("paper_json")
            return json.loads(pj) if isinstance(pj, str) else pj
    except Exception:  # noqa: BLE001
        pass
    return None


def listing(proposal_id: str | None = None) -> list[dict[str, Any]]:
    out = {}
    if ROOT.exists():
        for f in ROOT.glob("BR-*.json"):
            try:
                p = json.loads(f.read_text())
            except ValueError:
                continue
            out[p["request_id"]] = {k: p.get(k) for k in ("request_id", "proposal_id", "customer", "rm", "ask_text", "written_at", "status", "shared_with")} | {
                "total_proposed": p["totals"].get("proposed")}
    try:
        from backend.dealdesk.house_style.bankform import source as S
        for r in S.read("dd_business_request"):
            out.setdefault(r["request_id"], {"request_id": r["request_id"], "proposal_id": r.get("proposal_id"), "customer": r.get("customer_name"),
                                             "rm": r.get("rm"), "ask_text": r.get("ask_text"), "written_at": str(r.get("written_at") or ""),
                                             "status": r.get("status"), "shared_with": r.get("shared_with"), "total_proposed": r.get("total_proposed_mn")})
    except Exception:  # noqa: BLE001
        pass
    rows = [v for v in out.values() if proposal_id is None or v.get("proposal_id") == proposal_id]
    return sorted(rows, key=lambda r: str(r.get("written_at") or ""), reverse=True)
