# Spatial Exposure Pipeline — Technical Reference

**California BBS × CDPR PUR pesticide exposure, 2015–2023**

Doug Moody — Point Blue Conservation Science — May 2026

---

## Table of Contents

1. [Environment and Dependencies](#1-environment-and-dependencies)
2. [Repository Layout](#2-repository-layout)
3. [Coordinate Reference Systems](#3-coordinate-reference-systems)
4. [DuckDB Schema](#4-duckdb-schema)
5. [Module: `spatial_setup.py`](#5-module-spatial_setuppy)
6. [Module: `pur_loader.py`](#6-module-pur_loaderpy)
7. [Module: `crop_attribution.py`](#7-module-crop_attributionpy)
8. [Module: `exposure_engine.py`](#8-module-exposure_enginepy)
9. [Module: `validate.py`](#9-module-validatepy)
10. [Utility: `download_cdl.py`](#10-utility-download_cdlpy)
11. [Output File Formats](#11-output-file-formats)
12. [End-to-End Workflow](#12-end-to-end-workflow)
13. [Known Issues and Workarounds](#13-known-issues-and-workarounds)

---

## 1. Environment and Dependencies

### Python version

```
Python 3.12.3
```

### Virtual environment

The project shares a venv with the parent PUR analysis:

```bash
source /home/ubuntu/devops/pur/.venv/bin/activate
```

### Key packages

| Package | Version | Purpose |
|---|---|---|
| `duckdb` | 1.5.2 | Spatial database (PLSS polygons, PUR records, crop masks) |
| `geopandas` | 1.1.3 | PLSS GeoPackage I/O; geometry union for split sections |
| `rasterio` | 1.5.0 | CDL raster window reads |
| `pyproj` | 3.7.2 | CRS transforms (WGS84 → EPSG:3310 for buffer geometry) |
| `shapely` | 2.1.2 | Geometry construction; WKB serialisation for DuckDB bulk insert |
| `pandas` | 3.0.2 | DataFrame processing throughout |
| `numpy` | 2.4.4 | Pixel array arithmetic in crop attribution |
| `requests` | 2.33.1 | PLSS ArcGIS REST download; CDL WCS download |

### Install

```bash
pip install duckdb geopandas rasterio pyproj shapely pandas numpy requests
```

DuckDB's spatial extension is installed at runtime on first use:

```python
con.execute("INSTALL spatial; LOAD spatial;")
```

---

## 2. Repository Layout

```
spatial/
├── spatial_setup.py          # one-time setup: PLSS, CDL, DuckDB schema
├── pur_loader.py             # PUR ZIP → Parquet + DuckDB
├── crop_attribution.py       # CDL-based within-section attribution fractions
├── exposure_engine.py        # location × buffer × lag aggregation
├── validate.py               # five sanity checks
├── download_cdl.py           # standalone CDL downloader (NASS retry logic)
├── test_locations.csv        # 3-site smoke test
│
├── data/
│   ├── plss_ca.gpkg          # 131,579 CA PLSS sections (EPSG:3310)
│   ├── spatial.duckdb        # DuckDB database (~60 MB + PUR records)
│   └── cdl/
│       ├── cdl_2015_ca.tif   # USDA CDL annual raster (~1.07 GB each)
│       ├── cdl_2016_ca.tif
│       └── ...               # 2017–2023
│
└── outputs/
    ├── pur_sections.parquet          # 5,065,221 PUR records, section-keyed
    ├── pur_loader_summary.csv        # year × class validation totals
    ├── crop_attribution.parquet      # 344,108 (year, section, site) attribution fractions
    ├── bbs_locations.csv             # 44 route locations (cumulative)
    ├── bbs_locations_yearly.csv      # 396 route-year locations
    ├── bbs_exposure.csv              # long format, cumulative
    ├── bbs_exposure_wide.csv         # wide format, cumulative (model-ready)
    ├── bbs_exposure_yearly.csv       # long format, per-year
    ├── bbs_exposure_yearly_wide.csv  # wide format, per-year (primary model input)
    ├── bbs_ca_routes_ranked.csv      # all 221 active CA BBS routes with PUR density
    ├── spatial_exposure_analysis.md  # scientific summary whitepaper
    └── pipeline_technical_reference.md  # this file

../                           # parent directory
├── toxicity_lookup.csv       # 44 insecticide AIs: LD50, LC50, sources
├── pur_analysis/
│   └── cache/
│       ├── pur2015.zip       # CDPR PUR archives (~3 GB total)
│       └── ...               # pur2016.zip … pur2023.zip
└── .venv/                    # shared virtual environment
```

---

## 3. Coordinate Reference Systems

The pipeline uses three CRS values; mixing them up is the most common source of silent
geometry bugs.

| CRS | EPSG | Name | Used for |
|---|---|---|---|
| **WGS84** | 4326 | Geographic lat/lon | Input locations; PLSS download (ArcGIS returns GeoJSON in 4326) |
| **California Albers** | 3310 | NAD83 / California Albers (meters) | All stored geometries in DuckDB; buffer construction |
| **CONUS Albers** | 5070 | NAD83 / Conus Albers (meters) | CDL raster native CRS; window read bbox |

**Critical rule:** buffer distances (500 m, 1 km, 2 km, 5 km) must be computed in
EPSG:3310. Buffers constructed in WGS84 degrees will be silently wrong.

### Pyproj transform pattern

The correct pattern for WGS84 → EPSG:3310 is:

```python
from pyproj import Transformer
t = Transformer.from_crs("EPSG:4326", "EPSG:3310", always_xy=True)
# always_xy=True → input is (longitude, latitude), output is (easting, northing)
cx, cy = t.transform(longitude, latitude)
```

Do **not** use `t.transform(latitude, longitude)` — the axis order is a common mistake.
With `always_xy=True`, the first argument is always the x-axis (longitude/easting).

### CDL window read pattern

The CDL rasters are in EPSG:5070. Use `rasterio.warp.transform` (not pyproj directly)
to convert section bbox from EPSG:3310 → EPSG:5070 before the window read:

```python
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import from_bounds

with rasterio.open("data/cdl/cdl_2019_ca.tif") as src:
    # geom_3310.bounds → (minx, miny, maxx, maxy) in EPSG:3310
    xs, ys = warp_transform("EPSG:3310", src.crs,
                            [bounds[0], bounds[2]],
                            [bounds[1], bounds[3]])
    win = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform)
    pixels = src.read(1, window=win).ravel()
```

Note: the pyproj `Transformer` approach for EPSG:3310 → EPSG:5070 produced incorrect
results in testing (coordinates outside the CDL extent). `rasterio.warp.transform` is
the reliable path.

---

## 4. DuckDB Schema

The database at `data/spatial.duckdb` contains three tables. The spatial extension must
be loaded at the start of every session:

```python
import duckdb
con = duckdb.connect("data/spatial.duckdb")
con.execute("LOAD spatial;")
```

### `plss_sections`

131,577 California PLSS section polygons in EPSG:3310.

```sql
CREATE TABLE plss_sections (
    section_key  VARCHAR PRIMARY KEY,   -- 9-char: {meridian}{twp:02d}{tdir}{rng:02d}{rdir}{sec:02d}
    comtrs       VARCHAR,               -- 11-char CDPR key (county(2) + section_key)
    geom         GEOMETRY               -- polygon in EPSG:3310
);
CREATE INDEX idx_plss_key ON plss_sections (section_key);
```

Example `section_key`: `M03N02E20` (Mount Diablo meridian, T03N, R02E, section 20)

The `section_key` is derived from the BLM PLSSID string (see §5.1) and is the join
key between `plss_sections` and `pur_records`.

### `pur_records`

5,065,221 application records from CDPR PUR 2015–2023.

```sql
CREATE TABLE pur_records (
    id               BIGINT,
    year             INTEGER,
    comtrs           VARCHAR(11),
    section_key      VARCHAR(9),        -- join key to plss_sections
    county_cd        VARCHAR(2),
    chem_code        INTEGER,
    chemname         VARCHAR,
    chem_class       VARCHAR,           -- e.g. 'Pyrethroids', 'Organophosphates'
    lbs_ai           DOUBLE,            -- pounds of active ingredient applied
    acres_treated    DOUBLE,
    applic_dt        DATE,
    site_code        INTEGER,           -- CDPR crop/site code
    site_name        VARCHAR,
    aer_gnd_ind      VARCHAR(1),        -- 'A' aerial, 'G' ground
    avian_ld50       DOUBLE,            -- mg/kg, Bobwhite acute oral LD50
    avian_ceiling    BOOLEAN,           -- true if LD50 value is a ">N" ceiling
    aquatic_lc50     DOUBLE,            -- μg/L, Daphnia magna 48h EC50
    aquatic_ceiling  BOOLEAN
);
```

### `crop_masks`

344,108 attribution fractions from CDL analysis.

```sql
CREATE TABLE crop_masks (
    year                 INTEGER,
    section_key          VARCHAR(9),
    site_code            INTEGER,
    cdl_code             INTEGER,        -- matched CDL code (-1 if no match)
    crop_area_m2         DOUBLE,
    section_area_m2      DOUBLE,
    ag_area_m2           DOUBLE,
    attribution_fraction DOUBLE,         -- the key output: [0,1]
    fallback             VARCHAR         -- 'exact_crop', 'all_ag', or 'uniform'
);
```

### Bulk reload from Parquet

If `spatial_setup.py` is re-run (which drops and recreates all tables), reload
`pur_records` from the existing Parquet rather than re-streaming the ZIP archives:

```python
con.execute("DELETE FROM pur_records")
con.execute("""
    INSERT INTO pur_records
    SELECT id, year, comtrs, section_key, county_cd,
           chem_code::INTEGER, chemname, chem_class,
           lbs_ai::DOUBLE, acres_treated::DOUBLE,
           TRY_CAST(applic_dt AS DATE),
           site_code::INTEGER, site_name, aer_gnd_ind,
           avian_ld50::DOUBLE, avian_ceiling::BOOLEAN,
           aquatic_lc50::DOUBLE, aquatic_ceiling::BOOLEAN
    FROM read_parquet('outputs/pur_sections.parquet')
""")
```

The explicit column list with casts is required because Parquet column order differs
from the DuckDB table definition.

---

## 5. Module: `spatial_setup.py`

**Run once.** Downloads PLSS section polygons and CDL rasters; creates the DuckDB schema.

```bash
python spatial_setup.py [--years 2015 ... 2023] [--skip-cdl] [--force]
```

### 5.1 PLSS download and section key construction

Two sources are tried in order; first success wins:

1. **CDPR PLSS Feature Service** (`gis.cdpr.ca.gov`) — preferred but has SSL issues.
2. **BLM CadNSDI REST layer 2** (`gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/2`) — fallback; covers all of California.

The BLM data uses a `PLSSID` string to encode survey geometry. Parsing it to the
9-character section key that matches CDPR's COMTRS format:

```python
# BLM PLSSID example: 'CA210480N0170E0'
# Position: state[0:2], meridian_id[2:4], twp[4:7], pad[7], tdir[8],
#           range[9:12], pad[12], rdir[13], level_flag[14]

BLM_MERIDIAN = {21: "M", 27: "S", 18: "H"}  # Mount Diablo, San Bernardino, Humboldt

def _blm_section_key(props: dict) -> str | None:
    plssid = str(props.get("PLSSID", ""))
    if len(plssid) < 14 or plssid[:2] != "CA":
        return None
    meridian_id = int(plssid[2:4])
    meridian = BLM_MERIDIAN.get(meridian_id)
    if not meridian:
        return None
    twp  = int(plssid[4:7])
    tdir = plssid[8].upper()        # N or S  (index 7 is a zero-pad '0')
    rng  = int(plssid[9:12])
    rdir = plssid[13].upper()       # E or W  (index 12 is a zero-pad '0')
    sec  = int(props["FRSTDIVNO"])  # section number 1-36
    if not (1 <= sec <= 36):
        return None
    return f"{meridian}{twp:02d}{tdir}{rng:02d}{rdir}{sec:02d}"
```

This produces keys like `M03N02E20`, which matches what `pur_loader.py` extracts
from COMTRS via `comtrs[2:]`.

#### Section key anatomy

```
COMTRS:      1 9 M 0 3 N 0 2 E 2 0
             ↑↑ ↑ ↑↑ ↑ ↑↑ ↑ ↑↑
county_cd ──┘│ │ │  │ │  │ │  │  └── section (2 digits)
             │ │ │  │ │  │ └──────── range direction (E/W)
             │ │ │  │ └──────────── range (2 digits)
             │ │ │  └────────────── township direction (N/S)
             │ │ └───────────────── township (2 digits)
             │ └─────────────────── meridian (M/S/H)
             └───────────────────── (county_cd, 2 digits — NOT in section_key)

section_key = comtrs[2:] = 'M03N02E20'  (9 characters)
```

#### Split sections

Some sections straddle county lines and appear as multiple polygons with the same
`section_key`. These must be unioned before loading into DuckDB:

```python
from shapely.ops import unary_union

unioned = (
    gdf.groupby("section_key")["geometry"]
    .apply(unary_union)
    .reset_index()
)
```

### 5.2 Bulk geometry load into DuckDB

Row-by-row inserts with `ST_GeomFromText()` are extremely slow for 131K polygons.
The fast path: serialize all geometries to hex WKB, write a Parquet file, bulk-insert
with `ST_GeomFromHEXWKB()`:

```python
valid["wkb_hex"] = valid.geometry.to_wkb(hex=True)
tmp_df = valid[["section_key", "comtrs", "wkb_hex"]]
tmp_df.to_parquet("/tmp/plss_load.parquet", index=False)

con.execute("""
    INSERT INTO plss_sections
    SELECT section_key, comtrs, ST_GeomFromHEXWKB(wkb_hex)
    FROM read_parquet('/tmp/plss_load.parquet')
    WHERE wkb_hex IS NOT NULL
""")
```

### 5.3 CDL download with reconnect logic

The NASS CropScape WCS (`nassgeodata.gmu.edu`) serves California CDL rasters as
~1.07 GB GeoTIFFs but drops HTTP connections at exactly **130,023,424 bytes**
(124 MiB) on every connection. This requires 8–9 reconnects per file. The pipeline
handles this with HTTP `Range` headers:

```python
# Two-step: (1) get the download URL from the WCS, (2) download with resume
def _get_nass_url(year: int) -> str:
    xmin, ymin, xmax, ymax = CA_BBOX_5070  # (-2_110_000, 1_480_000, -1_160_000, 2_490_000)
    r = requests.get(
        "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile",
        params={"year": year, "bbox": f"{xmin},{ymin},{xmax},{ymax}",
                "format": "GeoTIFF", "crs": "EPSG:5070"},
        timeout=300,   # NASS is slow to generate the file; 5 min is needed
    )
    # Response is XML with a <returnURL> element
    root = ET.fromstring(r.text)
    url_el = root.find(".//{*}returnURL")
    if url_el is None:
        url_el = root.find("returnURL")
    return url_el.text.strip()

def download_cdl_year(year: int, force: bool = False) -> Path:
    out = Path(f"data/cdl/cdl_{year}_ca.tif")

    # Validate existing file: src.meta alone is insufficient — truncated files
    # have valid headers but fail on pixel reads
    if out.exists() and not force:
        try:
            with rasterio.open(out) as src:
                w = rasterio.windows.Window(src.width // 2, src.height - 100, 100, 100)
                src.read(1, window=w)   # pixel read near bottom of file
            return out                  # complete
        except Exception:
            out.unlink()                # truncated; restart

    file_url = _get_nass_url(year)
    written = 0
    for attempt in range(1, 21):       # up to 20 reconnects (9 needed for 1 GB)
        headers = {"Range": f"bytes={written}-"} if written else {}
        mode = "ab" if written else "wb"
        try:
            with requests.get(file_url, stream=True,
                              timeout=3600, headers=headers) as resp:
                if resp.status_code == 416:
                    break              # server confirms: already complete
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0)) + written
                with open(out, mode) as f:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                        written += len(chunk)
            break                      # finished without error
        except Exception:
            time.sleep(15)
```

**Important:** the download URL returned by the NASS WCS is ephemeral (cached on their
server for a session). If the process is restarted, a new URL must be requested —
the old URL will be dead. The loop above keeps the same URL for all reconnects within
a single run. The standalone `download_cdl.py` implements the same logic with better
progress output for manual runs.

---

## 6. Module: `pur_loader.py`

Reads PUR ZIP archives, filters to tracked insecticide classes, attaches toxicity values,
and writes `outputs/pur_sections.parquet` + loads into DuckDB.

```bash
python pur_loader.py [--years 2015 ... 2023] [--no-db]
```

### 6.1 PUR ZIP structure

Each archive (e.g., `pur2019.zip`) contains:
- `chemical.txt` — `chem_code` → `chemname` lookup (all years)
- `site.txt` — `site_code` → `site_name` lookup (all years)
- `udc*.txt` — one per county, one row per application event

**Pre-2023 format:** UDC files do not contain `chemname` or `site_name` columns;
these must be joined from the lookup files.

**2023+ format:** UDC files include `chemname` and `site_name` inline.

The loader handles both:

```python
def stream_year(zip_path, year, tox_lookup, chem_map, site_map):
    with zipfile.ZipFile(zip_path) as zf:
        for name in udc_files:
            for chunk in pd.read_csv(fh, usecols=..., chunksize=200_000):
                # Resolve chemname: column if present, else join from chem_map
                if "chemname" in chunk.columns:
                    chunk["chemname_lc"] = chunk["chemname"].str.lower().str.strip()
                else:
                    chunk["chemname_lc"] = chunk["chem_code"].map(
                        lambda c: chem_map.get(int(c), "") if pd.notna(c) else ""
                    )
                # Resolve site_name similarly
                if "site_name" not in chunk.columns:
                    chunk["site_name"] = chunk["site_code"].map(
                        lambda c: site_map.get(int(c), "") if pd.notna(c) else ""
                    )
```

### 6.2 Record filtering

Applied in order, each step drops rows that fail:

```python
# 1. Must have a valid 11-character COMTRS (section location)
chunk = chunk[chunk["comtrs"].notna()]
chunk["comtrs"] = chunk["comtrs"].str.strip().str.upper()
chunk = chunk[chunk["comtrs"].str.len() == 11]

# 2. Agricultural sites only (site_code < 65000 is CDPR's ag heuristic)
chunk = chunk[chunk["site_code"].fillna(99999) < 65000]

# 3. Must match a chemical in the toxicity lookup
chunk = chunk[chunk["chemname_lc"].isin(tox_lookup)]
```

### 6.3 Section key extraction

```python
chunk["section_key"] = chunk["comtrs"].str[2:]   # characters 2–10 (9 chars)
chunk["county_cd"]   = chunk["comtrs"].str[:2]   # characters 0–1
```

### 6.4 Toxicity attachment

Toxicity values are joined from `toxicity_lookup.csv`. The CSV has unquoted commas
in the notes column, so it is read by column index (not `pd.read_csv`):

```python
def load_toxicity_lookup() -> dict[str, dict]:
    rows = {}
    with open(TOXICITY_CSV) as fh:
        for i, line in enumerate(fh):
            if i == 0:
                continue
            parts = line.rstrip("\n").split(",")
            chemname = parts[0].strip().lower()
            rows[chemname] = {
                "chem_class":      parts[1].strip(),
                "avian_ld50":      _float(parts[2]),
                "avian_ceiling":   _bool(parts[3]),
                "aquatic_lc50":    _float(parts[6]),
                "aquatic_ceiling": _bool(parts[7]),
            }
    return rows
```

Column indices 0–9 are comma-free; column 10+ is the notes field. Do not add commas
to columns 0–9 when editing the CSV.

### 6.5 DuckDB insert

The Parquet → DuckDB insert uses an explicit column list with `TRY_CAST` to avoid
positional mismatches (Parquet column order differs from the table definition):

```python
con.execute(f"""
    INSERT INTO pur_records
    SELECT id, year, comtrs, section_key, county_cd,
           chem_code::INTEGER, chemname, chem_class,
           lbs_ai::DOUBLE, acres_treated::DOUBLE,
           TRY_CAST(applic_dt AS DATE),
           site_code::INTEGER, site_name, aer_gnd_ind,
           avian_ld50::DOUBLE, avian_ceiling::BOOLEAN,
           aquatic_lc50::DOUBLE, aquatic_ceiling::BOOLEAN
    FROM read_parquet('{tmp_parquet}')
""")
```

---

## 7. Module: `crop_attribution.py`

Computes within-section attribution fractions for every unique
(year, section, site_code) combination using CDL annual rasters.

```bash
python crop_attribution.py [--year YEAR]
```

### 7.1 Site-name → CDL code mapping

PUR `site_name` strings (e.g., "ALMONDS", "WINE GRAPES") are matched against a table of
lowercase fragments. The matching is substring-based, not exact:

```python
SITE_TO_CDL: list[tuple[str, set[int]]] = [
    ("almond",   {75}),
    ("grape",    {69}),
    ("tomato",   {54, 206}),
    ("cotton",   {2}),
    ("alfalfa",  {36}),
    ("wheat",    {22, 23, 24}),
    ("corn",     {1, 12, 46}),
    # ... 55 crops total
]

def site_name_to_cdl_codes(site_name: str) -> set[int]:
    sn = site_name.lower().strip()
    matched = set()
    for fragment, codes in SITE_TO_CDL:
        if fragment in sn:
            matched |= codes
    return matched
```

### 7.2 Attribution computation

The key optimization: read CDL pixels once per (section, year), not once per
(section, year, site_code). Sections typically have 4–5 distinct site_codes; this
gives ~4× speedup over the naive per-combo loop.

```python
for section_key, rows in combos.groupby("section_key"):
    geom = geom_map.get(section_key)
    pixels = _read_cdl_window(cdl_path_year, geom)   # one file open

    total_px = pixels.size
    ag_px = int(np.sum(pixels < 62))                  # codes 1-61 = agricultural

    for _, row in rows.iterrows():
        cdl_codes = site_name_to_cdl_codes(row["site_name"])
        if cdl_codes:
            crop_px = int(np.isin(pixels, list(cdl_codes)).sum())
            if crop_px > 0:
                # exact_crop tier
                attribution = (crop_px / total_px)
                continue
        if ag_px > 0:
            # all_ag tier
            attribution = (ag_px / total_px)
        else:
            # uniform tier
            attribution = 1.0
```

### 7.3 CDL window read

```python
def _read_cdl_window(cdl_path: Path, geom_3310) -> np.ndarray | None:
    import rasterio
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import from_bounds

    with rasterio.open(cdl_path) as src:
        # Transform section bbox EPSG:3310 → CDL CRS (EPSG:5070)
        bounds = geom_3310.bounds   # (minx, miny, maxx, maxy)
        xs, ys = warp_transform("EPSG:3310", src.crs,
                                [bounds[0], bounds[2]],
                                [bounds[1], bounds[3]])
        win = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform)
        data = src.read(1, window=win)
    return data.ravel()
```

Each section is approximately 1 mi² (~2.6 km²). At 30 m CDL resolution that is
roughly 87 × 87 = 7,500 pixels per section.

---

## 8. Module: `exposure_engine.py`

Given monitoring locations and survey dates, produces buffered and lag-windowed
exposure metrics by chemical class.

```bash
python exposure_engine.py \
    --locations outputs/bbs_locations_yearly.csv \
    --output    outputs/bbs_exposure_yearly.csv \
    [--buffers 500 1000 2000 5000] \
    [--lags 30 60 90] \
    [--no-crop-attr]
```

### 8.1 Input CSV format

```
location_id,latitude,longitude,survey_start_date,survey_end_date
BBS_CA_054_ORANGE_COVE_2019,36.6316,-119.3048,2019-05-28,2019-06-10
```

All five columns are required. Additional columns (e.g., `year`, `BCR`) are loaded
and ignored.

### 8.2 Buffer construction

Buffers are square bounding boxes in EPSG:3310 (California Albers, meters), not circles:

```python
_T_TO_ALBERS = Transformer.from_crs("EPSG:4326", "EPSG:3310", always_xy=True)

cx, cy = _T_TO_ALBERS.transform(longitude, latitude)
buffer_wkt = (
    f"POLYGON(("
    f"{cx-d} {cy-d},"
    f"{cx+d} {cy-d},"
    f"{cx+d} {cy+d},"
    f"{cx-d} {cy+d},"
    f"{cx-d} {cy-d}"
    f"))"
)
```

where `d` is the buffer distance in meters. A square overestimates a circular buffer
by ~27%; use consistently across all locations so relative comparisons are valid.

### 8.3 Spatial join query

The core DuckDB query for one (location, buffer, lag) combination:

```sql
SELECT
    p.id,
    p.year,
    p.section_key,
    p.chem_code,
    p.chem_class,
    p.lbs_ai,
    p.acres_treated,
    p.applic_dt,
    p.site_code,
    p.aer_gnd_ind,
    p.avian_ld50,
    p.aquatic_lc50,
    ST_Area(ST_Intersection(sec.geom, ST_GeomFromText('{buffer_wkt}')))
        / ST_Area(sec.geom) AS area_fraction
FROM pur_records p
JOIN plss_sections sec ON p.section_key = sec.section_key
WHERE ST_Intersects(sec.geom, ST_GeomFromText('{buffer_wkt}'))
  AND p.applic_dt BETWEEN DATE '{date_start}' AND DATE '{date_end}'
```

The lag window:
```python
from datetime import date, timedelta
survey_start = date.fromisoformat(row["survey_start_date"])
date_end   = survey_start - timedelta(days=1)
date_start = survey_start - timedelta(days=lag_days)
```

### 8.4 Exposure aggregation

For each intersecting application record, the effective contribution is:

```
effective_lbs = lbs_ai × area_fraction × attribution_fraction
```

where:
- `area_fraction` = (buffer ∩ section area) / section area  ∈ [0, 1]
- `attribution_fraction` = from `crop_masks` table (1.0 if not found = uniform fallback)

Toxicity units:

```python
tox_units_avian   = effective_lbs / avian_ld50   # ld50 in mg/kg
tox_units_aquatic = effective_lbs / aquatic_lc50 # lc50 in μg/L
```

Records lacking an LD50 or LC50 contribute 0.0 to the corresponding toxicity column.

### 8.5 Wide-format output

The wide table (`*_wide.csv`) has one row per location and one column per
(class, buffer, lag, metric) combination. Column naming convention:

```
{chemical_class}_{buffer_m}m_{lag_days}d_{metric}
```

Examples:
```
Pyrethroids_5000m_90d_tox_units_aquatic
Organophosphates_500m_30d_lbs_ai
Carbamates_2000m_60d_n_applications
```

With 8 classes × 4 buffers × 3 lags × 6 metrics = 576 possible columns, but only
combinations present in the data appear; null combinations are filled with 0.

### 8.6 Fallback: tabular join

If the DuckDB spatial query returns empty results (e.g., geometry not loaded for a
section), the engine falls back to a tabular county-level join using `pur_sections.parquet`
directly. The fallback is indicated by `spatial_join = 'county_tabular'` in the long
output; the spatial join is `'plss_spatial'`. All 2015–2023 BBS route results used
`plss_spatial`.

---

## 9. Module: `validate.py`

Runs five sanity checks on pipeline outputs. Exits with code 0 if all pass, 1 if any
critical check fails.

```bash
python validate.py [--exposure outputs/exposure.csv]
```

### Check 1: Statewide totals

Compares `pur_sections.parquet` lbs totals against the reference CSV produced by
`../pur_analyze.py` (`pur_analysis/pur_yearly_by_class.csv`). The loader should
be ≤ the reference for every year × class combination (the gap is COMTRS-untagged
records, expected at ~18%).

### Check 2: COMTRS coverage rate

Counts raw records in the PUR ZIP archives (any year with >50% coverage of its
raw record count passes; a warning is issued for years between 40–50%). 2023 shows
44% coverage — a known characteristic of that year's raw PUR data.

### Check 3: Buffer monotonicity

For each location in the exposure CSV, verifies that lbs AI at 500 m ≤ 1 km ≤ 2 km ≤ 5 km.
Violations would indicate a spatial join bug (a smaller buffer returning more area
than a larger one).

### Check 4: Section spot-checks

Randomly selects 5 high-intensity sections, manually sums lbs from the raw PUR
archive for all chemicals, and verifies that loader lbs ≤ raw all-chemical lbs
(the loader tracks only insecticide classes; raw includes herbicides, fungicides, etc.).

### Check 5: CDL attribution sanity

Verifies that the median `attribution_fraction` for `exact_crop` tier records is
lower than 1.0 (the uniform default). A median of 0.181 was observed, confirming
that crop pixel matching is actively constraining the attribution to sub-section area
in the exact_crop tier.

---

## 10. Utility: `download_cdl.py`

A standalone script for downloading CDL rasters, designed to be run directly in a
terminal (not via Claude) to avoid network interruption issues.

```bash
python download_cdl.py                        # all years 2015–2023
python download_cdl.py --years 2020 2021      # specific years
python download_cdl.py --force                # re-download even if cached
```

The script differs from the equivalent code in `spatial_setup.py` in two ways:
1. It prints progress as `{downloaded} / {total} MB ({pct}%)` for human monitoring.
2. It uses a pixel-level rasterio validation check (reads 100×100 tile near the bottom
   of each file) rather than a header-only check. GeoTIFF headers are intact even on
   truncated files; pixel reads are not.

```python
# Correct validation — do not use src.meta alone
with rasterio.open(out) as src:
    w = rasterio.windows.Window(src.width // 2, src.height - 100, 100, 100)
    src.read(1, window=w)   # raises if file is truncated
```

---

## 11. Output File Formats

### `pur_sections.parquet`

5,065,221 rows × 18 columns. One row per application event.

| Column | Type | Description |
|---|---|---|
| `id` | int64 | Sequential row ID |
| `year` | int64 | Survey year |
| `comtrs` | str | 11-char CDPR section key |
| `section_key` | str | 9-char PLSS key (`comtrs[2:]`) |
| `county_cd` | str | 2-char CDPR county code |
| `chem_code` | int | CDPR chemical code |
| `chemname` | str | Chemical name (lowercase) |
| `chem_class` | str | Class: Pyrethroids, Organophosphates, etc. |
| `lbs_ai` | float | Pounds of active ingredient applied |
| `acres_treated` | float | Acres treated |
| `applic_dt` | str | Application date (ISO YYYY-MM-DD) |
| `site_code` | int | CDPR crop/site code |
| `site_name` | str | Crop/site name |
| `aer_gnd_ind` | str | 'A' aerial, 'G' ground |
| `avian_ld50` | float | Bobwhite acute oral LD50 (mg/kg) |
| `avian_ceiling` | bool | True if LD50 is a ">N" ceiling value |
| `aquatic_lc50` | float | Daphnia magna 48h EC50 (μg/L) |
| `aquatic_ceiling` | bool | True if LC50 is a ">N" ceiling value |

### `crop_attribution.parquet`

344,108 rows × 9 columns. One row per unique (year, section, site_code).

| Column | Type | Description |
|---|---|---|
| `year` | int | PUR year |
| `section_key` | str | 9-char PLSS key |
| `site_code` | int | CDPR crop/site code |
| `cdl_code` | int | Matched CDL code (-1 if no match) |
| `crop_area_m2` | float | Exact-crop pixel area within section (m²) |
| `section_area_m2` | float | Total section area (m²) |
| `ag_area_m2` | float | All-ag pixel area within section (m²) |
| `attribution_fraction` | float | Weight applied to `lbs_ai` [0, 1] |
| `fallback` | str | 'exact_crop', 'all_ag', or 'uniform' |

### `bbs_exposure_yearly_wide.csv` (primary model input)

369 rows × 291 columns. One row per (route, year). First eight columns are identifiers:

```
location_id, latitude, longitude, survey_start_date, survey_end_date,
route_id, year, BCR
```

Remaining 283 columns follow the pattern `{class}_{buffer_m}m_{lag_d}d_{metric}`.
Zero-fill for combinations not observed. Three routes with no PUR coverage are absent.

---

## 12. End-to-End Workflow

### First-time setup

```bash
cd /home/ubuntu/devops/pur/spatial
source /home/ubuntu/devops/pur/.venv/bin/activate

# 1. Download PLSS, initialize DuckDB (skip CDL on first pass to get schema up fast)
python spatial_setup.py --skip-cdl

# 2. Download CDL rasters (run yourself; takes ~3 hours for 9 years)
python download_cdl.py --years 2015 2016 2017 2018 2019 2020 2021 2022 2023

# 3. Load PUR records (requires ZIP archives in ../pur_analysis/cache/)
python pur_loader.py --years 2015 2016 2017 2018 2019 2020 2021 2022 2023

# 4. Compute CDL crop attribution
python crop_attribution.py

# 5. Validate
python validate.py
```

### After a DuckDB re-initialization

If `spatial_setup.py` is re-run (e.g., to reload PLSS), the `pur_records` table is
wiped. Reload from the existing Parquet (fast, ~10 seconds):

```python
import duckdb, pathlib
con = duckdb.connect("data/spatial.duckdb")
con.execute("LOAD spatial; DELETE FROM pur_records")
con.execute(f"""
    INSERT INTO pur_records
    SELECT id, year, comtrs, section_key, county_cd,
           chem_code::INTEGER, chemname, chem_class,
           lbs_ai::DOUBLE, acres_treated::DOUBLE,
           TRY_CAST(applic_dt AS DATE),
           site_code::INTEGER, site_name, aer_gnd_ind,
           avian_ld50::DOUBLE, avian_ceiling::BOOLEAN,
           aquatic_lc50::DOUBLE, aquatic_ceiling::BOOLEAN
    FROM read_parquet('outputs/pur_sections.parquet')
""")
```

### Building the BBS location set

```bash
# Download USGS BBS routes.csv and rank by PUR density
python - << 'EOF'
import requests, io, pandas as pd, duckdb
from pyproj import Transformer

r = requests.get(
    'https://www.sciencebase.gov/catalog/file/get/64ad9c3dd34e70357a292cee?name=routes.csv',
    timeout=30
)
# ... (see bbs_locations.csv generation code in session history)
EOF

# Run exposure engine — cumulative
python exposure_engine.py \
    --locations outputs/bbs_locations.csv \
    --output    outputs/bbs_exposure.csv

# Run exposure engine — per-year (primary model input)
python exposure_engine.py \
    --locations outputs/bbs_locations_yearly.csv \
    --output    outputs/bbs_exposure_yearly.csv
```

---

## 13. Known Issues and Workarounds

### NASS CDL 124 MiB per-connection limit

**Symptom:** Downloads stop at exactly 130,023,424 bytes (124 MiB) with
`IncompleteRead` or `ReadTimeout`. The file header is intact but pixel reads fail.

**Cause:** The NASS CropScape reverse proxy (`nassgeodata.gmu.edu`, hosted at George
Mason University) has a per-connection response body size limit of 124 MiB.
A bug report has been filed with NASS.

**Workaround:** Resume with HTTP `Range: bytes={offset}-` on the same download URL.
Requires 8–9 reconnects for a ~1 GB file. Implemented in both `spatial_setup.py` and
`download_cdl.py`. Run `download_cdl.py` manually (not via Claude) to avoid session
interruption.

**Validation:** Always validate CDL files with a pixel read, not just `src.meta`:
```python
with rasterio.open(path) as src:
    w = rasterio.windows.Window(src.width // 2, src.height - 100, 100, 100)
    src.read(1, window=w)   # raises exception on truncated files
```

### CDL bounding box gap (western California)

**Symptom:** Sections west of approximately −122°W at 38°N (Sacramento-San Joaquin
Delta, Bay Area, coastal counties) fall outside the CDL raster extent and receive
uniform attribution fallback.

**Cause:** The `CA_BBOX_5070` constant in `spatial_setup.py` was set to
`(-2_110_000, 1_480_000, -1_160_000, 2_490_000)`, which does not extend far enough
west. The western California coastline reaches approximately x = −2,400,000 in
EPSG:5070.

**Fix:** Change `CA_BBOX_5070` to `(-2_400_000, 1_400_000, -1_100_000, 2_500_000)`
and re-download CDL rasters. The corrected bbox adds approximately 290 km to the
western extent.

**Current impact:** Affects 5–8 BBS routes with low PUR density; does not affect the
high-exposure San Joaquin Valley routes.

### DuckDB `pur_records` wiped on re-setup

**Symptom:** Spatial queries return 0 records after re-running `spatial_setup.py`.

**Cause:** `init_duckdb()` drops and recreates all three tables including `pur_records`.

**Workaround:** Always check record count after any `spatial_setup.py` run:
```python
con.execute("SELECT COUNT(*) FROM pur_records").fetchone()  # should be 5,065,221
```
If 0, reload from Parquet as shown in §12.

### pyproj EPSG:3310 → EPSG:5070 transform produces out-of-bounds coordinates

**Symptom:** When chaining CRS transforms via pyproj (EPSG:3310 → EPSG:5070),
the resulting EPSG:5070 coordinates fall outside the CDL raster extent.

**Cause:** Not fully diagnosed; may relate to pyproj's internal handling of the
EPSG:3310 false northing (−4,000,000 m). Coordinates come out with plausible x
values but incorrect y.

**Workaround:** Use `rasterio.warp.transform` directly with the source and
destination CRS, skipping the EPSG:3310 intermediate:
```python
# Correct: WGS84 (or any CRS) → CDL CRS via rasterio
from rasterio.warp import transform as warp_transform
xs, ys = warp_transform("EPSG:3310", src.crs, [x0, x1], [y0, y1])
```

### 70% crop attribution uniform fallback

**Symptom:** 70% of (section, site) combinations receive `attribution_fraction = 1.0`
(uniform coverage of full section).

**Cause:** Many PUR `site_name` values (e.g., "OTHER FIELD CROPS", "RANGELAND",
"MULTIPLE CROPS") do not match any fragment in `SITE_TO_CDL`.

**Partial fix:** Expand the `SITE_TO_CDL` list in `crop_attribution.py`. Run this
query to see the top site names currently falling through to uniform:
```sql
SELECT site_name, COUNT(*) as n
FROM pur_records
WHERE site_name NOT IN (
    SELECT DISTINCT site_name
    FROM pur_records p
    JOIN crop_masks m ON p.section_key = m.section_key
        AND p.year = m.year AND p.site_code = m.site_code
    WHERE m.fallback != 'uniform'
)
GROUP BY site_name
ORDER BY n DESC
LIMIT 20
```

### 2023 COMTRS coverage at 44%

**Symptom:** `validate.py` warns that 2023 has only 44% of raw records with valid
COMTRS, compared to 76–88% for other years.

**Cause:** Known characteristic of the raw 2023 PUR data from CDPR. Not a pipeline
artifact. Records without COMTRS cannot be spatially located and are excluded.

**Impact:** 2023 exposure estimates are based on a smaller fraction of true applications
than earlier years. Validate 2023 results with additional caution.
