-- BBS (Breeding Bird Survey) tables for pur_data database
-- Three normalized tables: route metadata, species counts, pesticide exposure
--
-- Load order: bbs_route → bbs_count → bbs_exposure
-- Loader: load_bbs_mysql.py
-- Source CSVs: spatial/outputs/bbs_locations.csv
--              spatial/outputs/level1_model_input.csv   (count columns)
--              spatial/outputs/bbs_exposure_yearly.csv

USE pur_data;

-- 44 California BBS routes used in the Level 1 exposure analysis
CREATE TABLE IF NOT EXISTS bbs_route (
    route_id          VARCHAR(30)       NOT NULL,   -- e.g. BBS_CA_054_ORANGE_COVE
    latitude          DOUBLE            NOT NULL,
    longitude         DOUBLE            NOT NULL,
    route_no          SMALLINT UNSIGNED NOT NULL,
    route_name        VARCHAR(60)       NOT NULL,
    bcr               TINYINT UNSIGNED,             -- Bird Conservation Region
    survey_start_date DATE,                         -- representative window start
    survey_end_date   DATE,                         -- representative window end
    n_pur_5km         INT UNSIGNED,                 -- PUR records within 5 km, all years
    lbs_ai_5km        DOUBLE,                       -- total lbs AI within 5 km, all years
    PRIMARY KEY (route_id)
);

-- Aerial insectivore counts by route × year × species
-- count_total NULL  = route not surveyed that year (COVID 2020, post-2022 cutoff, etc.)
-- count_total = 0   = route surveyed, focal species not detected
-- count_total > 0   = detected individuals
CREATE TABLE IF NOT EXISTS bbs_count (
    route_id       VARCHAR(30)       NOT NULL,
    year           SMALLINT UNSIGNED NOT NULL,
    species_code   VARCHAR(40)       NOT NULL,   -- stem of cnt_* column, e.g. barn_swallow
    species_name   VARCHAR(60)       NOT NULL,
    aou_code       SMALLINT UNSIGNED,            -- NULL for group totals
    is_group_total TINYINT(1)        DEFAULT 0, -- 1 for swallows_total etc.
    count_total    SMALLINT,                     -- NULL = not surveyed
    PRIMARY KEY (route_id, year, species_code),
    INDEX idx_cnt_year (year),
    INDEX idx_cnt_aou  (aou_code)
);

-- Pesticide exposure per route × year × chemical class × buffer × lag window
-- Derived from CDPR PUR via PLSS spatial join (spatial/bbs_counts.py pipeline)
CREATE TABLE IF NOT EXISTS bbs_exposure (
    id                     INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    route_id               VARCHAR(30)       NOT NULL,
    year                   SMALLINT UNSIGNED NOT NULL,
    survey_start           DATE              NOT NULL,
    survey_end             DATE              NOT NULL,
    chemical_class         VARCHAR(40)       NOT NULL,
    buffer_m               SMALLINT UNSIGNED NOT NULL,   -- 500, 1000, 2000, 5000
    lag_window_days        TINYINT UNSIGNED  NOT NULL,   -- 30, 60, 90
    lbs_ai                 DOUBLE,
    acres_treated          DOUBLE,
    tox_units_avian        DOUBLE,
    tox_units_aquatic      DOUBLE,
    n_sections_intersected SMALLINT UNSIGNED,
    n_applications         INT UNSIGNED,
    spatial_join           VARCHAR(20),                  -- e.g. plss_spatial
    PRIMARY KEY (id),
    UNIQUE KEY uq_exp (route_id, year, chemical_class, buffer_m, lag_window_days),
    INDEX idx_exp_route (route_id),
    INDEX idx_exp_year  (year),
    INDEX idx_exp_class (chemical_class)
);
