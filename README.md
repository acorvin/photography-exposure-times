# Photography Exposure Times, 1827–2026

**How long a photograph takes, from the first surviving camera photograph to phone night modes.** Published as the data study *Holding Still*.

Live page: https://acorvin.github.io/photography-exposure-times/

## Data

| Layer | Source | Notes |
|---|---|---|
| Camera records | Wikimedia Commons file metadata (EXIF), random sample | Capture date and exposure time as written by the camera |
| Documented exposures, 1827–2019 | Museums, archives and camera makers, listed with quotes in `data/reference/historical_exposures.csv` | Where sources disagree, the full range is kept |
| *Frames* | Alex Corvin's own photographs | Exposure metadata only |

## Method

- **Sampling.** `scripts/collect_commons.py` draws random files from the Commons File namespace and keeps those whose EXIF holds both `DateTimeOriginal` and `ExposureTime`.
- **Cleaning.** Duplicates removed; capture dates before 1990 or after the download (`SAMPLE_CUTOFF` in `build.py`) dropped; exposures of 1 microsecond or less, or longer than 1 year, dropped; files from film scanners dropped.
- **One photographer, one voice.** Commons holds bulk uploads from a few archives (for example, thousands of NASA astronaut photographs of Earth). The sample keeps one photograph per author per day and at most 50 per author. Author names are compared ignoring case and spacing, NASA's Earth Science and Remote Sensing Unit is merged across its two names, and files with no author are not grouped together. Caps of 20 or 100 move the published figures by about one percentage point at most, and the overall slow share by less than a tenth of a point.
- **Slow** means 1/13 s or longer.
- **Phones and tablets** are identified from the maker and model name (Apple, Samsung, Google, Xiaomi, Sony Ericsson and other phone makers, or a model name such as iPhone or Galaxy). Sony, Samsung and Kyocera also made cameras, so their files count only when the model name looks like a phone (an Xperia, or a Samsung SM-, GT- or Galaxy model). Any other file that names a maker or model counts as a camera; files with neither count in the overall figures only.
- **Shutter-speed steps.** An exposure counts as "on the ladder" when it is within 1% of a full- or third-stop speed (1/8000 s to 30 s).
- **Comparing my photographs.** Each one's figure is the share of the sample with a shorter exposure; anything within 1% of its speed counts as the same speed.
- **Historical bounds.** Where a source gives words rather than numbers ("several days", "a fraction of a second"), the plotted bound and the reason are recorded in the `bounds_note` column.

## Limitations

- Commons is a sample of what people upload, not of all photography.
- Capture dates come from camera clocks, some of which were never set.
- Phones that merge several frames may record one frame's exposure, not the total capture time.
- Film records no exposure metadata, so the years before digital cameras show documented exposures only.

## Repository

```
data/reference/historical_exposures.csv   documented exposures with sources and quotes
scripts/collect_commons.py                Commons sampler (standard library only)
scripts/read_own_exif.py                  exposure metadata from a folder of photographs
scripts/build.py                          clean, summarise, and build the page
notebooks/analysis.ipynb                  the analysis step by step, with checks and charts
src/page.template.html                    page source (D3 + canvas)
data/processed/                           every plausible record, the final sample, my photographs, yearly summary
docs/                                     built page and data.json (GitHub Pages)
embed/squarespace-snippet.html            iframe embed with auto-height
```

## Analysis notebook

`notebooks/analysis.ipynb` walks through the study: the data checks, why one archive had to be limited, how phones were told apart from cameras, the shutter-dial finding, the change over time, and a final cell that checks the notebook's figures against the published page. It reads the files in `data/processed/`, so it runs without repeating the download.

```bash
jupyter lab notebooks/analysis.ipynb
```

## Run it

```bash
pip install -r requirements.txt
python scripts/collect_commons.py --target 150000   # about 1–2 hours; safe to stop and restart
python scripts/read_own_exif.py "/path/to/Frames"   # optional
python scripts/build.py
```

Then open `docs/index.html` through a local server (`python -m http.server -d docs`).

## Licences

Commons metadata remains under each file's own licence; no Commons images are shown on the page. Photographs in docs/photos are © Alex Corvin. Quotations in `historical_exposures.csv` are short excerpts with links to their sources.
