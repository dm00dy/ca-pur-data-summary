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
- Added optional toxicity weighting via avian acute oral LD50 (illustrative
  defaults; see TOXICITY caveats below)
- Added optional aquatic invertebrate toxicity weighting via Daphnia magna
  acute LC50 (more relevant for aerial insectivore prey-base question)
- Four chart sets: lbs, acres, avian-tox-weighted, aquatic-tox-weighted
- Summary tables written for each metric

*** TOXICITY VALUES ARE ILLUSTRATIVE — NOT FOR EXTERNAL USE ***

The avian LD50 and aquatic LC50 reference tables in this script are
illustrative defaults suitable only for internal exploratory analysis. They
are NOT properly sourced from EPA ECOTOX, Hertfordshire PPDB, or any other
documented database, and they must NOT be cited or used in grant proposals,
manuscripts, agency reports, or external presentations without first being
re-sourced with documented citations. See the comment blocks above each
toxicity table for full details on what proper sourcing requires.

The lbs and acres outputs are sourced directly from CDPR PUR and are safe
to use externally with appropriate caveats about data resolution and
application-vs-exposure interpretation.

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

# Toggle toxicity-weighted output. Defaults are illustrative bobwhite quail
# acute oral LD50 (mg/kg) drawn from EPA ECOTOX and the Hertfordshire PPDB.
# Enable this if you want a directional toxicity comparison; do NOT use the
# specific numbers in a publication or proposal without sourcing them properly.
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
# TOXICITY REFERENCE TABLE — ILLUSTRATIVE DEFAULTS (NOT FOR PUBLICATION)
# ---------------------------------------------------------------------------
#
# *** READ THIS BEFORE USING ANY OF THESE NUMBERS EXTERNALLY ***
#
# The values in this table are ILLUSTRATIVE DEFAULTS suitable only for
# internal exploratory analysis. They are NOT properly sourced and must NOT
# be used in any of the following contexts without re-sourcing first:
#
#   - Grant proposals (beyond directional, internal-discussion use)
#   - Peer-reviewed manuscripts
#   - Reports to CDPR or any other agency
#   - Any external presentation or document
#
# Why these values are not yet publication-ready:
#   1. They are drawn from author knowledge of EPA ECOTOX and Hertfordshire
#      PPDB conventions, not from a documented query of either database.
#   2. Each chemical typically has multiple published LD50 values that vary
#      by test species (Bobwhite vs. Mallard), test duration (acute oral vs.
#      5-day dietary), and study conditions. The single value chosen here
#      reflects no documented selection criterion.
#   3. ">N" ceiling values (where LD50 was not reached at the highest dose
#      tested) are recorded as N, which understates true safety margins.
#   4. No citations are attached to individual values.
#
# To make this table publication-ready, every chemical needs: source database,
# chemical record URL or EPA ECOTOX query parameters, test species, test
# duration, selected endpoint with rationale, and citation. Plan ~4-8 hours
# of careful database work, ideally done collaboratively with a toxicology
# partner.
#
# Avian acute oral LD50 in mg/kg body weight (Northern Bobwhite, Colinus
# virginianus, where available; else Mallard or other surrogate).
#
# IMPORTANT INTERPRETATION CAVEAT
# -------------------------------
# Avian oral LD50 measures direct toxicity to birds via ingestion of the
# chemical. For aerial insectivores (birds AND bats), the dominant exposure
# pathway is via the prey base — flying insects whose populations are affected
# by these chemicals. For that question, aquatic invertebrate toxicity (Daphnia
# magna LC50) is more directly relevant, especially for pyrethroids which have
# very low avian toxicity but extreme aquatic invertebrate toxicity.
#
# The bird LD50 weighting below is therefore best read as a direct-mortality
# proxy. A second pass with prey-toxicity weighting (the AQUATIC_LC50_UG_PER_L
# table below) tells a meaningfully different story and is generally more
# relevant for the aerial-insectivore question.
#
# Lower LD50 = more toxic per unit mass.
# Values marked ">N" are reported as greater than the test ceiling — actual
# toxicity is at least that low (i.e., LD50 was not reached). Treated as N here.

AVIAN_LD50_MG_PER_KG: dict[str, float] = {
    # Restricted neonics
    "imidacloprid": 31.0,
    "clothianidin": 423.0,
    "thiamethoxam": 1552.0,
    "dinotefuran": 2000.0,        # >2000 reported
    # Other neonics
    "acetamiprid": 180.0,
    "thiacloprid": 49.0,
    "nitenpyram": 1130.0,
    # Next-gen systemics
    "sulfoxaflor": 750.0,
    "flupyradifurone": 1112.0,
    # Diamides
    "chlorantraniliprole": 2250.0,    # >2250 reported
    "cyantraniliprole": 2250.0,       # >2250 reported
    "flubendiamide": 2000.0,
    "tetraniliprole": 2000.0,
    # Pyrethroids — note low direct avian toxicity
    "lambda-cyhalothrin": 3950.0,
    "gamma-cyhalothrin": 3950.0,
    "bifenthrin": 1800.0,
    "esfenvalerate": 2000.0,
    "permethrin": 9847.0,
    "cypermethrin": 9929.0,
    "zeta-cypermethrin": 9929.0,
    "cyfluthrin": 2000.0,
    "beta-cyfluthrin": 2000.0,
    "deltamethrin": 4640.0,
    "fenpropathrin": 1089.0,
    "tau-fluvalinate": 2510.0,
    "tralomethrin": 2000.0,
    # Organophosphates — generally high direct avian toxicity
    "chlorpyrifos": 32.0,
    "malathion": 167.0,
    "diazinon": 4.0,
    "dimethoate": 22.0,
    "acephate": 234.0,
    "phosmet": 26.0,
    "methidathion": 12.0,
    "naled": 37.0,
    "oxydemeton-methyl": 6.5,
    "phorate": 1.0,
    "azinphos-methyl": 7.5,
    # Carbamates
    "carbaryl": 56.0,
    "methomyl": 24.0,
    "oxamyl": 4.0,
    "carbofuran": 0.4,
    "aldicarb": 1.0,
    # Spinosyns
    "spinosad": 2000.0,
    "spinetoram": 2000.0,
}

# Class-level fallback if a chemical isn't in the table above (median of
# in-class entries computed at runtime if needed).


# ---------------------------------------------------------------------------
# AQUATIC INVERTEBRATE TOXICITY REFERENCE — ILLUSTRATIVE DEFAULTS (NOT FOR PUBLICATION)
# ---------------------------------------------------------------------------
#
# *** SAME WARNING AS THE AVIAN LD50 TABLE ABOVE ***
#
# The values in this table are ILLUSTRATIVE DEFAULTS suitable only for
# internal exploratory analysis. They are NOT properly sourced and must NOT
# be used externally without re-sourcing. See the warning block above the
# avian LD50 table for the full caveat. Pyrethroid LC50 in particular varies
# by 1-2 orders of magnitude across published studies depending on test
# conditions, formulation, and Daphnia age class — proper sourcing for this
# class is especially important.
#
# Daphnia magna 48-hour acute LC50 in μg/L (micrograms per liter).
#
# WHY THIS METRIC MATTERS
# -----------------------
# Aerial insectivores (birds and bats) feed predominantly on flying insects,
# many of which have aquatic larval stages (chironomids, mayflies, caddisflies)
# or are otherwise affected by surface-water and edge-of-field contamination.
# Aquatic invertebrate toxicity is therefore a substantially better proxy for
# prey-base disruption than direct avian toxicity. Pyrethroids in particular
# show 4–6 orders of magnitude difference between avian and aquatic endpoints:
# permethrin's avian LD50 is ~9847 mg/kg (low direct bird toxicity) but its
# Daphnia LC50 is ~0.6 μg/L (extreme aquatic invert toxicity).
#
# CAVEAT: Daphnia magna is a freshwater zooplankton, not a flying insect
# larva. It is the EPA standard surrogate for "aquatic invertebrate toxicity"
# but the actual aerial-insectivore prey base includes chironomids, mayflies,
# and other dipteran/ephemeropteran larvae. Toxicity rankings are usually
# similar but not identical across these taxa.
#
# Lower LC50 = more toxic per unit concentration.
# Toxicity Units = lbs / LC50 — same formula as avian, but vastly different
# magnitudes per chemical class. Absolute TU values are not comparable across
# the avian and aquatic tables; only within-class trends and relative
# composition are meaningful.

AQUATIC_LC50_UG_PER_L: dict[str, float] = {
    # Restricted neonics — moderate-to-high aquatic invert toxicity
    "imidacloprid": 55.0,
    "clothianidin": 22.0,
    "thiamethoxam": 35.0,
    "dinotefuran": 1000.0,
    # Other neonics
    "acetamiprid": 49.8,
    "thiacloprid": 85.1,
    "nitenpyram": 600.0,
    # Next-gen systemics
    "sulfoxaflor": 380.0,
    "flupyradifurone": 290.0,
    # Diamides — selectively toxic, modest Daphnia impact
    "chlorantraniliprole": 11.6,
    "cyantraniliprole": 4.0,
    "flubendiamide": 320.0,
    "tetraniliprole": 200.0,
    # Pyrethroids — extreme aquatic invert toxicity, sub-ppb LC50s
    "lambda-cyhalothrin": 0.36,
    "gamma-cyhalothrin": 0.20,
    "bifenthrin": 0.16,
    "esfenvalerate": 0.10,
    "permethrin": 0.60,
    "cypermethrin": 0.30,
    "zeta-cypermethrin": 0.26,
    "cyfluthrin": 0.14,
    "beta-cyfluthrin": 0.14,
    "deltamethrin": 0.56,
    "fenpropathrin": 0.41,
    "tau-fluvalinate": 0.40,
    "tralomethrin": 0.41,
    # Organophosphates — high aquatic toxicity but mostly less than pyrethroids
    "chlorpyrifos": 0.10,
    "malathion": 0.74,
    "diazinon": 0.80,
    "dimethoate": 2000.0,
    "acephate": 92000.0,
    "phosmet": 5.7,
    "methidathion": 4.9,
    "naled": 0.35,
    "oxydemeton-methyl": 50.0,
    "phorate": 1.8,
    "azinphos-methyl": 1.0,
    # Carbamates — high aquatic invert toxicity
    "carbaryl": 5.6,
    "methomyl": 8.8,
    "oxamyl": 270.0,
    "carbofuran": 9.4,
    "aldicarb": 75.0,
    # Spinosyns — moderate aquatic invert toxicity
    "spinosad": 92.0,
    "spinetoram": 14.0,
}


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
                   tox_avian: dict[int, float],
                   tox_aquatic: dict[int, float],
                   ag_site_codes: set[int] | None) -> pd.DataFrame:
    """Returns one row per (year, class) with sums of lbs, acres, records,
    and toxicity-weighted lbs for both avian (lbs/LD50) and aquatic
    invertebrate (lbs/LC50) endpoints."""

    classes = sorted(set(code_to_class.values()))
    accumulator: dict[str, dict[str, float]] = {
        cls: {"lbs": 0.0, "acres": 0.0,
              "tox_avian": 0.0, "tox_aquatic": 0.0,
              "n_records": 0}
        for cls in classes
    }
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
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------

CHART_TITLES = {
    "lbs_active_ingredient": ("California agricultural insecticide use by chemical class",
                              "Million lbs AI applied", 1e6),
    "acres_treated": ("California agricultural insecticide application area by chemical class",
                      "Million acres treated", 1e6),
    "toxicity_units_avian_ld50": ("Avian-LD50-weighted insecticide load (illustrative)",
                                  "Toxicity units (lbs ÷ avian LD50)", 1.0),
    "toxicity_units_aquatic_lc50": ("Aquatic-invertebrate-LC50-weighted insecticide load (illustrative)",
                                    "Toxicity units (lbs ÷ Daphnia LC50)", 1.0),
}


def make_chart(summary: pd.DataFrame, value_col: str, out_path: Path) -> None:
    title, ylabel, scale = CHART_TITLES[value_col]
    pivot = summary.pivot_table(index="year", columns="class",
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


def print_pivot(summary: pd.DataFrame, value_col: str, label: str) -> None:
    pivot = summary.pivot_table(index="year", columns="class",
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
    print(f"Toxicity weighting: {'ON (illustrative defaults)' if TOXICITY_WEIGHTING else 'OFF'}\n")

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
    for year, zp in sorted(zip_paths.items()):
        print(f"  [{year}] aggregating ...")
        df = aggregate_year(zp, year, code_to_class, tox_avian, tox_aquatic, ag_site_codes)
        if not df.empty:
            yearly.append(df)
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
            "AVIAN-LD50-WEIGHTED TOXICITY UNITS (illustrative)",
        ))
        metrics.append((
            "toxicity_units_aquatic_lc50",
            "pur_yearly_tox_aquatic_by_class.csv",
            "pur_chart_toxicity_aquatic.png",
            "AQUATIC-INVERT-LC50-WEIGHTED TOXICITY UNITS (illustrative)",
        ))

    for value_col, csv_name, chart_name, label in metrics:
        slim = summary[["year", "class", value_col]].copy()
        slim.to_csv(OUTPUT_DIR / csv_name, index=False)
        print(f"  csv  -> {OUTPUT_DIR / csv_name}")
        make_chart(summary, value_col, OUTPUT_DIR / chart_name)
        print_pivot(summary, value_col, label)

    return 0


if __name__ == "__main__":
    sys.exit(main())
