"""UAT sweep, PLAN_R4 (part "r4-scorecard"). Imported by ops/uat_sweep.py, which puts ops/ on the path and passes the Sweep.

B3 Scorecard charts and G1/G3 on the Scorecard Validation screens. For each seeded validation (RET-APP, RET-BEH,
SME-ANN): the row on the home opens its thread, every test-group tab is opened (all WoE charts shown), and every
chart is checked in the browser from Plotly's own drawn layout (`el._fullLayout`, `el._fullData`) and the SVG:
the chart count matches the API, variable charts are horizontal bars, both axes have automargin, the legend sits
above the plot area, no tick label is clipped by the chart, no two tick labels overlap, and the legend overlaps no
tick label. The explanations are behind an (i), not loose text on the card; Back returns to the home. The Word
report is downloaded once (house style and the label rule are checked by the Sweep) and carries the charts.
Each step ends with no console error, no page error and no failed request (the Sweep).
"""
from __future__ import annotations

import io
import json
import urllib.request
import zipfile
from typing import Any, Callable

import core_login

SC = "http://127.0.0.1:8507/api/v1/scorecard"
HORIZONTAL = {"iv_bar", "vif", "csi_bar", "gini_segment", "ovr_outcome"}

# One chart, measured as drawn. Rects are in page pixels; 1px tolerance for anti-aliasing.
_MEASURE = r"""
(el) => {
  const fl = el._fullLayout, fd = el._fullData || [];
  if (!fl) return null;
  const box = el.getBoundingClientRect();
  const rect = (n) => { const r = n.getBoundingClientRect(); return {l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height}; };
  const texts = (sel) => [...el.querySelectorAll(sel)].filter((n) => (n.textContent || '').trim() && n.getBoundingClientRect().width > 0).map((n) => ({text: n.textContent.trim(), ...rect(n)}));
  const xt = texts('g.xaxislayer-above g.xtick text');
  const yt = texts('g.yaxislayer-above g.ytick text');
  const hit = (a, b) => Math.min(a.r, b.r) - Math.max(a.l, b.l) > 1 && Math.min(a.b, b.b) - Math.max(a.t, b.t) > 1;
  const overlaps = (list) => { const out = []; for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) if (hit(list[i], list[j])) out.push(list[i].text + ' / ' + list[j].text); return out; };
  const clipped = [...xt, ...yt].filter((r) => r.l < box.left - 1 || r.r > box.right + 1 || r.t < box.top - 1 || r.b > box.bottom + 1).map((r) => r.text);
  const legendNode = el.querySelector('g.legend');
  const legend = fl.showlegend && legendNode ? rect(legendNode) : null;
  const legendHits = legend ? [...xt, ...yt].filter((r) => hit(r, legend)).map((r) => r.text) : [];
  const plot = el.querySelector('g.cartesianlayer .bg, rect.bg') ? rect(el.querySelector('rect.bg')) : null;
  const bars = fd.filter((t) => t.type === 'bar');
  return {
    bars: bars.length, horizontal: bars.length > 0 && bars.every((t) => t.orientation === 'h'),
    xauto: !!(fl.xaxis && fl.xaxis.automargin), yauto: !!(fl.yaxis && fl.yaxis.automargin),
    showlegend: !!fl.showlegend, legendY: fl.legend ? fl.legend.y : null, legendAnchor: fl.legend ? fl.legend.yanchor : null,
    legendAbovePlot: !legend || !plot || legend.b <= plot.t + 1,
    xticks: xt.length, yticks: yt.length, clipped, overlapX: overlaps(xt), overlapY: overlaps(yt), legendHits,
  };
}
"""


def tid(t: str) -> str:
    return f'[data-testid="{t}"]'


def _get(path: str, cookie: str) -> Any:
    req = urllib.request.Request(SC + path, headers={"Cookie": f"cp_session={cookie}"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
        return json.loads(r.read())


def _open_from_home(page, UI: str, wait_for, validation_id: str) -> None:
    page.goto(UI + "/scorecard-validation", wait_until="domcontentloaded")
    wait_for(page, r".*/scorecard-validation$")
    page.wait_for_selector(tid("sv-past-row"), timeout=90_000)
    page.locator(f'{tid("sv-past-row")}[data-id="{validation_id}"] {tid("sv-past-open")}').click()
    wait_for(page, r".*/scorecard-validation/thread/[^/]+$")
    page.wait_for_selector(tid("sv-validation"), timeout=120_000)


def _wait_drawn(page) -> None:
    page.wait_for_function(
        "() => { const c = [...document.querySelectorAll('[data-testid^=\"sv-chart-\"][data-rendered]')];"
        " return c.length > 0 && c.every(e => e.dataset.rendered === 'true'); }", timeout=60_000)
    page.wait_for_timeout(300)


def scorecard_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    cookie = core_login.login("anne")["cookie"]
    seeded = {}
    for v in _get("/validations", cookie)["validations"]:
        if v["scorecard_id"] not in seeded and _get(f"/validations/{v['validation_id']}", cookie).get("seed"):
            seeded[v["scorecard_id"]] = v
    s.start("scorecard", "B3-0", "Seeded validations: one per scorecard")
    s.check("a seeded validation for RET-APP, RET-BEH and SME-ANN", set(seeded) >= {"RET-APP", "RET-BEH", "SME-ANN"}, "all three", sorted(seeded))

    for sid in ("RET-APP", "RET-BEH", "SME-ANN"):
        v = seeded.get(sid)
        if not v:
            continue
        full = _get(f"/validations/{v['validation_id']}", cookie)["result"]
        s.start("scorecard", f"B3-{sid}", f"{sid}: every chart readable (horizontal variable charts, labels not clipped, legend clear)")
        _open_from_home(page, UI, wait_for, v["validation_id"])
        s.check("the past-validation row opens its thread", page.locator(tid("sv-validation")).count() == 1)
        problems: list[str] = []
        drawn = 0
        for sec in full["sections"]:
            if not sec["charts"]:
                continue
            page.locator(tid(f"sv-tab-{sec['id']}")).last.click()
            page.wait_for_selector(tid(f"sv-panel-{sec['id']}"), timeout=30_000)
            if page.locator(tid("sv-woe-toggle")).count() and "Show all" in page.locator(tid("sv-woe-toggle")).inner_text():
                page.locator(tid("sv-woe-toggle")).click()
            _wait_drawn(page)
            ids = [c["id"] for c in sec["charts"]]
            on_screen = page.locator(f'{tid(f"sv-panel-{sec["id"]}")} [data-testid^="sv-chart-card-"]').count()
            s.check(f"{sec['title']}: every chart of the API is on the screen", on_screen == len(ids), len(ids), on_screen)
            for cid in ids:
                card = page.locator(tid(f"sv-chart-card-{cid}")).last
                el = page.locator(tid(f"sv-chart-{cid}")).last
                m = el.evaluate(_MEASURE)
                if not m:
                    problems.append(f"{cid}: not drawn")
                    continue
                drawn += 1
                if (cid in HORIZONTAL or cid.startswith("woe_")) and not m["horizontal"]:
                    problems.append(f"{cid}: variable chart not horizontal")
                if not (m["xauto"] and m["yauto"]):
                    problems.append(f"{cid}: axis without automargin")
                if m["showlegend"] and not ((m["legendY"] or 0) >= 1 and m["legendAnchor"] == "bottom" and m["legendAbovePlot"]):
                    problems.append(f"{cid}: legend inside or below the plot (y={m['legendY']})")
                for key, what in (("clipped", "tick label clipped"), ("overlapX", "x tick labels overlap"), ("overlapY", "y tick labels overlap"),
                                  ("legendHits", "legend over a tick label")):
                    if m[key]:
                        problems.append(f"{cid}: {what}: {m[key][:2]}")
                if m["xticks"] + m["yticks"] == 0 and m["bars"]:
                    problems.append(f"{cid}: no tick labels")
                if card.locator("p:visible").count():  # a hidden (i) tooltip body is not loose text
                    problems.append(f"{cid}: loose text on the chart card")
                if not card.locator(tid("sv-card-title")).inner_text().strip():
                    problems.append(f"{cid}: no title")
        expected = sum(len(x["charts"]) for x in full["sections"])
        s.check("every chart is drawn", drawn == expected, expected, drawn)
        s.check("every chart passes the readability rules", not problems, "none", problems[:4])
        page.locator(tid("sv-back")).first.click()
        wait_for(page, r".*/scorecard-validation$")
        s.check("Back returns to the Scorecard Validation home", page.locator(tid("sv-home")).count() == 1)

    v = seeded.get("SME-ANN") or next(iter(seeded.values()), None)
    if not v:
        return
    s.start("scorecard", "B3-i", "Explanations behind (i): chart and table notes, the home intro; the Word report carries the charts")
    _open_from_home(page, UI, wait_for, v["validation_id"])
    page.locator(tid("sv-tab-discrimination")).last.click()
    _wait_drawn(page)
    tip = page.locator(f'{tid("sv-chart-card-roc")} {tid("sv-info")}').last
    s.check("the ROC chart's note is behind an (i)", tip.count() == 1)
    hidden = tip.locator('[role="tooltip"]').evaluate("(n) => getComputedStyle(n).visibility")
    tip.locator("button").hover()
    page.wait_for_timeout(300)
    shown = tip.locator('[role="tooltip"]').evaluate("(n) => getComputedStyle(n).visibility")
    s.check("the note shows on hover only", hidden == "hidden" and shown == "visible", "hidden → visible", f"{hidden} → {shown}")
    s.check("table notes are behind an (i), not under the table",
            page.locator(f'{tid("sv-panel-discrimination")} [data-testid^="sv-table-"] > p').count() == 0)
    with page.expect_download(timeout=120_000) as dl:
        page.locator(tid("sv-word")).first.click()
    data = open(dl.value.path(), "rb").read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        images = [n for n in z.namelist() if n.startswith("word/media/")]
    s.check("the Word report carries the charts", len(images) >= 12, ">= 12 images", len(images))
    page.goto(UI + "/scorecard-validation", wait_until="domcontentloaded")
    page.wait_for_selector(tid("sv-past-row"), timeout=90_000)
    chat = page.locator(tid("sv-chat"))
    s.check("the home has no loose intro paragraph in the chat card", chat.locator("p").count() == 0, 0, chat.locator("p").count())
    s.check("the home intro is behind the (i) beside the title", page.locator('main button[aria-label="What is this screen for?"]').count() >= 1)
    s.check("one primary action on the home", page.locator("main button.bg-accent, main a.bg-accent").count() == 1, 1,
            page.locator("main button.bg-accent, main a.bg-accent").count())
