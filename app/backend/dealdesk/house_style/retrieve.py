"""P2: the 2-3 nearest exemplar sections (same memo type, sector and section) by TF-IDF cosine, pure Python.

Similarity is computed on the section's style tokens (names as '@', figures as '#'), so a match is a match of wording,
not of client. Boosts: same section key (required when one exists), same segment +0.15, same kind +0.05, same bank +0.10,
a primary exemplar +0.25 (Anne's contractor proposal leads for contractor memos).
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from backend.dealdesk.house_style import profile


def _terms(text: str) -> Counter:
    toks = profile._tok(text)
    return Counter(toks + [" ".join(toks[i:i + 2]) for i in range(len(toks) - 1)])


class Index:
    def __init__(self, docs: list[dict[str, Any]]):
        self.rows: list[dict[str, Any]] = []
        for d in docs:
            for s in d["sections"]:
                if s["key"] == "preamble":
                    continue
                text = "\n".join(s.get("paragraphs", []) + s.get("bullets", []))
                if not text.strip():
                    continue
                self.rows.append({"doc_id": d["doc_id"], "bank": d["bank"], "kind": d["kind"], "segment": d["segment"],
                                  "primary": d.get("primary", False), "source": d["source"], "key": s["key"], "heading": s["heading"],
                                  "voice": s.get("voice", "business"), "text": text, "tf": _terms(s["heading"] + " " + text)})
        df: Counter = Counter()
        for r in self.rows:
            df.update(set(r["tf"]))
        n = max(1, len(self.rows))
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        for r in self.rows:
            r["vec"] = self._vec(r["tf"])

    def _vec(self, tf: Counter) -> dict[str, float]:
        v = {t: c * self.idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def nearest(self, key: str, query: str, bank: str, kind: str, segment: str, k: int = 3,
                exclude: set[str] | None = None) -> list[dict[str, Any]]:
        q = self._vec(_terms(query))
        pool = [r for r in self.rows if r["key"] == key and r["doc_id"] not in (exclude or set())]
        if not pool:
            return []
        out = []
        for r in pool:
            cos = sum(q.get(t, 0.0) * x for t, x in r["vec"].items())
            boost = (0.15 if r["segment"] == segment else 0) + (0.05 if r["kind"] == kind else 0) + (0.10 if r["bank"] == bank else 0) \
                + (0.25 if r["primary"] and r["segment"] == segment else 0)
            out.append((round(cos + boost, 4), round(cos, 4), r))
        out.sort(key=lambda x: (-x[0], x[2]["doc_id"]))
        return [{"doc_id": r["doc_id"], "heading": r["heading"], "similarity": cos, "score": sc, "primary": r["primary"],
                 "bank": r["bank"], "segment": r["segment"], "voice": r["voice"], "text": r["text"][:1200]}
                for sc, cos, r in out[:k]]
