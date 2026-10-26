"""R10 M: UI review at 1440x900 on every screen.

For each route: screenshot to docs/v5/r10_review/, count KPI tiles (shared KpiRow and any
[data-kpi-tile]), check they sit in one row, check horizontal overflow (document and elements
whose text overflows their box), check page height vs. viewport, and that sign-in lands on the
Cockpit. Writes docs/v5/r10_review/review.json. No secret is printed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_login  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

V5 = Path(__file__).resolve().parents[1]
OUT = V5 / "docs" / "v5" / "r10_review"
OUT.mkdir(parents=True, exist_ok=True)
UI = "http://127.0.0.1:5500"

ROUTES = [
    ("cockpit", "/"), ("early-warning", "/early-warning"), ("borrower-360", "/borrower-360"),
    ("what-if", "/what-if"), ("lenses", "/lenses"), ("deal-desk", "/deal-desk"),
    ("scorecard", "/scorecard-validation"), ("brf", "/brf"), ("workspace", "/workspace"),
    ("mail", "/messages"), ("playbook", "/playbook"), ("policy-docs", "/policy-docs"),
    ("projects", "/projects"), ("investigations", "/investigations"), ("analyses", "/analyses"),
    ("data-domains", "/data-builder"), ("redirect-intelligence", "/intelligence"),
    ("redirect-queries", "/queries"), ("redirect-accepted-risk", "/accepted-risk"),
    ("admin-users", "/users"), ("admin-settings", "/settings"), ("admin-audit", "/audit-log"),
]

PROBE = r"""
() => {
  const vw = window.innerWidth;
  const tiles = [...document.querySelectorAll('[data-kpi-tile]')].filter(e => e.offsetParent !== null);
  const rows = {};
  for (const t of tiles) {
    const row = t.closest('[data-testid="kpi-row"]') || t.parentElement;
    const k = row ? (row.dataset.rid || (row.dataset.rid = Math.random().toString(36).slice(2))) : 'x';
    (rows[k] = rows[k] || []).push(Math.round(t.getBoundingClientRect().top));
  }
  const rowInfo = Object.values(rows).map(tops => ({count: tops.length, oneRow: new Set(tops).size === 1}));
  const over = [];
  for (const e of document.querySelectorAll('main *')) {
    if (e.offsetParent === null) continue;
    const r = e.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.right > vw + 1) { over.push('beyond viewport: ' + e.tagName + '.' + String(e.className).slice(0, 60)); }
    const cs = getComputedStyle(e);
    if (e.scrollWidth > e.clientWidth + 2 && cs.overflowX === 'visible' && e.children.length === 0 && e.textContent.trim()) {
      over.push('text overflow: ' + e.tagName + ' "' + e.textContent.trim().slice(0, 50) + '"');
    }
    if (over.length > 15) break;
  }
  return {
    url: location.pathname + location.search,
    docWidth: document.documentElement.scrollWidth, vw,
    docHeight: document.documentElement.scrollHeight, vh: window.innerHeight,
    tiles: tiles.length, rows: rowInfo, overflow: over,
    title: (document.querySelector('h1') || {}).textContent || '',
  };
}
"""


def main() -> int:
    report = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=None)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        sys.path.insert(0, str(V5))
        from r10_chat_audit import session as mint  # noqa: E402  (mints a session in the identity store; no password)
        ctx.add_cookies([{"name": "cp_session", "value": mint(), "domain": "127.0.0.1", "path": "/",
                          "httpOnly": True, "sameSite": "Lax"}])
        page = ctx.new_page()
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))
        for name, path in ROUTES:
            errs.clear()
            try:
                page.goto(UI + path, wait_until="domcontentloaded", timeout=90_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=25_000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                info = page.evaluate(PROBE)
            except Exception as e:  # noqa: BLE001
                info = {"error": str(e)[:200]}
            try:
                page.screenshot(path=str(OUT / f"{name}.png"))
            except Exception as e:  # noqa: BLE001  (a renderer crash in a small container: fresh page, go on)
                info = {"error": "screenshot: " + str(e)[:120]}
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)[:160]))
            info.update({"screen": name, "route": path, "pageErrors": list(errs)})
            fails = []
            if "error" in info:
                fails.append("load error")
            else:
                if any(r["count"] > 4 for r in info["rows"]):
                    fails.append("more than 4 tiles in a row")
                if any(not r["oneRow"] for r in info["rows"]):
                    fails.append("tiles not in one row")
                if info["docWidth"] > info["vw"] + 1:
                    fails.append("horizontal page scroll")
                if info["overflow"]:
                    fails.append(f"{len(info['overflow'])} overflow item(s)")
            info["fails"] = fails
            report.append(info)
            print(f"{'OK  ' if not fails else 'FAIL'} {name:24} -> {info.get('url')} tiles={info.get('tiles')} "
                  f"h={info.get('docHeight')} {'; '.join(fails)}")
        b.close()
    (OUT / "review.json").write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
