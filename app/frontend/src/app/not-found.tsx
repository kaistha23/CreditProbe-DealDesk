import Link from "next/link";

import { Button } from "@/components/ui/button";
import { BackButton } from "@/components/v5/core/back-button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function NotFound() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Page not found</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-text-secondary">
          That address does not exist in CreditProbe.
        </p>
        <div className="flex gap-2">
          <BackButton fallback={{ href: "/", label: "Cockpit" }} testId="not-found-back" />
          <Button asChild variant="outline" size="sm">
            <Link href="/">Go to the Cockpit</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
