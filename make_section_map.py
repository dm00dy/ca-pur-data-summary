#!/usr/bin/env python3
"""
Interactive California pesticide map at PLSS section level (~1 mi²).

Produces a self-contained HTML file using MapLibre GL JS.
Basemap tiles load from OpenFreeMap (free, no API key, needs internet);
all pesticide data is embedded so the sections render even offline.

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

OUTPUT_DIR      = Path("./pur_analysis")
SECTIONS_PARQUET = Path("./spatial/outputs/pur_sections.parquet")
PLSS_GPKG       = Path("./spatial/data/plss_ca.gpkg")
BBS_CSV         = Path("./spatial/outputs/bbs_locations.csv")
MAP_OUTPUT      = OUTPUT_DIR / "section_map.html"

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

def build_lookup(parquet_path: Path) -> tuple[dict, dict, set, list, list]:
    """Aggregate PUR records → section × year × class lookup for JavaScript."""
    print("Loading PUR section data ...")
    df = pd.read_parquet(
        parquet_path,
        columns=["section_key", "year", "chem_class", "lbs_ai", "county_cd"],
    )
    print(f"  {len(df):,} application records")

    # section → county: most frequent county_cd per section
    sec_county = (
        df.groupby("section_key")["county_cd"]
        .agg(lambda x: x.mode().iloc[0])
        .to_dict()
    )

    agg = (
        df.groupby(["section_key", "year", "chem_class"])["lbs_ai"]
        .sum()
        .reset_index()
    )
    agg["lbs_ai"] = agg["lbs_ai"].round(2)
    print(f"  {len(agg):,} section × year × class rows")
    print(f"  {agg['section_key'].nunique():,} unique sections with data")

    # {year_str: {class: {section_key: lbs}}}
    lookup: dict = {}
    for year, yr_grp in agg.groupby("year"):
        lookup[str(year)] = {
            cls: grp.set_index("section_key")["lbs_ai"].to_dict()
            for cls, grp in yr_grp.groupby("chem_class")
        }

    active  = set(agg["section_key"].unique())
    classes = sorted(agg["chem_class"].unique())
    years   = sorted(agg["year"].unique())
    return lookup, sec_county, active, classes, years


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
            "id": row["section_key"],        # string ID — MapLibre setFeatureState uses this
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
    lookup: dict,
    geojson: dict,
    bbs: dict | None,
    classes: list,
    years: list,
) -> str:
    lookup_json  = json.dumps(lookup,  separators=(",", ":"))
    geojson_str  = json.dumps(geojson, separators=(",", ":"))
    bbs_json     = json.dumps(bbs,     separators=(",", ":"))
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
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }}

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

  /* inline color legend */
  #legend {{ display: flex; align-items: center; gap: 5px; }}
  .leg-bar {{
    height: 14px; width: 100px;
    background: linear-gradient(to right, #ffffcc, #fed976, #fd8d3c, #e31a1c, #800026);
    border-radius: 2px; border: 1px solid #ccc;
  }}
  .leg-lo, .leg-hi {{ font-size: 0.7rem; color: #555; }}

  #map {{ flex: 1; min-height: 0; }}

  .maplibregl-popup-content {{
    font-family: -apple-system, sans-serif; font-size: 0.8rem;
    padding: 9px 13px; line-height: 1.5; min-width: 160px;
  }}
  .maplibregl-popup-content b {{ font-size: 0.85rem; display: block; margin-bottom: 2px; }}
  .lbs-val {{ font-size: 1rem; font-weight: 700; color: #c0392b; }}
</style>
</head>
<body>

<div id="header">
  <h1>California Agricultural Insecticide Use — PLSS Section Level (~1 mi²), 2015–2023</h1>
  <p>CDPR Pesticide Use Reports · select chemical class and year · hover sections for lbs applied · blue dots = BBS monitoring routes</p>
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
      <button id="play-btn">▶  Play</button>
    </div>
  </div>

  <div class="ctrl-group">
    <span class="ctrl-label">Lbs AI applied / section</span>
    <div id="legend">
      <span class="leg-lo">&lt; 1</span>
      <div class="leg-bar"></div>
      <span class="leg-hi">&gt; 5,000</span>
    </div>
  </div>
</div>

<div id="map"></div>

<script>
// ── Embedded data (generated by make_section_map.py) ─────────────────────────
const LOOKUP   = {lookup_json};
const SECTIONS = {geojson_str};
const BBS      = {bbs_json};
const CLASSES  = {classes_json};
const YEARS    = {years_json};

const ACTIVE = new Set(SECTIONS.features.map(f => f.id));

// ── State ────────────────────────────────────────────────────────────────────
let currentClass   = CLASSES[0];
let currentYearIdx = 0;
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

map.on('load', () => {{

  // PLSS sections (geometry embedded; feature IDs = section_key strings)
  map.addSource('sections', {{
    type: 'geojson',
    data: SECTIONS,
  }});

  // Fill: color by feature-state.lbs (step scale, log-approximate)
  map.addLayer({{
    id: 'sections-fill',
    type: 'fill',
    source: 'sections',
    paint: {{
      'fill-color': [
        'step',
        ['coalesce', ['feature-state', 'lbs'], 0],
        'rgba(0,0,0,0)',    //    0       → transparent
        0.01, '#ffffcc',    //   <1 lbs   → pale yellow
        10,   '#fed976',    //  <10 lbs
        100,  '#fd8d3c',    // <100 lbs
        1000, '#e31a1c',    // <1 k lbs
        5000, '#800026',    // ≥5 k lbs  → dark red
      ],
      'fill-opacity': [
        'case',
        ['>', ['coalesce', ['feature-state', 'lbs'], 0], 0],
        0.82,
        0,
      ],
    }},
  }});

  // Outline: thin at state zoom, slightly heavier when zoomed in
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

  // BBS monitoring routes (static — not filtered by year/class)
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

  // Load initial data
  updateSections();
  setupHover();
}});

// ── Data update (fast: removeFeatureState clears all at once) ─────────────────
function updateSections() {{
  if (!map.getSource('sections')) return;
  map.removeFeatureState({{ source: 'sections' }});
  const classData = LOOKUP[YEARS[currentYearIdx]]?.[currentClass] ?? {{}};
  for (const [sk, lbs] of Object.entries(classData)) {{
    map.setFeatureState({{ source: 'sections', id: sk }}, {{ lbs }});
  }}
}}

// ── Hover tooltips ────────────────────────────────────────────────────────────
function setupHover() {{
  const popup    = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, maxWidth: '240px' }});
  const bbsPopup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false }});

  map.on('mousemove', 'sections-fill', (e) => {{
    map.getCanvas().style.cursor = 'crosshair';
    const p   = e.features[0].properties;
    const sk  = p.sk;
    const lbs = LOOKUP[YEARS[currentYearIdx]]?.[currentClass]?.[sk] ?? 0;
    popup.setLngLat(e.lngLat).setHTML(
      `<b>${{p.cn}} County</b>`+
      `<div style="color:#555;font-size:0.75rem;margin-bottom:4px">Section ${{sk}}</div>`+
      `${{currentClass}}<br>`+
      `<span class="lbs-val">${{lbs.toLocaleString('en-US', {{maximumFractionDigits:1}})}}</span> lbs AI applied<br>`+
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
  const opt    = document.createElement('option');
  opt.value    = c;
  opt.textContent = c;
  sel.appendChild(opt);
}});

sel.addEventListener('change', () => {{
  currentClass = sel.value;
  updateSections();
}});

document.getElementById('year-slider').addEventListener('input', (e) => {{
  currentYearIdx = parseInt(e.target.value);
  document.getElementById('year-display').textContent = YEARS[currentYearIdx];
  updateSections();
}});

document.getElementById('play-btn').addEventListener('click', () => {{
  if (playTimer) {{
    clearInterval(playTimer); playTimer = null;
    document.getElementById('play-btn').textContent = '▶  Play';
  }} else {{
    document.getElementById('play-btn').textContent = '⏸  Pause';
    playTimer = setInterval(() => {{
      if (currentYearIdx >= YEARS.length - 1) {{
        clearInterval(playTimer); playTimer = null;
        document.getElementById('play-btn').textContent = '▶  Play';
        return;
      }}
      currentYearIdx++;
      document.getElementById('year-slider').value       = currentYearIdx;
      document.getElementById('year-display').textContent = YEARS[currentYearIdx];
      updateSections();
    }}, 900);
  }}
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    lookup, sec_county, active, classes, years = build_lookup(SECTIONS_PARQUET)
    geojson = build_geojson(PLSS_GPKG, active, sec_county)
    bbs     = load_bbs()
    if bbs:
        print(f"BBS routes:  {len(bbs['lat'])} points")

    print("Building HTML ...")
    html = build_html(lookup, geojson, bbs, classes, years)

    MAP_OUTPUT.write_text(html, encoding="utf-8")
    size_mb = MAP_OUTPUT.stat().st_size / 1e6
    print(f"\nMap written to: {MAP_OUTPUT.resolve()} ({size_mb:.1f} MB)")
    print("Open in any browser — MapLibre basemap tiles require internet,")
    print("pesticide section data is fully embedded.")


if __name__ == "__main__":
    main()
