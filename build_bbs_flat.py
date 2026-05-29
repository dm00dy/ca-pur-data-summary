#!/usr/bin/env python3
"""
Build the bbsFlat denormalized table in the bbs database.

Reads stop_count, weather, route, and species (already loaded by load_bbs_db.py),
then unpivots the 50 stop columns into one row per detection:
    (route × year × species × stop) where stop count > 0

Joins in survey metadata (weather), route metadata (lat/lon, BCR, name),
species names, and state/province/country labels.

Equivalent to the multimap-build-bbs/bbs.sql bbsFlat build, updated for
the 2024 BBS edition and our snake_case schema.

Credentials via environment variables:
    PUR_DB_HOST  (default: localhost)
    PUR_DB_PORT  (default: 3366)
    PUR_DB_USER  (default: root)
    PUR_DB_PASS  (default: password)

Usage:
    source .venv/bin/activate
    python build_bbs_flat.py
    python build_bbs_flat.py --recreate    # drop + recreate bbsFlat
    python build_bbs_flat.py --verify-only
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import mysql.connector
from mysql.connector import Error as MySQLError
import pandas as pd
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK_SIZE = 20_000   # rows read from stop_count per iteration
BATCH_SIZE = 50_000   # rows per executemany call

DB_CFG = {
    "host":     os.environ.get("PUR_DB_HOST", "localhost"),
    "port":     int(os.environ.get("PUR_DB_PORT", 3366)),
    "user":     os.environ.get("PUR_DB_USER", "root"),
    "password": os.environ.get("PUR_DB_PASS", "password"),
    "database": "bbs",
}

# ── Region / country lookups (from multimap-build-bbs/data/RegionCodes.txt) ──

REGION_CODES: dict[tuple[int, int], str] = {
    # Canada
    (124,  4): "Alberta",
    (124, 11): "British Columbia",
    (124, 43): "Northwest Territories",
    (124, 45): "Manitoba",
    (124, 56): "New Brunswick",
    (124, 57): "Newfoundland and Labrador",
    (124, 62): "Nunavut",
    (124, 65): "Nova Scotia",
    (124, 68): "Ontario",
    (124, 75): "Prince Edward Island",
    (124, 76): "Quebec",
    (124, 79): "Saskatchewan",
    (124, 93): "Yukon",
    # Mexico
    (484,  1): "Aguascalientes",
    (484,  2): "Baja California",
    (484,  3): "Baja California Sur",
    (484,  4): "Campeche",
    (484,  5): "Chiapas",
    (484,  6): "Chihuahua",
    (484,  7): "Coahuila",
    (484,  8): "Colima",
    (484,  9): "Distrito Federal",
    (484, 10): "Durango",
    (484, 11): "Guanajuato",
    (484, 12): "Guerrero",
    (484, 13): "Hidalgo",
    (484, 14): "Jalisco",
    (484, 15): "Mexico",
    (484, 16): "Michoacan",
    (484, 17): "Morelos",
    (484, 18): "Nayarit",
    (484, 19): "Nuevo Leon",
    (484, 20): "Oaxaca",
    (484, 21): "Puebla",
    (484, 22): "Queretaro",
    (484, 23): "Quintana Roo",
    (484, 24): "San Luis Potosi",
    (484, 25): "Sinaloa",
    (484, 26): "Sonora",
    (484, 27): "Tabasco",
    (484, 28): "Tamaulipas",
    (484, 29): "Tlaxcala",
    (484, 30): "Veracruz",
    (484, 31): "Yucatan",
    (484, 32): "Zacatecas",
    (484, 48): "Mexico Country",
    # United States
    (840,  2): "ALABAMA",
    (840,  3): "ALASKA",
    (840,  6): "ARIZONA",
    (840,  7): "ARKANSAS",
    (840, 14): "CALIFORNIA",
    (840, 17): "COLORADO",
    (840, 18): "CONNECTICUT",
    (840, 21): "DELAWARE",
    (840, 22): "District of Columbia",
    (840, 25): "FLORIDA",
    (840, 27): "GEORGIA",
    (840, 33): "IDAHO",
    (840, 34): "ILLINOIS",
    (840, 35): "INDIANA",
    (840, 36): "IOWA",
    (840, 38): "KANSAS",
    (840, 39): "KENTUCKY",
    (840, 42): "LOUISIANA",
    (840, 44): "MAINE",
    (840, 46): "MARYLAND",
    (840, 47): "MASSACHUSETTS",
    (840, 49): "MICHIGAN",
    (840, 50): "MINNESOTA",
    (840, 51): "MISSISSIPPI",
    (840, 52): "MISSOURI",
    (840, 53): "MONTANA",
    (840, 54): "NEBRASKA",
    (840, 55): "NEVADA",
    (840, 58): "NEW HAMPSHIRE",
    (840, 59): "NEW JERSEY",
    (840, 60): "NEW MEXICO",
    (840, 61): "NEW YORK",
    (840, 63): "NORTH CAROLINA",
    (840, 64): "NORTH DAKOTA",
    (840, 66): "OHIO",
    (840, 67): "OKLAHOMA",
    (840, 69): "OREGON",
    (840, 72): "PENNSYLVANIA",
    (840, 74): "PUERTO RICO",
    (840, 77): "RHODE ISLAND",
    (840, 80): "SOUTH CAROLINA",
    (840, 81): "SOUTH DAKOTA",
    (840, 82): "TENNESSEE",
    (840, 83): "TEXAS",
    (840, 85): "UTAH",
    (840, 87): "VERMONT",
    (840, 88): "VIRGINIA",
    (840, 89): "WASHINGTON",
    (840, 90): "WEST VIRGINIA",
    (840, 91): "WISCONSIN",
    (840, 92): "WYOMING",
}

COUNTRY: dict[int, str] = {
    124: "Canada",
    484: "Mexico",
    840: "United States",
}

# ── Schema ────────────────────────────────────────────────────────────────────

BBSFLAT_DDL = """
CREATE TABLE IF NOT EXISTS bbsFlat (
    route_data_id      INT UNSIGNED,
    country_num        SMALLINT UNSIGNED,
    state_num          SMALLINT UNSIGNED,
    route              SMALLINT UNSIGNED,
    rpid               SMALLINT UNSIGNED,
    year               SMALLINT UNSIGNED,
    month              TINYINT UNSIGNED,
    day                TINYINT UNSIGNED,
    obs_n              INT UNSIGNED,
    total_spp          SMALLINT UNSIGNED,
    start_temp         SMALLINT,
    end_temp           SMALLINT,
    temp_scale         CHAR(1),
    start_wind         TINYINT,
    end_wind           TINYINT,
    start_sky          TINYINT,
    end_sky            TINYINT,
    start_time         SMALLINT UNSIGNED,
    end_time           SMALLINT UNSIGNED,
    assistant          TINYINT(1),
    quality_current_id TINYINT UNSIGNED,
    run_type           TINYINT UNSIGNED,
    latitude           DOUBLE,
    longitude          DOUBLE,
    stratum            SMALLINT UNSIGNED,
    bcr                TINYINT UNSIGNED,
    route_name         VARCHAR(100),
    aou                SMALLINT UNSIGNED,
    seq                SMALLINT UNSIGNED,
    english_name       VARCHAR(120),
    french_name        VARCHAR(120),
    scientific_name    VARCHAR(130),
    stop_num           TINYINT UNSIGNED,
    stop               VARCHAR(8),
    obs_count          SMALLINT UNSIGNED,
    locality           VARCHAR(30),
    survey_area_id     VARCHAR(40),
    observation_date   DATE,
    state_province     VARCHAR(64),
    country_name       VARCHAR(64),
    PRIMARY KEY (route_data_id, aou, stop_num),
    INDEX idx_flat_year     (year),
    INDEX idx_flat_aou      (aou),
    INDEX idx_flat_route    (state_num, route),
    INDEX idx_flat_locality (locality)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

INSERT_SQL = """
INSERT IGNORE INTO bbsFlat
  (route_data_id, country_num, state_num, route, rpid, year,
   month, day, obs_n, total_spp,
   start_temp, end_temp, temp_scale, start_wind, end_wind, start_sky, end_sky,
   start_time, end_time, assistant, quality_current_id, run_type,
   latitude, longitude, stratum, bcr, route_name,
   aou, seq, english_name, french_name, scientific_name,
   stop_num, stop, obs_count,
   locality, survey_area_id, observation_date,
   state_province, country_name)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""

OUT_COLS = [
    "route_data_id", "country_num", "state_num", "route", "rpid", "year",
    "month", "day", "obs_n", "total_spp",
    "start_temp", "end_temp", "temp_scale", "start_wind", "end_wind", "start_sky", "end_sky",
    "start_time", "end_time", "assistant", "quality_current_id", "run_type",
    "latitude", "longitude", "stratum", "bcr", "route_name",
    "aou", "seq", "english_name", "french_name", "scientific_name",
    "stop_num", "stop", "obs_count",
    "locality", "survey_area_id", "observation_date",
    "state_province", "country_name",
]

STOP_COLS = [f"stop{i}" for i in range(1, 51)]
ID_COLS   = ["route_data_id", "country_num", "state_num", "route", "rpid", "year", "aou"]

# ── DB helpers ────────────────────────────────────────────────────────────────

def connect(buffered: bool = True) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**DB_CFG)


def apply_schema(conn, recreate: bool) -> None:
    cur = conn.cursor()
    if recreate:
        cur.execute("DROP TABLE IF EXISTS bbsFlat")
        conn.commit()
        print("  Dropped bbsFlat")
    cur.execute(BBSFLAT_DDL)
    conn.commit()
    cur.close()
    print("Schema applied.")


def _bulk_insert(cur, rows: list) -> None:
    for i in range(0, len(rows), BATCH_SIZE):
        cur.executemany(INSERT_SQL, rows[i : i + BATCH_SIZE])


# ── Reference loaders ─────────────────────────────────────────────────────────

def load_weather_df(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute("""
        SELECT route_data_id, month, day, obs_n, total_spp,
               start_temp, end_temp, temp_scale, start_wind, end_wind,
               start_sky, end_sky, start_time, end_time,
               assistant, quality_current_id, run_type
        FROM weather
    """)
    cols = ["route_data_id", "month", "day", "obs_n", "total_spp",
            "start_temp", "end_temp", "temp_scale", "start_wind", "end_wind",
            "start_sky", "end_sky", "start_time", "end_time",
            "assistant", "quality_current_id", "run_type"]
    df = pd.DataFrame(cur.fetchall(), columns=cols)
    cur.close()
    print(f"  weather: {len(df):,} rows")
    return df


def load_route_df(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute("""
        SELECT country_num, state_num, route,
               latitude, longitude, stratum, bcr, route_name
        FROM route
    """)
    cols = ["country_num", "state_num", "route",
            "latitude", "longitude", "stratum", "bcr", "route_name"]
    df = pd.DataFrame(cur.fetchall(), columns=cols)
    cur.close()
    print(f"  route: {len(df):,} rows")
    return df


def load_species_df(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute("SELECT aou, seq, english_name, french_name, genus, species_epithet FROM species")
    df = pd.DataFrame(cur.fetchall(),
                      columns=["aou", "seq", "english_name", "french_name", "genus", "species_epithet"])
    df["scientific_name"] = (df["genus"].fillna("") + " " + df["species_epithet"].fillna("")).str.strip()
    df = df.drop(columns=["genus", "species_epithet"])
    cur.close()
    print(f"  species: {len(df):,} rows")
    return df


# ── Flat builder ──────────────────────────────────────────────────────────────

def _nan_to_none(df: pd.DataFrame) -> list:
    """Convert DataFrame to list of tuples, replacing NaN/NaT with None."""
    out = []
    for row in df.itertuples(index=False, name=None):
        out.append(tuple(
            None if (v is pd.NaT or (isinstance(v, float) and np.isnan(v))) else v
            for v in row
        ))
    return out


def build_flat(conn_read, conn_write, wx_df, rt_df, sp_df) -> int:
    total  = 0
    cur_r  = conn_read.cursor(buffered=False)
    cur_w  = conn_write.cursor()

    cur_r.execute(f"SELECT {', '.join(ID_COLS + STOP_COLS)} FROM stop_count")

    chunk_n = 0
    t_start = time.time()

    while True:
        rows = cur_r.fetchmany(CHUNK_SIZE)
        if not rows:
            break
        chunk_n += 1

        sc = pd.DataFrame(rows, columns=ID_COLS + STOP_COLS)

        # Unpivot Stop1–Stop50 → long format, keep only detections
        melted = sc.melt(id_vars=ID_COLS, value_vars=STOP_COLS,
                         var_name="stop", value_name="obs_count")
        melted = melted[melted["obs_count"] > 0].copy()
        if melted.empty:
            continue

        melted["stop_num"] = melted["stop"].str[4:].astype(int)

        # Join reference tables
        merged = (melted
                  .merge(wx_df, on="route_data_id",                         how="inner")
                  .merge(rt_df, on=["country_num", "state_num", "route"],   how="inner")
                  .merge(sp_df, on="aou",                                   how="inner"))
        if merged.empty:
            continue

        # Derived columns
        merged["locality"] = (
            "Rgn" + merged["state_num"].astype(str) +
            "Rte" + merged["route"].apply(lambda x: f"{x:03d}")
        )
        merged["survey_area_id"] = (
            merged["locality"] + "Stop" + merged["stop_num"].astype(str)
        )

        # observation_date: None when month or day is missing
        has_date = merged["month"].notna() & merged["day"].notna()
        merged["observation_date"] = None
        if has_date.any():
            valid = merged.loc[has_date]
            m_str = valid["month"].astype(int).astype(str).str.zfill(2)
            d_str = valid["day"].astype(int).astype(str).str.zfill(2)
            merged.loc[has_date, "observation_date"] = (
                valid["year"].astype(str) + "-" + m_str + "-" + d_str
            )

        # State/province and country name
        merged["state_province"] = [
            REGION_CODES.get((cn, sn))
            for cn, sn in zip(merged["country_num"], merged["state_num"])
        ]
        merged["country_name"] = merged["country_num"].map(COUNTRY)

        # Build insert rows, converting NaN → None
        insert_rows = _nan_to_none(merged[OUT_COLS])

        _bulk_insert(cur_w, insert_rows)
        conn_write.commit()

        total += len(insert_rows)
        elapsed = time.time() - t_start
        print(f"  chunk {chunk_n:4d}: +{len(insert_rows):>7,}  total {total:>10,}  ({elapsed:.0f}s)")

    cur_r.close()
    cur_w.close()
    return total


# ── Verification ──────────────────────────────────────────────────────────────

def verify(conn) -> None:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM bbsFlat")
    n = cur.fetchone()[0]
    print(f"  bbsFlat: {n:,} rows")
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Build bbsFlat from stop_count + reference tables")
    ap.add_argument("--recreate",    action="store_true",
                    help="Drop and recreate bbsFlat before building")
    ap.add_argument("--verify-only", action="store_true",
                    help="Print row count without building")
    args = ap.parse_args()

    print(f"Connecting to {DB_CFG['host']}:{DB_CFG['port']} ...")
    try:
        conn_read  = connect()
        conn_write = connect()
    except MySQLError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verify_only:
        print("\nRow count:")
        verify(conn_read)
        conn_read.close()
        conn_write.close()
        return

    print("\nApplying schema ...")
    apply_schema(conn_write, args.recreate)

    print("\nLoading reference tables into memory ...")
    wx_df = load_weather_df(conn_read)
    rt_df = load_route_df(conn_read)
    sp_df = load_species_df(conn_read)

    print("\nBuilding bbsFlat (stop_count unpivot + joins) ...")
    t0 = time.time()
    n  = build_flat(conn_read, conn_write, wx_df, rt_df, sp_df)
    print(f"  total: {n:,} rows  ({time.time()-t0:.0f}s)")

    print("\nVerification:")
    verify(conn_write)

    conn_read.close()
    conn_write.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
