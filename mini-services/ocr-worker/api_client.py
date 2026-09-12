"""Controlled writeback client — the ONLY path from worker to database.

All writes go through the Next.js admin API (small JSON payloads: text +
scores + metadata). PDFs and page images are NEVER sent over HTTP; the
worker reads the original from local `storage/` and only the extracted
results travel. Every call carries the admin key; failures raise ApiError.
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str = ""):
        super().__init__(f"API {status}: {message}")
        self.status = status
        self.message = str(message)


class AdminApiClient:
    def __init__(self, base_url: str, admin_key: str, timeout_s: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_s
        self._s = requests.Session()
        self._s.headers.update({"Content-Type": "application/json", "x-admin-key": admin_key})
        retry = Retry(total=3, backoff_factor=1.0, status_forcelist=(502, 503, 504))
        self._s.mount("http://", HTTPAdapter(max_retries=retry))
        self._s.mount("https://", HTTPAdapter(max_retries=retry))

    def _check(self, res: requests.Response) -> dict:
        try:
            data = res.json()
        except ValueError:
            data = {}
        if not res.ok:
            raise ApiError(res.status_code, (data.get("error") if isinstance(data, dict) else "") or res.text[:300])
        return data if isinstance(data, dict) else {}

    # --- jobs (Phase 2: /api/admin/ingest) ---
    def create_job(self, book_id: str, total_pages: int, volume: int = 1, metadata: dict | None = None) -> dict:
        res = self._s.post(
            f"{self.base_url}/api/admin/ingest",
            json={"bookId": book_id, "totalPages": total_pages, "volume": volume, "metadata": metadata or {}},
            timeout=self.timeout,
        )
        return self._check(res)

    def get_job(self, job_id: str) -> dict:
        res = self._s.get(f"{self.base_url}/api/admin/ingest", params={"jobId": job_id}, timeout=self.timeout)
        return self._check(res)

    def get_book_record(self, book_id: str) -> dict:
        """Book row incl. sourceChecksum (for source-integrity verification)."""
        res = self._s.get(
            f"{self.base_url}/api/admin/resource",
            params={"entity": "book", "id": book_id},
            timeout=self.timeout,
        )
        return self._check(res)

    def advance_job(self, job_id: str, to: str) -> dict:
        res = self._s.patch(
            f"{self.base_url}/api/admin/ingest",
            json={"jobId": job_id, "action": "advance", "to": to},
            timeout=self.timeout,
        )
        return self._check(res)

    # --- pages (Phase 2: /api/admin/pages) ---
    def list_pages(self, job_id: str | None = None, book_id: str | None = None, review_only: bool = False, take: int = 500) -> dict:
        params: dict = {}
        if job_id:
            params["jobId"] = job_id
        if book_id:
            params["bookId"] = book_id
        if review_only:
            params["reviewOnly"] = "1"
        params["take"] = str(max(1, min(take, 500)))
        res = self._s.get(f"{self.base_url}/api/admin/pages", params=params, timeout=self.timeout)
        return self._check(res)

    def write_page_ocr(
        self,
        page_id: str,
        ocr_text: str,
        confidence: float | None,
        language: str,
        engine: str,
        checksum: str | None,
        normalized_text: str | None = None,
        signals: dict | None = None,
        needs_review: bool = False,
        blank: bool = False,
    ) -> dict:
        import json as _json

        res = self._s.patch(
            f"{self.base_url}/api/admin/pages",
            json={
                "pageId": page_id,
                "action": "ocr",
                "ocrText": ocr_text,
                "ocrConfidence": confidence,
                "language": language,
                "engine": engine,
                "checksum": checksum,
                "normalizedText": normalized_text,
                "signals": _json.dumps(signals) if signals is not None else None,
                "needsReview": needs_review,
                "blank": blank,
            },
            timeout=self.timeout,
        )
        return self._check(res)

    def write_page_ocr2(
        self,
        page_id: str,
        ocr_text: str,
        confidence: float | None,
        engine: str,
    ) -> dict:
        """Phase 13 secondary capture (action ocr2). Small JSON only."""
        res = self._s.patch(
            f"{self.base_url}/api/admin/pages",
            json={
                "pageId": page_id,
                "action": "ocr2",
                "ocrTextSecondary": ocr_text,
                "ocrConfidenceSecondary": confidence,
                "engineSecondary": engine,
            },
            timeout=self.timeout,
        )
        return self._check(res)

    def record_secondary_error(self, page_id: str, error: str) -> dict:
        res = self._s.patch(
            f"{self.base_url}/api/admin/pages",
            json={"pageId": page_id, "action": "ocr2", "secondaryError": error[:500]},
            timeout=self.timeout,
        )
        return self._check(res)

    def flag_page_review(self, page_id: str, note: str) -> dict:
        res = self._s.patch(
            f"{self.base_url}/api/admin/pages",
            json={"pageId": page_id, "action": "fail", "error": note[:500]},
            timeout=self.timeout,
        )
        return self._check(res)
