#!/usr/bin/env Rscript
# Within-California cell-level correlation: pyrethroid load increase vs bird trend
#
# Joins eBird S&T cell-level abd_ppy with county-level pyrethroid delta
# from PUR data. Restricted to agricultural counties to avoid confounding
# from urban pyrethroid decreases.

.libPaths(c("~/R/library", .libPaths()))
library(ebirdst)
library(dplyr)
library(sf)
library(tigris)
library(ggplot2)

options(tigris_use_cache = TRUE)

DATA_DIR <- "pur_analysis/ebirdst"
OUT_DIR  <- "pur_analysis"

SPECIES <- c(
  "cliswa" = "Cliff Swallow",
  "treswa" = "Tree Swallow",
  "barswa" = "Barn Swallow",
  "nrwswa" = "Northern Rough-winged Swallow"
)

# Agricultural counties only — exclude urban and mountain counties
# that would confound the exposure/trend relationship
AG_COUNTIES <- c(
  "001",  # Alameda (partial)
  "003",  # Amador
  "007",  # Butte
  "011",  # Colusa
  "019",  # Fresno
  "021",  # Glenn
  "029",  # Kern
  "031",  # Kings
  "033",  # Lake
  "039",  # Madera
  "047",  # Merced
  "053",  # Modoc
  "055",  # Monterey
  "057",  # Napa
  "061",  # Placer (partial)
  "067",  # Sacramento
  "069",  # San Benito
  "077",  # San Joaquin
  "079",  # San Luis Obispo
  "083",  # Santa Barbara
  "085",  # Santa Clara (partial)
  "087",  # Santa Cruz
  "089",  # Shasta
  "095",  # Solano
  "097",  # Sonoma
  "099",  # Stanislaus
  "101",  # Sutter
  "103",  # Tehama
  "107",  # Tulare
  "111",  # Ventura
  "113",  # Yolo
  "115"   # Yuba
)

# ---------------------------------------------------------------------------
# 1. County polygons from tigris
# ---------------------------------------------------------------------------
cat("Loading CA county polygons...\n")
ca_counties <- counties(state = "CA", cb = TRUE, year = 2022) |>
  filter(COUNTYFP %in% AG_COUNTIES) |>
  select(COUNTYFP, NAME) |>
  st_transform(4326)

# ---------------------------------------------------------------------------
# 2. County-level pyrethroid delta from PUR
# ---------------------------------------------------------------------------
cat("Loading PUR pyrethroid delta...\n")
pur <- read.csv(file.path(OUT_DIR, "pur_county_by_class.csv"),
                colClasses = c(county = "character"))
pur$county <- sprintf("%02d", as.integer(pur$county))

# CDPR 2-digit code -> FIPS 3-digit (CDPR uses sequential 1-58, FIPS is different)
# Map built from known county list
cdpr_to_fips <- c(
  "01"="001","02"="003","03"="005","04"="007","05"="009","06"="011",
  "07"="013","08"="015","09"="017","10"="019","11"="021","12"="023",
  "13"="025","14"="027","15"="029","16"="031","17"="033","18"="035",
  "19"="037","20"="039","21"="041","22"="043","23"="045","24"="047",
  "25"="049","26"="051","27"="053","28"="055","29"="057","30"="059",
  "31"="061","32"="063","33"="065","34"="067","35"="069","36"="071",
  "37"="073","38"="075","39"="077","40"="079","41"="081","42"="083",
  "43"="085","44"="087","45"="089","46"="091","47"="093","48"="095",
  "49"="097","50"="099","51"="101","52"="103","53"="105","54"="107",
  "55"="109","56"="111","57"="113","58"="115"
)
pur$fips <- cdpr_to_fips[pur$county]

pyr <- pur |>
  filter(class == "pyrethroid") |>
  group_by(fips, year) |>
  summarise(lbs = sum(lbs), .groups = "drop")

pre  <- pyr |> filter(year %in% 2015:2018) |>
  group_by(fips) |> summarise(pre_lbs = mean(lbs))
post <- pyr |> filter(year %in% 2021:2023) |>
  group_by(fips) |> summarise(post_lbs = mean(lbs))

county_pyr <- left_join(pre, post, by = "fips") |>
  mutate(pyr_delta = coalesce(post_lbs, 0) - coalesce(pre_lbs, 0),
         pyr_pct_change = 100 * pyr_delta / coalesce(pre_lbs, 1)) |>
  filter(!is.na(fips))

cat("  Counties with pyrethroid data:", nrow(county_pyr), "\n")

# ---------------------------------------------------------------------------
# 3. Load cell-level S&T for all species, assign to county
# ---------------------------------------------------------------------------
cat("Loading cell-level trends and assigning to counties...\n")

all_cells <- lapply(names(SPECIES), function(sp) {
  tr <- load_trends(sp, path = DATA_DIR) |>
    mutate(common_name = SPECIES[[sp]])
}) |> bind_rows()

# Convert to sf points
cells_sf <- all_cells |>
  filter(!is.na(longitude), !is.na(latitude)) |>
  st_as_sf(coords = c("longitude", "latitude"), crs = 4326)

# Spatial join: assign each cell to a county
cells_joined <- st_join(cells_sf, ca_counties, join = st_within) |>
  filter(!is.na(COUNTYFP)) |>
  as.data.frame() |>
  select(species_code, common_name, abd_ppy, abd_ppy_lower, abd_ppy_upper,
         COUNTYFP, NAME)

cat("  Cells matched to ag counties:", nrow(cells_joined), "\n")
cat("  Species breakdown:\n")
print(table(cells_joined$common_name))

# Join with pyrethroid delta
analysis_df <- cells_joined |>
  left_join(county_pyr, by = c("COUNTYFP" = "fips")) |>
  filter(!is.na(pyr_delta))

cat("  Cells with PUR data:", nrow(analysis_df), "\n")

# ---------------------------------------------------------------------------
# 4. Correlation analysis per species
# ---------------------------------------------------------------------------
cat("\n=== CORRELATION: pyrethroid delta vs abd_ppy ===\n")

results <- analysis_df |>
  group_by(common_name) |>
  summarise(
    n = n(),
    r = cor(pyr_delta, abd_ppy, use = "complete.obs"),
    p_val = tryCatch(
      cor.test(pyr_delta, abd_ppy)$p.value,
      error = function(e) NA
    ),
    .groups = "drop"
  ) |>
  mutate(
    sig = case_when(p_val < 0.01 ~ "**", p_val < 0.05 ~ "*", TRUE ~ "ns"),
    direction = if_else(r < 0, "more decline where pyrethroids increased", "less decline")
  )

print(results)

write.csv(analysis_df, file.path(OUT_DIR, "kern_cell_correlation_data.csv"),
          row.names = FALSE)

# ---------------------------------------------------------------------------
# 5. Scatter plot
# ---------------------------------------------------------------------------
COLORS <- c(
  "Cliff Swallow"                 = "#e05c2a",
  "Tree Swallow"                  = "#3d7abf",
  "Barn Swallow"                  = "#4a9e6b",
  "Northern Rough-winged Swallow" = "#9d755d"
)

p <- ggplot(analysis_df, aes(x = pyr_delta / 1000, y = abd_ppy,
                              color = common_name)) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray60") +
  geom_vline(xintercept = 0, linetype = "dashed", color = "gray60") +
  geom_point(alpha = 0.5, size = 1.8) +
  geom_smooth(method = "lm", se = TRUE, linewidth = 1, alpha = 0.15) +
  geom_text(data = results,
            aes(x = Inf, y = Inf,
                label = sprintf("r = %.2f %s", r, sig),
                color = common_name),
            hjust = 1.1, vjust = 2,
            size = 3.5, fontface = "bold", inherit.aes = FALSE) +
  scale_color_manual(values = COLORS, name = NULL) +
  facet_wrap(~common_name, nrow = 2) +
  labs(
    title    = "Pyrethroid use increase vs. breeding abundance trend — California ag counties",
    subtitle = "Each point = one 27km eBird S&T cell | PUR 2015–18 → 2021–23 delta | trend 2012–2022",
    x        = "County pyrethroid change (thousand lbs/yr, pre→post 2019)",
    y        = "Annual abundance change % per year (abd_ppy)"
  ) +
  theme_minimal(base_size = 12) +
  theme(legend.position = "none",
        strip.text = element_text(face = "bold"))

ggsave(file.path(OUT_DIR, "chart_cell_correlation.png"),
       p, width = 10, height = 8, dpi = 150)
cat("Chart saved to pur_analysis/chart_cell_correlation.png\n")
