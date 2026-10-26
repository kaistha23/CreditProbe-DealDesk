/** PLAN_R6 B4: morning before 12:00, afternoon 12:00–17:00, evening from 17:00, by the viewer's clock. */
export function salutationFor(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

/** The presenter's "Showing to" name when set, else the signed-in user's first name. */
export function greetingName(presenter: string, fullName: string): string {
  const p = (presenter ?? "").trim();
  if (p) return p;
  return (fullName ?? "").trim().split(/\s+/)[0] ?? "";
}
