"""v5 Workspace (Phase F): My workspace / Inbox, Messages, Projects,
Investigations, Analyses and Documents.

A small service of its own (`backend.workspace_v5.api:app`, port 8505) with its
own sqlite store, seeded on first start with Demo content tied to the v5 books.
It never imports the frozen Cockpit (`backend.cockpit_v4`) or `backend.spine`.
"""
