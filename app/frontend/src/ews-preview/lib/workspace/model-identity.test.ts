/**
 * The model details screen's identity, readiness and recovery.
 *
 * This file exists because of a failed acceptance run: the model details page
 * handed the panel a presentation sentence ("release · period · rule set")
 * where the panel's guard expects `domain|period`. The two can never be equal,
 * so a reading that had already arrived was presented as "Reading the rule
 * set…" for ever. That is a property of a string comparison, so it is tested
 * as one — and the states around it (switching book, switching period, a read
 * that failed and then succeeded) are tested as a sequence.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  modelDetailHref,
  modelDisplayState,
  modelIdentity,
  modelIsCurrent,
} from "./model-identity.ts";

const retail = { domain_id: "retail", period: "2026-06" };
const corporate = { domain_id: "corporate", period: "2026-06" };

describe("the identity a model reading is judged by", () => {
  it("is the book and the period, not a sentence for a reader", () => {
    assert.equal(modelIdentity("retail", "2026-06"), "retail|2026-06");
    assert.ok(modelIsCurrent(retail, modelIdentity("retail", "2026-06")));
  });

  it("rejects the presentation string that made the page sit on loading", () => {
    const sentence = "ews_retail_v5 · 2026-06 · rule set ews.RULES@5";
    assert.equal(modelIsCurrent(retail, sentence), false);
    assert.equal(modelDisplayState({ model: retail, identity: sentence, error: "" }), "loading");
    // The same reading, asked for by identity, is ready.
    assert.equal(
      modelDisplayState({ model: retail, identity: modelIdentity("retail", "2026-06"), error: "" }),
      "ready",
    );
  });

  it("holds a reading from the other book back as not yet arrived", () => {
    const want = modelIdentity("corporate", "2026-06");
    assert.equal(modelIsCurrent(retail, want), false);
    assert.equal(modelDisplayState({ model: retail, identity: want, error: "" }), "loading");
    assert.equal(modelDisplayState({ model: corporate, identity: want, error: "" }), "ready");
  });

  it("holds last period's reading back after a period switch", () => {
    const want = modelIdentity("retail", "2026-09");
    assert.equal(modelIsCurrent({ domain_id: "retail", period: "2026-06" }, want), false);
    assert.ok(modelIsCurrent({ domain_id: "retail", period: "2026-09" }, want));
  });

  it("accepts the period the server chose when the address names none", () => {
    // No period in the address means "the period this release publishes last";
    // the reading comes back stamped with it, and that is still current.
    const want = modelIdentity("retail", "");
    assert.ok(modelIsCurrent(retail, want));
    assert.equal(modelDisplayState({ model: retail, identity: want, error: "" }), "ready");
    assert.equal(modelIsCurrent(corporate, want), false);
  });

  it("has nothing to show before the first reading lands", () => {
    assert.equal(modelIsCurrent(null, modelIdentity("retail", "")), false);
    assert.equal(modelDisplayState({ model: null, identity: modelIdentity("retail", ""), error: "" }), "loading");
  });
});

describe("what the screen shows while the reader switches and recovers", () => {
  it("says a failure out loud instead of spinning", () => {
    const want = modelIdentity("retail", "2026-06");
    assert.equal(modelDisplayState({ model: null, identity: want, error: "the backend did not respond" }), "error");
    // A failure outranks a stale reading too: the screen must not present the
    // previous book's rule set as this book's while a read is failing.
    assert.equal(modelDisplayState({ model: corporate, identity: want, error: "boom" }), "error");
  });

  it("recovers when the next read for the same identity succeeds", () => {
    const want = modelIdentity("retail", "2026-06");
    // The page clears the error when it asks again, so the sequence is
    // error -> loading -> ready without a reload.
    assert.equal(modelDisplayState({ model: null, identity: want, error: "boom" }), "error");
    assert.equal(modelDisplayState({ model: null, identity: want, error: "" }), "loading");
    assert.equal(modelDisplayState({ model: retail, identity: want, error: "" }), "ready");
  });

  it("recovers when the reader switches to the book that can be read", () => {
    const failed = modelIdentity("retail", "2026-06");
    assert.equal(modelDisplayState({ model: null, identity: failed, error: "boom" }), "error");
    const switched = modelIdentity("corporate", "2026-06");
    assert.equal(modelDisplayState({ model: null, identity: switched, error: "" }), "loading");
    assert.equal(modelDisplayState({ model: corporate, identity: switched, error: "" }), "ready");
  });
});

describe("links into the model details", () => {
  it("carry the book and the period, inside the Early Warning module", () => {
    assert.equal(modelDetailHref("corporate", "2026-06"), "/early-warning/model?domain=corporate&period=2026-06");
    const href = modelDetailHref("retail", "2026-06");
    const url = new URL(href, "http://127.0.0.1:5436");
    assert.equal(url.pathname, "/early-warning/model");
    assert.equal(url.searchParams.get("domain"), "retail");
    assert.equal(url.searchParams.get("period"), "2026-06");
  });

  it("point at the v5 Early Warning module's model page, never into the Cockpit", () => {
    // v5: /early-warning IS the Early Warning module (its own backend, 8501);
    // the frozen Cockpit lives at / and /cockpit and is never linked into here.
    assert.ok(modelDetailHref("retail", "").startsWith("/early-warning/model"));
    assert.ok(!modelDetailHref("retail", "").startsWith("/cockpit"));
    assert.equal(modelDetailHref("retail", ""), "/early-warning/model?domain=retail");
  });

  it("round-trips: the address a link makes is the identity the page asks for", () => {
    const url = new URL(modelDetailHref("corporate", "2026-03"), "http://127.0.0.1:5436");
    const domain = url.searchParams.get("domain") === "corporate" ? "corporate" : "retail";
    const identity = modelIdentity(domain, url.searchParams.get("period") ?? "");
    assert.ok(modelIsCurrent({ domain_id: "corporate", period: "2026-03" }, identity));
    assert.equal(modelIsCurrent({ domain_id: "retail", period: "2026-03" }, identity), false);
  });
});
