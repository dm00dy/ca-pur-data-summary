#!/usr/bin/env python3
"""
Interactive California pesticide map at PLSS section level (~1 mi²).

Produces a self-contained HTML file using MapLibre GL JS.
Basemap tiles load from OpenFreeMap (free, no API key, needs internet);
all pesticide data is embedded so the sections render even offline.

Three metric views:
  - Lbs AI applied        (raw application pounds)
  - Aquatic tox units     (lbs / Daphnia LC50 μg/L — proxy for prey-base disruption)
  - Avian tox units       (lbs / avian oral LD50 mg/kg — proxy for direct mortality risk)

Usage:
    source .venv/bin/activate
    python make_section_map.py
    # open pur_analysis/section_map.html in any browser

Data sources (already on disk — no downloads needed):
    spatial/outputs/pur_sections.parquet  — 5M PUR records geocoded to sections
    spatial/data/plss_ca.gpkg            — California PLSS section polygons
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

OUTPUT_DIR       = Path("./pur_analysis")
SECTIONS_PARQUET = Path("./spatial/outputs/pur_sections.parquet")
PLSS_GPKG        = Path("./spatial/data/plss_ca.gpkg")
BBS_CSV          = Path("./spatial/outputs/bbs_locations.csv")
MAP_OUTPUT       = OUTPUT_DIR / "section_map.html"

COUNTY_NAMES: dict[str, str] = {
    "01": "Alameda",       "02": "Alpine",        "03": "Amador",
    "04": "Butte",         "05": "Calaveras",     "06": "Colusa",
    "07": "Contra Costa",  "08": "Del Norte",     "09": "El Dorado",
    "10": "Fresno",        "11": "Glenn",         "12": "Humboldt",
    "13": "Imperial",      "14": "Inyo",          "15": "Kern",
    "16": "Kings",         "17": "Lake",          "18": "Lassen",
    "19": "Los Angeles",   "20": "Madera",        "21": "Marin",
    "22": "Mariposa",      "23": "Mendocino",     "24": "Merced",
    "25": "Modoc",         "26": "Mono",          "27": "Monterey",
    "28": "Napa",          "29": "Nevada",        "30": "Orange",
    "31": "Placer",        "32": "Plumas",        "33": "Riverside",
    "34": "Sacramento",    "35": "San Benito",    "36": "San Bernardino",
    "37": "San Diego",     "38": "San Francisco", "39": "San Joaquin",
    "40": "San Luis Obispo","41": "San Mateo",    "42": "Santa Barbara",
    "43": "Santa Clara",   "44": "Santa Cruz",    "45": "Shasta",
    "46": "Sierra",        "47": "Siskiyou",      "48": "Solano",
    "49": "Sonoma",        "50": "Stanislaus",    "51": "Sutter",
    "52": "Tehama",        "53": "Trinity",       "54": "Tulare",
    "55": "Tuolumne",      "56": "Ventura",       "57": "Yolo",
    "58": "Yuba",
}


# ---------------------------------------------------------------------------
# DATA PREPARATION
# ---------------------------------------------------------------------------

def build_lookup(parquet_path: Path) -> tuple[dict, dict, dict, dict, set, list, list]:
    """Aggregate PUR records → three section × year × class lookup dicts."""
    print("Loading PUR section data ...")
    df = pd.read_parquet(
        parquet_path,
        columns=["section_key", "year", "chem_class", "lbs_ai", "county_cd",
                 "avian_ld50", "aquatic_lc50"],
    )
    print(f"  {len(df):,} application records")

    sec_county = (
        df.groupby("section_key")["county_cd"]
        .agg(lambda x: x.mode().iloc[0])
        .to_dict()
    )

    # Tox units per record (NaN where no LD50/LC50; groupby sum skips NaN)
    df["tox_aquatic"] = df["lbs_ai"] / df["aquatic_lc50"]
    df["tox_avian"]   = df["lbs_ai"] / df["avian_ld50"]

    agg = (
        df.groupby(["section_key", "year", "chem_class"])
        .agg(
            lbs_ai=("lbs_ai",      "sum"),
            tox_aquatic=("tox_aquatic", "sum"),
            tox_avian=("tox_avian",   "sum"),
        )
        .reset_index()
    )
    agg["lbs_ai"]      = agg["lbs_ai"].round(2)
    agg["tox_aquatic"] = agg["tox_aquatic"].round(4)
    agg["tox_avian"]   = agg["tox_avian"].round(4)

    print(f"  {len(agg):,} section × year × class rows")
    print(f"  {agg['section_key'].nunique():,} unique sections with data")
    for col in ["lbs_ai", "tox_aquatic", "tox_avian"]:
        v = agg[col][agg[col] > 0]
        print(f"  {col}: p50={v.quantile(0.50):.3g}  p90={v.quantile(0.90):.3g}  "
              f"p99={v.quantile(0.99):.3g}  max={v.max():.3g}")

    def make_lookup(value_col: str) -> dict:
        sub = agg[agg[value_col] > 0]
        lookup: dict = {}
        for year, yr_grp in sub.groupby("year"):
            lookup[str(year)] = {
                cls: grp.set_index("section_key")[value_col].to_dict()
                for cls, grp in yr_grp.groupby("chem_class")
            }
        return lookup

    lookup_lbs     = make_lookup("lbs_ai")
    lookup_aquatic = make_lookup("tox_aquatic")
    lookup_avian   = make_lookup("tox_avian")

    active  = set(agg["section_key"].unique())
    classes = sorted(agg["chem_class"].unique())
    years   = sorted(agg["year"].unique())

    return lookup_lbs, lookup_aquatic, lookup_avian, sec_county, active, classes, years


def build_geojson(plss_path: Path, active: set, sec_county: dict) -> dict:
    """Filter PLSS polygons to active sections, reproject to WGS84."""
    print("Loading PLSS section geometries ...")
    gdf = gpd.read_file(plss_path)
    print(f"  {len(gdf):,} total California PLSS sections")

    gdf = gdf[gdf["section_key"].isin(active)].copy()
    print(f"  {len(gdf):,} sections with pesticide data")

    gdf = gdf.to_crs("EPSG:4326")

    gdf["county_cd"]   = gdf["section_key"].map(sec_county).fillna("00")
    gdf["county_name"] = gdf["county_cd"].map(COUNTY_NAMES).fillna("Unknown")

    features = []
    for _, row in gdf.iterrows():
        features.append({
            "type": "Feature",
            "id": row["section_key"],
            "properties": {
                "sk": row["section_key"],
                "cn": row["county_name"],
            },
            "geometry": row["geometry"].__geo_interface__,
        })
    return {"type": "FeatureCollection", "features": features}


def load_bbs() -> dict | None:
    if not BBS_CSV.exists():
        return None
    df = pd.read_csv(BBS_CSV)
    max_exp = df["lbs_ai_5km"].max()
    return {
        "lat":   df["latitude"].tolist(),
        "lon":   df["longitude"].tolist(),
        "size":  (df["lbs_ai_5km"] / max_exp * 10 + 5).round(1).tolist(),
        "hover": df.apply(
            lambda r: f"BBS: {r['RouteName']}<br>{r['lbs_ai_5km']:,.0f} lbs AI within 5 km",
            axis=1,
        ).tolist(),
    }


# ---------------------------------------------------------------------------
# HTML GENERATION
# ---------------------------------------------------------------------------

def build_html(
    lookup_lbs: dict,
    lookup_aquatic: dict,
    lookup_avian: dict,
    geojson: dict,
    bbs: dict | None,
    classes: list,
    years: list,
) -> str:
    lbs_json     = json.dumps(lookup_lbs,     separators=(",", ":"))
    aquatic_json = json.dumps(lookup_aquatic, separators=(",", ":"))
    avian_json   = json.dumps(lookup_avian,   separators=(",", ":"))
    geojson_str  = json.dumps(geojson,        separators=(",", ":"))
    bbs_json     = json.dumps(bbs,            separators=(",", ":"))
    classes_json = json.dumps(classes)
    years_json   = json.dumps([str(y) for y in years])
    n_years      = len(years) - 1

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CA Pesticide Use — Section Level</title>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          display: flex; flex-direction: column; height: 100vh; overflow: hidden; }}

  #header {{ background: #1a3a5c; color: white; padding: 10px 18px; flex-shrink: 0; }}
  #header h1 {{ font-size: 1rem; font-weight: 600; }}
  #header p  {{ font-size: 0.72rem; opacity: 0.75; margin-top: 2px; }}

  #controls {{
    background: white; border-bottom: 1px solid #ddd;
    padding: 7px 18px; display: flex; align-items: center;
    gap: 22px; flex-wrap: wrap; flex-shrink: 0;
  }}
  .ctrl-group {{ display: flex; flex-direction: column; gap: 3px; }}
  .ctrl-label {{ font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 0.06em; color: #777; }}

  #class-select {{
    padding: 4px 10px; border: 1.5px solid #bbb; border-radius: 4px;
    font-size: 0.82rem; background: white; cursor: pointer; min-width: 210px;
  }}

  .year-row {{ display: flex; align-items: center; gap: 8px; }}
  #year-slider {{ width: 170px; accent-color: #1a3a5c; cursor: pointer; }}
  #year-display {{ font-size: 0.95rem; font-weight: 700; color: #1a3a5c; min-width: 2.4rem; }}
  #play-btn {{
    padding: 4px 12px; background: #1a3a5c; color: white; border: none;
    border-radius: 4px; cursor: pointer; font-size: 0.8rem; white-space: nowrap;
  }}
  #play-btn:hover {{ background: #2a5a8c; }}

  #metric-btns {{
    display: flex; border: 1.5px solid #bbb; border-radius: 4px; overflow: hidden;
  }}
  .metric-btn {{
    padding: 4px 11px; border: none; border-right: 1px solid #bbb;
    background: white; cursor: pointer; font-size: 0.78rem; color: #555;
    transition: background 0.12s, color 0.12s;
  }}
  .metric-btn:last-child {{ border-right: none; }}
  .metric-btn:hover {{ background: #f0f4f8; }}
  .metric-btn.active {{ background: #1a3a5c; color: white; font-weight: 600; }}

  #legend {{ display: flex; align-items: center; gap: 5px; }}
  #leg-bar {{
    height: 14px; width: 110px; border-radius: 2px; border: 1px solid #ccc;
    transition: background 0.25s;
  }}
  .leg-lo, .leg-hi {{ font-size: 0.7rem; color: #555; }}

  #map {{ flex: 1; min-height: 0; }}

  .maplibregl-popup-content {{
    font-family: -apple-system, sans-serif; font-size: 0.8rem;
    padding: 9px 13px; line-height: 1.5; min-width: 175px;
  }}
  .maplibregl-popup-content b {{ font-size: 0.85rem; display: block; margin-bottom: 2px; }}
  .metric-val {{ font-size: 1rem; font-weight: 700; color: #c0392b; }}
</style>
</head>
<body>

<div id="header">
  <h1>California Agricultural Insecticide Use — PLSS Section Level (~1 mi²), 2015–2023</h1>
  <p>CDPR Pesticide Use Reports · select class, year, and metric · hover sections for values · blue dots = BBS monitoring routes</p>
</div>

<div id="controls">
  <div class="ctrl-group">
    <span class="ctrl-label">Chemical class</span>
    <select id="class-select"></select>
  </div>

  <div class="ctrl-group">
    <span class="ctrl-label">Year</span>
    <div class="year-row">
      <input type="range" id="year-slider" min="0" max="{n_years}" value="0" step="1">
      <span id="year-display">2015</span>
      <button id="play-btn">&#9654;&#160;&#160;Play</button>
    </div>
  </div>

  <div class="ctrl-group">
    <span class="ctrl-label">Metric</span>
    <div id="metric-btns">
      <button class="metric-btn active" data-metric="lbs">Lbs AI</button>
      <button class="metric-btn" data-metric="aquatic">Aquatic Tox</button>
      <button class="metric-btn" data-metric="avian">Avian Tox</button>
    </div>
  </div>

  <div class="ctrl-group">
    <span class="ctrl-label" id="leg-label">Lbs AI applied / section</span>
    <div id="legend">
      <span class="leg-lo" id="leg-lo">&lt;1 lb</span>
      <div id="leg-bar" style="background:linear-gradient(to right,#ffffcc,#fed976,#fd8d3c,#e31a1c,#800026)"></div>
      <span class="leg-hi" id="leg-hi">&gt;5,000 lbs</span>
    </div>
  </div>
</div>

<div id="map"></div>

<script>
// ── Embedded data (generated by make_section_map.py) ─────────────────────────
const LOOKUP_LBS     = {lbs_json};
const LOOKUP_AQUATIC = {aquatic_json};
const LOOKUP_AVIAN   = {avian_json};
const SECTIONS = {geojson_str};
const BBS      = {bbs_json};
const CLASSES  = {classes_json};
const YEARS    = {years_json};

// ── Metric configuration ──────────────────────────────────────────────────────
// steps: flat array of [threshold, color, threshold, color, ...] for MapLibre step expr
// Thresholds tuned to the actual data distribution (p50/p90/p99 checked at build time)
const METRIC_CONFIG = {{
  lbs: {{
    lookup:   LOOKUP_LBS,
    label:    'Lbs AI applied / section',
    fmt:      v => v.toLocaleString('en-US', {{maximumFractionDigits:1}}) + ' lbs AI',
    steps:    [1,'#ffffcc', 10,'#fed976', 100,'#fd8d3c', 1000,'#e31a1c', 5000,'#800026'],
    gradient: 'linear-gradient(to right,#ffffcc,#fed976,#fd8d3c,#e31a1c,#800026)',
    legLo: '<1 lb', legHi: '>5,000 lbs',
  }},
  aquatic: {{
    lookup:   LOOKUP_AQUATIC,
    // Units: lbs_ai / Daphnia LC50 (μg/L) — higher = more hazard to aquatic invertebrates
    label:    'Aquatic tox units (lbs ÷ Daphnia LC50)',
    fmt:      v => v.toFixed(3) + ' tox units',
    steps:    [0.001,'#c6dbef', 0.1,'#6baed6', 10,'#2171b5', 1000,'#084594', 10000,'#08306b'],
    gradient: 'linear-gradient(to right,#c6dbef,#6baed6,#2171b5,#084594,#08306b)',
    legLo: '<0.001', legHi: '>10,000',
  }},
  avian: {{
    lookup:   LOOKUP_AVIAN,
    // Units: lbs_ai / avian oral LD50 (mg/kg) — higher = more direct mortality hazard to birds
    label:    'Avian tox units (lbs ÷ oral LD50)',
    fmt:      v => v.toFixed(4) + ' tox units',
    steps:    [0.001,'#fcc5c0', 0.01,'#f768a1', 1,'#c51b8a', 10,'#7a0177', 100,'#49006a'],
    gradient: 'linear-gradient(to right,#fcc5c0,#f768a1,#c51b8a,#7a0177,#49006a)',
    legLo: '<0.001', legHi: '>100',
  }},
}};

// ── State ────────────────────────────────────────────────────────────────────
let currentClass   = CLASSES[0];
let currentYearIdx = 0;
let currentMetric  = 'lbs';
let playTimer      = null;

// ── Map ───────────────────────────────────────────────────────────────────────
const map = new maplibregl.Map({{
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/positron',
  center: [-119.5, 37.3],
  zoom: 5.1,
  maxBounds: [[-126.5, 31], [-112, 43.5]],
}});

map.addControl(new maplibregl.NavigationControl(), 'top-right');
map.addControl(new maplibregl.ScaleControl({{ unit: 'imperial' }}), 'bottom-right');

function makeColorExpr(steps) {{
  return ['step', ['coalesce', ['feature-state', 'lbs'], 0],
    'rgba(0,0,0,0)', ...steps];
}}

map.on('load', () => {{

  // promoteId required for setFeatureState with string feature IDs
  map.addSource('sections', {{
    type: 'geojson',
    data: SECTIONS,
    promoteId: 'sk',
  }});

  map.addLayer({{
    id: 'sections-fill',
    type: 'fill',
    source: 'sections',
    paint: {{
      'fill-color': makeColorExpr(METRIC_CONFIG.lbs.steps),
      'fill-opacity': [
        'case',
        ['>', ['coalesce', ['feature-state', 'lbs'], 0], 0],
        0.82, 0,
      ],
    }},
  }});

  map.addLayer({{
    id: 'sections-line',
    type: 'line',
    source: 'sections',
    paint: {{
      'line-color': '#666',
      'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.15, 12, 0.7],
      'line-opacity': 0.35,
    }},
  }});

  if (BBS) {{
    map.addSource('bbs', {{
      type: 'geojson',
      data: {{
        type: 'FeatureCollection',
        features: BBS.lat.map((lat, i) => ({{
          type: 'Feature',
          geometry: {{ type: 'Point', coordinates: [BBS.lon[i], lat] }},
          properties: {{ label: BBS.hover[i], r: BBS.size[i] }},
        }})),
      }},
    }});
    map.addLayer({{
      id: 'bbs-circles',
      type: 'circle',
      source: 'bbs',
      paint: {{
        'circle-color': '#2196F3',
        'circle-radius': ['get', 'r'],
        'circle-opacity': 0.85,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': 'white',
      }},
    }});
  }}

  updateSections();
  setupHover();
}});

// ── Data update ───────────────────────────────────────────────────────────────
function updateSections() {{
  if (!map.getSource('sections')) return;
  map.removeFeatureState({{ source: 'sections' }});
  const classData = METRIC_CONFIG[currentMetric].lookup[YEARS[currentYearIdx]]?.[currentClass] ?? {{}};
  for (const [sk, val] of Object.entries(classData)) {{
    map.setFeatureState({{ source: 'sections', id: sk }}, {{ lbs: val }});
  }}
}}

// ── Metric switch ─────────────────────────────────────────────────────────────
function updateMetric(metric) {{
  currentMetric = metric;
  const cfg = METRIC_CONFIG[metric];
  map.setPaintProperty('sections-fill', 'fill-color', makeColorExpr(cfg.steps));
  document.getElementById('leg-bar').style.background    = cfg.gradient;
  document.getElementById('leg-lo').textContent          = cfg.legLo;
  document.getElementById('leg-hi').textContent          = cfg.legHi;
  document.getElementById('leg-label').textContent       = cfg.label;
  document.querySelectorAll('.metric-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.metric === metric));
  updateSections();
}}

// ── Hover tooltips ────────────────────────────────────────────────────────────
function setupHover() {{
  const popup    = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, maxWidth: '260px' }});
  const bbsPopup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false }});

  map.on('mousemove', 'sections-fill', (e) => {{
    map.getCanvas().style.cursor = 'crosshair';
    const p   = e.features[0].properties;
    const sk  = p.sk;
    const cfg = METRIC_CONFIG[currentMetric];
    const val = cfg.lookup[YEARS[currentYearIdx]]?.[currentClass]?.[sk] ?? 0;
    popup.setLngLat(e.lngLat).setHTML(
      `<b>${{p.cn}} County</b>`+
      `<div style="color:#555;font-size:0.75rem;margin-bottom:4px">Section ${{sk}}</div>`+
      `${{currentClass}}<br>`+
      `<span class="metric-val">${{cfg.fmt(val)}}</span><br>`+
      `<span style="color:#888">Year: ${{YEARS[currentYearIdx]}}</span>`
    ).addTo(map);
  }});
  map.on('mouseleave', 'sections-fill', () => {{
    map.getCanvas().style.cursor = '';
    popup.remove();
  }});

  if (BBS) {{
    map.on('mousemove', 'bbs-circles', (e) => {{
      map.getCanvas().style.cursor = 'pointer';
      bbsPopup.setLngLat(e.lngLat)
        .setHTML(`<b>BBS Route</b><br>${{e.features[0].properties.label}}`).addTo(map);
    }});
    map.on('mouseleave', 'bbs-circles', () => {{
      map.getCanvas().style.cursor = '';
      bbsPopup.remove();
    }});
  }}
}}

// ── Controls ──────────────────────────────────────────────────────────────────
const sel = document.getElementById('class-select');
CLASSES.forEach(c => {{
  const opt = document.createElement('option');
  opt.value = c;
  opt.textContent = c;
  sel.appendChild(opt);
}});
sel.addEventListener('change', () => {{ currentClass = sel.value; updateSections(); }});

document.getElementById('year-slider').addEventListener('input', (e) => {{
  currentYearIdx = parseInt(e.target.value);
  document.getElementById('year-display').textContent = YEARS[currentYearIdx];
  updateSections();
}});

document.getElementById('play-btn').addEventListener('click', () => {{
  if (playTimer) {{
    clearInterval(playTimer); playTimer = null;
    document.getElementById('play-btn').innerHTML = '&#9654;&#160;&#160;Play';
  }} else {{
    document.getElementById('play-btn').innerHTML = '&#9646;&#9646;&#160;Pause';
    playTimer = setInterval(() => {{
      if (currentYearIdx >= YEARS.length - 1) {{
        clearInterval(playTimer); playTimer = null;
        document.getElementById('play-btn').innerHTML = '&#9654;&#160;&#160;Play';
        return;
      }}
      currentYearIdx++;
      document.getElementById('year-slider').value        = currentYearIdx;
      document.getElementById('year-display').textContent = YEARS[currentYearIdx];
      updateSections();
    }}, 900);
  }}
}});

document.querySelectorAll('.metric-btn').forEach(btn => {{
  btn.addEventListener('click', () => updateMetric(btn.dataset.metric));
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    lookup_lbs, lookup_aquatic, lookup_avian, sec_county, active, classes, years = build_lookup(SECTIONS_PARQUET)
    geojson = build_geojson(PLSS_GPKG, active, sec_county)
    bbs = load_bbs()
    if bbs:
        print(f"BBS routes:  {len(bbs['lat'])} points")

    print("Building HTML ...")
    html = build_html(lookup_lbs, lookup_aquatic, lookup_avian, geojson, bbs, classes, years)

    MAP_OUTPUT.write_text(html, encoding="utf-8")
    size_mb = MAP_OUTPUT.stat().st_size / 1e6
    print(f"\nMap written to: {MAP_OUTPUT.resolve()} ({size_mb:.1f} MB)")
    print("Open in any browser — MapLibre basemap tiles require internet,")
    print("pesticide section data is fully embedded.")


if __name__ == "__main__":
    main()
