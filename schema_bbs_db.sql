-- North American Breeding Bird Survey (BBS) — full database schema
-- Source: USGS ScienceBase 2024 edition
-- Loader: load_bbs_db.py
--
-- Table load order:
--   species, route → weather → vehicle → count → stop_count → migrant

CREATE DATABASE IF NOT EXISTS bbs
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE bbs;

-- ── Reference tables ──────────────────────────────────────────────────────────

-- BBS species list (SpeciesList.csv)
CREATE TABLE IF NOT EXISTS species (
    aou              SMALLINT UNSIGNED NOT NULL,
    seq              SMALLINT UNSIGNED,
    english_name     VARCHAR(120)      NOT NULL,
    french_name      VARCHAR(120),
    `order`          VARCHAR(60),
    family           VARCHAR(60),
    genus            VARCHAR(60),
    species_epithet  VARCHAR(60),
    PRIMARY KEY (aou),
    INDEX idx_spp_family (family)
);

-- BBS routes (Routes.csv) — all countries/states
CREATE TABLE IF NOT EXISTS route (
    country_num           SMALLINT UNSIGNED NOT NULL,
    state_num             SMALLINT UNSIGNED NOT NULL,
    route                 SMALLINT UNSIGNED NOT NULL,
    route_name            VARCHAR(100),
    active                TINYINT(1),
    latitude              DOUBLE,
    longitude             DOUBLE,
    stratum               SMALLINT UNSIGNED,
    bcr                   TINYINT UNSIGNED,
    route_type_id         TINYINT UNSIGNED,
    route_type_detail_id  TINYINT UNSIGNED,
    PRIMARY KEY (country_num, state_num, route),
    INDEX idx_route_bcr    (bcr),
    INDEX idx_route_active (active)
);

-- ── Survey metadata ───────────────────────────────────────────────────────────

-- One row per survey run (Weather.csv)
-- run_type = 1 means valid survey (filter for analysis)
CREATE TABLE IF NOT EXISTS weather (
    route_data_id      INT UNSIGNED      NOT NULL,
    country_num        SMALLINT UNSIGNED NOT NULL,
    state_num          SMALLINT UNSIGNED NOT NULL,
    route              SMALLINT UNSIGNED NOT NULL,
    rpid               SMALLINT UNSIGNED NOT NULL,
    year               SMALLINT UNSIGNED NOT NULL,
    month              TINYINT UNSIGNED,
    day                TINYINT UNSIGNED,
    obs_n              INT UNSIGNED,
    total_spp          SMALLINT UNSIGNED,
    start_temp         SMALLINT,
    end_temp           SMALLINT,
    temp_scale         CHAR(1),
    start_wind         TINYINT,
    end_wind           TINYINT,
    start_sky          TINYINT,
    end_sky            TINYINT,
    start_time         SMALLINT UNSIGNED,
    end_time           SMALLINT UNSIGNED,
    assistant          TINYINT(1),
    quality_current_id TINYINT UNSIGNED,
    run_type           TINYINT UNSIGNED,
    PRIMARY KEY (route_data_id),
    INDEX idx_wx_route (country_num, state_num, route),
    INDEX idx_wx_year  (year),
    INDEX idx_wx_run   (run_type)
);

-- Traffic and background noise counts per stop (VehicleData.csv)
CREATE TABLE IF NOT EXISTS vehicle (
    route_data_id  INT UNSIGNED      NOT NULL,
    country_num    SMALLINT UNSIGNED NOT NULL,
    state_num      SMALLINT UNSIGNED NOT NULL,
    route          SMALLINT UNSIGNED NOT NULL,
    rpid           SMALLINT UNSIGNED NOT NULL,
    year           SMALLINT UNSIGNED NOT NULL,
    recorded_car   FLOAT,
    car1  SMALLINT UNSIGNED, car2  SMALLINT UNSIGNED, car3  SMALLINT UNSIGNED,
    car4  SMALLINT UNSIGNED, car5  SMALLINT UNSIGNED, car6  SMALLINT UNSIGNED,
    car7  SMALLINT UNSIGNED, car8  SMALLINT UNSIGNED, car9  SMALLINT UNSIGNED,
    car10 SMALLINT UNSIGNED, car11 SMALLINT UNSIGNED, car12 SMALLINT UNSIGNED,
    car13 SMALLINT UNSIGNED, car14 SMALLINT UNSIGNED, car15 SMALLINT UNSIGNED,
    car16 SMALLINT UNSIGNED, car17 SMALLINT UNSIGNED, car18 SMALLINT UNSIGNED,
    car19 SMALLINT UNSIGNED, car20 SMALLINT UNSIGNED, car21 SMALLINT UNSIGNED,
    car22 SMALLINT UNSIGNED, car23 SMALLINT UNSIGNED, car24 SMALLINT UNSIGNED,
    car25 SMALLINT UNSIGNED, car26 SMALLINT UNSIGNED, car27 SMALLINT UNSIGNED,
    car28 SMALLINT UNSIGNED, car29 SMALLINT UNSIGNED, car30 SMALLINT UNSIGNED,
    car31 SMALLINT UNSIGNED, car32 SMALLINT UNSIGNED, car33 SMALLINT UNSIGNED,
    car34 SMALLINT UNSIGNED, car35 SMALLINT UNSIGNED, car36 SMALLINT UNSIGNED,
    car37 SMALLINT UNSIGNED, car38 SMALLINT UNSIGNED, car39 SMALLINT UNSIGNED,
    car40 SMALLINT UNSIGNED, car41 SMALLINT UNSIGNED, car42 SMALLINT UNSIGNED,
    car43 SMALLINT UNSIGNED, car44 SMALLINT UNSIGNED, car45 SMALLINT UNSIGNED,
    car46 SMALLINT UNSIGNED, car47 SMALLINT UNSIGNED, car48 SMALLINT UNSIGNED,
    car49 SMALLINT UNSIGNED, car50 SMALLINT UNSIGNED,
    noise1  SMALLINT UNSIGNED, noise2  SMALLINT UNSIGNED, noise3  SMALLINT UNSIGNED,
    noise4  SMALLINT UNSIGNED, noise5  SMALLINT UNSIGNED, noise6  SMALLINT UNSIGNED,
    noise7  SMALLINT UNSIGNED, noise8  SMALLINT UNSIGNED, noise9  SMALLINT UNSIGNED,
    noise10 SMALLINT UNSIGNED, noise11 SMALLINT UNSIGNED, noise12 SMALLINT UNSIGNED,
    noise13 SMALLINT UNSIGNED, noise14 SMALLINT UNSIGNED, noise15 SMALLINT UNSIGNED,
    noise16 SMALLINT UNSIGNED, noise17 SMALLINT UNSIGNED, noise18 SMALLINT UNSIGNED,
    noise19 SMALLINT UNSIGNED, noise20 SMALLINT UNSIGNED, noise21 SMALLINT UNSIGNED,
    noise22 SMALLINT UNSIGNED, noise23 SMALLINT UNSIGNED, noise24 SMALLINT UNSIGNED,
    noise25 SMALLINT UNSIGNED, noise26 SMALLINT UNSIGNED, noise27 SMALLINT UNSIGNED,
    noise28 SMALLINT UNSIGNED, noise29 SMALLINT UNSIGNED, noise30 SMALLINT UNSIGNED,
    noise31 SMALLINT UNSIGNED, noise32 SMALLINT UNSIGNED, noise33 SMALLINT UNSIGNED,
    noise34 SMALLINT UNSIGNED, noise35 SMALLINT UNSIGNED, noise36 SMALLINT UNSIGNED,
    noise37 SMALLINT UNSIGNED, noise38 SMALLINT UNSIGNED, noise39 SMALLINT UNSIGNED,
    noise40 SMALLINT UNSIGNED, noise41 SMALLINT UNSIGNED, noise42 SMALLINT UNSIGNED,
    noise43 SMALLINT UNSIGNED, noise44 SMALLINT UNSIGNED, noise45 SMALLINT UNSIGNED,
    noise46 SMALLINT UNSIGNED, noise47 SMALLINT UNSIGNED, noise48 SMALLINT UNSIGNED,
    noise49 SMALLINT UNSIGNED, noise50 SMALLINT UNSIGNED,
    PRIMARY KEY (route_data_id),
    INDEX idx_veh_year (year)
);

-- ── Count tables ──────────────────────────────────────────────────────────────

-- Route-level species counts (States.zip — one CSV per state/province)
-- Count10/20/30/40/50 are decade subtotals (stops 1-10, 11-20, ..., 41-50)
-- SpeciesTotal = sum across all 50 stops
CREATE TABLE IF NOT EXISTS `count` (
    route_data_id  INT UNSIGNED      NOT NULL,
    country_num    SMALLINT UNSIGNED NOT NULL,
    state_num      SMALLINT UNSIGNED NOT NULL,
    route          SMALLINT UNSIGNED NOT NULL,
    rpid           SMALLINT UNSIGNED NOT NULL,
    year           SMALLINT UNSIGNED NOT NULL,
    aou            SMALLINT UNSIGNED NOT NULL,
    count10        SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    count20        SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    count30        SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    count40        SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    count50        SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    stop_total     SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    species_total  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (route_data_id, aou),
    INDEX idx_cnt_aou   (aou),
    INDEX idx_cnt_year  (year),
    INDEX idx_cnt_route (country_num, state_num, route)
);

-- Per-stop species counts (50-StopData.zip — 10 part files)
CREATE TABLE IF NOT EXISTS stop_count (
    route_data_id  INT UNSIGNED      NOT NULL,
    country_num    SMALLINT UNSIGNED NOT NULL,
    state_num      SMALLINT UNSIGNED NOT NULL,
    route          SMALLINT UNSIGNED NOT NULL,
    rpid           SMALLINT UNSIGNED NOT NULL,
    year           SMALLINT UNSIGNED NOT NULL,
    aou            SMALLINT UNSIGNED NOT NULL,
    stop1  SMALLINT UNSIGNED, stop2  SMALLINT UNSIGNED, stop3  SMALLINT UNSIGNED,
    stop4  SMALLINT UNSIGNED, stop5  SMALLINT UNSIGNED, stop6  SMALLINT UNSIGNED,
    stop7  SMALLINT UNSIGNED, stop8  SMALLINT UNSIGNED, stop9  SMALLINT UNSIGNED,
    stop10 SMALLINT UNSIGNED, stop11 SMALLINT UNSIGNED, stop12 SMALLINT UNSIGNED,
    stop13 SMALLINT UNSIGNED, stop14 SMALLINT UNSIGNED, stop15 SMALLINT UNSIGNED,
    stop16 SMALLINT UNSIGNED, stop17 SMALLINT UNSIGNED, stop18 SMALLINT UNSIGNED,
    stop19 SMALLINT UNSIGNED, stop20 SMALLINT UNSIGNED, stop21 SMALLINT UNSIGNED,
    stop22 SMALLINT UNSIGNED, stop23 SMALLINT UNSIGNED, stop24 SMALLINT UNSIGNED,
    stop25 SMALLINT UNSIGNED, stop26 SMALLINT UNSIGNED, stop27 SMALLINT UNSIGNED,
    stop28 SMALLINT UNSIGNED, stop29 SMALLINT UNSIGNED, stop30 SMALLINT UNSIGNED,
    stop31 SMALLINT UNSIGNED, stop32 SMALLINT UNSIGNED, stop33 SMALLINT UNSIGNED,
    stop34 SMALLINT UNSIGNED, stop35 SMALLINT UNSIGNED, stop36 SMALLINT UNSIGNED,
    stop37 SMALLINT UNSIGNED, stop38 SMALLINT UNSIGNED, stop39 SMALLINT UNSIGNED,
    stop40 SMALLINT UNSIGNED, stop41 SMALLINT UNSIGNED, stop42 SMALLINT UNSIGNED,
    stop43 SMALLINT UNSIGNED, stop44 SMALLINT UNSIGNED, stop45 SMALLINT UNSIGNED,
    stop46 SMALLINT UNSIGNED, stop47 SMALLINT UNSIGNED, stop48 SMALLINT UNSIGNED,
    stop49 SMALLINT UNSIGNED, stop50 SMALLINT UNSIGNED,
    PRIMARY KEY (route_data_id, aou),
    INDEX idx_stop_aou   (aou),
    INDEX idx_stop_year  (year),
    INDEX idx_stop_route (country_num, state_num, route)
);

-- Migrant and non-breeder stop-level data (MigrantNonBreeder.zip/Migrants.csv)
-- Same structure as stop_count but for species recorded outside breeding context
CREATE TABLE IF NOT EXISTS migrant (
    route_data_id  INT UNSIGNED      NOT NULL,
    country_num    SMALLINT UNSIGNED NOT NULL,
    state_num      SMALLINT UNSIGNED NOT NULL,
    route          SMALLINT UNSIGNED NOT NULL,
    rpid           SMALLINT UNSIGNED NOT NULL,
    year           SMALLINT UNSIGNED NOT NULL,
    aou            SMALLINT UNSIGNED NOT NULL,
    stop1  SMALLINT UNSIGNED, stop2  SMALLINT UNSIGNED, stop3  SMALLINT UNSIGNED,
    stop4  SMALLINT UNSIGNED, stop5  SMALLINT UNSIGNED, stop6  SMALLINT UNSIGNED,
    stop7  SMALLINT UNSIGNED, stop8  SMALLINT UNSIGNED, stop9  SMALLINT UNSIGNED,
    stop10 SMALLINT UNSIGNED, stop11 SMALLINT UNSIGNED, stop12 SMALLINT UNSIGNED,
    stop13 SMALLINT UNSIGNED, stop14 SMALLINT UNSIGNED, stop15 SMALLINT UNSIGNED,
    stop16 SMALLINT UNSIGNED, stop17 SMALLINT UNSIGNED, stop18 SMALLINT UNSIGNED,
    stop19 SMALLINT UNSIGNED, stop20 SMALLINT UNSIGNED, stop21 SMALLINT UNSIGNED,
    stop22 SMALLINT UNSIGNED, stop23 SMALLINT UNSIGNED, stop24 SMALLINT UNSIGNED,
    stop25 SMALLINT UNSIGNED, stop26 SMALLINT UNSIGNED, stop27 SMALLINT UNSIGNED,
    stop28 SMALLINT UNSIGNED, stop29 SMALLINT UNSIGNED, stop30 SMALLINT UNSIGNED,
    stop31 SMALLINT UNSIGNED, stop32 SMALLINT UNSIGNED, stop33 SMALLINT UNSIGNED,
    stop34 SMALLINT UNSIGNED, stop35 SMALLINT UNSIGNED, stop36 SMALLINT UNSIGNED,
    stop37 SMALLINT UNSIGNED, stop38 SMALLINT UNSIGNED, stop39 SMALLINT UNSIGNED,
    stop40 SMALLINT UNSIGNED, stop41 SMALLINT UNSIGNED, stop42 SMALLINT UNSIGNED,
    stop43 SMALLINT UNSIGNED, stop44 SMALLINT UNSIGNED, stop45 SMALLINT UNSIGNED,
    stop46 SMALLINT UNSIGNED, stop47 SMALLINT UNSIGNED, stop48 SMALLINT UNSIGNED,
    stop49 SMALLINT UNSIGNED, stop50 SMALLINT UNSIGNED,
    PRIMARY KEY (route_data_id, aou),
    INDEX idx_mig_aou   (aou),
    INDEX idx_mig_year  (year),
    INDEX idx_mig_route (country_num, state_num, route)
);
