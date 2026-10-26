import assert from "node:assert/strict";
import { test } from "node:test";

import { OBJECT_LABEL, embedHref, fileSize, hasFilters, listWhen, mailWhen, replyAllRecipients, replySubject, splitQuoted } from "./core.ts";

const u = (username: string) => ({ username }) as never;

test("embedHref appends embed=1 with the right separator", () => {
  assert.equal(embedHref("/borrower-360?domain=corporate"), "/borrower-360?domain=corporate&embed=1");
  assert.equal(embedHref("/documents/x"), "/documents/x?embed=1");
});

test("replySubject does not stack Re:", () => {
  assert.equal(replySubject("Hello"), "Re: Hello");
  assert.equal(replySubject("RE: Hello"), "RE: Hello");
});

test("reply-all addresses everyone but me, once", () => {
  const msg = { sender: u("a"), to: [u("me"), u("b")], cc: [u("c"), u("b"), u("me")] };
  assert.deepEqual(replyAllRecipients(msg, "me"), { to: ["a", "b"], cc: ["c"] });
  const mine = { sender: u("me"), to: [u("b")], cc: [] };
  assert.deepEqual(replyAllRecipients(mine, "me"), { to: ["b"], cc: [] });
});

test("mailWhen is a fixed UTC format", () => {
  assert.equal(mailWhen("2026-07-07T08:31:00Z"), "7 Jul 2026, 08:31");
  assert.equal(mailWhen(null), "—");
});

test("fileSize", () => {
  assert.equal(fileSize(12), "12 B");
  assert.equal(fileSize(2048), "2.0 KB");
  assert.equal(fileSize(5 * 1024 * 1024), "5.0 MB");
});

test("listWhen: HH:MM today (UTC), day and month this year, with the year before", () => {
  const now = new Date("2026-10-11T12:00:00Z");
  assert.equal(listWhen("2026-10-11T07:05:00Z", now), "07:05");
  assert.equal(listWhen("2026-10-10T23:59:00Z", now), "10 Oct");
  assert.equal(listWhen("2026-07-07T08:31:00Z", now), "7 Jul");
  assert.equal(listWhen("2025-12-31T08:31:00Z", now), "31 Dec 2025");
  assert.equal(listWhen(null, now), "");
});

test("splitQuoted keeps what the sender wrote and folds the quoted reply", () => {
  const html = "<p>No overlay yet.</p><blockquote><p>On 20 Jul 2026, 07:00 UTC, Khalid wrote:</p><p>Noura,</p></blockquote>";
  const parts = splitQuoted(html);
  assert.equal(parts.main, "<p>No overlay yet.</p>");
  assert.ok(parts.quoted.startsWith("<blockquote>") && parts.quoted.includes("Khalid wrote:"));
  assert.deepEqual(splitQuoted("<p>plain</p>"), { main: "<p>plain</p>", quoted: "" });
});

test("hasFilters: only the filters beyond free text count", () => {
  assert.equal(hasFilters({ q: "construction" }), false);
  assert.equal(hasFilters({ from: "sara.aldosari" }), true);
  assert.equal(hasFilters({ has_attachment: true }), true);
  assert.equal(hasFilters({ date_to: "2026-07-07" }), true);
});

test("every R3 object type has a label", () => {
  for (const t of ["analysis", "investigation", "project", "report", "scorecard-validation"] as const) assert.ok(OBJECT_LABEL[t]);
});
