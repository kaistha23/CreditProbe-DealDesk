"""Screen-level proof: Cockpit panels after the rescale differ only in scale.

Usage: python ops/compare_snapshots.py <before_dir> <after_dir> <factor> <out.json>

Walks every snapshot pair leaf by leaf. A leaf passes when it is
  * identical, or
  * a number equal to before x factor (relative 1e-9), or
  * a string identical once its numbers are masked, whose numbers are each
    either unchanged or the scaled value at the precision displayed.
Volatile fields (timings, cache flags, fingerprints, item ids derived from
them) are listed separately, never silently ignored.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

noise: list = []

VOLATILE = {"computed_ms", "cached", "release_fingerprint", "item_id", "fingerprint",
            "evidence_fingerprint"}
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def numbers(text):
    return [m.group(0) for m in NUMBER.finditer(text)]


def as_float(token):
    return float(token.replace(",", ""))


def number_matches(before_tok, after_tok, factor):
    b, a = as_float(before_tok), as_float(after_tok)
    if before_tok == after_tok:
        return "unchanged"
    decimals = len(after_tok.split(".")[1]) if "." in after_tok else 0
    if abs(a - b * factor) <= 0.5 * 10 ** (-decimals) + 1e-9 * abs(b * factor):
        return "scaled"
    return None


def compare(before, after, factor, path, tally, problems):
    if isinstance(before, dict) and isinstance(after, dict):
        if set(before) != set(after):
            problems.append({"path": path, "issue": "different keys",
                             "only_before": sorted(set(before) - set(after)),
                             "only_after": sorted(set(after) - set(before))})
        for key in sorted(set(before) & set(after)):
            if key in VOLATILE:
                tally["volatile:" + key] += 1
                continue
            compare(before[key], after[key], factor, f"{path}.{key}", tally, problems)
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            problems.append({"path": path, "issue": f"list length {len(before)} -> {len(after)}"})
        for i, (x, y) in enumerate(zip(before, after)):
            compare(x, y, factor, f"{path}[{i}]", tally, problems)
    elif isinstance(before, bool) or isinstance(after, bool) or before is None or after is None:
        tally["unchanged" if before == after else "PROBLEM"] += 1
        if before != after:
            problems.append({"path": path, "before": before, "after": after})
    elif isinstance(before, (int, float)) and isinstance(after, (int, float)):
        if before == after:
            tally["unchanged"] += 1
        elif abs(after - before * factor) <= 1e-9 * max(abs(before * factor), 1e-12):
            tally["scaled number"] += 1
        elif abs(after - before) <= 1e-9 * max(abs(before), 1e-12):
            # A ratio recomputed from scaled sums: equal to ~15 significant
            # digits. Counted, and listed in the report, never hidden.
            tally["unchanged ratio (float noise < 1e-9 relative)"] += 1
            noise.append({"path": path, "before": before, "after": after})
        elif abs(before) < 1e-6 and abs(after) < 1e-6:
            # A reconciliation residual: zero, to machine precision, both times.
            tally["zero residual (|x| < 1e-6 both)"] += 1
            noise.append({"path": path, "before": before, "after": after})
        else:
            problems.append({"path": path, "before": before, "after": after})
    elif isinstance(before, str) and isinstance(after, str):
        if before == after:
            tally["unchanged"] += 1
            return
        nb, na = numbers(before), numbers(after)
        if NUMBER.sub("#", before) != NUMBER.sub("#", after) or len(nb) != len(na):
            problems.append({"path": path, "before": before, "after": after})
            return
        verdicts = [number_matches(x, y, factor) for x, y in zip(nb, na)]
        if all(verdicts):
            tally["scaled text"] += 1
        else:
            problems.append({"path": path, "before": before, "after": after})
    else:
        problems.append({"path": path, "before": before, "after": after, "issue": "type changed"})


def main(before_dir, after_dir, factor, out):
    tally, problems, examples = Counter(), [], []
    files = sorted(p.name for p in Path(before_dir).glob("*.json"))
    for name in files:
        b = json.loads((Path(before_dir) / name).read_text())
        a = json.loads((Path(after_dir) / name).read_text())
        compare(b, a, factor, name, tally, problems)
        for item in (b.get("segments_requiring_attention") or []):
            match = next(x for x in a["segments_requiring_attention"] if x["segment"] == item["segment"]
                         and x["family"] == item["family"])
            examples.append({"before": item["headline"], "after": match["headline"],
                             "severity": [item.get("severity"), match.get("severity")]})
    report = {"files": len(files), "factor": factor, "tally": dict(tally),
              "problems": problems, "float_noise": noise,
              "attention_headlines": examples}
    Path(out).write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ("files", "tally")}, indent=1))
    for e in examples:
        print(f"  {e['before']}  ->  {e['after']}")
    print(f"PROBLEMS: {len(problems)}")
    for p in problems[:15]:
        print("  ", json.dumps(p)[:300])
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]))
