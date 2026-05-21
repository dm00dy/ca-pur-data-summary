#!/usr/bin/env python3
"""
Load California PUR data (1990-2023) into MySQL.

Creates schema, loads reference tables, then streams all UDC files into
pur_record in batches of 50,000 rows.

Format notes:
  1990-2019, 2021: UDC files in zip root, lowercase names
  2020:            UDC files in pur2020/ subdirectory
  2022:            UDC files in ftp_files/ subdirectory
  2023:            UDC files in pur2023/pur_data/, refs in pur2023/lookup_tables/

Credentials via environment variables (defaults match the Docker container):
    PUR_DB_HOST  (default: localhost)
    PUR_DB_PORT  (default: 3366)
    PUR_DB_USER  (default: root)
    PUR_DB_PASS  (default: password)
    PUR_DB_NAME  (default: pur_data)

Usage:
    source .venv/bin/activate
    python load_pur_mysql.py                            # download + load all years
    python load_pur_mysql.py --years 2010 2011 2012     # specific years
    python load_pur_mysql.py --skip-download            # use cached zips only
    python load_pur_mysql.py --skip-refs                # skip reference tables
    python load_pur_mysql.py --skip-facts               # refs only
    python load_pur_mysql.py --verify-only              # row count check
    python load_pur_mysql.py --recreate                 # drop + recreate all tables
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import mysql.connector
from mysql.connector import Error as MySQLError

# ── Config ────────────────────────────────────────────────────────────────────

CACHE_DIR    = Path("pur_analysis/cache")
SCHEMA_SQL   = Path("schema_pur.sql")
TOX_CSV      = Path("toxicity_lookup.csv")
YEARS        = list(range(1990, 2024))
BATCH_SIZE   = 50_000
ARCHIVE_BASE = "https://files.cdpr.ca.gov/pub/outgoing/pur_archives"

DB_CFG = {
    "host":     os.environ.get("PUR_DB_HOST", "localhost"),
    "port":     int(os.environ.get("PUR_DB_PORT", 3366)),
    "user":     os.environ.get("PUR_DB_USER", "root"),
    "password": os.environ.get("PUR_DB_PASS", "password"),
    "database": os.environ.get("PUR_DB_NAME", "pur_data"),
    "charset":  "utf8mb4",
    "autocommit": False,
}

# ── Download ──────────────────────────────────────────────────────────────────

def download_year(year: int) -> bool:
    """Download pur{year}.zip to cache if not already present. Returns True if downloaded."""
    dest = zip_path(year)
    if dest.exists():
        return False
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url  = f"{ARCHIVE_BASE}/pur{year}.zip"
    tmp  = dest.with_suffix(".tmp")
    print(f"  Downloading {url} ...", flush=True)
    t0   = time.time()
    try:
        req = urllib.request.urlopen(url, timeout=120)
        total = int(req.headers.get("Content-Length", 0))
        downloaded = 0
        with open(tmp, "wb") as out:
            while True:
                chunk = req.read(1 << 20)   # 1 MB chunks
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = 100 * downloaded / total
                    print(f"\r    {downloaded/1e6:.1f} / {total/1e6:.1f} MB  ({pct:.0f}%)",
                          end="", flush=True)
        tmp.rename(dest)
        elapsed = time.time() - t0
        print(f"\r    {dest.stat().st_size/1e6:.1f} MB saved in {elapsed:.0f}s" + " "*10)
        return True
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        print(f"\n    ERROR downloading pur{year}.zip: {e}", file=sys.stderr)
        return False


def download_years(years: list[int]) -> None:
    missing = [y for y in years if not zip_path(y).exists()]
    if not missing:
        print("  All zips already cached.")
        return
    print(f"\n── Downloading {len(missing)} zip(s): {missing[0]}–{missing[-1]} ────────────")
    for year in missing:
        download_year(year)


# ── Helpers ───────────────────────────────────────────────────────────────────

def connect() -> mysql.connector.MySQLConnection:
    cfg = {**DB_CFG}
    db_name = cfg.pop("database")
    conn = mysql.connector.connect(**cfg)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"USE `{db_name}`")
    conn.commit()
    cur.close()
    conn.database = db_name
    return conn


def null(val: str) -> str | None:
    v = val.strip()
    return v if v else None


def to_float(val: str) -> float | None:
    v = val.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def to_int(val: str) -> int | None:
    v = val.strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


_MONTH = {m: i+1 for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
)}

def parse_date(val: str) -> str | None:
    """
    Accept source date formats and return ISO YYYY-MM-DD or None.
    MM/DD/YYYY  — pre-2023 UDC
    DD-MON-YYYY — 2023 UDC and 2023 product table
    MMDDYYYY    — pre-2023 product table
    """
    v = val.strip()
    if not v:
        return None
    try:
        if "/" in v:
            m, d, y = v.split("/")
            return f"{y}-{int(m):02d}-{int(d):02d}"
        if "-" in v and len(v) == 11:
            d, mon, y = v.split("-")
            return f"{y}-{_MONTH[mon.upper()]:02d}-{int(d):02d}"
        if len(v) == 8 and v.isdigit():
            return f"{v[4:8]}-{v[0:2]}-{v[2:4]}"
    except (ValueError, KeyError):
        pass
    return None


def open_zip_text(zf: zipfile.ZipFile, name: str) -> io.TextIOWrapper:
    return io.TextIOWrapper(zf.open(name), encoding="latin-1", newline="")


def zip_path(year: int) -> Path:
    return CACHE_DIR / f"pur{year}.zip"


def _bulk_insert(conn, table: str, cols: list[str], rows: list[tuple],
                 ignore: bool = True) -> int:
    if not rows:
        return 0
    ph = ", ".join(["%s"] * len(cols))
    verb = "INSERT IGNORE" if ignore else "INSERT"
    sql = f"{verb} INTO `{table}` ({', '.join(cols)}) VALUES ({ph})"
    cur = conn.cursor()
    cur.executemany(sql, rows)
    n = cur.rowcount
    conn.commit()
    cur.close()
    return n


# ── Zip layout detection ──────────────────────────────────────────────────────
#
# Path structure varies by year:
#   2015-2019, 2021: root/formula.txt          root/udc{YY}_{CC}.txt
#   2020:            pur2020/formula.txt        pur2020/udc20_{CC}.txt
#   2022:            ftp_files/formula.txt      ftp_files/udc22_{CC}.txt
#   2023:            pur2023/lookup_tables/…    pur2023/pur_data/udc23_{CC}.txt
#
# 2023 also renames several files (FORMULATION, PUR_SITE, PUR_QUALIFY)
# and adds PROD_CHEM.  udc23_{CC}.txt retains the familiar column layout.

_REF_ALIASES_2023 = {
    "formula.txt":   "FORMULATION.txt",
    "site.txt":      "PUR_SITE.txt",
    "qualify.txt":   "PUR_QUALIFY.txt",
    "prod_chem.txt": "PROD_CHEM.txt",
}


def _detect_prefixes(zf: zipfile.ZipFile, year: int) -> tuple[str, str]:
    """
    Return (ref_prefix, udc_prefix) for the given zip.
    E.g. ("ftp_files/", "ftp_files/") or ("pur2023/lookup_tables/", "pur2023/pur_data/")
    """
    yy = str(year)[2:]
    names_set = set(zf.namelist())

    # 2023 has a dedicated lookup_tables subdirectory
    if f"pur{year}/lookup_tables/FORMULATION.txt" in names_set:
        return f"pur{year}/lookup_tables/", f"pur{year}/pur_data/"

    # probe for formula.txt in known prefixes
    for prefix in ("", f"pur{year}/", "ftp_files/"):
        if f"{prefix}formula.txt" in names_set:
            udc_prefix = prefix  # UDC files share the same prefix for these years
            return prefix, udc_prefix

    raise FileNotFoundError(f"Cannot detect zip layout for pur{year}.zip")


def ref_file(zf: zipfile.ZipFile, year: int, name: str) -> str:
    """Return the full member path for a named reference file in the zip."""
    ref_prefix, _ = _detect_prefixes(zf, year)
    if year >= 2023 and name in _REF_ALIASES_2023:
        name = _REF_ALIASES_2023[name]
    candidate = ref_prefix + name
    if candidate not in set(zf.namelist()):
        # try uppercase stem only (2023 lookup_tables use UPPER.txt)
        stem, ext = name.rsplit(".", 1)
        candidate_up = ref_prefix + stem.upper() + "." + ext
        if candidate_up in set(zf.namelist()):
            return candidate_up
        raise KeyError(f"'{name}' not found in pur{year}.zip (tried {candidate})")
    return candidate


def udc_members(zf: zipfile.ZipFile, year: int) -> list[str]:
    """Return sorted list of UDC county file paths in the zip."""
    _, udc_prefix = _detect_prefixes(zf, year)
    yy = str(year)[2:]
    return sorted(
        n for n in zf.namelist()
        if n.startswith(udc_prefix + f"udc{yy}_") and n.lower().endswith(".txt")
    )


def best_zip_for_refs(years: list[int]) -> tuple[zipfile.ZipFile, int]:
    """Open the most recent available zip for reference tables."""
    for y in sorted(years, reverse=True):
        p = zip_path(y)
        if p.exists():
            return zipfile.ZipFile(p), y
    raise FileNotFoundError("No PUR zip files found in cache directory")

# ── Schema ────────────────────────────────────────────────────────────────────

def apply_schema(conn, recreate: bool = False) -> None:
    print("Applying schema from schema_pur.sql ...")
    lines = [
        ln for ln in SCHEMA_SQL.read_text().splitlines()
        if not ln.strip().startswith("--")
    ]
    sql = "\n".join(lines)
    cur = conn.cursor()
    if recreate:
        drops = [
            "DROP TABLE IF EXISTS pur_record",
            "DROP TABLE IF EXISTS prod_chem",
            "DROP TABLE IF EXISTS toxicity",
            "DROP TABLE IF EXISTS product",
            "DROP TABLE IF EXISTS qualify",
            "DROP TABLE IF EXISTS error_description",
            "DROP TABLE IF EXISTS site",
            "DROP TABLE IF EXISTS county",
            "DROP TABLE IF EXISTS chemical",
            "DROP TABLE IF EXISTS formula",
        ]
        for d in drops:
            cur.execute(d)
        print("  Tables dropped.")
    for stmt in sql.split(";"):
        s = stmt.strip()
        if s:
            cur.execute(s)
    conn.commit()
    cur.close()
    print("  Schema ready.")

# ── Reference table loaders ───────────────────────────────────────────────────

def load_formula(conn, zf: zipfile.ZipFile, year: int) -> None:
    print("  Loading formula ...")
    rows = []
    reader = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "formula.txt")))
    for r in reader:
        rows.append((
            null(r.get("formula_cd","")),
            null(r.get("formula_dsc","")),
            null(r.get("dryliquid_sw","")),
        ))
    n = _bulk_insert(conn, "formula", ["formula_cd","formula_dsc","dryliquid_sw"], rows)
    print(f"    {n} rows")


def load_chemical(conn, zf: zipfile.ZipFile, year: int) -> None:
    print("  Loading chemical + casnum ...")
    rows = []
    reader = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "chemical.txt")))
    for r in reader:
        code = to_int(r.get("chem_code",""))
        name = null(r.get("chemname",""))
        if code is None or not name:
            continue
        rows.append((code, to_int(r.get("chemalpha_cd","")), name, None))
    _bulk_insert(conn, "chemical", ["chem_code","chemalpha_cd","chemname","casnum"], rows)

    # Patch casnum
    cas_rows = []
    reader2 = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "chem_cas.txt")))
    for r in reader2:
        code = to_int(r.get("chem_code",""))
        cas  = r.get("casnum","").strip()
        if code and cas:
            cas_rows.append((cas, code))
    if cas_rows:
        cur = conn.cursor()
        cur.executemany("UPDATE chemical SET casnum=%s WHERE chem_code=%s", cas_rows)
        conn.commit()
        cur.close()
    print(f"    {len(rows)} chemicals, {len(cas_rows)} casnum patches")


def load_county(conn, zf: zipfile.ZipFile, year: int) -> None:
    print("  Loading county ...")
    rows = []
    # Header has historic typo 'couty_name' — access by position
    reader = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "county.txt")))
    for r in reader:
        vals = list(r.values())
        code = to_int(vals[0]) if vals else None
        name = vals[1].strip() if len(vals) > 1 else ""
        if code and name:
            rows.append((code, name))
    n = _bulk_insert(conn, "county", ["county_cd","county_name"], rows)
    print(f"    {n} rows")


def load_site(conn, zf: zipfile.ZipFile, year: int) -> None:
    print("  Loading site ...")
    rows = []
    reader = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "site.txt")))
    for r in reader:
        code = to_int(r.get("site_code",""))
        name = null(r.get("site_name",""))
        if code is not None and name:
            rows.append((code, name))
    n = _bulk_insert(conn, "site", ["site_code","site_name"], rows)
    print(f"    {n} rows")


def load_qualify(conn, zf: zipfile.ZipFile, year: int) -> None:
    print("  Loading qualify ...")
    rows = []
    reader = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "qualify.txt")))
    for r in reader:
        code = to_int(r.get("qualify_cd",""))
        desc = null(r.get("qualify_dsc",""))
        if code is not None and desc:
            rows.append((code, desc))
    n = _bulk_insert(conn, "qualify", ["qualify_cd","qualify_dsc"], rows)
    print(f"    {n} rows")


def load_error_description(conn, zf: zipfile.ZipFile, year: int) -> None:
    print("  Loading error_description ...")
    if year >= 2023:
        print("    (not available in 2023 zip; using pre-loaded data)")
        return
    rows = []
    reader = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "error_descriptions.txt")))
    for r in reader:
        code = to_int(r.get("error_code") or r.get("error_cd") or "")
        desc = null(r.get("error_description") or r.get("description") or "")
        if code is not None and desc:
            rows.append((code, desc))
    n = _bulk_insert(conn, "error_description",
                     ["error_code","error_description"], rows)
    print(f"    {n} rows")


def load_product(conn, zf: zipfile.ZipFile, year: int) -> None:
    print("  Loading product ...")
    rows = []
    reader = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "product.txt")))
    for r in reader:
        prodno = to_int(r.get("prodno",""))
        if prodno is None:
            continue
        rows.append((
            prodno,
            to_int(r.get("mfg_firmno","")),
            to_int(r.get("reg_firmno","")),
            to_int(r.get("label_seq_no","")),
            null(r.get("revision_no","")),
            to_int(r.get("fut_firmno","")),
            null(r.get("prodstat_ind","")),
            null(r.get("product_name","")),
            null(r.get("show_regno","")),
            null(r.get("aer_grnd_ind","")),
            null(r.get("agriccom_sw","")),
            null(r.get("confid_sw","")),
            to_float(r.get("density","")),
            null(r.get("formula_cd","")),
            parse_date(r.get("full_exp_dt","")),
            parse_date(r.get("full_iss_dt","")),
            null(r.get("fumigant_sw","")),
            null(r.get("gen_pest_ind","")),
            parse_date(r.get("lastup_dt","")),
            null(r.get("mfg_ref_sw","")),
            parse_date(r.get("prod_inac_dt","")),
            parse_date(r.get("reg_dt","")),
            null(r.get("reg_type_ind","")),
            null(r.get("rodent_sw","")),
            null(r.get("signlwrd_ind","")),
            null(r.get("soilappl_sw","")),
            null(r.get("specgrav_sw","")),
            to_float(r.get("spec_gravity","")),
            null(r.get("condreg_sw","")),
        ))
    n = _bulk_insert(conn, "product", [
        "prodno","mfg_firmno","reg_firmno","label_seq_no","revision_no",
        "fut_firmno","prodstat_ind","product_name","show_regno","aer_grnd_ind",
        "agriccom_sw","confid_sw","density","formula_cd","full_exp_dt",
        "full_iss_dt","fumigant_sw","gen_pest_ind","lastup_dt","mfg_ref_sw",
        "prod_inac_dt","reg_dt","reg_type_ind","rodent_sw","signlwrd_ind",
        "soilappl_sw","specgrav_sw","spec_gravity","condreg_sw",
    ], rows)
    print(f"    {n} rows")


def load_prod_chem(conn, zf: zipfile.ZipFile, year: int) -> None:
    """Load product-to-chemical mapping (only available from 2023 zip)."""
    print("  Loading prod_chem ...")
    if year < 2023:
        print("    (not available in pre-2023 zips; skipping)")
        return
    rows = []
    reader = csv.DictReader(open_zip_text(zf, ref_file(zf, year, "prod_chem.txt")))
    for r in reader:
        prodno    = to_int(r.get("prodno",""))
        chem_code = to_int(r.get("chem_code",""))
        pct       = to_float(r.get("prodchem_pct",""))
        if prodno is not None and chem_code and chem_code > 0:
            rows.append((prodno, chem_code, pct))
    n = _bulk_insert(conn, "prod_chem",
                     ["prodno","chem_code","prodchem_pct"], rows)
    print(f"    {n} rows")


def load_toxicity(conn) -> None:
    """Load toxicity_lookup.csv.

    CSV column layout (cols 0-9 are original; 10-23 are extended endpoints;
    col 24+ is notes which may contain unquoted commas):
      0  chemname                 10 bee_contact_ld50   15 chironomid_ec50
      1  chem_class               11 bee_contact_ceil   16 chironomid_ceiling
      2  avian_ld50               12 bee_oral_ld50      17 chironomid_endpoint
      3  avian_ceiling            13 bee_oral_ceiling   18 chironomid_test_species
      4  avian_test_species       14 bee_source_url     19 chironomid_source_url
      5  avian_source_url                               20 avian_noec_repro
      6  aquatic_lc50                                   21 avian_noec_ceiling
      7  aquatic_ceiling                                22 avian_noec_test_species
      8  aquatic_test_species                           23 avian_noec_source_url
      9  aquatic_source_url                             24+ notes
    """
    print("  Loading toxicity from toxicity_lookup.csv ...")
    # Detect CSV version by inspecting header
    with open(TOX_CSV, encoding="utf-8") as f:
        header = f.readline()
    extended = "bee_contact_ld50" in header
    notes_col = 24 if extended else 10

    rows = []
    with open(TOX_CSV, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.rstrip("\n").split(",")
            if len(parts) < 10:
                continue
            if extended and len(parts) >= 24:
                row = (
                    parts[0].strip(), parts[1].strip(),
                    to_float(parts[2]), to_int(parts[3]),
                    null(parts[4]),    null(parts[5]),
                    to_float(parts[6]), to_int(parts[7]),
                    null(parts[8]),    null(parts[9]),
                    to_float(parts[10]), to_int(parts[11]),
                    to_float(parts[12]), to_int(parts[13]),
                    null(parts[14]),
                    to_float(parts[15]), to_int(parts[16]),
                    null(parts[17]),   null(parts[18]),
                    null(parts[19]),
                    to_float(parts[20]), to_int(parts[21]),
                    null(parts[22]),   null(parts[23]),
                    ",".join(parts[24:]).strip() or None,
                )
            else:
                row = (
                    parts[0].strip(), parts[1].strip(),
                    to_float(parts[2]), to_int(parts[3]),
                    null(parts[4]),    null(parts[5]),
                    to_float(parts[6]), to_int(parts[7]),
                    null(parts[8]),    null(parts[9]),
                    None, 0, None, 0, None,
                    None, 0, None, None, None,
                    None, 0, None, None,
                    ",".join(parts[10:]).strip() or None,
                )
            rows.append(row)
    cols = [
        "chemname", "chem_class",
        "avian_ld50", "avian_ceiling", "avian_test_species", "avian_source_url",
        "aquatic_lc50", "aquatic_ceiling", "aquatic_test_species", "aquatic_source_url",
        "bee_contact_ld50", "bee_contact_ceiling",
        "bee_oral_ld50", "bee_oral_ceiling", "bee_source_url",
        "chironomid_ec50", "chironomid_ceiling",
        "chironomid_endpoint", "chironomid_test_species", "chironomid_source_url",
        "avian_noec_repro", "avian_noec_ceiling",
        "avian_noec_test_species", "avian_noec_source_url",
        "notes",
    ]
    n = _bulk_insert(conn, "toxicity", cols, rows)
    print(f"    {n} rows")


def load_refs(conn, years: list[int]) -> None:
    print("\n── Loading reference tables ─────────────────────────────────────────")
    zf, ref_year = best_zip_for_refs(years)
    print(f"  Using pur{ref_year}.zip for reference tables")
    with zf:
        load_formula(conn, zf, ref_year)
        load_chemical(conn, zf, ref_year)
        load_county(conn, zf, ref_year)
        load_site(conn, zf, ref_year)
        load_qualify(conn, zf, ref_year)
        load_error_description(conn, zf, ref_year)
        load_product(conn, zf, ref_year)
        load_prod_chem(conn, zf, ref_year)

    # error_description only in pre-2023; load from earlier zip if needed
    if ref_year >= 2023:
        for y in sorted(years, reverse=True):
            if y < 2023 and zip_path(y).exists():
                print(f"  Loading error_description from pur{y}.zip ...")
                with zipfile.ZipFile(zip_path(y)) as zf2:
                    load_error_description(conn, zf2, y)
                break

    if TOX_CSV.exists():
        load_toxicity(conn)
    else:
        print("  toxicity_lookup.csv not found, skipping")

# ── UDC fact record loader ────────────────────────────────────────────────────

RECORD_COLS = [
    "year","use_no","prodno","chem_code","prodchem_pct",
    "lbs_chm_used","lbs_prd_used","amt_prd_used","unit_of_meas",
    "acre_planted","unit_planted","acre_treated","unit_treated",
    "applic_cnt","applic_dt","applic_time","county_cd",
    "base_ln_mer","township","tship_dir","range_no","range_dir","section",
    "site_loc_id","grower_id","license_no","planting_seq","aer_gnd_ind",
    "site_code","qualify_cd","batch_no","document_no","summary_cd",
    "record_id","comtrs","error_flag","ag_ind","fume_cd","pre_plant",
]
INSERT_SQL = (
    f"INSERT IGNORE INTO pur_record ({', '.join(RECORD_COLS)}) VALUES "
    f"({', '.join(['%s']*len(RECORD_COLS))})"
)


def _row_pre2023(r: dict, year: int) -> tuple:
    """Convert a 2015-2022 UDC DictReader row into the INSERT tuple."""
    chem = to_int(r.get("chem_code",""))
    if chem is None:
        return None
    return (
        year,
        to_int(r.get("use_no","")),
        to_int(r.get("prodno","")),
        chem,
        to_float(r.get("prodchem_pct","")),
        to_float(r.get("lbs_chm_used","")),
        to_float(r.get("lbs_prd_used","")),
        to_float(r.get("amt_prd_used","")),
        null(r.get("unit_of_meas","")),
        to_float(r.get("acre_planted","")),
        null(r.get("unit_planted","")),
        to_float(r.get("acre_treated","")),
        null(r.get("unit_treated","")),
        to_int(r.get("applic_cnt","")),
        parse_date(r.get("applic_dt","")),
        to_int(r.get("applic_time","")),
        to_int(r.get("county_cd","")),
        null(r.get("base_ln_mer","")),
        to_int(r.get("township","")),
        null(r.get("tship_dir","")),
        to_int(r.get("range","")),
        null(r.get("range_dir","")),
        to_int(r.get("section","")),
        null(r.get("site_loc_id","")),
        null(r.get("grower_id","")),
        null(r.get("license_no","")),
        to_int(r.get("planting_seq","")),
        null(r.get("aer_gnd_ind","")),
        to_int(r.get("site_code","")),
        to_int(r.get("qualify_cd","")),
        to_int(r.get("batch_no","")),
        null(r.get("document_no","")),
        null(r.get("summary_cd","")),
        null(r.get("record_id","")),
        null(r.get("comtrs","")),
        null(r.get("error_flag","")),
        None,   # ag_ind
        None,   # fume_cd
        None,   # pre_plant
    )


def _rows_2023(r: dict, prod_chem_map: dict) -> list[tuple]:
    """
    Expand a 2023 UDC product-level row into one tuple per chemical.
    Returns empty list if prodno has no prod_chem entries (inert-only products).
    """
    prodno = to_int(r.get("prodno",""))
    chems  = prod_chem_map.get(prodno, [])
    if not chems:
        return []

    lbs_prd = to_float(r.get("lbs_prd_used","")) or 0.0
    base = dict(
        use_no       = to_int(r.get("use_no","")),
        prodno       = prodno,
        lbs_prd_used = lbs_prd or None,
        amt_prd_used = to_float(r.get("amt_prd_used","")),
        unit_of_meas = null(r.get("unit_of_meas","")),
        acre_planted = to_float(r.get("acre_planted","")),
        unit_planted = null(r.get("unit_planted","")),
        acre_treated = to_float(r.get("acre_treated","")),
        unit_treated = null(r.get("unit_treated","")),
        applic_cnt   = to_int(r.get("applic_cnt","")),
        applic_dt    = parse_date(r.get("applic_dt","")),
        applic_time  = to_int(r.get("applic_time","")),
        county_cd    = to_int(r.get("county_cd","")),
        base_ln_mer  = null(r.get("base_ln_mer","")),
        township     = to_int(r.get("township","")),
        tship_dir    = null(r.get("tship_dir","")),
        range_no     = to_int(r.get("range","")),
        range_dir    = null(r.get("range_dir","")),
        section      = to_int(r.get("section","")),
        site_loc_id  = null(r.get("site_loc_id","")),
        grower_id    = null(r.get("grower_id","")),
        license_no   = null(r.get("license_no","")),
        planting_seq = to_int(r.get("planting_seq","")),
        aer_gnd_ind  = null(r.get("aer_gnd_ind","")),
        site_code    = to_int(r.get("site_code","")),
        qualify_cd   = to_int(r.get("qualify_cd","")),
        record_id    = null(r.get("record_id","")),
        comtrs       = null(r.get("comtrs","")),
        error_flag   = null(r.get("error_flag","")),
        ag_ind       = null(r.get("ag_ind","")),
        fume_cd      = null(r.get("fume_cd","")),
        pre_plant    = null(r.get("pre_plant","")),
    )

    rows = []
    for chem_code, pct in chems:
        lbs_chm = round(lbs_prd * pct / 100.0, 6) if lbs_prd else None
        rows.append((
            2023,
            base["use_no"],
            base["prodno"],
            chem_code,
            pct,
            lbs_chm,
            base["lbs_prd_used"],
            base["amt_prd_used"],
            base["unit_of_meas"],
            base["acre_planted"],
            base["unit_planted"],
            base["acre_treated"],
            base["unit_treated"],
            base["applic_cnt"],
            base["applic_dt"],
            base["applic_time"],
            base["county_cd"],
            base["base_ln_mer"],
            base["township"],
            base["tship_dir"],
            base["range_no"],
            base["range_dir"],
            base["section"],
            base["site_loc_id"],
            base["grower_id"],
            base["license_no"],
            base["planting_seq"],
            base["aer_gnd_ind"],
            base["site_code"],
            base["qualify_cd"],
            None,   # batch_no (not in 2023)
            None,   # document_no
            None,   # summary_cd
            base["record_id"],
            base["comtrs"],
            base["error_flag"],
            base["ag_ind"],
            base["fume_cd"],
            base["pre_plant"],
        ))
    return rows


def load_year(conn, year: int) -> int:
    zp = zip_path(year)
    if not zp.exists():
        print(f"  {year}: zip not found, skipping")
        return 0

    total = 0
    t0    = time.time()

    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    conn.commit()

    with zipfile.ZipFile(zp) as zf:
        members = udc_members(zf, year)
        for i, member in enumerate(members):
            tag   = member.split("/")[-1]
            batch: list[tuple] = []

            reader = csv.DictReader(open_zip_text(zf, member))
            for r in reader:
                row = _row_pre2023(r, year)
                if row and row[1] is not None:  # skip if use_no null
                    batch.append(row)
                if len(batch) >= BATCH_SIZE:
                    cur.executemany(INSERT_SQL, batch)
                    conn.commit()
                    total += len(batch)
                    batch  = []

            if batch:
                cur.executemany(INSERT_SQL, batch)
                conn.commit()
                total += len(batch)

            elapsed = time.time() - t0
            print(f"\r  {year}  {tag}  ({i+1}/{len(members)})  "
                  f"{total:,} rows  {elapsed:.0f}s",
                  end="", flush=True)

    cur.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()
    cur.close()

    elapsed = time.time() - t0
    print(f"\r  {year}: {total:,} rows loaded in {elapsed:.0f}s" + " "*30)
    return total


def load_facts(conn, years: list[int]) -> None:
    print("\n── Loading UDC fact records ──────────────────────────────────────────")
    grand_total = 0
    t0 = time.time()
    for year in years:
        grand_total += load_year(conn, year)
    elapsed = time.time() - t0
    print(f"\nTotal: {grand_total:,} rows in {elapsed:.0f}s")

# ── Verification ──────────────────────────────────────────────────────────────

def verify(conn) -> None:
    print("\n── Row counts ────────────────────────────────────────────────────────")
    cur = conn.cursor()
    cur.execute(
        "SELECT year, COUNT(*) n, ROUND(SUM(lbs_chm_used),0) lbs "
        "FROM pur_record GROUP BY year ORDER BY year"
    )
    for row in cur:
        lbs = f"{row[2]:,.0f}" if row[2] is not None else "n/a"
        print(f"  {row[0]}  {row[1]:>12,} records  {lbs:>16} lbs AI")
    cur.execute("SELECT COUNT(*) FROM chemical")
    print(f"\n  chemical:  {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM product")
    print(f"  product:   {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM prod_chem")
    print(f"  prod_chem: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM toxicity")
    print(f"  toxicity:  {cur.fetchone()[0]:,}")
    cur.close()

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Load PUR data into MySQL")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS,
                        metavar="YEAR")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip downloading missing zips (use cache only)")
    parser.add_argument("--skip-refs",   action="store_true")
    parser.add_argument("--skip-facts",  action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recreate", action="store_true",
                        help="Drop and recreate all tables before loading")
    args = parser.parse_args()

    print(f"Connecting to {DB_CFG['host']}:{DB_CFG['port']} ...")
    try:
        conn = connect()
    except MySQLError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print("  Connected.")

    if args.verify_only:
        verify(conn)
        conn.close()
        return

    if not args.skip_download:
        download_years(args.years)

    apply_schema(conn, recreate=args.recreate)

    if not args.skip_refs:
        load_refs(conn, args.years)

    if not args.skip_facts:
        load_facts(conn, args.years)

    verify(conn)
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
