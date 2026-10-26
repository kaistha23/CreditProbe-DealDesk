"""Re-derive the committed house-style profile from the corpus:

    python -m backend.dealdesk.house_style.build

writes data/dealdesk/house_style/profile.json (every group's readable profile), style_guide.md (the guide for the main
groups) and validation.json (the held-out tests). Run it again when an exemplar is added to exemplars/.
"""
from __future__ import annotations

import json
import os
import tempfile

from backend.dealdesk import paths


def main() -> None:
    os.environ.setdefault("DEALDESK_VAR", tempfile.mkdtemp(prefix="house-style-build-"))
    paths.VAR = paths._path("DEALDESK_VAR", paths.VAR)  # noqa: SLF001 - never write learning events of a build
    from backend.dealdesk.house_style import corpus, profile as prof, service, store
    store.reset()
    out = paths.DATA / "house_style"
    out.mkdir(parents=True, exist_ok=True)
    docs = corpus.load(include_uploads=False)
    st = prof.build(docs)
    views = {k: prof.view(st, group=k) for k, g in sorted(st["groups"].items()) if g.get("nb", 0) >= 1}
    (out / "profile.json").write_text(json.dumps({"corpus": [{"doc_id": d["doc_id"], "source": d["source"], "bank": d["bank"],
                                                              "kind": d["kind"], "segment": d["segment"], "role": prof.role_of(d),
                                                              "weight": d["weight"], "primary": d.get("primary", False)} for d in docs],
                                                  "fingerprint": corpus.fingerprint(), "groups": views}, indent=1, sort_keys=True) + "\n")
    main_groups = [prof.pick_group(st, "house-uae", "increase", "contractor"), prof.pick_group(st, "house-uae", "renewal", "trader"),
                   prof.pick_group(st, "house-ksa", "new", "contractor"), "house-ksa|*|*"]
    guide = ["# CreditProbe house style guide", "",
             "Derived by `python -m backend.dealdesk.house_style.build` from every proposal in the corpus "
             f"({len(docs)} documents). The profile updates incrementally in the app as proposals are uploaded and as RMs edit drafts.", ""]
    for g in dict.fromkeys(main_groups):
        guide += [prof.guide(views.get(g) or prof.view(st, group=g)).replace("# House style:", "## House style:").replace("\n## ", "\n### "), ""]
    (out / "style_guide.md").write_text("\n".join(guide))
    val = {"document_held_out": service.held_out("DD-05"),
           "section_held_out": [service.held_out_sections("PRP-A-GMC"), service.held_out_sections("PRP-B-ASB")]}
    (out / "validation.json").write_text(json.dumps(val, indent=1) + "\n")
    print(f"profile.json: {len(views)} groups; style_guide.md; validation.json "
          f"(held-out within band: {val['document_held_out']['within_band']} / {[x['within_band'] for x in val['section_held_out']]})")


if __name__ == "__main__":
    main()
