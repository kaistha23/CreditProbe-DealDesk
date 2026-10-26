# UAT sweep: 12/12 steps passed, 153 checks

UI http://127.0.0.1:5500 · API http://127.0.0.1:8501 · 2026-10-11T17:54:27.392713+00:00 · 85 s

| # | Book | UAT step | Step | Checks | Errors | Result |
|---|---|---|---|---|---|---|
| 1 | both | R3-3 | Mail (Khalid): three panes; folders, coloured labels and unread counts; list fields equal the API | 29/29 | 0 | PASS |
| 2 | both | R3-3 | Mail (Khalid): star from the list; select, select all; bulk archive, move to Inbox, read, unread, star, label, move to label | 15/15 | 0 | PASS |
| 3 | both | R3-3 | Mail (Khalid): a new label with its colour; applied from the conversation; listed and counted | 5/5 | 0 | PASS |
| 4 | both | R3-3 | Mail (Khalid): search with each filter (from, to, has attachment, label, date range) equals the server's search | 16/16 | 0 | PASS |
| 5 | both | R3-3 | Mail (Sara): To/Cc/Bcc from the directory, rich text, a file and objects; the draft saves itself and is in Drafts | 15/15 | 0 | PASS |
| 6 | both | R3-3 | Mail (Sara): send the draft; Bcc stays private; it lands in Sent and the recipients' Inboxes | 11/11 | 0 | PASS |
| 7 | both | R3-3 | Mail (Sara): Discard deletes an auto-saved draft | 4/4 | 0 | PASS |
| 8 | both | R3-3 | Mail: Omar replies all (never to the Bcc), Reem replies, Sara forwards; each lands in the right mailboxes; quoted text folds | 14/14 | 0 | PASS |
| 9 | both | R3-3 | Mail (Khalid): an object card opens in place; Close, Escape, Open full page and Back return; seeded quoted text | 14/14 | 0 | PASS |
| 10 | both | R3-3 | Notifications: new mail raises the bell, the Mail badge and the Inbox count, and shows a toast that opens it | 9/9 | 0 | PASS |
| 11 | both | R3-3 | Administrator: all mailboxes and the audit log inside the three-pane layout; Back paths | 16/16 | 0 | PASS |
| 12 | both | R3-3 | View as Khalid: his mail, filters work, and nothing can be changed | 5/5 | 0 | PASS |
