"""Phase 8 tests — storage resolution (no real files needed except tmp)."""
import os

import pytest

from storage import resolve_source_path, sha256_file, storage_root


def test_storage_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("NUR_STORAGE", str(tmp_path))
    assert storage_root() == str(tmp_path)


def test_rejects_absolute_and_traversal(tmp_path):
    with pytest.raises(ValueError):
        resolve_source_path("/etc/passwd", root=str(tmp_path))
    with pytest.raises(ValueError):
        resolve_source_path("../outside.pdf", root=str(tmp_path))
    with pytest.raises(ValueError):
        resolve_source_path("books/../../x.pdf", root=str(tmp_path))
    with pytest.raises(ValueError):
        resolve_source_path("", root=str(tmp_path))


def test_resolves_real_file(tmp_path):
    d = tmp_path / "books" / "abc"
    d.mkdir(parents=True)
    f = d / "original.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    got = resolve_source_path("books/abc/original.pdf", root=str(tmp_path))
    assert got == str(f)


def test_missing_file_is_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_source_path("books/nope/original.pdf", root=str(tmp_path))


def test_sha256_file_matches_hashlib(tmp_path):
    import hashlib

    f = tmp_path / "a.bin"
    f.write_bytes(b"abc" * 1000)
    assert sha256_file(str(f)) == hashlib.sha256(b"abc" * 1000).hexdigest()


def test_job_cancelled_predicate():
    from api_client import ApiError
    from runner import _job_cancelled

    class _Api:
        def __init__(self, status=None, fail=False):
            self._status = status
            self._fail = fail

        def get_job(self, _job_id):
            if self._fail:
                raise ApiError(500, "boom")
            return {"job": {"status": self._status}}

    assert _job_cancelled(_Api("CANCELLED"), "j") is True
    assert _job_cancelled(_Api("ANALYZING"), "j") is False
    assert _job_cancelled(_Api(None), "j") is False
    # transient API errors must NOT abort processing
    assert _job_cancelled(_Api(fail=True), "j") is False
