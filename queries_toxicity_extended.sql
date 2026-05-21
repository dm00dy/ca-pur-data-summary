-- ============================================================================
-- Example queries: bee, chironomid, and avian NOEC endpoints
-- Database: pur_data  (MySQL 8, port 3366)
-- Units:
--   bee_contact_ld50 / bee_oral_ld50  μg/bee  (lower = more toxic)
--   chironomid_ec50                   μg/L    (lower = more toxic)
--   aquatic_lc50 (Daphnia)            μg/L    (lower = more toxic)
--   avian_noec_repro                  mg/kg bw/day (lower = more sensitive)
--   avian_ld50                        mg/kg   (lower = more toxic)
--   lbs_chm_used                      lbs active ingredient
-- Tox units = lbs / endpoint_value  (higher = more toxic load)
-- ============================================================================


-- ── 1. REFERENCE: all endpoints side-by-side ─────────────────────────────────
-- Quick sanity check / scorecard across all four endpoints.
SELECT
    chemname,
    chem_class,
    ROUND(avian_ld50,        2)  AS avian_ld50_mg_kg,
    ROUND(aquatic_lc50,      3)  AS daphnia_ec50_ugl,
    ROUND(bee_contact_ld50,  4)  AS bee_contact_ug,
    ROUND(bee_oral_ld50,     4)  AS bee_oral_ug,
    ROUND(chironomid_ec50,   3)  AS chironomid_ugl,
    chironomid_endpoint,
    ROUND(avian_noec_repro,  3)  AS avian_noec_bwday
FROM toxicity
ORDER BY chem_class, chemname;


-- ── 2. BEE TOXICITY LOAD BY YEAR ─────────────────────────────────────────────
-- Pounds applied weighted by bee contact LD50 → comparable to avian/aquatic
-- tox units. Higher = more bee-toxic load on the landscape.
-- Uses ONLY real measurements (excludes ceiling values for conservative
-- accounting; swap the WHERE to include ceilings for upper-bound estimate).
SELECT
    r.year,
    t.chem_class,
    ROUND(SUM(r.lbs_chm_used) / 1e6,      2)  AS m_lbs_ai,
    ROUND(SUM(r.lbs_chm_used / t.bee_contact_ld50) / 1e6, 1)
                                               AS bee_tox_units_M
FROM pur_record r
JOIN chemical   c ON c.chem_code = r.chem_code
JOIN toxicity   t ON LOWER(c.chemname) = LOWER(t.chemname)
WHERE r.site_code < 65000          -- agricultural use only
  AND t.bee_contact_ld50 IS NOT NULL
  AND t.bee_contact_ceiling = 0    -- exclude ceiling values
  AND r.lbs_chm_used > 0
GROUP BY r.year, t.chem_class
ORDER BY r.year, bee_tox_units_M DESC;


-- ── 3. CHIRONOMID vs DAPHNIA: hidden pyrethroid risk ─────────────────────────
-- The "pyrethroid problem" in the Daphnia endpoint vs sediment-dwelling midges.
-- Ratio > 1 means chironomids are more sensitive than Daphnia for that compound.
-- Pyrethroids bind to sediment; Chironomus larvae live IN sediment → bigger gap.
SELECT
    chemname,
    chem_class,
    ROUND(aquatic_lc50,    3)  AS daphnia_ec50_ugl,
    ROUND(chironomid_ec50, 3)  AS chironomid_ugl,
    chironomid_endpoint,
    ROUND(aquatic_lc50 / chironomid_ec50, 1)  AS daphnia_chiro_ratio
    -- ratio > 1: chironomid more sensitive (Daphnia understates risk)
    -- ratio < 1: Daphnia more sensitive
FROM toxicity
WHERE chironomid_ec50 IS NOT NULL
  AND aquatic_lc50    IS NOT NULL
ORDER BY daphnia_chiro_ratio DESC;


-- ── 4. CHIRONOMID TOX UNITS BY CLASS AND YEAR (ag only) ─────────────────────
-- Same structure as the existing aquatic tox units but using chironomid LC50.
-- Expected result: pyrethroids will rank even higher here than in the Daphnia
-- analysis because they are sediment-active.
SELECT
    r.year,
    t.chem_class,
    ROUND(SUM(r.lbs_chm_used / t.chironomid_ec50) / 1e6, 2)
                            AS chironomid_tox_units_M,
    ROUND(SUM(r.lbs_chm_used / t.aquatic_lc50)    / 1e6, 2)
                            AS daphnia_tox_units_M,
    ROUND(
        SUM(r.lbs_chm_used / t.chironomid_ec50) /
        NULLIF(SUM(r.lbs_chm_used / t.aquatic_lc50), 0),
        1
    )                       AS chiro_vs_daphnia_ratio
FROM pur_record r
JOIN chemical   c ON c.chem_code = r.chem_code
JOIN toxicity   t ON LOWER(c.chemname) = LOWER(t.chemname)
WHERE r.site_code < 65000
  AND t.chironomid_ec50  IS NOT NULL AND t.chironomid_ceiling = 0
  AND t.aquatic_lc50     IS NOT NULL AND t.aquatic_ceiling    = 0
  AND r.lbs_chm_used > 0
GROUP BY r.year, t.chem_class
ORDER BY r.year, chironomid_tox_units_M DESC;


-- ── 5. AVIAN NOEC: chronic vs acute sensitivity gap ─────────────────────────
-- Which compounds have the biggest gap between acute lethality and sublethal
-- chronic effects? Large ratio = chronic effects occur at much lower doses than
-- acute kills → most relevant for reproductive failure in breeding birds.
-- NOEC is in mg/kg bw/day; LD50 is in mg/kg. Not directly comparable but
-- the ratio is a useful relative-sensitivity indicator within a compound.
SELECT
    chemname,
    chem_class,
    ROUND(avian_ld50,       2)  AS acute_ld50_mg_kg,
    avian_test_species,
    ROUND(avian_noec_repro, 3)  AS chronic_noec_bwday,
    avian_noec_test_species,
    ROUND(avian_ld50 / avian_noec_repro, 0)  AS acute_chronic_ratio
    -- higher ratio = larger gap between acute kill and chronic effect threshold
FROM toxicity
WHERE avian_ld50       IS NOT NULL
  AND avian_noec_repro IS NOT NULL
ORDER BY acute_chronic_ratio DESC;


-- ── 6. AVIAN NOEC TOX UNITS BY YEAR (ag only) ────────────────────────────────
-- Chronic reproductive risk weighted by pounds applied.
-- lbs / (noec mg/kg bw/day) is not standard but useful for relative ranking.
SELECT
    r.year,
    t.chem_class,
    ROUND(SUM(r.lbs_chm_used),                              0)  AS lbs_ai,
    ROUND(SUM(r.lbs_chm_used / t.avian_noec_repro) / 1e6,  3)
                                                                AS noec_tox_units_M
FROM pur_record r
JOIN chemical   c ON c.chem_code = r.chem_code
JOIN toxicity   t ON LOWER(c.chemname) = LOWER(t.chemname)
WHERE r.site_code < 65000
  AND t.avian_noec_repro IS NOT NULL
  AND t.avian_noec_ceiling = 0
  AND r.lbs_chm_used > 0
GROUP BY r.year, t.chem_class
ORDER BY r.year, noec_tox_units_M DESC;


-- ── 7. NEONIC BEE ORAL TOXICITY: THE REGISTRATION-REVIEW SIGNAL ──────────────
-- Neonics are systemic — bees ingest them through nectar/pollen, making oral
-- LD50 the mechanistically relevant endpoint.  Shows why they were restricted.
SELECT
    chemname,
    chem_class,
    ROUND(bee_oral_ld50, 6)     AS bee_oral_ug_per_bee,
    bee_oral_ceiling,
    ROUND(bee_contact_ld50, 4)  AS bee_contact_ug_per_bee,
    -- For comparison: a typical bee weighs ~0.1 g. A 0.004 μg oral LD50
    -- means <0.00004 mg/g body weight — orders of magnitude below mammalian
    -- toxicity thresholds, and achievable from residues in a single flower visit.
    ROUND(0.004 / bee_oral_ld50, 0)  AS x_more_toxic_than_clothianidin
FROM toxicity
WHERE chem_class IN ('Restricted neonics', 'Other neonics', 'Next-gen systemics')
  AND bee_oral_ld50 IS NOT NULL
ORDER BY bee_oral_ld50 ASC;


-- ── 8. SPINOSAD: biopesticide bee-toxicity check ─────────────────────────────
-- Spinosad is OMRI-listed (organic) but acutely toxic to bees during
-- application.  Dried residues are much less toxic (not captured here).
SELECT
    chemname, chem_class,
    ROUND(bee_contact_ld50, 4)    AS bee_contact_ug,
    ROUND(bee_oral_ld50,    4)    AS bee_oral_ug,
    ROUND(chironomid_ec50,  2)    AS chironomid_ugl,
    ROUND(aquatic_lc50,     2)    AS daphnia_ugl,
    ROUND(avian_ld50,       0)    AS avian_ld50,
    ROUND(avian_noec_repro, 1)    AS avian_noec
FROM toxicity
WHERE chemname IN ('spinosad','spinetoram');


-- ── 9. FULL MULTI-ENDPOINT SCORECARD BY CLASS (2023, ag only) ────────────────
-- Annual snapshot of ALL tox-unit dimensions in one query.
-- Use WHERE r.year = X to compare any year; compare 2015 vs 2023 for trend.
SELECT
    t.chem_class,
    ROUND(SUM(r.lbs_chm_used) / 1e6, 1)                             AS m_lbs,
    -- avian acute
    ROUND(SUM(r.lbs_chm_used / NULLIF(t.avian_ld50,       0)) / 1e6, 2)
                                                                     AS avian_tu_M,
    -- Daphnia (aquatic)
    ROUND(SUM(r.lbs_chm_used / NULLIF(t.aquatic_lc50,     0)) / 1e6, 2)
                                                                     AS daphnia_tu_M,
    -- bee contact
    ROUND(SUM(r.lbs_chm_used / NULLIF(t.bee_contact_ld50, 0)) / 1e6, 2)
                                                                     AS bee_tu_M,
    -- chironomid
    ROUND(SUM(r.lbs_chm_used / NULLIF(t.chironomid_ec50,  0)) / 1e6, 2)
                                                                     AS chiro_tu_M,
    -- avian chronic NOEC
    ROUND(SUM(r.lbs_chm_used / NULLIF(t.avian_noec_repro, 0)) / 1e6, 2)
                                                                     AS avian_noec_tu_M
FROM pur_record r
JOIN chemical   c ON c.chem_code = r.chem_code
JOIN toxicity   t ON LOWER(c.chemname) = LOWER(t.chemname)
WHERE r.site_code  < 65000
  AND r.year        = 2023
  AND r.lbs_chm_used > 0
GROUP BY t.chem_class
ORDER BY avian_tu_M DESC;


-- ── 10. CHLORPYRIFOS SUBSTITUTION: did replacement OPs/carbamates trade      ──
--         avian acute risk for chronic reproductive risk?                        ──
-- Compare chlorpyrifos (banned 2020) vs its likely substitutes.
-- Look at avian_ld50 (acute) vs avian_noec_repro (chronic).
SELECT
    chemname, chem_class,
    ROUND(avian_ld50,       1)  AS avian_ld50_mg_kg,
    ROUND(avian_noec_repro, 2)  AS avian_noec_bwday,
    ROUND(avian_ld50 / avian_noec_repro, 0)  AS acute_chronic_ratio,
    -- Tox units per 1M lbs applied — scale to compare substitutes at equal use
    ROUND(1e6 / avian_ld50,       0)          AS acute_tu_per_Mlb,
    ROUND(1e6 / avian_noec_repro, 0)          AS noec_tu_per_Mlb
FROM toxicity
WHERE chemname IN (
    'chlorpyrifos',           -- the banned OP
    'malathion',              -- OP alternative
    'dimethoate',             -- OP alternative
    'oxamyl',                 -- carbamate alternative (6× rise 2016-2019)
    'methomyl',               -- carbamate alternative
    'chlorantraniliprole',    -- diamide (low acute avian risk)
    'cyantraniliprole'        -- diamide
)
ORDER BY avian_noec_bwday ASC;


-- ── 11. SECTION-LEVEL QUERY: bee + chironomid exposure at a PLSS section ──────
-- For a given COMTRS (township-range-section), what was the bee and chironomid
-- tox-unit load in a given year?  Useful for BBS route exposure analysis.
-- Replace '20S016E01' with any valid COMTRS code.
SELECT
    r.comtrs,
    r.year,
    t.chem_class,
    c.chemname,
    ROUND(r.lbs_chm_used, 2)                            AS lbs,
    ROUND(r.lbs_chm_used / t.bee_contact_ld50,    2)    AS bee_tu,
    ROUND(r.lbs_chm_used / t.chironomid_ec50,     2)    AS chiro_tu,
    ROUND(r.lbs_chm_used / t.aquatic_lc50,        2)    AS daphnia_tu,
    ROUND(r.lbs_chm_used / t.avian_noec_repro,    2)    AS avian_noec_tu
FROM pur_record r
JOIN chemical c ON c.chem_code = r.chem_code
JOIN toxicity t ON LOWER(c.chemname) = LOWER(t.chemname)
WHERE r.comtrs     = '20S016E01'   -- substitute your target section
  AND r.year       = 2022
  AND r.lbs_chm_used > 0
ORDER BY bee_tu DESC NULLS LAST;


-- ── 12. DATA-GAP AUDIT ───────────────────────────────────────────────────────
-- Shows which chemicals are missing which endpoints — useful for knowing where
-- to prioritize additional literature searching before publication.
SELECT
    chemname,
    chem_class,
    IF(bee_contact_ld50  IS NOT NULL, 'Y', '--') AS bee_c,
    IF(bee_oral_ld50     IS NOT NULL, 'Y', '--') AS bee_o,
    IF(chironomid_ec50   IS NOT NULL, 'Y', '--') AS chiro,
    IF(avian_noec_repro  IS NOT NULL, 'Y', '--') AS avian_noec,
    IF(avian_ld50        IS NOT NULL, 'Y', '--') AS avian_acute,
    IF(aquatic_lc50      IS NOT NULL, 'Y', '--') AS daphnia
FROM toxicity
ORDER BY (bee_contact_ld50 IS NULL) + (bee_oral_ld50 IS NULL)
        + (chironomid_ec50 IS NULL) + (avian_noec_repro IS NULL) DESC,
         chem_class, chemname;
