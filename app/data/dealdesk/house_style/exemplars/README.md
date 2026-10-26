# House-style exemplars

Anonymised proposals that teach the drafter the bank's own language (PLAN_R11 P4). Every bank, client, staff, developer and
project name is replaced by a fictional one; no real name is ever committed.

- Formats: `.docx` (headings by Word style), `.md` or `.txt` (`#` headings or numbered heading lines).
- Optional sidecar `<same name>.json`: `{"bank": "house-uae", "kind": "increase", "segment": "contractor", "voice": "business",
  "weight": 5, "primary": true}`. Without one an exemplar is a UAE business-unit proposal, weight 5, primary for its segment
  (so a contractor exemplar leads the contractor profile).
- After adding one, run `python -m backend.dealdesk.house_style.build` to refresh `profile.json`, `style_guide.md` and
  `validation.json`. The running app picks it up on its own (the corpus fingerprint changes).

## R12 primary exemplars (PLAN_R12 F, N7)

- `twin_a_al_sahel_renewal.md`: Al Sahel Building Materials Group, a trading group renewal (fictional).
- `twin_b_gulf_meridian_new_project.md`: Gulf Meridian Contracting, a new project limit for Saadiyat Crest Developments (fictional).

Both are rebuilt section by section on the 20-section anatomy in `docs/v5/house_style/PROPOSAL_ANATOMY.md` and written by the
bank-form writers (`backend/dealdesk/house_style/bankform`); `bankform.coverage.check_headings` passes on both. They are the
primary profile for the UAE house's renewal/trader and new/contractor groups.
