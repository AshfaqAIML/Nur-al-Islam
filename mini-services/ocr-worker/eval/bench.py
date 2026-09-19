"""Benchmark orchestrator (Phase 9). Usage:
    python -m eval.bench --engines easyocr --variants raw,restored --limit 3
    python -m eval.bench --dataset-root /path/to/real/pages --engines all
Read-only w.r.t. inputs (Part 25): outputs go to eval/outputs/<run_id>/.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

import calibration
import dataset
import domain
import engines_eval
import errors
import ground_truth
import language as lang_mod
import layout_metrics
import metrics
import normalization
import preprocess_variants
import reports
import resources


def _load_image(sample: dict):
    if sample["path"].lower().endswith(".pdf"):
        import fitz

        doc = fitz.open(sample["path"])
        try:
            pix = doc.load_page(0).get_pixmap(dpi=200)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        finally:
            doc.close()
    return Image.open(sample["path"]).convert("RGB")


def _gt_text(gt: dict | None) -> str:
    if not gt:
        return ""
    return ground_truth.reference_text(gt)


def run_bench(args) -> dict:
    from config import WorkerConfig

    cfg = WorkerConfig()
    root = args.dataset_root
    disc = dataset.discover_dataset(root)
    samples = [s for s in disc["samples"]
               if (not args.categories or s["category"] in args.categories)
               and (not args.samples or s["id"] in args.samples)
               and (not args.limit or True)][: args.limit or None]
    env = resources.environment_fingerprint()
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(root or dataset.eval_root(), "outputs", run_id)
    os.makedirs(out_dir, exist_ok=True)

    wanted = args.engines.split(",") if args.engines != "all" else list(engines_eval.REGISTRY)
    variants = args.variants.split(",")
    records: list[dict] = []
    skipped: list[dict] = []
    engine_summaries: dict[str, dict] = {}

    for key in wanted:
        adapter = engines_eval.REGISTRY.get(key)
        if adapter is None:
            skipped.append({"engine": key, "status": "SKIPPED", "reason": "unknown engine key"})
            continue
        probe = adapter.probe()
        if not probe.available:
            skipped.append({"engine": key, "status": probe.status, "reason": probe.reason, "kind": probe.kind})
            continue
        with resources.Timer(f"load-{key}") as t_load:
            load_info = {"load_seconds": 0.0}
        # model load happens lazily inside run(); measured per first page below
        eng_rec = {"engine": key, "display": adapter.display, "model": "", "model_version": "",
                   "device": "cpu", "pages": 0, "cuts": [], "calibration": []}
        per_page_s: list[float] = []
        cal_rows: list[dict] = []
        first = True
        for sample in samples:
            gt = None
            try:
                gt = dataset.load_ground_truth(sample)
                if gt:
                    problems = ground_truth.validate_ground_truth(gt, sample["ground_truth"])
                    if problems:
                        records.append({"engine": key, "engine_status": "FAILED", "sample_id": sample["id"],
                                        "category": sample["category"], "reason": "; ".join(problems)})
                        continue
            except Exception as exc:  # noqa: BLE001 — one bad GT never kills the run
                records.append({"engine": key, "engine_status": "FAILED", "sample_id": sample["id"],
                                "category": sample["category"], "reason": f"GT load: {exc}"})
                continue
            sample_modality = (gt or {}).get("modality", "printed")
            if sample_modality != adapter.modality:
                records.append({"engine": key, "engine_status": "SKIPPED", "sample_id": sample["id"],
                                "category": sample["category"],
                                "reason": f"modality {adapter.modality} vs sample {sample_modality} (never cross-scored)"})
                continue
            try:
                img = _load_image(sample)
            except Exception as exc:  # noqa: BLE001
                records.append({"engine": key, "engine_status": "FAILED", "sample_id": sample["id"],
                                "category": sample["category"], "reason": f"load: {exc}"})
                continue
            for variant in variants:
                for rep in range(max(1, args.repeat)):
                    try:
                        prepped, applied = preprocess_variants.apply_variant(img, variant, cfg)
                    except Exception as exc:  # noqa: BLE001
                        records.append({"engine": key, "engine_status": "FAILED", "sample_id": sample["id"],
                                        "category": sample["category"], "preprocessing": variant,
                                        "reason": f"preprocess: {exc}"})
                        continue
                    kwargs = {}
                    if sample["path"].lower().endswith(".pdf"):
                        kwargs = {"pdf_path": sample["path"], "page_no": 1}
                    try:
                        with resources.Timer("page") as t_page:
                            res = adapter.run(prepped, lang_hint=(gt or {}).get("language", "mixed"), **kwargs)
                    except Exception as exc:  # noqa: BLE001
                        records.append({"engine": key, "engine_status": "FAILED", "sample_id": sample["id"],
                                        "category": sample["category"], "preprocessing": variant,
                                        "reason": f"run: {type(exc).__name__}: {exc}"})
                        continue
                    if first:
                        load_info["load_seconds"] = 0.0  # lazy-load measured inside run; see runtime_s
                        first = False
                    per_page_s.append(t_page.seconds)
                    if eng_rec["model"] == "":
                        eng_rec.update({"model": res.model, "model_version": res.model_version, "device": res.device})
                    ref = _gt_text(gt)
                    if not gt:
                        records.append({"engine": key, "engine_status": "NO_GT", "sample_id": sample["id"],
                                        "category": sample["category"], "preprocessing": variant,
                                        "runtime_s": res.runtime_s, "repeat": rep + 1, "language": "unknown"})
                        continue
                    m_raw = metrics.cer(ref, res.text)
                    norm = normalization.normalization_breakdown(ref, res.text)
                    m_wer = metrics.wer(ref, res.text)
                    lang = gt.get("language", "unknown")
                    # Line-sampled GT (partial human transcription): matched
                    # line CER is the primary metric; page CER is reported
                    # but NOT valid against a subset reference.
                    line_stats = None
                    if gt.get("partial"):
                        from metrics import line_level

                        ll = line_level(
                            [ln["text"] for ln in gt["lines"]],
                            [ln.text for ln in res.lines],
                            fold=normalization.normalize_for_eval,
                        )
                        line_stats = {k: v for k, v in ll.items() if k != "pairs"}
                        line_stats["pair_sample"] = [
                            {"gt": p["gt"][:80], "hyp": (p["hyp"] or "")[:80], "cer": round(p["cer"], 3)}
                            for p in ll["pairs"][:12]
                        ]
                    # layout (bboxes where available on both sides)
                    gt_boxes = [ln["bbox"] for ln in gt["lines"] if ln.get("bbox")]
                    pr_boxes = [ln.bbox for ln in res.lines if ln.bbox]
                    det = layout_metrics.detection_scores(pr_boxes, gt_boxes) if gt_boxes and pr_boxes else None
                    order = layout_metrics.reading_order_score(
                        [ln.text for ln in res.lines], [ln["text"] for ln in gt["lines"]]) if res.lines else None
                    # review verdict via production signals (PageResult reuse)
                    verdict, signals = _verdict_for(res, sample)
                    hits = domain.domain_hits(res.text)
                    rec = {"engine": key, "engine_status": "AVAILABLE", "sample_id": sample["id"],
                           "category": sample["category"], "language": lang,
                           "script": gt.get("script", "unknown"), "preprocessing": variant,
                           "variant_applied": applied, "raw_cer": m_raw["cer"], "cer_ops": {k: m_raw[k] for k in ("substitutions", "deletions", "insertions")},
                           "normalized_cer": norm["normalized_cer"], "norm_breakdown": norm,
                           "wer": m_wer["wer"], "wer_ops": {k: m_wer[k] for k in ("substitutions", "deletions", "insertions")},
                           "mean_confidence": res.mean_confidence, "verdict": verdict, "signals": signals,
                            "runtime_s": res.runtime_s, "repeat": rep + 1,
                            "hypothesis": res.text,
                            "line_level": line_stats,
                           "detection_f1": det["f1"] if det else None,
                           "order_distance": order["order_distance"] if order else None,
                           "domain_hits": sum(1 for v in hits.values() if v), "domain_total": len(hits)}
                    records.append(rec)
                    cal_rows.append({"mean_confidence": res.mean_confidence, "cer": m_raw["cer"]})
                    if args.save_cases and (m_raw["cer"] > 0.02 or verdict == "REVIEW"):
                        case_errs = errors.classify_errors(ref, res.text)
                        errors.save_case(os.path.join(out_dir, "cases"), f"{key}-{sample['id'].replace('/', '_')}-{variant}",
                                         sample["path"] if not sample["path"].lower().endswith(".pdf") else None,
                                         gt, res.text)
                        rec["error_summary"] = case_errs["summary"]
        eng_rec["pages"] = sum(1 for r in records if r["engine"] == key and r.get("engine_status") == "AVAILABLE")
        eng_rec["seconds_per_page"] = (sum(per_page_s) / len(per_page_s)) if per_page_s else None
        eng_rec["calibration"] = calibration.calibration_bins(cal_rows)
        eng_rec["cuts"] = _cuts(records, key)
        engine_summaries[key] = eng_rec
        _ = t_load

    payload = {"run_id": run_id, "environment": env, "warnings": disc["warnings"],
               "records": records, "skipped_engines": skipped,
               "engines": list(engine_summaries.values()),
               "notes": "No overall winner declared. Urdu column authoritative for this collection."}
    reports.write_json(os.path.join(out_dir, "results.json"), payload)
    reports.write_csv(os.path.join(out_dir, "results.csv"), [r for r in records if r.get("engine_status") == "AVAILABLE"])
    reports.write_markdown(os.path.join(out_dir, "report.md"), payload)
    return payload


def _cuts(records: list[dict], engine: str) -> list[dict]:
    """Per-engine cuts: overall, by language, by category, by variant."""
    rows = [r for r in records if r["engine"] == engine and r.get("engine_status") == "AVAILABLE"]
    cuts = []

    def agg(rs: list[dict], name: str) -> None:
        if not rs:
            return
        cuts.append({"cut": name, "n": len(rs),
                     "raw_cer": sum(r["raw_cer"] for r in rs) / len(rs),
                     "normalized_cer": sum(r["normalized_cer"] for r in rs) / len(rs),
                     "wer": sum(r["wer"] for r in rs) / len(rs),
                     "seconds_per_page": sum(r["runtime_s"] for r in rs) / len(rs)})

    agg(rows, "all")
    for lang in ("ur", "ar", "mixed"):
        agg([r for r in rows if r.get("language") == lang], f"lang:{lang}")
    for cat in sorted({r.get("category") for r in rows}):
        agg([r for r in rows if r.get("category") == cat], f"cat:{cat}")
    for var in sorted({r.get("preprocessing") for r in rows}):
        agg([r for r in rows if r.get("preprocessing") == var], f"pre:{var}")
    return cuts


def _verdict_for(res, sample: dict) -> tuple[str, dict]:
    """Production verify.verdict for the review-signal evaluation."""
    import sys as _sys
    import os as _os

    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from config import WorkerConfig
    from schemas import OcrBlock, OcrLine, PageResult
    from verify import verify_page

    lines = [OcrLine(text=ln.text, confidence=ln.confidence or 0.0, bbox=ln.bbox or [0, 0, 0, 0]) for ln in res.lines]
    pr = PageResult(job_id=None, book_id=None, volume=1, page_number=1, route="SCANNED_PRINTED",
                    raw_text=res.text, normalized_text=res.text, confidence=res.mean_confidence,
                    language="mixed", script="mixed", image_width=0, image_height=0,
                    blocks=[OcrBlock(text=res.text, confidence=res.mean_confidence or 0.0, bbox=[0, 0, 1, 1], lines=lines)],
                    engine=res.engine, model=res.model, model_version=res.model_version)
    signals = verify_page(pr, WorkerConfig())
    return signals["verdict"], signals


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Nur al-Usul OCR evaluation lab")
    ap.add_argument("--dataset-root", default=None)
    ap.add_argument("--engines", default="all")
    ap.add_argument("--variants", default="raw,restored")
    ap.add_argument("--categories", default=None, help="csv subset")
    ap.add_argument("--samples", default=None, help="csv sample-id subset (e.g. real-fatawa/fz-p100)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--save-cases", action="store_true")
    args = ap.parse_args(argv)
    if args.categories:
        args.categories = [c.strip() for c in args.categories.split(",")]
    if args.samples:
        args.samples = [s.strip() for s in args.samples.split(",")]
    payload = run_bench(args)
    recs = [r for r in payload["records"] if r.get("engine_status") == "AVAILABLE"]
    print(f"run {payload['run_id']}: {len(recs)} scored records, "
          f"{len(payload['skipped_engines'])} skipped engines, "
          f"reports in outputs/{payload['run_id']}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
