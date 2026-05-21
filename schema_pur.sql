-- California PUR (Pesticide Use Report) MySQL schema
-- Covers all 9 years 2015-2023 from CDPR annual archives
--
-- Load order:
--   formula, chemical (+casnum), county, site, qualify, error_description,
--   product, prod_chem, toxicity  ->  pur_record
--
-- 2015-2022: UDC files are chemical-level (one row per chem per application)
-- 2023:      UDC is product-level; ETL expands via prod_chem to chem-level
--
-- pur_record uses PARTITION BY RANGE(year).
-- MySQL prohibits foreign keys on partitioned tables;
-- referential integrity is enforced by the ETL layer only.

CREATE DATABASE IF NOT EXISTS pur_data
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE pur_data;

CREATE TABLE IF NOT EXISTS formula (
    formula_cd    CHAR(2)      NOT NULL,
    formula_dsc   VARCHAR(120) NOT NULL,
    dryliquid_sw  CHAR(1),
    PRIMARY KEY (formula_cd)
);

CREATE TABLE IF NOT EXISTS chemical (
    chem_code    MEDIUMINT UNSIGNED NOT NULL,
    chemalpha_cd MEDIUMINT UNSIGNED,
    chemname     VARCHAR(120) NOT NULL,
    casnum       VARCHAR(30),
    PRIMARY KEY (chem_code)
);

CREATE TABLE IF NOT EXISTS county (
    county_cd   TINYINT UNSIGNED NOT NULL,
    county_name VARCHAR(60)      NOT NULL,
    PRIMARY KEY (county_cd)
);

CREATE TABLE IF NOT EXISTS site (
    site_code MEDIUMINT    NOT NULL,
    site_name VARCHAR(120) NOT NULL,
    is_ag     TINYINT(1)   AS (site_code >= 0 AND site_code < 65000) STORED,
    PRIMARY KEY (site_code)
);

CREATE TABLE IF NOT EXISTS qualify (
    qualify_cd  SMALLINT     NOT NULL,
    qualify_dsc VARCHAR(200) NOT NULL,
    PRIMARY KEY (qualify_cd)
);

CREATE TABLE IF NOT EXISTS error_description (
    error_code        TINYINT UNSIGNED NOT NULL,
    error_description VARCHAR(500)     NOT NULL,
    PRIMARY KEY (error_code)
);

-- Product registry (2023 dropped fut_firmno and agriccom_sw vs 2015)
CREATE TABLE IF NOT EXISTS product (
    prodno       INT UNSIGNED  NOT NULL,
    mfg_firmno   INT UNSIGNED,
    reg_firmno   INT UNSIGNED,
    label_seq_no TINYINT UNSIGNED,
    revision_no  VARCHAR(10),
    fut_firmno   INT UNSIGNED,
    prodstat_ind CHAR(1),
    product_name VARCHAR(250),
    show_regno   VARCHAR(20),
    aer_grnd_ind CHAR(1),
    agriccom_sw  CHAR(1),
    confid_sw    CHAR(1),
    density      FLOAT,
    formula_cd   CHAR(2),
    full_exp_dt  DATE,
    full_iss_dt  DATE,
    fumigant_sw  CHAR(1),
    gen_pest_ind CHAR(1),
    lastup_dt    DATE,
    mfg_ref_sw   CHAR(1),
    prod_inac_dt DATE,
    reg_dt       DATE,
    reg_type_ind CHAR(1),
    rodent_sw    CHAR(1),
    signlwrd_ind CHAR(1),
    soilappl_sw  CHAR(1),
    specgrav_sw  CHAR(1),
    spec_gravity FLOAT,
    condreg_sw   CHAR(1),
    PRIMARY KEY (prodno),
    FOREIGN KEY (formula_cd) REFERENCES formula(formula_cd)
);

-- Product-to-chemical mapping; loaded from 2023 PROD_CHEM.txt
-- Used by ETL to expand 2023 product-level UDC records into chemical rows
CREATE TABLE IF NOT EXISTS prod_chem (
    prodno       INT UNSIGNED       NOT NULL,
    chem_code    MEDIUMINT UNSIGNED NOT NULL,
    prodchem_pct FLOAT,
    PRIMARY KEY (prodno, chem_code)
);

-- Enrichment: project toxicity values (from toxicity_lookup.csv)
-- bee_contact_ld50 / bee_oral_ld50 : μg/bee, Apis mellifera 48h (worst case)
-- chironomid_ec50                  : μg/L water column (see chironomid_endpoint)
-- avian_noec_repro                 : mg/kg bw/day, avian 21-day chronic NOEC
CREATE TABLE IF NOT EXISTS toxicity (
    chemname                VARCHAR(120) NOT NULL,
    chem_class              VARCHAR(60),
    avian_ld50              FLOAT,
    avian_ceiling           TINYINT(1)   DEFAULT 0,
    avian_test_species      VARCHAR(80),
    avian_source_url        VARCHAR(255),
    aquatic_lc50            FLOAT,
    aquatic_ceiling         TINYINT(1)   DEFAULT 0,
    aquatic_test_species    VARCHAR(80),
    aquatic_source_url      VARCHAR(255),
    bee_contact_ld50        FLOAT,
    bee_contact_ceiling     TINYINT(1)   DEFAULT 0,
    bee_oral_ld50           FLOAT,
    bee_oral_ceiling        TINYINT(1)   DEFAULT 0,
    bee_source_url          VARCHAR(255),
    chironomid_ec50         FLOAT,
    chironomid_ceiling      TINYINT(1)   DEFAULT 0,
    chironomid_endpoint     VARCHAR(40),
    chironomid_test_species VARCHAR(80),
    chironomid_source_url   VARCHAR(255),
    avian_noec_repro        FLOAT,
    avian_noec_ceiling      TINYINT(1)   DEFAULT 0,
    avian_noec_test_species VARCHAR(80),
    avian_noec_source_url   VARCHAR(255),
    notes                   TEXT,
    PRIMARY KEY (chemname)
);

-- Fact table: pesticide application records, all years unified
-- 2015-2022: loaded directly from UDC (chem_code inline, lbs_chm_used present)
-- 2023: expanded from product-level UDC via prod_chem join
-- Columns ag_ind, fume_cd, pre_plant only populated for 2023 records
CREATE TABLE IF NOT EXISTS pur_record (
    id           BIGINT UNSIGNED    NOT NULL AUTO_INCREMENT,
    year         SMALLINT UNSIGNED  NOT NULL,
    use_no       INT UNSIGNED       NOT NULL,
    prodno       INT UNSIGNED,
    chem_code    MEDIUMINT UNSIGNED NOT NULL,
    prodchem_pct FLOAT,
    lbs_chm_used FLOAT,
    lbs_prd_used FLOAT,
    amt_prd_used FLOAT,
    unit_of_meas CHAR(4),
    acre_planted FLOAT,
    unit_planted CHAR(4),
    acre_treated FLOAT,
    unit_treated CHAR(4),
    applic_cnt   TINYINT UNSIGNED,
    applic_dt    DATE,
    applic_time  SMALLINT UNSIGNED,
    county_cd    TINYINT UNSIGNED   NOT NULL,
    base_ln_mer  CHAR(1),
    township     TINYINT UNSIGNED,
    tship_dir    CHAR(1),
    range_no     TINYINT UNSIGNED,
    range_dir    CHAR(1),
    section      TINYINT UNSIGNED,
    site_loc_id  VARCHAR(20),
    grower_id    VARCHAR(30),
    license_no   VARCHAR(20),
    planting_seq TINYINT UNSIGNED,
    aer_gnd_ind  CHAR(1),
    site_code    MEDIUMINT,
    qualify_cd   SMALLINT,
    batch_no     INT UNSIGNED,
    document_no  VARCHAR(20),
    summary_cd   CHAR(2),
    record_id    VARCHAR(5),
    comtrs       CHAR(11),
    error_flag   CHAR(1),
    ag_ind       CHAR(1),
    fume_cd      VARCHAR(10),
    pre_plant    CHAR(1),
    PRIMARY KEY  (id, year),
    UNIQUE KEY   uq_record (year, county_cd, use_no, chem_code),
    INDEX idx_comtrs (comtrs),
    INDEX idx_applic (applic_dt),
    INDEX idx_chem   (chem_code),
    INDEX idx_site   (county_cd, site_code)
)
PARTITION BY RANGE (year) (
    PARTITION p2015 VALUES LESS THAN (2016),
    PARTITION p2016 VALUES LESS THAN (2017),
    PARTITION p2017 VALUES LESS THAN (2018),
    PARTITION p2018 VALUES LESS THAN (2019),
    PARTITION p2019 VALUES LESS THAN (2020),
    PARTITION p2020 VALUES LESS THAN (2021),
    PARTITION p2021 VALUES LESS THAN (2022),
    PARTITION p2022 VALUES LESS THAN (2023),
    PARTITION p2023 VALUES LESS THAN (2024)
);
