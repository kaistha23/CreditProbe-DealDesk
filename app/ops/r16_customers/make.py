"""R16 d: generate a customer pack (python -m ops.r16_customers.make c2 [c1 c3 c4] [--no-images]).

Writes data/dealdesk/demo_customers/<folder>/{word,pdf,images}/, manifest.json and facts.json. Deterministic: the
same spec gives the same numbers (files differ only in PDF/DOCX timestamps).
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import pathlib
import re
import sys
from typing import Any, Callable

from ops.r16_customers import docs as B
from ops.r16_customers import render
from ops.r16_customers.doctypes import BY_CODE
from ops.r16_customers.ids import AS_OF

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "dealdesk" / "demo_customers"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def plan(sp: dict[str, Any]) -> list[tuple[str, str, Callable[[], tuple], list[int], str]]:
    """(doc_type, subject, builder, image pages, image mode) in checklist order."""
    P: list[tuple[str, str, Callable[[], tuple], list[int], str]] = []
    for p in sp["people"]:
        P.append(("national_id", slug(p["name"].replace("Al-", "al ")), (lambda p=p: B.national_id(sp, p)), [1], "photo"))
    P.append(("articles_of_association", "", lambda: B.articles(sp), [1], "scan"))
    P.append(("commercial_registration", "", lambda: B.cr(sp), [1], "photo"))
    P.append(("vat_certificate", "", lambda: B.vat_cert(sp), [1], "scan"))
    if sp["co"].get("zakat"):
        P.append(("zakat_certificate", "", lambda: B.zakat(sp), [1], "scan"))
    P.append(("nitaqat_certificate", "", lambda: B.nitaqat(sp), [1], "photo"))
    P.append(("vat_returns", "oct2025_sep2026", lambda: B.vat_returns(sp), [1], "scan"))
    P.append(("simah_company", "", lambda: B.simah_company(sp), [1], "scan"))
    for p in sp["people"]:
        if p.get("simah"):
            P.append(("simah_consumer", slug(p["name"].replace("Al-", "al ")), (lambda p=p: B.simah_consumer(sp, p)), [1], "scan"))
    for y in ("FY2024", "FY2025"):
        if y in sp["audit"]:
            P.append(("audited_fs", y.lower(), (lambda y=y: B.audited_fs(sp, y)), [1, 2] if y == "FY2025" else [2], "photo"))
    if sp.get("inhouse_by"):
        P.append(("inhouse_fs", "9m2026", lambda: B.inhouse_fs(sp), [1], "scan"))
    for a in sp["accounts"]:
        P.append(("bank_statement", slug(a["bank"].split()[0] + " " + a["type"].split("(")[0]), (lambda a=a: B.bank_statement(sp, a)), [1], "photo"))
    if sp.get("request"):
        P.append(("facility_request_letter", "", lambda: B.request_letter(sp), [1], "photo"))
    if sp.get("resolution"):
        P.append(("board_resolution", "", lambda: B.board_resolution(sp), [1], "scan"))
    if sp.get("signatories"):
        P.append(("authorised_signatories", "", lambda: B.signatories(sp), [], ""))
    for p in sp["people"]:
        if p.get("pnw"):
            P.append(("personal_net_worth", slug(p["name"].replace("Al-", "al ")), (lambda p=p: B.pnw(sp, p)), [1], "photo"))
    for ob in sp.get("other_banks", []):
        P.append(("other_bank_offer_letter", slug(ob["bank"]), (lambda ob=ob: B.other_bank_offer(sp, ob)), [1], "scan"))
        P.append(("other_bank_statement", slug(ob["bank"]), (lambda ob=ob: B.other_bank_stmt(sp, ob)), [], ""))
    if sp.get("rec_ageing"):
        P.append(("receivables_ageing", "", lambda: B.rec_ageing(sp), [1], "scan"))
    if sp.get("pay_ageing"):
        P.append(("payables_ageing", "", lambda: B.pay_ageing(sp), [], ""))
    if sp.get("top"):
        P.append(("top_customers_suppliers", "", lambda: B.top_cs(sp), [], ""))
    if sp.get("projects"):
        P.append(("project_list", "", lambda: B.project_list(sp), [1], "scan"))
        for p in sp["projects"]["rows"]:
            if p.get("contract"):
                P.append(("project_contract", slug(p["id"]), (lambda p=p: B.project_contract(sp, p)), [], ""))
        pk = next(p for p in sp["projects"]["rows"] if p.get("contract"))
        for ipc in sp["ipcs"]:
            if ipc["no"] in sp.get("ipc_docs", []):
                P.append(("payment_certificate", slug(ipc["no"]), (lambda ipc=ipc: B.payment_cert(sp, pk, ipc)), [1] if ipc["no"] in ("IPC-11", "IPC-17") else [], "photo"))
    for col in sp.get("collateral", []):
        P.append(("valuation_report", slug(col["key"]), (lambda col=col: B.valuation(sp, col)), [1], "scan"))
        P.append(("title_deed", slug(col["key"]), (lambda col=col: B.title_deed(sp, col)), [1], "photo"))
        P.append(("insurance_policy", slug(col["key"]), (lambda col=col: B.insurance(sp, col)), [], ""))
    if sp.get("site_visit"):
        P.append(("site_visit_report", "", lambda: B.site_visit(sp), [], ""))
    if sp.get("aml"):
        P.append(("aml_kyc_questionnaire", "", lambda: B.aml(sp), [], ""))
    if sp.get("consent"):
        P.append(("simah_consent", "", lambda: B.simah_consent(sp), [], ""))
    skip = {(m["doc_type"], m.get("subject", "")) for m in sp.get("skip", [])}
    return [x for x in P if (x[0], x[1]) not in skip and (x[0], "*") not in skip]


def months_between(a: str, b: str) -> float:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days / 30.44


def status(code: str, meta: dict[str, Any]) -> str:
    rule = BY_CODE[code].validity
    if rule == "expiry_date" and meta.get("expiry_date") and meta["expiry_date"] < AS_OF:
        return "expired"
    if rule.startswith("months:") and meta.get("issue_date") and months_between(meta["issue_date"], AS_OF) > int(rule.split(":")[1]):
        return "expired"
    return "received"


def build(key: str, images: bool = True) -> dict[str, Any]:
    mod = importlib.import_module(f"ops.r16_customers.{key}")
    sp = mod.spec()
    folder = OUT / sp["co"]["folder"]
    for sub in ("word", "pdf", "images"):
        d = folder / sub
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*"):
            f.unlink()
    entries = []
    for n, (code, subj, fn, pages, mode) in enumerate(plan(sp), start=1):
        model, fields, meta = fn()
        base = f"{n:02d}_{code}" + (f"__{subj}" if subj else "")
        render.docx(model, folder / "word" / f"{base}.docx")
        render.pdf(model, folder / "pdf" / f"{base}.pdf")
        imgs = []
        if images:
            for pg in pages:
                img = render.photo(render.page_png(folder / "pdf" / f"{base}.pdf", pg), seed=f"{key}-{base}-{pg}", mode=mode)
                p = folder / "images" / f"{base}_p{pg}.jpg"
                render.save_jpg(img, p)
                imgs.append(f"images/{p.name}")
        entries.append({"doc_id": f"{key.upper()}-{n:02d}", "doc_type": code, "subject": subj or None, "title": model["title"],
                        "issuer": meta.get("issuer"), "issue_date": meta.get("issue_date"), "expiry_date": meta.get("expiry_date"),
                        "period_from": meta.get("period_from"), "period_to": meta.get("period_to"), "status_expected": status(code, meta),
                        "files": {"docx": f"word/{base}.docx", "pdf": f"pdf/{base}.pdf", "images": imgs}, "fields": fields})
    extra = {}
    if hasattr(mod, "bank") and hasattr(mod, "proposal_text"):
        from ops.r16_customers import proposal
        bk = mod.bank(sp)
        P = mod.proposal_text(sp, bk)
        extra = proposal.write(sp, bk, P, folder, br_alone=bool(sp.get("br_alone")), images=images)
        (folder / "bank").mkdir(exist_ok=True)
        (folder / "bank" / "bank_side.json").write_text(json.dumps(bk, indent=1, ensure_ascii=False, default=str))
        sp["ask"] = P.get("ask_summary")
    man = {"customer_key": key, "proposal_id": sp["co"]["proposal_id"], "cif": sp["co"]["cif"] or None, "customer_name": sp["co"]["name"],
           "cr_number": sp["co"]["cr_number"], "as_of": AS_OF, "documents": entries, "missing": sp.get("missing", []),
           "business_request": extra.get("business_request"), "reference": extra.get("reference")}
    (folder / "manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False, default=str))
    facts = {k: v for k, v in sp.items() if k not in ("co",)}
    facts["co"] = sp["co"]
    (folder / "facts.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False, default=str))
    if hasattr(mod, "ASK"):
        (folder / "ASK.md").write_text(mod.ASK)
    write_customers_json()
    print(f"{key}: {len(entries)} documents, {sum(len(e['files']['images']) for e in entries)} images -> {folder.relative_to(ROOT)}")
    return sp


def write_customers_json() -> None:
    from ops.r16_customers.ids import CUSTOMERS
    out = []
    for c in CUSTOMERS:
        row = dict(c)
        fp = OUT / c["folder"] / "facts.json"
        if fp.exists():
            f = json.loads(fp.read_text())
            row["headline_sar"] = {y: {"revenue": round(f["fs"][y]["revenue"] * 1e6), "net_profit": round(f["fs"][y]["net_profit"] * 1e6),
                                       "total_equity": round(f["fs"][y]["total_equity"] * 1e6)} for y in ("FY2024", "FY2025", "9M2026") if y in f["fs"]}
            row["ask"] = f.get("ask")
            row["documents"] = len(json.loads((OUT / c["folder"] / "manifest.json").read_text())["documents"])
        out.append(row)
    import importlib as _il
    parts = ["# R16 demo customers: answer key\n\nThe twist of each case, where it is discoverable (which documents and bank data to join) "
             "and what the reference credit comments say. Generated by `python -m ops.r16_customers.make`; all names fictional.\n"]
    for c in CUSTOMERS:
        try:
            parts.append(_il.import_module(f"ops.r16_customers.{c['key']}").ANSWER)
        except (ImportError, AttributeError):
            pass
    (OUT / "ANSWER_KEY.md").write_text("\n".join(parts))
    (OUT / "customers.json").write_text(json.dumps({"as_of": AS_OF, "customers": out}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for k in args or ["c1", "c2", "c3", "c4"]:
        build(k, images="--no-images" not in sys.argv)
