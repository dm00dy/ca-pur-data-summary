#!/usr/bin/env python3
"""
Interactive California pesticide application map.

Produces a self-contained HTML file — open directly in any browser.
No web server or Docker required; Plotly JS and all data are embedded.

Usage:
    source .venv/bin/activate
    python make_map.py
    # then open pur_analysis/pesticide_map.html

Three toggleable metrics:
  - Pyrethroid share of tracked lbs  →  aquatic / prey-base risk
  - Oxamyl share of tracked lbs      →  direct avian mortality risk
  - Total tracked lbs (all three)    →  overall insecticide pressure

Blue dots = BBS monitoring routes, sized by 5km pesticide exposure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

OUTPUT_DIR = Path("./pur_analysis")
COUNTY_CSV = OUTPUT_DIR / "pur_county_by_class.csv"
BBS_CSV = Path("./spatial/outputs/bbs_locations.csv")
GEOJSON_CACHE = Path("/tmp/ca_counties.geojson")
GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
MAP_OUTPUT = OUTPUT_DIR / "pesticide_map.html"

# CDPR sequential county code (01–58, alphabetical) → 5-digit FIPS
# California FIPS county codes are sequential odd numbers in alphabetical order.
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
# DATA
# ---------------------------------------------------------------------------

def fetch_ca_geojson() -> dict:
    if GEOJSON_CACHE.exists():
        with open(GEOJSON_CACHE) as f:
            return json.load(f)
    print("Fetching California county boundaries ...")
    r = requests.get(GEOJSON_URL, timeout=60)
    r.raise_for_status()
    ca = {
        "type": "FeatureCollection",
        "features": [f for f in r.json()["features"] if f["id"].startswith("06")],
    }
    with open(GEOJSON_CACHE, "w") as f:
        json.dump(ca, f)
    print(f"  {len(ca['features'])} counties cached")
    return ca


def prepare_county_data() -> pd.DataFrame:
    df = pd.read_csv(COUNTY_CSV)
    df["county"] = pd.to_numeric(df["county"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["county"])
    df["fips"] = df["county"].apply(cdpr_to_fips)
    df["county_name"] = df["county"].apply(lambda c: COUNTY_NAMES.get(int(c), f"County {c}"))

    pivot = df.pivot_table(
        index=["year", "fips", "county_name"],
        columns="class", values="lbs", aggfunc="sum",
    ).reset_index()
    pivot.columns.name = None

    for col in ["chlorpyrifos", "oxamyl", "pyrethroid"]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    pivot = pivot.fillna(0.0)

    pivot["total_lbs"] = pivot["chlorpyrifos"] + pivot["oxamyl"] + pivot["pyrethroid"]
    denom = pivot["total_lbs"].replace(0, float("nan"))
    pivot["pyr_pct"]    = (pivot["pyrethroid"] / denom * 100).fillna(0.0).round(1)
    pivot["oxamyl_pct"] = (pivot["oxamyl"]     / denom * 100).fillna(0.0).round(1)

    pivot["hover"] = pivot.apply(
        lambda r: (
            f"<b>{r['county_name']} County — {r['year']}</b><br>"
            f"Pyrethroid:    {r['pyrethroid']:>10,.0f} lbs  ({r['pyr_pct']:.0f}%)<br>"
            f"Chlorpyrifos: {r['chlorpyrifos']:>10,.0f} lbs<br>"
            f"Oxamyl:         {r['oxamyl']:>9,.0f} lbs  ({r['oxamyl_pct']:.0f}%)<br>"
            f"─────────────────────────<br>"
            f"Total tracked: {r['total_lbs']:>9,.0f} lbs"
        ),
        axis=1,
    )
    pivot["year"] = pivot["year"].astype(str)
    return pivot


def load_bbs() -> dict | None:
    if not BBS_CSV.exists():
        return None
    df = pd.read_csv(BBS_CSV)
    max_exp = df["lbs_ai_5km"].max()
    return {
        "lat":      df["latitude"].tolist(),
        "lon":      df["longitude"].tolist(),
        "size_raw": df["lbs_ai_5km"].tolist(),
        "hover":    df.apply(
            lambda r: f"<b>BBS: {r['RouteName']}</b><br>5 km exposure: {r['lbs_ai_5km']:,.0f} lbs AI",
            axis=1,
        ).tolist(),
    }


# ---------------------------------------------------------------------------
# HTML GENERATION
# ---------------------------------------------------------------------------

def build_html(county_df: pd.DataFrame, geojson: dict, bbs: dict | None) -> str:
    years = sorted(county_df["year"].unique())
    max_lbs = int(county_df["total_lbs"].max() * 1.05)  # 5% headroom

    # Precompute all_data[metric][year] = {fips, z, hover}
    all_data: dict = {}
    for metric in ("pyr_pct", "oxamyl_pct", "total_lbs"):
        all_data[metric] = {}
        for year in years:
            yr = county_df[county_df["year"] == year]
            all_data[metric][year] = {
                "fips":  yr["fips"].tolist(),
                "z":     yr[metric].round(1).tolist(),
                "hover": yr["hover"].tolist(),
            }

    # Embed Plotly JS from the installed package (offline-capable)
    try:
        import plotly as _plotly
        plotly_js_path = Path(_plotly.__file__).parent / "package_data" / "plotly.min.js"
        plotly_js_tag = f"<script>{plotly_js_path.read_text()}</script>"
    except Exception:
        plotly_js_tag = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'

    data_json   = json.dumps(all_data)
    geojson_str = json.dumps(geojson)
    bbs_json    = json.dumps(bbs)
    years_json  = json.dumps(years)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>California Pesticide Application Map</title>
{plotly_js_tag}
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f5f5f5; color: #222; }}

  #header {{ background: #1a3a5c; color: white; padding: 14px 20px; }}
  #header h1 {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 3px; }}
  #header p  {{ font-size: 0.78rem; opacity: 0.8; }}

  #controls {{ background: white; border-bottom: 1px solid #ddd;
               padding: 10px 20px; display: flex; align-items: center;
               gap: 24px; flex-wrap: wrap; }}

  .ctrl-group {{ display: flex; flex-direction: column; gap: 4px; }}
  .ctrl-label  {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
                  letter-spacing: 0.05em; color: #666; }}

  .metric-btns {{ display: flex; gap: 6px; }}
  .metric-btn {{
    padding: 5px 12px; border: 1.5px solid #bbb; border-radius: 4px;
    background: white; cursor: pointer; font-size: 0.82rem; transition: all 0.15s;
  }}
  .metric-btn:hover {{ border-color: #1a3a5c; color: #1a3a5c; }}
  .metric-btn.active {{
    background: #1a3a5c; color: white; border-color: #1a3a5c; font-weight: 600;
  }}

  .year-row {{ display: flex; align-items: center; gap: 10px; }}
  #year-slider {{ width: 180px; accent-color: #1a3a5c; cursor: pointer; }}
  #year-display {{ font-size: 1rem; font-weight: 700; color: #1a3a5c; min-width: 2.5rem; }}
  #play-btn {{
    padding: 5px 14px; background: #1a3a5c; color: white; border: none;
    border-radius: 4px; cursor: pointer; font-size: 0.82rem;
  }}
  #play-btn:hover {{ background: #2a5a8c; }}

  #metric-desc {{ font-size: 0.78rem; color: #888; font-style: italic; }}

  #map {{ width: 100%; height: calc(100vh - 130px); min-height: 500px; }}
</style>
</head>
<body>

<div id="header">
  <h1>California Agricultural Insecticide Use by County, 2015–2023</h1>
  <p>Chlorpyrifos phase-out (2019–2021) and chemical substitution patterns · hover counties for detail</p>
</div>

<div id="controls">
  <div class="ctrl-group">
    <span class="ctrl-label">Risk metric</span>
    <div class="metric-btns">
      <button class="metric-btn active" data-metric="pyr_pct">
        Pyrethroid share — aquatic / prey-base risk
      </button>
      <button class="metric-btn" data-metric="oxamyl_pct">
        Oxamyl share — direct avian mortality risk
      </button>
      <button class="metric-btn" data-metric="total_lbs">
        Total tracked lbs
      </button>
    </div>
  </div>

  <div class="ctrl-group">
    <span class="ctrl-label">Year</span>
    <div class="year-row">
      <input type="range" id="year-slider" min="0" max="{len(years) - 1}" value="0" step="1">
      <span id="year-display">{years[0]}</span>
      <button id="play-btn">▶  Play</button>
    </div>
  </div>

  <div class="ctrl-group" style="align-self:flex-end">
    <span id="metric-desc">Pyrethroid share of tracked insecticide lbs — proxy for aquatic invertebrate toxicity load</span>
  </div>
</div>

<div id="map"></div>

<script>
const YEARS       = {years_json};
const ALL_DATA    = {data_json};
const GEOJSON     = {geojson_str};
const BBS         = {bbs_json};
const MAX_LBS     = {max_lbs};

const METRIC_CONFIG = {{
  pyr_pct: {{
    colorscale: "YlOrRd",
    zmin: 0, zmax: 100,
    cbartitle: "Pyrethroid<br>share (%)",
    desc: "Pyrethroid share of tracked insecticide lbs — proxy for aquatic invertebrate toxicity load",
  }},
  oxamyl_pct: {{
    colorscale: "RdPu",
    zmin: 0, zmax: 100,
    cbartitle: "Oxamyl<br>share (%)",
    desc: "Oxamyl share of tracked insecticide lbs — proxy for direct avian mortality risk (LD50 = 3.16 mg/kg)",
  }},
  total_lbs: {{
    colorscale: "Blues",
    zmin: 0, zmax: MAX_LBS,
    cbartitle: "Tracked<br>lbs",
    desc: "Total tracked insecticide lbs (chlorpyrifos + pyrethroid + oxamyl) — overall application pressure",
  }},
}};

let currentMetric   = "pyr_pct";
let currentYearIdx  = 0;
let playTimer       = null;

// ── Initial render ──────────────────────────────────────────────────────────

function buildTraces(metric, yearIdx) {{
  const d   = ALL_DATA[metric][YEARS[yearIdx]];
  const cfg = METRIC_CONFIG[metric];

  const choropleth = {{
    type: "choropleth",
    geojson: GEOJSON,
    featureidkey: "id",
    locations: d.fips,
    z: d.z,
    text: d.hover,
    hovertemplate: "%{{text}}<extra></extra>",
    colorscale: cfg.colorscale,
    zmin: cfg.zmin,
    zmax: cfg.zmax,
    colorbar: {{
      title: {{ text: cfg.cbartitle, side: "right" }},
      thickness: 14,
      len: 0.55,
      y: 0.62,
    }},
    marker: {{ line: {{ color: "white", width: 0.6 }} }},
  }};

  const traces = [choropleth];

  if (BBS) {{
    const maxExp = Math.max(...BBS.size_raw);
    traces.push({{
      type: "scattergeo",
      lat: BBS.lat,
      lon: BBS.lon,
      mode: "markers",
      marker: {{
        size: BBS.size_raw.map(s => (s / maxExp) * 18 + 5),
        color: "steelblue",
        opacity: 0.85,
        line: {{ width: 1, color: "white" }},
      }},
      text: BBS.hover,
      hovertemplate: "%{{text}}<extra></extra>",
      name: "BBS routes",
      showlegend: true,
    }});
  }}

  return traces;
}}

const layout = {{
  geo: {{
    scope: "usa",
    projection: {{ type: "albers usa" }},
    showlakes: true,
    lakecolor: "lightcyan",
    landcolor: "whitesmoke",
    subunitcolor: "#ccc",
    lonaxis: {{ range: [-125.5, -113] }},
    lataxis: {{ range: [32, 42.5] }},
  }},
  margin: {{ r: 10, t: 10, l: 10, b: 10 }},
  legend: {{
    x: 0.01, y: 0.18,
    bgcolor: "rgba(255,255,255,0.88)",
    bordercolor: "#ccc", borderwidth: 1,
  }},
  paper_bgcolor: "white",
}};

Plotly.newPlot("map", buildTraces("pyr_pct", 0), layout, {{
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
}});

// ── Update ───────────────────────────────────────────────────────────────────

function updateChoropleth() {{
  const d   = ALL_DATA[currentMetric][YEARS[currentYearIdx]];
  const cfg = METRIC_CONFIG[currentMetric];
  Plotly.restyle("map", {{
    locations:               [d.fips],
    z:                       [d.z],
    text:                    [d.hover],
    colorscale:              [cfg.colorscale],
    zmin:                    cfg.zmin,
    zmax:                    cfg.zmax,
    "colorbar.title.text":   [cfg.cbartitle],
  }}, [0]);
  document.getElementById("year-display").textContent = YEARS[currentYearIdx];
  document.getElementById("year-slider").value        = currentYearIdx;
}}

function setMetric(metric) {{
  currentMetric  = metric;
  currentYearIdx = 0;
  document.querySelectorAll(".metric-btn").forEach(b => {{
    b.classList.toggle("active", b.dataset.metric === metric);
  }});
  document.getElementById("metric-desc").textContent = METRIC_CONFIG[metric].desc;
  updateChoropleth();
}}

function setYearIdx(idx) {{
  currentYearIdx = parseInt(idx);
  updateChoropleth();
}}

function togglePlay() {{
  if (playTimer) {{
    clearInterval(playTimer);
    playTimer = null;
    document.getElementById("play-btn").textContent = "▶  Play";
  }} else {{
    document.getElementById("play-btn").textContent = "⏸  Pause";
    playTimer = setInterval(() => {{
      if (currentYearIdx >= YEARS.length - 1) {{
        clearInterval(playTimer);
        playTimer = null;
        document.getElementById("play-btn").textContent = "▶  Play";
        return;
      }}
      setYearIdx(currentYearIdx + 1);
    }}, 850);
  }}
}}

// ── Event listeners ──────────────────────────────────────────────────────────

document.getElementById("year-slider").addEventListener("input",  e => setYearIdx(e.target.value));
document.getElementById("play-btn").addEventListener("click",      togglePlay);
document.querySelectorAll(".metric-btn").forEach(btn => {{
  btn.addEventListener("click", () => setMetric(btn.dataset.metric));
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    geojson    = fetch_ca_geojson()
    county_df  = prepare_county_data()
    bbs        = load_bbs()

    print(f"County data: {len(county_df)} rows, "
          f"years {county_df['year'].min()}–{county_df['year'].max()}, "
          f"{county_df['fips'].nunique()} counties")
    if bbs:
        print(f"BBS routes:  {len(bbs['lat'])} points")

    html = build_html(county_df, geojson, bbs)
    MAP_OUTPUT.write_text(html, encoding="utf-8")

    print(f"\nMap written to: {MAP_OUTPUT.resolve()}")
    print("Open in any browser — no server or Docker needed.")


if __name__ == "__main__":
    main()
