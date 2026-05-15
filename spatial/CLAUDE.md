# CLAUDE.md — Spatial Exposure Pipeline Session

## Mission

Build the spatial exposure pipeline that turns CDPR PUR records into
per-location, per-time-window pesticide exposure metrics for use in
landscape-scale wildlife response models. This is Level 1 of the CDPR
Ecosystem Monitoring proposal — the analysis that pairs long-term bird
data with PUR exposure to test whether agricultural pesticide reduction
has produced detectable insectivore response.

The deliverable is a reproducible pipeline that, given a set of point
locations (BBS routes, ARU deployments, eBird grid cells) and time windows,
produces a wide table of exposure metrics by chemical class and buffer
distance.

## Background context

This work follows from `pur_substitution_analysis.py`, which characterizes
California's statewide insecticide use trajectory and lives in a sibling
directory. That script answers "what's been applied, statewide, by class,
over time." This pipeline answers the harder question: "given a specific
location and time window, what was the pesticide exposure?"

The proposal collaborator is Dennis Jongsomjit. The proposal uses a
hierarchical Level 1/2/3 design (landscape SDMs, AudioMoth + BirdNET
acoustic monitoring, mist-netting + residue analysis). This pipeline is
the spatial backbone of Level 1.

Key methodological reference: Gunier et al. (2001) showed that integrating
crop maps with PUR section-level totals substantially refines exposure
assessment compared to assuming uniform pesticide distribution within
sections. We're building their approach in code.

## The core problem

PUR records are tagged to PLSS sections (~1 mi² each) via the COMTRS field.
The section-level total is the most precise spatial information PUR
provides — it does not say *which fields* within the section received the
application. For most California sections this matters because:

1. Sections often contain a mix of cropped land, non-cropped land,
   different crop types, and non-agricultural land uses.
2. A PUR record's `site_code` tells you what crop was treated (e.g.,
   "almonds") but not where the almonds are within the section.
3. A nearby ARU or BBS route is likely closer to some parts of the section
   than others, so within-section spatial assumptions affect exposure
   estimates meaningfully.

Within-section attribution refinement uses crop maps to constrain "where
the pesticide probably went" within each section.

## Inputs

**PUR data** — already cached at `../pur_toxicity/pur_analysis/cache/pur{YEAR}.zip`
from the toxicity-sourcing session. Reuse rather than re-downloading.

**PLSS section polygons** — California DPR publishes a Statewide DPR PLSS
GIS feature service that adds detail beyond standard BLM PLSS data. Pull
once, store locally as a GeoPackage or shapefile. Source:
https://gis.cdpr.ca.gov/

**CropScape / Cropland Data Layer (CDL)** — USDA NASS, annual 30m raster
classifying every pixel as a crop type or land cover. Free download.
Source: https://nassgeodata.gmu.edu/CropScape/. Need annual rasters for the
full PUR window we're analyzing (2015 onward).

**DWR Land Use Survey** — California-specific, ground-truthed crop maps.
Higher accuracy than CDL for California crops but updated on a 3-7 year
regional cadence. Use as cross-validation rather than primary attribution.
Source: https://data.cnra.ca.gov/dataset/statewide-crop-mapping

**Toxicity lookup CSV** — produced by the toxicity-sourcing session.
Contains avian LD50 and aquatic LC50 per chemical with documented sources.

**Target locations** — input as a CSV with columns:
`location_id, latitude, longitude, survey_start_date, survey_end_date`.
For initial development use a small test set (10-20 California ARU sites
or BBS route start points). Real analysis will scale to thousands.

## Outputs

A wide table per location × survey window × chemical class × buffer ring:

```
location_id, survey_start, survey_end, chemical_class, buffer_m,
lbs_ai, acres_treated, tox_units_avian, tox_units_aquatic,
n_sections_intersected, n_applications, lag_window_days
```

Plus a per-location summary CSV combining all chemical classes and buffers
into one row, suitable for direct use in mixed-effects models.

## Pipeline architecture

Recommended structure:

1. **`spatial_setup.py`** — one-time setup. Downloads / loads PLSS, CDL
   annual rasters, DWR survey. Builds spatial indexes. Writes everything
   to a working PostGIS database or, if PostgreSQL is heavy, a GeoPackage
   with spatial indexes.

2. **`pur_loader.py`** — extracts PUR records into a section-keyed format.
   For each PUR record: parse COMTRS, geocode to section polygon, attach
   chemical class via the toxicity lookup, attach toxicity values. Output
   a long-format table indexed on (year, section_id, chem_code).

3. **`crop_attribution.py`** — for each PUR record, compute the
   within-section "likely application area" mask:
   - Look up the chemical's `site_code` (crop) in the PUR site lookup
   - Find pixels in CDL matching that crop within the section
   - If matching pixels exist, treat them as the application area
   - If no matching pixels (CDL miss-classification, off-label use, etc.),
     fall back to "all agricultural pixels in section" or "uniform within
     section" with a documented choice

4. **`exposure_engine.py`** — given target locations and time windows:
   - Build concentric buffer polygons (500m, 1km, 2km, 5km)
   - For each buffer × time window, find intersecting PUR records via
     spatial join on the application-area masks
   - Compute area-weighted aggregations: lbs, acres, toxicity units
   - Apply lag windows (30/60/90 days before survey start)
   - Output the wide table

5. **`validate.py`** — sanity checks:
   - Sum exposure across all locations vs. statewide PUR totals (should
     be a known fraction)
   - Spot-check a few high-pressure sections by hand
   - Compare against any published California exposure assessment

## Recommended technology choices

- **Postgres + PostGIS** if you have it; large spatial joins with proper
  indexing will be much faster than file-based alternatives. Doug already
  has this infrastructure operational on the ADALO side.
- **GeoPandas / Shapely** for in-Python work where Postgres overhead isn't
  warranted (small test sets, prototyping).
- **Rasterio + rioxarray** for CDL raster access. Don't load full CONUS
  rasters into memory; window-read by section bounds.
- **DuckDB with spatial extension** is a credible alternative if Postgres
  feels heavy. Single-file, fast, supports ST_Intersection.

Performance target: full-California processing of ~10,000 target locations
× 9 years should complete overnight on a workstation. If runtime is much
longer than that, the pipeline architecture is wrong somewhere.

## Known traps

- **Coordinate reference systems**: CDL is in Albers Equal Area; PLSS is in
  geographic; ARU points are usually WGS84. Buffer distance computation
  must happen in a projected CRS (California Albers, EPSG:3310, is fine).
  This is the single most common source of silent bugs in geospatial work.
- **CDL classification accuracy** is ~90% for major crops in California
  but degrades for minor crops, organic operations, and recently-converted
  land. Document the fall-back rule for unmatched site_codes.
- **PUR sections that don't exist in the PLSS layer** — happens with
  reporting errors. Log and exclude rather than crash.
- **Aerial vs. ground application** — PUR has an `aer_gnd_ind` field. For
  drift-sensitive analyses you may want to weight aerial applications by
  a larger effective area than ground applications. Defer this refinement
  for the first pipeline pass; flag the field but don't act on it yet.
- **Chemical reformulations and product changes within years**. PUR
  records the AI applied; product-level differences in formulation,
  carrier, and adjuvants are not captured. Acknowledge in methods, don't
  try to model around it.

## Validation strategy

Before this pipeline output goes into any model, validate:

1. **Statewide totals**: sum of section-level lbs in the loader output
   should match within 1% the statewide totals from
   `pur_substitution_analysis.py`. Differences indicate dropped records or
   geocoding errors.

2. **Section-level spot checks**: pick 5 sections of varying intensity,
   manually compute lbs from the raw PUR text, verify against the loader.

3. **Buffer sanity**: a location buffered at 500m should have <= the lbs
   of the same location buffered at 1km. Always.

4. **CDL attribution sanity**: for a section dominated by almonds, an
   almond-targeted application should show >90% of its weight on
   almond-classified pixels.

5. **Cross-validation against DWR**: in counties with recent DWR surveys,
   the CDL-based application area should agree with DWR-based application
   area within reasonable tolerance. Large disagreements flag CDL
   classification errors worth documenting.

## What NOT to do (yet)

- Don't model pesticide drift (AGDISP / AERMOD-style off-target movement).
  PUR-as-application-proxy is the agreed scope; drift modeling is a
  potential later refinement.
- Don't try to capture surface water transport. Pyrethroid edge-of-field
  hydrology is a real concern but well outside this pipeline.
- Don't optimize for the wrong scale. The pipeline runs against thousands
  of locations × dozens of buffers × dozens of chemical classes × multiple
  time windows. Premature single-record optimization will hurt; vectorized
  spatial joins are what matter.
- Don't write into the toxicity sourcing CSV from this session. That's
  managed by the sibling session.

## Dependencies on the toxicity sourcing session

This pipeline reads `toxicity_lookup.csv` from the sibling toxicity-sourcing
work. If that work isn't complete yet:

- Use the illustrative values from `pur_substitution_analysis.py` as a
  placeholder so pipeline development can proceed, but do NOT publish or
  share any pipeline outputs that depend on those placeholder values.
- Mark all pipeline outputs that include toxicity weighting as
  "PRELIMINARY — illustrative toxicity values" until the sourced CSV
  becomes available.

## Setup checklist for a new session

1. Confirm Python environment: geopandas, rasterio, rioxarray, shapely,
   pyproj, pandas, requests installed.
2. Confirm PostGIS or DuckDB-spatial available.
3. Pull the CDPR PLSS feature service if not already local.
4. Pull CDL annual rasters for years of interest if not already local.
5. Verify access to PUR cache from sibling directory.
6. Verify access to `toxicity_lookup.csv` (or accept placeholder values
   per above).
7. Read this CLAUDE.md and the sibling project's CLAUDE.md before starting.

## When the pipeline is working

- Document the fall-back rules for unmatched site_codes in a methods
  appendix.
- Generate a small sanity-check report (a few maps, a few summary tables)
  that can be appended to the proposal as a methods supplement.
- Coordinate with Dennis on what location set should be used for the Level
  1 SDM analysis — almost certainly some combination of BBS route start
  points and a stratified sample from eBird Status & Trends grid cells.

## Files expected in this directory

- `CLAUDE.md` — this file
- `spatial_setup.py`, `pur_loader.py`, `crop_attribution.py`,
  `exposure_engine.py`, `validate.py` — to be created
- `data/` — local cache for CDL, DWR, PLSS layers
- `outputs/` — wide tables and validation reports
- `../pur_toxicity/` — sibling directory containing
  `pur_substitution_analysis.py`, `toxicity_lookup.csv`, and the PUR
  archive cache

## Running

Once the pipeline modules exist, the canonical workflow:

```bash
source .venv/bin/activate
python spatial_setup.py            # one-time, downloads layers
python pur_loader.py --years 2015-2023
python exposure_engine.py --locations input_locations.csv --output exposure.csv
python validate.py exposure.csv
```
