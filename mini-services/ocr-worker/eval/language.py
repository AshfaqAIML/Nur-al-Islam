"""Language-split aggregation (Phase 9, Part 14).

Urdu / Arabic / mixed are ALWAYS reported separately (books are primarily
Urdu — its column must stay visible). A combined score may accompany, never
replace, the split.
"""
from __future__ import annotations


def split_key(language: str) -> str:
    return language if language in ("ur", "ar", "mixed") else "other"


def aggregate_by_language(records: list[dict], metric: str = "cer") -> dict:
    """records: [{language, <metric>, ...}] → {ur: {...}, ar: {...}, mixed: {...}}."""
    buckets: dict[str, list[float]] = {"ur": [], "ar": [], "mixed": [], "other": []}
    for r in records:
        v = r.get(metric)
        if isinstance(v, (int, float)):
            buckets[split_key(str(r.get("language", "other")))].append(float(v))
    out: dict = {}
    for lang, vals in buckets.items():
        out[lang] = {
            "n": len(vals),
            f"mean_{metric}": (sum(vals) / len(vals)) if vals else None,
            f"min_{metric}": min(vals) if vals else None,
            f"max_{metric}": max(vals) if vals else None,
        }
    scored = [v for vals in buckets.values() for v in vals]
    out["combined"] = {"n": len(scored), f"mean_{metric}": (sum(scored) / len(scored)) if scored else None}
    return out
