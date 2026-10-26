/**
 * Banker language only (PLAN_R12 N2, R11_FEEDBACK I9 and I10 c): no internal tool, function or column name reaches a
 * reader. A follow-up chip such as "Run pipeline_optimise on the book" or "…with pipeline_test" reads "Optimise the
 * pipeline" / "…with the pipeline test". Every conversational layer passes its chips (and its answer prose) through
 * here, so a writer or a model that slips a tool name into a suggestion is corrected on screen.
 *
 * Pure TypeScript: tested with the node runner.
 */

/** Each internal tool: [what a banker would ask for, the thing it produces as a noun]. */
export const TOOL_PHRASES: Record<string, [string, string]> = {
  // Deal Desk
  pipeline_optimise: ["Optimise the pipeline", "the pipeline optimiser"],
  pipeline_optimize: ["Optimise the pipeline", "the pipeline optimiser"],
  pipeline_test: ["Test against the pipeline", "the pipeline test"],
  optimise: ["Optimise the structure", "the optimiser"],
  compute_terms: ["Price these terms", "the pricing"],
  alternatives: ["Show the alternatives", "the alternatives"],
  breakeven: ["Find the break-even margin", "the break-even margin"],
  compare: ["Compare the structures", "the comparison"],
  headroom: ["Check the limit headroom", "the limit headroom"],
  explain_constraint: ["Explain the limit", "the limit explanation"],
  explain_tile: ["Explain this figure", "the explanation"],
  forward_risk: ["Show the forward risk", "the forward risk"],
  stress: ["Stress the deal", "the stress test"],
  stress_lab: ["Open the stress lab", "the stress lab"],
  run_stress_analysis: ["Run the stress test", "the stress test"],
  review_memo: ["Review the proposal", "the proposal review"],
  committee_sheet: ["Prepare the committee sheet", "the committee sheet"],
  get_proposal: ["Open the proposal", "the proposal"],
  model_card: ["Show the model card", "the model card"],
  conduct_account: ["Check the account conduct", "the account conduct"],
  bureau_external: ["Check the bureau", "the bureau report"],
  collateral_mechanics: ["Check the collateral", "the collateral review"],
  b360_evidence: ["Show the group evidence", "the group evidence"],
  last_result: ["Show the last result", "the last result"],
  // What-If and ECL
  whatif_run_scenario: ["Run the scenario", "the scenario run"],
  whatif_design_scenarios: ["Design scenarios", "the scenario designs"],
  whatif_compare: ["Compare the scenarios", "the scenario comparison"],
  whatif_book_profile: ["Profile the book", "the book profile"],
  whatif_size_overlay: ["Size the overlay", "the overlay sizing"],
  whatif_test_action: ["Test the action", "the action test"],
  propose_scenario: ["Propose a scenario", "the proposed scenario"],
  scenario_ideas: ["Suggest scenarios", "the scenario ideas"],
  assess_likelihood: ["Assess the likelihood", "the likelihood assessment"],
  ecl_impact: ["Show the ECL impact", "the ECL impact"],
  decompose_ecl_factors: ["Break down the ECL drivers", "the ECL driver breakdown"],
  decompose_movement: ["Explain the movement", "the movement breakdown"],
  decompose_ratio: ["Break down the ratio", "the ratio breakdown"],
  diagnose: ["Diagnose the change", "the diagnosis"],
  // Early Warning
  ews_changes: ["Show what changed in early warning", "the early-warning changes"],
  ews_rules_trend: ["Show the warning-rule trend", "the warning-rule trend"],
  ews_sector_peers: ["Compare with sector peers", "the sector peers"],
  ews_warned_names: ["List the warned names", "the warned names"],
  propose_sicr: ["Propose SICR", "the SICR proposal"],
  propose_utp: ["Propose unlikely-to-pay", "the unlikely-to-pay proposal"],
  propose_watchlist: ["Propose for the watchlist", "the watchlist proposal"],
  triage_decide: ["Record the triage decision", "the triage decision"],
  triage_followup: ["Follow up the triage", "the triage follow-up"],
  triage_history: ["Show the triage history", "the triage history"],
  triage_summary: ["Summarise the triage", "the triage summary"],
  crm_assess: ["Assess the credit-risk rules", "the credit-risk rule assessment"],
  crm_breaches: ["List the rule breaches", "the rule breaches"],
  // Lenses
  build_lens: ["Build a lens", "the lens"],
  edit_lens: ["Edit the lens", "the lens"],
  lenses_backtest: ["Back-test the lens", "the back-test"],
  lenses_candidates: ["Find candidate names", "the candidate names"],
  lenses_composition: ["Show the composition", "the composition"],
  lenses_compute: ["Compute the lens", "the lens result"],
  lenses_decompose: ["Break down the change", "the breakdown"],
  lenses_detect: ["Detect outliers", "the outliers"],
  lenses_driver: ["Show the drivers", "the drivers"],
  lenses_ews_read: ["Read early warning", "the early-warning signals"],
  lenses_load_set: ["Load the lens set", "the lens set"],
  lenses_materiality: ["Check materiality", "the materiality check"],
  lenses_movement: ["Show the movement", "the movement"],
  lenses_notify: ["Notify the owners", "the notification"],
  lenses_propose_changes: ["Propose changes", "the proposed changes"],
  lenses_propose_set: ["Propose a lens set", "the proposed lens set"],
  lenses_rank: ["Rank the names", "the ranking"],
  lenses_regulation: ["Check the regulation", "the regulation check"],
  lenses_review: ["Review the lens", "the lens review"],
  lenses_risk_appetite: ["Check the risk appetite", "the risk appetite"],
  lenses_scope: ["Set the scope", "the scope"],
  lenses_whatif_read: ["Read the what-if results", "the what-if results"],
  suggest_tiles: ["Suggest tiles", "the suggested tiles"],
  tile_to_thread: ["Discuss this tile", "the tile"],
  // Scorecard validation
  calibration_by_grade: ["Check calibration by grade", "the calibration by grade"],
  segment_gini: ["Show the Gini by segment", "the Gini by segment"],
  variable_psi: ["Show the variable stability", "the variable stability"],
  metric_history: ["Show the metric history", "the metric history"],
  // Playbook, Admin, Workspace, Cockpit
  read_report: ["Read the report", "the report"],
  restructure_report: ["Restructure the report", "the restructured report"],
  section_outline: ["Outline the section", "the section outline"],
  search_documents: ["Search the documents", "the documents"],
  draft_policy: ["Draft the policy", "the policy draft"],
  draft_workflow: ["Draft the workflow", "the workflow draft"],
  preview_access: ["Preview the access", "the access preview"],
  override_analysis: ["Review the overrides", "the override analysis"],
  run_governed_analysis: ["Run the analysis", "the analysis"],
  run_query: ["Look it up", "the data"],
  query_dataset: ["Look it up in the data", "the data"],
  aggregate_dataset: ["Total it up", "the totals"],
  join_governed_datasets: ["Combine the data", "the combined data"],
  compare_periods: ["Compare the periods", "the period comparison"],
  rank_entities: ["Rank the names", "the ranking"],
  describe_dataset: ["Describe the data", "the data description"],
  describe_domain: ["Describe the data domain", "the data domain"],
  list_datasets: ["List the data", "the data list"],
  list_data_domains: ["List the data domains", "the data domains"],
  list_certified_analyses: ["List certified analyses", "the certified analyses"],
  get_available_dimensions: ["Show the breakdowns available", "the breakdowns available"],
  get_available_measures: ["Show the measures available", "the measures available"],
  get_data_dictionary: ["Open the data dictionary", "the data dictionary"],
  get_dataset_periods: ["Show the periods available", "the periods available"],
  get_metric_definition: ["Define the measure", "the measure definition"],
  get_model_definition: ["Explain the model", "the model definition"],
  get_policy_definition: ["Quote the policy", "the policy"],
  get_threshold_definition: ["Explain the threshold", "the threshold"],
  get_relationships: ["Show the relationships", "the relationships"],
  fetch_borrower_360: ["Open Borrower 360", "Borrower 360"],
  fetch_collateral_evidence: ["Show the collateral evidence", "the collateral evidence"],
  fetch_covenant_evidence: ["Show the covenant evidence", "the covenant evidence"],
  fetch_early_warning_evidence: ["Show the early-warning evidence", "the early-warning evidence"],
  fetch_external_intelligence: ["Show the external intelligence", "the external intelligence"],
  fetch_group_exposure: ["Show the group exposure", "the group exposure"],
  fetch_ifrs9_evidence: ["Show the IFRS 9 evidence", "the IFRS 9 evidence"],
  fetch_trace_evidence: ["Show the trace", "the trace"],
  inspect_catalog: ["Look at the data catalogue", "the data catalogue"],
  read_knowledge: ["Look it up in the product guide", "the product guide"],
  read_policy: ["Quote the policy", "the policy"],
  finalize_answer: ["Answer", "the answer"],
};

const ESCAPE = /[.*+?^${}()|[\]\\]/g;
const NAMES = Object.keys(TOOL_PHRASES).sort((a, b) => b.length - a.length);
const NAME_RE = NAMES.map((n) => n.replace(ESCAPE, "\\$&")).join("|");
/** Only names with an underscore are matched in running text: "stress", "compare" or "optimise" are also English. */
const SNAKE_RE = NAMES.filter((n) => n.includes("_")).map((n) => n.replace(ESCAPE, "\\$&")).join("|");
/** A verb before a tool name ("run pipeline_optimise") becomes the banker action; "with/using X" the noun. */
const VERB = new RegExp(`\\b(?:run|call|invoke|use|execute|trigger)\\s+(?:the\\s+)?\`?(${SNAKE_RE})\`?(?:\\s+(?:tool|function))?\\b`, "gi");
const PREP = new RegExp(`\\b(with|using|via|from|through|by)\\s+(?:the\\s+)?\`?(${SNAKE_RE})\`?(?:\\s+(?:tool|function))?\\b`, "gi");
/** A bare tool name only when it is unmistakably one: it has an underscore, or sits in backticks. */
const BARE_SNAKE = new RegExp(`\`?\\b(${SNAKE_RE})\\b\`?`, "g");
const BARE_TICKED = new RegExp(`\`(${NAME_RE})\``, "g");

const lowerFirst = (s: string) => (/^[A-Z][a-z]/.test(s) && !/^(ECL|SICR|IFRS|Gini|Borrower)/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
const upperFirst = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** The text with every internal tool name replaced by banker words. Prose keeps its sentence case. */
export function bankerText(text: string): string {
  let s = String(text ?? "");
  if (!s) return s;
  const startsSentence = (offset: number, whole: string) => offset === 0 || /[.!?:]\s*$/.test(whole.slice(0, offset));
  s = s.replace(VERB, (_m, name: string, offset: number, whole: string) => {
    const action = TOOL_PHRASES[name.toLowerCase()][0];
    return startsSentence(offset, whole) ? action : lowerFirst(action);
  });
  s = s.replace(PREP, (_m, prep: string, name: string) => `${prep} ${TOOL_PHRASES[name.toLowerCase()][1]}`);
  s = s.replace(BARE_TICKED, (_m, name: string) => TOOL_PHRASES[name.toLowerCase()][1]);
  s = s.replace(BARE_SNAKE, (_m, name: string, offset: number, whole: string) => {
    const noun = TOOL_PHRASES[name.toLowerCase()][1];
    return startsSentence(offset, whole) ? upperFirst(noun) : noun;
  });
  return s;
}

/** Any other code-like identifier in a chip (`ead_sar_mn`, `stage_2_share`) is read out in words. */
function humaniseIdentifiers(s: string): string {
  return s.replace(/`([^`]+)`/g, "$1").replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, (id) =>
    id.split("_").map((w) => (w === "sar" ? "SAR" : w === "mn" ? "million" : w === "pct" ? "%" : /^(ead|ecl|lgd|pd|psi|raroc|sva|rwa|dscr|ltv)$/.test(w) ? w.toUpperCase() : w)).join(" "));
}

/** Chips read as a banker's next question: tool names mapped, identifiers in words, at most `max` characters. */
export function bankerLabel(label: string, max = 64): string {
  let s = humaniseIdentifiers(bankerText(label)).replace(/\s+/g, " ").trim();
  s = s.replace(/^(?:tool|function)\s*:\s*/i, "");
  s = upperFirst(s);
  if (s.length > max) {
    const cut = s.slice(0, max - 1);
    const at = cut.lastIndexOf(" ");
    s = `${(at > max * 0.6 ? cut.slice(0, at) : cut).replace(/[,;:\s]+$/, "")}…`;
  }
  return s;
}

export interface BankerChip { label: string; send: string }

/**
 * Follow-up chips, in banker language: labels mapped and shortened, the text sent mapped too (the server reads a
 * banker question as well as a tool name), duplicates and empties dropped, at most `limit`.
 */
export function bankerChips<T extends { label: string; send?: string }>(chips: readonly T[] | null | undefined, limit = 4): (T & BankerChip)[] {
  const seen = new Set<string>();
  const out: (T & BankerChip)[] = [];
  for (const c of chips ?? []) {
    if (!c || !String(c.label ?? "").trim()) continue;
    const label = bankerLabel(c.label);
    const key = label.toLowerCase().replace(/\W+/g, " ").trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const send = c.send === undefined ? bankerText(c.label) : bankerText(c.send);
    out.push({ ...c, label, send });
    if (out.length >= limit) break;
  }
  return out;
}

/** True when the text still carries an internal identifier a reader should not see (used by tests and the sweep). */
export function hasInternalName(text: string): boolean {
  return new RegExp(`\\b(${NAMES.filter((n) => n.includes("_")).map((n) => n.replace(ESCAPE, "\\$&")).join("|")})\\b`).test(text);
}
