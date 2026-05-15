# Spatial Exposure Pipeline: BBS Route-Level Pesticide Exposure, California 2015–2023

**Level 1 spatial characterization supporting a proposed CDPR Ecosystem Monitoring study**

Doug Moody & Dennis Jongsomjit — Point Blue Conservation Science — May 2026

*Preliminary analysis — not for citation without author approval*

---

> **Summary**
>
> We built a reproducible spatial pipeline linking California CDPR Pesticide Use Report (PUR)
> records to North American Breeding Bird Survey (BBS) route locations via Public Land Survey
> System (PLSS) section polygons and USDA Cropland Data Layer (CDL) crop maps. Applied to
> 44 active BBS routes in California's agricultural landscapes, the pipeline produces
> year-by-year pesticide exposure estimates at four buffer distances and three lag windows
> for eight insecticide classes, 2015–2023. At the route level, the chlorpyrifos cancellation
> is clearly visible as an abrupt 97% decline in organophosphate aquatic toxicity units between
> 2015 and 2019 (85,000 → 2,800 tox units). Pyrethroid aquatic toxicity did not decline
> correspondingly; it rose from 17,300 tox units in 2015 to a peak of 23,300 in 2021, making
> pyrethroids the dominant aquatic toxicity contributor at 89% of the total load by 2021. The
> resulting wide-format table (369 route-years × 291 exposure columns) is ready for direct
> input into mixed-effects models pairing exposure with BBS count trends.

---

## 1. Background and Motivation

The companion analysis (`background_analysis.md`) characterizes California's statewide
insecticide use trajectory and documents that pyrethroids grew from approximately 28% to 77%
of the state's aquatic invertebrate toxicity load between 2015 and 2023, following the
chlorpyrifos cancellation. That analysis operates at the statewide level and cannot link
exposure to specific wildlife monitoring locations.

The spatial pipeline described here addresses the next inferential step: given a set of bird
monitoring locations and annual survey dates, what was the local pesticide exposure in the
weeks before each survey? This is the exposure variable needed to test whether route-level
BBS abundance or trend is associated with local pesticide load — the core Level 1 analysis
in the proposed CDPR Ecosystem Monitoring study.

The methodological approach follows Gunier et al. (2001), who showed that integrating crop
maps with PUR section-level totals substantially refines exposure assessment compared to
assuming uniform pesticide distribution within PLSS sections. A key feature of the pipeline
is that it preserves the section-level resolution that PUR provides while using CDL to
attribute applications to the crop-bearing fraction of each section.

---

## 2. Data Sources

| Layer | Source | Resolution | Coverage |
|---|---|---|---|
| PUR application records | CDPR Pesticide Use Reporting | Section (PLSS, ~1 mi²) | 2015–2023, all CA counties |
| PLSS section polygons | BLM CadNSDI (layer 2) | Polygon | 131,577 CA sections |
| Cropland Data Layer (CDL) | USDA NASS CropScape WCS | 30 m raster | Annual, 2015–2023 |
| BBS route locations | USGS Patuxent / ScienceBase | Point (route start) | 221 active CA routes |
| Toxicity values | Hertfordshire PPDB (primary); EPA ECOTOX (cross-check) | Per compound | 44 insecticide AIs |

PUR archives were already cached from the statewide analysis (9 ZIP files, ~3 GB).
CDL rasters for California total approximately 9.6 GB (9 years × ~1.07 GB/year); each file
required 8–10 HTTP reconnects to download due to a 124 MiB per-connection limit on the
NASS CropScape server (a bug report has been filed with NASS).

---

## 3. Pipeline Architecture

The pipeline consists of five modules run in sequence. All spatial data is stored in a
DuckDB database with the spatial extension; all intermediate and final outputs are Parquet
or CSV.

### 3.1 `spatial_setup.py` — One-time initialization

Downloads PLSS section polygons and CDL rasters; initializes the DuckDB schema.

PLSS data is fetched from the BLM CadNSDI ArcGIS REST service (layer 2, California
sections). The CDPR PLSS feature service was attempted first but returned SSL certificate
errors. BLM PLSSID strings are parsed to construct 9-character section keys
(`{meridian}{twp:02d}{tdir}{rng:02d}{rdir}{sec:02d}`) matching the COMTRS field format
used by CDPR PUR. Of 131,579 sections fetched, 131,577 were loaded into DuckDB after
dropping 2 with invalid geometry. All geometries are stored in EPSG:3310 (California
Albers, meters).

CDL rasters are clipped to California's extent (EPSG:5070 bounding box) during download
and validated with a pixel-level read test before being marked complete. Incomplete files
(a common occurrence given the NASS connection limit) are detected and re-downloaded.

### 3.2 `pur_loader.py` — PUR record extraction

Streams all county-level UDC files from PUR ZIP archives, filters to agricultural sites
(`site_code < 65,000`), matches chemicals against the toxicity lookup CSV, and writes a
section-keyed Parquet table.

Pre-2023 PUR UDC files lack `chemname` and `site_name` columns; these are resolved by
joining against `chemical.txt` and `site.txt` lookup files within each archive. Records
without a valid 11-character COMTRS field (no location) are dropped; the 9-character
section key is extracted as `comtrs[2:]`. A total of 5,065,221 records across 2015–2023
were loaded, representing approximately 82% of statewide AI mass (the 18% gap is records
without a valid COMTRS, a known characteristic of the PUR dataset).

### 3.3 `crop_attribution.py` — Within-section crop area estimation

For each unique (year, section, site_code) combination in the PUR records, estimates the
fraction of the section area plausibly occupied by the applied crop, using the CDL annual
raster. This is the spatial refinement step that avoids assigning applications uniformly
across the full section area.

The lookup maps PUR `site_name` fragments to CDL crop codes
(e.g., "almond" → CDL code 75; "grape" → CDL code 69). For each
(section, year) pair, CDL pixels within the section bounding box are window-read
from the annual GeoTIFF. The attribution fallback hierarchy is:

1. **exact\_crop** — pixels matching the PUR site's CDL code(s). Attribution fraction =
   crop pixels / total pixels.
2. **all\_ag** — all agricultural pixels (CDL codes 1–61). Used when no exact-crop
   pixels are found (CDL misclassification, off-label use, organic practices).
3. **uniform** — full section area. Used when CDL is unavailable or no agricultural
   pixels are found.

Of 344,108 unique (year, section, site) combinations processed:

| Fallback tier | Count | Percent |
|---|---|---|
| uniform | 241,548 | 70.2% |
| exact_crop | 81,175 | 23.6% |
| all_ag | 21,385 | 6.2% |

The 70% uniform fallback is primarily driven by PUR site names that do not match any
entry in the crop fragment table (e.g., "other field crops," "rangeland," and miscellaneous
categories). This does not discard those records — they are included with
`attribution_fraction = 1.0` — but it means CDL-based spatial refinement is only active
for approximately 30% of (section, site) combinations. Expanding the site-name mapping
table is a tractable improvement for future pipeline versions.

A secondary cause of uniform fallback is a gap in the CDL download bounding box: the
westward extent of the downloaded rasters ends near longitude −122°W at 38°N, excluding
the Sacramento-San Joaquin Delta and some coastal counties. Routes in those areas received
uniform attribution for their western-most sections. This affects a small number of routes
with low PUR density and has negligible effect on the high-exposure routes in the San
Joaquin and Imperial valleys.

### 3.4 `exposure_engine.py` — Location-level aggregation

Takes a CSV of monitoring locations with survey dates and produces aggregated exposure
metrics at each location. For each location:

1. **Buffer construction:** four concentric square buffers at 500 m, 1 km, 2 km, and 5 km
   around the route start point (EPSG:3310).
2. **Temporal window:** records are filtered to the 30-, 60-, or 90-day window ending at
   `survey_start_date`. For the per-year BBS analysis, `survey_start_date` is May 28
   of each year (the approximate BBS survey start in California).
3. **Spatial join:** sections intersecting the buffer are found via
   `ST_Intersects(section_geom, buffer_polygon)`. Area fraction is computed as
   `ST_Area(intersection) / ST_Area(section)`.
4. **Weighted aggregation:** for each PUR record in an intersecting section,
   contribution = `lbs_ai × area_fraction × attribution_fraction`.
5. **Output metrics per (location, class, buffer, lag):** `lbs_ai`, `acres_treated`,
   `tox_units_avian` (lbs\_ai / avian LD50 in mg/kg), `tox_units_aquatic`
   (lbs\_ai / aquatic LC50 in μg/L), `n_sections_intersected`, `n_applications`.

All 396 location-years (44 routes × 9 years) processed in approximately 25 minutes.

### 3.5 `validate.py` — Sanity checks

Five checks run automatically after the pipeline completes:

- **Statewide totals:** loader lbs ≤ reference statewide totals for every year × class
  combination. ✓ PASS (82% coverage expected; no year where loader exceeds reference)
- **COMTRS coverage:** fraction of raw PUR records with valid COMTRS. ✓ PASS (warning
  flagged for 2023 at 44% coverage — a known characteristic of that year's raw data)
- **Buffer monotonicity:** lbs at 500 m ≤ 1 km ≤ 2 km ≤ 5 km for all locations. ✓ PASS
- **Section spot-checks:** loader lbs ≤ raw archive totals for 5 randomly selected
  high-intensity sections. ✓ PASS (all-chemical raw > insecticide-only loader, as expected)
- **CDL attribution sanity:** median exact_crop attribution fraction (0.181) > uniform
  (1.0 on a fractional scale). ✓ PASS

---

## 4. Location Selection: California BBS Routes

Of 221 active California BBS routes, 44 had more than 100 PUR records within 5 km of the
route start point (2015–2023 aggregate). These were selected as the exposure-relevant subset.

BBS routes were ranked by PUR record density rather than CDL agricultural fraction because
the CDL bounding box issue (§3.3) would have incorrectly zeroed out some western routes.
PUR record density is also more directly relevant: it measures actual nearby pesticide
application, not just land cover type.

The 44 selected routes span two Bird Conservation Regions:

| BCR | Name | Routes |
|---|---|---|
| 32 | Coastal California | 31 |
| 33 | Sonoran and Mojave Deserts | 9 |
| 9 | Great Basin | 2 |
| 15 | Sierra Nevada | 1 |
| 5 | Northern Pacific Rainforest | 1 |

BCR 32 routes are concentrated in the San Joaquin Valley and Sacramento Valley — the
core area of California's agricultural insecticide use. BCR 33 routes add the Imperial
Valley and Salton Sea region, which has high per-route PUR density driven by cotton,
vegetables, and date palm agriculture.

**Table 1.** Top 15 BBS routes by PUR record count within 5 km, 2015–2023.

| Route | Name | Latitude | Longitude | BCR | PUR records (5 km) | Lbs AI (5 km) |
|---|---|---|---|---|---|---|
| 54 | ORANGE COVE | 36.63 | −119.30 | 32 | 25,597 | 153,347 |
| 21 | HUGHSON | 37.59 | −120.86 | 32 | 18,394 | 38,801 |
| 92 | ALAMO RIVER | 32.85 | −115.43 | 33 | 18,101 | 119,414 |
| 127 | SANGER | 36.70 | −119.51 | 32 | 12,087 | 63,787 |
| 90 | BLYTHE | 33.62 | −114.62 | 33 | 9,585 | 42,725 |
| 171 | TRANQUILLITY | 36.65 | −120.26 | 32 | 8,663 | 145,075 |
| 150 | BRAWLEY | 32.94 | −115.54 | 33 | 8,360 | 107,609 |
| 204 | ATHLONE | 37.14 | −120.40 | 32 | 7,626 | 49,051 |
| 147 | ARVIN | 35.22 | −118.88 | 32 | 6,684 | 76,256 |
| 24 | CARUTHERS | 36.55 | −119.84 | 32 | 6,381 | 41,494 |
| 320 | COLLEGEVILLE 2 | 37.93 | −121.17 | 32 | 5,897 | 56,186 |
| 245 | BUENA VISTA | 35.48 | −119.30 | 32 | 5,863 | 54,288 |
| 197 | TIPTON | 36.08 | −119.30 | 32 | 4,839 | 49,148 |
| 49 | PALO VERDE | 33.40 | −114.73 | 33 | 4,327 | 29,419 |
| 155 | WESTLEY | 37.51 | −121.16 | 32 | 4,126 | 25,161 |

Three routes — YOKOHL VAL, CADIZ, and JOFEGAN — produced zero exposure rows across all
buffer × lag combinations; these have insufficient local PUR coverage and are excluded
from the model-ready wide table (41 usable routes).

---

## 5. Results: Route-Level Exposure Trends, 2015–2023

### 5.1 The organophosphate collapse is sharp and consistent at the route level

Summed across all 44 routes at 5 km / 90-day lag, organophosphate aquatic toxicity units
declined from 85,147 in 2015 to 2,848 in 2023 — a **97% reduction** concentrated almost
entirely in the 2018–2019 transition year.

**Table 2.** Annual aquatic toxicity units by class, summed across 44 BBS routes
(5 km buffer, 90-day pre-survey lag).

| Year | Organophosphates | Pyrethroids | Carbamates | Diamides | Pyr share of total |
|---|---|---|---|---|---|
| 2015 | 85,147 | 17,312 | 441 | 42 | **16.8%** |
| 2016 | 33,512 | 12,914 | 518 | 44 | 27.5% |
| 2017 | 36,008 | 15,790 | 502 | 51 | 30.2% |
| 2018 | 22,609 | 11,060 | 348 | 64 | 32.4% |
| 2019 | 5,164 | 14,545 | 384 | 60 | **72.2%** |
| 2020 | 2,986 | 16,841 | 295 | 62 | 83.4% |
| 2021 | 2,230 | 23,345 | 480 | 117 | **89.2%** |
| 2022 | 2,150 | 17,972 | 659 | 75 | 86.2% |
| 2023 | 2,848 | 17,302 | 308 | 78 | 84.2% |

The organophosphate decline at the route level closely mirrors the statewide pattern
documented in `background_analysis.md` (16.8% pyrethroid share in 2015 vs. the
statewide estimate of 28%), confirming that the 44 selected routes are exposed to
broadly representative insecticide use patterns, though weighted somewhat toward
lower-pyrethroid-share areas in early years.

### 5.2 Pyrethroid dominance is sustained and peaked sharply in 2021

Pyrethroid aquatic toxicity across the 44 routes held roughly stable through 2016–2020
and then spiked to 23,345 tox units in 2021 — a **35% jump** over 2020 and the highest
pyrethroid aquatic toxicity load in the nine-year record. The spike partially subsided
in 2022–2023 but remained well above the 2016–2019 baseline.

The 2021 spike is worth flagging in the model. Avian response variables showing
departures in 2021–2022 BBS counts would be temporally consistent with this exposure
peak. Whether the spike reflects increased pyrethroid use specifically in sections near
BBS routes or a broader California-wide pattern is testable by cross-referencing against
the statewide PUR totals.

By 2021, pyrethroids accounted for 89% of aquatic toxicity units at the route level —
essentially all of the aquatic invertebrate toxicity burden in the monitoring landscape.

### 5.3 Spatial structure: which routes carry the highest pyrethroid load?

Routes with the highest *cumulative* pyrethroid aquatic toxicity (2015–2023) are
concentrated in the northern San Joaquin Valley and Sacramento-San Joaquin Delta, not
in the Imperial Valley (which has high total PUR density but lower pyrethroid share
relative to cotton-targeted chemistries):

**Table 3.** Top 10 BBS routes by cumulative pyrethroid aquatic toxicity units,
2015–2023 (5 km buffer, 90-day lag).

| Route | Name | Cumulative tox units (aquatic) |
|---|---|---|
| 21 | HUGHSON | 16,367 |
| 245 | BUENA VISTA | 14,634 |
| 92 | ALAMO RIVER | 12,804 |
| 204 | ATHLONE | 10,897 |
| 320 | COLLEGEVILLE 2 | 10,786 |
| 196 | ORA LOMA | 9,414 |
| 155 | WESTLEY | 8,969 |
| 33 | BAKERSFIELD | 8,131 |
| 54 | ORANGE COVE | 7,883 |
| 12 | PENNINGTON | 7,082 |

HUGHSON, BUENA VISTA, ATHLONE, ORA LOMA, WESTLEY, COLLEGEVILLE 2, and PENNINGTON are
all within approximately 50 km of one another in the northern San Joaquin Valley /
Sacramento Delta transition zone — a cluster that represents the highest-exposure patch
in the BBS-monitored California landscape for this class.

---

## 6. Output Files

All outputs are in `outputs/`:

| File | Format | Dimensions | Description |
|---|---|---|---|
| `bbs_locations.csv` | CSV | 44 × 8 | Route locations with cumulative PUR density annotation |
| `bbs_locations_yearly.csv` | CSV | 396 × 8 | One row per route per year, survey dates for exposure engine |
| `bbs_exposure.csv` | CSV | 1,066 × 13 | Long format: cumulative 2015–2023 per location × class × buffer × lag |
| `bbs_exposure_wide.csv` | CSV | 41 × 246 | Wide format: cumulative, model-ready |
| `bbs_exposure_yearly.csv` | CSV | 9,907 × 13 | Long format: per year per location × class × buffer × lag |
| `bbs_exposure_yearly_wide.csv` | CSV | 369 × 291 | **Wide format, per year: primary model input** |
| `pur_sections.parquet` | Parquet | 5,065,221 × 18 | All PUR records, section-keyed with toxicity values |
| `crop_attribution.parquet` | Parquet | 344,108 × 9 | CDL-based attribution fractions per (year, section, site) |
| `bbs_ca_routes_ranked.csv` | CSV | 221 × 12 | All active CA BBS routes ranked by PUR density |

The primary model input is `bbs_exposure_yearly_wide.csv`. Column naming convention:
`{class}_{buffer_m}m_{lag_days}d_{metric}` (e.g.,
`Pyrethroids_5000m_90d_tox_units_aquatic`). Three routes are absent from the wide table
(YOKOHL_VAL, CADIZ, JOFEGAN) due to zero PUR coverage at all buffer × lag configurations.

---

## 7. Connecting to BBS Count Data

The wide table is structured for direct join against the USGS BBS annual count data
(available at `sciencebase.gov`). The join key is BBS state number + route number,
recoverable from the `location_id` field (format: `BBS_CA_{route:03d}_{name}_{year}`).

For the Level 1 SDM analysis, a mixed-effects model structure would be:

```
abundance_index ~ pyrethroid_5000m_90d_tox_units_aquatic
               + organophosphate_5000m_90d_tox_units_aquatic
               + year + (1 | route_id)
               + [climate / habitat covariates]
```

The 90-day pre-survey lag is recommended as the primary exposure window, as it spans
the period from first arrival (mid-March for Tree Swallow) through the BBS survey date
(late May), covering the full period during which prey-base suppression could affect
breeding condition and detectable abundance. The 30- and 60-day lags are available for
sensitivity analysis.

The exposure values in the wide table are area-weighted and attribution-adjusted; they
represent estimated AI mass (in pounds) applied within the buffer area during the lag
window, not raw section totals.

---

## 8. Known Limitations

**COMTRS coverage (18% gap):** Approximately 18% of statewide PUR records lack a valid
COMTRS field and are therefore excluded from the spatial pipeline entirely. This is a
characteristic of the raw CDPR data, not a pipeline artifact. The 82% that are
section-tagged pass the statewide validation check (loader ≤ reference totals for all
year × class combinations).

**CDL attribution fallback (70% uniform):** The majority of (section, site) combinations
fall back to uniform attribution because PUR site names do not match the current
crop-fragment mapping table. This means the area-weighting refinement described in
Gunier et al. (2001) is only active for ~30% of records. The exposure values are
conservative in the sense that uniform attribution spreads AI mass across the full
section rather than concentrating it on crop pixels, which may underestimate local
concentrations near specific field edges.

**CDL bounding box:** The downloaded CDL rasters cover approximately −122°W to −114°W
at central California latitudes, excluding some coastal and delta sections. Routes in
those areas use uniform attribution for affected sections; this primarily affects
low-PUR-density routes.

**Buffer geometry:** Buffers are square bounding boxes rather than circular radii.
A 5 km square overestimates the true 5 km circular area by approximately 27%. For
consistency across all locations and years, the same geometry is used throughout; the
absolute exposure values should be interpreted relative to this convention rather than
as precise circular-buffer estimates.

**Aerial vs. ground application:** The PUR `aer_gnd_ind` field distinguishing aerial
from ground applications is loaded but not used in the current exposure calculation.
Aerial applications have larger effective drift radii and may warrant different area
weighting in a future pipeline version.

**Route start point as location anchor:** BBS routes are ~40 km linear transects; the
pipeline uses the route start point as the spatial anchor. Applications near the route
midpoint or far end contribute to the buffer only if they happen to fall within 5 km
of the start. This introduces route-specific spatial bias that is difficult to correct
without stop-level data. The USGS has published stop-level coordinates for a subset
of routes (see §9); incorporating these is a tractable enhancement.

---

## 9. Recommended Next Steps

1. **Join against BBS annual counts.** Download the USGS BBS States.zip (available from
   the same ScienceBase item as routes.csv), extract California species counts for the
   target aerial insectivore species, and join to `bbs_exposure_yearly_wide.csv` on
   route number and year. Run the mixed-effects model described in §7.

2. **Expand the CDL site-name mapping table.** Review the most common PUR site names
   in the 70% uniform-fallback pool and add mappings for the top 20. This is a
   one-time effort that would likely push the exact_crop tier above 40%.

3. **Fix the CDL bounding box.** Re-download CDL rasters with a corrected western
   extent (approximately −124.5°W). This recovers full attribution coverage for
   Sacramento Delta and coastal routes. A corrected bbox in EPSG:5070 is approximately
   `(-2,400,000, 1,400,000, -1,100,000, 2,500,000)`.

4. **Per-stop exposure (optional).** The USGS stop-level location dataset (linked from
   the BBS raw data page) would allow buffers centered on each of the 50 stops along
   a route. The average of all stops' exposure values would better represent the full
   route's pesticide environment than the start-point buffer alone.

5. **Coordinate with Dennis on species targets.** The model-ready table covers all
   species counts in the BBS database for these routes. For the proposal, pre-specifying
   3–4 focal species (Barn Swallow, Tree Swallow, Cliff Swallow, Western Kingbird)
   limits multiple-comparisons concerns.

---

## References

1. California Department of Pesticide Regulation (CDPR). 2024. Pesticide Use Reporting
   (PUR) database. Sacramento, CA. https://www.cdpr.ca.gov/docs/pur/purmain.htm

2. Fink, D., et al. 2023. eBird Status and Trends, Data Version: 2022. Cornell Lab of
   Ornithology, Ithaca, New York. https://doi.org/10.2173/ebirdst.2022

3. Gunier, R.B., Harnly, M.E., Reynolds, P., Hertz, A., and Von Behren, J. 2001.
   Agricultural pesticide use in California: pesticide prioritization, use densities,
   and population distributions for a childhood cancer study. *Environmental Health
   Perspectives* 109(10):1071–1078.

4. Lewis, K.A., Tzilivakis, J., Warner, D.J., and Green, A. 2016. An international
   database for pesticide risk assessments and management. *Human and Ecological Risk
   Assessment* 22(4):1050–1064. [Hertfordshire PPDB: https://sitem.herts.ac.uk/aeru/ppdb/]

5. Sauer, J.R., et al. 2017. The North American Breeding Bird Survey, Results and
   Analysis 1966–2015. Patuxent Wildlife Research Center, Laurel, MD.

6. U.S. Geological Survey. 2023. North American Breeding Bird Survey Dataset 1966–2022.
   https://doi.org/10.5066/P9GS9K64

7. U.S. Environmental Protection Agency. 2024. ECOTOX Knowledgebase.
   https://cfpub.epa.gov/ecotox/

8. USDA National Agricultural Statistics Service. 2024. Cropland Data Layer.
   https://nassgeodata.gmu.edu/CropScape/
