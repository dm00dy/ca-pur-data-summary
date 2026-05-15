#!/usr/bin/env python3
"""
Exposure Engine
===============
Given a CSV of target locations and survey time windows, produces pesticide
exposure metrics at concentric buffer distances using area-weighted spatial
joins to PUR application records.

Input CSV columns (required):
    location_id, latitude, longitude, survey_start_date, survey_end_date

Output (outputs/exposure.csv by default):
    location_id, survey_start, survey_end, chemical_class, buffer_m,
    lbs_ai, acres_treated, tox_units_avian, tox_units_aquatic,
    n_sections_intersected, n_applications, lag_window_days

Also writes a wide per-location summary (outputs/exposure_wide.csv) suitable
for use as a covariate table in mixed-effects models.

Usage:
    python exposure_engine.py --locations input_locations.csv [options]

Options:
    --output PATH          Output CSV (default: outputs/exposure.csv)
    --buffers 500 1000     Buffer distances in meters (default: 500 1000 2000 5000)
    --lags 30 60 90        Lag windows in days before survey_start (default: 30 60 90)
    --no-crop-attr         Skip crop attribution weighting (use raw section area)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point
from shapely.wkt import dumps as wkt_dumps

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("outputs")
DB_PATH = Path("data/spatial.duckdb")
PUR_PARQUET = OUTPUT_DIR / "pur_sections.parquet"
ATTR_PARQUET = OUTPUT_DIR / "crop_attribution.parquet"

BUFFER_DISTANCES_M = [500, 1_000, 2_000, 5_000]
LAG_WINDOWS_DAYS = [30, 60, 90]
CRS_ALBERS = "EPSG:3310"

# Transformer from WGS84 lat/lon → California Albers (meters)
_T_TO_ALBERS = Transformer.from_crs("EPSG:4326", CRS_ALBERS, always_xy=True)


# ---------------------------------------------------------------------------
# LOCATION LOADING
# ---------------------------------------------------------------------------

def load_locations(path: Path) -> pd.DataFrame:
    """Load and validate the input locations CSV."""
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"location_id", "latitude", "longitude", "survey_start_date", "survey_end_date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Input CSV missing columns: {missing}")

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    bad = df[df["latitude"].isna() | df["longitude"].isna()]
    if len(bad):
        print(f"WARNING: {len(bad)} locations with invalid coordinates — dropped")
        df = df.dropna(subset=["latitude", "longitude"])

    # Project to California Albers for buffer computation
    x, y = _T_TO_ALBERS.transform(df["longitude"].values, df["latitude"].values)
    df["x_albers"] = x
    df["y_albers"] = y

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# ATTRIBUTION LOOKUP
# ---------------------------------------------------------------------------

def load_attribution(use_attr: bool) -> dict[tuple, float]:
    """Load (year, section_key, site_code) → attribution_fraction mapping."""
    if not use_attr or not ATTR_PARQUET.exists():
        return {}
    attr = pd.read_parquet(ATTR_PARQUET, columns=["year", "section_key", "site_code", "attribution_fraction"])
    return {
        (int(r.year), str(r.section_key), int(r.site_code) if pd.notna(r.site_code) else -1):
            float(r.attribution_fraction)
        for r in attr.itertuples()
    }


# ---------------------------------------------------------------------------
# SPATIAL EXPOSURE QUERY
# ---------------------------------------------------------------------------

def query_buffer(
    con: duckdb.DuckDBPyConnection,
    buffer_wkt: str,
    date_start: str,
    date_end: str,
) -> pd.DataFrame:
    """Spatial join: PUR records whose PLSS section intersects buffer, within date window.

    Returns DataFrame with one row per intersecting application record, including
    area_fraction (intersection area / section area) for weighting.
    """
    sql = f"""
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
    """
    try:
        return con.execute(sql).df()
    except Exception as exc:
        print(f"    WARNING: spatial query failed ({exc})")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# EXPOSURE AGGREGATION
# ---------------------------------------------------------------------------

def aggregate_exposure(
    records: pd.DataFrame,
    attr: dict[tuple, float],
    buffer_m: int,
    lag_days: int,
) -> dict[str, object]:
    """Aggregate records into exposure metrics per chemical class."""
    if records.empty:
        return {}

    # Apply area fraction and attribution fraction
    records = records.copy()
    records["area_frac"] = records["area_fraction"].clip(0, 1)

    if attr:
        def _get_attr(row) -> float:
            key = (int(row.year), str(row.section_key),
                   int(row.site_code) if pd.notna(row.site_code) else -1)
            return attr.get(key, 1.0)
        records["attr_frac"] = records.apply(_get_attr, axis=1)
    else:
        records["attr_frac"] = 1.0

    records["weight"] = records["area_frac"] * records["attr_frac"]
    records["lbs_w"] = records["lbs_ai"] * records["weight"]
    records["acres_w"] = records["acres_treated"] * records["weight"]

    # Toxicity units: weighted lbs / LD50 (avian) or LC50 (aquatic)
    # LD50 in mg/kg, LC50 in μg/L — units are internally consistent for ranking
    records["tox_avian"] = records.apply(
        lambda r: r["lbs_w"] / r["avian_ld50"] if pd.notna(r["avian_ld50"]) and r["avian_ld50"] > 0 else 0.0,
        axis=1,
    )
    records["tox_aquatic"] = records.apply(
        lambda r: r["lbs_w"] / r["aquatic_lc50"] if pd.notna(r["aquatic_lc50"]) and r["aquatic_lc50"] > 0 else 0.0,
        axis=1,
    )

    rows = []
    for cls, grp in records.groupby("chem_class"):
        rows.append({
            "chemical_class": cls,
            "buffer_m": buffer_m,
            "lag_window_days": lag_days,
            "lbs_ai": round(float(grp["lbs_w"].sum()), 4),
            "acres_treated": round(float(grp["acres_w"].sum()), 4),
            "tox_units_avian": round(float(grp["tox_avian"].sum()), 6),
            "tox_units_aquatic": round(float(grp["tox_aquatic"].sum()), 6),
            "n_sections_intersected": int(grp["section_key"].nunique()),
            "n_applications": int(len(grp)),
        })
    return rows


# ---------------------------------------------------------------------------
# FALLBACK: PARQUET-BASED TABULAR JOIN (no DuckDB / no PLSS geometry)
# ---------------------------------------------------------------------------

def _tabular_fallback(
    location: pd.Series,
    pur: pd.DataFrame,
    attr: dict,
    buffers: list[int],
    lags: list[int],
) -> list[dict]:
    """Non-spatial fallback using county_cd matching.

    Matches PUR records in the same county as the location and within lag
    window. No spatial join — area weighting is set to 1.0 (conservative).
    Reports exposure for all county records, flagged with fallback=True.
    """
    # Map lat/lon → California county FIPS (rough box method for SJV counties)
    # This is intentionally coarse; real spatial join is the preferred path.
    lat, lon = float(location["latitude"]), float(location["longitude"])
    county_guess = _latlon_to_county_cd(lat, lon)
    if county_guess is None:
        return []

    rows: list[dict] = []
    for lag in lags:
        from datetime import date, timedelta
        end_dt = pd.to_datetime(location["survey_start_date"]).date()
        start_dt = end_dt - timedelta(days=lag)
        pur_sub = pur[
            (pur["county_cd"] == county_guess) &
            (pd.to_datetime(pur["applic_dt"], errors="coerce").dt.date >= start_dt) &
            (pd.to_datetime(pur["applic_dt"], errors="coerce").dt.date <= end_dt)
        ].copy()
        pur_sub["area_fraction"] = 1.0

        for buf in buffers:
            agg = aggregate_exposure(pur_sub, attr, buf, lag)
            for r in agg:
                r["location_id"] = location["location_id"]
                r["survey_start"] = location["survey_start_date"]
                r["survey_end"] = location["survey_end_date"]
                r["spatial_join"] = "county_fallback"
                rows.append(r)
    return rows


def _latlon_to_county_cd(lat: float, lon: float) -> str | None:
    """Very rough lat/lon → PUR 2-digit county code for common CA ag counties."""
    # Covers the main SJV counties; add more as needed
    COUNTY_BOXES = [
        ("10", 36.0, 38.0, -121.5, -119.5),   # Fresno
        ("15", 35.5, 36.7, -120.0, -118.7),   # Kern
        ("16", 35.9, 36.4, -120.2, -119.4),   # Kings
        ("20", 36.9, 37.5, -120.5, -119.5),   # Madera
        ("24", 37.0, 37.8, -121.1, -120.0),   # Merced
        ("39", 37.1, 38.4, -122.0, -120.5),   # San Joaquin
        ("50", 37.4, 38.0, -121.5, -120.5),   # Stanislaus
        ("54", 35.7, 36.9, -119.5, -118.5),   # Tulare
    ]
    for cd, lat_min, lat_max, lon_min, lon_max in COUNTY_BOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return cd
    return None


# ---------------------------------------------------------------------------
# PER-LOCATION PROCESSING
# ---------------------------------------------------------------------------

def process_location(
    location: pd.Series,
    con: duckdb.DuckDBPyConnection | None,
    pur_tabular: pd.DataFrame | None,
    attr: dict,
    buffers: list[int],
    lags: list[int],
) -> list[dict]:
    """Compute exposure metrics for a single location across all buffer × lag combos."""
    x, y = float(location["x_albers"]), float(location["y_albers"])
    loc_id = location["location_id"]

    rows: list[dict] = []
    for lag in lags:
        from datetime import date, timedelta
        try:
            end_dt = pd.to_datetime(location["survey_start_date"]).date()
        except Exception:
            print(f"  {loc_id}: invalid survey_start_date — skipping")
            return []
        start_dt = end_dt - timedelta(days=lag)

        for buf in buffers:
            if con is not None:
                # Spatial join path (preferred)
                point = Point(x, y)
                buffer_geom = point.buffer(buf)
                buffer_wkt = wkt_dumps(buffer_geom, rounding_precision=3)
                records = query_buffer(con, buffer_wkt, start_dt.isoformat(), end_dt.isoformat())
                spatial_join = "plss_spatial"
            elif pur_tabular is not None:
                # County-level tabular fallback
                records = pd.DataFrame()  # handled below
                spatial_join = "county_fallback"
            else:
                continue

            if records.empty and spatial_join == "county_fallback" and pur_tabular is not None:
                fallback_rows = _tabular_fallback(location, pur_tabular, attr, [buf], [lag])
                rows.extend(fallback_rows)
                continue

            agg_rows = aggregate_exposure(records, attr, buf, lag)
            for r in agg_rows:
                r["location_id"] = loc_id
                r["survey_start"] = location["survey_start_date"]
                r["survey_end"] = location["survey_end_date"]
                r["spatial_join"] = spatial_join
            rows.extend(agg_rows)

    return rows


# ---------------------------------------------------------------------------
# WIDE TABLE PIVOT
# ---------------------------------------------------------------------------

def pivot_wide(long_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot long exposure table to one row per location × survey window.

    Column format: {class}_{metric}_{buffer}m_{lag}d
    """
    if long_df.empty:
        return pd.DataFrame()

    long_df = long_df.copy()
    long_df["col_stem"] = (
        long_df["chemical_class"].str.replace(" ", "_")
        + "_" + long_df["buffer_m"].astype(str) + "m"
        + "_" + long_df["lag_window_days"].astype(str) + "d"
    )

    metrics = ["lbs_ai", "tox_units_avian", "tox_units_aquatic"]
    wide_frames = []
    for metric in metrics:
        piv = long_df.pivot_table(
            index=["location_id", "survey_start", "survey_end"],
            columns="col_stem",
            values=metric,
            aggfunc="sum",
        ).fillna(0)
        piv.columns = [f"{c}_{metric}" for c in piv.columns]
        wide_frames.append(piv)

    return pd.concat(wide_frames, axis=1).reset_index()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Compute pesticide exposure for target locations")
    parser.add_argument("--locations", required=True, type=Path,
                        help="Input CSV: location_id, latitude, longitude, survey_start_date, survey_end_date")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "exposure.csv")
    parser.add_argument("--buffers", nargs="+", type=int, default=BUFFER_DISTANCES_M)
    parser.add_argument("--lags", nargs="+", type=int, default=LAG_WINDOWS_DAYS)
    parser.add_argument("--no-crop-attr", action="store_true",
                        help="Skip crop attribution (raw section-area weighting)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    locations = load_locations(args.locations)
    print(f"Locations: {len(locations)} sites")

    attr = load_attribution(not args.no_crop_attr)
    if attr:
        print(f"Crop attribution: {len(attr):,} (year, section, site) records loaded")
    else:
        print("Crop attribution: not used (raw section area weighting)")

    # Try DuckDB spatial path first
    con: duckdb.DuckDBPyConnection | None = None
    pur_tabular: pd.DataFrame | None = None

    if DB_PATH.exists():
        try:
            con = duckdb.connect(str(DB_PATH), read_only=True)
            con.execute("LOAD spatial;")
            n_records = con.execute("SELECT COUNT(*) FROM pur_records").fetchone()[0]
            n_sections = con.execute("SELECT COUNT(*) FROM plss_sections").fetchone()[0]
            print(f"DuckDB: {n_records:,} PUR records, {n_sections:,} PLSS sections")
            if n_records == 0 or n_sections == 0:
                print("WARNING: DuckDB empty — falling back to tabular join")
                con.close()
                con = None
        except Exception as exc:
            print(f"DuckDB unavailable ({exc}) — falling back to tabular join")
            con = None

    if con is None:
        if PUR_PARQUET.exists():
            print(f"Loading PUR Parquet for tabular fallback ...")
            pur_tabular = pd.read_parquet(PUR_PARQUET)
            print(f"  {len(pur_tabular):,} records")
        else:
            print(f"ERROR: No DuckDB and no {PUR_PARQUET}. Run pur_loader.py first.")
            sys.exit(1)

    all_rows: list[dict] = []
    for i, (_, loc) in enumerate(locations.iterrows(), 1):
        print(f"  [{i}/{len(locations)}] {loc['location_id']} ...", end=" ", flush=True)
        rows = process_location(loc, con, pur_tabular, attr, args.buffers, args.lags)
        all_rows.extend(rows)
        print(f"{len(rows)} rows")

    if con is not None:
        con.close()

    if not all_rows:
        print("No exposure records generated.")
        sys.exit(0)

    long_df = pd.DataFrame(all_rows)
    long_df.to_csv(args.output, index=False)
    print(f"\n{len(long_df):,} rows → {args.output}")

    wide_df = pivot_wide(long_df)
    wide_path = args.output.parent / (args.output.stem + "_wide.csv")
    wide_df.to_csv(wide_path, index=False)
    print(f"{len(wide_df)} locations × {len(wide_df.columns)} columns → {wide_path}")


if __name__ == "__main__":
    main()
