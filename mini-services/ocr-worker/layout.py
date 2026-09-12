"""Reading-order layout — rows top-to-bottom, RTL-aware within rows.

Used for both digital blocks (PyMuPDF dict bboxes) and OCR lines so the
stored text follows the page's visual reading order in Urdu/Arabic.
"""
from __future__ import annotations

from schemas import OcrBlock, OcrLine


def order_lines(lines: list[OcrLine], rtl: bool = True, y_tol: float | None = None) -> list[OcrLine]:
    """Group detections into visual rows, then order rows top-to-bottom.

    y_tol defaults to 0.6× median line height: detector boxes on the same
    visual line jitter vertically, and a fixed pixel tolerance splits them
    into false rows (which then scrambles RTL word order and breaks
    marker+number adjacency like "مسئلہ نمبر 112"). Within a row, lines go
    right-to-left for RTL scripts, left-to-right otherwise.
    """
    if not lines:
        return []
    heights = sorted(max(1.0, ln.bbox[3] - ln.bbox[1]) for ln in lines)
    tol = y_tol if y_tol is not None else max(4.0, 0.6 * heights[len(heights) // 2])
    rows: list[list[OcrLine]] = []
    centers: list[float] = []
    for ln in sorted(lines, key=lambda l: ((l.bbox[1] + l.bbox[3]) / 2, l.bbox[0])):
        cy = (ln.bbox[1] + ln.bbox[3]) / 2
        placed = False
        for i, row in enumerate(rows):
            if abs(centers[i] - cy) <= tol:
                row.append(ln)
                centers[i] = sum((l.bbox[1] + l.bbox[3]) / 2 for l in row) / len(row)
                placed = True
                break
        if not placed:
            rows.append([ln])
            centers.append(cy)
    ordered: list[OcrLine] = []
    for row in rows:
        row.sort(key=lambda l: l.bbox[0], reverse=rtl)
        ordered.extend(row)
    return ordered


def blocks_from_lines(lines: list[OcrLine], rtl: bool = True) -> list[OcrBlock]:
    """Group ordered lines into one block per visual row-group (simple pass)."""
    ordered = order_lines(lines, rtl=rtl)
    if not ordered:
        return []
    xs0 = min(ln.bbox[0] for ln in ordered)
    ys0 = min(ln.bbox[1] for ln in ordered)
    xs1 = max(ln.bbox[2] for ln in ordered)
    ys1 = max(ln.bbox[3] for ln in ordered)
    conf = sum(ln.confidence for ln in ordered) / len(ordered)
    return [OcrBlock(text="\n".join(ln.text for ln in ordered), confidence=conf, bbox=[xs0, ys0, xs1, ys1], lines=ordered)]
