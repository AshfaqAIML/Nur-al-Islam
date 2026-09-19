"""Generate small eval fixtures + ground truth (committable, <1MB total).

Every fixture image is rendered from FIXTURE_STRINGS below (human-authored
→ valid GT source "fixture", never model output). Run:
    python eval/make_fixtures.py
Outputs: eval/samples/{category}/*.png + eval/ground_truth/{category}/*.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.abspath(__file__))
ARIAL = r"C:\Windows\Fonts\arial.ttf"


def shape(s):
    return get_display(arabic_reshaper.reshape(s))


FIXTURES = [
    ("urdu", "fatawa-line", ["یہ آزمائشی سطر ہے"], "ur", False, {}),
    ("urdu", "wudu-line", ["حنفی فقہ میں وضو کے فرائض چار ہیں"], "ur", False, {}),
    ("arabic", "basmala", ["بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"], "ar", False, {}),
    ("arabic", "tahara", ["كتاب الطهارة باب فرائض الوضوء"], "ar", False, {}),
    ("mixed", "bab-mixed", ["باب الوضوء — The Chapter of Ablution"], "mixed", False, {}),
    ("degraded", "blur-line", ["یہ دھندلی سطر ہے"], "ur", False, {"blur": 1.6}),
    ("degraded", "noise-line", ["شور والی سطر"], "ur", False, {"noise": 18}),
    ("difficult", "small-line", ["چھوٹا متن"], "ur", False, {"font_px": 22}),
    ("footnotes", "footnote", ["حاشیہ: یہ چھوٹی وضاحت ہے"], "ur", False, {"font_px": 26}),
    ("headings", "heading", ["باب الطہارۃ"], "ur", False, {"font_px": 72}),
    ("quran", "ayah", ["ذَٰلِكَ الْكِتَابُ لَا رَيْبَ فِيهِ"], "ar", False, {}),
]


def render(lines, font_px=44, blur=0.0, noise=0.0):
    import numpy as np

    W, H = 900, 260
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(ARIAL, font_px)
    y = 60
    for line in lines:
        shown = shape(line)
        bbox = d.textbbox((0, 0), shown, font=font)
        d.text((W - 60 - (bbox[2] - bbox[0]), y), shown, font=font, fill="black")
        y += font_px + 30
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        arr = np.array(img).astype(np.int16)
        arr = (arr + np.random.default_rng(7).normal(0, noise, arr.shape)).clip(0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
    return img


def main():
    for cat, name, lines, lang, _rtl, opts in FIXTURES:
        img = render(lines, **opts)
        img_path = os.path.join(ROOT, "samples", cat, f"{name}.png")
        os.makedirs(os.path.dirname(img_path), exist_ok=True)
        img.save(img_path)
        gt = {
            "sample_id": f"{cat}/{name}",
            "language": lang,
            "script": "arab" if lang in ("ur", "ar") else "mixed",
            "source": "fixture",
            "source_note": "rendered from authored FIXTURE_STRINGS in eval/make_fixtures.py",
            "lines": [{"text": ln, "bbox": None} for ln in lines],
        }
        gt_path = os.path.join(ROOT, "ground_truth", cat, f"{name}.json")
        os.makedirs(os.path.dirname(gt_path), exist_ok=True)
        with open(gt_path, "w", encoding="utf-8") as f:
            json.dump(gt, f, ensure_ascii=False, indent=1)
        print(f"wrote {img_path}")
    # fix script label for mixed (contains Latin → mixed script)
    p = os.path.join(ROOT, "ground_truth", "mixed", "bab-mixed.json")
    with open(p, encoding="utf-8") as f:
        gt = json.load(f)
    gt["script"] = "mixed"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
