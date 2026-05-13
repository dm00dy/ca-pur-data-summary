#!/usr/bin/env Rscript
# eBird Status & Trends — Kern NWR area trend extraction
#
# Downloads breeding-season trend estimates for focal aerial insectivores,
# filters to the San Joaquin Valley / Kern County region, and writes a
# summary CSV + chart.
#
# Usage:
#   Rscript kern_st_trends.R
#   (key is stored in ~/.Renviron after first run; re-run set_ebirdst_access_key()
#    if you need to update it)

.libPaths(c("~/R/library", .libPaths()))
library(ebirdst)
library(dplyr)
library(ggplot2)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Key stored in ~/.Renviron by set_ebirdst_access_key(); set it here if needed
# set_ebirdst_access_key("your_key")

DATA_DIR <- "pur_analysis/ebirdst"
dir.create(DATA_DIR, showWarnings = FALSE, recursive = TRUE)

# Two regions — swap REGION to switch
# "sjv" = San Joaquin Valley / Kern (treatment)
# "sac" = Sacramento Valley rice corridor (control)
REGION <- "sac"

BBOXES <- list(
  sjv = list(lon_min = -120.5, lon_max = -118.0, lat_min = 34.8, lat_max = 36.8),
  sac = list(lon_min = -122.5, lon_max = -121.0, lat_min = 38.5, lat_max = 40.5)
)
BBOX <- BBOXES[[REGION]]

SPECIES <- c("cliswa", "treswa", "barswa", "nrwswa")

# ---------------------------------------------------------------------------
# Download and extract
# ---------------------------------------------------------------------------

all_trends <- list()

for (sp in SPECIES) {
  common <- ebirdst_runs$common_name[ebirdst_runs$species_code == sp]
  cat("\n---", common, "(", sp, ") ---\n")

  tryCatch(
    ebirdst_download_trends(sp, path = DATA_DIR),
    error = function(e) cat("  Download error:", conditionMessage(e), "\n")
  )

  tr <- tryCatch(
    load_trends(sp, path = DATA_DIR),
    error = function(e) { cat("  Load error:", conditionMessage(e), "\n"); NULL }
  )
  if (is.null(tr)) next

  region <- tr |>
    filter(longitude >= BBOX$lon_min, longitude <= BBOX$lon_max,
           latitude  >= BBOX$lat_min, latitude  <= BBOX$lat_max)

  cat("  Region cells:", nrow(region), "of", nrow(tr), "total\n")
  if (nrow(region) == 0) next

  # abd_ppy = annual proportional change (e.g. -0.02 = 2% decline/yr)
  summary <- region |>
    summarise(
      species_code  = sp,
      common_name   = common,
      n_cells       = n(),
      ppy_median    = median(abd_ppy,       na.rm = TRUE),
      ppy_lower     = median(abd_ppy_lower, na.rm = TRUE),
      ppy_upper     = median(abd_ppy_upper, na.rm = TRUE),
      pct_declining = 100 * mean(abd_ppy < 0, na.rm = TRUE),
      trend_years   = paste(first(start_year), first(end_year), sep = "-")
    )

  cat(sprintf("  abd_ppy: median %.3f  (%.3f – %.3f)  %.0f%% cells declining\n",
              summary$ppy_median, summary$ppy_lower,
              summary$ppy_upper, summary$pct_declining))

  all_trends[[sp]] <- summary
}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

if (length(all_trends) == 0) {
  cat("\nNo data extracted.\n")
  quit(status = 1)
}

df <- bind_rows(all_trends)
write.csv(df, paste0("pur_analysis/", REGION, "_st_trend_summary.csv"), row.names = FALSE)
cat("\n=== SUMMARY ===\n")
print(df |> select(common_name, n_cells, ppy_median, ppy_lower, ppy_upper,
                   pct_declining, trend_years))

# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

df$label <- paste0(df$common_name, "\n(", df$n_cells, " cells)")

p <- ggplot(df, aes(x = reorder(label, ppy_median), y = ppy_median * 100)) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray50") +
  geom_pointrange(aes(ymin = ppy_lower * 100, ymax = ppy_upper * 100),
                  size = 0.8, color = "#3d7abf") +
  geom_point(size = 3, color = "#3d7abf") +
  coord_flip() +
  labs(
    title    = "Aerial insectivore breeding trends — San Joaquin Valley / Kern Co.",
    subtitle = paste("eBird Status & Trends", df$trend_years[1],
                     "| median abd_ppy across region cells (median CI range)"),
    x = NULL,
    y = "Annual abundance change (% per year)"
  ) +
  theme_minimal(base_size = 13)

ggsave("pur_analysis/kern_st_trend_chart.png", p, width = 8, height = 4, dpi = 150)
cat("Chart saved to pur_analysis/kern_st_trend_chart.png\n")
