# Pesticide Regime Shifts and Aerial Insectivore Response in California Agriculture: A Hierarchical Monitoring Proposal

**Doug Moody & Dennis Jongsomjit — Point Blue Conservation Science**

*Submitted to CDPR Ecosystem Monitoring Program — May 2026*

---

## The Opportunity

California's 2019 chlorpyrifos cancellation is one of the largest single regulatory events in North American pesticide history. At its peak, chlorpyrifos accounted for more than half of California's agricultural insecticide use by weight. Its removal did not simply reduce the state's pesticide load — it restructured it. Growers substituted across chemical classes, and the substitution pattern varied by crop, county, and target pest. Nine years later, the toxicological footprint of California agriculture looks fundamentally different from what it did in 2015, in ways that matter differently for birds, for invertebrates, and for the ecosystems that connect them.

CDPR collects the data to characterize this change at unprecedented spatial and temporal resolution. The Pesticide Use Report (PUR) database records every agricultural application in California at the section level — roughly 1 square mile — with the crop, the compound, the quantity, and the date. No other state has anything like it. What California has lacked until now is a framework that connects those application records to the wildlife monitoring programs that could detect a biological response.

This proposal builds that framework and uses it to address a specific question: **has the post-chlorpyrifos shift in California's agricultural insecticide load produced a detectable response in aerial insectivore bird populations?**

---

## What the PUR Data Reveals

We analyzed CDPR PUR records for 2015–2023 across all California agricultural counties, processing 5,065,221 section-tagged application records for 44 insecticide active ingredients. Two findings stand out.

**The organophosphate collapse is complete.** Statewide organophosphate use — dominated by chlorpyrifos — fell 97% between 2015 and 2019, concentrated almost entirely in a single growing season. At the level of individual Breeding Bird Survey routes in the San Joaquin and Sacramento valleys, organophosphate aquatic toxicity units dropped from 85,000 in 2015 to 2,800 in 2023 — the same 97% decline, confirming that the statewide pattern is reproduced at the scale of individual monitoring sites.

**Pyrethroids did not decline proportionally.** Pyrethroid use in absolute pounds declined modestly, but pyrethroids' much higher aquatic toxicity per pound meant their compositional share of the toxicity load grew dramatically. By 2021, pyrethroids accounted for 89% of aquatic invertebrate toxicity units at the route level — up from 17% in 2015. The 2021 total represents the single highest pyrethroid aquatic toxicity load in the nine-year record: 23,345 toxicity units summed across 44 monitoring routes, a 35% spike above the 2020 baseline. The aquatic invertebrate food base that aerial insectivores depend on encountered a qualitatively different pesticide environment after 2019 — not a cleaner one.

A secondary substitution is also visible in the carbamate class. Oxamyl — registered for cotton, potatoes, and cucurbits — increased approximately five-fold statewide between 2016 and 2019 (18,000 to 88,000 lbs AI), concentrated in Kings County cotton. Oxamyl's acute oral LD50 in Bobwhite Quail is 3.16 mg/kg, placing it in EPA's "extremely toxic" category and making it approximately ten times more acutely dangerous to birds per pound than the chlorpyrifos it appears to be replacing in some operations. Whether birds are encountering oxamyl at biologically significant doses is unknown, but the use pattern is consistent with OP substitution and warrants monitoring.

**A third substitution operates within the OP class itself.** While chlorpyrifos collapsed (1.1 million lbs statewide in 2015 to 39 lbs in 2023), the broader organophosphate class declined more modestly, to approximately 30% of its 2015 lbs total. The residual is dominated by three compounds — naled, malathion, and dimethoate — and is concentrated in the same Kings County cotton landscape where the oxamyl signal appears. In 2023, Kings County applied 149,496 lbs of organophosphates, 73% on cotton and 90% applied aerially. Naled (avian acute oral LD50 52 mg/kg) and dimethoate (LD50 41 mg/kg) both classify as "highly toxic to birds" under EPA criteria; on the avian endpoint, the residual OP load remained substantial even as chlorpyrifos disappeared. The OP exposure footprint did not vanish — its center of mass shifted to a smaller set of cotton-dominant landscapes and, on the avian endpoint, persisted.

**These residual OP applications sit adjacent to the southern San Joaquin Valley refuge complex.** The highest 2023 OP application sections in Kings County lie within 15 km of five managed protected areas: Pixley NWR (10 km), Tulare Basin Wildlife Management Area (12 km), Kern NWR (13 km), Allensworth Ecological Reserve (13 km), and Semitropic Ecological Reserve (15 km). These units support wintering waterfowl, sandhill cranes, white-faced ibis, and federally listed endemic species (Tipton kangaroo rat, blunt-nosed leopard lizard). Aerial-applied OPs have documented drift footprints exceeding 10 km. The aerial insectivore prey-base mechanism that motivates the broader proposal applies in this landscape; a second mechanism — direct avian toxicity from cotton OP drift onto refuges immediately downwind of intensive aerial application — operates here as well and warrants integrated monitoring.

---

## What the Bird Data Reveals — and Where It Goes Silent

eBird Status and Trends trend estimates (2012–2022) show that five of seven aerial insectivore species breeding in the San Joaquin Valley declined at 1–2% per year over the trend period. Barn Swallow (−2.1%/yr), Cliff Swallow (−1.5%/yr), and Western Kingbird (−1.5%/yr) show the strongest signals. Notably, Western Kingbird captures prey by sallying from a perch — a fundamentally different foraging mode from the in-flight pursuit used by swallows. That both guilds show similar decline rates in the same landscape points toward a shared food-base effect rather than a behavior-specific cause such as collision mortality or microhabitat change.

These are regional trends modeled from eBird data at ~27 km grid cell resolution. They describe direction and rate but not mechanism, and they cannot be linked to specific pesticide applications. The Sacramento Valley, a landscape with lower pyrethroid intensity, shows declines of comparable magnitude (Cliff Swallow −2.4%/yr, Barn Swallow −1.7%/yr), which complicates attribution to local chemistry and argues for direct, location-matched monitoring.

To build the bridge between application records and bird populations, we developed a spatial pipeline that links PUR section-level applications to Breeding Bird Survey route locations using PLSS section polygons, USDA Cropland Data Layer crop maps, and compound-specific toxicity values sourced from the Hertfordshire Pesticide Properties DataBase. The result is a year-by-year exposure profile — at four buffer distances and three lag windows, for eight chemical classes — for each BBS route in California's agricultural landscape. This pipeline, now fully operational, is the Level 1 infrastructure for this study.

Applied to the 44 BBS routes with the highest surrounding PUR density, the pipeline produced a model-ready table of 369 route-year exposure records (2015–2023), joined to annual BBS aerial insectivore count data. The initial Level 1 analysis will test whether route-level pyrethroid aquatic toxicity load in the 90 days before each BBS survey is associated with annual counts of swallows, swifts, and nightjars at that route.

**But the pipeline produced an unexpected finding that shapes the rest of this proposal.**

When we joined the exposure table to BBS survey records, we found that 14 of the 44 highest-PUR-density routes in California — including ORANGE COVE (153,000 lbs AI within 5 km over nine years), TRANQUILLITY (145,000 lbs), BRAWLEY (108,000 lbs), and TIPTON (49,000 lbs) — received **zero valid BBS surveys between 2015 and 2022**. These are not marginal routes: they include the single highest-PUR-density BBS route in the state and six of the top fifteen. They are concentrated in the San Joaquin Valley and Imperial Valley — the core of California's agricultural pesticide use.

The BBS monitoring network, designed for continent-scale population status assessment, does not cover the most pesticide-intensive landscapes in California. The 28 routes that do have survey data include strong candidates for the Level 1 analysis — HUGHSON averages 710 aerial insectivores per survey year across seven years of data, WESTLEY averages 372, SANGER 268 — but the highest-exposure routes are a biological blind spot.

This is not a flaw in the design of this study. It is the argument for it.

---

## The Proposed Study

We propose a three-level hierarchical design that (1) extracts the available signal from existing BBS data, (2) extends acoustic monitoring into the unsurveyed high-exposure routes, and (3) closes the causal chain with targeted biological sampling.

### Level 1: Route-level exposure-abundance modeling (BBS + PUR)

Using the completed exposure pipeline, we will fit mixed-effects models relating annual aerial insectivore abundance at 28 California BBS routes to route-level pesticide exposure over 2015–2022. Primary response variables are annual BBS counts for Barn Swallow, Cliff Swallow, Tree Swallow, and Western Kingbird — four species with sufficient detection rates and ecological rationale for a prey-base pathway. Primary exposure predictors are pyrethroid and organophosphate aquatic toxicity units within 5 km of the route start point in the 90-day pre-survey window. Route identity enters as a random effect; year as a fixed effect to capture the OP collapse.

The 90-day lag is ecologically motivated: it spans the window from first spring arrival through the BBS survey date, covering the period during which prey-base suppression would affect breeding condition, foraging success, and detectable abundance. The 30- and 60-day lags are available for sensitivity testing.

The Level 1 analysis will produce the first route-level, PUR-matched exposure-abundance test for California aerial insectivores. If a relationship exists at this scale, its form and magnitude will inform the spatial design of Levels 2 and 3.

### Level 2: Acoustic monitoring in unsurveyed high-exposure routes (AudioMoth + BirdNET)

Fourteen high-exposure routes — selected specifically because they lack BBS coverage — will receive a three-year deployment of autonomous recording units (AudioMoths, ~$80/unit, solar-powered). Sites will be paired where possible: one high-exposure route and one reference route within the same Bird Conservation Region but with lower surrounding pyrethroid load.

**The Tulare basin cotton-refuge cluster identified in the PUR analysis warrants dedicated treatment within this design.** TIPTON — one of the 14 unsurveyed high-exposure BBS routes already targeted for AudioMoth deployment — is the highest-priority anchor for this landscape: it lies within the residual-OP cotton belt and within 30 km of Pixley NWR, Kern NWR, and the Allensworth and Semitropic ecological reserves. We will augment the TIPTON route deployment with two refuge-interior AudioMoth stations, one each on Pixley NWR and Kern NWR (with refuge manager coordination). This pairing yields a within-landscape contrast — refuge-interior vs. ag-perimeter aerial insectivore vocal activity — with cotton OP application events as the time-varying exposure. Both refuges support Tree, Cliff, and Barn Swallow populations using refuge water bodies for foraging, making them ecologically appropriate prey-base reference sites; if aerial OP applications drive a detectable difference in swallow detection between refuge-interior and ag-perimeter stations, the dual-mechanism framing (prey-base depression + direct drift exposure) is supported. Two refuge-interior stations add approximately 15% to the proposed 14-route hardware cost while leveraging existing USFWS field infrastructure and refuge bird survey programs for site access, data backup, and biological context.

BirdNET neural network inference will be applied to all recordings to generate daily detection indices for focal species. Detection timing will be related to PUR application records for the surrounding sections, testing whether vocal activity decreases in the days following major pyrethroid applications. This tests a finer-grained hypothesis than Level 1: not just whether exposure predicts abundance, but whether application events predict behavioral response. For the TIPTON–Pixley–Kern triangle, the analogous test extends to organophosphate application events: do aerial naled, malathion, or dimethoate applications on the surrounding cotton drive detectable short-term shifts in swallow vocal activity at refuge-interior stations relative to upwind reference stations?

Bank Swallow (California Threatened) and Lesser Nighthawk — both regionally present and both lacking sufficient eBird S&T coverage for trend analysis — are priority targets for acoustic monitoring at several of the unsurveyed routes.

### Level 3: Mist-netting and residue analysis

At a subset of the acoustic monitoring sites, targeted mist-netting during peak breeding season will provide blood and feather samples for pesticide residue screening. Residue data serve two purposes. First, they confirm biological exposure: detection of pyrethroid metabolites in birds breeding near high-application sections would close the inference gap between application records and tissue burden. Second, body condition measurements (fat score, mass, wing measurement) allow testing of whether birds at high-exposure sites show physiological stress indicators independent of count-based abundance metrics.

Mist-netting sites will be selected from the Level 2 acoustic stations based on detection rates — sites with sufficient captures to make tissue sampling efficient. Sampling will be coordinated with CDPR permit requirements and will follow USFWS banding protocols.

**The TIPTON–Pixley–Kern triangle established at Level 2 carries forward as the priority residue-sampling landscape.** Refuge-interior captures at Pixley NWR and Kern NWR are particularly informative because they decompose the application-to-tissue inference chain into testable steps: if swallows foraging on insects emerging from refuge water bodies carry detectable cotton-OP metabolites, that evidence links aerial application on adjacent cotton through drift, deposition, and aquatic-prey uptake to bird tissue burden — the full mechanism captured in a single landscape. Residue screening at this triangle will accordingly target a dual panel: pyrethroid metabolites (3-phenoxybenzoic acid as the standard cross-pyrethroid marker) plus OP-specific oxon metabolites — dichlorvos (from naled), malaoxon (from malathion), and omethoate (from dimethoate). An acetylcholinesterase inhibition assay on plasma provides a class-wide functional biomarker for cumulative OP and carbamate exposure independent of which specific compound is implicated, and is the appropriate readout if oxon metabolites have already cleared by the time of capture. The refuge-interior vs. ag-perimeter pairing established by the Level 2 station design carries through to Level 3 as a paired-sample contrast at the tissue level — refuge-interior captures are the lower-exposure reference, ag-perimeter captures the higher-exposure treatment, with the same surrounding cotton OP application record as the predictor.

---

## Why This Study, Why Now

Three things have converged to make this proposal timely.

**The natural experiment is aging.** The chlorpyrifos cancellation took effect in 2019-2020. Population-level effects of a major pesticide shift, mediated through prey-base disruption, would be expected to manifest over 3–7 years as recruitment cohorts under the new exposure regime enter the breeding population. If a signal exists in the BBS data, the 2022–2026 window is when it would become detectable above the noise floor. Waiting diminishes statistical power.

**The exposure data exists and is already structured.** The Level 1 pipeline is not a proposal — it is done. The 5-million-record PUR database has been processed, section-keyed, toxicity-weighted, and joined to BBS route locations. The model input table exists. Level 1 analysis can begin immediately upon funding.

**The monitoring gap is specific and fillable.** The 14 unsurveyed high-exposure routes are not scattered randomly across the state; they cluster in the San Joaquin Valley and Imperial Valley in a pattern that reflects the BBS network's sparse coverage of intensive row-crop agriculture. A targeted 14-route AudioMoth deployment at $80/unit is among the most cost-effective monitoring investments available for addressing this gap.

CDPR's Ecosystem Monitoring program is positioned to answer the question that no other California monitoring program is currently designed to address: what biological effects, if any, has the post-chlorpyrifos pesticide regime produced in the non-target wildlife that depends on California's agricultural insect communities? The PUR database is the most detailed pesticide use record in the world. The missing piece is a biological monitoring design that uses that record's spatial and temporal resolution. This proposal provides it.

---

## Team and Data Access

**Doug Moody** (Point Blue Conservation Science) leads PUR data infrastructure, spatial pipeline development, and Level 1 modeling. The pipeline described here was built for this proposal and is available for CDPR review.

**Dennis Jongsomjit** (Point Blue Conservation Science) leads field design, BBS route coordination, and Level 2/3 biological monitoring. Dennis has extensive experience with AudioMoth deployment and BirdNET analysis in California agricultural landscapes.

PUR data are publicly available from CDPR. BBS data are publicly available from USGS ScienceBase. CDL data are publicly available from USDA NASS. No data acquisition costs are anticipated for Levels 1 or 2 beyond AudioMoth hardware.

---

## Expected Deliverables

| Level | Timeline | Deliverable |
|---|---|---|
| 1 | Year 1 | Route-level exposure-abundance model results; published or submitted manuscript |
| 1 | Year 1 | Reproducible PUR spatial pipeline, open-source on GitHub, usable by CDPR for future monitoring analyses |
| 2 | Years 1–3 | Annual acoustic monitoring reports for 14 high-exposure routes; detection index time series |
| 2 | Year 3 | Analysis of application-event acoustic response; manuscript |
| 3 | Years 2–3 | Residue screening results for focal species at paired high/low-exposure sites |
| 3 | Year 3 | Integrated synthesis: PUR exposure → acoustic detection → tissue burden |

The spatial pipeline and model inputs will be delivered to CDPR regardless of biological outcome. Even if no population-level signal is detected, the infrastructure for linking CDPR's application records to wildlife monitoring will exist and will be available for future studies, future chemistries, and future regulatory events.

---

## References

California Department of Pesticide Regulation. 2024. Pesticide Use Reporting (PUR) database. https://www.cdpr.ca.gov/docs/pur/purmain.htm

Fink, D., et al. 2023. eBird Status and Trends, Data Version: 2022. Cornell Lab of Ornithology. https://doi.org/10.2173/ebirdst.2022

Gunier, R.B., et al. 2001. Agricultural pesticide use in California: pesticide prioritization, use densities, and population distributions for a childhood cancer study. *Environmental Health Perspectives* 109(10):1071–1078.

Lewis, K.A., et al. 2016. An international database for pesticide risk assessments and management. *Human and Ecological Risk Assessment* 22(4):1050–1064. [Hertfordshire PPDB]

Li, Y., et al. 2020. Sublethal effects of neonicotinoid insecticide exposure on insectivorous bird populations in the United States. *Nature Sustainability* 3:1039–1044.

Nebel, S., et al. 2010. Declines of aerial insectivores in North America follow a geographic gradient. *Avian Conservation and Ecology* 5(2):1.

Rosenberg, K.V., et al. 2019. Decline of the North American avifauna. *Science* 366:120–124.

Sauer, J.R., et al. 2017. The North American Breeding Bird Survey, Results and Analysis 1966–2015. Patuxent Wildlife Research Center, Laurel, MD.

U.S. Geological Survey. 2023. North American Breeding Bird Survey Dataset 1966–2022. https://doi.org/10.5066/P9GS9K64
