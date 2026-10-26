import { redirect } from "next/navigation";

/**
 * The legacy saved-investigation route called the pre-v5 backend, which v5 does
 * not run. Old links land on the v5 Investigations list instead of an error.
 */
export default function LegacySavedInvestigation() {
  redirect("/investigations");
}
