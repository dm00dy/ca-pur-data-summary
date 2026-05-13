#!/usr/bin/env python3
"""
PLSS-Bird spatial join
======================
Links RWI + AMPL monitoring sites to CDPR PUR sections (PLSS) and
evaluates whether sites span the OP pesticide gradient needed for
a cross-level validation analysis.

Output: /tmp/sites_plss_joined.csv + console summary
"""

import math
import zipfile
import pandas as pd
import mysql.connector
from pathlib import Path

CACHE_DIR = Path("/home/ubuntu/devops/pur/pur_analysis/cache")
CHEM_LOOKUP = Path("/home/ubuntu/devops/pur/pur_analysis/chemical_lookup.csv")

MERIDIANS = {
    "M": (37.87810, -121.91402),   # Mount Diablo
    "S": (34.10806, -116.92667),   # San Bernardino
}
MILE_LAT = 1.0 / 69.0
MILE_LON = 1.0 / 54.6

SJV_COUNTIES = [10, 15, 16, 20, 24, 39, 50, 54]
PRE_YEARS  = [2015, 2016, 2017, 2018]
POST_YEARS = [2020, 2021, 2022, 2023]


# ---------------------------------------------------------------------------
# Inverse PLSS: (lat, lon) -> 9-char section key {meridian}{twp}{dir}{rng}{dir}{sec}
# ---------------------------------------------------------------------------
def latlon_to_plss(lat, lon, meridian="M"):
    orig_lat, orig_lon = MERIDIANS[meridian]

    # --- latitude → township + row ---
    dlat = lat - orig_lat
    if dlat >= 0:
        tdir = "N"
        nm_int = int(dlat / MILE_LAT)
        twp = nm_int // 6 + 1
        row = 5 - (nm_int % 6)
    else:
        tdir = "S"
        sm_int = int(-dlat / MILE_LAT)
        twp = sm_int // 6
        row = sm_int % 6

    # --- longitude → range + col ---
    dlon = lon - orig_lon
    if dlon >= 0:
        rdir = "E"
        east_miles = dlon / MILE_LON
    else:
        rdir = "W"
        east_miles = -dlon / MILE_LON

    rng = max(1, math.ceil(east_miles / 6))
    col = min(5, int(rng * 6 - east_miles))

    # --- (row, col) → section number ---
    col_in_row = (5 - col) if row % 2 == 0 else col
    sec = row * 6 + col_in_row + 1

    return f"{meridian}{twp:02d}{tdir}{rng:02d}{rdir}{sec:02d}"


# ---------------------------------------------------------------------------
# Step 1: monitoring sites from MySQL
# ---------------------------------------------------------------------------
print("Step 1: loading monitoring sites from ravian_wh …")
conn = mysql.connector.connect(
    host="127.0.0.1", port=3366, user="root", password="password", database="ravian_wh"
)
cur = conn.cursor()
cur.execute("""
    SELECT ProjectCode, SamplingUnitId,
           DecimalLatitude, DecimalLongitude,
           MIN(YearCollected) as yr_min,
           MAX(YearCollected) as yr_max,
           COUNT(*) as visits
    FROM ravianpointcountbase_v1
    WHERE ProjectCode IN ('RWI', 'AMPL')
      AND DecimalLatitude  BETWEEN 35.0 AND 38.5
      AND DecimalLongitude BETWEEN -122.0 AND -118.0
      AND DecimalLatitude  IS NOT NULL
      AND DecimalLongitude IS NOT NULL
    GROUP BY ProjectCode, SamplingUnitId, DecimalLatitude, DecimalLongitude
""")
sites = pd.DataFrame(
    cur.fetchall(),
    columns=["project", "site_id", "lat", "lon", "yr_min", "yr_max", "visits"],
)
conn.close()
print(f"  {len(sites)} unique point-count sites  (RWI + AMPL)")


# ---------------------------------------------------------------------------
# Step 2: assign PLSS key to every site
# ---------------------------------------------------------------------------
print("Step 2: computing PLSS section for each site …")
sites["plss_key"] = sites.apply(lambda r: latlon_to_plss(r.lat, r.lon), axis=1)
print(f"  {sites['plss_key'].nunique()} unique sections represented")


# ---------------------------------------------------------------------------
# Step 3: OP chem_codes from chemical_lookup.csv
# ---------------------------------------------------------------------------
chem_df = pd.read_csv(CHEM_LOOKUP, dtype=str)
op_codes = set(
    chem_df.loc[chem_df["class"].str.lower() == "organophosphates", "chem_code"]
)
print(f"Step 3: {len(op_codes)} OP chem_codes: {sorted(op_codes)}")


# ---------------------------------------------------------------------------
# Step 4: aggregate OP use per section from PUR archives
# ---------------------------------------------------------------------------
def load_op_by_section(years, counties, op_codes):
    """Return dict {section_key: lbs} aggregated across years and counties."""
    totals = {}
    for year in years:
        zip_path = CACHE_DIR / f"pur{year}.zip"
        yy = str(year)[2:]
        with zipfile.ZipFile(zip_path) as zf:
            # build basename → full path map (handles subdirectory prefixes)
            name_map = {Path(n).name: n for n in zf.namelist()}
            for county in counties:
                fname = f"udc{yy}_{county:02d}.txt"
                full_path = name_map.get(fname)
                if full_path is None:
                    continue
                with zf.open(full_path) as fh:
                    try:
                        df = pd.read_csv(
                            fh, encoding="latin-1", dtype=str,
                            usecols=lambda c: c.strip().lower() in
                                {"chem_code", "lbs_chm_used", "site_code", "comtrs"},
                        )
                    except Exception:
                        continue
                df.columns = [c.strip().lower() for c in df.columns]
                if "comtrs" not in df.columns:
                    continue
                df = df[df["chem_code"].isin(op_codes)].copy()
                # ag filter: site_code < 65000
                df = df[
                    pd.to_numeric(df["site_code"], errors="coerce").fillna(99999) < 65000
                ]
                df["lbs"] = pd.to_numeric(df["lbs_chm_used"], errors="coerce").fillna(0)
                df = df[df["lbs"] > 0]
                # strip 2-char county prefix from comtrs
                df["section_key"] = df["comtrs"].str[2:]
                for key, lbs in df.groupby("section_key")["lbs"].sum().items():
                    totals[key] = totals.get(key, 0) + lbs
        print(f"  {year}: {len(totals):,} sections with OP use so far")
    return totals


print("Step 4a: pre-period OP use (2015-2018) …")
pre_op  = load_op_by_section(PRE_YEARS,  SJV_COUNTIES, op_codes)

print("Step 4b: post-period OP use (2020-2023) …")
post_op = load_op_by_section(POST_YEARS, SJV_COUNTIES, op_codes)


# ---------------------------------------------------------------------------
# Step 5: join to sites
# ---------------------------------------------------------------------------
print("Step 5: joining to monitoring sites …")
sites["op_lbs_pre"]  = sites["plss_key"].map(pre_op).fillna(0)
sites["op_lbs_post"] = sites["plss_key"].map(post_op).fillna(0)
sites["op_drop_pct"] = (
    (sites["op_lbs_pre"] - sites["op_lbs_post"]) / sites["op_lbs_pre"].replace(0, float("nan"))
) * 100

# spans_2019: site has surveys on both sides of the policy change
sites["spans_2019"] = (sites["yr_min"] <= 2018) & (sites["yr_max"] >= 2020)

# treatment: high pre-period OP use that dropped post-2019
# (use median as threshold — data-driven split)
nonzero_pre = sites.loc[sites["op_lbs_pre"] > 0, "op_lbs_pre"]
threshold = nonzero_pre.median() if len(nonzero_pre) > 0 else 1.0

sites["treatment"] = (sites["op_lbs_pre"] > threshold) & (sites["op_lbs_post"] < sites["op_lbs_pre"] * 0.5)
sites["control"]   = sites["op_lbs_pre"] <= threshold


# ---------------------------------------------------------------------------
# Step 6: report
# ---------------------------------------------------------------------------
def pct(n, total):
    return f"{n} ({100*n/total:.0f}%)" if total else str(n)

n = len(sites)
n_match = (sites["op_lbs_pre"] > 0).sum()
n_spans = sites["spans_2019"].sum()
n_treat = sites["treatment"].sum()
n_ctrl  = sites["control"].sum()

print(f"""
╔══════════════════════════════════════════════════════════════╗
║         PLSS-BIRD SPATIAL JOIN SUMMARY                       ║
╠══════════════════════════════════════════════════════════════╣
║ Total RWI+AMPL sites (SJV bbox):       {n:>5}                ║
║ Sites with OP use in section (pre):    {pct(n_match, n):<20}║
║ Sites spanning 2019 (yr_min≤2018,      {pct(n_spans, n):<20}║
║   yr_max≥2020):                                              ║
╠══════════════════════════════════════════════════════════════╣
║  Pre-period OP lbs distribution (sites with >0 use):         ║""")

if len(nonzero_pre) > 0:
    print(f"║    n={len(nonzero_pre):>4}  min={nonzero_pre.min():>8.0f}  p25={nonzero_pre.quantile(0.25):>8.0f}  ║")
    print(f"║    median={nonzero_pre.median():>8.0f}  p75={nonzero_pre.quantile(0.75):>8.0f}  max={nonzero_pre.max():>8.0f} ║")

print(f"""╠══════════════════════════════════════════════════════════════╣
║ DiD-ready treatment sites             {pct(n_treat, n):<20}║
║   (high pre-OP, >50% drop post-2019)                         ║
║ Control sites (low/no OP)             {pct(n_ctrl, n):<20}║
╚══════════════════════════════════════════════════════════════╝""")

# Breakdown by project
print("\nBy project:")
print(sites.groupby("project")[["op_lbs_pre", "spans_2019", "treatment", "control"]].agg(
    sites=("op_lbs_pre", "count"),
    with_op=("op_lbs_pre", lambda x: (x > 0).sum()),
    spans_2019=("spans_2019", "sum"),
    treatment=("treatment", "sum"),
    control=("control", "sum"),
    median_op_lbs=("op_lbs_pre", "median"),
))

# OP lbs decile table
print("\nSite distribution across OP-lbs deciles (pre-period):")
sites["op_decile"] = pd.qcut(sites["op_lbs_pre"], q=10, labels=False, duplicates="drop")
print(sites.groupby("op_decile")["op_lbs_pre"].agg(["count", "min", "max"]).to_string())

sites.to_csv("/tmp/sites_plss_joined.csv", index=False)
print("\nFull results saved to /tmp/sites_plss_joined.csv")
