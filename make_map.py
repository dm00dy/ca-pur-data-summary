#!/usr/bin/env python3
"""
Interactive California pesticide application map.

Produces a self-contained HTML file — open directly in any browser.
No web server or Docker required; Plotly JS and all data are embedded.

Usage:
    source .venv/bin/activate
    python make_map.py
    # then open pur_analysis/pesticide_map.html in any browser

Shows:
  - County choropleth: pyrethroid share of tracked insecticide lbs,
    animated 2015–2023 (pyrethroid + chlorpyrifos + oxamyl tracked)
  - Hover detail: lbs for all three chemicals per county per year
  - Blue dots: BBS monitoring routes, sized by 5km pesticide exposure
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests
import plotly.graph_objects as go

OUTPUT_DIR = Path("./pur_analysis")
COUNTY_CSV = OUTPUT_DIR / "pur_county_by_class.csv"
BBS_CSV = Path("./spatial/outputs/bbs_locations.csv")
GEOJSON_CACHE = Path("/tmp/ca_counties.geojson")
GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
MAP_OUTPUT = OUTPUT_DIR / "pesticide_map.html"

# CDPR sequential county code (01–58, alphabetical) → 5-digit FIPS
# California FIPS: state=06, county portion = sequential odd numbers in alpha order
# Formula: cdpr_code N  →  06 + zero-padded(2N - 1)
def cdpr_to_fips(code: int) -> str:
    return f"06{(code * 2 - 1):03d}"

COUNTY_NAMES: dict[int, str] = {
    1: "Alameda", 2: "Alpine", 3: "Amador", 4: "Butte",
    5: "Calaveras", 6: "Colusa", 7: "Contra Costa", 8: "Del Norte",
    9: "El Dorado", 10: "Fresno", 11: "Glenn", 12: "Humboldt",
    13: "Imperial", 14: "Inyo", 15: "Kern", 16: "Kings",
    17: "Lake", 18: "Lassen", 19: "Los Angeles", 20: "Madera",
    21: "Marin", 22: "Mariposa", 23: "Mendocino", 24: "Merced",
    25: "Modoc", 26: "Mono", 27: "Monterey", 28: "Napa",
    29: "Nevada", 30: "Orange", 31: "Placer", 32: "Plumas",
    33: "Riverside", 34: "Sacramento", 35: "San Benito", 36: "San Bernardino",
    37: "San Diego", 38: "San Francisco", 39: "San Joaquin", 40: "San Luis Obispo",
    41: "San Mateo", 42: "Santa Barbara", 43: "Santa Clara", 44: "Santa Cruz",
    45: "Shasta", 46: "Sierra", 47: "Siskiyou", 48: "Solano",
    49: "Sonoma", 50: "Stanislaus", 51: "Sutter", 52: "Tehama",
    53: "Trinity", 54: "Tulare", 55: "Tuolumne", 56: "Ventura",
    57: "Yolo", 58: "Yuba",
}


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------

def fetch_ca_geojson() -> dict:
    """Fetch California county GeoJSON (Plotly's FIPS dataset), cache locally."""
    if GEOJSON_CACHE.exists():
        with open(GEOJSON_CACHE) as f:
            return json.load(f)

    print("Fetching California county boundaries from Plotly dataset CDN ...")
    r = requests.get(GEOJSON_URL, timeout=60)
    r.raise_for_status()
    full = r.json()
    ca = {
        "type": "FeatureCollection",
        "features": [feat for feat in full["features"] if feat["id"].startswith("06")],
    }
    with open(GEOJSON_CACHE, "w") as f:
        json.dump(ca, f)
    print(f"  {len(ca['features'])} California counties cached")
    return ca


def prepare_county_data() -> pd.DataFrame:
    """Pivot raw county CSV into one row per (year, county) with per-chemical columns."""
    df = pd.read_csv(COUNTY_CSV)
    df["county"] = pd.to_numeric(df["county"], errors="coerce").dropna().astype(int)
    df = df.dropna(subset=["county"])

    df["fips"] = df["county"].apply(cdpr_to_fips)
    df["county_name"] = df["county"].apply(lambda c: COUNTY_NAMES.get(int(c), f"County {c}"))

    pivot = df.pivot_table(
        index=["year", "fips", "county_name"],
        columns="class",
        values="lbs",
        aggfunc="sum",
    ).reset_index()
    pivot.columns.name = None

    for col in ["chlorpyrifos", "oxamyl", "pyrethroid"]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    pivot = pivot.fillna(0.0)

    pivot["total_lbs"] = pivot["chlorpyrifos"] + pivot["oxamyl"] + pivot["pyrethroid"]
    pivot["pyr_pct"] = (
        pivot["pyrethroid"] / pivot["total_lbs"].replace(0, float("nan")) * 100
    ).fillna(0.0).round(1)

    pivot["hover"] = pivot.apply(
        lambda r: (
            f"<b>{r['county_name']} County — {r['year']}</b><br>"
            f"Pyrethroid:    {r['pyrethroid']:>10,.0f} lbs  ({r['pyr_pct']:.0f}%)<br>"
            f"Chlorpyrifos: {r['chlorpyrifos']:>10,.0f} lbs<br>"
            f"Oxamyl:        {r['oxamyl']:>10,.0f} lbs<br>"
            f"Total tracked: {r['total_lbs']:>9,.0f} lbs"
        ),
        axis=1,
    )

    pivot["year"] = pivot["year"].astype(str)
    return pivot


def load_bbs() -> pd.DataFrame | None:
    if not BBS_CSV.exists():
        print(f"  BBS locations not found at {BBS_CSV}, skipping point layer")
        return None
    df = pd.read_csv(BBS_CSV)
    df["label"] = df.apply(
        lambda r: (
            f"<b>BBS {r['RouteName']}</b><br>"
            f"5 km exposure: {r['lbs_ai_5km']:,.0f} lbs AI"
        ),
        axis=1,
    )
    return df


# ---------------------------------------------------------------------------
# MAP ASSEMBLY
# ---------------------------------------------------------------------------

def choropleth_trace(yr_df: pd.DataFrame, geojson: dict) -> go.Choropleth:
    return go.Choropleth(
        geojson=geojson,
        featureidkey="id",
        locations=yr_df["fips"],
        z=yr_df["pyr_pct"],
        text=yr_df["hover"],
        hovertemplate="%{text}<extra></extra>",
        colorscale="YlOrRd",
        zmin=0,
        zmax=100,
        colorbar=dict(
            title=dict(text="Pyrethroid<br>share (%)", side="right"),
            thickness=14,
            len=0.6,
            y=0.55,
        ),
        marker_line_color="white",
        marker_line_width=0.6,
    )


def build_figure(county_df: pd.DataFrame, geojson: dict, bbs: pd.DataFrame | None) -> go.Figure:
    years = sorted(county_df["year"].unique())

    # Initial data (first year)
    yr0 = county_df[county_df["year"] == years[0]]
    traces: list[go.BaseTraceType] = [choropleth_trace(yr0, geojson)]

    # BBS point layer (static — same for all years)
    if bbs is not None:
        max_exp = bbs["lbs_ai_5km"].max()
        traces.append(
            go.Scattergeo(
                lat=bbs["latitude"],
                lon=bbs["longitude"],
                mode="markers",
                marker=dict(
                    size=(bbs["lbs_ai_5km"] / max_exp * 18 + 5).round(1),
                    color="steelblue",
                    opacity=0.85,
                    line=dict(width=1, color="white"),
                ),
                text=bbs["label"],
                hovertemplate="%{text}<extra></extra>",
                name="BBS routes",
                showlegend=True,
            )
        )

    # Animation frames — choropleth only (trace index 0)
    frames = [
        go.Frame(
            data=[choropleth_trace(county_df[county_df["year"] == yr], geojson)],
            traces=[0],
            name=yr,
        )
        for yr in years
    ]

    fig = go.Figure(data=traces, frames=frames)

    # Year slider
    sliders = [dict(
        active=0,
        pad={"b": 10, "t": 55},
        x=0.05,
        xanchor="left",
        y=0,
        yanchor="top",
        len=0.88,
        currentvalue=dict(prefix="Year: ", visible=True, xanchor="center"),
        transition=dict(duration=300),
        steps=[
            dict(
                label=yr,
                method="animate",
                args=[
                    [yr],
                    dict(frame=dict(duration=600, redraw=True),
                         mode="immediate",
                         transition=dict(duration=300)),
                ],
            )
            for yr in years
        ],
    )]

    play_pause = dict(
        type="buttons",
        showactive=False,
        x=0,
        xanchor="right",
        y=0,
        yanchor="top",
        pad={"b": 10, "r": 10},
        buttons=[
            dict(label="▶  Play", method="animate",
                 args=[None, dict(frame=dict(duration=700, redraw=True),
                                  fromcurrent=True,
                                  transition=dict(duration=300))]),
            dict(label="⏸ Pause", method="animate",
                 args=[[None], dict(frame=dict(duration=0, redraw=False),
                                     mode="immediate",
                                     transition=dict(duration=0))]),
        ],
    )

    fig.update_layout(
        title=dict(
            text=(
                "California Agricultural Insecticide Use by County, 2015–2023<br>"
                "<sup>Pyrethroid share of tracked lbs (chlorpyrifos + oxamyl + pyrethroid) — "
                "hover counties for detail &nbsp;|&nbsp; blue dots = BBS monitoring routes (size ∝ 5 km exposure)</sup>"
            ),
            x=0.5,
            xanchor="center",
            font=dict(size=14),
        ),
        geo=dict(
            scope="usa",
            projection_type="albers usa",
            showlakes=True,
            lakecolor="lightcyan",
            showland=True,
            landcolor="whitesmoke",
            subunitcolor="lightgrey",
            lonaxis=dict(range=[-125, -113]),
            lataxis=dict(range=[32, 42.5]),
        ),
        updatemenus=[play_pause],
        sliders=sliders,
        height=720,
        margin=dict(r=10, t=90, l=10, b=80),
        legend=dict(x=0.01, y=0.15, bgcolor="rgba(255,255,255,0.85)",
                    bordercolor="lightgrey", borderwidth=1),
        paper_bgcolor="white",
    )

    return fig


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    geojson = fetch_ca_geojson()

    print("Preparing county pesticide data ...")
    county_df = prepare_county_data()
    print(f"  {len(county_df)} county-year rows, "
          f"years {county_df['year'].min()}–{county_df['year'].max()}, "
          f"{county_df['fips'].nunique()} counties")

    print("Loading BBS monitoring locations ...")
    bbs = load_bbs()
    if bbs is not None:
        print(f"  {len(bbs)} BBS routes")

    print("Building map ...")
    fig = build_figure(county_df, geojson, bbs)

    fig.write_html(
        str(MAP_OUTPUT),
        include_plotlyjs=True,   # embed ~3 MB of Plotly JS — works fully offline
        full_html=True,
    )
    print(f"\nMap written to: {MAP_OUTPUT.resolve()}")
    print("Open in any browser — no server or Docker needed.")


if __name__ == "__main__":
    main()
