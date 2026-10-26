id: admin_agent_operations
name: Agent Operations
screen: /agent-operations
keywords: agent operations, ai runs, ai run log, kill switch, evaluation suite, refusals, latency
example: admin_agent_ops

## What it is
Agent Operations is the live log of every AI run in every module: user, module, question, the process steps with their timings, tools called, tokens, cost, latency, outcome, and the figures the validator checked or removed. It has a failure and refusal queue, daily charts (runs, latency p50 and p95, cost, refusal rate by module), an evaluation suite per module and a kill switch per module.

## Flow
1. [Open Agent Operations](/agent-operations) and filter the live log by module, user, outcome or words.
2. Click a run to see its full trace: each step's time bar and the tools called.
3. Check Failures and refusals, and the Daily charts.
4. In Evaluations, press Run on a module: its scripted questions are answered and checked against the expected trace.
5. In Kill switches, switch a module's assistant to planner mode at once (it is audited).

## Good to know
- The kill switch applies immediately, without a checker, because it is an emergency control; turning it back on is also audited.
