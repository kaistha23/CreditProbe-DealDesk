"""Prove the frozen Cockpit is byte-identical to the v5 base commit.

Exit 0 when every frozen path in the working tree (committed or not, plus any
new untracked file under them) matches commit 831044ce, the frozen Round H
245c50e4 plus the tenant fix. Exit 1 and list the offending files otherwise.
"""
import subprocess
import sys
from pathlib import Path

BASE = "831044ce2574"
FROZEN = (
    "backend/cockpit_v4",
    "frontend/src/components/cockpit-v4",
    "frontend/src/app/cockpit",
    "frontend/src/app/page.tsx",
    "scripts/cockpit_v4",
    "config/cockpit_v4",
)
ROOT = Path(__file__).resolve().parents[1]

#: The one frozen file v5 changes, and only by the corporate rescale's policy
#: calibration (docs/v5/RESCALE.md): its content must equal the base file
#: with exactly ops/rescale_corporate.POLICY_SUBSTITUTIONS applied.
CALIBRATED = ("backend/cockpit_v4/credit_policy.json",)


#: Registered presentation-layer exceptions (INBOX Item 3, B2;
#: docs/v5/FROZEN_EXCEPTIONS.md). A frozen file listed here may differ from the
#: base ONLY by its stored patch: reverse-applying the patch to the file on
#: disk must give back exactly the base file (its manifest SHA-256), and the
#: file must hash to the registered patched SHA-256. Anything else fails.
EXCEPTIONS = ROOT / "ops" / "frozen_exceptions.json"


def _exceptions() -> dict:
    import json
    if not EXCEPTIONS.exists():
        return {}
    return {e["path"]: e for e in json.loads(EXCEPTIONS.read_text())["exceptions"]}


def reverse_patch(text: str, patch: str) -> str | None:
    """Undo a unified diff on `text`; None if the patch does not apply exactly."""
    import re
    lines = text.splitlines(keepends=True)
    hunks, cur = [], None
    for ln in patch.splitlines(keepends=True):
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", ln)
        if m:
            cur = {"new_start": int(m.group(3)), "body": []}
            hunks.append(cur)
        elif cur is not None and ln[:1] in (" ", "-", "+"):
            cur["body"].append(ln)
        elif cur is not None and ln.startswith("\\"):
            continue
    for h in reversed(hunks):
        new = [x[1:] for x in h["body"] if x[0] in " +"]
        old = [x[1:] for x in h["body"] if x[0] in " -"]
        at = h["new_start"] - 1 if new else h["new_start"]
        if lines[at:at + len(new)] != new:
            return None
        lines[at:at + len(new)] = old
    return "".join(lines)


def exception_ok(name: str, base_digest: str) -> str | None:
    """'' when the file is base + exactly its registered patch, else the reason."""
    import hashlib
    e = _exceptions().get(name)
    if not e:
        return "not a registered exception"
    data = (ROOT / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != e["patched_sha256"]:
        return f"{e['id']}: file is not the registered patched content"
    undone = reverse_patch(data.decode("utf-8"), (ROOT / e["patch"]).read_text())
    if undone is None or hashlib.sha256(undone.encode("utf-8")).hexdigest() != base_digest:
        return f"{e['id']}: reverse-applying {e['patch']} does not give back the base file"
    return ""


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout


def base_present() -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{BASE}^{{commit}}"], cwd=ROOT,
                          capture_output=True).returncode == 0


def manifest_check() -> int:
    """Where the base commit is not in the clone (the pushed snapshot has a
    fresh history), compare against ops/frozen_manifest.json: SHA-256 of every
    frozen file at the base, written from the base commit itself."""
    import hashlib
    import json
    man = json.loads((ROOT / "ops" / "frozen_manifest.json").read_text())["files"]
    bad, accepted = [], []
    for name, digest in man.items():
        path = ROOT / name
        if not path.exists():
            bad.append(name + " (missing)")
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            why = exception_ok(name, digest)
            if why == "":
                accepted.append(f"{_exceptions()[name]['id']} {name}")
            else:
                bad.append(f"{name} ({why})")
    present = set(git("ls-files", "--", *FROZEN).split()) | set(
        git("ls-files", "--others", "--exclude-standard", "--", *FROZEN).split())
    extra = sorted(present - set(man))
    # The calibrated policy file's manifest entry is the digest of its
    # CALIBRATED content, so it too must match exactly.
    if bad or extra:
        print(f"FROZEN GUARD FAIL (manifest): {len(bad)} changed, {len(extra)} new")
        for n in bad + extra:
            print("  ", n)
        return 1
    print(f"FROZEN GUARD PASS (manifest): {len(man)} frozen files match {BASE}"
          + (f" (registered exceptions, each exactly its patch: {'; '.join(accepted)})" if accepted else ""))
    return 0


def main() -> int:
    if not base_present():
        sys.path.insert(0, str(ROOT))
        return manifest_check()
    changed = git("diff", "--name-only", BASE, "--", *FROZEN).split()
    sys.path.insert(0, str(ROOT))
    from ops.rescale_corporate import rescale_policy  # noqa: PLC0415
    calibrated = []
    for name in CALIBRATED:
        if name in changed:
            expected = rescale_policy(git("show", f"{BASE}:{name}"))
            if (ROOT / name).read_text(encoding="utf-8") == expected:
                changed.remove(name)
                calibrated.append(name)
    import hashlib
    accepted = []
    for name in list(changed):
        if name in _exceptions():
            digest = hashlib.sha256(subprocess.run(["git", "show", f"{BASE}:{name}"], cwd=ROOT, check=True,
                                                   capture_output=True).stdout).hexdigest()
            if exception_ok(name, digest) == "":
                changed.remove(name)
                accepted.append(f"{_exceptions()[name]['id']} {name}")
    untracked = git("ls-files", "--others", "--exclude-standard", "--", *FROZEN).split()
    files = int(git("ls-tree", "-r", "--name-only", BASE, "--", *FROZEN).count("\n"))
    if changed or untracked:
        print(f"FROZEN GUARD FAIL: {len(changed)} changed, {len(untracked)} new files")
        for name in changed + untracked:
            print("  ", name)
        return 1
    print(f"FROZEN GUARD PASS: {files} frozen files identical to {BASE}"
          + (f" (except the verified rescale calibration of {', '.join(calibrated)})"
             if calibrated else "")
          + (f" (registered exceptions, each exactly its patch: {'; '.join(accepted)})" if accepted else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
