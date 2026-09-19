"""Eval dataset loading (Phase 9, Part 2/4).

Layout (in-repo skeleton + external override via NUR_EVAL_DIR):
  eval/samples/{urdu,arabic,mixed,degraded,difficult,footnotes,headings,quran}/
  eval/ground_truth/{sample_id}.json
  eval/outputs/  eval/reports/  eval/configs/

Categories are incremental: any subset may exist; unknown subfolders are
ignored with a warning. Ground truth is NEVER inferred from model output —
human-verified JSON (see ground_truth.py). Real PDFs/pages stay OUTSIDE git
via NUR_EVAL_DIR; in-repo samples are synthetic fixtures only.
"""
from __future__ import annotations

import json
import os

CATEGORIES = (
    "urdu", "arabic", "mixed", "degraded", "difficult",
    "footnotes", "headings", "quran",
    "real-fatawa", "real-tibyan",
)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")


def eval_root(explicit: str | None = None) -> str:
    """In-repo eval/ unless NUR_EVAL_DIR points at an external collection."""
    if explicit:
        return explicit
    ext = os.environ.get("NUR_EVAL_DIR")
    if ext:
        return ext
    here = os.path.dirname(os.path.abspath(__file__))
    return here  # this package directory IS the eval root


def discover_dataset(root: str | None = None) -> dict:
    """Return {samples: [...], warnings: [...]}. Sample = image/pdf page file."""
    base = eval_root(root)
    samples_dir = os.path.join(base, "samples")
    samples: list[dict] = []
    warnings: list[str] = []
    if not os.path.isdir(samples_dir):
        return {"samples": samples, "warnings": [f"samples dir missing: {samples_dir}"]}
    for entry in sorted(os.listdir(samples_dir)):
        full = os.path.join(samples_dir, entry)
        if not os.path.isdir(full):
            continue
        if entry not in CATEGORIES:
            warnings.append(f"unknown category dir ignored: {entry}")
            continue
        for fn in sorted(os.listdir(full)):
            ext = os.path.splitext(fn)[1].lower()
            if ext in IMAGE_EXTS or ext == ".pdf":
                sample_id = f"{entry}/{os.path.splitext(fn)[0]}"
                samples.append({
                    "id": sample_id,
                    "category": entry,
                    "path": os.path.join(full, fn),
                    "ground_truth": os.path.join(base, "ground_truth", sample_id + ".json"),
                })
    return {"samples": samples, "warnings": warnings}


def load_ground_truth(sample: dict) -> dict | None:
    """Human-verified reference or None (sample runs unevaluated, never scored)."""
    path = sample["ground_truth"]
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for key in ("sample_id", "lines"):
        if key not in data:
            raise ValueError(f"ground truth {path} missing required key: {key}")
    return data
