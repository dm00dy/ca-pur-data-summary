#!/usr/bin/env python3
"""
SJV Pesticide-Gradient Map
==========================
Two-panel static figure for the CDPR proposal:
  Left:  Pre-period OP use (2015-2018) at township level
  Right: OP drop post-2019 at township level, with existing monitoring sites

Output: pur_analysis/sjv_gradient_map.png
"""

import io, re, math, zipfile, urllib.request
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
from pathlib import Path
import geopandas as gpd

CACHE_DIR  = Path("./pur_analysis/cache")
CHEM_LOOKUP = Path("./pur_analysis/chemical_lookup.csv")
OUT_FILE   = Path("./pur_analysis/sjv_gradient_map.png")

MERIDIANS = {"M": (37.87810, -121.91402)}
MILE_LAT  = 1.0 / 69.0
MILE_LON  = 1.0 / 54.6

SJV_COUNTIES_FIPS = {          # FIPS → name (for labelling)
    "06019": "Fresno",
    "06029": "Kern",
    "06031": "Kings",
    "06039": "Madera",
    "06047": "Merced",
    "06077": "San Joaquin",
    "06099": "Stanislaus",
    "06107": "Tulare",
}
SJV_PUR_CODES = [10, 15, 16, 20, 24, 39, 50, 54]   # CDPR county codes

MAP_EXTENT = (-122.1, -117.8, 34.8, 38.6)           # lon_min, lon_max, lat_min, lat_max

# ─────────────────────────────────────────────────────────────────────────────
# 1. Helper: PLSS township key → centroid
# ─────────────────────────────────────────────────────────────────────────────
_TWP_RE = re.compile(r'^([MSH])(\d{2})([NS])(\d{2})([EW])$')

def twp_centroid(twp_key):
    m = _TWP_RE.match(twp_key)
    if not m:
        return None, None
    mer, twp, tdir, rng, rdir = m.groups()
    twp, rng = int(twp), int(rng)
    orig_lat, orig_lon = MERIDIANS.get(mer, (None, None))
    if orig_lat is None:
        return None, None
    # township center: twp*6 + 3 miles in tdir, rng*6 - 3 miles in rdir
    lat = orig_lat + (-(twp * 6 + 3) if tdir == "S" else (twp * 6 - 3)) * MILE_LAT
    lon = orig_lon + (+(rng * 6 - 3) if rdir == "E" else -(rng * 6 - 3)) * MILE_LON
    return lat, lon


# ─────────────────────────────────────────────────────────────────────────────
# 2. Helper: PLSS township key → rectangle (lon_min, lon_max, lat_min, lat_max)
# ─────────────────────────────────────────────────────────────────────────────
def twp_rect(twp_key):
    m = _TWP_RE.match(twp_key)
    if not m:
        return None
    mer, twp, tdir, rng, rdir = m.groups()
    twp, rng = int(twp), int(rng)
    orig_lat, orig_lon = MERIDIANS.get(mer, (None, None))
    if orig_lat is None:
        return None
    if tdir == "S":
        lat_n = orig_lat - twp * 6 * MILE_LAT
        lat_s = lat_n - 6 * MILE_LAT
    else:
        lat_s = orig_lat + (twp * 6 - 6) * MILE_LAT
        lat_n = lat_s + 6 * MILE_LAT
    if rdir == "E":
        lon_e = orig_lon + rng * 6 * MILE_LON
        lon_w = lon_e - 6 * MILE_LON
    else:
        lon_w = orig_lon - rng * 6 * MILE_LON
        lon_e = lon_w + 6 * MILE_LON
    return lon_w, lon_e, lat_s, lat_n


# ─────────────────────────────────────────────────────────────────────────────
# 3. Load OP use by township from PUR archives
# ─────────────────────────────────────────────────────────────────────────────
def load_op_by_township(years):
    chem_df = pd.read_csv(CHEM_LOOKUP, dtype=str)
    op_codes = set(chem_df.loc[chem_df["class"].str.lower() == "organophosphates", "chem_code"])
    totals = {}
    for year in years:
        yy = str(year)[2:]
        with zipfile.ZipFile(CACHE_DIR / f"pur{year}.zip") as zf:
            name_map = {Path(n).name: n for n in zf.namelist()}
            for county in SJV_PUR_CODES:
                fname = f"udc{yy}_{county:02d}.txt"
                fp = name_map.get(fname)
                if not fp:
                    continue
                with zf.open(fp) as fh:
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
                df = df[df["chem_code"].isin(op_codes)]
                df = df[pd.to_numeric(df["site_code"], errors="coerce").fillna(99999) < 65000]
                df["lbs"] = pd.to_numeric(df["lbs_chm_used"], errors="coerce").fillna(0)
                df = df[df["lbs"] > 0]
                df["twp_key"] = df["comtrs"].str[2:9]
                for k, v in df.groupby("twp_key")["lbs"].sum().items():
                    totals[k] = totals.get(k, 0) + v
    return totals


# ─────────────────────────────────────────────────────────────────────────────
# 4. Load monitoring sites from MySQL
# ─────────────────────────────────────────────────────────────────────────────
def load_monitoring_sites():
    import mysql.connector
    conn = mysql.connector.connect(
        host="127.0.0.1", port=3366, user="root", password="password", database="ravian_wh"
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT ProjectCode, SamplingUnitId,
               AVG(DecimalLatitude)  AS lat,
               AVG(DecimalLongitude) AS lon,
               MIN(YearCollected)    AS yr_min,
               MAX(YearCollected)    AS yr_max
        FROM ravianpointcountbase_v1
        WHERE ProjectCode IN ('RWI', 'AMPL', 'WAFLS', 'CVRM', 'SJBR', 'RIVER_PARTNERS')
          AND DecimalLatitude  BETWEEN 34.8 AND 38.6
          AND DecimalLongitude BETWEEN -122.1 AND -117.8
          AND DecimalLatitude  IS NOT NULL
          AND DecimalLongitude IS NOT NULL
        GROUP BY ProjectCode, SamplingUnitId
    """)
    df = pd.DataFrame(cur.fetchall(),
                      columns=["project", "site_id", "lat", "lon", "yr_min", "yr_max"])
    conn.close()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
print("Loading PUR data …")
pre_op  = load_op_by_township([2015, 2016, 2017, 2018])
post_op = load_op_by_township([2020, 2021, 2022, 2023])
print(f"  {len(pre_op)} townships pre  /  {len(post_op)} townships post")

# build township table
all_twp = sorted(set(pre_op) | set(post_op))
twp_df = pd.DataFrame({
    "twp_key": all_twp,
    "pre_lbs":  [pre_op.get(t, 0)  for t in all_twp],
    "post_lbs": [post_op.get(t, 0) for t in all_twp],
})
twp_df["drop_pct"] = np.where(
    twp_df["pre_lbs"] > 0,
    100 * (twp_df["pre_lbs"] - twp_df["post_lbs"]) / twp_df["pre_lbs"],
    np.nan,
)
# add centroids and rectangles
twp_df[["lat_c", "lon_c"]] = twp_df["twp_key"].apply(
    lambda k: pd.Series(twp_centroid(k))
)
twp_df = twp_df.dropna(subset=["lat_c", "lon_c"])
# keep only SJV extent
lon_min, lon_max, lat_min, lat_max = MAP_EXTENT
twp_df = twp_df[
    twp_df["lat_c"].between(lat_min, lat_max) &
    twp_df["lon_c"].between(lon_min, lon_max)
]
print(f"  {len(twp_df)} townships in map extent")

print("Loading monitoring sites …")
sites = load_monitoring_sites()
sites = sites[
    sites["lat"].between(lat_min, lat_max) &
    sites["lon"].between(lon_min, lon_max)
]
print(f"  {len(sites)} monitoring sites")

print("Downloading CA county boundaries …")
ca_url = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "State_County/MapServer/1/query?where=STATE%3D%2706%27"
    "&outFields=GEOID,NAME&f=geojson&outSR=4326"
)
with urllib.request.urlopen(ca_url, timeout=30) as r:
    ca_gdf = gpd.read_file(io.BytesIO(r.read()))
sjv_gdf = ca_gdf[ca_gdf["GEOID"].isin(SJV_COUNTIES_FIPS)]
print(f"  {len(ca_gdf)} CA counties, {len(sjv_gdf)} SJV counties")


# ─────────────────────────────────────────────────────────────────────────────
# FIGURE
# ─────────────────────────────────────────────────────────────────────────────
print("Drawing map …")

fig, axes = plt.subplots(1, 2, figsize=(14, 9),
                         gridspec_kw={"wspace": 0.04})

HALF_LAT = 3 * MILE_LAT   # half-height of a township in degrees
HALF_LON = 3 * MILE_LON   # half-width

# colour norms
pre_vals = twp_df.loc[twp_df["pre_lbs"] > 0, "pre_lbs"]
norm_pre  = mcolors.LogNorm(vmin=max(pre_vals.min(), 1), vmax=pre_vals.max())
cmap_pre  = plt.cm.YlOrRd

drop_vals = twp_df.loc[twp_df["drop_pct"].notna(), "drop_pct"]
norm_drop = mcolors.Normalize(vmin=0, vmax=100)
cmap_drop = plt.cm.RdYlGn   # red=no drop, green=full drop

# site style by project
PROJ_STYLE = {
    "AMPL":           dict(marker="o", color="#1565C0", s=18, zorder=6, label="AMPL – Private Lands"),
    "RWI":            dict(marker="s", color="#388E3C", s=10, zorder=5, label="RWI – Rangeland"),
    "WAFLS":          dict(marker="^", color="#E65100", s=18, zorder=7, label="WAFLS – S-e Owl survey"),
    "CVRM":           dict(marker="D", color="#6A1B9A", s=16, zorder=6, label="CVRM – Riparian"),
    "SJBR":           dict(marker="P", color="#00695C", s=18, zorder=6, label="SJBR – San Joaquin BOR"),
    "RIVER_PARTNERS": dict(marker="*", color="#B71C1C", s=30, zorder=7, label="River Partners"),
}

for panel, ax in enumerate(axes):
    # ── base: all CA counties pale gray ──────────────────────────────────────
    ca_gdf.plot(ax=ax, color="#f0f0f0", edgecolor="#cccccc", linewidth=0.4)

    # ── SJV counties white fill + medium outline ──────────────────────────────
    sjv_gdf.plot(ax=ax, color="white", edgecolor="#555555", linewidth=0.9)

    # ── township rectangles ───────────────────────────────────────────────────
    for _, row in twp_df.iterrows():
        lw, le, ls, ln = (row.lon_c - HALF_LON, row.lon_c + HALF_LON,
                          row.lat_c - HALF_LAT, row.lat_c + HALF_LAT)

        if panel == 0:
            # Left panel: pre-period OP intensity
            if row["pre_lbs"] > 0:
                face = cmap_pre(norm_pre(row["pre_lbs"]))
                alpha = 0.85
            else:
                face = "#e8e8e8"
                alpha = 0.5
        else:
            # Right panel: OP drop %
            if pd.notna(row["drop_pct"]):
                face = cmap_drop(norm_drop(row["drop_pct"]))
                alpha = 0.88
            elif row["post_lbs"] > 0:
                # new OP user post-2019 (no pre-period baseline) — light yellow
                face = "#fffde7"
                alpha = 0.7
            else:
                # never had OP use in either period
                face = "#eeeeee"
                alpha = 0.35

        rect = mpatches.Rectangle(
            (lw, ls), le - lw, ln - ls,
            linewidth=0, facecolor=face, alpha=alpha
        )
        ax.add_patch(rect)

    # ── SJV county outlines (draw again on top) ───────────────────────────────
    sjv_gdf.plot(ax=ax, color="none", edgecolor="#333333", linewidth=1.1)

    # ── county name labels (SJV only) ────────────────────────────────────────
    for _, row in sjv_gdf.iterrows():
        cx = row.geometry.centroid.x
        cy = row.geometry.centroid.y
        if lon_min < cx < lon_max and lat_min < cy < lat_max:
            ax.text(cx, cy, row["NAME"].replace(" County", ""),
                    fontsize=8.5, ha="center", va="center",
                    color="#222222", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.75, ec="none"))

    # ── monitoring sites (right panel only) ──────────────────────────────────
    if panel == 1:
        for proj, style in PROJ_STYLE.items():
            sub = sites[sites["project"] == proj]
            if sub.empty:
                continue
            ax.scatter(sub["lon"], sub["lat"],
                       marker=style["marker"], c=style["color"],
                       s=style["s"], zorder=style["zorder"],
                       linewidths=0.3, edgecolors="white", alpha=0.85)

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.set_xlabel("Longitude", fontsize=8)
    if panel == 0:
        ax.set_ylabel("Latitude", fontsize=8)
    else:
        ax.set_yticklabels([])

# ── Panel titles ─────────────────────────────────────────────────────────────
axes[0].set_title(
    "A.  Pre-period OP use (2015–2018)\nby PLSS township (6 × 6 mile grid)",
    fontsize=10, loc="left", pad=8
)
axes[1].set_title(
    "B.  OP use decline post-2019 &\nexisting bird monitoring sites",
    fontsize=10, loc="left", pad=8
)

# ── Colorbars ─────────────────────────────────────────────────────────────────
# Left: log-scale lbs
sm_pre = plt.cm.ScalarMappable(norm=norm_pre, cmap=cmap_pre)
sm_pre.set_array([])
cb_pre = fig.colorbar(sm_pre, ax=axes[0], fraction=0.035, pad=0.02,
                      orientation="vertical", shrink=0.65)
cb_pre.set_label("OP lbs applied (log scale)", fontsize=8)
cb_pre.ax.tick_params(labelsize=7)

# Right: percent drop
sm_drop = plt.cm.ScalarMappable(norm=norm_drop, cmap=cmap_drop)
sm_drop.set_array([])
cb_drop = fig.colorbar(sm_drop, ax=axes[1], fraction=0.035, pad=0.02,
                       orientation="vertical", shrink=0.65)
cb_drop.set_label("OP use decline post-2019 (%)", fontsize=8)
cb_drop.ax.tick_params(labelsize=7)

# ── Legend for monitoring sites (right panel) ─────────────────────────────────
legend_elements = [
    Line2D([0], [0], marker=PROJ_STYLE[p]["marker"], color="w",
           markerfacecolor=PROJ_STYLE[p]["color"],
           markersize=7 if p != "RIVER_PARTNERS" else 9,
           label=PROJ_STYLE[p]["label"])
    for p in PROJ_STYLE
    if not sites[sites["project"] == p].empty
]
axes[1].legend(handles=legend_elements, loc="upper right",
               fontsize=7.5, framealpha=0.9, edgecolor="#aaaaaa",
               title="Bird monitoring projects", title_fontsize=8)

# ── Overall caption ───────────────────────────────────────────────────────────
fig.text(
    0.5, 0.01,
    "Each colored tile = one PLSS township (6 × 6 miles). "
    "Gray tiles = townships in SJV counties with no recorded OP use.\n"
    "OP = organophosphate insecticides (CDPR PUR). "
    "Monitoring sites shown are point-count stations from the ravian_wh data warehouse.",
    ha="center", va="bottom", fontsize=7, color="#555555"
)

OUT_FILE.parent.mkdir(exist_ok=True)
fig.savefig(OUT_FILE, dpi=180, bbox_inches="tight", facecolor="white")
print(f"\nSaved → {OUT_FILE}")
