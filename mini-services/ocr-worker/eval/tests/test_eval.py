"""Eval framework tests — no models, no network, deterministic."""
import json
import os

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
from config import WorkerConfig


def test_edit_ops_counts():
    r = metrics.edit_ops(list("kitten"), list("sitting"))
    assert (r["substitutions"], r["deletions"], r["insertions"]) == (2, 0, 1)
    assert r["distance"] == 3
    assert metrics.edit_ops([], [])["distance"] == 0


def test_cer_wer_known_values():
    c = metrics.cer("abc", "axc")
    assert abs(c["cer"] - 1 / 3) < 1e-9 and c["substitutions"] == 1
    assert metrics.cer("", "")["cer"] == 0.0
    assert metrics.cer("", "x")["cer"] == 1.0
    w = metrics.wer("a b c", "a x c d")
    assert abs(w["wer"] - 2 / 3) < 1e-9  # 1 sub + 1 ins over 3 ref words
    assert w["insertions"] == 1 and w["deletions"] == 0


def test_normalization_modes_documented_and_split():
    assert len(normalization.NORMALIZATION_RULES) >= 5
    ref, hyp = "ABC", "ABC"
    b = normalization.normalization_breakdown(ref, hyp)
    assert b["raw_cer"] == 0.0 and b["residual_cer"] == 0.0
    # diacritic-only difference vanishes in normalized mode, stays in raw
    assert normalization.strip_diacritics_only("X") == "X"
    assert normalization.unicode_only("X") == "X"


def test_dataset_discovers_categories_incrementally(tmp_path):
    (tmp_path / "samples" / "urdu").mkdir(parents=True)
    (tmp_path / "samples" / "urdu" / "a.png").write_bytes(b"x")
    (tmp_path / "samples" / "weird").mkdir()
    (tmp_path / "samples" / "weird" / "b.png").write_bytes(b"x")
    d = dataset.discover_dataset(str(tmp_path))
    assert [s["id"] for s in d["samples"]] == ["urdu/a"]
    assert any("weird" in w for w in d["warnings"])
    assert dataset.load_ground_truth(d["samples"][0]) is None  # no GT → unevaluated


def test_ground_truth_validation():
    good = {"sample_id": "u/a", "language": "ur", "script": "arab", "source": "human",
            "lines": [{"text": "x", "bbox": None}], "reading_order": [0]}
    assert ground_truth.validate_ground_truth(good) == []
    assert ground_truth.reference_text(good) == "x"
    bad = {"sample_id": "u/a", "language": "xx", "script": "arab", "source": "model",
           "lines": [{"ntext": 1}]}
    problems = ground_truth.validate_ground_truth(bad)
    assert any("language" in p for p in problems)
    assert any("source" in p for p in problems)
    assert any("line 0" in p for p in problems)
    # model output is never a valid source
    assert "model" not in ground_truth.VALID_SOURCES


def test_engine_registry_statuses():
    assert set(engines_eval.REGISTRY) >= {"easyocr", "tesseract", "paddleocr", "surya", "qaari", "native-extract"}
    kinds = {k: v.kind for k, v in engines_eval.REGISTRY.items()}
    assert kinds["qaari"] == "experimental"
    assert kinds["easyocr"] == "local"
    # missing engines report SKIPPED (never raise, never required)
    class _Fake:
        def probe(self):
            from engines_eval import EngineProbe
            return EngineProbe(False, "SKIPPED", reason="test")
    assert _Fake().probe().status == "SKIPPED"
    t = engines_eval.REGISTRY["tesseract"].probe()
    assert t.status in ("AVAILABLE", "SKIPPED")
    p = engines_eval.REGISTRY["paddleocr"].probe()
    assert p.status in ("AVAILABLE", "SKIPPED")
    if p.status == "SKIPPED":
        assert "reason" in p.__dict__ and p.reason


def test_preprocess_variants_exact():
    assert set(preprocess_variants.VARIANTS) >= {"raw", "deskew", "contrast", "restored"}
    try:
        preprocess_variants.apply_variant(None, "nope", WorkerConfig())
        raise AssertionError("must raise")
    except ValueError:
        pass


def test_layout_metrics_separate_from_cer():
    assert layout_metrics.iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert layout_metrics.iou([0, 0, 1, 1], [5, 5, 6, 6]) == 0.0
    d = layout_metrics.detection_scores([[0, 0, 10, 10]], [[0, 0, 10, 10]])
    assert d["f1"] == 1.0 and d["false_positives"] == 0
    assert layout_metrics.kendall_tau_distance([0, 1, 2], [0, 1, 2]) == 0.0
    assert layout_metrics.kendall_tau_distance([2, 1, 0], [0, 1, 2]) == 1.0
    r = layout_metrics.reading_order_score(["a", "b"], ["a", "b"])
    assert r["order_distance"] == 0.0 and r["matched_lines"] == 2


def test_language_split_never_single_only():
    recs = [{"language": "ur", "cer": 0.1}, {"language": "ur", "cer": 0.3},
            {"language": "ar", "cer": 0.2}]
    agg = lang_mod.aggregate_by_language(recs)
    assert agg["ur"]["n"] == 2 and abs(agg["ur"]["mean_cer"] - 0.2) < 1e-9
    assert agg["ar"]["mean_cer"] == 0.2
    assert agg["mixed"]["mean_cer"] is None
    assert agg["combined"]["n"] == 3  # accompanies, never replaces


def test_calibration_and_review_stats():
    recs = [{"mean_confidence": 0.9, "cer": 0.0, "verdict": "OK"},
            {"mean_confidence": 0.3, "cer": 0.5, "verdict": "REVIEW"},
            {"mean_confidence": 0.8, "cer": 0.4, "verdict": "OK"}]
    bins = calibration.calibration_bins(recs, bins=2)
    assert len(bins) == 2 and bins[1]["n"] == 2
    s = calibration.review_signal_stats(recs, error_thresh=0.05)
    assert (s["true_positives"], s["false_negatives"], s["false_positives"]) == (1, 1, 0)
    assert abs(s["review_rate"] - 1 / 3) < 1e-9


def test_error_classes_and_artifacts(tmp_path):
    e = errors.classify_errors("a b c", "a x c d")
    assert e["summary"]["substitution"] == 1 and e["summary"]["insertion"] == 1
    e2 = errors.classify_errors("a b", "b a")
    assert e2["summary"]["rtl_order"] == 1
    case = errors.save_case(str(tmp_path), "c1", None, {"sample_id": "s"}, "hyp")
    assert os.path.isfile(os.path.join(case, "hypothesis.txt"))
    assert os.path.isfile(os.path.join(case, "ground_truth.json"))


def test_reports_serialize(tmp_path):
    payload = {"run_id": "t", "environment": {"platform": "P", "python": "3"},
               "skipped_engines": [{"engine": "x", "status": "SKIPPED", "reason": "r"}],
               "engines": [{"engine": "e", "display": "E", "model": "m", "model_version": "v",
                            "device": "cpu", "pages": 1,
                            "cuts": [{"cut": "all", "n": 1, "raw_cer": 0.1, "normalized_cer": 0.05, "wer": 0.2, "seconds_per_page": 3.0}],
                            "calibration": []}],
               "records": [], "notes": "n"}
    j = reports.write_json(str(tmp_path / "r.json"), payload)
    c = reports.write_csv(str(tmp_path / "r.csv"), [])
    m = reports.write_markdown(str(tmp_path / "r.md"), payload)
    assert os.path.getsize(j) > 100 and os.path.getsize(m) > 100
    assert json.load(open(j))["run_id"] == "t"
    assert "SKIPPED" in open(m, encoding="utf-8").read()
    assert os.path.getsize(c) > 0


def test_domain_and_consensus():
    hits = domain.domain_hits("ABC", terms=["AB", "ZZ"])
    assert hits == {"AB": True, "ZZ": False}
    rep = domain.domain_report([{"engine": "e", "hits": {"AB": True}}, {"engine": "e", "hits": {"AB": False}}])
    assert rep["e"]["AB"] == 0.5
    assert domain.consensus(["x", "x"])["full_agreement"] is True
    assert domain.consensus(["x", "y"])["pair_agreement_rate"] == 0.0


def test_line_level_partial_gt():
    """Line-sampled GT: matched CER + coverage, unmatched = full miss."""
    from metrics import line_level

    ll = line_level(["a b c", "d e"], ["a b c", "zzz"], fold=lambda s: s)
    assert ll["matched"] == 1 and ll["n_gt"] == 2
    assert ll["pairs"][0]["cer"] == 0.0
    assert ll["pairs"][1]["hyp"] is None and ll["pairs"][1]["cer"] == 1.0
    # coverage: a,b,c,d,e = 5 toks, hyp has a,b,c + zzz → 3/5
    assert abs(ll["coverage"] - 0.6) < 1e-9
    # folded matching bridges spelling variants
    ll2 = line_level(["AB"], ["ab"], fold=str.lower)
    assert ll2["matched"] == 1 and ll2["pairs"][0]["cer"] == 1.0  # CER stays raw


def test_native_extract_baseline(tmp_path):
    """Part 21: native PDF text extraction as a scored baseline candidate."""
    import fitz

    from engines_eval import NativeExtractAdapter

    pdf = str(tmp_path / "d.pdf")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 80), "wudu face tahara", fontsize=14)
    doc.save(pdf)
    doc.close()
    res = NativeExtractAdapter().run(pdf_path=pdf, page_no=1)
    assert "wudu" in res.text
    assert res.mean_confidence == 1.0
    assert res.engine == "native-extract"
