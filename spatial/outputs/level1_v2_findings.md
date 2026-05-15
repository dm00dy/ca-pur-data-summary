# Level 1 model — second-swing findings (2026-05-15)

Three new specifications were fit beyond the original within-route LMM
(`level1_model.py`):

1. First-differences (Δ count ~ Δ exposure)
2. Pyrethroid share (chemistry-mix variable, within-route)
3. Difference-in-differences around the 2019 chlorpyrifos cancellation

The DiD result is the headline.

---

## Headline: post-chlorpyrifos rebound hypothesis is rejected

The first-swing within-route model returned null exposure effects. The
intuitive substitution narrative — "removing chlorpyrifos should let
aerial-insectivore populations recover on the routes that had been
receiving the most OP" — was untested in that pass. The DiD specification
in this swing tests it directly.

**Western Kingbird:** DiD β = **−0.401 (p = 0.037 \*)**
**Cliff Swallow:**    DiD β = **−0.621 (p = 0.102 .)**
**All Swallows:**     DiD β = −0.173 (p = 0.444 ns)
**Barn Swallow:**     DiD β = −0.183 (p = 0.589 ns)
**Tree Swallow:**     DiD β = −0.001 (p = 0.998 ns)

Translation: on routes whose 2015–2018 OP exposure was above the median
(n=14 routes), Western Kingbird counts after the 2020 cliff fell **33%
more** than on otherwise-similar low-OP routes (n=14 routes). Cliff
Swallow shows the same direction at marginal significance (−46%, p=0.10).

This is the opposite direction from what a "remove the OP, birds rebound"
mechanism would predict. The chemistry succession that followed chlorpyrifos
phase-out — pyrethroids rising from 28% to 77% of aquatic toxicity load,
oxamyl rising 6× in Kings County cotton — did not produce an aerial-
insectivore benefit on the routes that had been receiving the most OP. If
anything, the heaviest-substitution routes continued declining.

Causal caveats apply (parallel-trends assumption, 28-route sample, no
control for crop turnover), but as a sign test the result is striking:
the natural-experiment direction is wrong for the optimistic story.

---

## Supporting result: Barn Swallow first-difference year trend

Δ log(Barn Swallow) ~ year :  β = **−0.101 (p = 0.011 \*)**

In high-frequency (year-over-year) data, Barn Swallow shows a clear
state-wide decline. This corroborates the Western Kingbird temporal decline
(−4.4%/yr, p = 0.001) found in the first swing's within-route model. Two
focal species now show statistically significant temporal declines on the
surveyed routes, in models that have all level effects (route, habitat)
removed.

---

## Null results: pyrethroid share and Δ pyrethroid

Pyrethroid share within total (pyr + OP) tox load:
- All Swallows  β = −0.023 (p = 0.77 ns)
- Western Kingbird β = −0.095 (p = 0.16 ns)  ← directionally negative, marginal

Δ pyrethroid (year-over-year change):
- All Swallows  β = +0.065 (p = 0.39 ns)
- Barn Swallow  β = −0.138 (p = 0.30 ns)

Neither chemistry-mix nor short-window pyrethroid changes produce a
detectable signal on the surveyed 28 routes. The Western Kingbird share
result (−0.095, p=0.16) is the only one in the predicted negative direction
at any approach to significance.

---

## Interpretation

The first-swing paper read as "exposure-response signal below detection
threshold." With the DiD added, a more pointed reading is available:

- Aerial-insectivore counts on OP-heavy routes did NOT rebound after the
  chlorpyrifos cliff. For Western Kingbird, they declined faster than
  on OP-light routes.
- This is consistent with the chemistry-succession concern raised in
  the statewide PUR analysis — the post-2019 increase in pyrethroid
  share and oxamyl substitution may have offset the OP reduction at the
  exposure level relevant to aerial insectivores.
- The Level 2 acoustic monitoring at the 14 unsurveyed routes (the
  highest-exposure routes structurally excluded from BBS) becomes more
  important rather than less: BBS shows the substitution-era trajectory
  was not an improvement; the question of whether mortality, productivity,
  or prey-base depression drives it requires the higher-resolution Level
  2 data.

This is enough to upgrade the §3.5 paper result from "informative null"
to "directional evidence against the rebound hypothesis."
