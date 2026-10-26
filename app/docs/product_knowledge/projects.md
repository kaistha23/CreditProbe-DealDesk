id: projects
name: Projects
screen: /projects
keywords: projects, project, project thread, workspace project
example: projects_retail

## What it is
A project is a workspace for one piece of work, like a project in Claude: a name and description, documents, instructions, the data domains it may use (Cockpit books, Early Warning, What-If, Bureau, Open Banking, Scorecard) and its members. Threads inside a project answer only from its domains, documents and instructions, through the same conversational architecture as the Cockpit.

## Flow
1. [Open Projects](/projects) and open a project, or create one with a name and description.
2. Set its scope under Access: the data domains, the instructions ("answer for the retail book at 2026-08 and compare with the month before") and the members.
3. Upload documents (.docx, .pdf, text): answers cite them.
4. Start a thread and ask, for example "Give me a list of 5 high-alert Early Warning clients who are in Stage 1": the answer comes back as a table with IDs, band, score, EAD and reasons.
5. A question outside the project's domains is refused, naming the scope; "Ask the Cockpit with this project's context" opens a Cockpit thread with the project's context.

## Good to know
- Members see the project; outsiders do not see it, its documents or its threads.
