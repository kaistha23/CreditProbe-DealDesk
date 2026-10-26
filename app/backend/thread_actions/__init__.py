"""R16 t (M7): the shared thread actions on every answer in every module.

    intent.py     "write a memo / note / paper" in any thread -> a Word document (deterministic rule, no model)
    doc.py        the one answer document every module hands over (turns, blocks, sources) and its validation
    trace.py      Trace: sources, queries, relations and rows of an answer or a thread, in plain words
    memo.py       Word: the house-style memo of one answer or a whole thread (deterministic writer)
    relations.py  Data Domains relations ta_memo and ta_action (registered in backend/dealdesk/data/schema.py)
    store.py      where memos and the action log are kept (var/thread_actions + the two relations)
    api.py        /api/v1/thread-actions on the Core service (port 8505)

The frontend twin is frontend/src/lib/v5/thread-actions.ts (same intent rule, same document shape) and the bar
frontend/src/components/v5/thread/action-bar.tsx mounted on every answer.
"""
