"""Resumable book runner — one page at a time, constant memory.

Flow per invocation:
  1. open the PDF (lazy; total pages counted, nothing preloaded)
  2. pull the resumable set from the API (PENDING | QUEUED | FAILED) —
     pages already OCR_DONE / INDEXED are NEVER reprocessed
  3. for each page: classify → DIGITAL extract | render → preprocess →
     OCR chain → normalize → writeback (PATCH pages {action:"ocr"})
     BLANK → write empty OCR_DONE stub · HANDWRITTEN candidate →
     NEEDS_REVIEW via fail-note (human transcription, never HTR text)
  4. advance the job stage (ANALYZING → OCR → VERIFYING)

--dry-run processes local pages 1..N with no API calls (sample validation).
--create-job creates the Phase 2 job (with totalPages) before processing.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import AdminApiClient, ApiError
from config import WorkerConfig
from engines import build_chain, recognize_with_fallback
from engines.htr import is_handwritten_candidate
from extractor import extract_digital
from metadata import page_metadata
from normalize import detect_language, detect_script, normalize_text
from pdf_router import classify_page
from preprocess import preprocess
from renderer import document_info, open_pdf, render_page
from schemas import OcrBlock, PageResult
from verify import verify_page

RESUMABLE = {"PENDING", "QUEUED", "FAILED"}


def should_run_secondary(res, needs_review: bool, config, primary_engine: str) -> bool:
    """Review-routed dual capture decision (pure, unit-tested).

    - off: never. always: every page with primary text (except BLANK).
    - review (default): only when the primary needs review — REVIEW verdict,
      caller-flagged needs_review, HANDWRITTEN route, or confidence below
      the configured threshold. Never without primary text.
    The secondary engine equal to the primary is always skipped (no double-run).
    """
    mode = (config.secondary_mode or "review").lower()
    if mode == "off":
        return False
    if not (res.raw_text or "").strip():
        return False
    if (config.secondary_engine or "") == (primary_engine or ""):
        return False
    if res.route == "BLANK":
        return False
    if mode == "always":
        return True
    verdict = (res.signals or {}).get("verdict", "OK")
    if needs_review or verdict == "REVIEW" or res.route == "HANDWRITTEN":
        return True
    conf = res.confidence
    return conf is not None and conf < config.secondary_min_conf


def secondary_complete(page: dict) -> bool:
    """A stored secondary capture exists (text) or finished (signals)."""
    if page.get("ocrTextSecondary"):
        return True
    try:
        import json as _json

        sig = _json.loads(page.get("signals") or "{}")
        return isinstance(sig, dict) and isinstance(sig.get("secondary"), dict) \
            and sig["secondary"].get("status") == "done"
    except Exception:
        return False


def run_secondary_capture(doc, page_no: int, config, lang_hint: str = "mixed") -> dict:
    """Independent second OCR pass (fresh render; never touches primary state).

    Returns {text, confidence, engine, model_version} or {error}.
    """
    from engines import REGISTRY

    name = config.secondary_engine or ""
    cls = REGISTRY.get(name)
    if cls is None:
        return {"error": f"unknown secondary engine: {name}"}
    try:
        from preprocess import preprocess
        from renderer import render_page

        img = render_page(doc, page_no, dpi=config.render_dpi)
        try:
            prepped, _applied = preprocess(img, config)
        finally:
            del img
        engine = cls(config)
        if not engine.available():
            return {"error": f"secondary engine unavailable: {name}"}
        result = engine.recognize(prepped, lang_hint=lang_hint)
        return {"text": result.text, "confidence": result.mean_confidence,
                "engine": engine.name, "model_version": engine.model_version}
    except Exception as exc:  # noqa: BLE001 — isolated per Part 24
        return {"error": f"{type(exc).__name__}: {exc}"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_range(spec: str | None, total: int) -> list[int]:
    """'1-10,15' → [1..10, 15] (1-based), clamped to total. None → all."""
    if not spec:
        return list(range(1, total + 1))
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted({n for n in out if 1 <= n <= total})


def process_page(
    doc,
    page_no: int,
    config: WorkerConfig,
    chain,
    job_id: str | None,
    book_id: str | None,
    volume: int,
) -> PageResult:
    warnings: list[str] = []
    route_info = classify_page(doc, page_no, config)
    route = route_info["route"]

    if route == "BLANK":
        out = PageResult(
            job_id=job_id, book_id=book_id, volume=volume, page_number=page_no,
            route=route, raw_text="", normalized_text="", confidence=None,
            language="unknown", script="none", image_width=0, image_height=0,
            engine="router", model="blank-skip", model_version="router-1",
            warnings=warnings,
        )
        out.metadata = page_metadata("")  # type: ignore[attr-defined]
        out.signals = verify_page(out, config)  # type: ignore[attr-defined]
        return out

    if route == "DIGITAL":
        page = doc.load_page(page_no - 1)
        ext = extract_digital(page)
        lang = detect_language(ext["text"])
        out = PageResult(
            job_id=job_id, book_id=book_id, volume=volume, page_number=page_no,
            route=route, raw_text=ext["text"], normalized_text=normalize_text(ext["text"]),
            confidence=1.0, language=lang, script=detect_script(ext["text"]),
            image_width=0, image_height=0, blocks=ext["blocks"],
            engine="pymupdf-digital", model="embedded-text",
            model_version="pymupdf-digital-1", warnings=warnings,
            # no rendered image on this route: checksum over the exact text
            checksum=sha256_bytes(ext["text"].encode("utf-8")),
        )
        out.metadata = page_metadata(out.raw_text)  # type: ignore[attr-defined]
        out.signals = verify_page(out, config)  # type: ignore[attr-defined]
        return out

    # SCANNED_PRINTED or MIXED → render → preprocess → OCR chain
    img = render_page(doc, page_no, dpi=config.render_dpi)
    w, h = img.size
    checksum = sha256_bytes(img.tobytes())
    prepped, applied = preprocess(img, config)
    del img  # original preserved on disk; work only with the copy
    if applied:
        warnings.append("preprocess:" + ",".join(applied))
    if route_info.get("embedded_text"):
        warnings.append(f"embedded-chars-kept:{route_info['embedded_chars']}")

    if is_handwritten_candidate(prepped):
        warnings.append("htr-candidate:flagged-for-review")
        lang = "unknown"
        text, blocks, conf, engine, model, version = "", [], None, "htr-stub", "none", "htr-stub-0"
        final_route = "HANDWRITTEN"
    else:
        lang_hint = "mixed"
        result, engine, chain_warnings = recognize_with_fallback(prepped, chain, lang_hint=lang_hint)
        warnings.extend(chain_warnings)
        lang = detect_language(result.text)
        text, blocks, conf = result.text, result.blocks, result.mean_confidence
        model, version = result.model, ""
        # resolve model_version from the engine instance
        for e in chain:
            if e.name == engine:
                version = e.model_version
                break
        final_route = route
        if conf is not None and conf < 0.45:
            warnings.append(f"low-confidence:{conf:.2f}-needs-review")
    del prepped
    gc.collect()

    out = PageResult(
        job_id=job_id, book_id=book_id, volume=volume, page_number=page_no,
        route=final_route, raw_text=text, normalized_text=normalize_text(text),
        confidence=conf, language=lang, script=detect_script(text),
        image_width=w, image_height=h, blocks=blocks,
        engine=engine, model=model, model_version=version,
        checksum=checksum, warnings=warnings,
    )
    # Phase 4: metadata cues + verification verdict travel with the result
    # (dynamic attrs — schema stays stable). Raw text is never altered here.
    out.metadata = page_metadata(text)  # type: ignore[attr-defined]
    out.signals = verify_page(  # type: ignore[attr-defined]
        out, config,
        embedded_text=route_info.get("embedded_text", "") if route == "MIXED" else "",
    )
    return out


def _open_pdf_or_exit(path: str):
    """Context manager wrapper: corrupt/unreadable PDFs exit cleanly."""
    import contextlib

    @contextlib.contextmanager
    def _wrapped():
        try:
            with open_pdf(path) as doc:
                yield doc
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"cannot open PDF {path}: {type(exc).__name__}: {exc}")

    return _wrapped()


def _job_cancelled(api, job_id: str) -> bool:
    """Poll current job status; cancelled jobs stop the worker promptly."""
    try:
        job = api.get_job(job_id).get("job", {})
        return job.get("status") == "CANCELLED"
    except ApiError:
        return False  # transient errors must not abort processing


def run(args, config: WorkerConfig) -> dict:
    from pypdf import PdfReader

    try:
        reader = PdfReader(args.pdf)
        total = len(reader.pages)
        del reader
    except Exception as exc:  # noqa: BLE001 — corrupt/unreadable PDF fails fast, cleanly
        raise SystemExit(f"cannot open PDF {args.pdf}: {type(exc).__name__}: {exc}")

    api = None if args.dry_run else AdminApiClient(args.api_base, args.admin_key, config.request_timeout_s)
    job_id = args.job_id
    if api and getattr(args, "book_id", None) and not args.dry_run:
        # Source-integrity gate: local file must match the stored checksum
        # (detects moved/corrupted originals before spending OCR budget).
        try:
            rec = api.get_book_record(args.book_id)
            expected = ((rec.get("record") or {}).get("sourceChecksum")
                        or (rec.get("book") or {}).get("sourceChecksum"))
            if expected:
                from storage import sha256_file

                if sha256_file(args.pdf) != expected:
                    raise SystemExit(
                        f"source checksum mismatch for book {args.book_id}: "
                        "local file differs from the stored original — refusing to process"
                    )
                print(json.dumps({"source_verified": True}))
        except SystemExit:
            raise
        except ApiError as exc:
            print(json.dumps({"warn": f"source check skipped: {exc}"}))
    job_id = args.job_id
    if args.create_job and api:
        if not args.book_id:
            raise SystemExit("--create-job requires --book-id")
        try:
            created = api.create_job(args.book_id, total, args.volume, {"sourceRef": args.pdf, "requestedBy": "ocr-worker"})
        except ApiError as exc:
            raise SystemExit(f"cannot create job: {exc}")
        job_id = created["job"]["id"]
        print(json.dumps({"created_job": job_id}))

    # resumable set: only PENDING | QUEUED | FAILED (or local plan in dry-run)
    # plus secondary-only revisits: OCR_DONE/NEEDS_REVIEW rows whose secondary
    # capture is missing/failed (primary is NOT redone for these).
    secondary_wanted: set[int] = set()
    if api and job_id:
        try:
            listing = api.list_pages(job_id=job_id, take=500)
        except ApiError as exc:
            raise SystemExit(f"cannot list job pages: {exc}")
        wanted = {p["pageNumber"] for p in listing.get("pages", []) if p.get("status") in RESUMABLE}
        page_ids = {p["pageNumber"]: p["id"] for p in listing.get("pages", [])}
        page_rows = {p["pageNumber"]: p for p in listing.get("pages", [])}
        if config.secondary_mode != "off":
            secondary_wanted = {
                p["pageNumber"] for p in listing.get("pages", [])
                if p.get("status") in ("OCR_DONE", "NEEDS_REVIEW") and not secondary_complete(p)
            }
    else:
        wanted = set(parse_range(args.pages, total))
        page_ids = {}
        page_rows = {}

    selected = [n for n in parse_range(args.pages, total) if n in wanted]
    if args.limit and args.limit > 0:
        selected = selected[: args.limit]

    chain = build_chain(config)
    stats = {"total": total, "selected": len(selected), "done": 0, "failed": 0, "review": 0, "skipped_done": total - len(wanted),
             "secondary_done": 0, "secondary_failed": 0, "secondary_skipped": 0}
    done_secondary: set[int] = set()
    results: list[dict] = []

    with _open_pdf_or_exit(args.pdf) as doc:
        info = document_info(doc)
        stats["pdf_pages"] = info["page_count"]
        if api and job_id and selected:
            try:
                api.advance_job(job_id, "ANALYZING")
            except ApiError as exc:
                print(json.dumps({"warn": f"advance ANALYZING refused: {exc}"}))
        for i, page_no in enumerate(selected):
            if api and job_id and _job_cancelled(api, job_id):
                print(json.dumps({"cancelled": True, "at_page": page_no}))
                stats["cancelled"] = True
                break
            try:
                res = process_page(doc, page_no, config, chain, job_id, args.book_id, args.volume)
            except Exception as exc:  # noqa: BLE001 — one bad page never kills the run
                stats["failed"] += 1
                if api and job_id and page_no in page_ids:
                    try:
                        api.flag_page_review(page_ids[page_no], f"worker exception: {type(exc).__name__}: {exc}"[:500])
                    except ApiError:
                        pass
                print(json.dumps({"page": page_no, "error": f"{type(exc).__name__}: {exc}"}))
                continue
            if api and job_id and page_no in page_ids:
                pid = page_ids[page_no]
                try:
                    import json as _json

                    verdict = (res.signals or {}).get("verdict", "OK")
                    needs_review = verdict == "REVIEW" or res.route == "HANDWRITTEN"
                    if res.route == "BLANK":
                        api.write_page_ocr(pid, "", None, "unknown", "router/blank-skip", res.checksum, blank=True)
                        stats["done"] += 1
                    elif res.route == "HANDWRITTEN" and not res.raw_text.strip():
                        api.flag_page_review(pid, f"route=HANDWRITTEN warnings={'; '.join(res.warnings)}"[:500])
                        stats["review"] += 1
                    else:
                        wb = res.to_writeback()
                        # Phase 4: verification signals + metadata cues ride in
                        # the signals payload (stored on BookPage.signals);
                        # reindex merges cues into SearchDocument.meta.
                        payload_signals = dict(res.signals or {})
                        payload_signals["cues"] = res.metadata or {}
                        api.write_page_ocr(
                            pid, wb["ocrText"], wb["ocrConfidence"], wb["language"], wb["engine"], wb["checksum"],
                            normalized_text=res.normalized_text or None,
                            signals=payload_signals, needs_review=needs_review,
                        )
                        stats["done" if not needs_review else "review"] += 1
                        # Phase 13: review-routed secondary capture. Independent
                        # pass; primary record stands regardless of outcome.
                        row = page_rows.get(page_no, {})
                        if not secondary_complete(row) and should_run_secondary(
                            res, needs_review, config, res.engine
                        ):
                            sec = run_secondary_capture(doc, page_no, config)
                            if "error" in sec:
                                try:
                                    api.record_secondary_error(pid, str(sec["error"])[:500])
                                except ApiError:
                                    pass
                                stats["secondary_failed"] += 1
                                print(json.dumps({"page": page_no, "secondary": sec["error"][:200]}))
                            else:
                                try:
                                    api.write_page_ocr2(
                                        pid, sec["text"], sec["confidence"],
                                        f"{sec['engine']}/{sec['model_version']}" if sec.get("model_version") else sec["engine"],
                                    )
                                    stats["secondary_done"] += 1
                                    done_secondary.add(page_no)
                                except ApiError as exc2:
                                    stats["secondary_failed"] += 1
                                    print(json.dumps({"page": page_no, "error": f"secondary writeback: {exc2}"}))
                        else:
                            stats["secondary_skipped"] += 1
                except ApiError as exc:
                    stats["failed"] += 1
                    print(json.dumps({"page": page_no, "error": f"writeback: {exc}"}))
                    continue
            else:
                stats["done"] += 1
            if args.emit_json:
                from structure import chunk_page

                provenance = {
                    "bookId": args.book_id, "volume": args.volume,
                    "pageNumber": page_no, "pdfPage": page_no,
                    "pageId": page_ids.get(page_no, f"dryrun:{page_no}"),
                    "jobId": job_id, "engine": res.engine, "model": res.model,
                    "checksum": res.checksum, "language": res.language,
                    **(res.metadata or {}),
                }
                chunks = chunk_page(res.raw_text, provenance)
                d = res.to_dict()
                d["metadata"] = res.metadata
                d["signals"] = res.signals
                d["chunks"] = [
                    {k: c[k] for k in ("kind", "start", "end") if k in c} | {"chars": len(c["text"])}
                    for c in chunks
                ]
                results.append(d)
            if i == 0 and api and job_id:
                try:
                    api.advance_job(job_id, "OCR")
                except ApiError:
                    pass
        # Secondary-only revisits: pages whose primary is done but secondary
        # is missing/failed. No primary re-OCR, no attempts bump, no counter
        # changes — only secondary_done/failed move.
        if api and job_id:
            if _job_cancelled(api, job_id):
                print(json.dumps({"cancelled": True, "at_stage": "secondary-revisit"}))
                stats["cancelled"] = True
                return _finish(args, config, stats, results, api, job_id)
            revisit = sorted(
                secondary_wanted.intersection(parse_range(args.pages, total)) - done_secondary
            )
            if args.limit and args.limit > 0:
                revisit = revisit[: args.limit]
            for page_no in revisit:
                pid = page_ids.get(page_no)
                if not pid:
                    continue
                sec = run_secondary_capture(doc, page_no, config)
                if "error" in sec:
                    try:
                        api.record_secondary_error(pid, str(sec["error"])[:500])
                    except ApiError:
                        pass
                    stats["secondary_failed"] += 1
                    print(json.dumps({"page": page_no, "secondary": sec["error"][:200]}))
                else:
                    try:
                        api.write_page_ocr2(
                            pid, sec["text"], sec["confidence"],
                            f"{sec['engine']}/{sec['model_version']}" if sec.get("model_version") else sec["engine"],
                        )
                        stats["secondary_done"] += 1
                    except ApiError as exc2:
                        stats["secondary_failed"] += 1
                        print(json.dumps({"page": page_no, "error": f"secondary writeback: {exc2}"}))
        return _finish(args, config, stats, results, api, job_id)


def _finish(args, config, stats: dict, results: list, api, job_id) -> dict:
    """Shared tail: final advance attempt + stats return (cancel-safe exit)."""
    if api and job_id and not stats.get("cancelled"):
        try:
            api.advance_job(job_id, "VERIFYING")
        except ApiError as exc:
            print(json.dumps({"warn": f"advance VERIFYING refused: {exc}"}))
    stats["results"] = results if args.emit_json else []
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nur al-Usul book OCR worker (Phase 3)")
    ap.add_argument("--pdf", required=False, default=None, help="path to the original PDF (never modified)")
    ap.add_argument("--source-ref", default=None, help="stable storage reference, e.g. books/<id>/original.pdf (resolves via NUR_STORAGE; wins over --pdf)")
    ap.add_argument("--book-id", default=None)
    ap.add_argument("--job-id", default=None)
    ap.add_argument("--volume", type=int, default=1)
    ap.add_argument("--pages", default=None, help="e.g. 1-10,15 (default: all resumable)")
    ap.add_argument("--limit", type=int, default=0, help="max pages this invocation (0 = no cap)")
    ap.add_argument("--dry-run", action="store_true", help="no API calls; process local pages only")
    ap.add_argument("--create-job", action="store_true")
    ap.add_argument("--emit-json", action="store_true", help="include per-page results in output")
    ap.add_argument("--api-base", default=None)
    ap.add_argument("--admin-key", default=None)
    ap.add_argument("--engine", default=None, help="override OCR_PRIMARY_ENGINE")
    parsed = ap.parse_args(argv)
    config = WorkerConfig.from_env()
    if parsed.api_base:
        config.api_base = parsed.api_base
    if parsed.engine:
        config.primary_engine = parsed.engine
    admin_key = parsed.admin_key or os.environ.get("NUR_ADMIN_KEY", "")
    if not parsed.dry_run and not admin_key:
        raise SystemExit("NUR_ADMIN_KEY (or --admin-key) is required unless --dry-run")
    pdf_path = parsed.pdf
    if parsed.source_ref:
        from storage import resolve_source_path

        try:
            pdf_path = resolve_source_path(parsed.source_ref)
        except (ValueError, FileNotFoundError) as exc:
            raise SystemExit(f"cannot resolve --source-ref: {exc}")
    if not pdf_path or not os.path.isfile(pdf_path):
        raise SystemExit("--pdf <file> or --source-ref <ref> to an existing PDF is required")
    parsed.pdf = pdf_path
    parsed.api_base = config.api_base
    parsed.admin_key = admin_key
    stats = run(parsed, config)
    print(json.dumps({k: v for k, v in stats.items() if k != "results"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
