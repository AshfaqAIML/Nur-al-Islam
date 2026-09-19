"""Layout metrics — detection, lines, reading order (Phase 9, Part 13).

Reported SEPARATELY from CER/WER, never merged. Box geometry uses pixel
coords; reading order compares index sequences (Kendall-tau distance).
"""
from __future__ import annotations


def iou(a: list[float], b: list[float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0, ix1, iy1 = max(ax0, bx0), max(ay0, by0), min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def detection_scores(pred_boxes: list[list[float]], gt_boxes: list[list[float]], iou_thresh: float = 0.5) -> dict:
    """Greedy matching → precision/recall/F1 for text regions or lines."""
    matched_gt: set[int] = set()
    tp = 0
    for pb in pred_boxes:
        best, best_i = 0.0, -1
        for i, gb in enumerate(gt_boxes):
            if i in matched_gt:
                continue
            v = iou(pb, gb)
            if v > best:
                best, best_i = v, i
        if best >= iou_thresh and best_i >= 0:
            tp += 1
            matched_gt.add(best_i)
    fp = len(pred_boxes) - tp
    fn = len(gt_boxes) - len(matched_gt)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": precision, "recall": recall,
        "f1": (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0,
    }


def kendall_tau_distance(pred_order: list[int], ref_order: list[int]) -> float:
    """Normalized pairwise disagreement 0..1 (0 = identical order)."""
    pos = {v: i for i, v in enumerate(ref_order)}
    seq = [pos[v] for v in pred_order if v in pos]
    n = len(seq)
    if n < 2:
        return 0.0
    discord = sum(1 for i in range(n) for j in range(i + 1, n) if seq[i] > seq[j])
    return discord / (n * (n - 1) / 2)


def reading_order_score(pred_texts: list[str], gt_texts: list[str]) -> dict:
    """Match identical line texts, then score their relative order."""
    remaining = list(gt_texts)
    pred_idx: list[int] = []
    for t in pred_texts:
        if t in remaining:
            pred_idx.append(gt_texts.index(t))
            remaining.remove(t)
    return {
        "matched_lines": len(pred_idx),
        "gt_lines": len(gt_texts),
        "order_distance": kendall_tau_distance(pred_idx, list(range(len(gt_texts)))),
    }
