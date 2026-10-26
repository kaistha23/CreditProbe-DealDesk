id: admin_ai_studio
name: AI Studio
screen: /ai-studio
keywords: ai studio, system instructions, house tone, glossary, guardrails, test bench, model configuration
example: admin_studio

## What it is
AI Studio configures each module's assistant (What-If, Playbook, Deal Desk, Lenses, Scorecard, Projects): the model (Opus or Sonnet), system instructions and house tone, the glossary of bank terms, knowledge sources (Policy Docs packs), the tools it may call, guardrails (no untraced figure, refuse out-of-scope questions) and answer style. The Cockpit's configuration is shown read-only: it is frozen.

## Flow
1. [Open AI Studio](/ai-studio) and pick a module.
2. Change the configuration: it becomes a draft.
3. In the Test bench, ask a question: the live configuration and the draft answer side by side (the instructions the model receives, the tools it plans, a refusal if a guardrail applies).
4. Submit the draft for approval; once approved it is live.
