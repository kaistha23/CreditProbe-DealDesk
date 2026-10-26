"use client";

/** The old hand-built CRO Lens is now the "CRO portfolio" template: this address opens a lens from it. */

import { useRouter } from "next/navigation";
import * as React from "react";

import { lenses } from "@/lib/v5/lenses";
import { friendlyMessage } from "@/lib/v5/errors";

export default function CroLensPage() {
  const router = useRouter();
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    lenses.list("corporate").then((l) => {
      const t = l.templates.find((c) => c.template_key === "cro-portfolio");
      if (!live) return;
      if (t) return lenses.create({ template: t.lens_id }).then((o) => router.replace(`/lenses/${o.lens.lens_id}`));
      router.replace("/lenses");
    }).catch((e: unknown) => { if (live) setError(friendlyMessage(e)); });
    return () => { live = false; };
  }, [router]);
  return error ? <p className="text-sm text-negative" role="alert">{error}</p> : <p className="text-sm text-text-muted">Opening the CRO portfolio lens…</p>;
}
