"""Generate 5 small representative sample PDFs (fixtures, not real books).

Regenerate anytime: python samples/make_samples.py
Outputs go to samples/out/ (gitignored). Expected-text files sit alongside
for test assertions. Urdu/Arabic shaping via arabic_reshaper + python-bidi
(PIL/PyMuPDF have no complex-text shaper here); system Arial renders the
Arabic block incl. Urdu-specific glyphs.
"""
from __future__ import annotations

import os
import random

import arabic_reshaper
import fitz  # PyMuPDF
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
ARIAL = r"C:\Windows\Fonts\arial.ttf"

URDU_TEXT = [
    "یہ ایک آزمائشی صفحہ ہے",
    "حنفی فقہ میں وضو کے فرائض چار ہیں",
    "چہرہ دھونا، کہنیوں سمیت ہاتھ دھونا",
    "سر کا مسح کرنا اور ٹخنوں سمیت پاؤں دھونا",
]
ARABIC_TEXT = [
    "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
    "الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ",
    "كتاب الطهارة باب فرائض الوضوء",
]
EN_TEXT = [
    "The Hanafi school requires four integrals for wudu:",
    "washing the face, washing the arms including elbows,",
    "wiping a portion of the head, washing the feet including ankles.",
]
MIXED_TEXT = [
    "باب الوضوء — The Chapter of Ablution",
    "فرائض الوضوء أربعة — The integrals of wudu are four",
    "غسل الوجه — washing the face (page 112)",
]


def shape(line: str) -> str:
    return get_display(arabic_reshaper.reshape(line))


def digital_pdf(path: str, lines: list[str], shape_arabic: bool) -> None:
    digital_multipage(path, [lines], shape_arabic)


def digital_multipage(path: str, pages: list[list[str]], shape_arabic: bool) -> None:
    # NOTE: digital fixtures insert LOGICAL (unshaped) text on purpose.
    # PyMuPDF cannot shape complex scripts: pre-shaped visual strings embed
    # with a broken ToUnicode map (extraction returns tofu). Logical-order
    # insertion maps 1:1 → extraction is exact. Rendering looks disconnected
    # (no shaper here) — these fixtures validate the pipeline, not typography.
    # Scanned fixtures (PIL-rendered, correctly shaped) cover visual fidelity.
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page(width=595, height=842)
        y = 80
        for line in lines:
            shown = shape(line) if shape_arabic else line
            page.insert_text((60, y), shown, fontfile=ARIAL, fontsize=14)
            y += 26
            if y > 800:
                page = doc.new_page(width=595, height=842)
                y = 80
    doc.save(path)
    doc.close()


def scan_image(lines: list[str], shape_arabic: bool, size=(1240, 1754), font_px: int = 44, gap: int = 80, top: int = 120) -> Image.Image:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(ARIAL, font_px)
    y = top
    for line in lines:
        shown = shape(line) if shape_arabic else line
        # right-align Arabic-script lines (RTL page look), left-align Latin
        bbox = d.textbbox((0, 0), shown, font=font)
        w = bbox[2] - bbox[0]
        x = size[0] - 120 - w if shape_arabic else 120
        d.text((x, y), shown, font=font, fill="black")
        y += gap
    return img


def save_scan_pdf(img: Image.Image, path: str) -> None:
    """Embed a rendered page image as a single-page PDF (image-only → scanned)."""
    import io

    doc = fitz.open()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc.new_page(width=595, height=842)
    doc[-1].insert_image(doc[-1].rect, stream=buf.getvalue())
    doc.save(path)
    doc.close()


def degrade(img: Image.Image, seed: int = 7) -> Image.Image:
    rnd = random.Random(seed)
    img = img.rotate(2.5, expand=True, fillcolor="white")
    img = img.filter(ImageFilter.GaussianBlur(1.6))
    import numpy as np

    arr = np.array(img).astype(np.int16)
    noise = np.random.default_rng(seed).normal(0, 18, arr.shape).astype(np.int16)
    arr = np.clip((arr * 0.82) + noise, 0, 255).astype(np.uint8)
    out = Image.fromarray(arr)
    d = ImageDraw.Draw(out)
    for _ in range(12):  # speckles / shadow blotches
        x, y = rnd.randint(0, out.width), rnd.randint(0, out.height)
        d.ellipse([x, y, x + rnd.randint(20, 120), y + rnd.randint(10, 60)], fill=(235, 235, 230))
    return out


def write_expected(path: str, needles: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(needles))


FATAWA_P1 = [
    "فتاویٰ رضویہ شریف",
    "جلد 4",
    "باب الطہارۃ",
    "مسئلہ نمبر 112",
    "سوال: وضو میں مسح کا طریقہ کیا ہے؟",
    "جواب: سر کے چوتھائی حصے کا مسح فرض ہے",
    "اور پورے سر کا مسح سنت ہے",
]
FATAWA_P2 = [
    "فتاویٰ رضویہ شریف",
    "جلد 4",
    "مسئلہ نمبر 113",
    "سوال: کیا ناک میں پانی ڈالنا فرض ہے؟",
    "جواب: ناک کی نرم ہڈی تک پانی پہنچانا واجب ہے",
]
TIBYAN_P1 = [
    "تبیان القرآن",
    "سورۃ البقرۃ",
    "آیت 2",
    "پارہ 1",
    "رکوع 1",
    "ذَٰلِكَ الْكِتَابُ لَا رَيْبَ فِيهِ",
    "یہ وہ کتاب ہے جس میں کوئی شک نہیں",
    "متقیوں کے لیے ہدایت ہے",
]
TIBYAN_P2 = [
    "تبیان القرآن",
    "سورۃ البقرۃ",
    "آیت 3 الی 4",
    "پارہ 1",
    "جو لوگ غیب پر ایمان لاتے ہیں",
    "اور نماز قائم کرتے ہیں",
]


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    jobs = [
        ("digital_en.pdf", lambda p: digital_pdf(p, EN_TEXT, False), ["wudu", "elbows", "ankles"]),
        ("digital_ur.pdf", lambda p: digital_pdf(p, URDU_TEXT, False), ["آزمائشی", "وضو", "ٹخنوں"]),
        ("scanned_urdu.pdf", lambda p: save_scan_pdf(scan_image(URDU_TEXT * 3, True), p), ["آزمائشی", "وضو"]),
        ("arabic_mixed.pdf", lambda p: save_scan_pdf(scan_image((MIXED_TEXT + ARABIC_TEXT) * 2, True), p), ["الوضوء", "ablution"]),
        ("poor_quality.pdf", lambda p: save_scan_pdf(degrade(scan_image((URDU_TEXT[:2]) * 4, True)), p), ["آزمائشی"]),
        ("fatawa_razvia_sample.pdf",
         lambda p: save_scan_pdf(scan_image(FATAWA_P1 + FATAWA_P2, True, size=(1240, 1754), font_px=56, gap=100, top=100), p),
         ["رضویہ", "مسئلہ", "سوال", "جواب", "جلد"]),
        ("tibyan_sample.pdf",
         lambda p: save_scan_pdf(scan_image(TIBYAN_P1 + TIBYAN_P2, True, size=(1240, 1754), font_px=56, gap=100, top=100), p),
         ["تبیان", "البقرۃ", "پارہ", "رکوع"]),
    ]
    for name, fn, needles in jobs:
        pdf = os.path.join(OUT, name)
        fn(pdf)
        write_expected(os.path.join(OUT, name + ".expected.txt"), needles)
        print(f"wrote {pdf}")


if __name__ == "__main__":
    main()
