#!/usr/bin/env python3
"""
Download California protected-lands polygons from two authoritative sources:

  1. USFWS — National Wildlife Refuge System Boundaries (federal)
     National Wildlife Refuges, hatcheries, WMAs, etc.

  2. CDFW BIOS — CDFW Owned and Operated Lands [ds3092] (state)
     State Wildlife Areas (e.g. Mendota WA), Ecological Reserves, etc.

The federal NWRs and state Wildlife Areas / Ecological Reserves together
cover the conservation footprint that intersects California's agricultural
landscape — including the Grassland Ecological Area complex around
Mendota/Tranquillity, which is mostly CDFW-managed.

Output:
    spatial/data/protected_lands_ca.gpkg
        Columns: name, type, agency ('USFWS'|'CDFW'), geometry (EPSG:4326)

Usage:
    source .venv/bin/activate
    python download_nwr.py
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape

USFWS_URL = (
    "https://services.arcgis.com/QVENGdaPbd4LUkLV/ArcGIS/rest/services/"
    "National_Wildlife_Refuge_System_Boundaries/FeatureServer/0"
)
CDFW_URL = (
    "https://services2.arcgis.com/Uq9r85Potqm3MfRV/arcgis/rest/services/"
    "biosds3092_fpu/FeatureServer/0"
)
OUT_PATH = Path("./spatial/data/protected_lands_ca.gpkg")

CA_BBOX = "-125.0,32.0,-114.0,42.5"

# USFWS Realty Status Land types worth showing
USFWS_TYPES = {"NWR", "WMA", "WPA", "NFH", "CA"}
# CDFW property types worth showing — wildlife areas and ecological reserves
CDFW_TYPES = {"Wildlife Area", "Ecological Reserve"}


def _query_features(url: str, params: dict) -> list[dict]:
    r = requests.get(url + "/query", params=params, timeout=120)
    r.raise_for_status()
    return r.json().get("features", [])


def fetch_usfws() -> gpd.GeoDataFrame:
    print("Querying USFWS for NWRs / WMAs / hatcheries in CA ...")
    feats = _query_features(USFWS_URL, {
        "where": "1=1",
        "geometry": CA_BBOX,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "ORGNAME,RSL_TYPE,FWSREGION",
        "outSR": "4326",
        "returnGeometry": "true",
        "f": "geojson",
    })
    rows = []
    for f in feats:
        p = f["properties"]
        if p.get("RSL_TYPE") not in USFWS_TYPES:
            continue
        try:
            geom = shape(f["geometry"])
        except Exception:
            continue
        if geom.is_empty:
            continue
        rows.append({
            "name":   p.get("ORGNAME", ""),
            "type":   p.get("RSL_TYPE", ""),
            "agency": "USFWS",
            "geometry": geom,
        })
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.dissolve(by="name", aggfunc="first").reset_index()
    print(f"  Got {len(gdf)} unique USFWS units")
    return gdf


def fetch_cdfw() -> gpd.GeoDataFrame:
    print("Querying CDFW BIOS for state wildlife areas / ecological reserves ...")
    # Page through 2000-record limit
    all_feats = []
    offset = 0
    while True:
        feats = _query_features(CDFW_URL, {
            "where": "PROP_TYPE IN ('Wildlife Area','Ecological Reserve')",
            "outFields": "Name,PROP_TYPE,REGION",
            "outSR": "4326",
            "returnGeometry": "true",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 2000,
        })
        if not feats:
            break
        all_feats.extend(feats)
        if len(feats) < 2000:
            break
        offset += 2000
    print(f"  Returned {len(all_feats)} raw features (multiple polygons per unit)")
    rows = []
    for f in all_feats:
        p = f["properties"]
        if p.get("PROP_TYPE") not in CDFW_TYPES:
            continue
        try:
            geom = shape(f["geometry"])
        except Exception:
            continue
        if geom.is_empty:
            continue
        rows.append({
            "name":   p.get("Name", ""),
            "type":   p.get("PROP_TYPE", ""),
            "agency": "CDFW",
            "geometry": geom,
        })
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.dissolve(by="name", aggfunc="first").reset_index()
    print(f"  Got {len(gdf)} unique CDFW units after dissolve")
    return gdf


def main() -> None:
    usfws = fetch_usfws()
    cdfw  = fetch_cdfw()

    combined = pd.concat([usfws, cdfw], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")
    print(f"\nCombined: {len(combined)} units "
          f"({(combined['agency']=='USFWS').sum()} federal + "
          f"{(combined['agency']=='CDFW').sum()} state)")

    print("\nType breakdown:")
    print(combined.groupby(["agency","type"]).size().to_string())

    print("\nKey units present for proposal context:")
    for kw in ["MENDOTA","KERN","MERCED","SAN LUIS","GRASSLAND","VOLTA","KESTERSON","PIXLEY","COLUSA","SACRAMENTO","SUTTER"]:
        m = combined[combined["name"].str.upper().str.contains(kw, na=False)]
        for _, r in m.iterrows():
            print(f"  {r['agency']:6s} {r['type']:18s} {r['name']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists():
        OUT_PATH.unlink()
    combined.to_file(OUT_PATH, driver="GPKG")
    print(f"\nWrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
