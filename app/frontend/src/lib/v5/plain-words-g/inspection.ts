/**
 * R14 G (K14, K15, K34): the "In plain words" writer for the inspection responder — its empty state and its result.
 */
import type { InspectionPack } from "../intel-governance.ts";
import { lines } from "./fmt.ts";

export function writeInspectionEmpty(samples: number): string[] {
  return lines(
    "Use this when a regulator, an auditor or internal audit asks for evidence on borrowers",
    "You get a Word pack and an Excel with every figure traced, and a check of what was asked against what the data holds",
    `Pick one of the ${samples} sample requests below, or paste the request`,
  );
}

export function writeInspection(p: InspectionPack): string[] {
  const seed = p.coverage.some((c) => c.evidence === "governance register (demo seed)");
  const head = (p.summary ?? `${p.items.length} items; ${p.coverage_summary.answered} of ${p.coverage.length} requests answered`)
    .replace(/; approvals and conditions from the governance register \(demo seed\)/, "").replace(/\.$/, "");
  return lines(
    `The answer: ${head}`,
    "The table gives each borrower's exposure, stage path, approval and conditions",
    seed ? "Approvals come from a demo register; say so in any real reply" : null,
    `Download the Word or Excel pack above; ${p.pack_id} is its reference`,
  );
}
