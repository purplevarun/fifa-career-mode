#!/usr/bin/env python3
import os
import re
from pathlib import Path

from rapidocr_onnxruntime import RapidOCR


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw_data"
PROCESSED_DIR = ROOT / "processed_data"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def ensure_dirs():
    RAW_DIR.mkdir(exist_ok=True)
    PROCESSED_DIR.mkdir(exist_ok=True)


def list_images():
    if not RAW_DIR.exists():
        return []
    images = []
    for path in sorted(RAW_DIR.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
    return images


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    cleaned = cleaned.strip("._")
    return cleaned or "image"


def process_image(image_path: Path, ocr: RapidOCR):
    result, _ = ocr(image_path)
    text_lines = []
    if result:
        for item in result:
            text = item[1]
            if text and text.strip():
                text_lines.append(text.strip())
    text = "\n".join(text_lines).strip()

    file_stem = sanitize_name(image_path.stem)
    out_path = PROCESSED_DIR / f"{file_stem}.txt"
    out_path.write_text(text, encoding="utf-8")
    return out_path


def main():
    ensure_dirs()
    images = list_images()
    if not images:
        print(f"No images found under {RAW_DIR}")
        return 0

    ocr = RapidOCR()
    processed = []
    for image_path in images:
        try:
            out_path = process_image(image_path, ocr)
            processed.append(out_path)
            print(f"Processed: {image_path.name} -> {out_path.name}")
        except Exception as exc:
            print(f"FAILED: {image_path.name}: {exc}")

    print(f"Done. Processed {len(processed)} images into {PROCESSED_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
