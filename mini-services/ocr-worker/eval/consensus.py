"""Multi-engine consensus (Phase 11, Part 11/13/14/15).

Explainable line-level consensus: align lines across engines, score
character/word agreement, select per-line candidates ONLY on strong
agreement, otherwise flag conflict. NEVER rewrites source text silently —
low-agreement lines are flagged for human review, not auto-corrected.
"""
from __future__ import annotations

from metrics import cer, line_level


class ConsensusEngine:
    """compare() → align() → score_agreement() → select_candidate() → flag_conflicts()."""

    def __init__(self, match_thresh: float = 0.3, agree_thresh: float = 0.85, fold=None):
        self.match_thresh = match_thresh
        self.agree_thresh = agree_thresh
        self.fold = fold or (lambda s: s)

    def align(self, lines_a: list[str], lines_b: list[str]) -> list[dict]:
        """Greedy line alignment A→B. Returns [{a, b, f1}]."""
        used: set[int] = set()
        out = []
        for a in lines_a:
            at = self.fold(a).split()
            best, best_j, best_f1 = -1.0, -1, 0.0
            for j, b in enumerate(lines_b):
                if j in used:
                    continue
                bt = self.fold(b).split()
                sa, sb = set(at), set(bt)
                f1 = (2 * len(sa & sb) / (len(sa) + len(sb))) if (sa or sb) else 1.0
                if f1 > best_f1:
                    best, best_j, best_f1 = b, j, f1
            if best_j >= 0 and best_f1 >= self.match_thresh:
                used.add(best_j)
            out.append({"a": a, "b": best if best_j >= 0 and best_f1 >= self.match_thresh else None, "f1": best_f1})
        return out

    def compare(self, texts: list[str]) -> dict:
        """Pairwise character + word agreement across engine outputs."""
        n = len(texts)
        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                a, b = self.fold(texts[i]), self.fold(texts[j])
                denom = max(len(a), 1)
                char_agree = 1 - min(1.0, cer(a, b)["cer"])
                sa, sb = set(a.split()), set(b.split())
                word_agree = (2 * len(sa & sb) / (len(sa) + len(sb))) if (sa or sb) else 1.0
                pairs.append({"pair": (i, j), "char_agreement": char_agree, "word_agreement": word_agree})
        mean_c = sum(p["char_agreement"] for p in pairs) / len(pairs) if pairs else 1.0
        mean_w = sum(p["word_agreement"] for p in pairs) / len(pairs) if pairs else 1.0
        return {"n_engines": n, "pairs": pairs, "mean_char_agreement": mean_c, "mean_word_agreement": mean_w}

    def score_agreement(self, aligned: list[dict]) -> list[dict]:
        """Per-line agreement 0..1 from alignment F1 (explainable scalar)."""
        return [{"line": a["a"], "agreement": a["f1"]} for a in aligned]

    def select_candidate(self, aligned: list[dict], confidences: list[float] | None = None) -> list[dict]:
        """Select line text ONLY on strong agreement; else flag conflict.

        Returns [{text|None, decision: agree|conflict, reason}]. No silent
        rewriting: conflicts yield text=None + reason for human review.
        """
        out = []
        for idx, a in enumerate(aligned):
            if a["b"] is not None and a["f1"] >= self.agree_thresh:
                out.append({"text": a["a"], "decision": "agree",
                            "reason": f"engines agree (line-F1 {a['f1']:.2f})"})
            else:
                conf = f" conf={confidences[idx]:.2f}" if confidences and idx < len(confidences) else ""
                out.append({"text": None, "decision": "conflict",
                            "reason": f"engines disagree (line-F1 {a['f1']:.2f}{conf}) → human review"})
        _ = confidences
        return out

    def flag_conflicts(self, decisions: list[dict]) -> list[dict]:
        return [d for d in decisions if d["decision"] == "conflict"]
