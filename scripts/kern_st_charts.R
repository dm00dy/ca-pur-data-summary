#!/usr/bin/env Rscript
# Static charts for eBird S&T swallow declines — San Joaquin Valley / Kern Co.
# Assumes trend data already downloaded by kern_st_trends.R

.libPaths(c("~/R/library", .libPaths()))
library(ebirdst)
library(dplyr)
library(ggplot2)

DATA_DIR <- "pur_analysis/ebirdst"
OUT_DIR  <- "pur_analysis"

BBOX <- list(lon_min = -120.5, lon_max = -118.0,
             lat_min =   34.8, lat_max =   36.8)

SPECIES <- c(
  "cliswa" = "Cliff Swallow",
  "treswa" = "Tree Swallow",
  "barswa" = "Barn Swallow",
  "nrwswa" = "Northern Rough-winged Swallow"
)

COLORS <- c(
  "Cliff Swallow"                 = "#e05c2a",
  "Tree Swallow"                  = "#3d7abf",
  "Barn Swallow"                  = "#4a9e6b",
  "Northern Rough-winged Swallow" = "#9d755d"
)

# Load all region data
region_data <- lapply(names(SPECIES), function(sp) {
  tr <- load_trends(sp, path = DATA_DIR)
  tr |>
    filter(longitude >= BBOX$lon_min, longitude <= BBOX$lon_max,
           latitude  >= BBOX$lat_min, latitude  <= BBOX$lat_max) |>
    mutate(common_name = SPECIES[[sp]])
}) |> bind_rows()

# ---------------------------------------------------------------------------
# Chart 1: Species trend comparison (pointrange)
# ---------------------------------------------------------------------------

summary_df <- region_data |>
  group_by(common_name) |>
  summarise(
    ppy_median = median(abd_ppy, na.rm = TRUE),
    ppy_lower  = median(abd_ppy_lower, na.rm = TRUE),
    ppy_upper  = median(abd_ppy_upper, na.rm = TRUE),
    n_cells    = n(),
    .groups = "drop"
  ) |>
  mutate(
    label = paste0(common_name, "\n(n=", n_cells, " cells)"),
    pct_change_10yr = round((1 + ppy_median / 100)^10 * 100 - 100, 0)
  )

p1 <- ggplot(summary_df,
             aes(x = reorder(label, ppy_median),
                 y = ppy_median, color = common_name)) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray60", linewidth = 0.7) +
  geom_pointrange(aes(ymin = ppy_lower, ymax = ppy_upper),
                  linewidth = 1.1, size = 0.6) +
  geom_point(size = 4) +
  geom_text(aes(label = paste0(pct_change_10yr, "% over 10 yr")),
            hjust = -0.15, size = 3.5, color = "gray30") +
  scale_color_manual(values = COLORS, guide = "none") +
  scale_y_continuous(limits = c(-5, 3),
                     labels = function(x) paste0(x, "%")) +
  coord_flip() +
  labs(
    title    = "Breeding season abundance trends — San Joaquin Valley / Kern Co.",
    subtitle = "eBird Status & Trends 2012–2022 | median abd_ppy (median CI range)",
    x = NULL,
    y = "Annual abundance change (% per year)"
  ) +
  theme_minimal(base_size = 13) +
  theme(panel.grid.major.y = element_blank())

ggsave(file.path(OUT_DIR, "chart_st_species_comparison.png"),
       p1, width = 9, height = 4.5, dpi = 150)
cat("Saved chart_st_species_comparison.png\n")

# ---------------------------------------------------------------------------
# Chart 2: Spatial map of trends across the region
# ---------------------------------------------------------------------------

# Use all cells within a wider box for context, highlight focal bbox
map_data <- lapply(names(SPECIES), function(sp) {
  load_trends(sp, path = DATA_DIR) |>
    filter(longitude >= -121.5, longitude <= -117.0,
           latitude  >=   34.0, latitude  <=   37.5) |>
    mutate(common_name = SPECIES[[sp]])
}) |> bind_rows()

p2 <- ggplot(map_data, aes(x = longitude, y = latitude, color = abd_ppy * 100)) +
  geom_point(size = 1.8, alpha = 0.85) +
  scale_color_gradient2(
    low      = "#c0392b",
    mid      = "gray90",
    high     = "#2980b9",
    midpoint = 0,
    limits   = c(-6, 6),
    oob      = scales::squish,
    name     = "% change\nper year"
  ) +
  # Kern NWR marker
  annotate("point", x = -119.37, y = 35.65, shape = 17, size = 3, color = "black") +
  annotate("text",  x = -119.37, y = 35.65, label = "Kern NWR",
           hjust = -0.1, vjust = 0.5, size = 3, fontface = "bold") +
  facet_wrap(~common_name, nrow = 2) +
  coord_fixed(ratio = 1.2) +
  labs(
    title    = "Aerial insectivore breeding trends — San Joaquin Valley region",
    subtitle = "eBird Status & Trends 2012–2022 | each point = 27 km cell | red = declining",
    x = "Longitude", y = "Latitude"
  ) +
  theme_minimal(base_size = 11) +
  theme(strip.text = element_text(face = "bold"))

ggsave(file.path(OUT_DIR, "chart_st_spatial_map.png"),
       p2, width = 10, height = 8, dpi = 150)
cat("Saved chart_st_spatial_map.png\n")

# ---------------------------------------------------------------------------
# Chart 3: Projected population trajectory (cumulative decline)
# ---------------------------------------------------------------------------

years <- 2012:2022
traj_df <- summary_df |>
  rowwise() |>
  mutate(
    traj = list(data.frame(
      year  = years,
      index = (1 + ppy_median / 100) ^ (years - 2012) * 100
    ))
  ) |>
  tidyr::unnest(traj)

# Ribbon from lower to upper CI
ribbon_df <- summary_df |>
  rowwise() |>
  mutate(
    traj = list(data.frame(
      year  = years,
      lower = (1 + ppy_lower / 100) ^ (years - 2012) * 100,
      upper = (1 + ppy_upper / 100) ^ (years - 2012) * 100
    ))
  ) |>
  tidyr::unnest(traj)

p3 <- ggplot() +
  geom_ribbon(data = ribbon_df,
              aes(x = year, ymin = lower, ymax = upper, fill = common_name),
              alpha = 0.12) +
  geom_line(data = traj_df,
            aes(x = year, y = index, color = common_name),
            linewidth = 1.2) +
  geom_hline(yintercept = 100, linetype = "dashed", color = "gray50", linewidth = 0.6) +
  geom_vline(xintercept = 2019, linetype = "dotted", color = "gray40", linewidth = 0.7) +
  annotate("text", x = 2019.1, y = 70, label = "Chlorpyrifos\nphase-out",
           hjust = 0, size = 3, color = "gray35") +
  scale_color_manual(values = COLORS, name = NULL) +
  scale_fill_manual(values  = COLORS, name = NULL) +
  scale_x_continuous(breaks = 2012:2022) +
  scale_y_continuous(labels = function(x) paste0(x, "%")) +
  labs(
    title    = "Projected cumulative abundance change — San Joaquin Valley aerial insectivores",
    subtitle = "eBird Status & Trends 2012–2022 | indexed to 100 at 2012 | ribbon = median CI",
    x = NULL,
    y = "Relative abundance index (2012 = 100%)"
  ) +
  theme_minimal(base_size = 13) +
  theme(legend.position = "bottom",
        panel.grid.minor = element_blank())

ggsave(file.path(OUT_DIR, "chart_st_trajectory.png"),
       p3, width = 10, height = 5.5, dpi = 150)
cat("Saved chart_st_trajectory.png\n")
