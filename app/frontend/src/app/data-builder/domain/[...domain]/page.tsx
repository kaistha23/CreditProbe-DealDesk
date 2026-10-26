import { redirect } from "next/navigation";

/**
 * v5: the legacy Data Builder screens (catalogue estate, inbox, dataset
 * editor, relationship map) called a backend v5 does not run. Browsing the
 * data now lives on one screen, /data-builder, on the Data Builder service;
 * an old link lands there rather than on an error.
 */
export default function LegacyDataBuilderRoute() {
  redirect("/data-builder");
}
