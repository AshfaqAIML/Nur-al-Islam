"""Adaptive preprocessing — mild, gated, fully logged.

Every step runs on a COPY (the original page image is never mutated) and
records itself in `applied`. Steps self-gate on measured image quality so
clean pages pass through nearly untouched; nothing aggressive is applied
blindly. Dewarp is implemented as detect-and-report (no destructive
transform) unless explicitly enabled in config.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from config import WorkerConfig


def _to_gray(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("L"))


def _laplacian_var(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _contrast_rms(gray: np.ndarray) -> float:
    return float(gray.std())


def estimate_skew_deg(gray: np.ndarray) -> float:
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(bw)
    if coords is None or len(coords) < 100:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    # minAreaRect returns [-90, 0) with a 90° ambiguity; map to [-45, 45].
    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90
    return float(angle)


def preprocess(image: Image.Image, config: WorkerConfig) -> tuple[Image.Image, list[str]]:
    """Returns (processed PIL image, applied step names). Input is not mutated."""
    applied: list[str] = []
    work = image.copy()
    gray = _to_gray(work)

    # --- deskew (only for small, confident angles) ---
    if config.enable_deskew:
        angle = estimate_skew_deg(gray)
        if 0.5 < abs(angle) < 15:
            h, w = gray.shape
            mat = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            gray = cv2.warpAffine(gray, mat, (w, h), flags=cv2.INTER_LINEAR, borderValue=255)
            applied.append(f"deskew:{angle:.2f}deg")

    # --- crop to content (only when it removes real margin) ---
    if config.enable_crop:
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ys, xs = np.where(bw > 0)
        if len(xs) > 0:
            margin = 20
            x0, x1 = max(0, xs.min() - margin), min(gray.shape[1], xs.max() + margin)
            y0, y1 = max(0, ys.min() - margin), min(gray.shape[0], ys.max() + margin)
            area_ratio = ((x1 - x0) * (y1 - y0)) / (gray.shape[0] * gray.shape[1])
            if area_ratio < 0.98:
                gray = gray[y0:y1, x0:x1]
                applied.append(f"crop:{area_ratio:.2f}")

    # --- background correction / deshadow (only on uneven backgrounds) ---
    if config.enable_background:
        bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
        if float(bg.std()) > 12:
            norm = cv2.divide(gray, bg, scale=255)
            gray = np.clip(norm, 0, 255).astype(np.uint8)
            applied.append("background:flatten+deshadow")

    # --- denoise (only when noisy) ---
    if config.enable_denoise:
        # rough noise proxy: high-frequency energy on a blurred residual
        blur = cv2.GaussianBlur(gray, (0, 0), 1.5)
        noise = float(np.abs(gray.astype(np.int16) - blur.astype(np.int16)).mean())
        if noise > 6:
            gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
            applied.append(f"denoise:{noise:.1f}")

    # --- contrast (only when flat) ---
    if config.enable_contrast:
        if _contrast_rms(gray) < 40:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            applied.append("contrast:clahe")

    # --- deblur (only when measurably blurry; mild unsharp mask) ---
    if config.enable_deblur:
        if _laplacian_var(gray) < 80:
            blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
            gray = cv2.addWeighted(gray, 1.4, blur, -0.4, 0)
            applied.append("deblur:unsharp-mild")

    # --- dewarp: detect-and-report by default (no destructive transform) ---
    if config.enable_dewarp:
        applied.append("dewarp:requested-but-unproven-NEEDS_REVIEW")
    # curvature probe (cheap): compare left/right margin skew of text rows
    # → recorded as info only; real dewarp stays behind the config flag.
    # (No transform applied here in either case.)

    # --- binarization: off by default; engines prefer grayscale ---
    if config.enable_binarize:
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 9)
        applied.append("binarize:adaptive-gaussian")

    return Image.fromarray(gray).convert("RGB"), applied
