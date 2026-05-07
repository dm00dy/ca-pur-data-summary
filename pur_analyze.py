#!/usr/bin/env python3
"""
PUR Substitution Analysis (v2)
==============================

Downloads California Department of Pesticide Regulation (CDPR) Pesticide Use
Report (PUR) annual archives, aggregates agricultural insecticide use by
chemical class and year, and produces summary tables and charts to assess
California's post-2020 regulatory landscape.

v2 changes:
- Added acres_treated as a co-equal output alongside lbs_ai
- Toxicity weighting via avian acute oral LD50 and Daphnia magna 48h EC50;
  values sourced from Hertfordshire PPDB and EPA ECOTOX — see
  toxicity_lookup.csv for per-chemical citations and species
- Aquatic invertebrate toxicity weighting (more relevant for aerial
  insectivore prey-base question than direct avian toxicity)
- Four chart sets: lbs, acres, avian-tox-weighted, aquatic-tox-weighted
- Summary tables written for each metric

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
    chemical_lookup.csv               - resolved chem_code -> class mapping
    pur_yearly_lbs_by_class.csv       - long-format summary, lbs AI
    pur_yearly_acres_by_class.csv     - long-format summary, acres treated
    pur_yearly_tox_avian_by_class.csv - long-format summary, avian-LD50-weighted
    pur_yearly_tox_aquatic_by_class.csv - long-format summary, Daphnia-LC50-weighted
    pur_chart_lbs.png                 - stacked area chart, lbs
    pur_chart_acres.png               - stacked area chart, acres treated
    pur_chart_toxicity_avian.png      - stacked area chart, avian-tox-weighted
    pur_chart_toxicity_aquatic.png    - stacked area chart, aquatic-invert-tox-weighted

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

# Restrict to agricultural use only.
AG_ONLY = True

# Toggle toxicity-weighted output. Values sourced from Hertfordshire PPDB and
# EPA ECOTOX; see toxicity_lookup.csv for per-chemical citations and species.
TOXICITY_WEIGHTING = True

# Chemical class definitions.
CHEMICAL_CLASSES: dict[str, list[str]] = {
    "Restricted neonics": [
        "imidacloprid", "clothianidin", "thiamethoxam", "dinotefuran",
    ],
    "Other neonics": [
        "acetamiprid", "thiacloprid", "nitenpyram",
    ],
    "Next-gen systemics": [
        "sulfoxaflor", "flupyradifurone",
    ],
    "Diamides": [
        "chlorantraniliprole", "cyantraniliprole", "flubendiamide", "tetraniliprole",
    ],
    "Pyrethroids": [
        "lambda-cyhalothrin", "gamma-cyhalothrin", "bifenthrin", "esfenvalerate",
        "permethrin", "cypermethrin", "zeta-cypermethrin", "cyfluthrin",
        "beta-cyfluthrin", "deltamethrin", "fenpropathrin", "tau-fluvalinate",
        "tralomethrin",
    ],
    "Organophosphates": [
        "chlorpyrifos", "malathion", "diazinon", "dimethoate", "acephate",
        "phosmet", "methidathion", "naled", "oxydemeton-methyl", "phorate",
        "azinphos-methyl",
    ],
    "Carbamates": [
        "carbaryl", "methomyl", "oxamyl", "carbofuran", "aldicarb",
    ],
    "Spinosyns": [
        "spinosad", "spinetoram",
    ],
}


# ---------------------------------------------------------------------------
# TOXICITY REFERENCE TABLES — sourced from Hertfordshire PPDB and EPA ECOTOX
# ---------------------------------------------------------------------------
# Per-chemical citations, test species, ceiling flags, and data-quality notes
# are in toxicity_lookup.csv alongside this script.
#
# IMPORTANT INTERPRETATION CAVEAT
# --------------------------------
# Avian oral LD50 measures direct toxicity to birds via ingestion of the
# chemical. For aerial insectivores (birds AND bats), the dominant exposure
# pathway is via the prey base — flying insects whose populations are affected
# by these chemicals. For that question, aquatic invertebrate toxicity (Daphnia
# magna EC50) is more directly relevant, especially for pyrethroids which have
# very low avian toxicity but extreme aquatic invertebrate toxicity.
#
# The bird LD50 weighting is therefore best read as a direct-mortality proxy.
# Prey-base disruption is better captured by the Daphnia EC50 weighting.
#
# Lower LD50/EC50 = more toxic per unit mass/concentration.
# Ceiling values (">N") are stored as N — conservative floor; actual toxicity
# is at least that low.
# Class-level medians are used as fallback for any chemical not in the CSV
# (see build_toxicity_lookup).

def _load_toxicity_csv() -> tuple[dict[str, float], dict[str, float]]:
    # Schema: chemname(0),class(1),avian_ld50(2),avian_ceiling(3),avian_species(4),
    #         avian_url(5),aquatic_lc50(6),aquatic_ceiling(7),aquatic_species(8),
    #         aquatic_url(9),notes(10+)
    # The notes field often contains unquoted commas so we read by column index.
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
            try:
                avian[parts[0]] = float(parts[2])
                aquatic[parts[0]] = float(parts[6])
            except ValueError:
                pass
    return avian, aquatic


AVIAN_LD50_MG_PER_KG, AQUATIC_LC50_UG_PER_L = _load_toxicity_csv()


# ---------------------------------------------------------------------------
# DOWNLOAD AND CACHE
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def download_year(year: int) -> Path:
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
            for chunk in r.iter_content(chunk_size=1 << 20):
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
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith("site.txt")]
        if not names:
            return pd.DataFrame(columns=["site_code", "site_name"])
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, encoding="latin-1", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    df["site_code"] = pd.to_numeric(df["site_code"], errors="coerce").astype("Int64")
    return df


def resolve_chem_classes(chem_lookup: pd.DataFrame) -> tuple[
    dict[int, str],            # code -> class
    dict[int, str],            # code -> chemical name (lowercase, normalized)
    list[str],                 # unresolved class:chemical entries
]:
    name_to_code: dict[str, int] = {}
    for _, row in chem_lookup.iterrows():
        nm = row["chemname"].lower().strip()
        if nm and pd.notna(row["chem_code"]):
            name_to_code.setdefault(nm, int(row["chem_code"]))

    code_to_class: dict[int, str] = {}
    code_to_name: dict[int, str] = {}
    unresolved: list[str] = []
    for cls, names in CHEMICAL_CLASSES.items():
        for n in names:
            n_lower = n.lower()
            code = name_to_code.get(n_lower)
            if code is None:
                matches = [c for nm, c in name_to_code.items() if n_lower in nm]
                if len(matches) == 1:
                    code = matches[0]
            if code is None:
                unresolved.append(f"{cls}: {n}")
            else:
                code_to_class[code] = cls
                code_to_name[code] = n_lower
    return code_to_class, code_to_name, unresolved


def build_toxicity_lookup(code_to_name: dict[int, str],
                          code_to_class: dict[int, str],
                          reference: dict[str, float],
                          label: str) -> dict[int, float]:
    """Build chem_code -> toxicity reference value. For codes without an
    explicit value, use the median of in-class entries that do have one.
    Returns empty dict if toxicity weighting disabled."""
    lookup: dict[int, float] = {}
    if not TOXICITY_WEIGHTING:
        return lookup

    class_values: dict[str, list[float]] = {}
    for code, name in code_to_name.items():
        val = reference.get(name)
        if val is not None:
            cls = code_to_class[code]
            class_values.setdefault(cls, []).append(val)
    class_medians = {
        cls: float(pd.Series(vals).median()) for cls, vals in class_values.items()
    }

    missing = []
    for code, name in code_to_name.items():
        val = reference.get(name)
        if val is None:
            cls = code_to_class[code]
            val = class_medians.get(cls)
            if val is None:
                missing.append(f"{cls}: {name}")
                continue
        lookup[code] = val

    if missing:
        print(f"  WARNING [{label}]: no value (chemical or class median) for {len(missing)} codes:")
        for m in missing:
            print(f"    - {m}")
    return lookup


# ---------------------------------------------------------------------------
# UDC AGGREGATION
# ---------------------------------------------------------------------------

UDC_USECOLS = ["chem_code", "lbs_chm_used", "acre_treated", "site_code"]


def aggregate_year(zip_path: Path, year: int,
                   code_to_class: dict[int, str],
                   code_to_name: dict[int, str],
                   tox_avian: dict[int, float],
                   tox_aquatic: dict[int, float],
                   ag_site_codes: set[int] | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (class_df, chem_df).

    class_df: one row per (year, class) with sums of lbs, acres, records,
    and toxicity-weighted lbs for both avian and aquatic endpoints.
    chem_df: one row per (year, chemname) for Carbamates only, with lbs
    and avian toxicity units — for per-chemical carbamate breakdown."""

    classes = sorted(set(code_to_class.values()))
    accumulator: dict[str, dict[str, float]] = {
        cls: {"lbs": 0.0, "acres": 0.0,
              "tox_avian": 0.0, "tox_aquatic": 0.0,
              "n_records": 0}
        for cls in classes
    }
    chem_accum: dict[str, dict[str, float]] = {}
    target_codes = set(code_to_class.keys())

    with zipfile.ZipFile(zip_path) as zf:
        udc_names = [n for n in zf.namelist()
                     if Path(n).name.lower().startswith("udc")
                     and n.lower().endswith(".txt")]
        if not udc_names:
            print(f"    [{year}] WARNING: no udc*.txt files found")
            return pd.DataFrame()

        print(f"    [{year}] {len(udc_names)} county files")

        for i, name in enumerate(udc_names, 1):
            with zf.open(name) as f:
                try:
                    reader = pd.read_csv(
                        f, encoding="latin-1",
                        usecols=lambda c: c.strip().lower() in UDC_USECOLS,
                        dtype=str, chunksize=200_000,
                        low_memory=False, on_bad_lines="skip",
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

                    chunk["lbs_chm_used"] = pd.to_numeric(chunk.get("lbs_chm_used"),
                                                          errors="coerce").fillna(0.0)
                    chunk["acre_treated"] = pd.to_numeric(chunk.get("acre_treated"),
                                                          errors="coerce").fillna(0.0)

                    for code, sub in chunk.groupby("chem_code"):
                        cls = code_to_class.get(int(code))
                        if cls is None:
                            continue
                        lbs = float(sub["lbs_chm_used"].sum())
                        accumulator[cls]["lbs"] += lbs
                        accumulator[cls]["acres"] += float(sub["acre_treated"].sum())
                        accumulator[cls]["n_records"] += int(len(sub))
                        avian_v = tox_avian.get(int(code))
                        if avian_v and avian_v > 0:
                            accumulator[cls]["tox_avian"] += lbs / avian_v
                        aquatic_v = tox_aquatic.get(int(code))
                        if aquatic_v and aquatic_v > 0:
                            accumulator[cls]["tox_aquatic"] += lbs / aquatic_v
                        if cls == "Carbamates":
                            name = code_to_name.get(int(code), str(int(code)))
                            entry = chem_accum.setdefault(name, {"lbs": 0.0, "tox_avian": 0.0})
                            entry["lbs"] += lbs
                            if avian_v and avian_v > 0:
                                entry["tox_avian"] += lbs / avian_v

            if i % 10 == 0 or i == len(udc_names):
                print(f"      processed {i}/{len(udc_names)} county files")

    rows = [
        {"year": year, "class": cls,
         "lbs_active_ingredient": vals["lbs"],
         "acres_treated": vals["acres"],
         "toxicity_units_avian_ld50": vals["tox_avian"],
         "toxicity_units_aquatic_lc50": vals["tox_aquatic"],
         "n_records": vals["n_records"]}
        for cls, vals in accumulator.items()
    ]
    chem_rows = [
        {"year": year, "chemname": name,
         "lbs_active_ingredient": vals["lbs"],
         "toxicity_units_avian_ld50": vals["tox_avian"]}
        for name, vals in chem_accum.items()
    ]
    return pd.DataFrame(rows), pd.DataFrame(chem_rows)


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------

CHART_TITLES = {
    "lbs_active_ingredient": ("California agricultural insecticide use by chemical class",
                              "Million lbs AI applied", 1e6),
    "acres_treated": ("California agricultural insecticide application area by chemical class",
                      "Million acres treated", 1e6),
    "toxicity_units_avian_ld50": ("Avian-LD50-weighted insecticide load",
                                  "Toxicity units (lbs ÷ avian LD50)", 1.0),
    "toxicity_units_aquatic_lc50": ("Aquatic-invertebrate-LC50-weighted insecticide load",
                                    "Toxicity units (lbs ÷ Daphnia EC50)", 1.0),
    "carbamate_avian_by_chem": ("Carbamate avian-LD50-weighted load — per chemical",
                                "Toxicity units (lbs ÷ avian LD50)", 1.0),
    "carbamate_lbs_by_chem": ("Carbamate use by chemical (lbs AI)",
                              "Thousand lbs AI", 1e3),
}


def make_chart(summary: pd.DataFrame, value_col: str, out_path: Path,
               pivot_col: str = "class", title_key: str | None = None) -> None:
    title, ylabel, scale = CHART_TITLES[title_key or value_col]
    pivot = summary.pivot_table(index="year", columns=pivot_col,
                                values=value_col, aggfunc="sum").fillna(0.0).sort_index()
    if pivot.empty or pivot.sum().sum() == 0:
        print(f"  [skip] {value_col}: no data")
        return

    order = pivot.sum().sort_values(ascending=False).index.tolist()
    pivot = pivot[order]

    fig, axes = plt.subplots(2, 1, figsize=(11, 9), sharex=True)

    ax = axes[0]
    ax.stackplot(pivot.index, pivot.T.values / scale, labels=pivot.columns, alpha=0.85)
    ax.axvline(2020.5, color="black", linestyle="--", linewidth=1, alpha=0.6)
    # Add 15% headroom so the legend and the regulation annotation don't overlap
    cur_top = ax.get_ylim()[1]
    ax.set_ylim(0, cur_top * 1.15)
    # Pin annotation and legend to axes coordinates so they never collide
    ax.text(2020.6, 0.78, "2020 neonic\nrestrictions",
            transform=ax.get_xaxis_transform(),
            fontsize=9, va="top", ha="left", alpha=0.7)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0),
              fontsize=8, frameon=False)
    ax.grid(True, alpha=0.3)

    prop = pivot.div(pivot.sum(axis=1), axis=0) * 100
    ax = axes[1]
    ax.stackplot(prop.index, prop.T.values, labels=prop.columns, alpha=0.85)
    ax.axvline(2020.5, color="black", linestyle="--", linewidth=1, alpha=0.6)
    ax.set_ylabel(f"% of total ({value_col.replace('_', ' ')})")
    ax.set_xlabel("Year")
    ax.set_title("Compositional shift")
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  chart -> {out_path}")


def print_pivot(summary: pd.DataFrame, value_col: str, label: str,
                pivot_col: str = "class") -> None:
    pivot = summary.pivot_table(index="year", columns=pivot_col,
                                values=value_col, aggfunc="sum").fillna(0.0)
    if pivot.empty or pivot.sum().sum() == 0:
        return
    order = pivot.loc[pivot.index.min()].sort_values(ascending=False).index.tolist()
    pivot = pivot[order]
    print(f"\n{label}:")
    print(pivot.round(0).astype(int).to_string())


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    ensure_dirs()

    print(f"PUR analysis v2: years {YEARS[0]}–{YEARS[-1]}")
    print(f"Output: {OUTPUT_DIR.resolve()}")
    print(f"Toxicity weighting: {'ON (PPDB/ECOTOX sources)' if TOXICITY_WEIGHTING else 'OFF'}\n")

    # Step 1: download
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

    # Step 2: chemical class resolution
    print("\nStep 2: resolve chemical classes")
    latest_year = max(zip_paths.keys())
    chem_lookup = load_chemical_lookup(zip_paths[latest_year])
    code_to_class, code_to_name, unresolved = resolve_chem_classes(chem_lookup)
    print(f"  resolved {len(code_to_class)} chem_codes across {len(set(code_to_class.values()))} classes")
    if unresolved:
        print(f"  WARNING: {len(unresolved)} chemicals could not be resolved:")
        for u in unresolved:
            print(f"    - {u}")

    mapping_df = pd.DataFrame([
        {"chem_code": code,
         "chemname": chem_lookup.set_index("chem_code")["chemname"].get(code, ""),
         "class": cls,
         "ld50_mg_per_kg": AVIAN_LD50_MG_PER_KG.get(code_to_name[code], None)}
        for code, cls in sorted(code_to_class.items())
    ])
    mapping_df.to_csv(OUTPUT_DIR / "chemical_lookup.csv", index=False)
    print(f"  mapping -> {OUTPUT_DIR / 'chemical_lookup.csv'}")

    # Step 3: toxicity references (avian + aquatic invertebrate)
    print("\nStep 3: build toxicity lookups")
    tox_avian = build_toxicity_lookup(code_to_name, code_to_class,
                                      AVIAN_LD50_MG_PER_KG, "avian LD50")
    print(f"  avian LD50 values for {len(tox_avian)} chem_codes")
    tox_aquatic = build_toxicity_lookup(code_to_name, code_to_class,
                                        AQUATIC_LC50_UG_PER_L, "aquatic LC50")
    print(f"  aquatic LC50 values for {len(tox_aquatic)} chem_codes")

    # Step 4: ag site filter
    ag_site_codes: set[int] | None = None
    if AG_ONLY:
        print("\nStep 4: build ag site filter")
        site_df = load_site_lookup(zip_paths[latest_year])
        if not site_df.empty:
            ag_site_codes = set(site_df.loc[site_df["site_code"] < 65000,
                                            "site_code"].dropna().astype(int))
            print(f"  ag site codes: {len(ag_site_codes)}")
        else:
            print("  no site.txt found; falling back to all records")

    # Step 5: aggregate per year
    print("\nStep 5: aggregate UDC data")
    yearly: list[pd.DataFrame] = []
    yearly_chem: list[pd.DataFrame] = []
    for year, zp in sorted(zip_paths.items()):
        print(f"  [{year}] aggregating ...")
        df, chem_df = aggregate_year(zp, year, code_to_class, code_to_name,
                                     tox_avian, tox_aquatic, ag_site_codes)
        if not df.empty:
            yearly.append(df)
            if not chem_df.empty:
                yearly_chem.append(chem_df)
            print(f"    total lbs AI: {df['lbs_active_ingredient'].sum():,.0f} | "
                  f"total acres: {df['acres_treated'].sum():,.0f}")

    if not yearly:
        print("No data aggregated; aborting.")
        return 1

    summary = pd.concat(yearly, ignore_index=True)

    # Step 6: write per-metric long-format CSVs and charts
    print("\nStep 6: outputs")
    metrics = [
        ("lbs_active_ingredient", "pur_yearly_lbs_by_class.csv", "pur_chart_lbs.png", "LBS ACTIVE INGREDIENT"),
        ("acres_treated", "pur_yearly_acres_by_class.csv", "pur_chart_acres.png", "ACRES TREATED"),
    ]
    if TOXICITY_WEIGHTING:
        metrics.append((
            "toxicity_units_avian_ld50",
            "pur_yearly_tox_avian_by_class.csv",
            "pur_chart_toxicity_avian.png",
            "AVIAN-LD50-WEIGHTED TOXICITY UNITS",
        ))
        metrics.append((
            "toxicity_units_aquatic_lc50",
            "pur_yearly_tox_aquatic_by_class.csv",
            "pur_chart_toxicity_aquatic.png",
            "AQUATIC-INVERT-EC50-WEIGHTED TOXICITY UNITS",
        ))

    for value_col, csv_name, chart_name, label in metrics:
        slim = summary[["year", "class", value_col]].copy()
        slim.to_csv(OUTPUT_DIR / csv_name, index=False)
        print(f"  csv  -> {OUTPUT_DIR / csv_name}")
        make_chart(summary, value_col, OUTPUT_DIR / chart_name)
        print_pivot(summary, value_col, label)

    # Carbamate per-chemical breakdown
    if TOXICITY_WEIGHTING and yearly_chem:
        chem_summary = pd.concat(yearly_chem, ignore_index=True)
        chem_summary.to_csv(OUTPUT_DIR / "pur_yearly_carbamate_by_chem.csv", index=False)
        print(f"\n  csv  -> {OUTPUT_DIR / 'pur_yearly_carbamate_by_chem.csv'}")
        make_chart(chem_summary, "toxicity_units_avian_ld50",
                   OUTPUT_DIR / "pur_chart_carbamate_avian_by_chem.png",
                   pivot_col="chemname", title_key="carbamate_avian_by_chem")
        make_chart(chem_summary, "lbs_active_ingredient",
                   OUTPUT_DIR / "pur_chart_carbamate_lbs_by_chem.png",
                   pivot_col="chemname", title_key="carbamate_lbs_by_chem")
        print_pivot(chem_summary, "toxicity_units_avian_ld50",
                    "CARBAMATE AVIAN-LD50-WEIGHTED TOXICITY UNITS — PER CHEMICAL",
                    pivot_col="chemname")
        print_pivot(chem_summary, "lbs_active_ingredient",
                    "CARBAMATE LBS AI — PER CHEMICAL",
                    pivot_col="chemname")

    return 0


if __name__ == "__main__":
    sys.exit(main())
