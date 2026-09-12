"""Worker configuration — every model/engine/threshold overridable via env.

Conventions: OCR_PRIMARY_ENGINE selects the first engine in the chain,
OCR_FALLBACK_ENGINES is comma-separated. Model versions are explicit so
results stay reproducible (stored per page in `engine`/`model_version`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _getenv(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _getint(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _getfloat(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _getbool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class WorkerConfig:
    # --- engines (registry keys in engines/__init__.py) ---
    primary_engine: str = "easyocr"
    fallback_engines: list[str] = field(default_factory=lambda: ["tesseract"])
    # HTR is an abstraction only (engines/htr.py); "htr" in the chain means
    # handwritten candidates are flagged for review, never silently OCR'd.
    htr_engine: str = "htr-stub"
    easyocr_langs: list[str] = field(default_factory=lambda: ["ar", "en"])
    easyocr_model_version: str = "easyocr-1.7.2/craft_mlt_25k+arabic"
    tesseract_langs: str = "urd+ara+eng"
    tesseract_cmd: str = "tesseract"

    # --- PDF routing thresholds ---
    digital_min_chars: int = 50      # embedded chars to trust digital extraction
    blank_ink_coverage: float = 0.002  # below this → BLANK (skip OCR spend)
    render_dpi: int = 200
    thumb_dpi: int = 100             # cheap render used only for routing stats

    # --- preprocessing (adaptive; each step self-gates, see preprocess.py) ---
    enable_deskew: bool = True
    enable_crop: bool = True
    enable_background: bool = True
    enable_denoise: bool = True
    enable_contrast: bool = True
    enable_deblur: bool = True
    enable_dewarp: bool = False      # perspective correction — off unless curvature proven
    enable_binarize: bool = False    # engines prefer grayscale; binarize only on demand

    # --- secondary capture (Phase 13: review-routed dual capture) ---
    # review  = second opinion only when the primary needs review
    # always  = every page with primary text (explicit opt-in)
    # off     = single capture (rollback switch, no code change)
    secondary_mode: str = "review"
    secondary_engine: str = "tesseract"
    secondary_min_conf: float = 0.5  # review-mode trigger threshold

    # --- runner ---
    api_base: str = "http://localhost:3000"
    request_timeout_s: int = 60
    max_pages_per_run: int = 0       # 0 = no cap (use --limit per invocation instead)

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        fallbacks = [s.strip() for s in _getenv("OCR_FALLBACK_ENGINES", "tesseract").split(",") if s.strip()]
        mode = _getenv("OCR_SECONDARY_MODE", "review").strip().lower()
        if mode not in ("review", "always", "off"):
            mode = "review"
        cfg = cls(
            primary_engine=_getenv("OCR_PRIMARY_ENGINE", "easyocr"),
            fallback_engines=fallbacks,
            htr_engine=_getenv("OCR_HTR_ENGINE", "htr-stub"),
            easyocr_langs=[s.strip() for s in _getenv("OCR_EASYOCR_LANGS", "ar,en").split(",") if s.strip()],
            easyocr_model_version=_getenv("OCR_EASYOCR_MODEL", "easyocr-1.7.2/craft_mlt_25k+arabic"),
            tesseract_langs=_getenv("OCR_TESSERACT_LANGS", "urd+ara+eng"),
            tesseract_cmd=_getenv("OCR_TESSERACT_CMD", "tesseract"),
            digital_min_chars=_getint("OCR_DIGITAL_MIN_CHARS", 50),
            blank_ink_coverage=_getfloat("OCR_BLANK_COVERAGE", 0.002),
            render_dpi=_getint("OCR_RENDER_DPI", 200),
            thumb_dpi=_getint("OCR_THUMB_DPI", 100),
            enable_deskew=_getbool("OCR_PRE_DESKEW", True),
            enable_crop=_getbool("OCR_PRE_CROP", True),
            enable_background=_getbool("OCR_PRE_BACKGROUND", True),
            enable_denoise=_getbool("OCR_PRE_DENOISE", True),
            enable_contrast=_getbool("OCR_PRE_CONTRAST", True),
            enable_deblur=_getbool("OCR_PRE_DEBLUR", True),
            enable_dewarp=_getbool("OCR_PRE_DEWARP", False),
            enable_binarize=_getbool("OCR_PRE_BINARIZE", False),
            secondary_mode=mode,
            secondary_engine=_getenv("OCR_SECONDARY_ENGINE", "tesseract"),
            secondary_min_conf=_getfloat("OCR_SECONDARY_MIN_CONF", 0.5),
            api_base=_getenv("NUR_API_BASE", "http://localhost:3000"),
            request_timeout_s=_getint("NUR_API_TIMEOUT_S", 60),
        )
        return cfg
