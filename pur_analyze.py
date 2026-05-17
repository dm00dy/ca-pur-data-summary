#!/usr/bin/env python3
"""
PUR Substitution Analysis
=========================

Downloads California Department of Pesticide Regulation (CDPR) Pesticide Use
Report (PUR) annual archives, aggregates agricultural insecticide use by
chemical class and year, and produces summary tables and charts to assess
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
    python pur_analyze.py

Outputs (in OUTPUT_DIR):
    chemical_lookup.csv              - resolved chem_code -> class mapping
    pur_yearly_lbs_by_class.csv      - long-format summary, pounds applied
    pur_yearly_acres_by_class.csv    - long-format summary, acres treated
    pur_yearly_tox_avian_by_class.csv   - avian-LD50-weighted toxicity units
    pur_yearly_tox_aquatic_by_class.csv - aquatic-LC50-weighted toxicity units
    pur_chart_lbs.png                - stacked area chart, pounds
    pur_chart_acres.png              - stacked area chart, acres
    pur_chart_toxicity_avian.png     - stacked area chart, avian-weighted
    pur_chart_toxicity_aquatic.png   - stacked area chart, aquatic-weighted

Toxicity reference:
    Avian endpoint: acute oral LD50 (mg/kg), Bobwhite preferred
    Aquatic endpoint: Daphnia magna 48h EC50 (µg/L)
    Source: Hertfordshire PPDB (primary), EPA ECOTOX (cross-check)
    Values stored in toxicity_lookup.csv alongside the script.

Author: Point Blue Conservation Science
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

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

def _load_toxicity_csv() -> tuple[dict[str, float], dict[str, float]]:
    """Load toxicity constants from toxicity_lookup.csv.

    Returns two dicts keyed by lowercase chemname:
        avian   — acute oral LD50 (mg/kg)
        aquatic — Daphnia magna 48h EC50 (µg/L)

    Reads by column index rather than pd.read_csv because the notes column
    (col 10+) contains unquoted commas that confuse the CSV parser.
    """
    csv_path = Path(__file__).parent / "toxicity_lookup.csv"
    if not csv_path.exists():
        sys.exit(f"ERROR: toxicity_lookup.csv not found at {csv_path}")

    avian: dict[str, float] = {}
    aquatic: dict[str, float] = {}
    with open(csv_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue  # header
            parts = line.rstrip("\n\r").split(",")
            if len(parts) < 7:
                continue
            # col 0: chemname, col 2: avian_ld50_mg_per_kg, col 6: aquatic_lc50_ug_per_l
            try:
                avian[parts[0].strip().lower()] = float(parts[2])
                aquatic[parts[0].strip().lower()] = float(parts[6])
            except ValueError:
                pass
    return avian, aquatic


def load_chemical_lookup(zip_path: Path) -> pd.DataFrame:
    """Load chemical.txt from a PUR archive. Returns DataFrame with chem_code + chemname."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith("chemical.txt")]
        if not names:
            sys.exit(f"ERROR: chemical.txt not found in {zip_path}")
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, encoding="latin-1", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    df["chem_code"] = pd.to_numeric(df["chem_code"], errors="coerce").astype("Int64")
    df["chemname"] = df["chemname"].str.strip().str.lower()
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


def aggregate_year(
    zip_path: Path,
    year: int,
    code_to_class: dict[int, str],
    ag_site_codes: set[int] | None,
    code_to_avian: dict[int, float] | None = None,
    code_to_aquatic: dict[int, float] | None = None,
) -> pd.DataFrame:
    """Stream all udc*.txt files in the year archive, filter to chemicals of
    interest, aggregate by class. Returns a DataFrame with one row per class.

    Toxicity units = lbs_ai / toxicity_value (avian: LD50 mg/kg; aquatic: LC50 µg/L).
    A larger toxicity unit value means greater hazard load.
    """

    classes = sorted(set(code_to_class.values()))
    accumulator: dict[str, dict[str, float]] = {
        cls: {"lbs": 0.0, "acres": 0.0, "tox_avian": 0.0, "tox_aquatic": 0.0, "n_records": 0}
        for cls in classes
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
                        lbs = float(sub["lbs_chm_used"].sum())
                        accumulator[cls]["lbs"] += lbs
                        accumulator[cls]["acres"] += float(sub["acre_treated"].sum())
                        accumulator[cls]["n_records"] += int(len(sub))

                        if code_to_avian:
                            av = code_to_avian.get(int(code))
                            if av:
                                accumulator[cls]["tox_avian"] += lbs / av

                        if code_to_aquatic:
                            aq = code_to_aquatic.get(int(code))
                            if aq:
                                accumulator[cls]["tox_aquatic"] += lbs / aq

            if i % 10 == 0 or i == len(udc_names):
                print(f"      processed {i}/{len(udc_names)} county files")

    rows = [
        {
            "year": year,
            "class": cls,
            "lbs_ai": vals["lbs"],
            "acres_treated": vals["acres"],
            "tox_units_avian": vals["tox_avian"],
            "tox_units_aquatic": vals["tox_aquatic"],
            "n_records": vals["n_records"],
        }
        for cls, vals in accumulator.items()
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------

def make_chart(
    summary: pd.DataFrame,
    value_col: str,
    ylabel: str,
    title: str,
    out_path: Path,
    scale: float = 1.0,
    vline_x: float = 2018.5,
    vline_label: str = "2019 chlorpyrifos phase-out",
) -> None:
    """Two-panel chart: absolute metric by class (stacked area), and proportional
    composition (stacked area, normalized to 100%)."""

    pivot = summary.pivot_table(index="year", columns="class", values=value_col, aggfunc="sum").fillna(0.0)
    pivot = pivot.sort_index()

    # Order classes for consistent stacking; biggest at bottom
    order = pivot.sum().sort_values(ascending=False).index.tolist()
    pivot = pivot[order]

    fig, axes = plt.subplots(2, 1, figsize=(11, 9), sharex=True)

    # Panel 1: absolute values
    ax = axes[0]
    ax.stackplot(pivot.index, pivot.T.values * scale, labels=pivot.columns, alpha=0.85)
    ax.axvline(vline_x, color="black", linestyle="--", linewidth=1, alpha=0.6)
    ax.text(vline_x + 0.05, ax.get_ylim()[1] * 0.95, vline_label,
            fontsize=9, va="top", ha="left", alpha=0.7)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    # Panel 2: proportional composition
    row_totals = pivot.sum(axis=1)
    prop = pivot.div(row_totals, axis=0).fillna(0.0) * 100
    ax = axes[1]
    ax.stackplot(prop.index, prop.T.values, labels=prop.columns, alpha=0.85)
    ax.axvline(vline_x, color="black", linestyle="--", linewidth=1, alpha=0.6)
    ax.set_ylabel(f"% of total {ylabel.split()[0].lower()}")
    ax.set_xlabel("Year")
    ax.set_title("Compositional shift")
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
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

    # Step 2b: load toxicity constants and build chem_code → value maps
    print("\nStep 2b: load toxicity reference values")
    avian_by_name, aquatic_by_name = _load_toxicity_csv()
    code_to_avian: dict[int, float] = {}
    code_to_aquatic: dict[int, float] = {}
    for _, row in chem_lookup.iterrows():
        if pd.isna(row["chem_code"]) or pd.isna(row["chemname"]):
            continue
        c = int(row["chem_code"])
        nm = str(row["chemname"])
        if nm in avian_by_name:
            code_to_avian[c] = avian_by_name[nm]
        if nm in aquatic_by_name:
            code_to_aquatic[c] = aquatic_by_name[nm]
    print(f"  toxicity matched: {len(code_to_avian)} avian, {len(code_to_aquatic)} aquatic chem_codes")

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
        df = aggregate_year(zp, year, code_to_class, ag_site_codes, code_to_avian, code_to_aquatic)
        if not df.empty:
            yearly.append(df)
            total_lbs = df["lbs_ai"].sum()
            total_tox_aq = df["tox_units_aquatic"].sum()
            print(f"    lbs AI (tracked classes): {total_lbs:,.0f}  |  aquatic tox units: {total_tox_aq:.4f}")

    if not yearly:
        print("No data aggregated; aborting.")
        return 1

    summary = pd.concat(yearly, ignore_index=True)

    # Step 5: save per-metric CSVs
    print("\nStep 5: save CSVs")
    outputs = [
        ("lbs_ai",            "pur_yearly_lbs_by_class.csv"),
        ("acres_treated",     "pur_yearly_acres_by_class.csv"),
        ("tox_units_avian",   "pur_yearly_tox_avian_by_class.csv"),
        ("tox_units_aquatic", "pur_yearly_tox_aquatic_by_class.csv"),
    ]
    for col, fname in outputs:
        out = summary[["year", "class", col, "n_records"]].copy()
        out.to_csv(OUTPUT_DIR / fname, index=False)
        print(f"  -> {OUTPUT_DIR / fname}")

    # Step 6: charts
    print("\nStep 6: charts")
    make_chart(
        summary, "lbs_ai",
        ylabel="Million lbs AI applied",
        title="California agricultural insecticide use by chemical class",
        out_path=OUTPUT_DIR / "pur_chart_lbs.png",
        scale=1e-6,
    )
    make_chart(
        summary, "acres_treated",
        ylabel="Million acres treated",
        title="California agricultural insecticide treated area by chemical class",
        out_path=OUTPUT_DIR / "pur_chart_acres.png",
        scale=1e-6,
    )
    make_chart(
        summary, "tox_units_avian",
        ylabel="Avian toxicity units (lbs / LD50 mg kg⁻¹)",
        title="California agricultural insecticide avian toxicity load by class",
        out_path=OUTPUT_DIR / "pur_chart_toxicity_avian.png",
    )
    make_chart(
        summary, "tox_units_aquatic",
        ylabel="Aquatic toxicity units (lbs / LC50 µg L⁻¹)",
        title="California agricultural insecticide aquatic toxicity load by class",
        out_path=OUTPUT_DIR / "pur_chart_toxicity_aquatic.png",
    )

    # Step 7: tabular preview
    print("\nFinal pivot (lbs AI applied):")
    pivot = summary.pivot_table(index="year", columns="class", values="lbs_ai", aggfunc="sum").fillna(0.0)
    print(pivot.round(0).to_string())

    print("\nFinal pivot (aquatic toxicity units):")
    pivot_tox = summary.pivot_table(index="year", columns="class", values="tox_units_aquatic", aggfunc="sum").fillna(0.0)
    print(pivot_tox.round(4).to_string())

    return 0


if __name__ == "__main__":
    sys.exit(main())
