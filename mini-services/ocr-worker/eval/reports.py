"""Reports — machine-readable JSON/CSV + human markdown (Phase 9, Part 19).

Never reduced to one winner score: every table is cut by language, script,
quality, document type, preprocessing, and engine. SKIPPED/FAILED engines
appear explicitly with reasons.
"""
from __future__ import annotations

import csv
import io
import json
import os


def write_json(path: str, payload: dict) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return path


def flatten_records(records: list[dict]) -> list[dict]:
    """One flat row per engine×sample×variant for CSV."""
    rows = []
    for r in records:
        rows.append({
            "engine": r.get("engine"), "engine_status": r.get("engine_status"),
            "sample_id": r.get("sample_id"), "category": r.get("category"),
            "language": r.get("language"), "script": r.get("script"),
            "preprocessing": r.get("preprocessing"),
            "raw_cer": r.get("raw_cer"), "normalized_cer": r.get("normalized_cer"),
            "wer": r.get("wer"), "mean_confidence": r.get("mean_confidence"),
            "verdict": r.get("verdict"), "runtime_s": r.get("runtime_s"),
            "repeat": r.get("repeat", 1),
        })
    return rows


def write_csv(path: str, records: list[dict]) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rows = flatten_records(records)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["note"])
        w.writeheader()
        w.writerows(rows) if rows else w.writerow({"note": "no records"})
    return path


def _fmt(v, digits: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def write_markdown(path: str, payload: dict) -> str:
    """Human report: per-engine sections with language/quality cuts."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    out = io.StringIO()
    out.write(f"# OCR Evaluation Report — {payload.get('run_id', '')}\n\n")
    out.write(f"Environment: {payload.get('environment', {}).get('platform', '?')} · "
              f"Python {payload.get('environment', {}).get('python', '?')}\n\n")
    skipped = payload.get("skipped_engines", [])
    if skipped:
        out.write("## Skipped / failed engines\n\n")
        for s in skipped:
            out.write(f"- **{s.get('engine')}**: {s.get('status')} — {s.get('reason', '')}\n")
        out.write("\n")
    for eng in payload.get("engines", []):
        out.write(f"## Engine: {eng.get('display', eng.get('engine'))}\n\n")
        out.write(f"Model: `{eng.get('model', '?')}` · version `{eng.get('model_version', '?')}` · "
                  f"device `{eng.get('device', '?')}` · pages `{eng.get('pages', 0)}`\n\n")
        out.write("| Cut | n | Raw CER | Norm. CER | WER | s/page |\n")
        out.write("|---|---|---|---|---|---|\n")
        for row in eng.get("cuts", []):
            out.write(f"| {row.get('cut')} | {row.get('n')} | {_fmt(row.get('raw_cer'))} | "
                      f"{_fmt(row.get('normalized_cer'))} | {_fmt(row.get('wer'))} | {_fmt(row.get('seconds_per_page'), 2)} |\n")
        out.write("\n")
        cal = eng.get("calibration") or []
        if cal:
            out.write("Confidence calibration (bin → measured CER):\n\n")
            for b in cal:
                out.write(f"- {_fmt(b.get('conf_lo'), 2)}–{_fmt(b.get('conf_hi'), 2)}: "
                          f"n={b.get('n')} CER={_fmt(b.get('mean_cer'))}\n")
            out.write("\n")
    out.write("## Notes\n\n" + (payload.get("notes", "No overall winner is declared — compare cuts above.") + "\n"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(out.getvalue())
    return path
