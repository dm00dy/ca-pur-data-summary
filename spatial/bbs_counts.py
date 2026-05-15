"""
bbs_counts.py — Download BBS count data and join to pesticide exposure wide table.

Downloads States.zip, weather.csv, and SpeciesList.txt from ScienceBase,
extracts California aerial insectivore counts (2015–2022), uses weather.csv
to distinguish "surveyed but zero detections" (→ 0) from "not surveyed" (→ NaN),
and joins to bbs_exposure_yearly_wide.csv to produce the Level 1 model input.

Output: outputs/level1_model_input.csv

AOU codes verified against SpeciesList.txt from the same ScienceBase item
(https://www.sciencebase.gov/catalog/item/64ad9c3dd34e70357a292cee).
Dataset covers 1966–2022; 2023 exposure rows are retained but count columns
will be NaN (no survey data available yet).
"""

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests

SB_ITEM = "64ad9c3dd34e70357a292cee"
SB_BASE = "https://www.sciencebase.gov/catalog/file/get"

DATA_DIR = Path("data/bbs")
OUT_DIR = Path("outputs")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Focal species — AOU codes verified against BBS SpeciesList.txt
# ---------------------------------------------------------------------------
AERIAL_INSECTIVORES = {
    # Nightjars (Caprimulgidae)
    4180: "Common Poorwill",
    4200: "Common Nighthawk",
    4210: "Lesser Nighthawk",      # common in Imperial Valley / desert CA
    # Swifts (Apodidae)
    4220: "Black Swift",
    4230: "Chimney Swift",
    4240: "Vaux's Swift",
    4250: "White-throated Swift",
    # Swallows (Hirundinidae)
    6110: "Purple Martin",
    6120: "Cliff Swallow",
    6130: "Barn Swallow",
    6140: "Tree Swallow",
    6150: "Violet-green Swallow",
    6160: "Bank Swallow",
    6170: "Northern Rough-winged Swallow",
    # Aerial-foraging flycatchers (secondary group)
    4440: "Eastern Kingbird",
    4470: "Western Kingbird",
    4480: "Cassin's Kingbird",
    4570: "Say's Phoebe",
    4580: "Black Phoebe",
    4590: "Olive-sided Flycatcher",
    4620: "Western Wood-Pewee",
}

SWALLOWS   = {6110, 6120, 6130, 6140, 6150, 6160, 6170}
SWIFTS     = {4220, 4230, 4240, 4250}
NIGHTJARS  = {4180, 4200, 4210}
FLYCATCHERS = {4440, 4470, 4480, 4570, 4580, 4590, 4620}

CA_STATE_NUM = 14
YEARS = range(2015, 2024)   # exposure years; counts only available through 2022


def _download(name: str, dest: Path, force: bool = False) -> Path:
    if dest.exists() and not force:
        print(f"  {name}: cached ({dest.stat().st_size // 1024:,} KB)")
        return dest
    url = f"{SB_BASE}/{SB_ITEM}?name={name}"
    print(f"  {name}: downloading ...", end="", flush=True)
    r = requests.get(url, timeout=300, stream=True)
    r.raise_for_status()
    with dest.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    print(f" done ({dest.stat().st_size // 1024:,} KB)")
    return dest


def load_valid_surveys(weather_csv: Path) -> set:
    """
    Return set of (StateNum, Route, Year) for CA routes with RunType=1
    (valid survey). Used to distinguish zero-detection rows from unsurveyed.
    """
    print("\nLoading weather.csv for valid survey list ...")
    df = pd.read_csv(
        weather_csv,
        usecols=["StateNum", "Route", "Year", "RunType"],
        dtype={"StateNum": "Int16", "Route": "Int16",
               "Year": "Int16", "RunType": "Int16"},
    )
    ca = df[(df["StateNum"] == CA_STATE_NUM) & (df["RunType"] == 1)]
    surveyed = set(zip(ca["Route"].astype(int), ca["Year"].astype(int)))
    print(f"  {len(surveyed):,} valid CA surveys (route × year)")
    return surveyed


def load_ca_counts(states_zip: Path) -> pd.DataFrame:
    """
    Extract California aerial insectivore counts from States.zip.

    Returns long-format DataFrame: Route, Year, AOU, SpeciesTotal
    filtered to CA, focal AOU codes, and years 2015–2023.
    """
    print("\nParsing States.zip for California aerial insectivores ...")
    focal_set = set(AERIAL_INSECTIVORES.keys())
    year_set = set(YEARS)
    chunks = []

    with zipfile.ZipFile(states_zip) as zf:
        ca_file = next(n for n in zf.namelist() if "califor" in n.lower())
        print(f"  Reading {ca_file} ...")
        with zf.open(ca_file) as f:
            for chunk in pd.read_csv(
                f, chunksize=100_000,
                usecols=lambda c: c in {
                    "StateNum", "Route", "RPID", "Year", "AOU", "SpeciesTotal",
                },
                dtype={
                    "StateNum": "Int16", "Route": "Int16", "RPID": "Int16",
                    "Year": "Int16", "AOU": "Int32", "SpeciesTotal": "Int32",
                },
                low_memory=False,
            ):
                mask = (
                    (chunk["AOU"].isin(focal_set)) &
                    (chunk["Year"].isin(year_set))
                )
                sub = chunk[mask].copy()
                if len(sub):
                    chunks.append(sub)

    if not chunks:
        raise RuntimeError("No CA focal-species records found")

    df = pd.concat(chunks, ignore_index=True)
    print(f"  {len(df):,} records — {df['Route'].nunique()} routes, "
          f"{df['Year'].nunique()} years, {df['AOU'].nunique()} species")
    return df


def aggregate_counts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot long counts to wide (Route × Year), adding per-species and
    group-total columns. Sums across RPID variants within a route-year.
    """
    base = (
        df.groupby(["Route", "Year", "AOU"], as_index=False)["SpeciesTotal"]
        .sum()
    )

    wide = base.pivot_table(
        index=["Route", "Year"], columns="AOU",
        values="SpeciesTotal", fill_value=0,
    ).reset_index()
    wide.columns.name = None

    def _safe(name: str) -> str:
        return "cnt_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    rename = {aou: _safe(name)
              for aou, name in AERIAL_INSECTIVORES.items()
              if aou in wide.columns}
    wide.rename(columns=rename, inplace=True)

    def _group_sum(aou_set):
        cols = [_safe(AERIAL_INSECTIVORES[a]) for a in aou_set
                if _safe(AERIAL_INSECTIVORES[a]) in wide.columns]
        return wide[cols].sum(axis=1) if cols else 0

    wide["cnt_swallows_total"]            = _group_sum(SWALLOWS)
    wide["cnt_swifts_total"]              = _group_sum(SWIFTS)
    wide["cnt_nightjars_total"]           = _group_sum(NIGHTJARS)
    wide["cnt_flycatchers_total"]         = _group_sum(FLYCATCHERS)
    wide["cnt_aerial_insectivores_total"] = (
        wide["cnt_swallows_total"] +
        wide["cnt_swifts_total"] +
        wide["cnt_nightjars_total"] +
        wide["cnt_flycatchers_total"]
    )

    return wide


def zero_fill_surveyed(counts_wide: pd.DataFrame,
                       valid_surveys: set,
                       exposure: pd.DataFrame) -> pd.DataFrame:
    """
    For every exposure row, decide:
      - matched in counts_wide → use count values
      - not matched, but (route, year) in valid_surveys → 0 (detected nothing)
      - not matched, not in valid_surveys → NaN (not surveyed / no data)
    """
    cnt_cols = [c for c in counts_wide.columns if c.startswith("cnt_")]

    # Build lookup: (route, year) → count row
    counts_idx = counts_wide.set_index(["Route", "Year"])

    rows = []
    for _, row in exposure.iterrows():
        route = row["_route"]
        year  = row["_year"]
        key   = (route, year)

        new_row = row.to_dict()
        if key in counts_idx.index:
            # direct match — use values from counts
            cdata = counts_idx.loc[key]
            for c in cnt_cols:
                new_row[c] = int(cdata[c]) if c in cdata else 0
        elif key in valid_surveys:
            # surveyed but no focal species detected
            for c in cnt_cols:
                new_row[c] = 0
        else:
            # no survey data (2020 COVID suspension, 2023 after cutoff, or
            # route not run that year)
            for c in cnt_cols:
                new_row[c] = None

        rows.append(new_row)

    return pd.DataFrame(rows)


def main():
    print("=== BBS counts → Level 1 model input ===\n")

    # 1. Download
    print("Downloading BBS data files ...")
    states_zip  = _download("States.zip",      DATA_DIR / "States.zip")
    weather_csv = _download("weather.csv",     DATA_DIR / "weather.csv")
    _download("SpeciesList.txt", DATA_DIR / "SpeciesList.txt")

    # 2. Valid surveys
    valid_surveys = load_valid_surveys(weather_csv)

    # 3. Load CA counts
    ca_counts = load_ca_counts(states_zip)

    # 4. Aggregate to wide
    counts_wide = aggregate_counts(ca_counts)
    cnt_cols = [c for c in counts_wide.columns if c.startswith("cnt_")]
    print(f"\nCounts wide: {len(counts_wide)} route-year rows, "
          f"{len(cnt_cols)} count columns")

    # Annual CA totals summary
    year_summary = counts_wide.groupby("Year")[
        ["cnt_swallows_total", "cnt_swifts_total",
         "cnt_nightjars_total", "cnt_aerial_insectivores_total"]
    ].sum()
    print("\nCA annual totals across all BBS routes:")
    print(year_summary.to_string())

    # 5. Load exposure wide table
    print("\nLoading exposure wide table ...")
    exposure = pd.read_csv(OUT_DIR / "bbs_exposure_yearly_wide.csv")
    exposure["_route"] = exposure["location_id"].str.split("_").str[2].astype(int)
    exposure["_year"]  = exposure["location_id"].str.split("_").str[-1].astype(int)
    print(f"  {len(exposure)} rows × {len(exposure.columns)} columns")

    # Pre-populate count cols as NaN so zero_fill_surveyed can fill them
    for c in cnt_cols:
        exposure[c] = None

    # 6. Zero-fill and join
    joined = zero_fill_surveyed(counts_wide, valid_surveys, exposure)
    joined.drop(columns=["_route", "_year"], inplace=True)

    # 7. Reporting
    n_total   = len(joined)
    n_matched = (joined["cnt_aerial_insectivores_total"].notna() &
                 (joined["cnt_aerial_insectivores_total"] > 0)).sum()
    n_zero    = (joined["cnt_aerial_insectivores_total"] == 0).sum()
    n_null    = joined["cnt_aerial_insectivores_total"].isna().sum()

    print(f"\nJoin summary ({n_total} rows):")
    print(f"  {n_matched:3d}  detected ≥1 focal species")
    print(f"  {n_zero:3d}  surveyed, zero focal species detected")
    print(f"  {n_null:3d}  no survey data (2020 COVID / 2023 cutoff / route not run)")

    # Routes with no data across all years
    by_route = joined.groupby(
        joined["location_id"].str.rsplit("_", n=1).str[0]
    )["cnt_aerial_insectivores_total"].apply(lambda s: s.notna().sum())
    dead_routes = by_route[by_route == 0].index.tolist()
    if dead_routes:
        print(f"\n  Routes with zero survey matches across all years:")
        for r in dead_routes:
            print(f"    {r}")

    # 8. Save
    out_path = OUT_DIR / "level1_model_input.csv"
    joined.to_csv(out_path, index=False)
    print(f"\n{len(joined)} rows × {len(joined.columns)} columns → {out_path}")

    # 9. Top routes by mean annual count (surveyed years only)
    print("\nTop 15 routes by mean annual aerial insectivore count (surveyed years):")
    tmp = joined[joined["cnt_aerial_insectivores_total"].notna()].copy()
    tmp["route_base"] = tmp["location_id"].str.rsplit("_", n=1).str[0]
    top = (
        tmp.groupby("route_base")["cnt_aerial_insectivores_total"]
        .mean()
        .sort_values(ascending=False)
        .head(15)
    )
    for route, val in top.items():
        print(f"  {route:<40} {val:6.1f}")

    # 10. Species breakdown for top routes
    print("\nSpecies group breakdown — top 5 routes (mean annual count):")
    top5 = top.head(5).index.tolist()
    group_cols = ["cnt_swallows_total", "cnt_swifts_total",
                  "cnt_nightjars_total", "cnt_flycatchers_total",
                  "cnt_aerial_insectivores_total"]
    tmp5 = tmp[tmp["route_base"].isin(top5)].groupby("route_base")[group_cols].mean()
    print(tmp5.round(1).to_string())

    print("\nDone.")


if __name__ == "__main__":
    main()
