# OCR Evaluation Guide — exact commands

> Working directory for all commands: `mini-services/ocr-worker/`.
> Production pipeline is never touched. Real PDFs stay outside git.

## Add sample pages

1. Copy page images (PNG/JPG/WebP) or single-page PDFs into
   `eval/samples/{urdu,arabic,mixed,degraded,difficult,footnotes,headings,quran}/`
   (create the category dir if missing; unknown dirs are ignored with a warning).
2. Or point at an external collection (nothing committed):
   `NUR_EVAL_DIR=/path/to/real/pages python -m eval.bench ...`

## Add ground truth

Create `eval/ground_truth/{category}/{name}.json` (same relative path as the
sample, `.json` extension):

```json
{
  "sample_id": "urdu/fatawa-p1",
  "language": "ur",
  "script": "arab",
  "source": "human",
  "source_note": "Transcribed by <name>, <date>",
  "lines": [{ "text": "...", "bbox": [x0, y0, x1, y1] }],
  "reading_order": [0, 1]
}
```

- `source` must be `human` (real pages) or `fixture` (authored alongside a
  synthetic fixture). Model output is rejected.
- `bbox` may be `null` (text-only scoring still works; layout metrics skip).
- Validate: the bench validates every GT file and reports problems per file
  instead of crashing.

## Run one engine

```bash
python -m eval.bench --engines easyocr --variants raw,restored --categories urdu,arabic
python -m eval.bench --engines tesseract --variants raw --limit 5
python -m eval.bench --engines paddleocr --variants raw --limit 2
python -m eval.bench --engines native-extract --categories urdu
```

## Run all available engines

```bash
python -m eval.bench --engines all --variants raw,restored
```

Unavailable engines report SKIPPED with reasons; failures record FAILED per
sample. Nothing required to be installed for the lab to run.

## Useful flags

- `--dataset-root PATH` — external collection (same layout, plus GT).
- `--categories urdu,degraded` — subset run.
- `--limit N` — first N discovered samples.
- `--repeat 2` — determinism check (identical CER expected on CPU).
- `--save-cases` — persist error artifacts (image, GT, hypothesis) per miss.

## Generate reports

Every run writes `eval/outputs/<run_id>/results.json`, `results.csv`,
`report.md` (regenerate anytime from `results.json` via `eval/reports.py`).

## Synthetic fixtures (committed)

```bash
python eval/make_fixtures.py   # 11 PNGs + GT, <1MB total
```

## Tests

```bash
python -m pytest eval/tests/ -q   # framework: metrics, GT, registry, reports
```

Run suites separately (`pytest tests/` and `pytest eval/tests/` from
`mini-services/ocr-worker/`): the two `conftest.py` files share a module
name, so a combined single invocation collides — separate commands are the
supported flow.
