/** R14 m (K12): the current-regime block every scenario answer opens with (backend/scenarios/regime.py `block`). */
export interface RegimeBlock {
  type: "regime";
  title: string;
  label: string;
  regime: string;
  as_of: string;
  lines: string[];
  vintage: string;
  tiles: { label: string; value: string; sub?: string }[];
  relations: string[];
  compact?: boolean;
  revenue?: Record<string, unknown> | null;
}

export const HIGH_OIL_REGIMES = new Set(["supply_shock_high_oil", "high_oil_rising", "high_oil"]);
