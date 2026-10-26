/**
 * R16 m (M3): chat-box placeholders are short. One rule for every ask/chat box:
 * at most 60 characters and at most one example; longer examples are starter chips.
 */

export const PLACEHOLDER_MAX = 60;

/** The What-If landing box, per book ("Corporate" / "Retail"); a generic line before the book loads. */
export function whatIfPlaceholder(book?: string): string {
  return book ? `Ask about the ${book.toLowerCase()} book, e.g. “LGD +5pp”` : "Ask about the book, or describe a scenario";
}

/** The What-If landing chips: the book's starters plus the example that used to sit in the box. */
export function whatIfStarterChips(examples: string[] | undefined): string[] {
  const chips = (examples ?? []).slice(0, 4);
  return chips.some((c) => c.toLowerCase() === "reduce collateral by 20%") ? chips : [...chips, "reduce collateral by 20%"];
}

/** True when a placeholder follows the rule: ≤ 60 characters and at most one quoted example. */
export function placeholderOk(text: string): boolean {
  return text.length <= PLACEHOLDER_MAX && (text.match(/“/g) ?? []).length <= 1;
}
