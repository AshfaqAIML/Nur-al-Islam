"""Edit metrics — CER/WER with full op breakdown (Phase 9, Part 11).

Pure functions, no dependencies. Levenshtein via single-row DP with
backtrace for insertions/deletions/substitutions. Word tokenization is
whitespace-based (script-agnostic — no stemming, no stopwords).
"""
from __future__ import annotations


def edit_ops(ref: list, hyp: list) -> dict:
    """Levenshtein ops between token lists. Returns counts + aligned pairs."""
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    # backpointer table: 0=diag/sub, 1=del, 2=ins
    bp = [[0] * (m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        bp[0][j] = 2
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            sub = prev[j - 1] + cost
            dele = prev[j] + 1
            ins = cur[j - 1] + 1
            best = min(sub, dele, ins)
            cur[j] = best
            bp[i][j] = 0 if best == sub else (1 if best == dele else 2)
        prev = cur
    distance = prev[m]
    subs = dels = inss = 0
    pairs: list[tuple] = []
    i, j = n, m
    while i > 0 or j > 0:
        op = bp[i][j] if i > 0 and j > 0 else (1 if i > 0 else 2)
        if i > 0 and j > 0 and op == 0:
            if ref[i - 1] != hyp[j - 1]:
                subs += 1
            pairs.append(("ok" if ref[i - 1] == hyp[j - 1] else "sub", ref[i - 1], hyp[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and (j == 0 or op == 1):
            dels += 1
            pairs.append(("del", ref[i - 1], None))
            i -= 1
        else:
            inss += 1
            pairs.append(("ins", None, hyp[j - 1]))
            j -= 1
    pairs.reverse()
    return {"distance": distance, "substitutions": subs, "deletions": dels, "insertions": inss, "pairs": pairs}


def cer(ref: str, hyp: str) -> dict:
    """Character error rate + ops. Empty ref: 0.0 iff hyp empty else 1.0."""
    if not ref:
        return {"cer": 0.0 if not hyp else 1.0, "distance": len(hyp), "substitutions": 0, "deletions": 0, "insertions": len(hyp), "ref_len": 0}
    r = edit_ops(list(ref), list(hyp))
    return {"cer": r["distance"] / len(ref), "distance": r["distance"],
            "substitutions": r["substitutions"], "deletions": r["deletions"],
            "insertions": r["insertions"], "ref_len": len(ref)}


def wer(ref: str, hyp: str) -> dict:
    """Word error rate + ops. Same empty convention as cer()."""
    rw, hw = ref.split(), hyp.split()
    if not rw:
        return {"wer": 0.0 if not hw else 1.0, "distance": len(hw), "substitutions": 0, "deletions": 0, "insertions": len(hw), "ref_len": 0}
    r = edit_ops(rw, hw)
    return {"wer": r["distance"] / len(rw), "distance": r["distance"],
            "substitutions": r["substitutions"], "deletions": r["deletions"],
            "insertions": r["insertions"], "ref_len": len(rw)}


def _token_f1(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    return 2 * inter / (len(sa) + len(sb))


def line_level(ref_lines: list[str], hyp_lines: list[str], match_thresh: float = 0.3,
               fold=None) -> dict:
    """Line-sampled scoring for partial (human-transcribed) ground truth.

    Each GT line greedily matches the hyp line with best token-F1 (on folded
    text when `fold` is given, so Urdu spelling variants still match).
    Reports matched CER (raw pairs), match rate, and unmatched counts.
    Unmatched GT lines count as full misses (CER 1.0 weighted in).
    """
    fold = fold or (lambda s: s)
    hyp_tokens = [(h, fold(h).split()) for h in hyp_lines]
    used: set[int] = set()
    pairs: list[dict] = []
    for gt in ref_lines:
        gt_toks = fold(gt).split()
        best, best_j, best_f1 = -1.0, -1, 0.0
        for j, (h, ht) in enumerate(hyp_tokens):
            if j in used:
                continue
            f1 = _token_f1(gt_toks, ht)
            if f1 > best_f1:
                best, best_j, best_f1 = h, j, f1
        if best_j >= 0 and best_f1 >= match_thresh:
            used.add(best_j)
            c = cer(gt, best)
            pairs.append({"gt": gt, "hyp": best, "f1": best_f1, "cer": c["cer"], "ops": {
                "substitutions": c["substitutions"], "deletions": c["deletions"], "insertions": c["insertions"]}})
        else:
            pairs.append({"gt": gt, "hyp": None, "f1": 0.0, "cer": 1.0,
                          "ops": {"substitutions": 0, "deletions": len(gt_toks), "insertions": 0}})
    matched = [p for p in pairs if p["hyp"] is not None]
    weights = [max(1, len(p["gt"])) for p in pairs]
    wcer = sum(p["cer"] * w for p, w in zip(pairs, weights)) / sum(weights)
    # Coverage: GT tokens found ANYWHERE in hyp (segmentation-independent
    # content recovery — complements alignment-sensitive matched CER).
    gt_toks = [t for g in ref_lines for t in fold(g).split()]
    hyp_set = set()
    for h in hyp_lines:
        hyp_set.update(fold(h).split())
    coverage = (sum(1 for t in gt_toks if t in hyp_set) / len(gt_toks)) if gt_toks else 0.0
    return {
        "n_gt": len(ref_lines), "n_hyp": len(hyp_lines),
        "matched": len(matched), "match_rate": len(matched) / len(ref_lines) if ref_lines else 0.0,
        "unmatched_hyp": len(hyp_lines) - len(used),
        "weighted_cer": wcer,
        "mean_best_f1": sum(p["f1"] for p in pairs) / len(pairs) if pairs else 0.0,
        "coverage": coverage,
        "pairs": pairs,
    }
