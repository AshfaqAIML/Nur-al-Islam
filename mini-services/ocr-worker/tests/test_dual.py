"""Phase 13 tests — review-routed dual capture decisions (no models)."""
from config import WorkerConfig
from runner import secondary_complete, should_run_secondary
from schemas import PageResult


def _res(route="SCANNED_PRINTED", text="some words here", conf=0.8, engine="easyocr", verdict="OK"):
    r = PageResult(job_id=None, book_id=None, volume=1, page_number=1, route=route,
                   raw_text=text, normalized_text=text, confidence=conf, language="ur",
                   script="arab", image_width=0, image_height=0, engine=engine,
                   model="m", model_version="v")
    r.signals = {"verdict": verdict}
    return r


def _cfg(**kw):
    base = {f: getattr(WorkerConfig(), f) for f in
            ("secondary_mode", "secondary_engine", "secondary_min_conf")}
    base.update(kw)
    cfg = WorkerConfig()
    for k, v in base.items():
        setattr(cfg, k, v)
    return cfg


def test_off_never_runs():
    cfg = _cfg(secondary_mode="off")
    assert should_run_secondary(_res(), True, cfg, "easyocr") is False
    assert should_run_secondary(_res(conf=0.1), True, cfg, "easyocr") is False


def test_always_runs_on_text_only():
    cfg = _cfg(secondary_mode="always")
    assert should_run_secondary(_res(), False, cfg, "easyocr") is True
    assert should_run_secondary(_res(route="BLANK", text=""), False, cfg, "easyocr") is False
    assert should_run_secondary(_res(text="  "), False, cfg, "easyocr") is False


def test_review_mode_triggers():
    cfg = _cfg(secondary_mode="review")
    assert should_run_secondary(_res(verdict="REVIEW"), False, cfg, "easyocr") is True
    assert should_run_secondary(_res(), True, cfg, "easyocr") is True
    assert should_run_secondary(_res(conf=0.2), False, cfg, "easyocr") is True
    assert should_run_secondary(_res(route="HANDWRITTEN", text="x"), False, cfg, "easyocr") is True
    # clean primary: no second pass
    assert should_run_secondary(_res(), False, cfg, "easyocr") is False
    assert should_run_secondary(_res(conf=0.9), False, cfg, "easyocr") is False


def test_same_engine_never_double_runs():
    cfg = _cfg(secondary_mode="always", secondary_engine="easyocr")
    assert should_run_secondary(_res(), True, cfg, "easyocr") is False


def test_secondary_complete_predicate():
    assert secondary_complete({"ocrTextSecondary": "x"}) is True
    assert secondary_complete({"ocrTextSecondary": None, "signals": '{"secondary": {"status": "done"}}'}) is True
    assert secondary_complete({"ocrTextSecondary": None, "signals": '{"secondary": {"status": "failed"}}'}) is False
    assert secondary_complete({"ocrTextSecondary": None, "signals": None}) is False
    assert secondary_complete({"ocrTextSecondary": None, "signals": "{broken"}) is False
    assert secondary_complete({}) is False


def test_config_modes_validated():
    import os

    os.environ["OCR_SECONDARY_MODE"] = "bogus"
    try:
        assert WorkerConfig.from_env().secondary_mode == "review"
    finally:
        del os.environ["OCR_SECONDARY_MODE"]
