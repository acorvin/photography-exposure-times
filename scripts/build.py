"""Build the Holding Still page and its data.

Reads
    data/reference/historical_exposures.csv   documented exposures, 1827-2019, with sources
    data/raw/commons_sample.csv                camera metadata from Wikimedia Commons
                                               (scripts/collect_commons.py)
    data/raw/own_photos.csv                    Alex Corvin's own exposures (optional,
                                               scripts/read_own_exif.py)
Writes
    data/processed/commons_clean.csv           cleaned camera records
    data/processed/commons_by_year.csv         yearly summary used in the text
    docs/data.json                             what the page draws
    docs/index.html                            the page (GitHub Pages)

    python scripts/build.py
"""
import argparse
import csv
import json
import math
import random
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "data" / "reference" / "historical_exposures.csv"
RAW = ROOT / "data" / "raw" / "commons_sample.csv"
OWN = ROOT / "data" / "raw" / "own_photos.csv"
PROCESSED = ROOT / "data" / "processed"
TEMPLATE = ROOT / "src" / "page.template.html"
DOCS = ROOT / "docs"

SEED = 1827
DISPLAY_MAX = None   # draw every photograph in the sample
# "Slow" means as slow as most of Alex's own photographs (the page states how many reach it).
SLOW_S = 1 / 13
SLOW_LABEL = "1/13 s"
MIN_YEAR_COUNT = 200
MAX_PER_AUTHOR = 50   # years with fewer photos are left out of the over-time chart
EXAMPLES_PER_BIN = 120
MIN_YEAR = 1990
MIN_EXPOSURE = 1e-6           # 1 microsecond
MAX_EXPOSURE = 366 * 86400    # 1 year

# Full and third-stop shutter speeds printed on camera dials and menus.
LADDER = sorted(
    [1 / d for d in (8000, 6400, 5000, 4000, 3200, 2500, 2000, 1600, 1250, 1000, 800, 640,
                     500, 400, 320, 250, 200, 160, 125, 100, 80, 60, 50, 40, 30, 25, 20,
                     15, 13, 10, 8, 6, 5, 4, 3)]
    + [0.4, 0.5, 0.6, 0.8, 1, 1.3, 1.6, 2, 2.5, 3.2, 4, 5, 6, 8, 10, 13, 15, 20, 25, 30]
)

# Makers whose cameras in this data are phones or tablets. Sony also makes cameras,
# so a Sony file counts only when the model name looks like an Xperia phone.
MOBILE_MAKES = re.compile(
    r"^(apple|samsung|google|huawei|honor|xiaomi|redmi|poco|oneplus|motorola|lge|lg electronics"
    r"|htc|oppo|vivo|realme|nokia|hmd global|zte|asus|blackberry|fairphone|meizu|lenovo|"
    r"microsoft|nothing|tecno|infinix|alcatel|tcl|sony ?ericsson|kyocera|sharp|bq|wiko|coolpad|nec|lg"
    r"|elephone|blackview|itel|nubia|oukitel|ulefone|vodafone|gionee|crosscall|micromax|fly|yu|docomo|kddi"
    r"|qmobile|cat|qcom|zuk|tinno|archos|mobiwire|tct|bullitt|orange|symphony|doogee|cubot|umidigi|intex"
    r"|fcnt|homtom|prestigio|lava|explay|walton|blu|infocus|vernee|vonino|highscreen|unihertz|vsmart"
    r"|general mobile|jiayu|iqoo|mptech|gigaset)\b",
    re.I,
)
SONY_PHONE = re.compile(r"xperia|^(so-|sov|sol|xq-)|^[cdefgh]\d{4}", re.I)
# Samsung and Kyocera also sold compact and system cameras (Digimax, NX, WB, Finecam, Contax),
# so their files count as phones only when the model name looks like a phone.
SAMSUNG_CAMERA_MAKE = re.compile(r"techwin|digital ima", re.I)
SAMSUNG_PHONE = re.compile(r"^(samsung[- _])?(sm-|gt-|sgh|sch|sph|shv|shw|scl|sc-\d|sc[gv]\d|sm_|sec_)|galaxy|nexus|^yp-g|^$", re.I)
KYOCERA_CAMERA = re.compile(r"finecam|contax", re.I)


PHONE_MODELS = re.compile(r"iphone|ipad|\bhtc\b|nokia|galaxy|\bpixel\b|redmi|xperia|lumia", re.I)


def is_mobile(make, model):
    make, model = (make or "").strip(), (model or "").strip()
    if make.lower().startswith("samsung"):
        return not SAMSUNG_CAMERA_MAKE.search(make) and bool(SAMSUNG_PHONE.search(model))
    if make.lower().startswith("kyocera"):
        return not KYOCERA_CAMERA.search(model)
    if MOBILE_MAKES.search(make):
        return True
    if PHONE_MODELS.search(model):   # some files name the phone only in the model field
        return True
    if make.lower().startswith("sony"):
        return bool(SONY_PHONE.search(model))
    return False


def on_ladder(s):
    return any(abs(s - v) / v <= 0.01 for v in LADDER)


def load_history():
    rows = list(csv.DictReader(HIST.open(encoding="utf-8")))
    out = []
    for r in rows:
        sources = []
        for i in (1, 2):
            if r.get(f"source_{i}_name"):
                sources.append({k: r[f"source_{i}_{k}"] for k in ("name", "url", "type", "quote")})
        out.append({
            "id": r["id"], "year": int(r["year"]), "yearNote": r["year_note"], "label": r["label"],
            "kind": r["kind"], "min": float(r["min_s"]), "max": float(r["max_s"]),
            "minLabel": r["min_label"], "maxLabel": r["max_label"], "note": r["bounds_note"],
            "sources": sources,
        })
    return out


def clean_commons(collected_on):
    df = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    n_raw = len(df)
    df = df.drop_duplicates("pageid")
    df["exposure_s"] = pd.to_numeric(df["exposure_s"], errors="coerce")
    df["captured"] = pd.to_datetime(df["captured"], errors="coerce", format="%Y-%m-%d %H:%M:%S")
    steps = {"collected": n_raw, "after_dedupe": len(df)}
    df = df[df["captured"].notna() & df["exposure_s"].notna()]
    df = df[(df["captured"].dt.year >= MIN_YEAR) & (df["captured"] <= pd.Timestamp(collected_on))]
    steps["plausible_date"] = len(df)
    df = df[(df["exposure_s"] >= MIN_EXPOSURE) & (df["exposure_s"] <= MAX_EXPOSURE)]
    steps["plausible_exposure"] = len(df)
    # Saved before the per-author limit, so the notebook can show why the limit is there.
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.assign(author=df["artist"].str.strip())[["pageid", "captured", "exposure_s", "make", "model", "author"]] \
        .to_csv(PROCESSED / "commons_all.csv", index=False)
    # Keep the sample about many photographers, not a few archives: Commons holds bulk uploads
    # (e.g. thousands of NASA astronaut photographs). One photo per author per day, at most
    # MAX_PER_AUTHOR per author. Results barely move between caps of 20, 50 and 100.
    df = df.copy()
    df["author"] = df["artist"].str.strip()
    df = df.sample(frac=1, random_state=SEED)
    df["day"] = df["captured"].dt.date
    df = df.drop_duplicates(["author", "day"])
    steps["one_per_author_day"] = len(df)
    df = df.groupby("author", group_keys=False).head(MAX_PER_AUTHOR)
    steps["capped_per_author"] = len(df)
    steps["authors"] = int(df["author"].nunique())
    df["year"] = df["captured"].dt.year
    start = pd.to_datetime(df["year"].astype(str) + "-01-01")
    days = 365 + df["captured"].dt.is_leap_year.astype(int)
    df["t"] = df["year"] + (df["captured"] - start).dt.total_seconds() / (days * 86400)
    df["mobile"] = [is_mobile(a, b) for a, b in zip(df["make"], df["model"])]
    df["ladder"] = df["exposure_s"].map(on_ladder)
    df["long"] = df["exposure_s"] >= 1
    df["slow"] = df["exposure_s"] >= SLOW_S * 0.97   # tolerance for 1/13 written as 0.0769
    return df.sort_values("captured").reset_index(drop=True), steps


def yearly(df):
    g = df.groupby("year")
    out = pd.DataFrame({
        "photos": g.size(),
        "median_exposure_s": g["exposure_s"].median(),
        "share_mobile": g["mobile"].mean(),
        "share_on_ladder": g["ladder"].mean(),
        "share_1s_or_longer": g["long"].mean(),
        "share_1s_or_longer_mobile": df[df["mobile"]].groupby("year")["long"].mean(),
        "share_1s_or_longer_camera": df[~df["mobile"]].groupby("year")["long"].mean(),
        "share_slow": g["slow"].mean(),
        "photos_camera": df[~df["mobile"]].groupby("year").size(),
        "photos_mobile": df[df["mobile"]].groupby("year").size(),
        "share_slow_camera": df[~df["mobile"]].groupby("year")["slow"].mean(),
        "share_slow_mobile": df[df["mobile"]].groupby("year")["slow"].mean(),
    }).reset_index()
    return out


def era_stats(df, years):
    sub = df[df["year"].between(*years)]
    if sub.empty:
        return None
    return {
        "years": list(years), "photos": int(len(sub)),
        "medianExposure": float(sub["exposure_s"].median()),
        "shareMobile": float(sub["mobile"].mean()),
        "shareOnLadder": float(sub["ladder"].mean()),
        "shareOnLadderCamera": float(sub[~sub["mobile"]]["ladder"].mean()) if (~sub["mobile"]).any() else None,
        "shareOnLadderMobile": float(sub[sub["mobile"]]["ladder"].mean()) if sub["mobile"].any() else None,
        "share1sOrLonger": float(sub["long"].mean()),
        "shareSlow": float(sub["slow"].mean()),
        "shareSlowCamera": float(sub[~sub["mobile"]]["slow"].mean()) if (~sub["mobile"]).any() else None,
        "shareSlowMobile": float(sub[sub["mobile"]]["slow"].mean()) if sub["mobile"].any() else None,
        "photosCamera": int((~sub["mobile"]).sum()), "photosMobile": int(sub["mobile"].sum()),
        "quantiles": {q: float(sub["exposure_s"].quantile(q / 100)) for q in (10, 25, 50, 75, 90, 99)},
    }


def pick_examples(df, rng):
    """Spread example photos across exposure decades so long exposures get examples too."""
    ok = df[(df["thumb_url"] != "") & (df["license"] != "")]
    bins = (ok["exposure_s"].map(math.log10)).floordiv(1)
    picks = []
    for _, idx in ok.groupby(bins).groups.items():
        idx = list(idx)
        rng.shuffle(idx)
        picks += idx[:EXAMPLES_PER_BIN]
    return sorted(picks)


CAMERA_NAMES = {"FUJIFILM": "Fujifilm", "OLYMPUS CORPORATION": "Olympus", "OM DIGITAL SOLUTIONS": "OM System",
                "RICOH IMAGING COMPANY, LTD.": "Ricoh", "NIKON CORPORATION": "Nikon", "Canon": "Canon", "SONY": "Sony"}


def camera_name(make, model):
    """Readable camera name for Alex's photographs, e.g. 'Fujifilm X-S20'."""
    make, model = (make or "").strip(), (model or "").strip()
    brand = CAMERA_NAMES.get(make, make.title())
    model = model.replace("MarkII", " Mark II").replace("MarkIII", " Mark III")
    if model.lower().startswith(brand.lower()):
        model = model[len(brand):].strip()
    return f"{brand} {model}".strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collected-on", default=None,
                    help="collection date (YYYY-MM-DD); defaults to the raw file's date")
    args = ap.parse_args()
    rng = random.Random(SEED)
    history = load_history()
    payload = {"history": history, "photos": None, "examples": [], "models": [], "own": [], "meta": {}}

    if RAW.exists():
        collected_on = args.collected_on or date.fromtimestamp(RAW.stat().st_mtime).isoformat()
        df, steps = clean_commons(collected_on)
        PROCESSED.mkdir(parents=True, exist_ok=True)
        keep = ["pageid", "title", "captured", "exposure_s", "exposure_raw", "f_number", "iso", "make",
                "model", "mobile", "ladder", "license", "artist", "page_url"]
        df[keep].to_csv(PROCESSED / "commons_clean.csv", index=False)
        by_year = yearly(df)
        by_year.to_csv(PROCESSED / "commons_by_year.csv", index=False, float_format="%.6g")

        show = list(range(len(df))) if DISPLAY_MAX is None else sorted(rng.sample(range(len(df)), min(DISPLAY_MAX, len(df))))
        ex_rows = []   # example photos are not shown on the page
        # example photos are not shown on the page, so the chart sample stays purely random
        models = sorted({m for m in df.loc[show, "model"] if m})
        mi = {m: i for i, m in enumerate(models)}
        ex_index = {r: i for i, r in enumerate(ex_rows)}
        payload["models"] = models
        payload["photos"] = {
            "t": [round(float(df.at[i, "t"]), 3) for i in show],
            "e": [round(math.log10(float(df.at[i, "exposure_s"])), 3) for i in show],
            "m": [mi.get(df.at[i, "model"], -1) for i in show],
            "p": [1 if df.at[i, "mobile"] else 0 for i in show],
            "x": [ex_index.get(i, -1) for i in show],
        }
        payload["examples"] = [{
            "title": df.at[i, "title"].removeprefix("File:"),
            "captured": df.at[i, "captured"].strftime("%Y-%m-%d"),
            "exposure": df.at[i, "exposure_raw"],
            "artist": df.at[i, "artist"], "license": df.at[i, "license"],
            "thumb": df.at[i, "thumb_url"], "page": df.at[i, "page_url"],
        } for i in ex_rows]
        first, last = int(df["year"].min()), int(df["year"].max())
        payload["meta"] = {
            "cleaning": steps, "photos": int(len(df)),
            "shown": len(show), "firstYear": first, "lastYear": last,
            "mobileShare": float(df["mobile"].mean()),
            "slowS": SLOW_S, "slowLabel": SLOW_LABEL, "minYearCount": MIN_YEAR_COUNT,
            "eras": {
                "all": era_stats(df, (first, last)),
                "p1": era_stats(df, (2005, 2012)),
                "p2": era_stats(df, (2013, 2018)),
                "p3": era_stats(df, (2019, last)),
            },
            "byYear": json.loads(by_year.to_json(orient="records")),
        }
        print(f"Commons: {steps} -> {len(df):,} photographs, {first}-{last}; showing {len(show):,}")
    else:
        print("No data/raw/commons_sample.csv yet; building with documented history only.")

    exposures = sorted(df["exposure_s"]) if RAW.exists() else None
    if OWN.exists():
        import bisect
        own = pd.read_csv(OWN, dtype=str, keep_default_na=False)
        # Public copy of Alex's photographs: title, date, shutter speed and camera only.
        pub = own[own.get("role", "series") != "hero"] if "role" in own else own
        pd.DataFrame({
            "title": pub["title"], "captured": pub["captured"].str[:10],
            "exposure_s": pub["exposure_s"], "camera": [camera_name(a, b) for a, b in zip(pub["make"], pub["model"])],
        }).to_csv(PROCESSED / "alex_photos.csv", index=False)
        for _, r in own.iterrows():
            when = datetime.strptime(r["captured"][:19], "%Y-%m-%d %H:%M:%S")
            y0 = datetime(when.year, 1, 1)
            y1 = datetime(when.year + 1, 1, 1)
            payload["own"].append({
                "t": round(when.year + (when - y0) / (y1 - y0), 4),
                "e": round(math.log10(float(r["exposure_s"])), 4),
                "exposure": r["exposure_raw"], "captured": when.strftime("%Y-%m-%d"),
                "title": r.get("title", ""), "camera": camera_name(r.get("make", ""), r.get("model", "")), "image": r.get("image", ""), "role": r.get("role", "series") or "series",
                # share of the sample with a strictly shorter exposure, and with exactly the same one
                "fasterShare": (bisect.bisect_left(exposures, float(r["exposure_s"]) * 0.99) / len(exposures)) if exposures else None,
                "sameShare": ((bisect.bisect_right(exposures, float(r["exposure_s"]) * 1.01)
                               - bisect.bisect_left(exposures, float(r["exposure_s"]) * 0.99)) / len(exposures)) if exposures else None,
            })
        print(f"Own photographs: {len(payload['own'])}")

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (DOCS / "index.html").write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote docs/index.html and docs/data.json ({(DOCS / 'data.json').stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
