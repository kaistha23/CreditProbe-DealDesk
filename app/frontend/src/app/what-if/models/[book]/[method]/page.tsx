"use client";

import { useParams } from "next/navigation";
import * as React from "react";

import { useWideContent } from "@/components/layout/content-width";
import { WhatIfModelCard } from "@/components/v5/whatif/model-card";

export default function WhatIfModelCardPage() {
  const params = useParams<{ book: string; method: string }>();
  useWideContent();
  const book = params?.book === "retail" ? "retail" : "corporate";
  const method = params?.method === "xgboost" ? "xgboost" : "delta";
  return <WhatIfModelCard book={book} method={method} />;
}
