/** The tour script from the Deal Desk service (`/api/v1/tour`, backend/agents_v5/tour/api.py), with the session cookie. */
import { dealdeskOrigin } from "@/lib/v5/dealdesk";

import type { TourLang, TourScript } from "./tour-model";

export async function fetchTour(lang: TourLang): Promise<TourScript> {
  const res = await fetch(`${dealdeskOrigin()}/api/v1/tour/script?lang=${lang}`, {
    credentials: "include", cache: "no-store",
  });
  if (!res.ok) throw new Error(`tour ${res.status}`);
  return (await res.json()) as TourScript;
}
