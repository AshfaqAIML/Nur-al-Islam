"""Resource measurement (Phase 9, Part 17).

Separates one-time model-load cost from per-page cost. Hardware + versions
are recorded with every measurement (runtimes are meaningless without them).
GPU memory reported only when torch+CUDA present; CPU RSS via psutil when
available, else null (never fabricated).
"""
from __future__ import annotations

import os
import platform
import sys
import time


def environment_fingerprint() -> dict:
    info = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["gpu_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        info["torch"] = None
        info["cuda_available"] = False
    for pkg in ("easyocr", "paddleocr", "pytesseract", "surya", "numpy", "PIL"):
        try:
            mod = __import__(pkg)
            info[f"{pkg}_version"] = getattr(mod, "__version__", "?")
        except ImportError:
            info[f"{pkg}_version"] = None
    return info


def rss_mb() -> float | None:
    try:
        import psutil

        return psutil.Process().memory_info().rss / 1048576
    except ImportError:
        return None


def gpu_mb() -> float | None:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.memory_allocated(0) / 1048576
    except ImportError:
        pass
    return None


class Timer:
    """Context manager recording wall seconds + RSS delta."""

    def __init__(self, label: str):
        self.label = label
        self.seconds = 0.0
        self.rss_before: float | None = None
        self.rss_after: float | None = None

    def __enter__(self) -> "Timer":
        self.rss_before = rss_mb()
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.seconds = time.perf_counter() - self._t0
        self.rss_after = rss_mb()

    def record(self) -> dict:
        return {"label": self.label, "seconds": self.seconds,
                "rss_before_mb": self.rss_before, "rss_after_mb": self.rss_after,
                "gpu_mb": gpu_mb()}


def per_page_stats(page_seconds: list[float]) -> dict:
    if not page_seconds:
        return {"n": 0, "seconds_per_page": None, "pages_per_minute": None}
    mean = sum(page_seconds) / len(page_seconds)
    return {"n": len(page_seconds), "seconds_per_page": mean,
            "pages_per_minute": (60.0 / mean) if mean > 0 else None,
            "min_s": min(page_seconds), "max_s": max(page_seconds)}
