"""Error analysis (Phase 9, Part 20).

Aligns reference vs hypothesis at word level and classifies each error:
substitution / deletion / insertion / segmentation (split/merge via
character-overlap heuristic) / dot-diacritic (differ only by dots/diacritics
or Arabic-script folds) / rtl-ordering (same words, different order).
Artifacts (image copy, GT, output) are saved per analyzed case so every
error can be traced to a fix class: preprocessing / OCR / segmentation /
normalization / post-processing.
"""
from __future__ import annotations

import os
import shutil

from metrics import edit_ops
from normalization import normalize_for_eval


def _dots_only(a: str, b: str) -> bool:
    """True if words differ only by dots/diacritics/folds (not real letters)."""
    if a == b:
        return False
    na, nb = normalize_for_eval(a), normalize_for_eval(b)
    if na == nb:
        return True
    strip = str.maketrans("", "", "\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0670")
    return a.translate(strip) == b.translate(strip)


def classify_errors(ref: str, hyp: str) -> dict:
    r = edit_ops(ref.split(), hyp.split())
    cats = {"substitution": [], "deletion": [], "insertion": [],
            "segmentation": [], "dot_diacritic": [], "rtl_order": []}
    for kind, a, b in r["pairs"]:
        if kind == "ok":
            continue
        if kind == "sub" and _dots_only(a or "", b or ""):
            cats["dot_diacritic"].append((a, b))
        elif kind == "sub":
            cats["substitution"].append((a, b))
        elif kind == "del":
            cats["deletion"].append((a, None))
        else:
            cats["insertion"].append((None, b))
    # segmentation: a deleted word adjacent to an inserted word sharing chars
    dels = [a for a, _ in cats["deletion"]]
    inss = [b for _, b in cats["insertion"]]
    for a in list(dels):
        for b in list(inss):
            if a and b and (a in b or b in a):
                cats["segmentation"].append((a, b))
    # rtl-ordering: same multiset, different sequence
    if sorted(ref.split()) == sorted(hyp.split()) and ref.split() != hyp.split():
        cats["rtl_order"].append((ref, hyp))
    summary = {k: len(v) for k, v in cats.items()}
    summary["total"] = sum(summary.values())
    return {"categories": cats, "summary": summary, "wer_ops": {
        "substitutions": r["substitutions"], "deletions": r["deletions"], "insertions": r["insertions"]}}


def save_case(out_dir: str, case_id: str, image_path: str | None,
              ground_truth: dict | None, hypothesis: str) -> str:
    """Persist one analyzed case. Returns the case directory."""
    import json

    case_dir = os.path.join(out_dir, case_id)
    os.makedirs(case_dir, exist_ok=True)
    if image_path and os.path.isfile(image_path):
        shutil.copy2(image_path, os.path.join(case_dir, "image" + os.path.splitext(image_path)[1]))
    if ground_truth is not None:
        with open(os.path.join(case_dir, "ground_truth.json"), "w", encoding="utf-8") as f:
            json.dump(ground_truth, f, ensure_ascii=False, indent=1)
    with open(os.path.join(case_dir, "hypothesis.txt"), "w", encoding="utf-8") as f:
        f.write(hypothesis)
    return case_dir
