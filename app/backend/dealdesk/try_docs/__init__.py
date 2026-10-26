"""R12 Session T (I18): "Try it on your documents".

A participant drops a credit proposal (PDF, Word or a scan; English or Arabic) and their credit policy. CreditProbe then
runs live, step by step, in a demo session that is wiped when the participant leaves:

  1. learn the policy        what it sets (found) and what it leaves to CreditProbe defaults (missing), kept as a
                             demo-only version unless a checker approves it (then it becomes a normal P6 proposal);
  2. extract the proposal    into a Deal Desk deal (demo scope), published to Data Domains under the demo scope;
  3. review                  against THEIR policy clauses (Session B's review when merged, else the R11 review);
  4. counter-proposal and committee paper (Session F's paper when merged, else the R11 committee sheet);
  5. draft                   the credit memo in the language of their proposal (English or Arabic).

Safeguards: runs on the laptop (127.0.0.1); a confidentiality notice; every file and row of the session is removed
on exit (`session.wipe`) and by a time-to-live sweep; a no-model (deterministic) mode that makes no external call.
Each step is timed and the total shown.
"""
