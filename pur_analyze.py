#!/usr/bin/env python3
"""
PUR Substitution Analysis
=========================

Downloads California Department of Pesticide Regulation (CDPR) Pesticide Use
Report (PUR) annual archives, aggregates agricultural insecticide use by
chemical class and year, and produces a summary table and chart to assess
whether California's 2020 neonicotinoid restrictions resulted in net reduction
or substitution to other chemical classes.

Source:
    https://files.cdpr.ca.gov/pub/outgoing/pur_archives/pur{YEAR}.zip

PUR archive structure (each year):
    chemical.txt              - chemical lookup (chem_code -> name)
    product.txt               - product lookup
    site.txt                  - site/crop lookup
    udc{cc}_{yy}.txt          - Use Data Chemical files, one per county

UDC file fields of interest (comma-delimited, latin-1 encoding):
    use_no, prodno, chem_code, lbs_chm_used, amt_prd_used, unit_of_meas,
    acre_treated, unit_treated, applic_dt, applic_time, county_cd, base_ln_mer,
    township, tship_dir, range, range_dir, section, site_loc_id, grower_id,
    license_no, planting_seq, applic_cnt, aer_gnd_ind, site_code, qualify_cd,
    batch_no, document_no, summary_cd, record_id, comtrs, error_flag

Usage:
    pip install pandas requests matplotlib
    python pur_substitution_analysis.py

Outputs (in OUTPUT_DIR):
    chemical_lookup.csv         - resolved chem_code -> class mapping
    pur_yearly_by_class.csv     - long-format summary
    pur_substitution_chart.png  - stacked area / line chart

Author: Point Blue Conservation Science
"""

from __future__ import annotations

import io
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

YEARS: list[int] = list(range(2015, 2024))  # 2015–2023; add 2024 when published
OUTPUT_DIR = Path("./pur_analysis")
CACHE_DIR = OUTPUT_DIR / "cache"
BASE_URL = "https://files.cdpr.ca.gov/pub/outgoing/pur_archives"

# Restrict to agricultural use only. PUR's `record_id` field encodes ag vs nonag,
# but the most reliable filter is the site_code -> ag flag in site.txt. For a
# first-pass analysis we accept all records and rely on site filtering later if
# needed. This keeps the script simple; tighten if numbers look suspicious.
AG_ONLY = True  # set False to include all records

# Chemical class definitions. Names are matched case-insensitively against the
# `chemname` field in chemical.txt. Add or edit freely — the script will report
# any names it can't resolve.
CHEMICAL_CLASSES: dict[str, list[str]] = {
    "Restricted neonics": [
        "imidacloprid",
        "clothianidin",
        "thiamethoxam",
        "dinotefuran",
    ],
    "Other neonics": [
        "acetamiprid",
        "thiacloprid",
        "nitenpyram",
    ],
    "Next-gen systemics": [
        "sulfoxaflor",
        "flupyradifurone",
    ],
    "Diamides": [
        "chlorantraniliprole",
        "cyantraniliprole",
        "flubendiamide",
        "tetraniliprole",
    ],
    "Pyrethroids": [
        "lambda-cyhalothrin",
        "gamma-cyhalothrin",
        "bifenthrin",
        "esfenvalerate",
        "permethrin",
        "cypermethrin",
        "zeta-cypermethrin",
        "cyfluthrin",
        "beta-cyfluthrin",
        "deltamethrin",
        "fenpropathrin",
        "tau-fluvalinate",
        "tralomethrin",
    ],
    "Organophosphates": [
        "chlorpyrifos",
        "malathion",
        "diazinon",
        "dimethoate",
        "acephate",
        "phosmet",
        "methidathion",
        "naled",
        "oxydemeton-methyl",
        "phorate",
        "azinphos-methyl",
    ],
    "Carbamates": [
        "carbaryl",
        "methomyl",
        "oxamyl",
        "carbofuran",
        "aldicarb",
    ],
    "Spinosyns": [
        "spinosad",
        "spinetoram",
    ],
}


# ---------------------------------------------------------------------------
# DOWNLOAD AND CACHE
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def download_year(year: int) -> Path:
    """Download pur{year}.zip if not already cached. Returns local path."""
    url = f"{BASE_URL}/pur{year}.zip"
    local = CACHE_DIR / f"pur{year}.zip"
    if local.exists() and local.stat().st_size > 0:
        print(f"  [{year}] cached at {local} ({local.stat().st_size / 1e6:.1f} MB)")
        return local

    print(f"  [{year}] downloading {url} ...")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(local, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = 100 * downloaded / total
                    print(f"\r    {downloaded / 1e6:6.1f} / {total / 1e6:6.1f} MB ({pct:5.1f}%)", end="")
        print()
    return local


# ---------------------------------------------------------------------------
# LOOKUP TABLES
# ---------------------------------------------------------------------------

def load_chemical_lookup(zip_path: Path) -> pd.DataFrame:
    """Load chemical.txt from a PUR archive. Returns DataFrame with columns
    [chem_code, chemname]."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith("chemical.txt")]
        if not names:
            raise FileNotFoundError(f"chemical.txt not found in {zip_path}")
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, encoding="latin-1", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    df["chem_code"] = pd.to_numeric(df["chem_code"], errors="coerce").astype("Int64")
    df["chemname"] = df["chemname"].fillna("").str.strip()
    return df[["chem_code", "chemname"]].dropna(subset=["chem_code"])


def load_site_lookup(zip_path: Path) -> pd.DataFrame:
    """Load site.txt and return ag-flagged site codes if available."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith("site.txt")]
        if not names:
            return pd.DataFrame(columns=["site_code", "site_name"])
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, encoding="latin-1", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    df["site_code"] = pd.to_numeric(df["site_code"], errors="coerce").astype("Int64")
    return df


def resolve_chem_classes(chem_lookup: pd.DataFrame) -> tuple[dict[int, str], list[str]]:
    """Map chem_code -> class name. Returns (mapping, unresolved_names)."""
    name_to_code: dict[str, int] = {}
    for _, row in chem_lookup.iterrows():
        nm = row["chemname"].lower().strip()
        if nm and pd.notna(row["chem_code"]):
            # First-occurrence wins; PUR sometimes lists multiple chem_codes per
            # name due to formulation variants. Worth verifying for production.
            name_to_code.setdefault(nm, int(row["chem_code"]))

    code_to_class: dict[int, str] = {}
    unresolved: list[str] = []
    for cls, names in CHEMICAL_CLASSES.items():
        for n in names:
            code = name_to_code.get(n.lower())
            if code is None:
                # Try fuzzy: name contained in chemname
                matches = [c for nm, c in name_to_code.items() if n.lower() in nm]
                if len(matches) == 1:
                    code = matches[0]
            if code is None:
                unresolved.append(f"{cls}: {n}")
            else:
                code_to_class[code] = cls
    return code_to_class, unresolved


# ---------------------------------------------------------------------------
# UDC AGGREGATION
# ---------------------------------------------------------------------------

UDC_USECOLS = ["chem_code", "lbs_chm_used", "acre_treated", "site_code"]
UDC_DTYPES = {
    "chem_code": "string",
    "lbs_chm_used": "string",
    "acre_treated": "string",
    "site_code": "string",
}


def aggregate_year(zip_path: Path, year: int, code_to_class: dict[int, str],
                   ag_site_codes: set[int] | None) -> pd.DataFrame:
    """Stream all udc*.txt files in the year archive, filter to chemicals of
    interest, aggregate by class. Returns a DataFrame with one row per class."""

    classes = sorted(set(code_to_class.values()))
    accumulator: dict[str, dict[str, float]] = {
        cls: {"lbs": 0.0, "acres": 0.0, "n_records": 0} for cls in classes
    }
    target_codes = set(code_to_class.keys())

    with zipfile.ZipFile(zip_path) as zf:
        udc_names = [n for n in zf.namelist()
                     if Path(n).name.lower().startswith("udc") and n.lower().endswith(".txt")]
        if not udc_names:
            print(f"    [{year}] WARNING: no udc*.txt files found")
            return pd.DataFrame()

        print(f"    [{year}] {len(udc_names)} county files")

        for i, name in enumerate(udc_names, 1):
            with zf.open(name) as f:
                # Stream in chunks; keep memory bounded
                try:
                    reader = pd.read_csv(
                        f,
                        encoding="latin-1",
                        usecols=lambda c: c.strip().lower() in UDC_USECOLS,
                        dtype=str,
                        chunksize=200_000,
                        low_memory=False,
                        on_bad_lines="skip",
                    )
                except ValueError as e:
                    print(f"      {Path(name).name}: skipped ({e})")
                    continue

                for chunk in reader:
                    chunk.columns = [c.strip().lower() for c in chunk.columns]
                    if "chem_code" not in chunk.columns:
                        continue

                    chunk["chem_code"] = pd.to_numeric(chunk["chem_code"], errors="coerce")
                    chunk = chunk[chunk["chem_code"].isin(target_codes)]
                    if chunk.empty:
                        continue

                    if ag_site_codes is not None and "site_code" in chunk.columns:
                        chunk["site_code"] = pd.to_numeric(chunk["site_code"], errors="coerce")
                        chunk = chunk[chunk["site_code"].isin(ag_site_codes)]
                        if chunk.empty:
                            continue

                    chunk["lbs_chm_used"] = pd.to_numeric(chunk.get("lbs_chm_used"), errors="coerce").fillna(0.0)
                    chunk["acre_treated"] = pd.to_numeric(chunk.get("acre_treated"), errors="coerce").fillna(0.0)

                    for code, sub in chunk.groupby("chem_code"):
                        cls = code_to_class.get(int(code))
                        if cls is None:
                            continue
                        accumulator[cls]["lbs"] += float(sub["lbs_chm_used"].sum())
                        accumulator[cls]["acres"] += float(sub["acre_treated"].sum())
                        accumulator[cls]["n_records"] += int(len(sub))

            if i % 10 == 0 or i == len(udc_names):
                print(f"      processed {i}/{len(udc_names)} county files")

    rows = [
        {"year": year, "class": cls,
         "lbs_ai": vals["lbs"], "acres_treated": vals["acres"],
         "n_records": vals["n_records"]}
        for cls, vals in accumulator.items()
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------

def make_chart(summary: pd.DataFrame, out_path: Path) -> None:
    """Two-panel chart: absolute lbs by class (stacked area), and proportional
    composition (stacked area, normalized)."""

    pivot = summary.pivot_table(index="year", columns="class", values="lbs_ai", aggfunc="sum").fillna(0.0)
    pivot = pivot.sort_index()

    # Order classes for consistent stacking; biggest at bottom
    order = pivot.sum().sort_values(ascending=False).index.tolist()
    pivot = pivot[order]

    fig, axes = plt.subplots(2, 1, figsize=(11, 9), sharex=True)

    # Panel 1: absolute lbs
    ax = axes[0]
    ax.stackplot(pivot.index, pivot.T.values / 1e6, labels=pivot.columns, alpha=0.85)
    ax.axvline(2018.5, color="black", linestyle="--", linewidth=1, alpha=0.6)
    ax.text(2018.55, ax.get_ylim()[1] * 0.95, "2019 chlorpyrifos phase-out",
            fontsize=9, va="top", ha="left", alpha=0.7)
    ax.set_ylabel("Million lbs AI applied")
    ax.set_title("California agricultural insecticide use by chemical class")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    # Panel 2: proportional
    prop = pivot.div(pivot.sum(axis=1), axis=0) * 100
    ax = axes[1]
    ax.stackplot(prop.index, prop.T.values, labels=prop.columns, alpha=0.85)
    ax.axvline(2018.5, color="black", linestyle="--", linewidth=1, alpha=0.6)
    ax.set_ylabel("% of total tracked insecticide lbs")
    ax.set_xlabel("Year")
    ax.set_title("Compositional shift")
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"  chart -> {out_path}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    ensure_dirs()

    print(f"PUR substitution analysis: years {YEARS[0]}–{YEARS[-1]}")
    print(f"Output: {OUTPUT_DIR.resolve()}\n")

    # Step 1: download all year archives
    print("Step 1: download archives")
    zip_paths: dict[int, Path] = {}
    for year in YEARS:
        try:
            zip_paths[year] = download_year(year)
        except Exception as e:
            print(f"  [{year}] FAILED: {e}")

    if not zip_paths:
        print("No archives downloaded; aborting.")
        return 1

    # Step 2: resolve chemical classes from the most recent year's lookup
    # (chemical.txt is largely stable but use the latest available)
    print("\nStep 2: resolve chemical classes")
    latest_year = max(zip_paths.keys())
    chem_lookup = load_chemical_lookup(zip_paths[latest_year])
    code_to_class, unresolved = resolve_chem_classes(chem_lookup)
    print(f"  resolved {len(code_to_class)} chem_codes across {len(set(code_to_class.values()))} classes")
    if unresolved:
        print(f"  WARNING: {len(unresolved)} chemicals could not be resolved:")
        for u in unresolved:
            print(f"    - {u}")

    # Persist the resolved mapping for inspection
    mapping_df = pd.DataFrame([
        {"chem_code": code, "chemname": chem_lookup.set_index("chem_code")["chemname"].get(code, ""),
         "class": cls}
        for code, cls in sorted(code_to_class.items())
    ])
    mapping_df.to_csv(OUTPUT_DIR / "chemical_lookup.csv", index=False)
    print(f"  mapping -> {OUTPUT_DIR / 'chemical_lookup.csv'}")

    # Step 3: build ag site filter if requested
    ag_site_codes: set[int] | None = None
    if AG_ONLY:
        print("\nStep 3: build ag site filter")
        site_df = load_site_lookup(zip_paths[latest_year])
        # PUR sites with codes < 65000 are typically agricultural commodities;
        # sites 65000+ are non-ag (structural, ROW, etc.). This is a coarse
        # heuristic — refine with site.txt's ag flag if present.
        if not site_df.empty:
            ag_site_codes = set(site_df.loc[site_df["site_code"] < 65000, "site_code"].dropna().astype(int))
            print(f"  ag site codes: {len(ag_site_codes)}")
        else:
            print("  no site.txt found; falling back to all records")

    # Step 4: aggregate each year
    print("\nStep 4: aggregate UDC data")
    yearly: list[pd.DataFrame] = []
    for year, zp in sorted(zip_paths.items()):
        print(f"  [{year}] aggregating ...")
        df = aggregate_year(zp, year, code_to_class, ag_site_codes)
        if not df.empty:
            yearly.append(df)
            total_lbs = df["lbs_ai"].sum()
            print(f"    total lbs AI (tracked classes): {total_lbs:,.0f}")

    if not yearly:
        print("No data aggregated; aborting.")
        return 1

    summary = pd.concat(yearly, ignore_index=True)
    summary_path = OUTPUT_DIR / "pur_yearly_by_class.csv"
    summary.to_csv(summary_path, index=False)
    print(f"\n  summary -> {summary_path}")

    # Step 5: chart
    print("\nStep 5: chart")
    make_chart(summary, OUTPUT_DIR / "pur_substitution_chart.png")

    # Step 6: tabular preview
    print("\nFinal pivot (lbs AI applied):")
    pivot = summary.pivot_table(index="year", columns="class", values="lbs_ai", aggfunc="sum").fillna(0.0)
    print(pivot.round(0).to_string())

    return 0


if __name__ == "__main__":
    sys.exit(main())
