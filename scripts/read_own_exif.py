"""Read capture date and exposure time from a folder of photographs.

Writes data/raw/own_photos.csv for the "Frames" layer. Reads metadata only;
the images themselves are not copied, resized or uploaded.

    python scripts/read_own_exif.py "/path/to/Frames" [--titles titles.csv]

titles.csv (optional) maps file names to published titles: columns file,title.
Uses exiftool when installed (handles RAW and HEIC), otherwise Pillow (JPEG/TIFF).
"""
import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "own_photos.csv"
EXTS = {".jpg", ".jpeg", ".tif", ".tiff", ".heic", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2"}


def with_exiftool(files):
    out = subprocess.run(
        ["exiftool", "-json", "-n", "-DateTimeOriginal", "-ExposureTime", "-Make", "-Model", *map(str, files)],
        capture_output=True, text=True, check=False,
    )
    for r in json.loads(out.stdout or "[]"):
        yield Path(r["SourceFile"]), r.get("DateTimeOriginal"), r.get("ExposureTime"), r.get("Make"), r.get("Model")


def with_pillow(files):
    from PIL import Image
    for f in files:
        try:
            ex = Image.open(f).getexif()
            sub = ex.get_ifd(0x8769)
            yield f, sub.get(36867) or ex.get(306), sub.get(33434), ex.get(271), ex.get(272)
        except Exception as e:  # unsupported format
            print(f"  skipped {f.name}: {e}", file=sys.stderr)


def seconds(v):
    if v is None:
        return None
    try:
        return float(Fraction(str(v))) if "/" in str(v) else float(v)
    except (ValueError, ZeroDivisionError):
        return None


def raw_label(s):
    return f"1/{round(1 / s)}" if s < 0.3 else f"{s:g}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--titles")
    args = ap.parse_args()
    files = sorted(p for p in Path(args.folder).rglob("*") if p.suffix.lower() in EXTS)
    titles = {}
    if args.titles:
        titles = {r["file"]: r["title"] for r in csv.DictReader(open(args.titles, encoding="utf-8"))}
    reader = with_exiftool if shutil.which("exiftool") else with_pillow
    rows, missing = [], []
    for f, when, exp, make, model in reader(files):
        s = seconds(exp)
        try:
            dt = datetime.strptime(str(when)[:19], "%Y:%m:%d %H:%M:%S")
        except (TypeError, ValueError):
            dt = None
        if s is None or dt is None:
            missing.append(f.name)
            continue
        rows.append({"file": f.name, "captured": dt.strftime("%Y-%m-%d %H:%M:%S"), "exposure_s": f"{s:.8g}",
                     "exposure_raw": raw_label(s), "make": (make or "").strip(), "model": (model or "").strip(),
                     "title": titles.get(f.name, "")})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "captured", "exposure_s", "exposure_raw", "make", "model", "title"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} photographs with date and exposure -> {OUT.relative_to(ROOT)}")
    if missing:
        print(f"{len(missing)} without exposure data: {', '.join(missing[:10])}{' …' if len(missing) > 10 else ''}")


if __name__ == "__main__":
    main()
