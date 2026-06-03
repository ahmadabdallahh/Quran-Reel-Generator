"""
verify_font_rendering.py
========================

End-to-end test of the font-rendering quality fixes.  Run this from
the project root::

    python verify_font_rendering.py

The script:

  1.  Reports Quranic-codepoint coverage for every font in ``fonts/``.
  2.  Confirms the auto-fallback picks a full-coverage font for the
      most common problem cases (Tajawal, Uthman TN1, RanaKufi, ...).
  3.  Renders a Bismillah and an Ayat-al-Kursi image with several
      fonts and saves them to ``verify_out/``.

The image files are written to ``verify_out/`` so you can open them
and confirm visually that the Quranic ligatures (ﷲ, ﷽) form
correctly.
"""

import logging
import os
import sys

# Force UTF-8 in the console (Windows defaults to cp1256 which chokes
# on Arabic codepoints).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Add the project root to sys.path so we can import main.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def banner(text: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {text}\n{bar}")


def main() -> int:
    banner("1. Per-font Quranic-codepoint coverage")
    from quran_reels.services.shaping import check_font_coverage

    FONTS = "fonts"
    fonts = sorted(f for f in os.listdir(FONTS) if f.endswith((".ttf", ".otf")))

    test_texts = {
        "Bismillah": "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",
        "Ayah-end-marker": "إِنَّا أَنزَلْنَاهُ ۝ فِي لَيْلَةِ الْقَدْرِ",
    }

    for label, text in test_texts.items():
        print(f"\n  [{label}]  ({len({ord(c) for c in text})} distinct codepoints)")
        print(f"  {'font':32s}  cov   missing")
        print(f"  {'-'*32}  ---   -------")
        for f in fonts:
            cov, total, miss, rep = check_font_coverage(os.path.join(FONTS, f), text)
            mark = "OK " if cov == total else "** "
            print(f"  {mark}{f:30s}  {cov}/{total:<2d}  {rep}")

    banner("2. Auto-fallback selection")
    from quran_reels.services.shaping import select_rendering_font, reset_font_warnings

    reset_font_warnings()
    for label, text in test_texts.items():
        print(f"\n  [{label}]")
        for f in [
            "Tajawal-Bold.ttf",
            "UthmanTN1-Ver10.otf",
            "Dubai-Bold.ttf",
            "RanaKufi.otf",
            "Almadinah1.otf",
            "Amiri-Bold.ttf",
            "Lateef-Bold.ttf",
        ]:
            p = os.path.join(FONTS, f)
            if not os.path.isfile(p):
                continue
            chosen, fb, cov, rep = select_rendering_font(p, text)
            mark = "  " if not fb else "->"
            print(
                f"  {mark} {f:30s} -> {os.path.basename(chosen):30s}"
                f"  cov={int(cov*100)}%  fallback={fb}"
            )

    banner("3. End-to-end render test")
    from main import render_arabic_to_pil_image, FONT_DIR

    OUT = "verify_out"
    os.makedirs(OUT, exist_ok=True)

    test_cases = [
        ("Bismillah", "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"),
        ("Ayat-al-Kursi", "ٱللَّهُ لَآ إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ"),
    ]
    test_fonts = [
        "Tajawal-Bold.ttf",
        "UthmanTN1-Ver10.otf",
        "Amiri-Bold.ttf",
        "Lateef-Bold.ttf",
    ]

    for txt_label, text in test_cases:
        for font_name in test_fonts:
            f_path = os.path.join(FONT_DIR, font_name)
            if not os.path.isfile(f_path):
                continue
            # Make a filename-safe version of the text label.
            safe = txt_label.replace(" ", "-").lower()
            tag = f"{safe}_{font_name.replace('.', '_').replace('-', '_')}"
            img = render_arabic_to_pil_image(
                text=text,
                fontsize=80,
                color="#FFFFFF",
                stroke_color="#000000",
                stroke_width=3,
                target_width=920,
                font_path=f_path,
                supersample=2,
                shadow=True,
            )
            out = os.path.join(OUT, f"{tag}.png")
            img.save(out)
            print(f"  {tag:50s} -> {out}")

    banner("DONE")
    print(f"  Images written to: {os.path.abspath(OUT)}")
    print("  Open the PNGs and confirm the ﷲ ligature forms as a single")
    print("  calligraphic shape (not disconnected letters).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
