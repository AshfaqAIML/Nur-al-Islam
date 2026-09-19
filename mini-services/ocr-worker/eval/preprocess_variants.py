"""Preprocessing variants (Phase 9, Part 10).

Each variant maps to production preprocess flags — no new image code.
`raw` is always measured (the no-preprocessing baseline). Every test record
carries the exact variant name; more preprocessing is never assumed better.
"""
from __future__ import annotations

VARIANTS: dict[str, dict] = {
    "raw": {},
    "deskew": {"enable_deskew": True},
    "contrast": {"enable_contrast": True},
    "deshadow": {"enable_background": True},
    "denoise": {"enable_denoise": True},
    "background": {"enable_background": True, "enable_contrast": True},
    "deblur": {"enable_deblur": True},
    "restored": {  # production default bundle (all safe steps on)
        "enable_deskew": True, "enable_crop": True, "enable_background": True,
        "enable_denoise": True, "enable_contrast": True, "enable_deblur": True,
    },
}


def apply_variant(image, variant: str, base_config):
    """Preprocess a COPY under variant flags. Returns (image, applied_steps)."""
    import copy

    if variant not in VARIANTS:
        raise ValueError(f"unknown preprocessing variant: {variant}")
    cfg = copy.copy(base_config)
    # start from everything OFF so variants are exact (except raw = passthrough)
    for flag in ("enable_deskew", "enable_crop", "enable_background", "enable_denoise",
                 "enable_contrast", "enable_deblur", "enable_dewarp", "enable_binarize"):
        setattr(cfg, flag, False)
    for flag, value in VARIANTS[variant].items():
        setattr(cfg, flag, value)
    if variant == "raw":
        return image.copy(), []
    from preprocess import preprocess

    return preprocess(image, cfg)
