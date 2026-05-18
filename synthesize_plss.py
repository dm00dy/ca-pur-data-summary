#!/usr/bin/env python3
"""
Synthesize PLSS section polygons for PUR section_keys that don't exist in
BLM CADNSDI. These are overwhelmingly in Mexican land grant (rancho) areas
where the PLSS grid was never surveyed on the ground — yet CDPR's PUR
COMTRS field uses synthetic section keys derived from a virtual 6×6 grid
overlaid on every township.

We replicate that virtual grid here: download BLM Layer 1 (PLSS Township)
polygons, subdivide each into 36 sections using standard PLSS numbering
(NE corner = section 1, boustrophedon down to SE corner = section 36),
clip to the actual township polygon (handles coastal irregularity), and
merge into an augmented PLSS file.

Standard PLSS section numbering inside a township (north at top):

     6  5  4  3  2  1
     7  8  9 10 11 12
    18 17 16 15 14 13
    19 20 21 22 23 24
    30 29 28 27 26 25
    31 32 33 34 35 36

Output:
    spatial/data/plss_ca_augmented.gpkg
        Columns: section_key, comtrs, geometry, source ('blm' or 'synthetic')

The original spatial/data/plss_ca.gpkg is untouched.

Usage:
    source .venv/bin/activate
    python synthesize_plss.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box, shape

sys.path.insert(0, str(Path(__file__).parent / "spatial"))
from spatial_setup import (  # noqa: E402
    PAGE_SIZE,
    REQUEST_DELAY,
    CRS_ALBERS,
    BLM_MERIDIAN,
    _arcgis_count,
    _arcgis_page,
)

PARQUET_PATH = Path("./spatial/outputs/pur_sections.parquet")
OLD_PLSS     = Path("./spatial/data/plss_ca.gpkg")
NEW_PLSS     = Path("./spatial/data/plss_ca_augmented.gpkg")

BLM_TWP_URL = "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer/1"
BLM_WHERE   = "PLSSID LIKE 'CA%'"

# Inverse of BLM_MERIDIAN — needed to turn PUR's "M14N01E" key into a BLM PLSSID
MERIDIAN_INV = {v: k for k, v in BLM_MERIDIAN.items()}


def twp_key_to_plssid(twp_key: str) -> str | None:
    """Convert 7-char township key 'M14N01E' → BLM 15-char PLSSID 'CA210140N0010E0'."""
    try:
        meridian_num = MERIDIAN_INV[twp_key[0]]
        twp = int(twp_key[1:3])
        tdir = twp_key[3]
        rng = int(twp_key[4:6])
        rdir = twp_key[6]
        return f"CA{meridian_num:02d}{twp:03d}0{tdir}{rng:03d}0{rdir}0"
    except (KeyError, ValueError):
        return None


def section_no_to_grid(sec: int) -> tuple[int, int]:
    """
    Inverse of the boustrophedon numbering: section_no (1-36) → (row, col).
    row=0 is south, row=5 is north. col=0 is west, col=5 is east.
    """
    if not 1 <= sec <= 36:
        raise ValueError(sec)
    rft = (sec - 1) // 6           # row-from-top (0 = northernmost row, sections 1-6)
    pos_in_row = (sec - 1) % 6     # 0-5 within the row
    if rft % 2 == 0:               # rows 0, 2, 4 — numbered east-to-west
        col = 5 - pos_in_row
    else:                          # rows 1, 3, 5 — numbered west-to-east
        col = pos_in_row
    row = 5 - rft                  # convert to south-origin row
    return row, col


def synthesize_section(twp_poly, twp_bounds: tuple, sec: int):
    """Build the synthetic 1/36-of-township polygon for the given section number."""
    minx, miny, maxx, maxy = twp_bounds
    dx = (maxx - minx) / 6
    dy = (maxy - miny) / 6
    row, col = section_no_to_grid(sec)
    cell_minx = minx + col * dx
    cell_maxx = minx + (col + 1) * dx
    cell_miny = miny + row * dy
    cell_maxy = miny + (row + 1) * dy
    cell = box(cell_minx, cell_miny, cell_maxx, cell_maxy)
    return cell.intersection(twp_poly)


def main() -> None:
    print("=" * 70)
    print("Step 1: Identify unmatched PUR sections and parent townships")
    print("=" * 70)
    agg = pd.read_parquet(PARQUET_PATH, columns=["section_key", "lbs_ai"])
    pur_secs = set(agg["section_key"].unique())
    old_plss = gpd.read_file(OLD_PLSS)
    old_secs = set(old_plss["section_key"].unique())
    unmatched = pur_secs - old_secs

    # Group unmatched sections by parent township (first 7 chars of section_key)
    unmatched_by_twp: dict[str, list[int]] = {}
    for sk in unmatched:
        twp_key = sk[:7]
        sec_no = int(sk[7:9])
        unmatched_by_twp.setdefault(twp_key, []).append(sec_no)

    total_lbs = agg["lbs_ai"].sum()
    um_lbs = agg[agg["section_key"].isin(unmatched)]["lbs_ai"].sum()
    print(f"  Unmatched PUR sections: {len(unmatched):,}  "
          f"({um_lbs:,.0f} lbs = {100*um_lbs/total_lbs:.1f}% of total)")
    print(f"  Unique parent townships needed: {len(unmatched_by_twp):,}")

    print()
    print("=" * 70)
    print("Step 2: Download BLM PLSS Township polygons for CA")
    print("=" * 70)
    total = _arcgis_count(BLM_TWP_URL, BLM_WHERE)
    print(f"  BLM reports {total:,} CA townships")

    features: list[dict] = []
    t0 = time.time()
    for offset in range(0, total, PAGE_SIZE):
        batch = _arcgis_page(BLM_TWP_URL, BLM_WHERE, offset)
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

    # Build dict: PLSSID → township polygon (in CA Albers for metric grid)
    geoms = [shape(f["geometry"]) for f in features]
    props = [f["properties"] for f in features]
    twp_gdf = gpd.GeoDataFrame(props, geometry=geoms, crs="EPSG:4326").to_crs(CRS_ALBERS)
    twp_gdf = twp_gdf.dissolve(by="PLSSID").reset_index()   # union split townships
    twp_lookup: dict[str, object] = dict(zip(twp_gdf["PLSSID"], twp_gdf.geometry))
    print(f"  Indexed {len(twp_lookup):,} unique CA townships")

    print()
    print("=" * 70)
    print("Step 3: Synthesize section polygons for unmatched keys")
    print("=" * 70)
    rows = []
    no_township = 0
    bad_geom = 0
    for twp_key, sec_list in unmatched_by_twp.items():
        plssid = twp_key_to_plssid(twp_key)
        if plssid is None:
            no_township += len(sec_list)
            continue
        twp_poly = twp_lookup.get(plssid)
        if twp_poly is None:
            no_township += len(sec_list)
            continue
        bounds = twp_poly.bounds
        for sec_no in sec_list:
            sec_poly = synthesize_section(twp_poly, bounds, sec_no)
            if sec_poly.is_empty or not sec_poly.is_valid:
                bad_geom += 1
                continue
            section_key = f"{twp_key}{sec_no:02d}"
            rows.append({
                "section_key": section_key,
                "comtrs": "",
                "geometry": sec_poly,
                "source": "synthetic",
            })

    synth_gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS_ALBERS)
    print(f"  Synthesized {len(synth_gdf):,} section polygons")
    print(f"  Skipped {no_township:,} (parent township not in BLM)")
    print(f"  Skipped {bad_geom:,} (empty/invalid geometry after clip)")

    rec_lbs = agg[agg["section_key"].isin(set(synth_gdf["section_key"]))]["lbs_ai"].sum()
    print(f"  Recovered {rec_lbs:,.0f} lbs "
          f"({100*rec_lbs/total_lbs:.1f}% of total; "
          f"{100*rec_lbs/um_lbs:.1f}% of previously-missing)")

    print()
    print("=" * 70)
    print("Step 4: Merge with existing BLM PLSS and write augmented file")
    print("=" * 70)
    blm_gdf = old_plss.copy()
    blm_gdf["source"] = "blm"
    if "comtrs" not in blm_gdf.columns:
        blm_gdf["comtrs"] = ""
    blm_gdf = blm_gdf[["section_key", "comtrs", "geometry", "source"]]
    if blm_gdf.crs is None:
        blm_gdf = blm_gdf.set_crs(CRS_ALBERS)
    elif blm_gdf.crs.to_string() != CRS_ALBERS:
        blm_gdf = blm_gdf.to_crs(CRS_ALBERS)

    combined = pd.concat([blm_gdf, synth_gdf], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=CRS_ALBERS)

    if NEW_PLSS.exists():
        NEW_PLSS.unlink()
    combined.to_file(NEW_PLSS, driver="GPKG")

    print(f"  Wrote {NEW_PLSS} ({NEW_PLSS.stat().st_size / 1e6:.1f} MB)")
    print(f"    BLM sections:       {(combined['source']=='blm').sum():,}")
    print(f"    Synthetic sections: {(combined['source']=='synthetic').sum():,}")
    print(f"    Total:              {len(combined):,}")

    new_secs = set(combined["section_key"])
    new_matched = pur_secs & new_secs
    new_unmatched = pur_secs - new_secs
    new_um_lbs = agg[agg["section_key"].isin(new_unmatched)]["lbs_ai"].sum()
    print()
    print(f"  PUR coverage: {len(new_matched):,} / {len(pur_secs):,} sections matched")
    print(f"    {len(new_unmatched):,} still unmatched  "
          f"({new_um_lbs:,.0f} lbs = {100*new_um_lbs/total_lbs:.1f}% of total)")
    print()
    print("  Original spatial/data/plss_ca.gpkg is UNCHANGED.")


if __name__ == "__main__":
    main()
