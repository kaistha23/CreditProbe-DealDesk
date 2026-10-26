import { redirect } from "next/navigation";

/**
 * PLAN_R12 I7: "Portfolio RAROC at origination" is now the Book's RAROC drift view. An old link or bookmark lands
 * there rather than on an error.
 */
export default function PortfolioRaroc() {
  redirect("/deal-desk/raroc-drift");
}
