"""Collect a random sample of camera exposure data from Wikimedia Commons.

Draws random files from the File namespace, keeps those whose embedded camera
metadata (EXIF) has both a capture date and an exposure time, and writes one
row per photograph. Safe to stop and restart: rows already collected are kept
and skipped.

    python scripts/collect_commons.py --target 150000

Standard library only. Follows the Wikimedia API etiquette: a descriptive
User-Agent, one request at a time, maxlag, and back-off on errors.
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from fractions import Fraction
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "HoldingStill/1.0 (data study of photographic exposure times; https://github.com/acorvin)"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "commons_sample.csv"

FIELDS = [
    "pageid", "title", "captured", "exposure_s", "exposure_raw", "f_number", "iso",
    "make", "model", "software", "mime", "license", "artist", "thumb_url", "page_url",
]
KEEP_EXIF = {"DateTimeOriginal", "ExposureTime", "FNumber", "ISOSpeedRatings",
             "PhotographicSensitivity", "Make", "Model", "Software"}


def api_get(params, tries=6):
    params = {**params, "format": "json", "formatversion": "2", "maxlag": "5"}
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            if "error" in data:
                if data["error"].get("code") == "maxlag":
                    time.sleep(5 * (attempt + 1))
                    continue
                raise RuntimeError(data["error"])
            return data
        except Exception as e:  # network hiccups, 429, 5xx
            wait = min(60, 2 ** attempt * 2)
            print(f"  request failed ({e}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("API unreachable after retries")


def parse_exposure(v):
    """'1/250', '10/2500', '0.004', '30' -> seconds as float, else None."""
    if v is None:
        return None
    s = str(v).strip()
    try:
        x = float(Fraction(s)) if "/" in s else float(s)
    except (ValueError, ZeroDivisionError):
        return None
    return x if 0 < x < 10**9 else None


def parse_date(v):
    if not v:
        return None
    s = str(v).strip()[:19]
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[: len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    return None


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def rows_from(data):
    for p in data.get("query", {}).get("pages", []):
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii.get("mime", "").startswith("image/"):
            continue
        md = {m["name"]: m.get("value") for m in (ii.get("metadata") or []) if m.get("name") in KEEP_EXIF}
        exp = parse_exposure(md.get("ExposureTime"))
        when = parse_date(md.get("DateTimeOriginal"))
        if exp is None or when is None:
            continue
        ext = ii.get("extmetadata") or {}
        get = lambda k: strip_html((ext.get(k) or {}).get("value"))
        yield {
            "pageid": p["pageid"],
            "title": p["title"],
            "captured": when.strftime("%Y-%m-%d %H:%M:%S"),
            "exposure_s": f"{exp:.10g}",
            "exposure_raw": md.get("ExposureTime"),
            "f_number": md.get("FNumber"),
            "iso": md.get("ISOSpeedRatings") or md.get("PhotographicSensitivity"),
            "make": (md.get("Make") or "").strip(),
            "model": (md.get("Model") or "").strip(),
            "software": (md.get("Software") or "").strip(),
            "mime": ii.get("mime"),
            "license": get("LicenseShortName"),
            "artist": get("Artist")[:200],
            "thumb_url": ii.get("thumburl", ""),
            "page_url": ii.get("descriptionurl", ""),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=150000, help="photos with exposure data to collect")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between requests")
    args = ap.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if OUT.exists():
        with OUT.open(newline="", encoding="utf-8") as f:
            seen = {int(r["pageid"]) for r in csv.DictReader(f)}
    new_file = not OUT.exists()
    drawn = 0
    with OUT.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        while len(seen) < args.target:
            data = api_get({
                "action": "query", "generator": "random", "grnnamespace": "6",
                "grnlimit": str(args.batch), "prop": "imageinfo",
                "iiprop": "metadata|extmetadata|mime|url",
                "iiextmetadatafilter": "LicenseShortName|Artist",
                "iiurlwidth": "320",
            })
            drawn += args.batch
            for row in rows_from(data):
                if row["pageid"] in seen:
                    continue
                seen.add(row["pageid"])
                w.writerow(row)
            f.flush()
            if drawn % 2500 == 0:
                print(f"drawn {drawn:,} files, kept {len(seen):,}")
            time.sleep(args.pause)
    print(f"Done: {len(seen):,} photographs in {OUT.relative_to(ROOT)} ({drawn:,} files drawn this run)")


if __name__ == "__main__":
    main()
