import * as React from "react";

import { LoginForm } from "@/components/v5/core/login";

/** Sign in. Everything else redirects here when nobody is signed in. */
export default function LoginPage() {
  return (
    <React.Suspense fallback={<div className="min-h-dvh bg-canvas" />}>
      <LoginForm />
    </React.Suspense>
  );
}
