# UAT sweep: 18/18 steps passed, 212 checks

UI http://127.0.0.1:5500 · API http://127.0.0.1:8501 · 2026-10-11T17:52:03.519071+00:00 · 75 s

| # | Book | UAT step | Step | Checks | Errors | Result |
|---|---|---|---|---|---|---|
| 1 | both | R2-1 | Sign-in: nobody signed in is sent to /login and brought back; a wrong password is refused | 10/10 | 0 | PASS |
| 2 | both | R2-1 | Persona anne: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 3 | both | R2-1 | Persona faisal.alqahtani: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 4 | both | R2-1 | Persona noura.alharbi: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 5 | both | R2-1 | Persona khalid.alotaibi: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 6 | both | R2-1 | Persona reem.alshehri: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 7 | both | R2-1 | Persona abdullah.alzahrani: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 8 | both | R2-1 | Persona sara.aldosari: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 9 | both | R2-1 | Persona omar.alghamdi: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 10 | both | R2-1 | Persona lama.almutairi: header, books, Mail badge, workspace figures equal the API | 8/8 | 0 | PASS |
| 11 | both | R2-1 | Administrator: View as Sara shows her mailbox and workspace, read only; back to Administrator | 8/8 | 0 | PASS |
| 12 | both | R2-5 | Mail (Khalid): folders, counts, search, unread filter and labels equal the API | 12/12 | 0 | PASS |
| 13 | both | R2-5 | Mail (Khalid): open each conversation: messages, attachments, in-place objects, read state | 57/57 | 0 | PASS |
| 14 | both | R2-5 | Mail (Khalid): mark unread, star, archive, label, unarchive: counts follow | 8/8 | 0 | PASS |
| 15 | both | R2-5 | Mail: Sara writes to Omar (cc Reem) with bold text, a file and a borrower attached; it arrives | 14/14 | 0 | PASS |
| 16 | both | R2-5 | Mail: Omar sees it unread, downloads the file, opens the borrower in place, replies; Reem replies all; Sara forwards | 12/12 | 0 | PASS |
| 17 | both | R2-5 | Mail: drafts: save, find under Drafts, reopen, send; a closed unsaved message is kept as a draft | 7/7 | 0 | PASS |
| 18 | both | R2-5 | Administrator: every mailbox, open one read only, audit log filters, a user cannot reach it | 12/12 | 0 | PASS |
