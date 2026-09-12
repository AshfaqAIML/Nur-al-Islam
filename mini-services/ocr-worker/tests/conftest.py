import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "out")


def ensure_samples() -> None:
    need = ["digital_en.pdf", "digital_ur.pdf", "scanned_urdu.pdf", "arabic_mixed.pdf", "poor_quality.pdf"]
    if all(os.path.exists(os.path.join(OUT, n)) for n in need):
        return
    subprocess.run([sys.executable, "samples/make_samples.py"], check=True,
                   cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sample(name: str) -> str:
    ensure_samples()
    return os.path.join(OUT, name)


def expected(name: str) -> list[str]:
    with open(sample(name) + ".expected.txt", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]
