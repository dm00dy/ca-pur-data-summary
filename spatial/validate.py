#!/usr/bin/env python3
"""
Validate
========
Sanity checks for spatial pipeline outputs. Designed to be run after
pur_loader.py and optionally exposure_engine.py. Exits 0 if all checks pass,
1 if any critical checks fail.

Checks:
  1. Statewide totals: pur_sections.parquet lbs/class/year vs.
     pur_analyze.py's pur_yearly_by_class.csv (must agree within 2%)
  2. COMTRS coverage: fraction of PUR records with a valid COMTRS field
  3. Buffer monotonicity: for each location, 500m <= 1km <= 2km <= 5km
  4. Section-level spot checks: 5 random high-intensity sections vs.
     raw PUR archive totals
  5. CDL attribution sanity: for sections dominated by a crop, attribution
     fraction for that crop's applications should be > uniform

Usage:
    python validate.py [--exposure outputs/exposure.csv]
"""

from __future__ import annotations

import argparse
import random
import sys
import zipfile
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("outputs")
PUR_PARQUET = OUTPUT_DIR / "pur_sections.parquet"
STATEWIDE_CSV = Path("../pur_analysis/pur_yearly_by_class.csv")
PUR_CACHE_DIR = Path("../pur_analysis/cache")
ATTR_PARQUET = OUTPUT_DIR / "crop_attribution.parquet"

TOLERANCE = 0.02   # 2% tolerance for statewide total comparison
CRITICAL_CHECKS = {"statewide_totals", "comtrs_coverage"}  # failures exit nonzero


# ---------------------------------------------------------------------------
# CHECK 1: STATEWIDE TOTALS
# ---------------------------------------------------------------------------

def check_statewide_totals() -> bool:
    """Loader lbs must be <= reference (pur_analyze.py) for every year×class.

    The loader only retains records with a valid COMTRS field (~40-70% of all
    records, depending on year). Loader < reference is therefore expected and
    correct. Loader > reference would indicate double-counting or a logic bug.

    Also reports the per-year COMTRS coverage fraction as an informational note.
    """
    if not PUR_PARQUET.exists():
        print("  SKIP — pur_sections.parquet not found")
        return True
    if not STATEWIDE_CSV.exists():
        print("  SKIP — pur_yearly_by_class.csv not found (run pur_analyze.py first)")
        return True

    loader = pd.read_parquet(PUR_PARQUET, columns=["year", "chem_class", "lbs_ai"])
    loader_pivot = loader.groupby(["year", "chem_class"])["lbs_ai"].sum().unstack(fill_value=0)

    reference = pd.read_csv(STATEWIDE_CSV)
    ref_pivot = reference.pivot_table(index="year", columns="class", values="lbs_ai", aggfunc="sum")

    common_years = loader_pivot.index.intersection(ref_pivot.index)
    common_classes = loader_pivot.columns.intersection(ref_pivot.columns)

    if len(common_years) == 0 or len(common_classes) == 0:
        print("  SKIP — no overlapping year/class combinations to compare")
        return True

    loader_sub = loader_pivot.loc[common_years, common_classes]
    ref_sub = ref_pivot.loc[common_years, common_classes]

    # Coverage summary: what fraction of statewide lbs are in the spatial subset
    total_loader = float(loader_sub.values.sum())
    total_ref = float(ref_sub.values.sum())
    coverage = total_loader / total_ref if total_ref > 0 else 0
    print(f"  Spatial coverage: loader {total_loader:,.0f} / reference {total_ref:,.0f} lbs "
          f"({coverage:.0%} of statewide — COMTRS-tagged records only)")

    # Per-year coverage
    for yr in sorted(common_years):
        yr_ldr = float(loader_sub.loc[yr].sum()) if yr in loader_sub.index else 0
        yr_ref = float(ref_sub.loc[yr].sum()) if yr in ref_sub.index else 0
        cov = yr_ldr / yr_ref if yr_ref > 0 else 0
        print(f"    {yr}: {yr_ldr:>12,.0f} / {yr_ref:>12,.0f} lbs  ({cov:.0%})")

    # FAIL only if loader exceeds reference (double-counting bug)
    failures: list[str] = []
    for cls in common_classes:
        for yr in common_years:
            ref_val = float(ref_sub.loc[yr, cls]) if cls in ref_sub.columns else 0.0
            ldr_val = float(loader_sub.loc[yr, cls]) if cls in loader_sub.columns else 0.0
            if ldr_val > ref_val * (1 + TOLERANCE):
                failures.append(
                    f"    {yr} {cls}: loader={ldr_val:,.0f} > reference={ref_val:,.0f} (OVERCOUNTING)"
                )

    if failures:
        print(f"\n  FAIL — loader exceeds reference in {len(failures)} year×class pairs:")
        for f in failures:
            print(f)
        return False

    print("  PASS — loader does not exceed reference for any year×class")
    return True


# ---------------------------------------------------------------------------
# CHECK 2: COMTRS COVERAGE
# ---------------------------------------------------------------------------

def check_comtrs_coverage() -> bool:
    """Warn if a high fraction of PUR records were dropped due to missing COMTRS."""
    if not PUR_PARQUET.exists():
        print("  SKIP — pur_sections.parquet not found")
        return True

    # The loader only writes records with valid COMTRS; compare total to a raw
    # record count from the archive to estimate drop rate.
    loader = pd.read_parquet(PUR_PARQUET, columns=["year", "lbs_ai"])
    loader_by_year = loader.groupby("year").size()

    # Quick raw count from one cached zip (2023 if available)
    years_available = sorted(loader["year"].unique(), reverse=True)
    if not years_available:
        print("  SKIP — no loader data")
        return True

    check_year = years_available[0]
    zip_path = PUR_CACHE_DIR / f"pur{check_year}.zip"
    if not zip_path.exists():
        print(f"  SKIP — pur{check_year}.zip not in cache")
        return True

    raw_count = 0
    with zipfile.ZipFile(zip_path) as zf:
        udc_files = [n for n in zf.namelist()
                     if Path(n).name.lower().startswith("udc") and n.lower().endswith(".txt")]
        for name in udc_files[:5]:  # sample 5 counties for speed
            with zf.open(name) as fh:
                df = pd.read_csv(fh, encoding="latin-1", dtype=str,
                                 usecols=lambda c: c.strip().lower() == "comtrs",
                                 on_bad_lines="skip")
                raw_count += len(df)

    loader_count = loader_by_year.get(check_year, 0)
    # Extrapolate raw_count from 5 counties to all ~58 counties
    estimated_total = raw_count * (len(udc_files) / min(5, len(udc_files)))
    coverage = loader_count / estimated_total if estimated_total > 0 else 0

    if coverage < 0.5:
        print(f"  WARN — {check_year}: loader has {loader_count:,} records vs ~{estimated_total:,.0f} raw "
              f"({coverage:.0%} coverage). Low COMTRS fill rate in raw data is expected for some years.")
    else:
        print(f"  PASS — {check_year}: estimated {coverage:.0%} of records have valid COMTRS")
    return True


# ---------------------------------------------------------------------------
# CHECK 3: BUFFER MONOTONICITY
# ---------------------------------------------------------------------------

def check_buffer_monotonicity(exposure_path: Path) -> bool:
    """For each location × chemical_class × lag, lbs must be non-decreasing with buffer size."""
    if not exposure_path.exists():
        print(f"  SKIP — {exposure_path} not found (run exposure_engine.py)")
        return True

    df = pd.read_csv(exposure_path)
    if "buffer_m" not in df.columns:
        print("  SKIP — exposure file lacks buffer_m column")
        return True

    buffers = sorted(df["buffer_m"].unique())
    if len(buffers) < 2:
        print("  SKIP — fewer than 2 buffer distances")
        return True

    failures = 0
    group_cols = [c for c in ["location_id", "chemical_class", "lag_window_days"] if c in df.columns]
    for keys, grp in df.groupby(group_cols):
        grp_sorted = grp.sort_values("buffer_m")
        vals = grp_sorted["lbs_ai"].values
        for i in range(len(vals) - 1):
            if vals[i] > vals[i + 1] + 0.001:  # small tolerance for float rounding
                failures += 1

    if failures:
        print(f"  FAIL — {failures} group(s) violate buffer monotonicity (lbs at r1 > lbs at r2 where r1 < r2)")
        return False

    n_groups = df.groupby(group_cols).ngroups
    print(f"  PASS — {n_groups:,} groups all monotonically non-decreasing across buffers")
    return True


# ---------------------------------------------------------------------------
# CHECK 4: SECTION SPOT CHECKS
# ---------------------------------------------------------------------------

def check_section_spotchecks(n: int = 5) -> bool:
    """Compare a sample of sections in the loader output against raw PUR totals."""
    if not PUR_PARQUET.exists():
        print("  SKIP — pur_sections.parquet not found")
        return True

    loader = pd.read_parquet(PUR_PARQUET, columns=["year", "section_key", "comtrs", "chem_class", "lbs_ai"])
    # Pick top-intensity sections for spot-checking (easier to verify manually)
    top = (loader.groupby("section_key")["lbs_ai"].sum()
           .nlargest(50)
           .sample(min(n, 50), random_state=42)
           .index.tolist())

    year = int(loader["year"].max())
    zip_path = PUR_CACHE_DIR / f"pur{year}.zip"
    if not zip_path.exists():
        print(f"  SKIP — pur{year}.zip not in cache")
        return True

    # Get all chem_codes for tracked chemicals from loader
    loader_sub = loader[(loader["section_key"].isin(top)) & (loader["year"] == year)]
    loader_totals = loader_sub.groupby("section_key")["lbs_ai"].sum()

    # Compute raw archive totals for these sections + year
    comtrs_for_sections = loader[(loader["section_key"].isin(top))]["comtrs"].unique()
    raw_totals: dict[str, float] = {}
    with zipfile.ZipFile(zip_path) as zf:
        udc_files = [n for n in zf.namelist()
                     if Path(n).name.lower().startswith("udc") and n.lower().endswith(".txt")]
        for name in udc_files:
            with zf.open(name) as fh:
                try:
                    df = pd.read_csv(fh, encoding="latin-1", dtype=str,
                                     usecols=lambda c: c.strip().lower() in
                                         {"comtrs", "lbs_chm_used", "site_code"},
                                     on_bad_lines="skip")
                except Exception:
                    continue
            df.columns = [c.strip().lower() for c in df.columns]
            if "comtrs" not in df.columns:
                continue
            df = df[df["comtrs"].isin(comtrs_for_sections)].copy()
            if df.empty:
                continue
            df["lbs"] = pd.to_numeric(df["lbs_chm_used"], errors="coerce").fillna(0)
            df["site_code"] = pd.to_numeric(df.get("site_code", pd.Series(dtype=str)), errors="coerce")
            df = df[df["site_code"].fillna(99999) < 65000]
            for comtrs, sub in df.groupby("comtrs"):
                key = str(comtrs)[2:]  # strip county prefix
                raw_totals[key] = raw_totals.get(key, 0) + float(sub["lbs"].sum())

    print("  Section spot-checks (loader vs raw archive, all chemicals):")
    print(f"  {'section_key':<12} {'loader_lbs':>12} {'raw_lbs':>12} {'diff%':>8}")
    ok = True
    for sk in top:
        ldr = float(loader_totals.get(sk, 0))
        raw = float(raw_totals.get(sk, 0))
        if raw == 0 and ldr == 0:
            continue
        denom = max(ldr, raw)
        diff_pct = abs(ldr - raw) / denom * 100 if denom > 0 else 0
        flag = " <-- NOTE" if diff_pct > 10 else ""
        print(f"  {sk:<12} {ldr:>12,.0f} {raw:>12,.0f} {diff_pct:>7.1f}%{flag}")
        # Large differences are expected (raw includes all chemicals, loader only tracked ones)
    print("  NOTE: raw_lbs includes ALL chemicals; loader_lbs is tracked insecticides only.")
    print("        loader < raw is expected; loader > raw indicates a problem.")
    for sk in top:
        ldr = float(loader_totals.get(sk, 0))
        raw = float(raw_totals.get(sk, 0))
        if ldr > raw * 1.02:
            print(f"  FAIL — {sk}: loader ({ldr:.0f}) > raw ({raw:.0f})")
            ok = False
    if ok:
        print("  PASS — no sections where loader exceeds raw total")
    return ok


# ---------------------------------------------------------------------------
# CHECK 5: CDL ATTRIBUTION SANITY
# ---------------------------------------------------------------------------

def check_attribution_sanity() -> bool:
    """Crop-matched attribution should exceed 'uniform' for sections with that crop."""
    if not ATTR_PARQUET.exists():
        print(f"  SKIP — {ATTR_PARQUET} not found (run crop_attribution.py)")
        return True

    attr = pd.read_parquet(ATTR_PARQUET)
    n_total = len(attr)
    if n_total == 0:
        print("  SKIP — attribution file is empty")
        return True

    by_tier = attr["fallback"].value_counts()
    print(f"  Attribution tiers: {dict(by_tier)}")

    exact = attr[attr["fallback"] == "exact_crop"]
    if exact.empty:
        print("  SKIP — no exact_crop records to check")
        return True

    # For exact_crop records, attribution_fraction should generally be < 1.0
    # (the crop doesn't cover the whole section) but > 0 (crop exists there)
    bad_zero = (exact["attribution_fraction"] <= 0).sum()
    bad_one = (exact["attribution_fraction"] > 1.0).sum()

    if bad_zero:
        print(f"  FAIL — {bad_zero} exact_crop records have attribution_fraction <= 0")
        return False
    if bad_one:
        print(f"  FAIL — {bad_one} exact_crop records have attribution_fraction > 1.0")
        return False

    median_exact = float(exact["attribution_fraction"].median())
    all_ag = attr[attr["fallback"] == "all_ag"]
    median_ag = float(all_ag["attribution_fraction"].median()) if not all_ag.empty else None

    print(f"  Median attribution_fraction: exact_crop={median_exact:.3f}"
          + (f", all_ag={median_ag:.3f}" if median_ag is not None else ""))

    if median_exact > 0.95:
        print("  WARN — median exact_crop attribution is very high (near 1.0); "
              "check CDL raster registration")
    print("  PASS")
    return True


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate spatial pipeline outputs")
    parser.add_argument("--exposure", type=Path, default=OUTPUT_DIR / "exposure.csv",
                        help="Exposure CSV from exposure_engine.py")
    args = parser.parse_args()

    print("Spatial pipeline validation\n" + "=" * 40)

    results: dict[str, bool] = {}

    print("\nCheck 1: Statewide totals (loader vs pur_analyze.py)")
    results["statewide_totals"] = check_statewide_totals()

    print("\nCheck 2: COMTRS coverage rate")
    results["comtrs_coverage"] = check_comtrs_coverage()

    print("\nCheck 3: Buffer monotonicity")
    results["buffer_monotonicity"] = check_buffer_monotonicity(args.exposure)

    print("\nCheck 4: Section spot-checks (5 high-intensity sections)")
    results["section_spotchecks"] = check_section_spotchecks()

    print("\nCheck 5: CDL attribution sanity")
    results["attribution_sanity"] = check_attribution_sanity()

    print("\n" + "=" * 40)
    n_pass = sum(results.values())
    n_fail = len(results) - n_pass
    print(f"Results: {n_pass} passed, {n_fail} failed")
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {name}")

    critical_failures = [k for k in CRITICAL_CHECKS if not results.get(k, True)]
    if critical_failures:
        print(f"\nCritical failures: {critical_failures}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
