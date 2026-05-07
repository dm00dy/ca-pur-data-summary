# California PUR Insecticide Use Analysis

A Python script for downloading and aggregating California Department of Pesticide Regulation (CDPR) Pesticide Use Report (PUR) data to characterize agricultural insecticide use patterns over time, with optional toxicity weighting for ecological risk assessment.

This tool was built to support a grant proposal investigating wildlife response to California's recent reductions in agricultural insecticide use, but it's general enough to be useful for anyone working with PUR data who wants annual statewide aggregations by chemical class.

## What it does

Given a range of years, the script:

1. Downloads CDPR's annual PUR archives from the public FTP and caches them locally.
2. Streams the per-county Use Data Chemical (UDC) files, filtering to a configurable set of chemical classes.
3. Aggregates application records by year and chemical class.
4. Produces summary CSVs and stacked-area charts for four metrics:
   - Pounds of active ingredient applied
   - Acres treated
   - Avian-LD50-weighted toxicity units (illustrative — see caveats)
   - Daphnia-LC50-weighted toxicity units (illustrative — see caveats)

The four metrics tell meaningfully different stories. Total California agricultural insecticide use dropped 41% by pounds and 70% by aquatic toxicity between 2015 and 2023, but only 12% by acres treated — the same landscape footprint is being treated with newer, lower-rate-per-acre chemistries.

## Why four metrics matter

For ecological risk questions, no single metric is sufficient:

- **Pounds applied** is the headline number most commonly reported, but reductions in pounds can reflect a shift to more potent chemistries rather than reduced ecological pressure.
- **Acres treated** tracks landscape footprint independent of application rate, which is often a better proxy for how much of the agricultural matrix is exposed.
- **Avian toxicity** weights chemicals by direct bird mortality risk (relevant for granivores, raptors, and incidental exposure routes).
- **Aquatic invertebrate toxicity** weights chemicals by impact on aquatic insect larvae — the better proxy for prey-base disruption affecting aerial insectivores like swallows, swifts, flycatchers, and bats.

Pyrethroids in particular show 4–6 orders of magnitude difference between avian and aquatic endpoints, so the choice of toxicity reference materially affects which class looks most concerning.

## Important caveat: toxicity values are illustrative

The avian LD50 and aquatic LC50 reference tables in the script are **illustrative defaults suitable only for internal exploratory analysis**. They are not properly sourced from EPA ECOTOX, Hertfordshire PPDB, or any other documented database. Do not use the toxicity-weighted outputs in publications, grant proposals, or agency reports without first replacing the reference tables with documented values.

The pounds and acres outputs are sourced directly from CDPR PUR and are publication-suitable with appropriate caveats about data resolution and the difference between application records and environmental exposure.

See the comment blocks at the top of `pur_substitution_analysis.py` for the full disclaimer and what proper sourcing requires.

## Installation

Requires Python 3.9+ and ~3 GB of disk space for the cached PUR archives.

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
python3 -m venv .venv
source .venv/bin/activate
pip install pandas requests matplotlib
```

If you're on a system with PEP 668 protection (modern Ubuntu, macOS with Homebrew Python), the venv is required. `uv` works equally well if you prefer it.

## Usage

```bash
python pur_substitution_analysis.py
```

The script downloads data on first run and caches it. Subsequent runs reuse the cache. To force a re-download, delete the `pur_analysis/cache/` directory.

Configuration options at the top of the script:

- `YEARS` — list of years to process. Defaults to 2015–2023. Add years as CDPR publishes them (typically a 12–18 month lag from the end of a calendar year).
- `AG_ONLY` — restrict to agricultural records using a `site_code < 65000` heuristic. Defaults to `True`.
- `TOXICITY_WEIGHTING` — toggle the toxicity-weighted outputs. Defaults to `True`.
- `CHEMICAL_CLASSES` — chemical class definitions. Edit freely to add or reorganize chemicals.

## Outputs

Written to `./pur_analysis/`:

- `chemical_lookup.csv` — resolved chem_code → class mapping, including any LD50 values
- `pur_yearly_lbs_by_class.csv` — long-format summary, pounds applied
- `pur_yearly_acres_by_class.csv` — long-format summary, acres treated
- `pur_yearly_tox_avian_by_class.csv` — long-format summary, avian-toxicity-weighted
- `pur_yearly_tox_aquatic_by_class.csv` — long-format summary, aquatic-toxicity-weighted
- `pur_chart_lbs.png` — stacked area chart, pounds
- `pur_chart_acres.png` — stacked area chart, acres
- `pur_chart_toxicity_avian.png` — stacked area chart, avian-weighted
- `pur_chart_toxicity_aquatic.png` — stacked area chart, aquatic-weighted

Each chart has two panels: absolute values on top, proportional composition (% of total) on the bottom, with a vertical line marking California's 2020 neonicotinoid restrictions.

## Data source

Annual PUR archives from CDPR:
`https://files.cdpr.ca.gov/pub/outgoing/pur_archives/pur{YEAR}.zip`

Each archive contains chemical, product, and site lookup tables plus per-county Use Data Chemical (UDC) files with application-level records dating back to 1990 for agricultural use.

CDPR publishes a new year roughly 12–18 months after that year ends, with periodic refreshes for late corrections.

## Performance notes

- Each annual PUR archive is 150–260 MB compressed.
- Processing nine years (2015–2023) takes 5–15 minutes on a modern laptop.
- Memory footprint stays under 1 GB through chunked streaming reads.
- Cached zips persist across runs; aggregation is the dominant cost on repeat runs.

## What this tool does NOT do

This is a statewide-aggregation tool, not a spatial analysis pipeline. It does not:

- Compute per-location or per-buffer exposure metrics
- Refine within-section attribution using crop maps (CropScape, DWR Land Use Survey)
- Model pesticide drift, runoff, or surface water transport
- Translate application records into environmental concentration estimates

A separate spatial pipeline that does these things is needed for site-specific exposure work.

## License

MIT License — see `LICENSE` for full terms.

## Acknowledgments

PUR data published by the California Department of Pesticide Regulation. The within-section attribution methodology referenced in the comments is based on Gunier et al. (2001), *Agriculture, Ecosystems & Environment* 86:171–184.
