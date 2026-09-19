"""Confidence calibration + review-signal evaluation (Phase 9, Part 15/16).

- Calibration: bin mean engine confidence vs measured CER. Raw confidence is
  reported as an observation, NEVER as a calibrated probability.
- Review signals: production verify.verdict vs actual error (cer > threshold)
  → false positives / false negatives / review rate for threshold tuning.
"""
from __future__ import annotations


def calibration_bins(records: list[dict], bins: int = 5) -> list[dict]:
    """records: [{mean_confidence, cer}]. Returns per-bin {conf, cer, n}."""
    rows = [(r["mean_confidence"], r["cer"]) for r in records
            if isinstance(r.get("mean_confidence"), (int, float)) and isinstance(r.get("cer"), (int, float))]
    if not rows:
        return []
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        cell = [(c, e) for c, e in rows if (lo <= c < hi) or (b == bins - 1 and c == hi)]
        if not cell:
            out.append({"conf_lo": lo, "conf_hi": hi, "n": 0, "mean_conf": None, "mean_cer": None})
            continue
        out.append({"conf_lo": lo, "conf_hi": hi, "n": len(cell),
                    "mean_conf": sum(c for c, _ in cell) / len(cell),
                    "mean_cer": sum(e for _, e in cell) / len(cell)})
    return out


def review_signal_stats(records: list[dict], error_thresh: float = 0.05) -> dict:
    """records: [{verdict: OK|REVIEW, cer}]."""
    tp = fp = tn = fn = 0
    for r in records:
        flagged = r.get("verdict") == "REVIEW"
        bad = isinstance(r.get("cer"), (int, float)) and r["cer"] > error_thresh
        if flagged and bad:
            tp += 1
        elif flagged:
            fp += 1
        elif bad:
            fn += 1
        else:
            tn += 1
    total = tp + fp + tn + fn
    return {
        "true_positives": tp, "false_positives": fp,
        "true_negatives": tn, "false_negatives": fn,
        "review_rate": (tp + fp) / total if total else 0.0,
        "miss_rate": fn / (tp + fn) if (tp + fn) else 0.0,
        "precision": tp / (tp + fp) if (tp + fp) else 0.0,
        "error_threshold_cer": error_thresh,
    }
