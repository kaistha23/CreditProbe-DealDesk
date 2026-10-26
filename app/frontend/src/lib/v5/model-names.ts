/**
 * Model names shown in the UI (PLAN_R6 B6). A vendor model name (its family or its ID) is never shown: the main
 * model is "LLM model 1.1" and the second model is "LLM model 1.2". The real IDs live in the Admin config
 * (Settings, "LLM model names", seeded from backend/admin/seed.py MODEL_NAMES); this table mirrors it.
 */

/** Display name -> real model ID, in the order shown. */
export const MODEL_NAMES: readonly { display: string; id: string }[] = [
  { display: "LLM model 1.1", id: "claude-opus-5" },
  { display: "LLM model 1.2", id: "claude-sonnet-5" },
];

export const MAIN_MODEL = MODEL_NAMES[0].display;
export const SECOND_MODEL = MODEL_NAMES[1].display;

const VENDOR = /\b(claude|anthropic|opus|sonnet|haiku|gpt|openai|gemini|llama)/i;

/** True when the text carries a vendor model or provider name. */
export function hasVendorName(text: string | null | undefined): boolean {
  return VENDOR.test(String(text ?? ""));
}

/**
 * The display name of a model ID. A known ID maps through the table (an Admin mapping may be passed to override it);
 * an unknown vendor ID maps by family (Opus-class to 1.1, Sonnet-class to 1.2, anything else to "LLM model");
 * a text with no vendor name (e.g. "planner (kill switch on)") is returned unchanged.
 */
export function modelDisplayName(id: string | null | undefined, mapping?: Record<string, string>): string {
  const raw = String(id ?? "").trim();
  if (!raw) return "";
  if (mapping) {
    const hit = Object.entries(mapping).find(([, v]) => String(v).toLowerCase() === raw.toLowerCase());
    if (hit) return hit[0];
  }
  const known = MODEL_NAMES.find((m) => m.id.toLowerCase() === raw.toLowerCase() || m.display.toLowerCase() === raw.toLowerCase());
  if (known) return known.display;
  if (/opus/i.test(raw)) return MAIN_MODEL;
  if (/sonnet/i.test(raw)) return SECOND_MODEL;
  if (VENDOR.test(raw)) return "LLM model";
  return raw;
}
