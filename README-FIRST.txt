CREDITPROBE AI - DEAL DESK EDITION
==================================

CreditProbe Deal Desk reads a customer's credit file (Word, PDF, Excel, photos and scans), checks it against
the bank's checklist and policy, and drafts the RM's business request and the credit proposal, with every
figure traced back to the document it came from. Everything runs on your own computer; the sample bank data
inside is fictional.


WHAT YOU NEED
-------------
- Windows 10/11 or a Mac (Apple Silicon or Intel), 16 GB RAM recommended, 15 GB free disk space.
- Docker Desktop (free): https://www.docker.com/products/docker-desktop/
  After installing, open Docker Desktop once and wait until it says "Engine running".
  In Docker Desktop > Settings > Resources, give it at least 6 GB of memory if that setting is shown.
- Optional: your own Anthropic API key (starts with sk-ant-). Without a key the app still runs: it reads the
  documents (OCR included), runs the checklist and writes a rule-based business request. The AI drafting and
  the Noor chat need the key.


START ON WINDOWS
----------------
1. Unzip this folder somewhere simple, e.g. C:\CreditProbe-DealDesk  (not inside OneDrive if you can avoid it).
2. Double-click  Start-Windows.bat
   - First run only: Notepad opens settings.env. Paste your API key after ANTHROPIC_API_KEY= , save, close.
   - First run builds the app: 10-20 minutes, then 3-10 minutes to prepare the data. Later starts: about 1 minute.
3. The browser opens http://127.0.0.1:6600 when it is ready.
   If Windows shows "Windows protected your PC", click More info > Run anyway.
To stop: double-click Stop-Windows.bat. Your uploads and work are kept for next time.


START ON A MAC
--------------
1. Unzip this folder (e.g. into Documents).
2. The first time only: right-click  Start-Mac.command > Open > Open  (macOS asks because it was downloaded).
   After that, a double-click is enough.
   - First run only: TextEdit opens settings.env. Paste your API key after ANTHROPIC_API_KEY= , save, close,
     then press Return in the Terminal window.
   - First run builds the app: 10-20 minutes, then 3-10 minutes to prepare the data.
3. The browser opens http://127.0.0.1:6600 when it is ready.
To stop: Stop-Mac.command.
(No Docker? Start-Mac.command can also run the app directly if Python 3.12 and Node.js 22 are installed:
 brew install python@3.12 node@22.)


SIGN IN  (password = user name)
-------
  nawaf.alotaibi    Relationship Manager      - upload a customer file, write the business request
  sara.aldosari     Credit Analyst            - review, prepare the credit proposal
  noura.alharbi     Head of Credit
  anne              Administrator


TRY A CUSTOMER CASE
-------------------
The folder "Customer cases" (next to this one) has one sub-folder per customer. Each holds the full credit
file as an RM would receive it, and a file "00 Ask and RM notes.txt".

1. Sign in as nawaf.alotaibi and open Deal Desk (left menu).
2. Click "New proposal" > "Customer documents".
3. Drag in all the files of one customer folder (or click and select them all; a ZIP of the folder works too).
   You do not need to upload the 00 file.
4. Open "00 Ask and RM notes.txt": paste THE ASK into "The ask" and the RM NOTES into "RM notes".
5. Click Run. CreditProbe reads and classifies each document (photos and scans through OCR), checks the file
   against the checklist, lists what is missing or expired, and drafts the business request with sources.
6. Then try "Business request" on the Deal Desk page, and "Prepare the credit proposal" with Noor beside it
   (Noor needs the API key).

Some cases have deliberately blurred or skewed photos to test how the reader copes with poor scans.


IF SOMETHING GOES WRONG
-----------------------
- "port is already allocated": another program uses port 6600 or 8500-8517. Close it and start again.
- The page does not load after 20 minutes: run Stop, then Start again. On Windows/Mac you can see what it is
  doing in Docker Desktop > Containers > creditprobe-dealdesk > Logs.
- To start completely fresh (deletes your uploads in the app): Docker Desktop > Volumes > delete
  creditprobe-dealdesk_dealdesk-data, then Start again.
