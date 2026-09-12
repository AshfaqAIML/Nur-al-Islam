"""Preprocessing is adaptive, logged, and never mutates the original."""
from PIL import Image

from config import WorkerConfig
from conftest import sample
from preprocess import estimate_skew_deg, preprocess
from renderer import open_pdf, render_page


def _render(name: str) -> Image.Image:
    with open_pdf(sample(name)) as doc:
        return render_page(doc, 1, dpi=200)


def test_original_not_mutated():
    img = _render("poor_quality.pdf")
    before = img.tobytes()
    _, applied = preprocess(img, WorkerConfig())
    assert img.tobytes() == before
    assert isinstance(applied, list)


def test_degraded_page_gets_corrective_steps():
    img = _render("poor_quality.pdf")
    out, applied = preprocess(img, WorkerConfig())
    assert len(applied) >= 1, "degraded fixture should trigger ≥1 adaptive step"
    assert out.size[0] > 0 and out.size[1] > 0


def test_clean_page_passes_through_lightly():
    img = _render("scanned_urdu.pdf")
    _, applied = preprocess(img, WorkerConfig())
    # clean synthetic page: deskew angle ~0, no crop/background over-trigger
    assert not any(a.startswith("deskew") for a in applied), applied


def test_deskew_detects_rotation():
    img = _render("scanned_urdu.pdf")
    rotated = img.rotate(5, expand=True, fillcolor="white")
    from preprocess import _to_gray

    angle = estimate_skew_deg(_to_gray(rotated))
    assert abs(angle) > 0.5, f"expected measurable skew, got {angle}"
    # ...and preprocessing a rotated page records the correction
    _, applied = preprocess(rotated, WorkerConfig())
    assert any(a.startswith("deskew") for a in applied), applied


def test_all_steps_can_disable():
    cfg = WorkerConfig(
        enable_deskew=False, enable_crop=False, enable_background=False,
        enable_denoise=False, enable_contrast=False, enable_deblur=False,
    )
    img = _render("poor_quality.pdf")
    out, applied = preprocess(img, cfg)
    assert applied == []
    assert out.size == img.size
