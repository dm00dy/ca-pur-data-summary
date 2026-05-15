#!/usr/bin/env python3
"""
Crop Attribution
================
For each unique (year, section, crop) in the PUR loader output, computes
the fraction of the section area plausibly covered by that crop, using the
USDA CDL annual raster.

Fallback hierarchy (documented in pipeline methods):
  1. 'exact_crop'  — CDL pixels matching the PUR site_code crop type
  2. 'all_ag'      — all agricultural CDL pixels in section (CDL codes 1-61)
  3. 'uniform'     — entire section area (used when CDL unavailable)

The output attribution_fraction field multiplies the raw lbs_ai in
exposure_engine.py to produce area-weighted exposure estimates.

Outputs:
    outputs/crop_attribution.parquet  — one row per (year, section_key, site_code)

Usage:
    python crop_attribution.py [--year YEAR] [--workers N]
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("outputs")
CDL_DIR = Path("data/cdl")
DB_PATH = Path("data/spatial.duckdb")
PUR_PARQUET = OUTPUT_DIR / "pur_sections.parquet"

# CDL codes classed as agricultural (row crops + orchards + fallow)
# CDL 1-61 are cultivated/crop classes; 62+ are non-agricultural
AG_CDL_CODES = set(range(1, 62))

# ---------------------------------------------------------------------------
# PUR SITE → CDL CROP CODE MAPPING
# ---------------------------------------------------------------------------
# Maps fragments of PUR site_name (lowercase) to CDL crop codes.
# Multiple CDL codes per crop cover classification variants across years.
# Source: NASS CDL class definitions (https://www.nass.usda.gov/Research_and_Science/Cropland/docs/cdl_codes.pdf)

SITE_TO_CDL: list[tuple[str, set[int]]] = [
    # Grains
    ("corn",          {1, 12, 46}),
    ("cotton",        {2}),
    ("rice",          {3}),
    ("sorghum",       {4}),
    ("barley",        {21}),
    ("wheat",         {22, 23, 24}),
    ("oats",          {28}),
    ("sunflower",     {6}),
    ("canola",        {31}),
    ("flaxseed",      {31}),
    # Vegetables
    ("tomato",        {54, 206}),
    ("lettuce",       {49, 206}),
    ("potato",        {43}),
    ("onion",         {206}),
    ("carrot",        {206}),
    ("celery",        {206}),
    ("garlic",        {206}),
    ("pepper",        {206}),
    ("squash",        {206}),
    ("melon",         {46}),
    ("watermelon",    {46}),
    ("cucumber",      {206}),
    ("spinach",       {206}),
    ("broccoli",      {206}),
    ("cauliflower",   {206}),
    ("bean",          {42, 53}),
    ("pea",           {52}),
    # Field crops
    ("alfalfa",       {36}),
    ("hay",           {37, 36}),
    ("safflower",     {6}),
    ("sugar beet",    {41}),
    ("soybean",       {5}),
    # Orchards / vineyards
    ("almond",        {75}),
    ("walnut",        {76}),
    ("pistachio",     {204}),
    ("pecan",         {77}),
    ("grape",         {69}),
    ("citrus",        {72, 71}),
    ("orange",        {72}),
    ("lemon",         {72}),
    ("peach",         {67}),
    ("nectarine",     {67}),
    ("plum",          {67}),
    ("prune",         {67}),
    ("cherry",        {66}),
    ("apple",         {68}),
    ("pear",          {65}),
    ("apricot",       {67}),
    ("fig",           {204}),
    ("olive",         {204}),
    ("avocado",       {211}),
    ("strawberry",    {221}),
    ("blueberry",     {242}),
    # Specialty
    ("mint",          {14}),
    ("hops",          {206}),
    ("nursery",       {68, 204}),
    ("flowers",       {206}),
]

# CDL codes that should never appear (non-plant / water / developed)
NON_AG_FLOOR = 62  # codes >= 62 are non-agricultural in CDL


def site_name_to_cdl_codes(site_name: str | None) -> set[int]:
    """Map a PUR site_name string to a set of CDL crop codes.

    Returns empty set if no match found (caller should use all_ag fallback).
    """
    if not site_name or str(site_name).strip().lower() in ("nan", ""):
        return set()
    sn = str(site_name).lower().strip()
    matched: set[int] = set()
    for fragment, codes in SITE_TO_CDL:
        if fragment in sn:
            matched |= codes
    return matched


# ---------------------------------------------------------------------------
# CDL WINDOW READ
# ---------------------------------------------------------------------------

def _rasterio_available() -> bool:
    try:
        import rasterio  # noqa: F401
        return True
    except ImportError:
        return False


def _read_cdl_window(
    cdl_path: Path,
    geom_3310,
) -> np.ndarray | None:
    """Window-read CDL pixels within the bounding box of geom (EPSG:3310).

    Returns 1-D array of CDL codes, or None if CDL file unavailable.
    CDL is in EPSG:5070 (NAD83/Conus Albers); bbox is reprojected before read.
    """
    if not cdl_path.exists():
        return None

    import rasterio
    from pyproj import Transformer
    from rasterio.windows import from_bounds

    with rasterio.open(cdl_path) as src:
        # Transform section bbox from EPSG:3310 → CDL native CRS (EPSG:5070)
        t = Transformer.from_crs("EPSG:3310", src.crs.to_epsg() or 5070,
                                  always_xy=True)
        bounds = geom_3310.bounds  # (minx, miny, maxx, maxy) in 3310
        xmin, ymin = t.transform(bounds[0], bounds[1])
        xmax, ymax = t.transform(bounds[2], bounds[3])
        win = from_bounds(
            min(xmin, xmax), min(ymin, ymax),
            max(xmin, xmax), max(ymin, ymax),
            src.transform,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            data = src.read(1, window=win)
    return data.ravel()


# ---------------------------------------------------------------------------
# ATTRIBUTION COMPUTATION
# ---------------------------------------------------------------------------

def compute_attribution(
    section_key: str,
    site_code: int,
    site_name: str | None,
    year: int,
    geom_3310,
) -> dict:
    """Compute attribution fraction for one (section, site, year) combination."""

    base = {
        "year": year,
        "section_key": section_key,
        "site_code": int(site_code) if pd.notna(site_code) else -1,
        "cdl_code": -1,
        "crop_area_m2": None,
        "section_area_m2": geom_3310.area if geom_3310 is not None else None,
        "ag_area_m2": None,
        "attribution_fraction": 1.0,
        "fallback": "uniform",
    }

    if geom_3310 is None:
        return base

    cdl_path = CDL_DIR / f"cdl_{year}_ca.tif"
    pixels = _read_cdl_window(cdl_path, geom_3310)

    if pixels is None or pixels.size == 0:
        # No CDL available — uniform fallback
        return base

    # Pixel area in m²: CDL is 30m resolution
    PIXEL_AREA = 30 * 30

    total_px = pixels.size
    ag_px = int((pixels < NON_AG_FLOOR).sum())
    base["ag_area_m2"] = ag_px * PIXEL_AREA

    cdl_codes = site_name_to_cdl_codes(site_name)
    if cdl_codes:
        crop_px = int(np.isin(pixels, list(cdl_codes)).sum())
        if crop_px > 0:
            base["cdl_code"] = next(iter(cdl_codes))
            base["crop_area_m2"] = crop_px * PIXEL_AREA
            denom = total_px * PIXEL_AREA
            base["attribution_fraction"] = (crop_px * PIXEL_AREA) / denom if denom > 0 else 1.0
            base["fallback"] = "exact_crop"
            return base

    # Fall back to all-ag pixels
    if ag_px > 0:
        denom = total_px * PIXEL_AREA
        base["attribution_fraction"] = (ag_px * PIXEL_AREA) / denom if denom > 0 else 1.0
        base["fallback"] = "all_ag"
    else:
        base["attribution_fraction"] = 1.0
        base["fallback"] = "uniform"

    return base


# ---------------------------------------------------------------------------
# SECTION GEOMETRY LOOKUP
# ---------------------------------------------------------------------------

def load_section_geoms(section_keys: list[str]) -> dict[str, object]:
    """Load section geometries from DuckDB. Returns {section_key: shapely_geom}."""
    if not DB_PATH.exists():
        return {}
    from shapely.wkt import loads as wkt_loads
    keys_str = ", ".join(f"'{k}'" for k in section_keys)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute("LOAD spatial;")
    rows = con.execute(
        f"SELECT section_key, ST_AsText(geom) FROM plss_sections "
        f"WHERE section_key IN ({keys_str})"
    ).fetchall()
    con.close()
    return {r[0]: wkt_loads(r[1]) for r in rows}


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Compute crop attribution fractions from CDL")
    parser.add_argument("--year", type=int, default=None,
                        help="Process a single year (default: all years in pur_sections.parquet)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not PUR_PARQUET.exists():
        raise FileNotFoundError(
            f"PUR records not found at {PUR_PARQUET}. Run pur_loader.py first."
        )

    pur = pd.read_parquet(PUR_PARQUET, columns=[
        "year", "section_key", "site_code", "site_name",
    ])
    if args.year is not None:
        pur = pur[pur["year"] == args.year]

    # Unique (year, section_key, site_code) combinations
    combos = (
        pur.drop_duplicates(subset=["year", "section_key", "site_code"])
        .dropna(subset=["section_key"])
        .reset_index(drop=True)
    )
    print(f"{len(combos):,} unique (year, section, site) combinations to attribute")

    if not _rasterio_available():
        print("WARNING: rasterio not installed — all records will use 'uniform' fallback")
        print("Install: pip install rasterio")

    # Load all needed section geometries in one query
    section_keys = combos["section_key"].unique().tolist()
    print(f"Loading {len(section_keys):,} section geometries from DuckDB ...")
    geom_map = load_section_geoms(section_keys)
    print(f"  {len(geom_map):,} geometries loaded ({len(section_keys) - len(geom_map):,} missing from PLSS)")

    results: list[dict] = []
    years = sorted(combos["year"].unique())
    for year in years:
        subset = combos[combos["year"] == year]
        cdl_exists = (CDL_DIR / f"cdl_{year}_ca.tif").exists()
        print(f"  [{year}] {len(subset):,} combos across "
              f"{subset['section_key'].nunique():,} sections, "
              f"CDL: {'yes' if cdl_exists else 'NO — uniform fallback'}")

        cdl_path_year = CDL_DIR / f"cdl_{year}_ca.tif"
        # Group by section so we read each CDL window once per section, not once per combo
        section_groups = subset.groupby("section_key", sort=False)
        n_sections = len(section_groups)
        for i, (section_key, rows) in enumerate(section_groups, 1):
            geom = geom_map.get(section_key)

            # Read CDL pixels once for this section
            pixels = _read_cdl_window(cdl_path_year, geom) if (geom is not None and cdl_exists) else None

            PIXEL_AREA = 30 * 30
            total_px = pixels.size if pixels is not None else 0
            ag_px = int((pixels < NON_AG_FLOOR).sum()) if pixels is not None else 0

            for _, row in rows.iterrows():
                base = {
                    "year": year,
                    "section_key": section_key,
                    "site_code": int(row["site_code"]) if pd.notna(row["site_code"]) else -1,
                    "cdl_code": -1,
                    "crop_area_m2": None,
                    "section_area_m2": geom.area if geom is not None else None,
                    "ag_area_m2": ag_px * PIXEL_AREA if pixels is not None else None,
                    "attribution_fraction": 1.0,
                    "fallback": "uniform",
                }

                if pixels is None or pixels.size == 0:
                    results.append(base)
                    continue

                cdl_codes = site_name_to_cdl_codes(row.get("site_name"))
                if cdl_codes:
                    crop_px = int(np.isin(pixels, list(cdl_codes)).sum())
                    if crop_px > 0:
                        denom = total_px * PIXEL_AREA
                        base.update({
                            "cdl_code": next(iter(cdl_codes)),
                            "crop_area_m2": crop_px * PIXEL_AREA,
                            "attribution_fraction": (crop_px * PIXEL_AREA) / denom if denom > 0 else 1.0,
                            "fallback": "exact_crop",
                        })
                        results.append(base)
                        continue

                if ag_px > 0:
                    denom = total_px * PIXEL_AREA
                    base["attribution_fraction"] = (ag_px * PIXEL_AREA) / denom if denom > 0 else 1.0
                    base["fallback"] = "all_ag"

                results.append(base)

            if i % 1000 == 0 or i == n_sections:
                print(f"\r    {i:,}/{n_sections:,} sections", end="", flush=True)
        print()

    attr_df = pd.DataFrame(results)
    out_path = OUTPUT_DIR / "crop_attribution.parquet"
    attr_df.to_parquet(out_path, index=False)
    print(f"\n{len(attr_df):,} attribution records → {out_path}")

    # Summary of fallback tiers
    counts = attr_df["fallback"].value_counts()
    print("\nFallback distribution:")
    for tier, n in counts.items():
        print(f"  {tier:<15} {n:>8,}  ({100 * n / len(attr_df):.1f}%)")

    # Load into DuckDB if available
    if DB_PATH.exists():
        con = duckdb.connect(str(DB_PATH))
        con.execute("LOAD spatial;")
        con.execute("DELETE FROM crop_masks")
        tmp = OUTPUT_DIR / "_tmp_attr.parquet"
        attr_df.to_parquet(tmp, index=False)
        con.execute(f"INSERT INTO crop_masks SELECT * FROM read_parquet('{tmp}')")
        con.close()
        tmp.unlink(missing_ok=True)
        print(f"DuckDB: crop_masks updated")


if __name__ == "__main__":
    main()
