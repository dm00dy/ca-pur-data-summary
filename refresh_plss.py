#!/usr/bin/env python3
"""
Refresh the BLM PLSS download for California to recover unmatched PUR sections.

The current spatial/data/plss_ca.gpkg has 131,579 sections, but the BLM
CADNSDI service now serves 141,904 California sections (~10K more than when
the original file was downloaded). 3,569 PUR section keys (21% of all lbs)
have no matching polygon in the current file — this script tests whether a
fresh BLM download recovers them.

Downloads to spatial/data/plss_ca_v2.gpkg (side-by-side; original untouched).
Prints a coverage comparison: old vs new, and how many of the 3,569
previously-unmatched section keys now have geometry.

Usage:
    source .venv/bin/activate
    python refresh_plss.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape
from shapely.ops import unary_union

# Reuse constants and helpers from the spatial setup module
sys.path.insert(0, str(Path(__file__).parent / "spatial"))
from spatial_setup import (  # noqa: E402
    PAGE_SIZE,
    REQUEST_DELAY,
    CRS_ALBERS,
    BLM_MERIDIAN,
    _arcgis_count,
    _arcgis_page,
    _blm_section_key,
)

PARQUET_PATH = Path("./spatial/outputs/pur_sections.parquet")
OLD_PLSS     = Path("./spatial/data/plss_ca.gpkg")
NEW_PLSS     = Path("./spatial/data/plss_ca_v2.gpkg")

BLM_URL   = "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/2"
BLM_WHERE = "PLSSID LIKE 'CA%'"


def main() -> None:
    print("=" * 70)
    print("Step 1: Identify currently unmatched PUR section keys")
    print("=" * 70)
    agg = pd.read_parquet(PARQUET_PATH, columns=["section_key", "lbs_ai"])
    pur_secs = set(agg["section_key"].unique())
    print(f"  PUR sections: {len(pur_secs):,}")

    old_plss = gpd.read_file(OLD_PLSS, columns=["section_key"])
    old_secs = set(old_plss["section_key"].unique())
    print(f"  Old PLSS sections: {len(old_secs):,}")

    old_matched   = pur_secs & old_secs
    old_unmatched = pur_secs - old_secs
    old_lbs_um    = agg[agg["section_key"].isin(old_unmatched)]["lbs_ai"].sum()
    total_lbs     = agg["lbs_ai"].sum()
    print(f"  Currently matched:   {len(old_matched):,}")
    print(f"  Currently unmatched: {len(old_unmatched):,}  "
          f"({old_lbs_um:,.0f} lbs = {100*old_lbs_um/total_lbs:.1f}% of total)")

    print()
    print("=" * 70)
    print("Step 2: Download fresh BLM PLSS Layer 2 (CA sections)")
    print("=" * 70)
    total = _arcgis_count(BLM_URL, BLM_WHERE)
    print(f"  BLM reports {total:,} CA sections available")
    if total == 0:
        print("  ABORT: BLM returned 0 features")
        return

    features: list[dict] = []
    t0 = time.time()
    for offset in range(0, total, PAGE_SIZE):
        batch = _arcgis_page(BLM_URL, BLM_WHERE, offset)
        features.extend(batch)
        done = min(offset + PAGE_SIZE, total)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(f"\r  {done:,} / {total:,}  ({rate:.0f}/s, ETA {eta:.0f}s)",
              end="", flush=True)
        time.sleep(REQUEST_DELAY)
    print()
    print(f"  Downloaded {len(features):,} features in {time.time()-t0:.0f}s")

    print()
    print("=" * 70)
    print("Step 3: Build section_keys and union split sections")
    print("=" * 70)
    geoms = [shape(f["geometry"]) for f in features]
    props = [f["properties"] for f in features]
    gdf = gpd.GeoDataFrame(props, geometry=geoms, crs="EPSG:4326")

    gdf["section_key"] = gdf.apply(lambda r: _blm_section_key(r.to_dict()), axis=1)
    n_before = len(gdf)
    gdf = gdf[gdf["section_key"].notna() & (gdf["section_key"].str.len() == 9)]
    print(f"  Built keys: {len(gdf):,} valid / {n_before:,} raw "
          f"({n_before - len(gdf):,} dropped — missing/invalid)")

    # Union split sections (sections crossing county lines come in multiple polygons)
    n_unique = gdf["section_key"].nunique()
    if len(gdf) > n_unique:
        print(f"  Unioning {len(gdf) - n_unique:,} split-section fragments ...")
        unioned = (
            gdf.groupby("section_key")["geometry"]
            .apply(unary_union)
            .reset_index()
        )
        gdf = gpd.GeoDataFrame(unioned, geometry="geometry", crs="EPSG:4326")

    gdf["comtrs"] = ""
    gdf = gdf.to_crs(CRS_ALBERS)[["section_key", "comtrs", "geometry"]]
    new_secs = set(gdf["section_key"].unique())
    print(f"  Final unique sections: {len(new_secs):,}")

    print()
    print("=" * 70)
    print("Step 4: Coverage comparison")
    print("=" * 70)
    new_matched   = pur_secs & new_secs
    new_unmatched = pur_secs - new_secs
    new_lbs_um    = agg[agg["section_key"].isin(new_unmatched)]["lbs_ai"].sum()

    recovered = old_unmatched & new_secs
    rec_lbs   = agg[agg["section_key"].isin(recovered)]["lbs_ai"].sum()

    print(f"  Old → New PLSS sections:    {len(old_secs):,} → {len(new_secs):,}  "
          f"(+{len(new_secs) - len(old_secs):,})")
    print(f"  Old → New matched PUR:      {len(old_matched):,} → {len(new_matched):,}  "
          f"(+{len(new_matched) - len(old_matched):,})")
    print(f"  Old → New unmatched lbs:    {old_lbs_um:,.0f} → {new_lbs_um:,.0f}  "
          f"({100*new_lbs_um/total_lbs:.1f}% of total)")
    print(f"  Recovered section_keys:     {len(recovered):,}  "
          f"({rec_lbs:,.0f} lbs)")

    print()
    print("=" * 70)
    print("Step 5: Save fresh download")
    print("=" * 70)
    NEW_PLSS.parent.mkdir(parents=True, exist_ok=True)
    if NEW_PLSS.exists():
        NEW_PLSS.unlink()
    gdf.to_file(NEW_PLSS, driver="GPKG")
    print(f"  Wrote {NEW_PLSS} ({NEW_PLSS.stat().st_size / 1e6:.1f} MB)")
    print()
    print("  Original spatial/data/plss_ca.gpkg is UNCHANGED.")
    print("  Review coverage above; if better, replace the original with:")
    print(f"    mv {NEW_PLSS} {OLD_PLSS}")


if __name__ == "__main__":
    main()
