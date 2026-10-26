id: threads
name: Threads and the process trace
screen: /what-if?domain=corporate
keywords: thread, process trace, timer, how do I ask, ask a question, chat box, conversation, execute scenario, create report, add to section, optimise
example: none

## What it is
Every module that answers a question (Cockpit, What-If, Scorecard Validation, Playbook, Projects, Deal Desk, Lenses, Admin) uses the same thread: the conversation scrolls in the middle, the chat box is pinned at the bottom with the module's main action beside Send (Execute scenario, Create report, Add to section, Optimise), and every answer shows the Cockpit's process trace. The trace lists the steps as they happen, Understand, Plan, Query, Answer, Validate and Publish, each with its elapsed time, and a running timer while the answer is being worked on. Once done it collapses to "Answered in 4.2s"; open it to see every step.

## Flow
1. Ask from the module's home, for example [What-If](/what-if?domain=corporate), [Scorecard Validation](/scorecard-validation) or [Playbook](/playbook): a thread opens at once.
2. Watch the process trace: the step that is running counts up every second; a step appears only when it starts.
3. Read the answer: tables render as tables, charts as charts, and the queries behind it sit behind the (i) under the answer.
4. Ask a follow-up, pick a chip above the chat box, or press the main action beside Send.
5. Reopen the thread later from its address: every answer keeps its trace with the measured times.

## Good to know
- A message can hold several questions and a request at once; each question gets its own answer part.
- Every figure in an answer comes from a real query on the module's own data; numbers follow one format (SAR m or bn, percentages with one or two decimals, bps as whole numbers).
- Nothing changes until you press the action (Execute scenario, Create report, Add to section).
