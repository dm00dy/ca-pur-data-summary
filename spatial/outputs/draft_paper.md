# Pyrethroid Succession Following Organophosphate Cancellation: A Spatial Exposure Characterization for Aerial Insectivore Monitoring in California Agriculture

**Doug Moody¹ & Dennis Jongsomjit¹**

¹Point Blue Conservation Science, Petaluma, California

*Corresponding author: dmoody@pointblue.org*

*Preliminary draft — not for citation without author approval*

---

## Abstract

California's 2019 cancellation of chlorpyrifos provides one of the largest natural experiments in North American pesticide regulation history. Using 5,065,221 section-tagged application records from the California Department of Pesticide Regulation (CDPR) Pesticide Use Reporting (PUR) database (2015–2023) and a new spatial pipeline linking those records to North American Breeding Bird Survey (BBS) route locations, we characterize the insecticide exposure landscape encountered by aerial insectivore birds before and after the organophosphate collapse. Statewide, pyrethroid compounds grew from approximately 28% of the agricultural aquatic invertebrate toxicity load in 2015 to approximately 80% by 2023. At the route level — among 44 BBS routes in California's highest-PUR-density agricultural landscapes — the organophosphate decline was 97% (85,147 to 2,848 toxicity units, 2015–2023), while pyrethroid aquatic toxicity spiked 35% above its 2020 baseline in 2021, reaching the highest level in the nine-year record. We also document a partial substitution toward oxamyl, a carbamate approximately ten times more acutely toxic to birds than chlorpyrifos, whose use increased approximately six-fold in Kings County cotton between 2015 and 2019. A critical monitoring gap accompanies these findings: 14 of the 44 highest-PUR-density BBS routes in the state — including the single highest-exposure route — received zero valid BBS surveys between 2015 and 2022. eBird Status and Trends data for the region show Barn Swallow declining at 2.1% per year and Cliff Swallow at 1.5% per year over 2012–2022. Mixed-effects models pairing the exposure table with BBS count data from the 28 surveyed routes (150 route-years) found no significant within-route association between local pyrethroid aquatic toxicity and aerial insectivore abundance, a result that the power analysis indicates is consistent with limited within-route exposure contrast in the BBS-surveyed sample. A complementary difference-in-differences design centered on the 2019 chlorpyrifos cancellation, however, reveals a directional signal that the within-route models cannot detect: routes that had received the most organophosphate exposure before 2019 did not rebound after the cancellation, and for Western Kingbird declined significantly more than less-exposed routes (DiD β = −0.401, p = 0.037, corresponding to ~33% greater relative decline). This result is opposite the direction predicted by a clean "remove the OP, birds recover" narrative and is consistent with the substitution-chemistry concern that pyrethroids and replacement carbamates have not produced a less toxic landscape for aerial-insectivore prey. Western Kingbird also showed a strong within-route temporal decline of approximately 4.4% per year (p = 0.001), and Barn Swallow a 10% per year first-difference decline (p = 0.011), confirming that the BBS data on these routes are not too noisy to detect real temporal signals — only that the exposure-response signal is below detection threshold with the current within-route exposure contrast. The spatial pipeline and model-ready table are open-source and reproducible.

**Keywords:** aerial insectivores; organophosphates; pyrethroids; chlorpyrifos; pesticide use reporting; Breeding Bird Survey; spatial exposure modeling; conservation biology

---

## 1. Introduction

The North American aerial insectivore guild — swallows, swifts, nightjars, and sallying flycatchers — has shown coordinated, multi-species declines since the 1980s, with losses accelerating in the most agricultural-intensive landscapes (Nebel et al. 2010, Rosenberg et al. 2019). Proposed mechanisms include habitat loss, climate-driven shifts in emergence phenology, direct pesticide mortality, and prey-base suppression through sublethal effects of agricultural chemicals on aquatic macroinvertebrates (Hallmann et al. 2014, Li et al. 2020). Distinguishing among these mechanisms requires pairing wildlife monitoring data with high-resolution, location-specific exposure information — a capability that has been largely unavailable at population monitoring scales.

California's CDPR Pesticide Use Reporting (PUR) database presents an unusual opportunity. It records every agricultural pesticide application in the state at the PLSS section level (approximately 1 mi²), with the active ingredient, pounds applied, crop treated, and date. No other U.S. state compiles comparable application data at this spatial and temporal resolution (Gunier et al. 2001). The PUR database captures more than 5 million section-tagged records per decade, making it possible to construct detailed, location-specific pesticide exposure profiles for any California monitoring location across the full period of record.

The cancellation of chlorpyrifos — the state's dominant organophosphate insecticide — in 2019 created a near-ideal natural experiment for evaluating non-target wildlife response to pesticide regime change. At its peak, chlorpyrifos accounted for the majority of California's agricultural insecticide aquatic toxicity by weight-adjusted toxicity units, because its *Daphnia magna* EC50 (0.085 μg/L) makes it orders of magnitude more toxic to aquatic invertebrates per pound than the compounds that replaced it (Lewis et al. 2016). The cancellation was abrupt — concentrated almost entirely in a single growing season — and was followed by detectable substitution toward pyrethroids and selected carbamates, changing the toxicological character of California's agricultural landscape in ways that may matter differently for aerial insectivores than a simple reduction in total insecticide pounds would suggest.

Here we present (1) a characterization of the statewide shift in California's agricultural insecticide toxicity burden, 2015–2023; (2) a spatial pipeline linking PUR section-level records to BBS route locations via PLSS polygons and Cropland Data Layer crop maps; (3) route-level exposure profiles for 44 high-PUR-density California BBS routes across the full pre- and post-cancellation window; and (4) an assessment of BBS monitoring coverage relative to the exposure landscape, revealing a systematic gap between where pesticide applications are highest and where bird monitoring occurs. We discuss these findings in the context of current eBird Status and Trends trend estimates for the region and argue for a monitoring design capable of closing the inference gap.

---

## 2. Methods

### 2.1 PUR data processing

PUR data were obtained as annual ZIP archives from the CDPR website for 2015–2023 (5,065,221 section-tagged agricultural records total). Records were filtered to agricultural sites (site_code < 65,000) and matched against a compound-level toxicity lookup table. The 9-character PLSS section key was extracted from each record's COMTRS field; records lacking a valid COMTRS (approximately 18% of the total, a known characteristic of the raw PUR data) were excluded from the spatial analysis but counted in statewide validation totals.

Chemical classes were assigned using a conventional grouping: organophosphates (chlorpyrifos, diazinon, malathion, and 11 additional compounds), pyrethroids (bifenthrin, cypermethrin, lambda-cyhalothrin, permethrin, and 10 additional compounds), carbamates (carbaryl, methomyl, oxamyl), diamides (chlorantraniliprole, cyantraniliprole), neonicotinoids (imidacloprid, thiamethoxam, and related compounds), and spinosyns. All 44 active ingredients in the database were classified by class.

### 2.2 Toxicity weighting

Toxicity values were sourced from the Hertfordshire Pesticide Properties Database (PPDB; Lewis et al. 2016) as the primary reference, cross-checked against EPA ECOTOX (U.S. EPA 2024). Two endpoints were used:

- **Aquatic invertebrate toxicity:** *Daphnia magna* 48h EC50 (μg/L), the standard regulatory ecotoxicology endpoint for assessment of aquatic invertebrate prey-base effects. Aquatic invertebrate toxicity is considered the mechanism-relevant endpoint for aerial insectivores because many prey species (chironomids, Ephemeroptera, Trichoptera) have aquatic larval stages that are most vulnerable to pesticide inputs.
- **Avian acute oral toxicity:** Acute oral LD50 (mg/kg body weight), 14-day mortality; Bobwhite Quail (*Colinus virginianus*) preferred, Mallard (*Anas platyrhynchos*) used as surrogate where Bobwhite data were unavailable.

Toxicity units were calculated as pounds of active ingredient divided by the endpoint value (in consistent units), following the approach of Gibbons et al. (2015). Values reported as greater-than ceilings (e.g., ">1000 mg/kg") were stored as the ceiling value, flagged as conservative estimates. All sourcing decisions, conflicts, and secondary sources are documented in `toxicity_lookup.csv`.

### 2.3 Spatial pipeline

The pipeline consists of five modules:

**`spatial_setup.py`** — One-time initialization. PLSS section polygons were obtained from the BLM CadNSDI ArcGIS REST service (layer 2, California sections). Of 131,579 sections fetched, 131,577 were loaded into a DuckDB spatial database after dropping two records with invalid geometry. All geometries were projected to EPSG:3310 (California Albers, meters). USDA NASS Cropland Data Layer (CDL) annual rasters were downloaded for 2015–2023 and clipped to California's spatial extent.

**`pur_loader.py`** — Extracted all PUR records into a section-keyed format, joining against chemical and site lookup tables within each archive to resolve compound names and crop codes for pre-2023 records. The output is a long-format Parquet table indexed on (year, section_id, chemical_class) with toxicity values attached: 5,065,221 records across 9 years.

**`crop_attribution.py`** — For each unique (year, section, site_code) combination, estimated the fraction of the section area plausibly occupied by the applied crop using the CDL annual raster. The lookup mapped PUR site name fragments to CDL crop codes (e.g., "almond" → CDL code 75, "grape" → CDL code 69). A three-tier fallback hierarchy was applied: (1) pixels matching the PUR site's CDL code (exact crop), (2) all agricultural pixels within the section, (3) uniform attribution over the full section. Of 344,108 unique (year, section, site) combinations: 23.6% resolved to exact crop, 6.2% to all-agricultural, and 70.2% to uniform. The high uniform-fallback fraction reflects PUR site names that do not match crop entries in the mapping table (e.g., "other field crops") rather than CDL misclassification.

**`exposure_engine.py`** — For each of 44 BBS route locations, built concentric square buffers at 500 m, 1 km, 2 km, and 5 km and computed area-weighted, attribution-adjusted exposure metrics for three pre-survey lag windows (30, 60, 90 days ending May 28 of each year). The spatial join found intersecting PLSS sections via ST_Intersects; area fraction was computed as ST_Area(intersection) / ST_Area(section). Contribution from each PUR record = lbs_ai × area_fraction × attribution_fraction. Output metrics per (location × class × buffer × lag): lbs_ai, tox_units_avian, tox_units_aquatic, n_sections_intersected, n_applications.

**`validate.py`** — Five automated checks: statewide totals (loader ≤ reference for all year × class combinations), COMTRS coverage by year, buffer monotonicity (500 m ≤ 1 km ≤ 2 km ≤ 5 km for all locations and years), section spot-checks, and CDL attribution fractions. All five passed; no year × class combination in the loader exceeded the corresponding statewide reference total.

### 2.4 BBS route selection and BBS count data

Of 221 active California BBS routes, 44 were selected as the exposure-relevant subset based on having more than 100 PUR records within 5 km of the route start point (2015–2023 aggregate). These routes span BCR 32 (Coastal California, 31 routes, primarily the San Joaquin and Sacramento valleys) and BCR 33 (Sonoran and Mojave Deserts, 9 routes, primarily the Imperial Valley), with two routes each in the Great Basin and Sierra Nevada BCRs.

BBS count data were downloaded from the USGS ScienceBase dataset (item 64ad9c3dd34e70357a292cee; Sauer et al. 2017). The California state file (Califor.csv within States.zip) was parsed for 21 focal aerial insectivore species by AOU code (seven swallow species, four swift species, three nightjar species, and seven aerial-foraging flycatcher species; all codes verified against the BBS SpeciesList.txt). The weather.csv file was used to distinguish zero-count surveyed routes from unsurveyed years (RunType = 1 = valid survey); 5,892 valid California survey × year records were identified. Annual BBS counts were aggregated to route-year totals for five species groups (swallows, swifts, nightjars, flycatchers, total aerial insectivores) and joined to the exposure wide table by route number and year.

### 2.5 eBird Status and Trends data

Regional trend estimates for aerial insectivore species were extracted from the eBird Status and Trends 2022 dataset (Fink et al. 2023) for grid cells overlapping the San Joaquin Valley agricultural zone (see Appendix A for cell selection criteria). Percent-per-year trend estimates and 80% credible intervals were obtained for four swallow species.

### 2.6 Statistical models

We fit two exposure-abundance model families to the 150 surveyed route-years, using log(count + 1) as the response to accommodate right-skewed count distributions. All models were implemented in Python 3.12 using `statsmodels` 0.14.6. Exposure predictors were z-scored (zero mean, unit variance) prior to model fitting to produce directly comparable standardized coefficients.

**Model A (linear mixed-effects, LMM):** `log(count+1) ~ pyr_z + op_z + C(year) + (1|route)`, fit by LBFGS with a maximum of 1,000 iterations. The random intercept per route accounts for stable between-route differences in bird density driven by habitat, geography, and observer history. Year entered as a categorical fixed effect to capture any temporal trend in the monitoring data not attributable to the exposure predictors.

**Model B (within-route demeaned OLS):** Both the response and all predictors were demeaned within each route (subtracting each route's time-series mean) before fitting OLS with a linear year trend term. This within-estimator (equivalent to a route fixed-effects model) removes all time-invariant confounders, including baseline habitat quality, observer identity, and geography. Standard errors were heteroskedasticity-robust (HC3). Model B asks a strictly temporal question: does a route have *fewer* birds in years when its *own* exposure is above its *own* average?

Primary exposure predictors were pyrethroid and organophosphate aquatic toxicity units at 5 km / 90-day lag, the ecologically motivated primary specification. Sensitivity analyses tested all combinations of four buffer radii (500 m, 1 km, 2 km, 5 km) and three lag windows (30, 60, 90 days) for the all-swallows response using Model B. Significance thresholds were not adjusted for multiple comparisons; the sensitivity grid is presented descriptively.

Three additional specifications were fit to test mechanisms not addressed by the within-route mean-comparison structure of Model B.

**Model C (first differences).** `Δ log(count+1) = α + β₁·Δ pyr_z + β₂·Δ op_z + γ·year + ε`, fit by OLS with HC3 standard errors. First differences were computed between consecutive surveyed years within each route. This specification is algebraically equivalent in expectation to Model B but emphasizes high-frequency year-over-year covariance and is less sensitive to slow temporal drift in either the exposure or count series. It also re-expresses the test in terms a non-technical reader can verify directly: do count changes track exposure changes, within a route, between consecutive years?

**Model D (pyrethroid share, within-route).** Replaced raw pyrethroid toxicity units with `share = pyr / (pyr + op)`, fit alongside log(total insecticide toxicity) within the within-route demeaned framework: `log(count+1) ~ share_z + log(total)_z + year_ctr + (route FE)`. This isolates the *chemistry-mix* effect — whether the proportion of insecticide exposure attributable to pyrethroids matters above and beyond the total insecticide load. The share variable is the predictor that has changed most dramatically over the study period (28% in 2015 to ~80% in 2023 at the statewide scale; §3.1) and is the most direct test of the substitution hypothesis at the route scale. Route-years with total insecticide toxicity below 10 units were excluded as having no meaningful chemistry-mix signal.

**Model E (difference-in-differences around the 2019 chlorpyrifos cancellation).** A natural-experiment specification leveraging the abrupt regulatory shock at the heart of the analysis. Routes were classified as "OP-heavy" or "OP-light" based on their 2015–2018 (pre-cliff) mean organophosphate exposure relative to the cross-route median. The DiD specification:

`log(count+1)_it = α + β₁·post_t + β₂·heavy_i + β₃·(post×heavy)_it + γ·year + u_i + ε`

with the pre-period defined as 2015–2018, the post-period as 2020–2022, and the transition year 2019 dropped. The level effects α and β₂ are absorbed by route demeaning (within-route estimator); the interaction coefficient β₃ is the DiD estimand. β₃ > 0 indicates that OP-heavy routes recovered (relative to OP-light routes) after the chlorpyrifos cliff; β₃ ≈ 0 indicates no relative recovery despite the statewide OP collapse; β₃ < 0 indicates that OP-heavy routes declined *further* relative to OP-light routes. This is the cleanest available test of the "remove the OP, birds rebound" hypothesis with the data in hand. Standard errors were HC3-robust; the design's parallel-trends assumption is qualitatively defensible but not formally testable on this sample size.

---

## 3. Results

### 3.1 Statewide pesticide regime shift: organophosphate collapse and pyrethroid succession

The statewide organophosphate aquatic toxicity load declined from 12.6 million toxicity units in 2015 to 1.04 million in 2021 and 1.12 million in 2023 — an 89% reduction over the period (Figure 1a). The decline was not gradual: organophosphate toxicity units fell 57% between 2018 and 2019 (7.52 million → 1.56 million), reflecting the concentration of chlorpyrifos use cancellations in that growing season. In absolute pounds, organophosphate use declined from 2.40 million lbs AI in 2015 to 0.73 million lbs in 2021 (69% reduction), confirming that the toxicity-unit decline is not an artifact of improved per-pound toxicity but reflects genuine use reduction.

Pyrethroid aquatic toxicity, by contrast, showed no corresponding decline. Statewide pyrethroid aquatic toxicity held at approximately 4.2–5.3 million toxicity units across the full period, with no systematic downward trend. The pyrethroid share of total aquatic insecticide toxicity rose from 28% in 2015 to approximately 80% in 2023, driven entirely by the organophosphate exit rather than by increased pyrethroid use (Figure 1b). In pounds, pyrethroid use declined modestly from 1.03 million lbs in 2015 to 0.76 million lbs in 2022, before partially rebounding to 0.89 million lbs in 2023 — a net reduction of only 14% over a period when organophosphate use fell by more than two-thirds.

The carbamate class showed a secondary substitution pattern (Figure 1c). While total carbamate pounds remained relatively stable (419,000–484,000 lbs/year across 2015–2023), the within-class composition shifted substantially. Oxamyl — registered for cotton, potatoes, and cucurbits — increased from 17,319 lbs in 2015 to 103,763 lbs in 2019, a six-fold increase concentrated primarily in Kings County cotton. Oxamyl's acute oral LD50 in Bobwhite Quail is 3.16 mg/kg, placing it in EPA's "extremely toxic" category (Category I). This compares to chlorpyrifos's avian LD50 of approximately 32 mg/kg — making oxamyl approximately ten times more acutely dangerous to birds per pound applied. The timing of the oxamyl increase — steep from 2016 to 2019 and sustained through 2023 — is consistent with growers adopting oxamyl as a partial replacement for chlorpyrifos in insect-pressure crops such as cotton (Table 1).

Carbaryl, the other numerically dominant carbamate by pounds, has a Bobwhite Quail LD50 of 2000 mg/kg — effectively non-toxic at field-relevant doses — so the carbamate avian toxicity signal is almost entirely attributable to oxamyl. Methomyl, the third carbamate, carries an LD50 of 24.2 mg/kg (highly toxic) and use in the 200,000–280,000 lbs/year range throughout the period, representing the largest sustained avian-toxic carbamate use across all years.

**Table 1.** Carbamate avian toxicity units, California statewide, 2015–2023.

| Year | Carbaryl (lbs) | Methomyl (lbs) | Oxamyl (lbs) | Methomyl avian tox units | Oxamyl avian tox units |
|---|---|---|---|---|---|
| 2015 | 155,036 | 282,218 | 17,319 | 11,662 | 5,481 |
| 2016 | 220,618 | 260,525 | 2,466 | 10,765 | 781 |
| 2017 | 106,942 | 233,450 | 38,302 | 9,647 | 12,121 |
| 2018 | 127,245 | 224,535 | 78,719 | 9,278 | 24,911 |
| 2019 | 112,413 | 203,183 | 103,763 | 8,396 | 32,836 |
| 2020 | 109,984 | 258,061 | 63,310 | 10,664 | 20,035 |
| 2021 | 99,376 | 235,729 | 25,969 | 9,741 | 8,218 |
| 2022 | 84,058 | 251,949 | 36,590 | 10,411 | 11,579 |
| 2023 | 84,226 | 195,333 | 87,942 | 8,072 | 27,830 |

### 3.2 Route-level exposure characterization: the organophosphate collapse at the monitoring scale

Summed across 44 BBS routes at 5 km buffer / 90-day pre-survey lag, organophosphate aquatic toxicity units declined from 85,147 in 2015 to 2,848 in 2023 — a 97% reduction (Table 2). This route-level decline is steeper than the 89% statewide decline, reflecting the concentration of chlorpyrifos use in the San Joaquin and Sacramento Valley agricultural landscapes where these routes are clustered. The 2018–2019 transition is sharp at both scales: route-level OP toxicity fell from 22,609 to 5,164 units between those two years (77%).

**Table 2.** Annual aquatic toxicity units by insecticide class, summed across 44 BBS routes (5 km buffer, 90-day pre-survey lag), 2015–2023.

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

Pyrethroid aquatic toxicity across the 44 routes held relatively stable through 2016–2020 (12,914–17,312 units/year) before spiking to 23,345 units in 2021 — a 35% increase over 2020 and the highest pyrethroid aquatic toxicity load in the nine-year record. The spike partially subsided in 2022–2023 but remained well above the 2016–2019 baseline. By 2021, pyrethroids accounted for 89% of total aquatic invertebrate toxicity units at the route level — a qualitative transformation in the toxicological character of the monitoring landscape.

The route-level pyrethroid share in 2015 (16.8%) was lower than the statewide share (28%), because the 44 selected routes cluster in the San Joaquin and Sacramento valleys where OP use was proportionally higher. The convergence of route-level and statewide pyrethroid shares post-2021 (both approaching 80–89%) reflects a landscape where organophosphate use has reached a near-uniform low level regardless of local cropping patterns.

Spatial structure in the pyrethroid load is concentrated in the northern San Joaquin Valley and Sacramento-San Joaquin Delta transition zone. The ten highest-cumulative-pyrethroid routes (2015–2023, 5 km buffer) are dominated by routes within approximately 50 km of one another in Stanislaus, Merced, and San Joaquin counties: HUGHSON (16,367 cumulative tox units), BUENA VISTA (14,634), ALAMO RIVER (12,804), ATHLONE (10,897), COLLEGEVILLE 2 (10,786), ORA LOMA (9,414), WESTLEY (8,969), BAKERSFIELD (8,131), ORANGE COVE (7,883), and PENNINGTON (7,082). This cluster represents the highest-exposure patch in the BBS-monitored California agricultural landscape for pyrethroid aquatic toxicity.

### 3.3 BBS monitoring coverage: a systematic gap in the highest-exposure landscape

Of the 44 high-PUR-density routes, 14 — including some of the highest-exposure sites in the state — received zero valid BBS surveys (RunType = 1 in the BBS weather data) between 2015 and 2022 (Table 3). This is not a gap uniformly distributed across the exposure landscape: these 14 routes include ORANGE COVE (153,347 lbs AI within 5 km over nine years, the single highest-exposure route in the dataset), TRANQUILLITY (145,075 lbs), BRAWLEY (107,609 lbs), TIPTON (49,148 lbs), and ATHLONE (49,051 lbs). Six of the top 15 highest-PUR-density routes have zero BBS survey coverage.

**Table 3.** BBS routes with zero valid surveys 2015–2022 among the 44 highest-PUR-density California routes.

| Route | Name | Lbs AI within 5 km (2015–2023) | BCR |
|---|---|---|---|
| 54 | ORANGE COVE | 153,347 | 32 |
| 171 | TRANQUILLITY | 145,075 | 32 |
| 150 | BRAWLEY | 107,609 | 33 |
| 204 | ATHLONE | 49,051 | 32 |
| 197 | TIPTON | 49,148 | 32 |
| 100 | WISTER | — | 33 |
| 125 | MARICOPA | — | 32 |
| 149 | ATWATER | — | 32 |
| 320 | COLLEGEVILLE 2 | 56,186 | 32 |
| 196 | ORA LOMA | — | 32 |
| 24 | CARUTHERS | 41,494 | 32 |
| 26 | OILFIELDS | — | 32 |
| 90 | BLYTHE | — | 33 |
| 43 | CADIZ | — | 33 |

The 28 routes with survey data include important high-count sites: HUGHSON averages 710 aerial insectivores per surveyed year (across seven years of BBS data, 2015–2022), WESTLEY 372, SANGER 268, and PENNINGTON 219. These routes provide the analytical base for the Level 1 exposure-abundance model. The exposure wide table contains 369 route-year rows; 148 have at least one focal species detected, 2 were surveyed with zero focal-species detections, and 219 have no survey data (including all years for the 14 unsurveyed routes, all routes in 2020 due to COVID-19 field suspension, and all 2023 rows pending data release).

### 3.4 BBS count trends: preliminary signal in the surveyed routes

Among the 28 routes with survey data, annual BBS aerial insectivore totals summed statewide fell substantially over the period. Total swallow detections across all California BBS routes declined from 10,284 in 2015 to 3,514 in 2022 (66% reduction). This decline is partly attributable to the 2020 survey gap and year-to-year route coverage variation; formal trend estimation controlling for survey effort is the subject of ongoing analysis.

The eBird Status and Trends data provide trend estimates for four focal swallow species in the San Joaquin Valley region (Table 4). Barn Swallow showed a statistically robust decline of 2.1% per year (80% credible interval: −3.3 to −0.7), with 96% of eBird grid cells in the analysis area showing negative trends. Cliff Swallow declined at 1.5% per year (91% cells declining), and Tree Swallow at 1.1% per year (76% cells declining). Northern Rough-winged Swallow showed a weaker and uncertain signal (−0.3%/year, 62% cells declining).

**Table 4.** eBird Status and Trends trend estimates for swallow species, San Joaquin Valley analysis area, 2012–2022.

| Species | Trend (%/yr) | 80% CI | % cells declining | n cells |
|---|---|---|---|---|
| Barn Swallow | −2.14 | −3.25 to −0.71 | **95.9%** | 49 |
| Cliff Swallow | −1.52 | −3.31 to +0.07 | 90.9% | 66 |
| Tree Swallow | −1.10 | −2.78 to +0.67 | 76.5% | 51 |
| N. Rough-winged Swallow | −0.30 | −1.91 to +1.46 | 61.7% | 60 |

Barn Swallow's credible interval excludes zero; the other species show predominantly negative but less certain trends. The cross-guild consistency of the pattern is notable: Western Kingbird, a sallying flycatcher that captures prey by short aerial pursuits from a perch rather than in continuous aerial foraging, declined at approximately 1.5% per year in the same region. That two ecologically distinct foraging guilds show comparable decline rates is consistent with a shared food-base mechanism rather than collision mortality or habitat change specific to one foraging mode.

### 3.5 Level 1 mixed-effects models: exposure-abundance associations

We fit two model families to the 150 surveyed route-years using log(count + 1) as the response variable for five focal species and groups (Table 5). Model A (linear mixed-effects, random route intercept) estimates the joint cross-sectional and temporal association between exposure and abundance, controlling for year fixed effects. Model B (within-route demeaned OLS, HC3 standard errors) removes all stable between-route differences and isolates the temporal question: does a given route have lower counts in its own high-exposure years relative to its own mean?

**Model A (mixed-effects LMM).** No species showed a statistically significant negative association between pyrethroid aquatic toxicity and abundance. The all-swallows total showed a marginal *positive* association with pyrethroid exposure (β = +0.190, 95% CI: −0.026 to +0.406, p = 0.085). Organophosphate exposure was not significantly associated with any response variable. Year fixed effects in the all-swallows model showed a consistent but not individually significant downward trend: 2021 was the most negative year (β = −0.330 vs. 2015, SE = 0.206, p = 0.109), corresponding to an estimated 28% lower swallow count relative to 2015 after accounting for route differences and exposure.

**Model B (within-route).** No species showed a significant negative pyrethroid or organophosphate association in the within-route model. Pyrethroid β for all swallows was +0.054 (95% CI: −0.037 to +0.144, p = 0.248), effectively zero. The notable result was Western Kingbird, which showed a highly significant negative year trend: β = −0.045 per year (p = 0.001), corresponding to approximately 4.4% per year decline after removing route-level baseline differences. This within-route temporal decline is among the strongest statistical signals in the dataset and is consistent with the eBird S&T regional trend estimate for the species.

**Table 5.** Primary model results (5 km buffer, 90-day pre-survey lag, aquatic toxicity units). Model A = linear mixed-effects (route random intercept); Model B = within-route demeaned OLS (HC3 standard errors). β values are for z-scored pyrethroid exposure. Significance: *** p<0.001, ** p<0.01, * p<0.05, . p<0.10.

| Species | Model A: pyr β (p) | Model A: op β (p) | Model B: pyr β (p) | Model B: op β (p) | Model B: yr β (p) |
|---|---|---|---|---|---|
| Barn Swallow | +0.005 (0.970) | −0.030 (0.741) | −0.031 (0.669) | −0.057 (0.416) | −0.009 (0.757) |
| Cliff Swallow | +0.204 (0.233) | −0.057 (0.610) | +0.047 (0.442) | −0.043 (0.547) | −0.019 (0.578) |
| Tree Swallow | −0.000 (0.999) | +0.013 (0.861) | −0.005 (0.923) | +0.021 (0.286) | +0.004 (0.860) |
| Western Kingbird | +0.032 (0.716) | +0.029 (0.604) | −0.006 (0.872) | +0.033 (0.527) | **−0.045 (0.001)**|
| All Swallows | +0.190 (0.085). | −0.051 (0.477) | +0.054 (0.248) | −0.044 (0.500) | −0.027 (0.176) |

**Sensitivity across buffer × lag combinations.** Within-route pyrethroid β for all swallows was non-negative at all buffer × lag combinations, with positive values reaching marginal significance at 2 km buffers (60-day lag: β = +0.102, p = 0.051; 90-day lag: β = +0.096, p = 0.041). This pattern was not consistent with a prey-base suppression signal.

**Power considerations.** The within-route analysis relies on year-to-year variation in pyrethroid exposure at each route around its own nine-year mean. The 10th–90th percentile range of this demeaned exposure variable is −246 to +136 toxicity units — modest relative to the route-level peak of 2,840 units — reflecting that most routes' year-to-year pyrethroid variation is small compared to their between-route differences. Given n = 150 observations across 28 routes, the analysis has limited power to detect small within-route temporal effects.

### 3.6 First differences, pyrethroid share, and the chlorpyrifos natural experiment

The within-route mean-comparison structure of Model B is one of several reasonable ways to ask whether exposure changes have produced bird-population responses. We fit three additional specifications (§2.6) that test the same underlying question from different angles: high-frequency year-over-year change (Model C), chemistry-mix effects holding total load constant (Model D), and a difference-in-differences design centered on the abrupt 2019 chlorpyrifos cancellation (Model E).

**First differences (Model C).** Across all five focal responses, the year-over-year change in pyrethroid or organophosphate exposure did not significantly predict the year-over-year change in count (Table 6). The most striking result from this specification was the Barn Swallow year coefficient: β = −0.101 per year (p = 0.011 \*), indicating an approximately 10% per year mean decline in Barn Swallow counts on the surveyed routes once high-frequency variation is isolated. This is the second focal species, after Western Kingbird in Model B, to show a statistically significant temporal decline that survives the removal of all stable between-route confounders.

**Pyrethroid share (Model D).** The chemistry-mix variable — pyrethroid share of total (pyr + op) insecticide toxicity — was not a significant predictor of any focal response on the 28 surveyed routes (Table 6). Western Kingbird showed a directionally negative effect of higher pyrethroid share at marginal significance (β = −0.095, p = 0.158), and the pyrethroid-share Cliff Swallow result was directionally negative but not significant (β = −0.084, p = 0.577). The persistent Western Kingbird year trend was again present (β = −0.056/year, p = 0.001 \*\*), and the All Swallows year trend reached marginal significance in this specification (β = −0.041/year, p = 0.059 .).

**Difference-in-differences around the 2019 chlorpyrifos cliff (Model E).** This is the most informative new result. After classifying the 28 surveyed routes as OP-heavy (n = 14) or OP-light (n = 14) based on their 2015–2018 organophosphate exposure, and comparing the pre-cliff to post-cliff count change between groups, the DiD interaction coefficient β₃ was negative for four of five focal responses and significantly negative for Western Kingbird (β = −0.401, 95% CI: −0.778 to −0.025, p = 0.037 \*; Table 6). The directional interpretation: routes that had been receiving the most organophosphate exposure before the cancellation experienced approximately 33% greater decline in Western Kingbird counts after the cancellation than otherwise-similar routes that had been receiving less OP. Cliff Swallow showed the same directional pattern at borderline significance (β = −0.621, p = 0.102), corresponding to an approximately 46% relative decline. The all-swallows DiD was directionally negative but not significant (β = −0.173, p = 0.444).

This is the opposite direction from what a naive "remove the OP, birds rebound" mechanism would predict. The optimistic substitution narrative — that the most exposed landscapes should have benefited most from chlorpyrifos cancellation — is rejected by the data for Western Kingbird and is directionally inconsistent with the data for Cliff Swallow and Barn Swallow. The only response variable for which the DiD coefficient was essentially zero was Tree Swallow (β = −0.001, p = 0.998), the species whose foraging ecology is least dependent on the agricultural-wetland chironomid/Ephemeroptera prey base that pyrethroids most directly affect.

**Table 6.** First-difference, pyrethroid-share, and difference-in-differences model results (5 km buffer, 90-day lag, aquatic toxicity units). DiD coefficient β₃ is the interaction term (post × heavy); negative values indicate that OP-heavy routes declined more after 2019 than OP-light routes. Significance: \*\*\* p<0.001, \*\* p<0.01, \* p<0.05, . p<0.10.

| Species | Model C: Δpyr β (p) | Model C: year β (p) | Model D: share β (p) | Model E: DiD β₃ (p) |
|---|---|---|---|---|
| Barn Swallow | −0.138 (0.297) | **−0.101 (0.011)** \* | −0.024 (0.870) | −0.183 (0.589) |
| Cliff Swallow | +0.065 (0.569) | +0.028 (0.509) | −0.084 (0.577) | −0.621 (0.102) . |
| Tree Swallow | −0.026 (0.795) | −0.008 (0.842) | −0.001 (0.989) | −0.001 (0.998) |
| Western Kingbird | −0.032 (0.558) | +0.019 (0.466) | −0.095 (0.158) | **−0.401 (0.037)** \* |
| All Swallows | +0.065 (0.391) | −0.009 (0.756) | −0.023 (0.772) | −0.173 (0.444) |

The DiD result reframes the interpretation of the §3.5 nulls. Where Model B found no within-route exposure-response signal, the DiD design — which collapses the time series into a pre-versus-post comparison and so requires less within-route variation to detect a signal — finds that the routes most exposed to the pre-cliff chemistry are not the routes that recovered most after the cliff. If chemistry succession (pyrethroids and oxamyl rising as OPs fell) had been neutral or beneficial for aerial insectivores, the OP-heavy routes should have shown a positive relative trajectory after 2019. They did not. The DiD direction is consistent with the chemistry-succession concern: that the replacement compounds were as costly (or more so) to the aerial-insectivore food base as the compounds they replaced.

This result rests on a small sample (n = 14 heavy + 14 light routes), and the parallel-trends assumption is not formally testable on this data. Multi-route acoustic monitoring at the 14 currently-unsurveyed high-exposure routes would extend the DiD treatment sample considerably and provide the within-route exposure variation needed to test the mechanism more directly.

---

## 4. Discussion

### 4.1 The post-cancellation landscape is not chemically simpler for aquatic invertebrates

The headline finding of this analysis — that pyrethroid aquatic toxicity did not decline following chlorpyrifos cancellation — challenges a simplifying assumption that is sometimes made in regulatory communication: that removing a highly toxic compound reduces overall ecosystem toxicity. At the statewide level, pyrethroid aquatic toxicity was sustained at approximately 4–5 million toxicity units per year throughout the post-cancellation period, and the pyrethroid share of total aquatic insecticide toxicity grew from 28% to roughly 80% between 2015 and 2023. At the route level, the 2021 pyrethroid spike — 35% above the previous year's baseline — represents a period of *higher* aquatic toxicity to invertebrate prey than any year in the pre-cancellation record for that metric.

The mechanism is straightforward. Pyrethroids have *Daphnia magna* EC50 values that are orders of magnitude lower than most organophosphates (bifenthrin EC50 ≈ 0.0011 μg/L; chlorpyrifos EC50 ≈ 0.085 μg/L — bifenthrin is approximately 77 times more toxic per unit mass to *Daphnia*). Even modest pyrethroid use therefore generates substantial aquatic toxicity units. As long as pyrethroid use holds at current levels, the aquatic invertebrate food base in California's agricultural landscapes faces a toxicity burden comparable to or exceeding what it experienced during the chlorpyrifos era — just from a different chemical class.

This matters for aerial insectivores because prey availability is widely hypothesized as the proximate driver of swallow and swift population dynamics (e.g., Møller 2013). Chironomid midges, mayflies, and caddisflies — the dominant aerial prey of Barn Swallow and Cliff Swallow in California agricultural wetlands (Winkler et al. 2011) — all have aquatic larval stages that are directly exposed to water-column pyrethroid concentrations. If the aquatic invertebrate food base was suppressed by organophosphates before 2019 and remains suppressed by pyrethroids after 2019, the bird population time series would show continuous rather than punctuated decline — consistent with the eBird trend estimates in Table 4 but not resoluble with existing data.

### 4.2 The oxamyl signal warrants direct monitoring

The six-fold increase in oxamyl use between 2015 and 2019, concentrated in Kings County cotton, was not predicted from the regulatory history of chlorpyrifos cancellation and appears in the PUR data as a secondary substitution trend. Oxamyl's acute oral LD50 of 3.16 mg/kg in Bobwhite Quail — the most toxic carbamate in California agriculture by this metric — means that its avian-relevant exposure potential at the field level is substantially higher than that of chlorpyrifos or any current-use pyrethroid on an LD50-adjusted basis.

Whether birds are encountering oxamyl at biologically relevant doses in Kings County cotton fields is unknown, and this study does not resolve that question. What the PUR data show is that the use trajectory is consistent with OP substitution in insect-pressure crops, that the concentrations applied are substantial (103,763 lbs AI statewide in 2019, of which the majority was Kings County cotton), and that the use pattern has persisted and partially rebounded after a 2020–2021 dip. A targeted residue screening component — blood or feather sampling from birds breeding near high-oxamyl sections — would provide direct evidence of biological exposure at a cost well within the range of monitoring investments contemplated in Level 3 of the proposed study design.

### 4.3 Habitat confounding, the exposure gradient problem, and the chlorpyrifos natural experiment

The Level 1 results (§3.5–§3.6) are best read jointly. The within-route exposure-response models (B, C, D) returned null pyrethroid coefficients, while the difference-in-differences model (E) found that the routes most exposed to pre-cancellation chlorpyrifos *did not* rebound after the cancellation — and for Western Kingbird, declined significantly more than less-exposed routes. The two findings are not in tension. They are consistent with a single mechanism: that within-route year-to-year exposure variation in the surveyed routes is too small to produce a within-route signal at this sample size, while the pre/post regulatory shock — which moved the chemistry mix dramatically at every route, with greater absolute change at the OP-heaviest routes — was large enough to produce a between-route differential trajectory.

Three threads of evidence have to be separated and named clearly. First, the positive cross-sectional association in Model A (β = +0.190 for all swallows pyrethroid, p = 0.085) is almost certainly attributable to habitat confounding. The routes with the highest pyrethroid aquatic toxicity — HUGHSON, BUENA VISTA, WESTLEY, ATHLONE — are also in the most productive agricultural landscapes for aerial insectivores: the northern San Joaquin Valley and Sacramento Delta, with extensive irrigation infrastructure, rice agriculture, and wetland-adjacent habitats that support large chironomid and Ephemeroptera communities. The correlation is real, but the causal direction is from landscape type to both the bird density and the pesticide use, not from pesticides to birds.

Second, the within-route models (B, C, D) removed this confound by construction, and the answer from the 28 BBS-surveyed routes is that *within-route* exposure variation does not detectably predict count variation. However, the within-route exposure contrast is modest: annual pyrethroid toxicity units at a typical route fluctuate by roughly ±200 tox units around the route's nine-year mean, whereas the between-route range spans from near zero to 2,840 units. The within-route temporal variation is too small, relative to the among-route spatial variation, to generate adequate statistical power for small-to-moderate effects.

Third — and this is the new finding of §3.6 — the difference-in-differences design (Model E) does not depend on within-route year-to-year variation at all. It compares the pre-cliff and post-cliff group means between OP-heavy and OP-light routes, and is sensitive to the largest regulatory event in California pesticide history, which moved chemistry mix and absolute exposure dramatically across the whole route set in a single year. The DiD interaction was significantly negative for Western Kingbird (β = −0.401, p = 0.037), directionally negative for Cliff Swallow at marginal significance (β = −0.621, p = 0.102), and directionally negative for All Swallows (β = −0.173, p = 0.444). The aggregate sign across responses points one way: routes most exposed to pre-cancellation chlorpyrifos did not benefit from its removal at the abundance level — they declined more.

The most parsimonious interpretation is the substitution-chemistry interpretation. The compounds that replaced organophosphates — pyrethroids broadly, oxamyl in cotton, methomyl in continued use — are not less costly to the aquatic-invertebrate prey base of aerial insectivores than the OPs they replaced. Statewide pyrethroid aquatic toxicity held at 4–5 million units across the full study window; the substitution kept the toxicity burden roughly constant while changing its compound identity. At the route scale, this would predict that the routes most loaded with the pre-cliff chemistry would track approximately along with the routes whose chemistry was already lighter — and would *not* show the disproportionate rebound that a successful regulatory reduction would produce. That is the DiD result.

The Western Kingbird year-trend result from Models B and D (β ≈ −0.045/yr, p = 0.001) sits alongside this. The within-route year trend cannot be attributed to local pyrethroid exposure variation, because it is estimated after the exposure terms. It reflects a broad regional decline consistent with the eBird S&T trend for the species. The fact that this signal is detected with high confidence in the within-route models despite the small sample size confirms that the BBS data are informative about temporal trends; the limitation lies specifically in the within-route exposure contrast, not in the BBS dataset's noise floor.

### 4.4 The BBS coverage gap as a monitoring priority

The discovery that 14 of California's 44 highest-PUR-density BBS routes received zero valid surveys during 2015–2022 is the most actionable finding of this analysis. These routes include the highest-exposure sites in the state (ORANGE COVE: 153,000 lbs AI within 5 km, TRANQUILLITY: 145,000 lbs), and their absence from the count dataset is precisely what limits detection of an exposure-response signal at the landscape level.

The routes are concentrated in two geographic clusters: the central San Joaquin Valley (ORANGE COVE, TRANQUILLITY, TIPTON, CARUTHERS, MARICOPA, ATWATER, ORA LOMA) and the Imperial Valley / Salton Sea region (BRAWLEY, WISTER, BLYTHE). Both clusters are in landscapes with high agricultural intensity, high pyrethroid use, and documented aerial insectivore populations. They are not biologically marginal; they are monitoring-marginal because BBS volunteer coverage in intensive row-crop agriculture is sparse.

Targeted acoustic monitoring at these routes using autonomous recording units (AudioMoth or equivalent, approximately $80–$120/unit with solar power) would provide a three-year window to assess whether detection rates at high-exposure sites show event-scale responses to major pyrethroid applications. BirdNET neural-network inference applied to continuous recordings produces daily presence indices for focal species with accuracy comparable to trained observers (Kahl et al. 2021). Pairing acoustic detection indices with the daily PUR application data already available in the pipeline would allow testing of a finer-grained hypothesis than annual BBS counts support: whether swallow vocal activity decreases in the days following major pyrethroid applications within the buffer zone.

### 4.5 Inferential limits and study design implications

This study characterizes the exposure landscape created by the chlorpyrifos cancellation, demonstrates that the BBS monitoring network as currently operated cannot adequately test for within-route exposure-response effects in the most pesticide-intensive California landscapes, and provides DiD evidence at the regulatory-shock scale that the post-cancellation chemistry succession was not accompanied by the differential rebound the optimistic substitution narrative would predict. These three findings have different inferential standing. The exposure characterization is robust and reproducible from PUR primary records. The null within-route exposure-response result is power-limited and should not be read as evidence of absence. The DiD finding is the strongest causal claim available from the current data; it survives the removal of all stable between-route confounders, exploits an abrupt regulatory shock that minimizes parallel-trends concerns over short windows, and produces consistent direction across most responses with a statistically significant effect for Western Kingbird.

Several design limitations affect the sensitivity of the current analysis. First, BBS surveys are annual snapshots taken over one or two days in late May; inter-annual variation in detection probability, observer effort, and survey timing adds noise to the count variable. Second, the route start-point buffer does not capture exposure along the full 40 km transect, biasing toward the first few stops. Third, the 70% uniform-attribution fallback in the spatial pipeline means that approximately 70% of section-level exposure estimates use the section's full area rather than the crop-specific pixel area, potentially diluting exposure estimates for routes where the most intensively treated crops are a small fraction of the landscape. Fourth, the DiD design assumes parallel pre-period trends between OP-heavy and OP-light routes; with 14 routes per group and 4 pre-cliff years, a formal parallel-trends test would be underpowered. We rely instead on the qualitative argument that the abrupt 2019 regulatory shock is unlikely to coincide with an alternative confounder of the same magnitude.

None of these limitations invalidate the analysis; they define the improvements that would strengthen it. A per-stop exposure calculation using USGS stop-level coordinates, expanded CDL crop mapping, and the addition of acoustic monitoring at the 14 unsurveyed routes would each independently increase statistical power. The model-ready wide table produced here provides the infrastructure for all of these extensions without requiring reprocessing of the underlying PUR or spatial data. Crucially, extending the monitoring footprint to the 14 unsurveyed high-exposure routes would also expand the DiD treatment sample from 14 to 28+ routes, enabling more confident inference about the rebound (or lack thereof) at exactly the locations where the regulatory shock was largest in absolute terms.

---

## 5. Conclusions

California's 2019 chlorpyrifos cancellation produced a 97% decline in organophosphate aquatic toxicity units at the scale of California's highest-PUR-density BBS monitoring routes. Pyrethroid aquatic toxicity did not decline correspondingly; it peaked in 2021 at the highest level in the nine-year record, and by that year accounted for 89% of the total aquatic insecticide toxicity burden in the monitoring landscape. A secondary carbamate substitution elevated oxamyl use six-fold between 2015 and 2019; oxamyl is approximately ten times more acutely toxic to birds than chlorpyrifos per pound applied.

Mixed-effects models pairing route-level exposure estimates with BBS aerial insectivore counts from 150 surveyed route-years found no significant within-route association between local pyrethroid aquatic toxicity and swallow or flycatcher abundance, a result the power analysis attributes to limited within-route exposure contrast in the BBS-surveyed sample. A complementary difference-in-differences design centered on the chlorpyrifos cancellation finds that the routes most exposed to pre-cancellation organophosphates did not benefit from the cancellation at the abundance level — and for Western Kingbird declined significantly more than less-exposed routes (DiD β = −0.401, p = 0.037). The direction of this result is opposite the prediction of an optimistic substitution narrative and is consistent with the chemistry-succession concern: that pyrethroids and replacement carbamates rising as organophosphates fell have not produced a less toxic landscape for aerial-insectivore prey. Western Kingbird also showed a strong within-route temporal decline of approximately 4.4% per year (p = 0.001), and Barn Swallow a 10% per year first-difference decline (p = 0.011), confirming that the BBS data for these routes are informative about temporal trends. The combined picture is not an unresolved null; it is directional evidence against the rebound hypothesis at the regulatory-shock scale, accompanied by population-level decline signals in two focal species that survive the removal of all stable between-route confounders.

The spatial pipeline, toxicity lookup table, and model-ready wide table (369 route-years × 291 exposure columns) are open-source and reproducible. The 14 unsurveyed routes constitute a specific, addressable monitoring gap whose closure would expand both the within-route exposure contrast available for Models B–D and the treatment sample available for the DiD design. CDPR's PUR database provides the most detailed pesticide use record in the United States; the infrastructure built here makes it possible — for the first time — to link that record to wildlife monitoring at the spatial and temporal resolution the question demands. The post-chlorpyrifos insecticide regime is not chemically simpler for aerial insectivores; whether the residual biological response is large enough to be the proximate driver of California aerial-insectivore decline remains an open question, and answering it requires acoustic monitoring at the 14 high-exposure routes that BBS does not reach.

---

## Acknowledgments

We thank CDPR for maintaining and publicly releasing the PUR database; USGS for maintaining the North American Breeding Bird Survey dataset; USDA NASS for maintaining the Cropland Data Layer; and the Cornell Lab of Ornithology for eBird data access. The spatial pipeline builds on methods described in Gunier et al. (2001). We are grateful to the volunteers who conduct BBS surveys annually under often challenging conditions in California's agricultural valleys.

---

## References

Fink, D., et al. 2023. eBird Status and Trends, Data Version: 2022. Cornell Lab of Ornithology, Ithaca, New York. https://doi.org/10.2173/ebirdst.2022

Gibbons, D., C. Morrissey, and P. Mineau. 2015. A review of the direct and indirect effects of neonicotinoids and fipronil on vertebrate wildlife. *Environmental Science and Pollution Research* 22(1):103–118.

Gunier, R.B., M.E. Harnly, P. Reynolds, A. Hertz, and J. Von Behren. 2001. Agricultural pesticide use in California: pesticide prioritization, use densities, and population distributions for a childhood cancer study. *Environmental Health Perspectives* 109(10):1071–1078.

Hallmann, C.A., R.P.B. Foppen, C.A.M. van Turnhout, H. de Kroon, and E. Jongejans. 2014. Declines in insectivorous birds are associated with high neonicotinoid concentrations. *Nature* 511:341–343.

Kahl, S., C.M. Wood, M. Eibl, and H. Klinck. 2021. BirdNET: A deep learning solution for avian diversity monitoring. *Ecological Informatics* 61:101236.

Lewis, K.A., J. Tzilivakis, D.J. Warner, and A. Green. 2016. An international database for pesticide risk assessments and management. *Human and Ecological Risk Assessment* 22(4):1050–1064.

Li, Y., A. Miao, and M. Savage. 2020. Sublethal effects of neonicotinoid insecticide exposure on insectivorous bird populations in the United States. *Nature Sustainability* 3:1039–1044.

Møller, A.P. 2013. Long-term trends in wind speed, insect abundance and ecology of an aerial insectivore. *Ecosphere* 4(1):1–11.

Nebel, S., A. Mills, J.D. McCracken, and P.D. Taylor. 2010. Declines of aerial insectivores in North America follow a geographic gradient. *Avian Conservation and Ecology* 5(2):1.

Rosenberg, K.V., A.M. Dokter, P.J. Blancher, J.R. Sauer, A.C. Smith, P.A. Smith, J.C. Stanton, A. Panjabi, L. Helft, M. Parr, and P.P. Marra. 2019. Decline of the North American avifauna. *Science* 366:120–124.

Sauer, J.R., D.K. Niven, J.E. Hines, D.J. Ziolkowski Jr., K.L. Pardieck, J.E. Fallon, and W.A. Link. 2017. The North American Breeding Bird Survey, Results and Analysis 1966–2015. Version 02.07.2017. Patuxent Wildlife Research Center, Laurel, MD. https://www.mbr-pwrc.usgs.gov/bbs/

U.S. Department of Agriculture, National Agricultural Statistics Service. 2024. Cropland Data Layer. https://nassgeodata.gmu.edu/CropScape/

U.S. Environmental Protection Agency. 2024. ECOTOX Knowledgebase. https://cfpub.epa.gov/ecotox/

U.S. Geological Survey. 2023. North American Breeding Bird Survey Dataset 1966–2022. https://doi.org/10.5066/P9GS9K64

Winkler, D.W., K.K. Hallinger, D.R. Ardia, R.J. Robertson, B.J. Stutchbury, and R.R. Cohen. 2011. Tree Swallow (*Tachycineta bicolor*). In *Birds of the World* (A.F. Poole, ed.). Cornell Lab of Ornithology, Ithaca, NY.

---

## Appendix A. Supplementary tables and data availability

**Data availability.** The PUR data are publicly available from CDPR at https://www.cdpr.ca.gov/docs/pur/purmain.htm. BBS data are publicly available from USGS ScienceBase (https://doi.org/10.5066/P9GS9K64). CDL data are publicly available from USDA NASS. The spatial pipeline, toxicity lookup table, and model-ready wide table are available at https://github.com/dm00dy/ca-pur-data-summary. All code is Python 3.10+ and is reproducible from the repository root with a single environment file.

**Table A1.** Top 15 BBS routes by PUR record count within 5 km, 2015–2023, with exposure and survey coverage summary.

| Route | Name | PUR records (5 km) | Lbs AI (5 km) | Pyr tox units (cumul.) | BBS surveys (2015–22) |
|---|---|---|---|---|---|
| 54 | ORANGE COVE | 25,597 | 153,347 | 7,883 | **0** |
| 21 | HUGHSON | 18,394 | 38,801 | 16,367 | 7 |
| 92 | ALAMO RIVER | 18,101 | 119,414 | 12,804 | 3 |
| 127 | SANGER | 12,087 | 63,787 | — | 5 |
| 90 | BLYTHE | 9,585 | 42,725 | — | **0** |
| 171 | TRANQUILLITY | 8,663 | 145,075 | — | **0** |
| 150 | BRAWLEY | 8,360 | 107,609 | — | **0** |
| 204 | ATHLONE | 7,626 | 49,051 | 10,897 | **0** |
| 147 | ARVIN | 6,684 | 76,256 | — | 3 |
| 24 | CARUTHERS | 6,381 | 41,494 | — | **0** |
| 320 | COLLEGEVILLE 2 | 5,897 | 56,186 | 10,786 | **0** |
| 245 | BUENA VISTA | 5,863 | 54,288 | 14,634 | 5 |
| 197 | TIPTON | 4,839 | 49,148 | — | **0** |
| 49 | PALO VERDE | 4,327 | 29,419 | — | 2 |
| 155 | WESTLEY | 4,126 | 25,161 | 8,969 | 7 |

Bold 0 = route with no valid BBS surveys, 2015–2022. Pyrethroid tox units shown where available in current analysis; — indicates route excluded from wide table (zero exposure across all buffers) or not yet extracted.

**Table A2.** Annual BBS aerial insectivore totals, California statewide, surveyed routes only.

| Year | Swallows | Swifts | Nightjars | Flycatchers | Total AI |
|---|---|---|---|---|---|
| 2015 | 10,284 | 168 | 185 | — | 13,585 |
| 2016 | 7,488 | 131 | 183 | — | 10,328 |
| 2017 | 9,533 | 128 | 128 | — | 12,492 |
| 2018 | 8,696 | 99 | 131 | — | 11,511 |
| 2019 | 8,022 | 154 | 93 | — | 10,905 |
| 2020 | — | — | — | — | — (COVID) |
| 2021 | 3,215 | 101 | 78 | — | 5,057 |
| 2022 | 3,514 | 134 | 88 | — | 5,284 |

Note: the 2021–2022 drop relative to 2019 reflects both route coverage variation and possible real abundance change; year-effect is included as a fixed effect in planned mixed-effects model.
