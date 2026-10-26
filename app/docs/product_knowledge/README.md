# CreditProbe product knowledge base

One file per module. Each file has the same parts, which `backend/ai_work/knowledge.py` reads:

- a header block: `id`, `name`, `screen` (the link that opens the module), `keywords`, `example` (the key of the worked example computed on the real books);
- **What it is**: one paragraph;
- **Flow**: the process step by step, each step with the link that opens its screen;
- **Good to know**: rules and limits a user should know.

The worked example is not written here: it is computed from the current books (`backend/ai_work/knowledge.py`, `worked_example`) each time the pack is built (`ops/build_product_knowledge.py`), so every figure in it is the books' figure at the as-of date. The Cockpit reads the pack through its product-help path (registered exception FX-A4); Playbook, Projects and Cockpit help answers quote it.
