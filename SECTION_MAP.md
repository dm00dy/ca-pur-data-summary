# Section-Level Pesticide Map — Pipeline Documentation

**Output:** `pur_analysis/section_map.html` (~41 MB, self-contained)  
**Script:** `make_section_map.py`  
**Last updated:** 2026-05-17

---

## What it produces

A browser-based interactive map of California agricultural insecticide use at
PLSS section resolution (~1 mi²), covering 2015–2023. Controls:

- **Chemical class** dropdown — 8 insecticide classes (Pyrethroids, OPs, Carbamates, etc.)
- **Year slider + Play button** — animate year by year
- **Metric toggle** — three views of the same underlying data:
  - *Lbs AI* — raw pounds of active ingredient applied
  - *Aquatic Tox* — lbs ÷ *Daphnia magna* 48h LC50 (μg/L); proxy for prey-base disruption affecting aerial insectivores
  - *Avian Tox* — lbs ÷ acute oral LD50 (mg/kg, Bobwhite); proxy for direct bird mortality risk

BBS (Breeding Bird Survey) monitoring routes appear as blue circles sized by
exposure within 5 km of each route, updating with the year/class/metric
selection.

The HTML is self-contained (all pesticide data embedded). It requires an
internet connection only for basemap tiles (OpenFreeMap, free, no API key).

---

## Prerequisites

### Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas geopandas pyarrow matplotlib requests
```

GeoPandas pulls in Shapely and Fiona; those are the only non-trivial
dependencies beyond what the rest of the project already uses.

### Data files — already on disk, no downloads needed

| File | Contents | Size |
|------|----------|------|
| `spatial/outputs/pur_sections.parquet` | 5.07M PUR application records geocoded to PLSS sections, 2015–2023 | 92 MB |
| `spatial/data/plss_ca_augmented.gpkg` | 134,885 California PLSS section polygons — 131,579 BLM CADNSDI + 3,306 synthetic sections subdivided from township polygons to cover Mexican land grant (rancho) areas. See `synthesize_plss.py` for derivation. | 61 MB |
| `spatial/data/plss_ca.gpkg` | Original 131,579 BLM-only sections (fallback if augmented file is absent) | 58 MB |
| `spatial/outputs/bbs_locations.csv` | 44 BBS monitoring route centroids (lat/lon, route name) | <1 MB |

The parquet columns used by this script:

```
section_key   — PLSS section identifier (COMTRS string, e.g. "CA06015T29SR27E14")
year          — calendar year (int)
chem_class    — insecticide class string (one of 8 values)
lbs_ai        — pounds of active ingredient applied (float)
county_cd     — CDPR two-digit county code string ("01"–"58")
avian_ld50    — avian acute oral LD50 (mg/kg); NaN if not sourced
aquatic_lc50  — Daphnia magna 48h EC50 (μg/L); NaN if not sourced
```

Toxicity values are sourced from the Hertfordshire PPDB (primary) and EPA ECOTOX
(cross-check), covering all 44 insecticide active ingredients present in the data.
See `toxicity_lookup.csv` and `CLAUDE.md` for sourcing details.

---

## Running the script

```bash
source .venv/bin/activate
python make_section_map.py
```

Expected runtime: **5–12 minutes** (PLSS geometry loads twice — once for
section polygons, once for the BBS spatial join). Output is
`pur_analysis/section_map.html`.

---

## Pipeline walkthrough

### Step 1 — `build_lookup()`: aggregate PUR data

Reads the parquet, computes toxicity units per application record, then
aggregates to `section_key × year × chem_class`:

```python
df["tox_aquatic"] = df["lbs_ai"] / df["aquatic_lc50"]   # lbs per μg/L
df["tox_avian"]   = df["lbs_ai"] / df["avian_ld50"]     # lbs per mg/kg
```

`groupby.sum()` silently skips NaN, so records without a toxicity value
contribute 0 to the tox columns but still contribute to lbs.

Result: ~475K rows. Three lookup dicts are built from this aggregation —
one per metric — with the structure:

```python
{
  "2023": {
    "Pyrethroids": {
      "CA06015T29SR27E14": 1234.56,
      ...
    },
    ...
  },
  ...
}
```

This structure gives O(1) lookup in JavaScript when the user selects a
year + class combination.

Also returns the raw `agg` DataFrame, which is passed to the BBS step.

### Step 2 — `build_geojson()`: load section polygons

Reads `plss_ca_augmented.gpkg` (falls back to `plss_ca.gpkg`), filters to
the ~21,226 sections present in the PUR data (~20,963 have matching geometry
after join, of which ~3,306 are synthetic rancho sections), and reprojects
to WGS84 (EPSG:4326) for the web map. Annotates each feature with
`county_name` decoded from the CDPR county code.

GeoJSON features use the `section_key` as the feature `id` (required for
MapLibre's `feature-state` mechanism).

No geometry simplification is applied — PLSS sections are already rectangular
with 4–5 vertices each.

### Step 3 — `build_bbs_lookup()`: BBS exposure by year and class

Computes responsive exposure values for each BBS route using a spatial join:

1. Buffer each BBS route centroid by **5 km** (California Albers, EPSG:3310)
2. Compute centroids of all active PLSS sections
3. `gpd.sjoin(section_centroids, bbs_buffers, predicate="within")` →
   ~737 section × route pairs across 44 routes
4. Merge joined pairs with the aggregated PUR data
5. Sum by `route_index × year × chem_class` for all three metrics

Returns three lookup dicts (same structure as section lookups, keyed by
route index string "0"–"43") plus the `sqrt` of each metric's maximum
value for circle-radius scaling.

**Caveat on absolute values:** The original `lbs_ai_5km` column in
`bbs_locations.csv` was computed by the upstream spatial pipeline using
the full 25-mile route line geometry. Buffering the centroid point instead
captures approximately 50–65% of those sections. Routes through
predominantly non-agricultural terrain (JOFEGAN, YOKOHL VAL) return zero
because their agricultural sections lie away from the route centroid. The
relative ranking of routes within a given year/class is preserved; only
the absolute totals are lower than the route-line approach.

---

## HTML / JavaScript architecture

The HTML file embeds six JSON objects (three section lookups, three BBS
lookups) plus the GeoJSON section geometries and BBS route metadata. Total
embedded data is ~41 MB.

### MapLibre GL JS

WebGL-based mapping library (CDN, no API key). Chosen over Plotly or
Leaflet because it handles 17K+ polygon features smoothly via GPU
rendering and supports `feature-state` — the mechanism that makes
year/class/metric switching fast.

### The `feature-state` pattern

Section fill colors and BBS circle radii are driven entirely by MapLibre
`feature-state`, not by reloading or rebuilding geometry. On each
year/class/metric change:

```javascript
map.removeFeatureState({ source: 'sections' });           // clear all
Object.entries(classData).forEach(([sk, val]) =>
  map.setFeatureState({ source: 'sections', id: sk }, { lbs: val }));
```

The paint expression reads `feature-state.lbs`:

```javascript
['step', ['coalesce', ['feature-state', 'lbs'], 0], 'rgba(0,0,0,0)', ...colorSteps]
```

The property is named `lbs` for all three metrics — only the lookup source
and color steps change when the metric toggles. `map.setPaintProperty()` swaps
the color ramp without touching the geometry.

**Critical:** `promoteId: 'sk'` must be set on the GeoJSON source.
Without it, MapLibre silently ignores `setFeatureState` calls for
string feature IDs and all sections remain transparent.

The same pattern applies to BBS circles: `promoteId: 'ri'` on the BBS
source, feature-state property also named `lbs`.

### BBS circle radius

Circle area scales with value (area ∝ value) using a sqrt interpolation:

```javascript
['interpolate', ['linear'],
  ['sqrt', ['coalesce', ['feature-state', 'lbs'], 0]],
  0, 4,         // no data → radius 4 (always visible)
  sqrtMax, 16   // max value → radius 16
]
```

`sqrtMax` is pre-computed at build time and varies per metric. On metric
change, `map.setPaintProperty('bbs-circles', 'circle-radius', newExpr)`
updates the scale.

### `METRIC_CONFIG` object

All per-metric configuration lives in one JS object:

```javascript
const METRIC_CONFIG = {
  lbs:     { lookup, bbsLookup, label, fmt, bbsFmt, steps, gradient, legLo, legHi },
  aquatic: { ... },
  avian:   { ... },
};
```

`updateMetric(metric)` reads from `METRIC_CONFIG[metric]` to update the
color ramp, legend, paint properties, and feature states in one pass.

### Color scales

Log-spaced thresholds tuned to the actual data distribution
(p50/p90/p99 printed at build time):

| Metric | Scale | Steps |
|--------|-------|-------|
| Lbs AI | lbs/section | 1 / 10 / 100 / 1,000 / 5,000 |
| Aquatic Tox | lbs ÷ LC50 | 0.001 / 0.1 / 10 / 1,000 / 10,000 |
| Avian Tox | lbs ÷ LD50 | 0.001 / 0.01 / 1 / 10 / 100 |

Sections with value 0 (no use that year/class) are fully transparent.

---

## Known limitations

- **~263 unmatched sections (1.2% of total lbs)**: 21,226 sections have
  PUR records; 20,963 are matched after PLSS augmentation. The remaining
  263 fall in townships not present in BLM Layer 1 at all, or produce
  empty geometry after clipping (sections that land entirely outside
  irregular township polygons — e.g., coastal cutoffs). These are dropped
  from the map.

- **~3,306 sections use synthetic polygons (~20% of total lbs)**: Mexican
  land grant (rancho) areas were never surveyed under PLSS, so BLM has no
  section polygons for them. CDPR's PUR uses synthetic section keys based
  on a virtual 6×6 grid laid over each township. `synthesize_plss.py`
  replicates that virtual grid by subdividing BLM township polygons into
  36 equal cells with standard PLSS numbering (NE corner = section 1,
  boustrophedon down to SE corner = section 36), clipped to the township
  boundary. The boundaries are approximate — fine for visualization but
  not for precise sub-section spatial analysis. Synthetic vs surveyed
  sections are distinguishable via the `source` column ('synthetic' vs
  'blm') in `plss_ca_augmented.gpkg`.

- **BBS centroid buffer vs. route line**: See Step 3 caveat above. Using
  actual BBS route line geometry would require the USGS BBS route shapefile
  and a more complex spatial join. The centroid approach is adequate for
  visual context; do not use the per-route totals for quantitative analysis.

- **All classes combined in BBS dot size**: The dot size reflects the
  current class selection. "All classes" is not available as a single
  dropdown option; switching classes changes the dot sizes independently.

- **Internet required for basemap**: OpenFreeMap tile CDN. The section
  data is fully embedded and renders without internet; only the background
  map tiles are remote.

- **File size**: ~41 MB HTML. Opens immediately in any modern browser but
  may be slow to transfer or email. For sharing, host on a static file server
  or GitHub Pages.

---

## Extending the map

**Add a new year**: Re-run the upstream spatial pipeline to update
`pur_sections.parquet`, then re-run `make_section_map.py`. The `YEARS`
array is derived automatically from the parquet.

**Add a new chemical class**: Update `CHEMICAL_CLASSES` in `pur_analyze.py`
and re-run the spatial pipeline to regenerate the parquet. The class
dropdown populates from the data.

**Add a new metric**: Add a column to the `agg` groupby in `build_lookup()`,
add a `make_lookup()` call, pass the new lookup through `build_html()`, and
add an entry to `METRIC_CONFIG` in the JavaScript template. Also add to
`build_bbs_lookup()` for route-level values.

**Switch to route-line BBS buffers**: Replace the centroid GeoDataFrame in
`build_bbs_lookup()` with a GeoDataFrame loaded from the USGS BBS route
shapefile. The rest of the function is unchanged.

**Reduce file size**: Run the section GeoJSON through `topojson` before
embedding, or serve the GeoJSON as a separate file and load it via URL.
Switching to vector tiles (MBTiles) would handle larger datasets but
requires a tile server.

**Refresh the augmented PLSS file**: Run `python synthesize_plss.py` to
re-download BLM township polygons and regenerate `plss_ca_augmented.gpkg`.
This takes ~30s (downloads only townships, not all 142K sections). The
original `plss_ca.gpkg` is never modified.

---

## File inventory

| File | Role |
|------|------|
| `make_section_map.py` | Build script — run this to regenerate the map |
| `synthesize_plss.py` | One-time setup — builds the augmented PLSS file with synthetic rancho sections |
| `refresh_plss.py` | Optional — fresh BLM Layer 2 download with coverage comparison (diagnostic) |
| `pur_analysis/section_map.html` | Generated output — open in any browser |
| `spatial/data/plss_ca_augmented.gpkg` | Augmented PLSS (BLM + synthetic), used by `make_section_map.py` |
| `spatial/outputs/pur_sections.parquet` | Primary data source (read-only) |
| `spatial/data/plss_ca.gpkg` | Section geometries (read-only) |
| `spatial/outputs/bbs_locations.csv` | BBS route centroids (read-only) |
| `toxicity_lookup.csv` | Toxicity reference values (sourced upstream) |
