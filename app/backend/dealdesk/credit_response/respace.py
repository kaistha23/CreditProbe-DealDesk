"""Spaces back into words that OCR ran together ("Murabahaagainstpaymentcertificates" → "Murabaha against payment
certificates"). A run of letters is split only when every piece is a known word: the banking vocabulary below plus every
word the same document prints with spaces around it. Deterministic; anything not fully split is left as read.
"""
from __future__ import annotations

import re
from functools import lru_cache

BASE = """a an and as at by for from in of on or the to up with within without per against under over into until after before
limit limits sub general project projects facility facilities total totals renewal renew new existing outstanding proposed
cash margin margins particulars advance payment payments guarantee guarantees guarantor bond bonds performance retention
letter letters credit sight usance murabaha tawarruq overdraft certificate certificates certified engineer net amount amounts
months month days day year years review interchangeable dedicated life only used open ended wording employer employers standard
format proceeds assigned assignment assignments bank banks first settle settled related outstanding funded covered least remaining
contract contracts route routing turnover through audited financial statements statement in house half each existing complied
complied not acknowledged signature signed promissory note replacing deposit personal corporate shareholder share shares partner
security support terms conditions condition status action requested request business corporate banking eastern province branch
main customer group date account opened connected party heavy equipment rental real estate owned purpose code finance contracting
type additional industry construction buildings collateral rating proposed number relationship manager hub package logistics
corridor imports mep commission benchmark spread floor tenor validity repayment until full recovery end defects liability period
recovery draw draws per max maximum minimum cap capped balances balance due not exceed approved approval committee group exposure
than less cover ratio covenant covenants undertaking undertakings lg lgs lc lcs dmccm saibor dlp pq pa worth accepted ended only used
requested via standard employer shareholder awarded value contract signature""".split()


def _vocab(extra: tuple[str, ...]) -> frozenset[str]:
    return frozenset(BASE) | frozenset(extra)


@lru_cache(maxsize=4096)
def _split(word: str, vocab: frozenset[str]) -> tuple[str, ...] | None:
    w = word.lower()
    n = len(w)
    best: list[tuple[int, ...] | None] = [None] * (n + 1)
    best[0] = ()
    for i in range(1, n + 1):
        for j in range(max(0, i - 16), i):
            if best[j] is not None and w[j:i] in vocab and (len(w[j:i]) > 1 or w[j:i] in ("a",)):
                cand = best[j] + (i,)
                if best[i] is None or len(cand) < len(best[i]):
                    best[i] = cand
    if best[n] is None or len(best[n]) < 2:
        return None
    cuts, out, j = best[n], [], 0
    for i in cuts:
        out.append(word[j:i])
        j = i
    return tuple(out)


def respace(text: str, context: str = "") -> str:
    """Split letter runs of 8+ characters that are not words of the context into known words."""
    base = _vocab(())
    seen = tuple(sorted({w.lower() for w in re.findall(r"(?<![A-Za-z])[A-Za-z]{2,8}(?![A-Za-z])", context)
                         if w.lower() in base or _split(w, base) is None}))  # a run of known words is not a word
    vocab = _vocab(seen)

    def fix(m: re.Match) -> str:
        w = m.group(0)
        if w.lower() in vocab:
            return w
        parts = _split(w, vocab)
        return " ".join(parts) if parts else w
    return re.sub(r"[A-Za-z]{8,}", fix, text)
