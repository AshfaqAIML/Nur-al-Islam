# Nur OCR Worker (Phase 3)

Server-side book processing worker. Reads original PDFs from local `storage/`,
processes one page at a time, writes results back through the Next.js admin API.
Full documentation: `docs/PYTHON_PROCESSOR.md` (repo root).

```bash
pip install -r requirements.txt        # or: pip install -e ".[dev]"
python samples/make_samples.py        # build the 5 sample fixtures
python -m pytest tests/ -q            # unit tests (fast, no models)
python -m pytest tests/test_samples.py -q  # sample validation (needs EasyOCR models)

# dry run — no server needed
python runner.py --dry-run --pdf samples/out/digital_en.pdf --pages 1

# real run against a Phase 2 job
NUR_ADMIN_KEY=... python runner.py --pdf /path/original.pdf --job-id <id> --book-id <id>
NUR_ADMIN_KEY=... python runner.py --pdf /path/original.pdf --book-id <id> --create-job --limit 20
```
