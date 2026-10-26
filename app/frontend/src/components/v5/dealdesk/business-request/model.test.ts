import { test } from "node:test";
import assert from "node:assert/strict";

import { brHref, brStudioHref, brUrls, customerIn, isBusinessAsk, pagesOf, stripCustomer, traceGroups } from "./model.ts";

const CUSTOMERS = [
  { key: "c1", proposal_id: "R16-C1", cif: "CB09001", name: "Dar Al Naseem Medical Supplies Co.", short: "Dar Al Naseem", cr_number: "1010384527", existing: true },
  { key: "c3", proposal_id: "R16-C3", cif: "", name: "Nukhba Polymer Industries Co.", short: "Nukhba Polymer", cr_number: "2055104486", existing: false },
];

test("an RM's ask is told apart from a question", () => {
  assert.equal(isBusinessAsk("Renew all facilities and increase the overdraft to SAR 60m"), true);
  assert.equal(isBusinessAsk("Take over the other bank's facilities with a SAR 60m term loan"), true);
  assert.equal(isBusinessAsk("Write the business request for Nukhba Polymer"), true);
  assert.equal(isBusinessAsk("Which proposals breach a hard limit?"), false);
  assert.equal(isBusinessAsk("How much real-estate headroom is left this quarter?"), false);
  assert.equal(isBusinessAsk("Why does DD-03 fail?"), false);
  assert.equal(isBusinessAsk("New SME customer Sanad: overdraft SAR 3m and LGs SAR 5m for tenders"), true);
  assert.equal(isBusinessAsk("How much sector headroom is left?"), false);
});

test("the customer a line names", () => {
  assert.equal(customerIn("Dar Al Naseem: renew all and increase the LC to SAR 40m", CUSTOMERS)?.key, "c1");
  assert.equal(customerIn("new limit for CR 2055104486", CUSTOMERS)?.key, "c3");
  assert.equal(customerIn("renew the overdraft", CUSTOMERS), null);
  assert.equal(stripCustomer("Dar Al Naseem: renew all", CUSTOMERS[0]), "renew all");
  assert.equal(stripCustomer("Renew Dar Al Naseem's SAR 95m facilities", CUSTOMERS[0]), "Renew Dar Al Naseem's SAR 95m facilities");
});

test("urls", () => {
  assert.equal(brUrls.docx("BR-R16-C1-1A2B3C4D"), "/api/v1/dealdesk/business-requests/BR-R16-C1-1A2B3C4D.docx");
  assert.equal(brUrls.customer("R16 C1"), "/api/v1/dealdesk/business-requests/customer/R16%20C1");
  assert.equal(brHref("BR-1"), "/deal-desk?br=BR-1");
  assert.equal(brStudioHref("c1", "renew all"), "/deal-desk?brc=c1&ask=renew%20all");
});

test("pages: header with the action requested on page 1, one page per part", () => {
  const s = (key: string) => ({ key, n: null, heading: key, voice: "business", part: "anatomy", blocks: [], gaps: [], method: "deterministic" });
  const pages = pagesOf({ sections: ["header", "action", "facilities", "background", "justification"].map(s),
                          parts: [{ key: "action", title: "ACTION REQUESTED", subtitle: "", sections: ["action", "facilities"] },
                                  { key: "business", title: "BUSINESS COMMENTS", subtitle: "", sections: ["background"] },
                                  { key: "justification", title: "RM'S JUSTIFICATION", subtitle: "", sections: ["justification"] }] });
  assert.deepEqual(pages.map((p) => p.sections.map((x) => x.key)), [["header", "action", "facilities"], ["background"], ["justification"]]);
});

test("trace groups by source, most used first", () => {
  const f = (source: string) => ({ section: "x", label: "l", value: 1, text: "1", source });
  const g = traceGroups([f("A"), f("B"), f("B")]);
  assert.deepEqual(g.map((x) => [x.source, x.figures.length]), [["B", 2], ["A", 1]]);
});
