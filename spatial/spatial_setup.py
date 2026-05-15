#!/usr/bin/env python3
"""
Spatial Setup
=============
One-time setup: downloads California PLSS section polygons and USDA CDL annual
rasters, initializes the DuckDB spatial database for the exposure pipeline.

Run once before using other pipeline modules:
    python spatial_setup.py [--years 2015 2016 ...] [--skip-cdl] [--force]

Downloads ~50-200 MB (PLSS) + ~200-350 MB/year (CDL, optional).
CDL for 2015-2023 is ~2.7 GB total; skip with --skip-cdl and crop_attribution.py
will fall back to uniform-within-section.
"""

from __future__ import annotations

import argparse
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import duckdb
import geopandas as gpd
import requests
from shapely.geometry import shape

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "spatial.duckdb"
PLSS_GPKG = DATA_DIR / "plss_ca.gpkg"
CDL_DIR = DATA_DIR / "cdl"

CRS_ALBERS = "EPSG:3310"  # California Albers (meters) — all geometry stored in this CRS

# PLSS sources tried in order; first success wins
PLSS_SOURCES = [
    {
        "name": "CDPR PLSS Feature Service",
        # Verify exact path at https://gis.cdpr.ca.gov/arcgis/rest/services/
        "url": "https://gis.cdpr.ca.gov/arcgis/rest/services/PUR/PLSS_Sections/FeatureServer/0",
        "where": "1=1",
        "comtrs_field": "COMTRS",
    },
    {
        "name": "BLM PLSS CadNSDI (layer 2 — sections)",
        # Layer 2 = PLSS Section. Filter by PLSSID prefix 'CA' for California only.
        "url": "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/2",
        "where": "PLSSID LIKE 'CA%'",
        "comtrs_field": None,  # built from PLSSID + FRSTDIVNO
    },
]

# BLM PLSSID meridian numeric code → PUR single-char meridian (base_ln_mer in UDC)
BLM_MERIDIAN = {21: "M", 27: "S", 18: "H"}  # Mount Diablo, San Bernardino, Humboldt

# NASS CropScape WCS — returns a redirect URL to a clipped GeoTIFF
CDL_WCS = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile"

# California bbox in EPSG:5070 (NAD83 / Conus Albers — CDL native CRS)
CA_BBOX_5070 = (-2_110_000, 1_480_000, -1_160_000, 2_490_000)

PAGE_SIZE = 1000   # ArcGIS REST records per page
REQUEST_DELAY = 0.05  # polite pacing between pages (seconds)


# ---------------------------------------------------------------------------
# ARCGIS REST HELPERS
# ---------------------------------------------------------------------------

def _arcgis_count(url: str, where: str) -> int:
    r = requests.get(
        f"{url}/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("count", 0)


def _arcgis_page(url: str, where: str, offset: int) -> list[dict]:
    params = {
        "where": where,
        "outFields": "*",
        "returnGeometry": "true",
        "geometryType": "esriGeometryPolygon",
        "f": "geojson",
        "outSR": "4326",          # always request WGS84; required for GeoJSON parsing
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
    }
    r = requests.get(f"{url}/query", params=params, timeout=120)
    r.raise_for_status()
    return r.json().get("features", [])


# ---------------------------------------------------------------------------
# PLSS DOWNLOAD
# ---------------------------------------------------------------------------

def _blm_section_key(props: dict) -> str | None:
    """Build 9-char section key from BLM PLSS layer-2 feature properties.

    PLSSID format: state(2) + meridian(2) + township(3) + pad(1) + tdir(1)
                   + range(3) + pad(1) + rdir(1) + level_flag(1)
    Example: 'CA210480N0170E0' → meridian=21('M'), twp=48, N, range=17, E

    FRSTDIVNO: section number within the township (int as string, e.g. '32').
    """
    try:
        plssid = str(props.get("PLSSID", ""))
        if len(plssid) < 14 or plssid[:2] != "CA":
            return None
        meridian_id = int(plssid[2:4])
        meridian = BLM_MERIDIAN.get(meridian_id)
        if not meridian:
            return None
        twp = int(plssid[4:7])
        tdir = plssid[8].upper()        # N or S (index 7 is a zero-pad)
        rng = int(plssid[9:12])
        rdir = plssid[13].upper()       # E or W (index 12 is a zero-pad)
        sec = int(props["FRSTDIVNO"])
        if not (1 <= sec <= 36):
            return None
        return f"{meridian}{twp:02d}{tdir}{rng:02d}{rdir}{sec:02d}"
    except (KeyError, ValueError, TypeError, IndexError):
        return None


def download_plss(force: bool = False) -> gpd.GeoDataFrame:
    """Download CA PLSS section polygons. Returns GeoDataFrame in CRS_ALBERS."""
    if PLSS_GPKG.exists() and not force:
        print(f"  PLSS: loading cached {PLSS_GPKG}")
        gdf = gpd.read_file(PLSS_GPKG)
        print(f"  {len(gdf):,} sections loaded")
        return gdf

    for src in PLSS_SOURCES:
        print(f"  PLSS: trying {src['name']} ...")
        try:
            total = _arcgis_count(src["url"], src["where"])
            if total == 0:
                print("    returned 0 features; trying next source")
                continue
            print(f"    {total:,} features — downloading ...")

            features: list[dict] = []
            for offset in range(0, total, PAGE_SIZE):
                batch = _arcgis_page(src["url"], src["where"], offset)
                features.extend(batch)
                done = min(offset + PAGE_SIZE, total)
                print(f"\r    {done:,} / {total:,}", end="", flush=True)
                time.sleep(REQUEST_DELAY)
            print()

            geoms = [shape(f["geometry"]) for f in features]
            props = [f["properties"] for f in features]
            gdf = gpd.GeoDataFrame(props, geometry=geoms, crs="EPSG:4326")

            if src["comtrs_field"] and src["comtrs_field"] in gdf.columns:
                gdf["comtrs"] = gdf[src["comtrs_field"]].str.strip().str.upper()
                gdf["section_key"] = gdf["comtrs"].str[2:]
            else:
                gdf["section_key"] = gdf.apply(
                    lambda r: _blm_section_key(r.to_dict()), axis=1
                )
                gdf["comtrs"] = ""

            before = len(gdf)
            gdf = gdf[gdf["section_key"].notna() & (gdf["section_key"].str.len() == 9)]

            # Some sections are split by county lines (multiple partial polygons per key).
            # Union them back into one polygon per section_key.
            n_raw = len(gdf)
            n_unique = gdf["section_key"].nunique()
            if n_raw > n_unique:
                from shapely.ops import unary_union
                unioned_geoms = (
                    gdf.groupby("section_key")["geometry"]
                    .apply(unary_union)
                    .reset_index()
                    .rename(columns={"geometry": "geometry"})
                )
                # Carry comtrs from first occurrence of each section_key
                comtrs_first = (
                    gdf.drop_duplicates("section_key")
                    .set_index("section_key")["comtrs"]
                )
                unioned_geoms["comtrs"] = unioned_geoms["section_key"].map(comtrs_first).fillna("")
                gdf = gpd.GeoDataFrame(unioned_geoms, geometry="geometry", crs="EPSG:4326")
                print(f"    unioned {n_raw - n_unique} split-section fragments → {n_unique} sections")

            dropped = before - len(gdf)
            if dropped:
                print(f"    dropped {dropped} records with missing/invalid keys")

            gdf = gdf.to_crs(CRS_ALBERS)[["section_key", "comtrs", "geometry"]]

            PLSS_GPKG.parent.mkdir(parents=True, exist_ok=True)
            gdf.to_file(PLSS_GPKG, driver="GPKG")
            print(f"    {len(gdf):,} sections → {PLSS_GPKG}")
            return gdf

        except Exception as exc:
            print(f"    FAILED: {exc}")

    raise RuntimeError(
        "Could not download PLSS from any source.\n"
        "Check network access to gis.cdpr.ca.gov and gis.blm.gov,\n"
        "or manually place a GeoPackage at data/plss_ca.gpkg with\n"
        "columns: section_key (9-char), comtrs (11-char), geometry (EPSG:3310)."
    )


# ---------------------------------------------------------------------------
# CDL DOWNLOAD
# ---------------------------------------------------------------------------

def cdl_path(year: int) -> Path:
    return CDL_DIR / f"cdl_{year}_ca.tif"


def _get_nass_url(year: int) -> str:
    """Request a CDL clip URL from NASS CropScape WCS. Retries on timeout."""
    xmin, ymin, xmax, ymax = CA_BBOX_5070
    for attempt in range(1, 6):
        try:
            r = requests.get(
                CDL_WCS,
                params={
                    "year": year,
                    "bbox": f"{xmin},{ymin},{xmax},{ymax}",
                    "format": "GeoTIFF",
                    "crs": "EPSG:5070",
                },
                timeout=300,   # NASS server is slow; give it 5 min
            )
            r.raise_for_status()
            root = ET.fromstring(r.text)
            url_el = root.find(".//{*}returnURL")
            if url_el is None:
                url_el = root.find("returnURL")
            if url_el is None or not (url_el.text or "").strip():
                raise RuntimeError(f"No returnURL in response: {r.text[:200]}")
            return url_el.text.strip()
        except Exception as exc:
            if attempt < 5:
                print(f"    attempt {attempt} failed ({exc}); retrying in {10 * attempt}s ...")
                time.sleep(10 * attempt)
            else:
                raise


def download_cdl_year(year: int, force: bool = False) -> Path:
    """Download USDA CDL GeoTIFF for California from NASS CropScape WCS.

    Validates existing files with rasterio (detects truncated downloads).
    Resumes partial downloads via HTTP Range. Retries up to 3× on errors.
    Files are ~1 GB uncompressed; allow ~20 min per year.
    """
    out = cdl_path(year)
    CDL_DIR.mkdir(parents=True, exist_ok=True)

    # Validate any existing file; incomplete files fail to open in rasterio
    if out.exists() and not force:
        try:
            import rasterio
            with rasterio.open(out) as src:
                _ = src.meta
            mb = out.stat().st_size / 1e6
            print(f"  CDL {year}: cached and valid ({mb:.0f} MB)")
            return out
        except Exception:
            print(f"  CDL {year}: existing file is incomplete — deleting and restarting")
            out.unlink()  # partial file is from an old URL; must start fresh

    print(f"  CDL {year}: requesting URL from NASS CropScape WCS ...")
    file_url = _get_nass_url(year)
    print(f"    {file_url}")

    # NASS drops connections at ~130 MB; resume with Range headers each time.
    # 1066 MB / 130 MB per connection ≈ 9 connections needed; use 20 to be safe.
    written_so_far = 0
    max_attempts = 20
    for attempt in range(1, max_attempts + 1):
        headers = {"Range": f"bytes={written_so_far}-"} if written_so_far else {}
        mode = "ab" if written_so_far else "wb"
        if written_so_far:
            print(f"    resuming from {written_so_far / 1e6:.0f} MB (attempt {attempt})")
        try:
            with requests.get(file_url, stream=True, timeout=3600, headers=headers) as dl:
                if dl.status_code == 416:
                    print(f"    server says download complete (416)")
                    return out
                dl.raise_for_status()
                total_bytes = int(dl.headers.get("content-length", 0)) + written_so_far
                total_mb = total_bytes / 1e6
                downloaded = written_so_far
                with open(out, mode) as f:
                    for chunk in dl.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_mb:
                            print(f"\r    {downloaded / 1e6:.0f} / {total_mb:.0f} MB",
                                  end="", flush=True)
            print(f"\n    saved → {out} ({out.stat().st_size / 1e6:.0f} MB)")
            return out
        except Exception as exc:
            written_so_far = out.stat().st_size if out.exists() else 0
            if attempt < max_attempts:
                print(f"\n    network error ({exc}); retrying in 15s ...")
                time.sleep(15)
            else:
                raise RuntimeError(f"CDL {year} failed after {max_attempts} attempts: {exc}")


# ---------------------------------------------------------------------------
# DUCKDB INITIALIZATION
# ---------------------------------------------------------------------------

def init_duckdb(plss_gdf: gpd.GeoDataFrame) -> None:
    """Create the DuckDB spatial database and load PLSS section geometries."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("INSTALL spatial; LOAD spatial;")

    con.execute("DROP TABLE IF EXISTS plss_sections")
    con.execute("""
        CREATE TABLE plss_sections (
            section_key VARCHAR PRIMARY KEY,
            comtrs      VARCHAR,
            geom        GEOMETRY
        )
    """)

    # Filter invalid geometries, then bulk-load via temp GeoPackage read
    valid = plss_gdf[plss_gdf.geometry.notna() & plss_gdf.geometry.is_valid].copy()
    n_dropped = len(plss_gdf) - len(valid)
    if n_dropped:
        print(f"  DuckDB: dropped {n_dropped} features with invalid/null geometry")

    # Vectorized WKB export then bulk insert via temp Parquet (much faster than iterrows)
    import tempfile, os
    valid["wkb_hex"] = valid.geometry.to_wkb(hex=True)
    tmp_df = valid[["section_key", "comtrs", "wkb_hex"]].copy()
    tmp_df["comtrs"] = tmp_df["comtrs"].fillna("").astype(str)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tf:
        tmp_path = tf.name
    tmp_df.to_parquet(tmp_path, index=False)
    con.execute(f"""
        INSERT INTO plss_sections
        SELECT section_key, comtrs, ST_GeomFromHEXWKB(wkb_hex)
        FROM read_parquet('{tmp_path}')
        WHERE wkb_hex IS NOT NULL
    """)
    os.unlink(tmp_path)
    con.execute("CREATE INDEX idx_plss_key ON plss_sections (section_key)")
    n = con.execute("SELECT COUNT(*) FROM plss_sections").fetchone()[0]
    print(f"  DuckDB: {n:,} PLSS sections loaded")

    # PUR records table — populated by pur_loader.py
    con.execute("DROP TABLE IF EXISTS pur_records")
    con.execute("""
        CREATE TABLE pur_records (
            id               BIGINT,
            year             INTEGER,
            comtrs           VARCHAR(11),
            section_key      VARCHAR(9),
            county_cd        VARCHAR(2),
            chem_code        INTEGER,
            chemname         VARCHAR,
            chem_class       VARCHAR,
            lbs_ai           DOUBLE,
            acres_treated    DOUBLE,
            applic_dt        DATE,
            site_code        INTEGER,
            site_name        VARCHAR,
            aer_gnd_ind      VARCHAR(1),
            avian_ld50       DOUBLE,
            avian_ceiling    BOOLEAN,
            aquatic_lc50     DOUBLE,
            aquatic_ceiling  BOOLEAN
        )
    """)

    # Crop attribution table — populated by crop_attribution.py
    con.execute("DROP TABLE IF EXISTS crop_masks")
    con.execute("""
        CREATE TABLE crop_masks (
            year                 INTEGER,
            section_key          VARCHAR(9),
            site_code            INTEGER,
            cdl_code             INTEGER,
            crop_area_m2         DOUBLE,
            section_area_m2      DOUBLE,
            ag_area_m2           DOUBLE,
            attribution_fraction DOUBLE,
            fallback             VARCHAR
        )
    """)

    con.close()
    print(f"  DuckDB: schema initialized → {DB_PATH}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Spatial pipeline one-time setup")
    parser.add_argument("--years", nargs="+", type=int,
                        default=list(range(2015, 2024)),
                        help="Years for CDL download (default 2015-2023)")
    parser.add_argument("--skip-cdl", action="store_true",
                        help="Skip CDL raster download (~300 MB/year)")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if cached files exist")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CDL_DIR.mkdir(parents=True, exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    print("Step 1: PLSS sections")
    plss_gdf = download_plss(force=args.force)

    print("\nStep 2: DuckDB initialization")
    init_duckdb(plss_gdf)

    if not args.skip_cdl:
        print(f"\nStep 3: CDL rasters for {len(args.years)} year(s)")
        for year in args.years:
            try:
                download_cdl_year(year, force=args.force)
            except Exception as exc:
                print(f"  CDL {year}: FAILED — {exc}")
    else:
        print("\nStep 3: CDL skipped (--skip-cdl)")
        print("  crop_attribution.py will fall back to uniform-within-section")

    print("\nSetup complete.")
    print(f"  PLSS GeoPackage: {PLSS_GPKG}")
    print(f"  DuckDB:          {DB_PATH}")
    cdl_files = sorted(CDL_DIR.glob("cdl_*.tif"))
    if cdl_files:
        print(f"  CDL rasters:     {len(cdl_files)} files in {CDL_DIR}/")


if __name__ == "__main__":
    main()
