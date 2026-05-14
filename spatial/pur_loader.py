#!/usr/bin/env python3
"""
PUR Loader
==========
Reads PUR zip archives from the sibling cache directory, filters to tracked
insecticide classes, attaches toxicity values from toxicity_lookup.csv, and
writes a section-keyed Parquet table for use by exposure_engine.py.

Also loads the records into the DuckDB spatial database so exposure_engine.py
can run spatial queries against them.

Outputs:
    outputs/pur_sections.parquet      — one row per application record with comtrs
    outputs/pur_loader_summary.csv    — year × class totals for validation

Usage:
    python pur_loader.py [--years 2015 2016 ...]
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

PUR_CACHE_DIR = Path("../pur_analysis/cache")
TOXICITY_CSV = Path("../toxicity_lookup.csv")
OUTPUT_DIR = Path("outputs")
DB_PATH = Path("data/spatial.duckdb")

YEARS_DEFAULT = list(range(2015, 2024))

# UDC columns to read — chem_code and site_code are always present;
# chemname and site_name only appear in 2023+ (joined from lookup files for earlier years)
UDC_CORE_COLS = {
    "chem_code", "lbs_chm_used", "acre_treated",
    "applic_dt", "county_cd", "site_code", "aer_gnd_ind", "comtrs",
}
UDC_EXTRA_COLS = {"chemname", "site_name"}   # present in 2023+; joined otherwise
CHUNK = 200_000


# ---------------------------------------------------------------------------
# TOXICITY LOOKUP
# ---------------------------------------------------------------------------

def load_toxicity_lookup() -> dict[str, dict]:
    """Parse toxicity_lookup.csv by column index (notes col has unquoted commas).

    Returns {chemname_lower: {class, avian_ld50, avian_ceiling, aquatic_lc50, aquatic_ceiling}}.
    """
    rows: dict[str, dict] = {}
    with open(TOXICITY_CSV, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i == 0:
                continue  # skip header
            parts = line.rstrip("\n").split(",")
            if len(parts) < 8:
                continue
            chemname = parts[0].strip().lower()
            if not chemname:
                continue
            def _float(s: str) -> float | None:
                try:
                    return float(s.strip())
                except ValueError:
                    return None
            def _bool(s: str) -> bool:
                return s.strip().upper() in ("TRUE", "1", "YES")
            rows[chemname] = {
                "chem_class": parts[1].strip(),
                "avian_ld50": _float(parts[2]),
                "avian_ceiling": _bool(parts[3]),
                "aquatic_lc50": _float(parts[6]),
                "aquatic_ceiling": _bool(parts[7]),
            }
    return rows


# ---------------------------------------------------------------------------
# LOOKUP TABLE LOADING
# ---------------------------------------------------------------------------

def load_chem_lookup(zip_path: Path) -> dict[int, str]:
    """Load chemical.txt → {chem_code: chemname_lower}."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith("chemical.txt")]
        if not names:
            return {}
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, encoding="latin-1", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    df["chem_code"] = pd.to_numeric(df["chem_code"], errors="coerce")
    df["chemname"] = df["chemname"].str.strip().str.lower().fillna("")
    return {int(r.chem_code): r.chemname for r in df.itertuples() if pd.notna(r.chem_code)}


def load_site_lookup(zip_path: Path) -> dict[int, str]:
    """Load site.txt → {site_code: site_name}."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith("site.txt")]
        if not names:
            return {}
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, encoding="latin-1", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    df["site_code"] = pd.to_numeric(df["site_code"], errors="coerce")
    df["site_name"] = df["site_name"].str.strip().fillna("")
    return {int(r.site_code): r.site_name for r in df.itertuples() if pd.notna(r.site_code)}


# ---------------------------------------------------------------------------
# UDC STREAMING
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> str | None:
    """Convert PUR date strings (DD-MON-YYYY or MM/DD/YYYY) to ISO YYYY-MM-DD."""
    s = s.strip()
    if not s or s == "nan":
        return None
    import datetime
    for fmt in ("%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def stream_year(
    zip_path: Path,
    year: int,
    tox_lookup: dict[str, dict],
    chem_map: dict[int, str],
    site_map: dict[int, str],
) -> pd.DataFrame:
    """Stream all udc*.txt files for one year. Returns annotated DataFrame.

    chem_map / site_map are pre-loaded from chemical.txt / site.txt and used
    for years where chemname / site_name columns are absent from the UDC files.
    """
    frames: list[pd.DataFrame] = []
    all_cols = UDC_CORE_COLS | UDC_EXTRA_COLS

    with zipfile.ZipFile(zip_path) as zf:
        udc_files = [
            n for n in zf.namelist()
            if Path(n).name.lower().startswith("udc") and n.lower().endswith(".txt")
        ]
        print(f"  [{year}] {len(udc_files)} county files", flush=True)

        for i, name in enumerate(udc_files, 1):
            with zf.open(name) as fh:
                try:
                    reader = pd.read_csv(
                        fh,
                        encoding="latin-1",
                        usecols=lambda c: c.strip().lower() in all_cols,
                        dtype=str,
                        chunksize=CHUNK,
                        low_memory=False,
                        on_bad_lines="skip",
                    )
                except ValueError as exc:
                    print(f"    {Path(name).name}: skipped ({exc})")
                    continue

                for chunk in reader:
                    chunk.columns = [c.strip().lower() for c in chunk.columns]

                    # Drop records without a COMTRS (no location)
                    if "comtrs" not in chunk.columns:
                        continue
                    chunk = chunk[chunk["comtrs"].notna()].copy()
                    chunk["comtrs"] = chunk["comtrs"].str.strip().str.upper()
                    chunk = chunk[chunk["comtrs"].str.len() == 11]
                    if chunk.empty:
                        continue

                    # Numeric conversions
                    chunk["chem_code"] = pd.to_numeric(chunk.get("chem_code"), errors="coerce")
                    chunk["lbs_chm_used"] = pd.to_numeric(chunk.get("lbs_chm_used"), errors="coerce").fillna(0.0)
                    chunk["acre_treated"] = pd.to_numeric(chunk.get("acre_treated"), errors="coerce").fillna(0.0)
                    chunk["site_code"] = pd.to_numeric(chunk.get("site_code"), errors="coerce")

                    # Keep only ag sites (site_code < 65000)
                    chunk = chunk[chunk["site_code"].fillna(99999) < 65000]
                    if chunk.empty:
                        continue

                    # Resolve chemname: use column if present, else join from chem_map
                    if "chemname" in chunk.columns:
                        chunk["chemname_lc"] = chunk["chemname"].fillna("").str.strip().str.lower()
                    else:
                        chunk["chemname_lc"] = chunk["chem_code"].map(
                            lambda c: chem_map.get(int(c), "") if pd.notna(c) else ""
                        )

                    chunk = chunk[chunk["chemname_lc"].isin(tox_lookup)].copy()
                    if chunk.empty:
                        continue

                    # Resolve site_name: use column if present, else join from site_map
                    if "site_name" not in chunk.columns:
                        chunk["site_name"] = chunk["site_code"].map(
                            lambda c: site_map.get(int(c), "") if pd.notna(c) else ""
                        )

                    # Canonical chemname (title-cased from lookup key)
                    chunk["chemname"] = chunk["chemname_lc"]

                    # Attach class and toxicity values
                    chunk["chem_class"] = chunk["chemname_lc"].map(lambda n: tox_lookup[n]["chem_class"])
                    chunk["avian_ld50"] = chunk["chemname_lc"].map(lambda n: tox_lookup[n]["avian_ld50"])
                    chunk["avian_ceiling"] = chunk["chemname_lc"].map(lambda n: tox_lookup[n]["avian_ceiling"])
                    chunk["aquatic_lc50"] = chunk["chemname_lc"].map(lambda n: tox_lookup[n]["aquatic_lc50"])
                    chunk["aquatic_ceiling"] = chunk["chemname_lc"].map(lambda n: tox_lookup[n]["aquatic_ceiling"])

                    chunk["year"] = year
                    chunk["section_key"] = chunk["comtrs"].str[2:]
                    chunk["county_cd"] = chunk["comtrs"].str[:2]
                    chunk["applic_dt"] = chunk.get("applic_dt", pd.Series(dtype=str)).apply(
                        lambda x: _parse_date(str(x)) if pd.notna(x) else None
                    )

                    frames.append(chunk[[
                        "year", "comtrs", "section_key", "county_cd",
                        "chem_code", "chemname", "chem_class",
                        "lbs_chm_used", "acre_treated",
                        "applic_dt", "site_code", "site_name", "aer_gnd_ind",
                        "avian_ld50", "avian_ceiling", "aquatic_lc50", "aquatic_ceiling",
                    ]].copy())

            if i % 10 == 0 or i == len(udc_files):
                print(f"\r    {i}/{len(udc_files)} counties", end="", flush=True)

    print()
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"lbs_chm_used": "lbs_ai", "acre_treated": "acres_treated"})
    df["id"] = range(len(df))
    return df


# ---------------------------------------------------------------------------
# DUCKDB LOAD
# ---------------------------------------------------------------------------

def load_into_duckdb(df: pd.DataFrame) -> None:
    """Append records to the pur_records table in DuckDB."""
    if not DB_PATH.exists():
        print(f"  DuckDB not found at {DB_PATH}; skipping DB load")
        print("  Run spatial_setup.py first to initialize the database.")
        return

    con = duckdb.connect(str(DB_PATH))
    con.execute("LOAD spatial;")

    # Append via Parquet round-trip (fast for large DataFrames)
    tmp = OUTPUT_DIR / "_tmp_pur_load.parquet"
    df.to_parquet(tmp, index=False)
    # Explicit column list avoids positional mismatch between Parquet and table schema
    con.execute(f"""
        INSERT INTO pur_records
        SELECT id, year, comtrs, section_key, county_cd,
               chem_code::INTEGER, chemname, chem_class,
               lbs_ai::DOUBLE, acres_treated::DOUBLE,
               TRY_CAST(applic_dt AS DATE),
               site_code::INTEGER, site_name, aer_gnd_ind,
               avian_ld50::DOUBLE, avian_ceiling::BOOLEAN,
               aquatic_lc50::DOUBLE, aquatic_ceiling::BOOLEAN
        FROM read_parquet('{tmp}')
    """)
    n = con.execute("SELECT COUNT(*) FROM pur_records").fetchone()[0]
    con.close()
    tmp.unlink(missing_ok=True)
    print(f"  DuckDB: pur_records now has {n:,} rows")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Load PUR archives into Parquet + DuckDB")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS_DEFAULT)
    parser.add_argument("--no-db", action="store_true",
                        help="Skip DuckDB load (write Parquet only)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not TOXICITY_CSV.exists():
        raise FileNotFoundError(f"Toxicity lookup not found: {TOXICITY_CSV}")
    tox_lookup = load_toxicity_lookup()
    print(f"Toxicity lookup: {len(tox_lookup)} chemicals")

    all_frames: list[pd.DataFrame] = []
    for year in args.years:
        zip_path = PUR_CACHE_DIR / f"pur{year}.zip"
        if not zip_path.exists():
            print(f"  [{year}] not cached — skipping ({zip_path})")
            continue
        chem_map = load_chem_lookup(zip_path)
        site_map = load_site_lookup(zip_path)
        df = stream_year(zip_path, year, tox_lookup, chem_map, site_map)
        if df.empty:
            print(f"  [{year}] no matching records")
            continue
        lbs = df["lbs_ai"].sum()
        print(f"  [{year}] {len(df):,} records, {lbs:,.0f} lbs AI total")
        all_frames.append(df)

    if not all_frames:
        print("No data loaded.")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    combined["id"] = range(len(combined))

    out_parquet = OUTPUT_DIR / "pur_sections.parquet"
    combined.to_parquet(out_parquet, index=False)
    print(f"\n{len(combined):,} records → {out_parquet}")

    # Validation summary: year × class totals
    summary = (
        combined.groupby(["year", "chem_class"])[["lbs_ai", "acres_treated"]]
        .sum()
        .round(1)
        .reset_index()
    )
    summary_path = OUTPUT_DIR / "pur_loader_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Summary → {summary_path}")

    # Print pivot for quick review
    pivot = summary.pivot_table(index="year", columns="chem_class", values="lbs_ai", aggfunc="sum")
    print("\nLbs AI by year × class:")
    print(pivot.fillna(0).round(0).to_string())

    if not args.no_db:
        print("\nLoading into DuckDB ...")
        # Reset and reload (handles re-runs cleanly)
        if DB_PATH.exists():
            con = duckdb.connect(str(DB_PATH))
            con.execute("DELETE FROM pur_records")
            con.close()
        load_into_duckdb(combined)


if __name__ == "__main__":
    main()
