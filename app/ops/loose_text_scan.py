"""G1 (PLAN_R4): CreditProbe looks and feels like a system -- no loose explanatory text, provenance notes or warnings.

Lists every free-text paragraph on a screen that is not page content (muted or small text that is not a heading,
a figure, a table cell, a control, a chart or a chat message), and fails on the known phrases. Explanations a user
genuinely needs live behind an (i) popover, which renders nothing until it is opened.

    .venv/bin/python ops/loose_text_scan.py [route ...]     prints the inventory, exit 1 on a known phrase
The sweep part "r4-g1" (ops/sweep_r4_g1.py) runs the same scan and writes evidence/v5/r4/g1_loose_text.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
UI = "http://127.0.0.1:5500"

#: The phrases Anne listed (PLAN_R4 G1) and their siblings: provenance and runtime notes, never page content.
KNOWN = re.compile("|".join([
    r"not in this runtime", r"dashboard service", r"Cockpit V4 reachable",
    r"Charts are not available", r"not available for this item",
    r"Measured on history", r"history; not a probability",
    r"written by the assistant model", r"Read by the assistant model", r"check the restatement",
    r"every figure checked", r"Not Early Warning", r"no live signal",
    r"Frozen by Early Warning", r"membership hash",
    r"Nothing was substituted", r"The numbers above are unchanged",
]), re.I)

#: Every screen a signed-in Administrator reaches from the sidebar, plus the deep links UAT uses.
ROUTES = ["/", "/?domain=retail", "/workspace", "/messages", "/analyses", "/analyses/ead-by-sector-2026q2",
          "/investigations", "/investigations/construction-ecl-rise-q2-2026", "/projects",
          "/projects/construction-deep-dive-q2-2026", "/projects/construction-deep-dive-q2-2026/threads/pt-construction-why",
          "/playbook", "/playbook?report=rp_ccp_q2_2026", "/policy-docs", "/policy-docs?doc=pd_circ_c_2026_03",
          "/early-warning", "/early-warning?domain=retail", "/early-warning/model", "/what-if",
          "/borrower-360", "/borrower-360?domain=retail",
          "/borrower-360?domain=corporate&customer_id=CB01312&period=2026Q2&tab=profile",
          "/borrower-360?domain=retail&customer_id=RC000001&period=2026-08&tab=profile",
          "/scorecard-validation", "/data-builder", "/cockpit/data", "/deal-desk", "/deal-desk/DD-01", "/lenses", "/lenses?book=retail"]

#: Free text a user reads that is not content: small or muted paragraphs outside headings, tables, controls,
#: charts, chat answers and popovers. Each entry is the element's own text, its route and a CSS hint.
INVENTORY = r"""() => {
  const out = [];
  const skip = 'h1,h2,h3,h4,h5,h6,table,thead,tbody,tr,td,th,button,a,label,select,option,input,textarea,svg,'
    + '.js-plotly-plot,[role=dialog],[role=tooltip],[role=menu],[role=listbox],nav,aside nav,dt,dd,'
    + '[data-content],[data-testid*=markdown],[data-testid*=answer],[data-testid*=message],[data-testid*=commentary],'
    + '[data-testid*=narrative],[data-testid*=turn],.prose,[data-testid^=ews-mc],[data-testid^=whatif-mc],[data-testid*=model-card]';
  for (const el of document.querySelectorAll('p, small, span, div')) {
    if (el.closest(skip)) continue;
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\s+/g, ' ').trim();
    if (own.length < 40) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    const size = parseFloat(st.fontSize);
    const muted = /text-muted|text-text-muted|text-text-secondary|text-warning|italic/.test(el.className || '');
    if (!(muted || size <= 12)) continue;
    out.push({ text: el.innerText.replace(/\s+/g, ' ').trim().slice(0, 300), tag: el.tagName.toLowerCase(),
               testid: el.getAttribute('data-testid') || (el.closest('[data-testid]') || {getAttribute: () => ''}).getAttribute('data-testid') || '' });
  }
  return out;
}"""

SCREEN_TEXT = """() => {
  const t = [document.title, document.body ? document.body.innerText : ""];
  document.querySelectorAll('[title],[aria-label],[placeholder],[alt]').forEach(e => {
    for (const a of ['title', 'aria-label', 'placeholder', 'alt']) t.push(e.getAttribute(a) || '');
  });
  return t.join('\\n');
}"""


def known_in(text: str) -> list[str]:
    return sorted({text[max(0, m.start() - 50):m.end() + 50].replace("\n", " ") for m in KNOWN.finditer(text)})


def settle(page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(1200)


def scan_page(page) -> dict:
    """The loose-text inventory of the screen as it is now, and the known phrases on it."""
    loose = page.evaluate(INVENTORY)
    seen, rows = set(), []
    for x in loose:
        if x["text"] not in seen:
            seen.add(x["text"])
            rows.append(x)
    return {"loose": rows, "known": known_in(page.evaluate(SCREEN_TEXT))}


def main() -> int:
    sys.path.insert(0, str(V5 / "ops"))
    import core_login
    from playwright.sync_api import sync_playwright

    routes = sys.argv[1:] or ROUTES
    known_total, report = 0, {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
        core_login.add_session(ctx, "anne")
        page = ctx.new_page()
        page.set_default_timeout(60_000)
        for route in routes:
            page.goto(UI + route, wait_until="domcontentloaded")
            settle(page)
            r = scan_page(page)
            report[route] = r
            known_total += len(r["known"])
            print(f"{route}: {len(r['loose'])} loose, {len(r['known'])} known")
            for h in r["known"]:
                print("   KNOWN ", h)
            for x in r["loose"]:
                print(f"   loose  [{x['testid']}] {x['text'][:160]}")
        browser.close()
    out = V5 / "var" / "loose_text_scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(f"\n{known_total} known-phrase hits; inventory in {out.relative_to(V5)}")
    return 1 if known_total else 0


if __name__ == "__main__":
    sys.exit(main())
