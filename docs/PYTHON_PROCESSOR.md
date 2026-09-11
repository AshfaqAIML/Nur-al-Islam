# Python Book Processor — Phase 3 Deliverable

> Server-side processor in `mini-services/ocr-worker/`. Wired to the Phase 2
> `BookProcessingJob` foundation. **Sample workflow validated; no full book processed.**
> Audit reference: `docs/BOOK_PIPELINE_INTEGRATION_AUDIT.md` §14.

## 1. Responsibility map (all in `mini-services/ocr-worker/`)

| Concern | Module | Notes |
|---|---|---|
| PDF analysis + routing | `pdf_router.py` + `renderer.py` | `classify_page` → DIGITAL / SCANNED_PRINTED / MIXED / BLANK; thumbnails for stats, full render per page only |
| Page rendering | `renderer.py` | PyMuPDF, lazy per-page, pixmaps released immediately |
| Digital text extraction | `extractor.py` | `get_text("dict")` words/blocks/coords, confidence 1.0, engine `pymupdf-digital` — never OCR'd |
| Image preprocessing | `preprocess.py` | Adaptive, gated, logged; original never mutated (works on copies) |
| Layout analysis | `layout.py` | Row grouping + RTL-aware within-row ordering for OCR and digital lines |
| Urdu/Arabic recognition | `engines/easyocr_engine.py` | EasyOCR primary; Urdu → Arabic-script model (documented, no dedicated Urdu model exists) |
| Second OCR engine | `engines/tesseract_engine.py` | Fallback; `urd+ara+eng`; degrades gracefully when binary/data absent |
| HTR abstraction | `engines/htr.py` | `is_handwritten_candidate()` heuristic + stub whose `recognize()` always raises — HTR text can never enter OCR results; flagged pages → NEEDS_REVIEW |
| Document structure | `schemas.py` | `PageResult`: raw/normalized text, confidence, language, script, blocks, lines, bboxes, engine, model, model_version, checksum, warnings, job |
| Engine registry | `engines/__init__.py` | `build_chain(config)` + `recognize_with_fallback()`; PaddleOCR/PP-StructureV3 slot reserved as lazy modules |
| Config / model pins | `config.py` + `requirements.txt` | Every engine, model version, DPI, and threshold env-overridable |
| DB writeback | `api_client.py` → `PATCH /api/admin/pages {action:"ocr"}` | Small JSON only — **never PDFs or Base64 images** |
| Orchestration | `runner.py` | Resumable, incremental, constant-memory CLI |

## 2. Library selection (verified 2026-09-27, Python 3.13.2, 12 CPU / 6 GB)

| Library | Version | Role | Status |
|---|---|---|---|
| PyMuPDF | 1.27.2.3 | render + digital extract + metadata | installed, used |
| pypdf | 6.15.0 | page counting / metadata | installed, used |
| opencv-python-headless | 4.11.0.86 | preprocessing, skew, HTR heuristic | installed, used |
| Pillow | 11.1.0 | image IO (no raqm → shaping via libs below) | installed, used |
| numpy | 2.2.4 | pixel stats | installed, used |
| EasyOCR (+torch 2.7.0 CPU) | 1.7.2 | primary OCR, langs `ar,en` | installed; `craft_mlt_25k` + `arabic` models pre-cached, init + inference verified offline |
| requests (+urllib3 Retry) | 2.34.2 | writeback client | installed, used |
| arabic-reshaper / python-bidi | 3.0.1 / 0.6.10 | sample synthesis (reshaper installed this phase; bidi pre-existing) | installed, samples-only |
| Tesseract binary / pytesseract | — | fallback engine | **absent here** → engine reports unavailable, chain skips (never fatal) |
| PaddleOCR / PP-StructureV3 | — | optional future engine | **not installed** (paddlepaddle wheels unverified for this interpreter); registry slot + config pins ready, no code depends on it |
| pypdfium2 | — | optional alt renderer | documented option, not installed (PyMuPDF covers it) |

## 3. PDF routing

`classify_page(doc, n, config)`: embedded chars ≥ `digital_min_chars` (50) → **DIGITAL** (direct extract); else thumbnail ink coverage < `blank_ink_coverage` (0.002) → **BLANK** (skip spend); some embedded text + image → **MIXED** (OCR primary, embedded kept as cross-check warning); else **SCANNED_PRINTED** (render → preprocess → layout → OCR → structure). Post-render, `is_handwritten_candidate()` may re-route to **HANDWRITTEN** → NEEDS_REVIEW. Two real calibration fixes during testing: coverage threshold lowered 0.005→0.002 (sparse real pages), skew normalization extended to the ±90° ambiguity.

## 4. Urdu/Arabic support

Primary Urdu, secondary Arabic. `normalize.py`: verbatim `raw_text` always stored; `normalized_text` = NFC + kashida removal + alef folding (أإآٱ→ا; ة/ه untouched) + optional tashkeel strip — Quranic/diacritic text intact in raw. `detect_language` mirrors RAG's `detectLanguage` (ar/ur/en/mixed/unknown, same Urdu codepoints); `detect_script` arab/latn/mixed/none. RTL: right-aligned synthesis, RTL within-row ordering, `rtl+font-arabic` writeback rendering unchanged server-side. Nastaliq: no Nastaliq font on this machine (Arial/Tahoma Naskh used) — architecture is font-agnostic; note as data caveat, not a code gap.

## 5. Image preprocessing (adaptive, logged, non-destructive)

deskew (±0.5–15° only) · content crop (>2% margin only) · background flatten+deshadow (uneven bg only) · fastNlMeans denoise (noisy only) · CLAHE contrast (flat only) · mild unsharp deblur (blurry only) · binarize OFF by default (engines prefer grayscale) · dewarp detect-and-report (transform behind `enable_dewarp=false`). Every applied step recorded in `warnings` (`preprocess:deskew:5.02deg,…`); failures fall back to the previous image. Original page image never mutated (copy-on-write; disk originals read-only).

## 6. OCR result (per page)

`PageResult`: `raw_text`, `normalized_text`, `confidence` (mean line conf; 1.0 digital; null blank/HTR), `language`, `script`, `blocks[]` (`text/conf/bbox/lines[]`), image size, pixel bboxes, `engine` (+`model_version` pin), `checksum` (sha256 of rendered image), `warnings`, `job_id/book_id/volume/page_number/route`. `to_writeback()` → `{ocrText, ocrConfidence, language, engine, checksum}` for `PATCH /api/admin/pages`.

## 7. Database writeback (controlled, no second DB)

`AdminApiClient` (retries, timeouts, `ApiError`): `create_job` → Phase 2 `POST /ingest`; `list_pages` → resumable set; `write_page_ocr` → **new `PATCH /admin/pages {action:"ocr"}`** (this phase's only backend change: validates non-empty ≤200k chars, confidence 0..1, bounded strings, sets `OCR_DONE` + `attempts+1`, refreshes parent job counters); `flag_page_review` → `fail` path; `advance_job` → stage transitions. No direct DB access from Python; no binary over HTTP.

## 8. Resumability + performance

Runner pulls the resumable set (`PENDING|QUEUED|FAILED`) from the API — `OCR_DONE|INDEXED` pages are never refetched for work; restart at page 300/800 continues from the last valid state. `--pages`, `--limit` bound each invocation; single-page loop with pixmap release + periodic `gc`; PDF opened lazily (page count via pypdf without rendering); one bad page logs and continues. Stages advanced `ANALYZING → OCR → VERIFYING`; completion left to review/index phases (honest terminal states).

## 9. Sample validation (run 2026-09-27)

Fixtures (`samples/make_samples.py`, outputs gitignored): `digital_en` · `digital_ur` · `scanned_urdu` (12-line Naskh render) · `arabic_mixed` (Arabic+English) · `poor_quality` (rotated 2.5° + blur + noise + speckles), each with `.expected.txt` needles.

| Suite | Result |
|---|---|
| `pytest tests/ --ignore=test_samples` (router, preprocess, normalize, engines, API contract) | **23 passed** |
| `pytest tests/test_samples.py` (EasyOCR CPU offline) | **5 passed** — digital exact-needle recovery; Urdu scan non-empty Arabic-script text with bboxes + checksum; mixed runs; poor page records warnings; CLI dry-run regression test |
| **Total** | **28 passed / 0 failed** |

Bugs found & fixed by the tests: minAreaRect ±90° ambiguity (deskew silently skipped), BLANK threshold too aggressive, CLI `--api-base` kwarg collision, Tesseract bbox union error, ApiError forward reference.

## 10. Deferred / risks

- Tesseract binary + `urd/ara` data not installed here → fallback untested live (unit-tested unavailable-path). Install before production use.
- PaddleOCR/PP-StructureV3 unevaluated (registry-ready, not installed).
- No Nastaliq-font sample (font-agnostic code; add when a font is available).
- Live server round-trip (`--job-id` writeback) untested — needs running Next.js + DB; checklist: create job → run `--limit 2` → verify `OCR_DONE` rows + counters → `retry` → resume skips done pages.
- Vision-LLM OCR (`POST /api/ocr`) untouched — future: difficult pages escalatable per-page; keep as separate flow, not in this chain.
- Full-book runs forbidden until sample→review→index loop is validated end-to-end (per phase brief).
