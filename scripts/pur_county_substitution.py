#!/usr/bin/env python3
"""
County-level oxamyl / chlorpyrifos substitution analysis
=========================================================

Tests whether the chlorpyrifos phase-out (2019–2021) was followed by
compensatory oxamyl adoption in the same counties.

Reads from the cached PUR zip archives in pur_analysis/cache/ — no new
downloads needed if pur_analyze.py has already been run.

Outputs (in pur_analysis/):
    pur_county_substitution.csv     -- long-format: year, county_cd, chemical, lbs
    pur_substitution_statewide.png  -- two-line statewide totals
    pur_substitution_scatter.png    -- county delta scatter (Δchlor vs Δoxamyl)

Usage:
    source .venv/bin/activate
    python pur_county_substitution.py
"""

from __future__ import annotations

import zipfile
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

YEARS = list(range(2015, 2024))
OUTPUT_DIR = Path("./pur_analysis")
CACHE_DIR = OUTPUT_DIR / "cache"

TARGET_CHEMICALS = {"chlorpyrifos", "oxamyl",
                    "lambda-cyhalothrin", "bifenthrin", "permethrin",
                    "cypermethrin", "zeta-cypermethrin", "cyfluthrin",
                    "beta-cyfluthrin", "deltamethrin", "esfenvalerate"}

# Ag filter: site_code < 65000 (same heuristic as main script)
AG_ONLY = True
AG_SITE_MAX = 65000

# For the scatter: compare the pre-phase-out peak window to the post window
PRE_YEARS  = (2015, 2018)   # chlorpyrifos still legal everywhere
POST_YEARS = (2021, 2023)   # post-phase-out

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _resolve_targets(zip_path: Path) -> dict[int, str]:
    """Return {chem_code: chemical_name} for TARGET_CHEMICALS from chemical.txt."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith("chemical.txt")]
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, encoding="latin-1", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    df["chem_code"] = pd.to_numeric(df["chem_code"], errors="coerce")
    df["chemname"] = df["chemname"].str.strip().str.lower()
    mask = df["chemname"].isin(TARGET_CHEMICALS)
    mapping = df.loc[mask].set_index("chem_code")["chemname"].to_dict()
    return {int(k): v for k, v in mapping.items() if pd.notna(k)}


def _aggregate_year(zip_path: Path, year: int,
                    code_to_name: dict[int, str]) -> pd.DataFrame:
    """Return DataFrame with columns [county_cd, chemical, lbs] for one year."""
    target_codes = set(code_to_name.keys())
    acc: dict[tuple[str, str], float] = defaultdict(float)

    with zipfile.ZipFile(zip_path) as zf:
        udc_names = [
            n for n in zf.namelist()
            if Path(n).name.lower().startswith("udc") and n.lower().endswith(".txt")
        ]
        print(f"  [{year}] {len(udc_names)} county files", flush=True)

        for i, name in enumerate(udc_names, 1):
            with zf.open(name) as f:
                try:
                    reader = pd.read_csv(
                        f,
                        encoding="latin-1",
                        usecols=lambda c: c.strip().lower() in
                                         {"chem_code", "lbs_chm_used", "site_code", "county_cd"},
                        dtype=str,
                        chunksize=200_000,
                        low_memory=False,
                        on_bad_lines="skip",
                    )
                except ValueError as e:
                    print(f"    {Path(name).name}: skipped ({e})")
                    continue

                for chunk in reader:
                    chunk.columns = [c.strip().lower() for c in chunk.columns]
                    if "chem_code" not in chunk.columns:
                        continue

                    chunk["chem_code"] = pd.to_numeric(chunk["chem_code"], errors="coerce")
                    chunk = chunk[chunk["chem_code"].isin(target_codes)].copy()
                    if chunk.empty:
                        continue

                    if AG_ONLY and "site_code" in chunk.columns:
                        chunk["site_code"] = pd.to_numeric(chunk["site_code"], errors="coerce")
                        chunk = chunk[chunk["site_code"] < AG_SITE_MAX]
                        if chunk.empty:
                            continue

                    chunk["lbs_chm_used"] = pd.to_numeric(
                        chunk["lbs_chm_used"], errors="coerce"
                    ).fillna(0.0)

                    county_col = chunk.get("county_cd", pd.Series(["unknown"] * len(chunk)))
                    chunk["county_cd"] = county_col.fillna("unknown").astype(str).str.strip().str.zfill(2)

                    for (county, code), sub in chunk.groupby(
                        ["county_cd", "chem_code"], observed=True
                    ):
                        chem = code_to_name.get(int(code))
                        if chem:
                            acc[(county, chem)] += float(sub["lbs_chm_used"].sum())

            if i % 10 == 0 or i == len(udc_names):
                print(f"    processed {i}/{len(udc_names)}", end="\r", flush=True)
        print()

    rows = [
        {"year": year, "county_cd": county, "chemical": chem, "lbs": lbs}
        for (county, chem), lbs in acc.items()
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CHARTS
# ---------------------------------------------------------------------------

COLORS = {"chlorpyrifos": "#e05c2a", "oxamyl": "#3d7abf"}


def chart_statewide(df: pd.DataFrame, out: Path) -> None:
    state = (
        df.groupby(["year", "chemical"])["lbs"]
        .sum()
        .unstack(fill_value=0.0)
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    for chem in ["chlorpyrifos", "oxamyl"]:
        if chem in state.columns:
            ax.plot(state.index, state[chem] / 1e3, marker="o",
                    label=chem.capitalize(), color=COLORS[chem], linewidth=2)

    ax.axvspan(2018.5, 2019.5, alpha=0.08, color="gray", label="Chlorpyrifos phase-out")
    ax.set_xlabel("Year")
    ax.set_ylabel("Thousand lbs AI applied (CA agriculture)")
    ax.set_title("Chlorpyrifos decline and oxamyl adoption — California")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved {out}")


def chart_scatter(df: pd.DataFrame, out: Path) -> None:
    """County-level scatter: mean annual lbs change (chlorpyrifos) on x,
    mean annual lbs change (oxamyl) on y. Pre vs post phase-out."""

    pre  = df[df["year"].between(*PRE_YEARS)].groupby(["county_cd", "chemical"])["lbs"].mean().unstack(fill_value=0.0)
    post = df[df["year"].between(*POST_YEARS)].groupby(["county_cd", "chemical"])["lbs"].mean().unstack(fill_value=0.0)

    delta = post.subtract(pre, fill_value=0.0)
    if "chlorpyrifos" not in delta.columns or "oxamyl" not in delta.columns:
        print("  Scatter skipped: one or both chemicals absent from county data")
        return

    # Drop counties that had zero of both in both windows (no ag activity)
    active = delta[(delta["chlorpyrifos"].abs() > 0) | (delta["oxamyl"].abs() > 0)]

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(
        active["chlorpyrifos"] / 1e3,
        active["oxamyl"] / 1e3,
        alpha=0.7, s=40, color="#555", edgecolors="none",
    )

    # Label a few large-change counties
    top = active.nlargest(6, "oxamyl").index.tolist() + \
          active.nsmallest(6, "chlorpyrifos").index.tolist()
    for cty in set(top):
        row = active.loc[cty]
        ax.annotate(f"  {cty}", (row["chlorpyrifos"] / 1e3, row["oxamyl"] / 1e3),
                    fontsize=7, alpha=0.8)

    ax.axhline(0, color="gray", linewidth=0.8)
    ax.axvline(0, color="gray", linewidth=0.8)
    ax.set_xlabel(f"Δ Chlorpyrifos (thousand lbs/yr,  {PRE_YEARS[0]}–{PRE_YEARS[1]} → {POST_YEARS[0]}–{POST_YEARS[1]})")
    ax.set_ylabel(f"Δ Oxamyl (thousand lbs/yr)")
    ax.set_title("County-level substitution: chlorpyrifos decline vs. oxamyl adoption\n"
                 "(Q2: upper-left = substitution; Q3: both declined = abandonment)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved {out}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Resolve chem_codes from the first available cached zip
    code_to_name: dict[int, str] = {}
    for year in YEARS:
        zp = CACHE_DIR / f"pur{year}.zip"
        if zp.exists():
            code_to_name = _resolve_targets(zp)
            print(f"Resolved {len(code_to_name)} target chem_codes from {zp.name}:")
            for code, name in sorted(code_to_name.items(), key=lambda x: x[1]):
                print(f"  {code:6d}  {name}")
            break

    if not code_to_name:
        print("ERROR: no cached zip files found in", CACHE_DIR)
        return

    frames = []
    for year in YEARS:
        zp = CACHE_DIR / f"pur{year}.zip"
        if not zp.exists():
            print(f"  [{year}] not cached — skipping")
            continue
        frames.append(_aggregate_year(zp, year, code_to_name))

    if not frames:
        print("No data collected.")
        return

    df = pd.concat(frames, ignore_index=True)
    df["year"] = df["year"].astype(int)

    csv_out = OUTPUT_DIR / "pur_county_substitution.csv"
    df.to_csv(csv_out, index=False)
    print(f"\nWrote {len(df):,} rows → {csv_out}")

    # Statewide summary for quick sanity check
    state = df.groupby(["year", "chemical"])["lbs"].sum().unstack(fill_value=0.0)
    print("\nStatewide totals (lbs AI):")
    print(state.round(0).to_string())

    chart_statewide(df, OUTPUT_DIR / "pur_substitution_statewide.png")
    chart_scatter(df, OUTPUT_DIR / "pur_substitution_scatter.png")

    print("\nDone.")


if __name__ == "__main__":
    main()
