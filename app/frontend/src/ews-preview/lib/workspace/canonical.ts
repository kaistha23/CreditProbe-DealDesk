/**
 * The canonical customer read, client side.
 *
 * Early Warning and Borrower 360 call the same four endpoints
 * (`/canonical/drill`, `/canonical/owners`, `/canonical/profile`,
 * `/canonical/model`) so the row a banker clicks in one screen and the row
 * they open in the other are the same row, from the same release and period.
 *
 * Every payload echoes `domain_id`, `release_id`, `period` and `tenant_id`,
 * and the deep link carries the first three. `borrower360Href` is the ONE
 * place that knows the parameter names: two screens agreeing on a URL by
 * coincidence is how a deep link quietly stops working.
 */

import { WorkspaceError, workspaceUrl, wsGet, wsSend } from "@/ews-preview/lib/workspace/client";
import type { DomainId } from "@/ews-preview/lib/workspace/objects";

export {
  BACK_PARAM,
  DOMAIN_PARAM,
  LEGACY_OWNER_PARAM,
  OWNER_PARAM,
  PERIOD_PARAM,
  RELEASE_PARAM,
  afterDomainSwitch,
  borrower360Href,
  selectionFrom,
} from "@/ews-preview/lib/workspace/borrower360-link";

export interface Identity {
  domain_id: DomainId;
  release_id: string;
  fingerprint: string;
  tenant_id: string;
  period: string;
  prior_period: string;
  periods: string[];
  ruleset: string;
  exposure_grain: string;
  owner_grain: string;
}

export interface Totals {
  exposures: number;
  owners: number;
  ead_sar_mn: number;
  ecl_sar_mn: number;
  bad_ead_sar_mn: number;
  bad_owners: number;
  bad_exposures: number;
  warned_performing_ead_sar_mn: number;
  warned_performing_owners: number;
  warned_performing_exposures: number;
}

export interface BandRow {
  value: string;
  /** Each owner once, in the WORST band it holds. Sums to total owners. */
  owners: number;
  /** Owners with any exposure in this band; a multi-band owner is in several
   *  rows, so this column deliberately over-counts and is never a population. */
  owners_touching: number;
  exposures: number;
  ead_sar_mn: number;
  ecl_sar_mn: number;
}

export interface Overview extends Identity {
  totals: Totals;
  bands: BandRow[];
  stage_mix: { value: number | string; n: number; ead_sar_mn: number; ecl_sar_mn: number }[];
  filter_description: string;
}

export interface ReasonRow {
  id: string;
  reason: string;
  weight: number;
  limitation: string;
  exposures: number;
  owners: number;
  ead_sar_mn: number;
}

export interface LevelRow {
  value: string | number | null;
  exposures: number;
  owners: number;
  ead_sar_mn: number;
  ecl_sar_mn: number;
  warned_owners: number;
  warned_ead_sar_mn: number;
  bad_owners: number;
  bad_exposures: number;
  bad_ead_sar_mn: number;
  bad_ecl_sar_mn: number;
  warned_performing_owners: number;
  warned_performing_ead_sar_mn: number;
  critical_owners: number;
  worst_ews_score: number | null;
}

/** One ladder value's own series, oldest first. An absent period is absent. */
export interface LevelPoint {
  period: string;
  exposures: number;
  owners: number;
  ead_sar_mn: number;
  ecl_sar_mn: number;
  warned_owners: number;
  warned_ead_sar_mn: number;
}

/** The rung's own totals over time, oldest first. */
export interface OverviewPoint {
  period: string;
  owners: number;
  bad_owners: number;
  warned_performing_owners: number;
  exposures: number;
  ead_sar_mn: number;
  ecl_sar_mn: number;
  warned_ead_sar_mn: number;
  bad_ead_sar_mn: number;
}

/** A rule actually driving one ladder value, with the EAD behind it. */
export interface LevelReason {
  id: string;
  reason: string;
  weight: number;
  exposures: number;
  owners: number;
  ead_sar_mn: number;
}

export type OwnerRow = Record<string, string | number | null> & {
  owner_id: string;
  exposures: number;
  ead_sar_mn: number | null;
  ecl_sar_mn: number | null;
  ews_score: number | null;
  ews_band: string;
  worst_stage: number | null;
  worst_dpd_days: number | null;
};

export interface OwnerPage extends Identity {
  owner_column: string;
  fields: string[];
  rows: OwnerRow[];
  total: { owners: number; exposures: number; ead_sar_mn: number; ecl_sar_mn: number };
  sort: string;
  desc: boolean;
  offset: number;
  limit: number;
  search: string;
  facets?: Record<string, { value: string | number | null; count: number }[]>;
}

export interface LadderLevel {
  id: string;
  column: string;
  label: string;
  grain: "segment" | "owner" | "exposure";
  alternate?: string;
}

export interface DrillStep {
  level: string;
  value: string | number | null;
}

export interface Drill {
  ladder: LadderLevel[];
  depth: number;
  level: LadderLevel & { column_in_use: string };
  path: DrillStep[];
  reason: string;
  overview: Overview;
  reasons: ReasonRow[];
  next_level: LevelRow[] | null;
  /** Keyed by the level value as a string; "" is the unrecorded value. */
  level_history?: Record<string, LevelPoint[]>;
  level_reasons?: Record<string, LevelReason[]>;
  history?: OverviewPoint[];
  owners: OwnerPage | null;
}

export interface RuleMeta {
  id: string;
  label: string;
  weight: number;
  expression: string;
  inputs: string[];
  missing_columns: string[];
  evaluated: boolean;
  limitation: string;
  exposures_tripped: number | null;
  owners_tripped: number | null;
  status: "live" | "live_no_match" | "not_evaluated";
}

/**
 * The ONE active signal catalogue, served by `/canonical/signals` and carried
 * inside the model read. The model screen, a customer's fired signals and the
 * investigation handoff all render THESE objects, so no screen states a
 * condition, threshold or unit of its own.
 */
export interface SignalInput {
  column: string;
  label: string;
  unit: string;
  meaning: string;
  grain: "exposure" | "owner";
  source: string;
  observed_as: string;
  published?: boolean;
}

export interface CatalogueSignal {
  id: string;
  label: string;
  expression: string;
  weight: number;
  /** Always "rule_weight". A rule weight is NOT a fitted score contribution. */
  contribution_kind: string;
  limitation: string;
  ruleset: string;
  source: string;
  source_label: string;
  source_connected: boolean;
  family: string;
  family_label: string;
  /** The internal layer key. Never rendered as the layer's name. */
  layer: string;
  /** The reader-facing layer name, served beside the key. */
  layer_label: string;
  layer_means: string;
  condition: string;
  review: string;
  proxy: boolean;
  observed_column: string;
  inputs: SignalInput[];
  inputs_required?: string[];
  missing_columns?: string[];
  evaluated?: boolean;
  exposures_tripped?: number | null;
  owners_tripped?: number | null;
  status?: "live" | "live_no_match" | "not_evaluated";
}

export interface SourceGroup {
  key: string;
  label: string;
  means: string;
  connected: boolean;
  /** Served wording for `connected`. A published relation, not a live feed. */
  availability: string;
  availability_means: string;
  absent_because: string;
  requires: string[];
  signals: string[];
  signal_count: number;
  evaluable_signals?: string[];
  evaluable_count?: number;
  has_observations?: boolean;
}

export interface SignalCatalogue extends Identity {
  catalogue_version: string;
  active_model: {
    id: string;
    name: string;
    version: string;
    kind: string;
    status: string;
    scoring: string;
    contribution_kind: string;
    contribution_caveat: string;
    overrides: string;
    model_calls: number;
  };
  signals: CatalogueSignal[];
  families: { key: string; label: string; means: string; layer: string; signals: string[] }[];
  layers: { key: string; label: string; means: string; signals: string[] }[];
  sources: SourceGroup[];
  axes: string;
  signals_total: number;
  signals_evaluated: number;
  model_calls: number;
}

/** The reference instance's model, carried as DEFINITIONS and never as scoring. */
export interface ReferenceCompatibility {
  status: string;
  scores_active: boolean;
  means: string;
  available: boolean;
  model: {
    model_id?: string;
    model_name?: string;
    model_version?: string;
    source?: string;
    captured_utc?: string;
    file_sha256?: string;
  };
  summary: {
    reference_layers?: number;
    reference_triggers?: number;
    reference_classifiers?: number;
    reference_hard_triggers?: number;
    distinct_input_mappings?: number;
    by_canonical_status?: Record<string, number>;
    verdict?: string;
  };
  inputs: {
    reference_key: string;
    reference_name: string;
    reference_kind: string;
    reference_layer: string;
    reference_sublayer: string;
    reference_column: string;
    role: string;
    reference_severity: string;
    reference_unit: string;
    reference_threshold: number | null;
    true_source_group: string;
    source_group_connected: boolean;
    canonical_status: string;
    canonical_field: string;
    canonical_label: string;
    canonical_unit: string;
    canonical_grain: string;
    note: string;
  }[];
  layers: unknown[];
  domain_id: string;
  /** The ONE domain the reference model covers. */
  reference_domain: string;
  /** False when the book being read is not that domain. */
  applies_to_domain: boolean;
  /** Set only when it does not apply: why it is not a comparison here. */
  domain_note: string;
}

/** One observed canonical value, in its own unit, dated as the book dates it. */
export interface ObservedValue {
  column: string;
  label: string;
  unit: string;
  meaning: string;
  grain: string;
  observed_as: string;
  value: unknown;
}

/** One entity's FIRED signals, with the value the book actually holds. */
export interface EntitySignals extends Identity {
  catalogue_version: string;
  active_model: SignalCatalogue["active_model"];
  entity_id: string;
  grain: string;
  found: boolean;
  exposures: {
    key: string;
    owner_id: string;
    ews_score: number | null;
    ews_band: string;
    ews_reasons: string;
    fired: string[];
  }[];
  /** Every row of this owner is counted, even where only a page is carried. */
  exposures_total: number;
  exposures_shown: number;
  truncated: boolean;
  truncation_note: string;
  /** Worst-of, never a sum. Served, not restated here. */
  aggregation: string;
  fired_signals: (CatalogueSignal & {
    /** The period of the headline observation below. */
    observed_period: string;
    exposures: string[];
    /** One dated observation per exposure that fired the rule. */
    observations: {
      exposure: string;
      owner_id: string;
      observed_period: string;
      ews_score: number | null;
      ews_band: string;
      values: ObservedValue[];
    }[];
    /** The observation of the worst-scoring exposure that fired it. */
    observed: ObservedValue[];
    observed_on: string;
    observed_exposures: number;
  })[];
  fired_count: number;
  signals_not_evaluated: string[];
  sources: { key: string; label: string; connected: boolean; absent_because: string; fired: string[] }[];
  contribution_disclosure: string;
  override_disclosure: string;
  model_calls: number;
}

export interface ModelMeta extends Identity {
  bands: { band: string; min_score: number }[];
  rules: RuleMeta[];
  rules_evaluated: number;
  rules_live: number;
  rules_no_match: number;
  rules_total: number;
  coverage: { exposures: number; unscored_exposures: number; owners: number };
  model_calls: number;
  basis: string;
  /** What the one scoring layer actually produced, band by band. */
  score_observations?: {
    bands: {
      band: string;
      min_score_required: number | null;
      exposures: number;
      owners: number;
      observed_min_score: number | null;
      observed_max_score: number | null;
      observed_mean_score: number | null;
      ead_sar_mn: number;
    }[];
    how: string;
    layers: number;
    model_calls: number;
  };
  /** The ONE active catalogue, annotated with what this release can see. */
  catalogue?: SignalCatalogue;
  /** The reference model's compatibility statement. Never its scores. */
  reference?: ReferenceCompatibility;
  /** The rule set's version history, or the statement that there is none. */
  log?: {
    ruleset: string;
    release_id: string;
    fingerprint: string;
    period: string;
    entries: {
      version: string;
      status: string;
      applied_to_periods: string[];
      source: string;
      evidence: string;
    }[];
    history_available: boolean;
    history_relations: string[];
    disclosure: string;
  };
}

export interface NetworkMember {
  owner_id: string;
  borrower_name: string | null;
  sector: string | null;
  sub_sector: string | null;
  region: string | null;
  rating_current: string | null;
  watchlist_flag: number | null;
  exposures: number;
  ead_sar_mn: number | null;
  ecl_sar_mn: number | null;
  ews_score: number | null;
  ews_band: string;
  is_centre: boolean;
  in_period: boolean;
}

export interface Network {
  published: boolean;
  centre: string;
  group_id: string | null;
  group_name: string | null;
  members: NetworkMember[];
  member_total: number;
  truncated: boolean;
  /**
   * Over EVERY recorded member of the group in this period, including the
   * members the largest-N cap does not draw. This is the denominator for a
   * member's share of the group; the drawn rows are not.
   */
  group_totals: {
    ead_sar_mn: number | null;
    ecl_sar_mn: number | null;
    exposures: number;
    members_in_period: number;
    basis: string;
  };
  period: string;
  edge_types: { id: string; label: string; source: string }[];
  missing_edge_types: { id: string; label: string }[];
  note: string;
}

export interface DetailTable {
  section: string;
  relation: string;
  published: boolean;
  rows: Record<string, string | number | null>[];
  note?: string;
}

export interface OwnerRecord {
  relation: string;
  published: boolean;
  found?: boolean;
  period: string;
  record: Record<string, string | number | null>;
}

export interface Profile extends Identity {
  owner_id: string;
  owner_column: string;
  fields: string[];
  owner: OwnerRow;
  record: OwnerRecord;
  exposures: { grain: string; key: string; rows: Record<string, string | number | null>[] };
  detail: Record<string, DetailTable>;
  early_warning: { ruleset: string; tripped: ReasonRow[] };
  history: { period: string; exposures: number; ead_sar_mn: number; ecl_sar_mn: number; worst_stage: number | null; worst_dpd_days: number | null; ews_score: number | null; ews_band: string }[];
  network: Network;
  coverage: { section: string; relation: string; published: boolean; note?: string }[];
}

export function drill(body: {
  domain: DomainId;
  period?: string;
  release?: string;
  path?: DrillStep[];
  reason?: string;
  /** A published delinquency band key; the ladder applies it with `reason`. */
  dpd?: string;
  /**
   * Warning severities the caller is focused on (`critical` / `high` /
   * `moderate` / `low`). Omitted means no severity filter; the server
   * refuses a band it does not publish rather than widening the population.
   */
  bands?: string[];
  alternate?: boolean;
  search?: string;
  sort?: string;
  desc?: boolean;
  offset?: number;
  limit?: number;
}): Promise<Drill> {
  return wsSend<Drill>("/canonical/drill", body);
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === "" || v === null) continue;
    out.set(k, String(v));
  }
  return out.toString();
}

export function ownerList(params: {
  domain: DomainId;
  period?: string;
  release?: string;
  search?: string;
  sort?: string;
  desc?: boolean;
  offset?: number;
  limit?: number;
  band?: string;
  filter_column?: string;
  filter_value?: string;
}): Promise<OwnerPage> {
  return wsGet<OwnerPage>(`/canonical/owners?${query(params)}`);
}

export function profileOf(params: {
  domain: DomainId;
  owner_id: string;
  period?: string;
  release?: string;
}): Promise<Profile> {
  return wsGet<Profile>(`/canonical/profile?${query(params)}`);
}

export function modelMeta(params: { domain: DomainId; period?: string }): Promise<ModelMeta> {
  return wsGet<ModelMeta>(`/canonical/model?${query(params)}`);
}

export function signalCatalogue(params: { domain: DomainId; period?: string }): Promise<SignalCatalogue> {
  return wsGet<SignalCatalogue>(`/canonical/signals?${query(params)}`);
}

/**
 * One customer's or borrower's FIRED signals. Only what fired, each with the
 * observed value, its unit and the period it was observed in.
 */
export function entitySignals(params: {
  domain: DomainId;
  entity: string;
  period?: string;
}): Promise<EntitySignals> {
  return wsGet<EntitySignals>(`/canonical/entity-signals?${query(params)}`);
}

/**
 * Saved actions: this person's pins and saved searches, and the pack.
 *
 * A pin and a saved search carry the release, fingerprint and period they
 * were made in. `same_release` is the server's answer to "is this still the
 * book in use", and `disclosure` is the sentence the screen shows when it is
 * not: a pin is never silently rebound to today's numbers.
 */
export interface SavedPin {
  object_id: string;
  version: number;
  owner_id: string;
  label: string;
  note: string;
  domain_id: DomainId;
  release_id: string;
  fingerprint: string;
  period: string;
  owner_grain: string;
  /** The pinned row as it read THEN. Never presented as current. */
  as_pinned: Record<string, string | number | null>;
  created_at: number;
  release_in_use: string;
  same_release: boolean;
  disclosure: string;
}

export interface SavedSearchQuery {
  filters: { column: string; op: string; value?: unknown; values?: unknown[] }[];
  search: string;
  sort: string;
  desc: boolean;
}

export interface SavedSearch {
  object_id: string;
  version: number;
  name: string;
  domain_id: DomainId;
  release_id: string;
  fingerprint: string;
  period: string;
  query: SavedSearchQuery;
  filters: SavedSearchQuery["filters"];
  matched_when_saved: { owners: number; exposures: number; ead_sar_mn: number; ecl_sar_mn: number; basis: string };
  created_at: number;
  release_in_use: string;
  same_release: boolean;
  disclosure: string;
}

export interface WorkingSet extends Identity {
  version: string;
  pins: SavedPin[];
  searches: SavedSearch[];
  maximum_per_kind: number;
  /** Releases held in the working set that are not the one in use. */
  other_releases: string[];
  note: string;
}

export function workingSet(params: {
  domain: DomainId;
  period?: string;
  release?: string;
}): Promise<WorkingSet> {
  return wsGet<WorkingSet>(`/canonical/working-set?${query(params)}`);
}

export function addPin(body: {
  domain: DomainId;
  owner_id: string;
  period?: string;
  release?: string;
  note?: string;
}): Promise<SavedPin> {
  return wsSend<SavedPin>("/canonical/pins", body);
}

export function dropPin(domain: DomainId, objectId: string): Promise<SavedPin> {
  return wsSend<SavedPin>(
    `/canonical/pins/${encodeURIComponent(objectId)}?domain=${domain}`,
    undefined,
    "DELETE",
  );
}

export function saveSearch(body: {
  domain: DomainId;
  name: string;
  period?: string;
  filters?: SavedSearchQuery["filters"];
  search?: string;
  sort?: string;
  desc?: boolean;
}): Promise<SavedSearch> {
  return wsSend<SavedSearch>("/canonical/searches", body);
}

export function dropSearch(domain: DomainId, objectId: string): Promise<SavedSearch> {
  return wsSend<SavedSearch>(
    `/canonical/searches/${encodeURIComponent(objectId)}?domain=${domain}`,
    undefined,
    "DELETE",
  );
}

/**
 * Download one owner's canonical pack, and report what was downloaded.
 *
 * The sha256 the server computed over the bytes comes back in a header; it is
 * returned here so the screen can state it beside the filename. The same
 * owner, period and release produce the same bytes, so that digest is a
 * checkable statement rather than decoration.
 */
export async function downloadPack(params: {
  domain: DomainId;
  owner_id: string;
  period?: string;
  release?: string;
}): Promise<{ filename: string; sha256: string; release_id: string; period: string }> {
  const response = await fetch(workspaceUrl(`/canonical/pack?${query(params)}`), {
    credentials: "include",
  });
  if (!response.ok) {
    let detail: unknown = await response.text();
    try {
      detail = JSON.parse(detail as string);
    } catch {
      /* not JSON; the text is the detail */
    }
    throw new WorkspaceError(response.status, detail);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const named = /filename="([^"]+)"/.exec(disposition)?.[1];
  const filename =
    named ?? `canonical-pack-${params.domain}-${params.owner_id}.csv`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  return {
    filename,
    sha256: response.headers.get("X-Canonical-Pack-Sha256") ?? "",
    release_id: response.headers.get("X-Canonical-Release-Id") ?? "",
    period: response.headers.get("X-Canonical-Period") ?? "",
  };
}

/**
 * What data this runtime holds, read from the published release manifests.
 *
 * Data Builder's own overview is served by the main backend, which an
 * isolated V4 runtime does not start, so the generic request guard refuses
 * that path before it is sent. This is the same question answered from the
 * authority that IS present here. Read-only: it publishes nothing.
 */
export interface CatalogueRelation {
  relation: string;
  grain: string;
  description: string;
  period_column: string;
  key_columns: string[];
  columns: number;
  row_count: number | null;
  row_count_source: string;
  row_count_unavailable: string;
  readable: boolean;
}

export interface CatalogueDomain {
  domain_id: DomainId;
  domain_label: string;
  published: boolean;
  status: string;
  reason: string;
  provision_command?: string;
  release_id?: string;
  release_fingerprint?: string;
  tenant_id?: string;
  tenants_in_release?: string[];
  data_version?: string;
  origin?: string;
  not_client_data?: string;
  reporting_currency?: string;
  amount_scale?: string;
  reporting_frequency?: string;
  periods: string[];
  latest_period?: string;
  entity_counts: Record<string, number>;
  entity_counts_basis?: string;
  relations: CatalogueRelation[];
  relation_count?: number;
  row_count: number;
  joins: { left: string; right: string; on: string[]; cardinality: string; warning: string }[];
  lake_root?: string;
  unavailable_metadata: Record<string, string>;
}

export interface Catalogue {
  version: string;
  tenant_id: string;
  source: string;
  domains: CatalogueDomain[];
  domains_published: number;
  domains_total: number;
  row_count: number;
  unavailable_metadata: Record<string, string>;
  limitation: string;
}

export function runtimeCatalogue(): Promise<Catalogue> {
  return wsGet<Catalogue>("/canonical/catalogue");
}
