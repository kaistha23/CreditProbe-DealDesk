import { test } from "node:test";
import assert from "node:assert/strict";

import { backLabel, herePath, isInternal, readFrom, stripFrom, shouldHistoryBack, withFrom } from "./back-link-model.ts";

const P = (s: string) => new URLSearchParams(s);

test("K1: a brief navigation carries from=brief and the target reads Back to Brief", () => {
  const href = withFrom("/intelligence/regulatory?check=c_stage3", "brief");
  assert.equal(href, "/intelligence/regulatory?check=c_stage3&from=brief");
  const o = readFrom(P(href.split("?")[1]));
  assert.deepEqual(o, { label: "Brief", href: "/?tab=brief" });
  assert.equal(backLabel(o!), "Back to Brief");
});

test("K11: a borrower card carries the filtered list as the back path", () => {
  const href = withFrom("/borrower-360?id=CB00020", "ews", "/early-warning?band=red&sector=Hospitality");
  const sp = P(href.split("?")[1]);
  assert.equal(sp.get("id"), "CB00020");
  assert.equal(sp.get("from"), "ews");
  assert.deepEqual(readFrom(sp), { label: "Early Warning", href: "/early-warning?band=red&sector=Hospitality" });
});

test("first origin wins; override replaces", () => {
  const a = withFrom("/x?from=brief", "ews");
  assert.equal(a, "/x?from=brief");
  assert.equal(withFrom("/x?from=brief", "ews", null, true), "/x?from=ews");
});

test("back paths never nest and never point at the same screen", () => {
  const href = withFrom("/b?id=1", "ask", "/?tab=ask&from=brief&back=%2Fz");
  assert.equal(P(href.split("?")[1]).get("back"), "/?tab=ask");
  assert.equal(withFrom("/a?q=1", "deal", "/a?q=1"), "/a?q=1&from=deal");
});

test("hash is kept at the end", () => {
  assert.equal(withFrom("/t/1#turn-3", "ask"), "/t/1?from=ask#turn-3");
});

test("external or unsafe paths are refused", () => {
  assert.equal(withFrom("https://evil.example/x", "brief"), "https://evil.example/x");
  for (const bad of ["//evil.example", "/\\evil", "javascript:alert(1)", "http://x", "", null]) {
    assert.equal(isInternal(bad as string), false, String(bad));
  }
  assert.deepEqual(readFrom(P("from=brief&back=%2F%2Fevil.example")), { label: "Brief", href: "/?tab=brief" });
});

test("unknown origin: needs a back path; junk from is ignored", () => {
  assert.equal(readFrom(P("from=somewhere")), null);
  assert.deepEqual(readFrom(P("from=somewhere&back=%2Fx")), { label: "somewhere", href: "/x" });
  assert.equal(readFrom(P("from=%3Cscript%3E&back=%2Fx")), null);
  assert.equal(readFrom(P("")), null);
});

test("herePath strips from/back; history back only when the previous entry is the target", () => {
  assert.equal(herePath({ pathname: "/early-warning", search: "?band=red&from=brief" }), "/early-warning?band=red");
  assert.equal(stripFrom("/a?from=x&back=%2Fb#h"), "/a#h");
  assert.equal(shouldHistoryBack("http://127.0.0.1:6600/?tab=brief", "/?tab=brief"), true);
  assert.equal(shouldHistoryBack("http://127.0.0.1:6600/lenses", "/?tab=brief"), false);
  assert.equal(shouldHistoryBack(null, "/?tab=brief"), false);
});
