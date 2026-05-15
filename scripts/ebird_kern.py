#!/usr/bin/env python3
"""
eBird quick-look for Kern NWR and surrounding area.

Pulls recent observations and nearby hotspot info for aerial insectivores
around Kern National Wildlife Refuge (lat 35.65, lon -119.37).

Usage:
    export EBIRD_API_KEY=<your key>
    python ebird_kern.py
"""

import os
import sys
import requests
import pandas as pd
from collections import defaultdict

API_KEY = os.environ.get("EBIRD_API_KEY", "")
if not API_KEY:
    sys.exit("Set EBIRD_API_KEY environment variable before running.")

BASE = "https://api.ebird.org/v2"
HEADERS = {"X-eBirdApiToken": API_KEY}

# Kern NWR centroid
LAT, LON = 35.65, -119.37

# Aerial insectivore species codes (eBird 6-letter codes)
AERIAL_INSECTIVORES = {
    "treswa": "Tree Swallow",
    "barswa": "Barn Swallow",
    "cliswa": "Cliff Swallow",
    "nrwswa": "Northern Rough-winged Swallow",
    "purmar": "Purple Martin",
    "vigswa": "Violet-green Swallow",
    "banswa": "Bank Swallow",
    "chiswi": "Chimney Swift",
    "vauxsw": "Vaux's Swift",
    "comni2": "Common Nighthawk",
    "lesvio": "Lesser Nighthawk",
}


def get(endpoint, params=None):
    r = requests.get(f"{BASE}{endpoint}", headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# 1. Find nearby hotspots
# ---------------------------------------------------------------------------
print("=== NEARBY HOTSPOTS (50 km radius) ===")
hotspots = get("/ref/hotspot/geo", {"lat": LAT, "lng": LON, "dist": 50, "fmt": "json"})
hs_df = pd.DataFrame(hotspots)[["locId", "locName", "lat", "lng", "numSpeciesAllTime"]]
hs_df = hs_df.sort_values("numSpeciesAllTime", ascending=False)
print(hs_df.head(15).to_string(index=False))

# Find Kern NWR specifically
kern_hs = [h for h in hotspots if "kern" in h["locName"].lower() and "refuge" in h["locName"].lower()]
if not kern_hs:
    kern_hs = [h for h in hotspots if "kern" in h["locName"].lower() and "national" in h["locName"].lower()]
if kern_hs:
    kern_loc_id = kern_hs[0]["locId"]
    print(f"\nKern NWR hotspot: {kern_hs[0]['locName']}  ({kern_loc_id})")
else:
    # Fall back to first result
    kern_loc_id = hs_df.iloc[0]["locId"]
    print(f"\nKern NWR not found by name — using top hotspot: {hs_df.iloc[0]['locName']}")

# ---------------------------------------------------------------------------
# 2. Recent observations of aerial insectivores at Kern NWR
# ---------------------------------------------------------------------------
print("\n=== RECENT AERIAL INSECTIVORE OBSERVATIONS AT KERN NWR (30 days) ===")
recent = get(f"/data/obs/{kern_loc_id}/recent",
             {"back": 30, "includeProvisional": "true"})
recent_df = pd.DataFrame(recent) if recent else pd.DataFrame()
if not recent_df.empty and "speciesCode" in recent_df.columns:
    ai_recent = recent_df[recent_df["speciesCode"].isin(AERIAL_INSECTIVORES)]
    if not ai_recent.empty:
        cols = [c for c in ["comName", "howMany", "obsDt", "locName"] if c in ai_recent.columns]
        print(ai_recent[cols].sort_values("obsDt", ascending=False).to_string(index=False))
    else:
        print("No aerial insectivores in recent 30-day window.")
else:
    print("No recent observations returned.")

# ---------------------------------------------------------------------------
# 3. Aerial insectivores seen near Kern NWR this year (county-level)
# ---------------------------------------------------------------------------
print("\n=== AERIAL INSECTIVORES IN KERN COUNTY (recent 30 days) ===")
# Kern County eBird region code
kern_county = "US-CA-029"
county_recent = get(f"/data/obs/{kern_county}/recent",
                    {"back": 30, "includeProvisional": "true"})
county_df = pd.DataFrame(county_recent) if county_recent else pd.DataFrame()
if not county_df.empty and "speciesCode" in county_df.columns:
    ai_county = county_df[county_df["speciesCode"].isin(AERIAL_INSECTIVORES)]
    if not ai_county.empty:
        summary = (ai_county.groupby("comName")
                   .agg(max_count=("howMany", "max"), n_checklists=("subId", "nunique"))
                   .sort_values("max_count", ascending=False))
        print(summary.to_string())
    else:
        print("No aerial insectivores in recent county window.")
else:
    print("No county observations returned.")

# ---------------------------------------------------------------------------
# 4. Notable species near Kern NWR right now (all species, top counts)
# ---------------------------------------------------------------------------
print(f"\n=== TOP SPECIES NEAR KERN NWR BY COUNT (25 km, 14 days) ===")
nearby_obs = get("/data/obs/geo/recent",
                 {"lat": LAT, "lng": LON, "dist": 25, "back": 14,
                  "includeProvisional": "true"})
nearby_df = pd.DataFrame(nearby_obs) if nearby_obs else pd.DataFrame()
if not nearby_df.empty:
    top = (nearby_df.groupby("comName")["howMany"]
           .max()
           .sort_values(ascending=False)
           .head(20))
    print(top.to_string())
