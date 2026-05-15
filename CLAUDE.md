# CLAUDE.md — PUR Analysis

## Status: toxicity sourcing complete

All 44 chemicals sourced from Hertfordshire PPDB (primary) and EPA ECOTOX
(cross-check). Illustrative warning blocks removed. Script and CSV committed
to https://github.com/dm00dy/ca-pur-data-summary.

## Background context

This script supports a grant proposal to CDPR (California Department of
Pesticide Regulation) for their Ecosystem Monitoring program. The proposal
is collaborative with Dennis Jongsomjit and uses a hierarchical Level 1/
2/3 design (landscape SDMs, AudioMoth + BirdNET acoustic monitoring,
mist-netting + residue analysis). The toxicity-weighted outputs from this
script support the Level 1 exposure characterization.

The scientific question that toxicity weighting serves: aerial insectivores
(birds and bats) are most likely affected by pesticides through prey-base
disruption rather than direct mortality. Many of their prey (chironomids,
mayflies, caddisflies) have aquatic larval stages, so aquatic invertebrate
toxicity is the more mechanism-relevant endpoint. Avian toxicity is included
as a direct-mortality comparison.

## Key findings (confirmed under properly-sourced values)

**Headline (aquatic toxicity, CA agricultural insecticides):**
- Pyrethroids: 28% of aquatic toxicity load in 2015 → 77% in 2023
- This matches the prior illustrative estimate (26%) — story is robust to sourcing
- Pyrethroid use rebounded ~20% in lbs (2019→2023) even as overall use declined
- Organophosphate cliff visible 2018–2021 (chlorpyrifos phase-out)

**Carbamate avian signal (new finding from proper sourcing):**
- Carbaryl's old illustrative LD50 (56 mg/kg) was masking the signal
- Properly sourced carbaryl LD50 = 2000 mg/kg (effectively non-toxic to birds)
- Oxamyl (LD50 3.16 mg/kg, extremely toxic) now drives the entire carbamate
  avian pattern — use increased ~6× from 2016 to 2019
- Timing is consistent with OP substitution: as chlorpyrifos was phased out
  2019–2021, growers switched to alternative chemistries including oxamyl

**Possible next step:**
- Crop/county breakdown for oxamyl to test the OP substitution hypothesis:
  are oxamyl increases concentrated in the same crops and counties that saw
  chlorpyrifos declines? Uses the PUR data's crop_code and county_cd fields.

## Toxicity data approach

- **Primary source:** Hertfordshire PPDB (`https://sitem.herts.ac.uk/aeru/ppdb/en/Reports/{ID}.htm`)
- **Cross-check:** EPA ECOTOX (`https://cfpub.epa.gov/ecotox/`)
- **Avian endpoint:** acute oral LD50 (mg/kg), 14-day mortality; Bobwhite preferred,
  mallard acceptable surrogate
- **Aquatic endpoint:** *Daphnia magna* 48h EC50 (μg/L) — called "LC50 immobility" in PPDB
- **Ceiling values** (">N"): stored as N (conservative floor); tracked with boolean
  `avian_ceiling`/`aquatic_ceiling` columns in the CSV

**Notable sourcing flags (see `toxicity_lookup.csv` notes column):**
- thiacloprid: no PPDB oral LD50; used APVMA secondary source (2716 mg/kg Bobwhite)
- tetraniliprole: no avian data found; used class estimate
- tralomethrin: L3 source; pheasant family surrogate
- tau-fluvalinate: 3-source conflict in aquatic values; documented in notes
- spinosad: sourced from BPDB (biopesticides database), not PPDB

## Files in this directory

- `pur_analyze.py` — main analysis script (renamed from `pur_substitution_analysis.py`)
- `toxicity_lookup.csv` — toxicity reference values with full sourcing; 44 chemicals,
  schema: `chemname,class,avian_ld50_mg_per_kg,avian_ceiling,avian_test_species,
  avian_source_url,aquatic_lc50_ug_per_l,aquatic_ceiling,aquatic_test_species,
  aquatic_source_url,notes`
- `pur_analysis/cache/pur{YEAR}.zip` — cached PUR archives, ~3 GB total.
  Don't delete unless re-downloading.
- `pur_analysis/chemical_lookup.csv` — auto-generated; chem_code → class mapping
- `pur_analysis/pur_yearly_*.csv` — auto-generated outputs (includes
  `pur_yearly_carbamate_by_chem.csv` for per-chemical carbamate detail)
- `pur_analysis/pur_chart_*.png` — auto-generated charts (includes carbamate detail charts)

## Running the script

```bash
source .venv/bin/activate
python pur_analyze.py
```

Cached zips are reused; fresh runs take roughly 5–10 minutes for the per-
county UDC streaming. If you want to force a re-download, delete
`pur_analysis/cache/`.

## What NOT to change

- The lbs and acres calculations. These are sourced directly from CDPR PUR
  and are already publication-ready.
- The chemical class definitions. These are conventional and shouldn't
  drift from what's already in `CHEMICAL_CLASSES`.
- The chart structure. The legend/annotation layout was specifically tuned
  for proposal-quality output.
- The ag/non-ag site filter. The `site_code < 65000` heuristic is rough
  but adequate; refining it is a separate piece of work.

## CSV loader note

`toxicity_lookup.csv` notes column contains unquoted commas. The script
reads it by column index (not `pd.read_csv`) — columns 0–9 are comma-free,
column 10+ is notes. Don't add commas to columns 0–9 when editing the CSV.
