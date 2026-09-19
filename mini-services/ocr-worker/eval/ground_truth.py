"""Ground-truth format + validation (Phase 9, Part 5).

ground_truth/{category}/{name}.json:
{
  "sample_id": "urdu/fatawa-p1",
  "language": "ur" | "ar" | "en" | "mixed",
  "script": "arab" | "latn" | "mixed",
  "source": "human" | "fixture",
  "source_note": "who verified / which fixture generated it",
  "lines": [{"text": "...", "bbox": [x0,y0,x1,y1] | null}],
  "reading_order": [0, 1, 2, ...]   // optional line indices in reading order
}

"source: fixture" = text authored alongside a synthetic fixture (NOT model
output). "human" = transcribed by a person from a real page. Anything else
is rejected — model output is never ground truth.
"""
from __future__ import annotations

VALID_SOURCES = ("human", "fixture")
VALID_LANGS = ("ur", "ar", "en", "mixed")
VALID_SCRIPTS = ("arab", "latn", "mixed")


def validate_ground_truth(data: dict, path: str = "<memory>") -> list[str]:
    """Return a list of problems (empty = valid). Never raises on content."""
    problems: list[str] = []
    for key in ("sample_id", "lines", "language", "script", "source"):
        if key not in data:
            problems.append(f"missing required key: {key}")
    if not isinstance(data.get("lines"), list):
        problems.append("lines must be a list")
        return problems
    if data.get("source") not in VALID_SOURCES:
        problems.append(f"source must be one of {VALID_SOURCES}")
    if data.get("language") not in VALID_LANGS:
        problems.append(f"language must be one of {VALID_LANGS}")
    if data.get("script") not in VALID_SCRIPTS:
        problems.append(f"script must be one of {VALID_SCRIPTS}")
    for i, ln in enumerate(data["lines"]):
        if not isinstance(ln, dict) or "text" not in ln:
            problems.append(f"line {i}: missing text")
            continue
        bbox = ln.get("bbox")
        if bbox is not None and not (
            isinstance(bbox, list) and len(bbox) == 4
            and all(isinstance(v, (int, float)) for v in bbox)
        ):
            problems.append(f"line {i}: bbox must be [x0,y0,x1,y1] or null")
    order = data.get("reading_order")
    if order is not None:
        if sorted(order) != list(range(len(data["lines"]))):
            problems.append("reading_order must be a permutation of line indices")
    if problems:
        problems.insert(0, f"invalid ground truth: {path}")
    return problems


def reference_text(data: dict, order: str = "given") -> str:
    """Reference string for CER/WER. order='reading' uses reading_order."""
    lines = data["lines"]
    if order == "reading" and data.get("reading_order"):
        lines = [lines[i] for i in data["reading_order"]]
    return "\n".join(ln["text"] for ln in lines)
