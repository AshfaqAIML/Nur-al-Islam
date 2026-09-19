"""Domain term analysis + multi-engine consensus (Phase 9, Part 22/24).

Domain list: representative Islamic-literature terms for ERROR ANALYSIS
(hit/miss per term per engine). It is NOT ground truth and never scores —
it shows WHICH vocabulary each engine drops. Consensus: agreement between
engines predicts error only if measured — reported, never acted on.
"""
from __future__ import annotations

DOMAIN_TERMS = [
    "میلاد", "ولادت", "نماز", "وضو", "حدیث", "سنت", "فتوی",
    "فقہ", "قرآن", "تفسیر", "صحابہ", "اجماع", "قیاس", "طہارت",
]


def domain_hits(text: str, terms: list[str] | None = None) -> dict:
    """Per-term presence in a hypothesis text (folded comparison)."""
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from normalize import normalize_text

    folded = normalize_text(text)
    out: dict[str, bool] = {}
    for term in terms or DOMAIN_TERMS:
        out[term] = normalize_text(term) in folded
    return out


def domain_report(records: list[dict]) -> dict:
    """records: [{engine, hits: {term: bool}}] → per-term hit-rate by engine."""
    by_engine: dict[str, dict[str, list[bool]]] = {}
    for r in records:
        eng = by_engine.setdefault(r["engine"], {})
        for term, hit in (r.get("hits") or {}).items():
            eng.setdefault(term, []).append(bool(hit))
    return {eng: {t: (sum(v) / len(v)) for t, v in terms.items()} for eng, terms in by_engine.items()}


def consensus(texts: list[str]) -> dict:
    """Agreement across engine outputs (normalized exact match + pair rates)."""
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from normalize import normalize_text

    folded = [normalize_text(t) for t in texts]
    n = len(folded)
    pairs = 0
    agree = 0
    for i in range(n):
        for j in range(i + 1, n):
            pairs += 1
            if folded[i] == folded[j]:
                agree += 1
    return {"n_engines": n, "pairs": pairs,
            "full_agreement": all(t == folded[0] for t in folded) if folded else True,
            "pair_agreement_rate": (agree / pairs) if pairs else 1.0}
