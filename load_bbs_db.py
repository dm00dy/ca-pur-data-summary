#!/usr/bin/env python3
"""
Load the full USGS BBS 2024 dataset into a MySQL database named 'bbs'.

Tables loaded (in order):
  species      ← SpeciesList.csv
  route        ← Routes.csv
  weather      ← Weather.csv
  vehicle      ← VehicleData.csv
  count        ← States.zip  (63 state/province CSVs)
  stop_count   ← 50-StopData.zip  (Fifty1.csv … Fifty10.csv)
  migrant      ← MigrantNonBreeder.zip/Migrants.csv

Credentials via environment variables:
    PUR_DB_HOST  (default: localhost)
    PUR_DB_PORT  (default: 3366)
    PUR_DB_USER  (default: root)
    PUR_DB_PASS  (default: password)

Usage:
    source .venv/bin/activate
    python load_bbs_db.py
    python load_bbs_db.py --data-dir spatial/data/bbs
    python load_bbs_db.py --recreate        # drop + recreate all tables
    python load_bbs_db.py --skip-counts     # load everything except count/stop_count
    python load_bbs_db.py --verify-only     # print row counts
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
import zipfile
from pathlib import Path

import mysql.connector
from mysql.connector import Error as MySQLError
import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────

DATA_DIR   = Path("spatial/data/bbs")
SCHEMA_SQL = Path("schema_bbs_db.sql")
BATCH_SIZE = 50_000
ENCODING   = "latin-1"

DB_CFG = {
    "host":     os.environ.get("PUR_DB_HOST", "localhost"),
    "port":     int(os.environ.get("PUR_DB_PORT", 3366)),
    "user":     os.environ.get("PUR_DB_USER", "root"),
    "password": os.environ.get("PUR_DB_PASS", "password"),
    "database": "bbs",
}

# Stop columns shared by stop_count and migrant tables
STOP_COLS  = [f"stop{i}"  for i in range(1, 51)]
CAR_COLS   = [f"car{i}"   for i in range(1, 51)]
NOISE_COLS = [f"noise{i}" for i in range(1, 51)]


# ── DB helpers ────────────────────────────────────────────────────────────────

def connect(with_db: bool = True) -> mysql.connector.MySQLConnection:
    cfg = {**DB_CFG}
    if not with_db:
        cfg.pop("database")
    return mysql.connector.connect(**cfg)


def apply_schema(conn, recreate: bool) -> None:
    cur = conn.cursor()
    if recreate:
        for tbl in ("migrant", "stop_count", "count", "vehicle",
                    "weather", "route", "species"):
            cur.execute(f"DROP TABLE IF EXISTS `{tbl}`")
            print(f"  Dropped {tbl}")
        conn.commit()

    # Strip comment lines before splitting so leading comments don't hide statements
    raw = SCHEMA_SQL.read_text()
    lines = [l for l in raw.splitlines() if not l.strip().startswith("--")]
    sql = "\n".join(lines)
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt:
            cur.execute(stmt)
    conn.commit()
    cur.close()
    print("Schema applied.")


def bulk_insert(conn, table: str, sql: str, rows: list) -> int:
    if not rows:
        return 0
    cur = conn.cursor()
    for i in range(0, len(rows), BATCH_SIZE):
        cur.executemany(sql, rows[i : i + BATCH_SIZE])
    conn.commit()
    cur.close()
    return len(rows)


def _ni(v) -> int | None:
    """Nullable int — handles NaN and whitespace-only strings."""
    if pd.isna(v):
        return None
    s = str(v).strip()
    return None if s == "" else int(float(s))


def _nf(v) -> float | None:
    """Nullable float — handles NaN and whitespace-only strings."""
    if pd.isna(v):
        return None
    s = str(v).strip()
    return None if s == "" else float(s)


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_species(conn, data_dir: Path) -> None:
    df = pd.read_csv(data_dir / "SpeciesList.csv", encoding=ENCODING)
    rows = [
        (_ni(r.AOU), _ni(r.Seq), r.English_Common_Name,
         r.French_Common_Name, r.Order, r.Family, r.Genus, r.Species)
        for _, r in df.iterrows()
    ]
    n = bulk_insert(conn, "species", """
        INSERT INTO species
          (aou, seq, english_name, french_name, `order`, family, genus, species_epithet)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE english_name=VALUES(english_name)
    """, rows)
    print(f"  species: {n:,} rows")


def load_routes(conn, data_dir: Path) -> None:
    df = pd.read_csv(data_dir / "Routes.csv", encoding=ENCODING)
    rows = [
        (int(r.CountryNum), int(r.StateNum), int(r.Route),
         r.RouteName, int(r.Active),
         float(r.Latitude), float(r.Longitude),
         int(r.Stratum), int(r.BCR),
         int(r.RouteTypeID), int(r.RouteTypeDetailID))
        for _, r in df.iterrows()
    ]
    n = bulk_insert(conn, "route", """
        INSERT INTO route
          (country_num, state_num, route, route_name, active,
           latitude, longitude, stratum, bcr, route_type_id, route_type_detail_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE route_name=VALUES(route_name), active=VALUES(active)
    """, rows)
    print(f"  route: {n:,} rows")


def load_weather(conn, data_dir: Path) -> None:
    df = pd.read_csv(data_dir / "Weather.csv", encoding=ENCODING)
    rows = [
        (int(r.RouteDataID), int(r.CountryNum), int(r.StateNum),
         int(r.Route), int(r.RPID), int(r.Year),
         _ni(r.Month), _ni(r.Day), _ni(r.ObsN), _ni(r.TotalSpp),
         _ni(r.StartTemp), _ni(r.EndTemp),
         r.TempScale if pd.notna(r.TempScale) else None,
         _ni(r.StartWind), _ni(r.EndWind),
         _ni(r.StartSky), _ni(r.EndSky),
         _ni(r.StartTime), _ni(r.EndTime),
         _ni(r.Assistant), _ni(r.QualityCurrentID), _ni(r.RunType))
        for _, r in df.iterrows()
    ]
    n = bulk_insert(conn, "weather", """
        INSERT INTO weather
          (route_data_id, country_num, state_num, route, rpid, year,
           month, day, obs_n, total_spp,
           start_temp, end_temp, temp_scale,
           start_wind, end_wind, start_sky, end_sky,
           start_time, end_time, assistant, quality_current_id, run_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE run_type=VALUES(run_type)
    """, rows)
    print(f"  weather: {n:,} rows")


def load_vehicle(conn, data_dir: Path) -> None:
    df = pd.read_csv(data_dir / "VehicleData.csv", encoding=ENCODING)
    car_src   = [f"Car{i}"   for i in range(1, 51)]
    noise_src = [f"Noise{i}" for i in range(1, 51)]

    # Build rows: nullable RecordedCar (float), integer car/noise columns
    key_cols = ["RouteDataID", "CountryNum", "StateNum", "Route", "RPID", "Year"]
    keys    = df[key_cols].values.tolist()
    rec_car = [None if pd.isna(v) else float(v) for v in df["RecordedCar"]]
    # Replace any remaining NaN in car/noise arrays with None
    def _clean_row(vals):
        return [None if (isinstance(v, float) and pd.isna(v)) else int(v) for v in vals]
    cars  = [_clean_row(r) for r in df[car_src].values.tolist()]
    noise = [_clean_row(r) for r in df[noise_src].values.tolist()]
    rows  = [tuple(k) + (rc,) + tuple(c) + tuple(n)
             for k, rc, c, n in zip(keys, rec_car, cars, noise)]

    placeholders = ",".join(["%s"] * (7 + 50 + 50))
    car_cols_str   = ",".join(CAR_COLS)
    noise_cols_str = ",".join(NOISE_COLS)
    n = bulk_insert(conn, "vehicle", f"""
        INSERT INTO vehicle
          (route_data_id, country_num, state_num, route, rpid, year,
           recorded_car, {car_cols_str}, {noise_cols_str})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE recorded_car=VALUES(recorded_car)
    """, rows)
    print(f"  vehicle: {n:,} rows")


COUNT_COLS = ["RouteDataID", "CountryNum", "StateNum", "Route", "RPID", "Year",
              "AOU", "Count10", "Count20", "Count30", "Count40", "Count50",
              "StopTotal", "SpeciesTotal"]
COUNT_SQL = """
    INSERT IGNORE INTO `count`
      (route_data_id, country_num, state_num, route, rpid, year,
       aou, count10, count20, count30, count40, count50,
       stop_total, species_total)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""


def load_count(conn, data_dir: Path) -> None:
    zpath = data_dir / "States.zip"
    total = 0
    cur = conn.cursor()
    with zipfile.ZipFile(zpath) as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        for name in sorted(csv_names):
            state = Path(name).stem
            with zf.open(name) as f:
                for chunk in pd.read_csv(f, chunksize=BATCH_SIZE,
                                         encoding=ENCODING):
                    rows = chunk[COUNT_COLS].values.tolist()
                    cur.executemany(COUNT_SQL, rows)
                    conn.commit()
                    total += len(rows)
            print(f"    {state}: running total {total:,}")
    cur.close()
    print(f"  count: {total:,} rows")


STOP_SRC_COLS = (["RouteDataID", "CountryNum", "StateNum", "Route", "RPID", "Year", "AOU"]
                 + [f"Stop{i}" for i in range(1, 51)])


def _load_stop_table(conn, table: str, zpath: Path, csv_names: list[str]) -> None:
    stop_col_list = ",".join(STOP_COLS)
    placeholders  = ",".join(["%s"] * (7 + 50))
    sql = f"""
        INSERT IGNORE INTO `{table}`
          (route_data_id, country_num, state_num, route, rpid, year, aou,
           {stop_col_list})
        VALUES ({placeholders})
    """
    total = 0
    cur = conn.cursor()
    with zipfile.ZipFile(zpath) as zf:
        for name in sorted(csv_names):
            fname = Path(name).name
            with zf.open(name) as f:
                for chunk in pd.read_csv(f, chunksize=BATCH_SIZE,
                                         encoding=ENCODING):
                    rows = chunk[STOP_SRC_COLS].values.tolist()
                    cur.executemany(sql, rows)
                    conn.commit()
                    total += len(rows)
            print(f"    {fname}: running total {total:,}")
    cur.close()
    print(f"  {table}: {total:,} rows")


def load_stop_count(conn, data_dir: Path) -> None:
    zpath = data_dir / "50-StopData.zip"
    with zipfile.ZipFile(zpath) as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
    _load_stop_table(conn, "stop_count", zpath, csv_names)


def load_migrant(conn, data_dir: Path) -> None:
    zpath = data_dir / "MigrantNonBreeder.zip"
    with zipfile.ZipFile(zpath) as zf:
        csv_names = [n for n in zf.namelist()
                     if n.endswith(".csv") and "Migrants.csv" in n]
    _load_stop_table(conn, "migrant", zpath, csv_names)


# ── Verification ──────────────────────────────────────────────────────────────

def verify(conn) -> None:
    cur = conn.cursor()
    for tbl in ("species", "route", "weather", "vehicle",
                "count", "stop_count", "migrant"):
        try:
            cur.execute(f"SELECT COUNT(*) FROM `{tbl}`")
            n = cur.fetchone()[0]
            print(f"  {tbl}: {n:,} rows")
        except MySQLError as e:
            print(f"  {tbl}: ERROR — {e}")
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Load BBS 2024 data into MySQL 'bbs' database")
    ap.add_argument("--data-dir",    default=str(DATA_DIR),
                    help="Directory containing BBS data files")
    ap.add_argument("--recreate",    action="store_true",
                    help="Drop and recreate all tables before loading")
    ap.add_argument("--skip-counts", action="store_true",
                    help="Skip count, stop_count, and migrant tables (load refs + weather only)")
    ap.add_argument("--verify-only", action="store_true",
                    help="Print row counts without loading")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    required = ["SpeciesList.csv", "Routes.csv", "Weather.csv",
                "VehicleData.csv", "States.zip", "50-StopData.zip",
                "MigrantNonBreeder.zip"]
    missing = [f for f in required if not (data_dir / f).exists()]
    if missing:
        print(f"ERROR: missing files in {data_dir}:", file=sys.stderr)
        for f in missing:
            print(f"  {f}", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to {DB_CFG['host']}:{DB_CFG['port']} ...")
    try:
        # Create database if needed, then reconnect with it selected
        conn_no_db = connect(with_db=False)
        cur = conn_no_db.cursor()
        cur.execute("CREATE DATABASE IF NOT EXISTS bbs "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn_no_db.commit()
        conn_no_db.close()
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

    print("\nLoading reference tables ...")
    load_species(conn, data_dir)
    load_routes(conn, data_dir)

    print("\nLoading survey metadata ...")
    load_weather(conn, data_dir)
    load_vehicle(conn, data_dir)

    if not args.skip_counts:
        print("\nLoading count (States.zip) ...")
        t0 = time.time()
        load_count(conn, data_dir)
        print(f"  ({time.time()-t0:.0f}s)")

        print("\nLoading stop_count (50-StopData.zip) ...")
        t0 = time.time()
        load_stop_count(conn, data_dir)
        print(f"  ({time.time()-t0:.0f}s)")

        print("\nLoading migrant (MigrantNonBreeder.zip) ...")
        load_migrant(conn, data_dir)

    print("\nVerification:")
    verify(conn)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
