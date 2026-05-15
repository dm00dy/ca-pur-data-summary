#!/usr/bin/env python3
"""
Historical swallow counts at Kern NWR — eBird historic observations pull.

The /product/lists endpoint only returns recent checklists regardless of
page number. Instead, this script queries /data/obs/{locId}/historic/{y}/{m}/{d}
for sample dates in each breeding season (Apr–Aug) from 2015 to present,
across the three Kern NWR hotspots.

Usage:
    export EBIRD_API_KEY=<your key>
    python ebird_kern_history.py
"""

import os, sys, time
import requests
import pandas as pd
import matplotlib.pyplot as plt

API_KEY = os.environ.get("EBIRD_API_KEY", "")
if not API_KEY:
    sys.exit("Set EBIRD_API_KEY environment variable before running.")

BASE = "https://api.ebird.org/v2"
HEADERS = {"X-eBirdApiToken": API_KEY}

KERN_HOTSPOTS = {
    "L628412":  "Kern NWR",
    "L1481043": "Kern NWR--North Auto Tour",
    "L2520115": "Kern NWR--South Auto Tour",
}

AERIAL_INSECTIVORES = {
    "treswa": "Tree Swallow",
    "barswa": "Barn Swallow",
    "cliswa": "Cliff Swallow",
    "nrwswa": "Northern Rough-winged Swallow",
    "purmar": "Purple Martin",
    "vigswa": "Violet-green Swallow",
    "banswa": "Bank Swallow",
    "comni2": "Common Nighthawk",
    "lesvio": "Lesser Nighthawk",
}

YEARS = list(range(2015, 2026))
# Every day of May — denser smoke test
SAMPLE_DATES = [(5, d) for d in range(1, 32)]


def get(endpoint, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE}{endpoint}", headers=HEADERS,
                             params=params, timeout=20)
            if r.status_code == 429:
                print("  rate limited — sleeping 10s")
                time.sleep(10)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"  failed: {e}")
                return []
            time.sleep(1)
    return []


# ---------------------------------------------------------------------------
# Main pull — historic endpoint
# ---------------------------------------------------------------------------

all_records = []

total_queries = len(KERN_HOTSPOTS) * len(YEARS) * len(SAMPLE_DATES)
done = 0

for loc_id, loc_name in KERN_HOTSPOTS.items():
    print(f"\n--- {loc_name} ---")
    for year in YEARS:
        for month, day in SAMPLE_DATES:
            obs_list = get(f"/data/obs/{loc_id}/historic/{year}/{month}/{day}",
                           {"includeProvisional": "true"})
            done += 1
            if not obs_list:
                continue

            for obs in obs_list:
                sc = obs.get("speciesCode", "")
                if sc not in AERIAL_INSECTIVORES:
                    continue
                how_many = obs.get("howMany")
                count = int(how_many) if how_many else 1

                all_records.append({
                    "year": year,
                    "month": month,
                    "date": f"{year}-{month:02d}-{day:02d}",
                    "loc": loc_name,
                    "speciesCode": sc,
                    "species": AERIAL_INSECTIVORES[sc],
                    "count": count,
                })

            time.sleep(0.1)

        print(f"  {year}: {sum(1 for r in all_records if r['year']==year and r['loc']==loc_name)} AI obs", flush=True)

print(f"\nTotal aerial insectivore records: {len(all_records)}")

if not all_records:
    print("No data collected — exiting.")
    sys.exit(0)

# ---------------------------------------------------------------------------
# Aggregate and report
# ---------------------------------------------------------------------------

df = pd.DataFrame(all_records)

print("\n=== MAX COUNT PER SPECIES PER YEAR (breeding season) ===")
annual_max = (df.groupby(["year", "species"])["count"]
              .max()
              .unstack(fill_value=0)
              .sort_index())
print(annual_max.to_string())

print("\n=== CHECKLIST FREQUENCY (years with any AI record) ===")
freq = (df.groupby(["year", "species"])
        .agg(n_checklists=("date", "nunique"),
             max_count=("count", "max"),
             mean_count=("count", "mean"))
        .round(1))
print(freq.to_string())

# Save CSV
out_csv = "pur_analysis/kern_nwr_aerial_insectivores.csv"
df.to_csv(out_csv, index=False)
print(f"\nRaw records saved to {out_csv}")

# ---------------------------------------------------------------------------
# Chart: max annual count per species
# ---------------------------------------------------------------------------

focus = ["Tree Swallow", "Cliff Swallow", "Barn Swallow",
         "Northern Rough-winged Swallow", "Purple Martin"]
colors = ["#4c78a8", "#f58518", "#e45756", "#72b7b2", "#9d755d"]

fig, ax = plt.subplots(figsize=(10, 5))
for sp, color in zip(focus, colors):
    if sp not in annual_max.columns:
        continue
    series = annual_max[sp].replace(0, float("nan"))
    ax.plot(series.index, series.values, marker="o", label=sp,
            color=color, linewidth=2)

# Oxamyl ramp reference
ax.axvspan(2018.5, 2019.5, alpha=0.08, color="gray")
ax.text(2019.6, ax.get_ylim()[1] * 0.95 if ax.get_ylim()[1] > 0 else 10,
        "chlorpyrifos\nphase-out", fontsize=8, va="top", alpha=0.6)

ax.set_xlabel("Year")
ax.set_ylabel("Max single-count (breeding season Apr–Aug)")
ax.set_title("Aerial insectivores at Kern NWR — breeding season peak counts")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
fig.tight_layout()
chart_out = "pur_analysis/kern_nwr_swallow_trend.png"
fig.savefig(chart_out, dpi=150)
plt.close(fig)
print(f"Chart saved to {chart_out}")
