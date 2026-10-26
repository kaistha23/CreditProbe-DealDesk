import { test } from "node:test";
import assert from "node:assert/strict";

import { monitorScopeOf, monitorTabOf, scopeQuery } from "./monitoring-scope.ts";

const lens = (template_key: string, filters: { dim: string; values: string[] }[] = []) =>
  ({ lens_id: "lens-1", book: "corporate" as const, template_key, spec: { filters } });

test("a lens the agent built opens its set's scope", () => {
  assert.deepEqual(monitorScopeOf(lens("monitor:corporate:all")), { book: "corporate", filters: [] });
  const f = [{ dim: "sector", values: ["Construction"] }];
  assert.deepEqual(monitorScopeOf(lens("monitor:corporate:sector=Construction", f)), { book: "corporate", filters: f });
  assert.deepEqual(monitorScopeOf(lens("monitor:lens:lens-9")), { lensId: "lens-9" });
});

test("any other lens is a scope of its own", () => {
  assert.deepEqual(monitorScopeOf(lens("")), { lensId: "lens-1" });
  assert.deepEqual(monitorScopeOf(lens("cro-portfolio")), { lensId: "lens-1" });
});

test("the notification link opens the right tab", () => {
  assert.equal(monitorTabOf("alerts"), "alerts");
  assert.equal(monitorTabOf("active"), "active");
  assert.equal(monitorTabOf("1"), "proposed");
  assert.equal(monitorTabOf(null), undefined);
});

test("scope query", () => {
  assert.equal(scopeQuery({ lensId: "lens-1" }), "lens_id=lens-1");
  assert.equal(new URLSearchParams(scopeQuery({ book: "retail" })).get("filters"), "[]");
});
