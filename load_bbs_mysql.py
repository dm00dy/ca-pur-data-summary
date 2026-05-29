#!/usr/bin/env python3
"""
Load BBS (Breeding Bird Survey) data into the pur_data MySQL database.

Creates three tables:
  bbs_route    — 44 California BBS route metadata
  bbs_count    — aerial insectivore counts by route × year × species
  bbs_exposure — pesticide exposure by route × year × class × buffer × lag

Source CSVs (spatial/outputs/):
  bbs_locations.csv          → bbs_route
  level1_model_input.csv     → bbs_count  (cnt_* columns unpivoted)
  bbs_exposure_yearly.csv    → bbs_exposure

Credentials via environment variables (same defaults as load_pur_mysql.py):
    PUR_DB_HOST  (default: localhost)
    PUR_DB_PORT  (default: 3366)
    PUR_DB_USER  (default: root)
    PUR_DB_PASS  (default: password)
    PUR_DB_NAME  (default: pur_data)

Usage:
    source .venv/bin/activate
    python load_bbs_mysql.py
    python load_bbs_mysql.py --bbs-dir spatial/outputs
    python load_bbs_mysql.py --recreate   # drop + recreate BBS tables
    python load_bbs_mysql.py --verify-only
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import mysql.connector
from mysql.connector import Error as MySQLError
import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────

BBS_DIR    = Path("spatial/outputs")
SCHEMA_SQL = Path("schema_bbs.sql")

DB_CFG = {
    "host":     os.environ.get("PUR_DB_HOST", "localhost"),
    "port":     int(os.environ.get("PUR_DB_PORT", 3366)),
    "user":     os.environ.get("PUR_DB_USER", "root"),
    "password": os.environ.get("PUR_DB_PASS", "password"),
    "database": os.environ.get("PUR_DB_NAME", "pur_data"),
}

# AOU code → (species_code stem, species_name)
# Derived from bbs_counts.py AERIAL_INSECTIVORES dict.
# species_code = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
SPECIES_MAP: dict[int, tuple[str, str]] = {
    4180: ("common_poorwill",              "Common Poorwill"),
    4200: ("common_nighthawk",             "Common Nighthawk"),
    4210: ("lesser_nighthawk",             "Lesser Nighthawk"),
    4220: ("black_swift",                  "Black Swift"),
    4230: ("chimney_swift",                "Chimney Swift"),
    4240: ("vaux_s_swift",                 "Vaux's Swift"),
    4250: ("white_throated_swift",         "White-throated Swift"),
    6110: ("purple_martin",               "Purple Martin"),
    6120: ("cliff_swallow",               "Cliff Swallow"),
    6130: ("barn_swallow",                "Barn Swallow"),
    6140: ("tree_swallow",                "Tree Swallow"),
    6150: ("violet_green_swallow",        "Violet-green Swallow"),
    6160: ("bank_swallow",                "Bank Swallow"),
    6170: ("northern_rough_winged_swallow", "Northern Rough-winged Swallow"),
    4440: ("eastern_kingbird",            "Eastern Kingbird"),
    4470: ("western_kingbird",            "Western Kingbird"),
    4480: ("cassin_s_kingbird",           "Cassin's Kingbird"),
    4570: ("say_s_phoebe",                "Say's Phoebe"),
    4580: ("black_phoebe",               "Black Phoebe"),
    4590: ("olive_sided_flycatcher",      "Olive-sided Flycatcher"),
    4620: ("western_wood_pewee",          "Western Wood-Pewee"),
}

# code → name for the cnt_* column stems (inverse of SPECIES_MAP)
_STEM_TO_AOU: dict[str, int] = {stem: aou for aou, (stem, _) in SPECIES_MAP.items()}

# Group-total columns (no AOU code)
GROUP_TOTALS: dict[str, str] = {
    "swallows_total":            "Swallows (total)",
    "swifts_total":              "Swifts (total)",
    "nightjars_total":           "Nightjars (total)",
    "flycatchers_total":         "Flycatchers (total)",
    "aerial_insectivores_total": "Aerial Insectivores (total)",
}


# ── DB helpers ────────────────────────────────────────────────────────────────

def connect() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**DB_CFG)


def apply_schema(conn, recreate: bool) -> None:
    cur = conn.cursor()
    if recreate:
        for tbl in ("bbs_exposure", "bbs_count", "bbs_route"):
            cur.execute(f"DROP TABLE IF EXISTS `{tbl}`")
            print(f"  Dropped {tbl}")
        conn.commit()

    sql = SCHEMA_SQL.read_text()
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("--"):
            cur.execute(stmt)
    conn.commit()
    cur.close()
    print("Schema applied.")


# ── Route loader ──────────────────────────────────────────────────────────────

def load_routes(conn, bbs_dir: Path) -> None:
    path = bbs_dir / "bbs_locations.csv"
    df = pd.read_csv(path)

    rows = []
    for _, r in df.iterrows():
        route_id = r["location_id"]
        route_no = int(route_id.split("_")[2])  # BBS_CA_054_... → 54
        rows.append((
            route_id,
            float(r["latitude"]),
            float(r["longitude"]),
            route_no,
            r["RouteName"],
            int(r["BCR"]),
            str(r["survey_start_date"]),
            str(r["survey_end_date"]),
            int(r["n_pur_5km"]),
            float(r["lbs_ai_5km"]),
        ))

    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO bbs_route
           (route_id, latitude, longitude, route_no, route_name, bcr,
            survey_start_date, survey_end_date, n_pur_5km, lbs_ai_5km)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
             latitude=VALUES(latitude), longitude=VALUES(longitude),
             route_name=VALUES(route_name), bcr=VALUES(bcr),
             n_pur_5km=VALUES(n_pur_5km), lbs_ai_5km=VALUES(lbs_ai_5km)
        """,
        rows,
    )
    conn.commit()
    cur.close()
    print(f"  bbs_route: {len(rows)} rows")


# ── Count loader ──────────────────────────────────────────────────────────────

def _parse_route_year(location_id: str) -> tuple[str, int]:
    """'BBS_CA_054_ORANGE_COVE_2015' → ('BBS_CA_054_ORANGE_COVE', 2015)"""
    year = int(location_id[-4:])
    route_id = location_id[:-5]   # strip _YYYY
    return route_id, year


def load_counts(conn, bbs_dir: Path) -> None:
    path = bbs_dir / "level1_model_input.csv"
    df = pd.read_csv(path)

    cnt_cols = [c for c in df.columns if c.startswith("cnt_")]
    rows: list[tuple] = []

    for _, r in df.iterrows():
        route_id, year = _parse_route_year(r["location_id"])

        for col in cnt_cols:
            stem = col[4:]   # strip "cnt_"
            val = r[col]
            count_total = None if pd.isna(val) else int(val)

            if stem in GROUP_TOTALS:
                aou_code     = None
                species_name = GROUP_TOTALS[stem]
                is_group     = 1
            else:
                aou_code     = _STEM_TO_AOU.get(stem)
                species_name = (SPECIES_MAP[aou_code][1]
                                if aou_code is not None
                                else stem.replace("_", " ").title())
                is_group     = 0

            rows.append((
                route_id, year, stem, species_name,
                aou_code, is_group, count_total,
            ))

    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO bbs_count
           (route_id, year, species_code, species_name,
            aou_code, is_group_total, count_total)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
             count_total=VALUES(count_total)
        """,
        rows,
    )
    conn.commit()
    cur.close()
    print(f"  bbs_count: {len(rows)} rows "
          f"({df['location_id'].nunique()} route-years, "
          f"{len(cnt_cols)} species/groups each)")


# ── Exposure loader ───────────────────────────────────────────────────────────

def load_exposure(conn, bbs_dir: Path) -> None:
    path = bbs_dir / "bbs_exposure_yearly.csv"
    df = pd.read_csv(path)

    rows: list[tuple] = []
    for _, r in df.iterrows():
        route_id, year = _parse_route_year(r["location_id"])

        def _f(col: str):
            v = r[col]
            return None if pd.isna(v) else float(v)

        def _i(col: str):
            v = r[col]
            return None if pd.isna(v) else int(v)

        rows.append((
            route_id,
            year,
            str(r["survey_start"]),
            str(r["survey_end"]),
            r["chemical_class"],
            int(r["buffer_m"]),
            int(r["lag_window_days"]),
            _f("lbs_ai"),
            _f("acres_treated"),
            _f("tox_units_avian"),
            _f("tox_units_aquatic"),
            _i("n_sections_intersected"),
            _i("n_applications"),
            r["spatial_join"] if pd.notna(r["spatial_join"]) else None,
        ))

    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO bbs_exposure
           (route_id, year, survey_start, survey_end, chemical_class,
            buffer_m, lag_window_days, lbs_ai, acres_treated,
            tox_units_avian, tox_units_aquatic,
            n_sections_intersected, n_applications, spatial_join)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
             lbs_ai=VALUES(lbs_ai),
             acres_treated=VALUES(acres_treated),
             tox_units_avian=VALUES(tox_units_avian),
             tox_units_aquatic=VALUES(tox_units_aquatic),
             n_sections_intersected=VALUES(n_sections_intersected),
             n_applications=VALUES(n_applications)
        """,
        rows,
    )
    conn.commit()
    cur.close()
    print(f"  bbs_exposure: {len(rows)} rows")


# ── Verification ──────────────────────────────────────────────────────────────

def verify(conn) -> None:
    cur = conn.cursor()
    for tbl in ("bbs_route", "bbs_count", "bbs_exposure"):
        cur.execute(f"SELECT COUNT(*) FROM `{tbl}`")
        n = cur.fetchone()[0]
        print(f"  {tbl}: {n:,} rows")
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Load BBS data into pur_data MySQL")
    ap.add_argument("--bbs-dir",     default=str(BBS_DIR),
                    help="Directory containing BBS output CSVs")
    ap.add_argument("--recreate",    action="store_true",
                    help="Drop and recreate BBS tables before loading")
    ap.add_argument("--verify-only", action="store_true",
                    help="Print row counts without loading")
    args = ap.parse_args()

    bbs_dir = Path(args.bbs_dir)
    for fname in ("bbs_locations.csv", "level1_model_input.csv",
                  "bbs_exposure_yearly.csv"):
        if not (bbs_dir / fname).exists():
            print(f"ERROR: {bbs_dir / fname} not found", file=sys.stderr)
            sys.exit(1)

    print(f"Connecting to {DB_CFG['host']}:{DB_CFG['port']} ...")
    try:
        conn = connect()
    except MySQLError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verify_only:
        print("\nRow counts:")
        verify(conn)
        conn.close()
        return

    print("\nApplying schema ...")
    apply_schema(conn, recreate=args.recreate)

    print("\nLoading BBS tables ...")
    load_routes(conn, bbs_dir)
    load_counts(conn, bbs_dir)
    load_exposure(conn, bbs_dir)

    print("\nVerification:")
    verify(conn)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
