"use client";

/** One lens at its own URL (/lenses/<id>?period=&panel=). The id is in the path. */

import { useParams } from "next/navigation";
import * as React from "react";

import { useWideContent } from "@/components/layout/content-width";
import { LensView } from "@/components/v5/lenses/lens-view";
import { threadViewKey } from "@/lib/v5/thread-rule";

export default function LensPage() {
  const params = useParams<{ lensId: string }>();
  useWideContent();
  const lensId = String(params?.lensId ?? "");
  if (!lensId) return null;
  return (
    <React.Suspense fallback={<p className="text-sm text-text-muted">Opening the lens…</p>}>
      <LensView key={threadViewKey("lenses", lensId)} lensId={lensId} />
    </React.Suspense>
  );
}
