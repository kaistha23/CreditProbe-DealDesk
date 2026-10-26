import * as React from "react";

import { MailApp } from "@/components/v5/mail/mail-app";
import { Loading } from "@/components/v5/workspace/parts";

/** CreditProbe Mail: folders, conversations, compose, attachments, labels, and (Administrator) every mailbox. */
export default function MessagesPage() {
  return (
    <React.Suspense fallback={<Loading what="Opening Mail…" />}>
      <MailApp />
    </React.Suspense>
  );
}
