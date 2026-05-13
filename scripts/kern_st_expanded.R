#!/usr/bin/env Rscript
# Expanded aerial insectivore S&T trends for Kern NWR region
# Includes all 9 species recorded at Kern NWR hotspots, not just the 4 swallows

.libPaths(c("~/R/library", .libPaths()))
library(ebirdst)
library(dplyr)
library(ggplot2)

DATA_DIR <- "pur_analysis/ebirdst"
OUT_DIR  <- "pur_analysis"

# All 9 aerial insectivores recorded at Kern NWR hotspots
SPECIES_ALL <- c(
  "banswa" = "Bank Swallow",
  "barswa" = "Barn Swallow",
  "cliswa" = "Cliff Swallow",
  "lesnig" = "Lesser Nighthawk",
  "nrwswa" = "Northern Rough-winged Swallow",
  "purmar" = "Purple Martin",
  "treswa" = "Tree Swallow",
  "weskin" = "Western Kingbird",
  "whtswi" = "White-throated Swift"
)

BBOX_SJV <- list(lon_min = -120.5, lon_max = -118.0, lat_min = 34.8, lat_max = 36.8)

# ---------------------------------------------------------------------------
# 1. Check which species have S&T data available
# ---------------------------------------------------------------------------
cat("Checking S&T data availability...\n")
available <- ebirdst_runs$species_code
have_data  <- names(SPECIES_ALL)[names(SPECIES_ALL) %in% available]
no_data    <- names(SPECIES_ALL)[!names(SPECIES_ALL) %in% available]

cat("  Have S&T data:", paste(SPECIES_ALL[have_data], collapse=", "), "\n")
cat("  No S&T data:  ", paste(SPECIES_ALL[no_data],   collapse=", "), "\n\n")

# ---------------------------------------------------------------------------
# 2. Download and extract SJV trends for available species
# ---------------------------------------------------------------------------
all_trends <- list()

for (sp in have_data) {
  common <- SPECIES_ALL[[sp]]
  cat("---", common, "(", sp, ") ---\n")

  tryCatch(
    ebirdst_download_trends(sp, path = DATA_DIR),
    error = function(e) cat("  Download:", conditionMessage(e), "\n")
  )

  tr <- tryCatch(
    load_trends(sp, path = DATA_DIR),
    error = function(e) { cat("  Load error:", conditionMessage(e), "\n"); NULL }
  )
  if (is.null(tr)) next

  region <- tr |>
    filter(longitude >= BBOX_SJV$lon_min, longitude <= BBOX_SJV$lon_max,
           latitude  >= BBOX_SJV$lat_min, latitude  <= BBOX_SJV$lat_max)

  cat("  SJV cells:", nrow(region), "\n")
  if (nrow(region) == 0) next

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

  cat(sprintf("  abd_ppy: %.2f%%/yr  (CI %.2f – %.2f)  %.0f%% cells declining\n",
              summary$ppy_median, summary$ppy_lower, summary$ppy_upper,
              summary$pct_declining))

  all_trends[[sp]] <- summary
}

# ---------------------------------------------------------------------------
# 3. Output table
# ---------------------------------------------------------------------------
if (length(all_trends) == 0) {
  cat("\nNo data.\n")
  quit(status = 1)
}

df <- bind_rows(all_trends) |>
  arrange(ppy_median)

cat("\n=== SAN JOAQUIN VALLEY AERIAL INSECTIVORE TRENDS (2012-2022) ===\n")
print(df |> select(common_name, n_cells, ppy_median, ppy_lower, ppy_upper,
                   pct_declining) |> as.data.frame())

write.csv(df, file.path(OUT_DIR, "sjv_expanded_trends.csv"), row.names = FALSE)

# ---------------------------------------------------------------------------
# 4. Chart: all species by guild, ranked by decline within guild
# ---------------------------------------------------------------------------

# Guild assignment
GUILD <- c(
  "Barn Swallow"                  = "Continuous aerial forager\n(swallows / swifts)",
  "Cliff Swallow"                 = "Continuous aerial forager\n(swallows / swifts)",
  "Tree Swallow"                  = "Continuous aerial forager\n(swallows / swifts)",
  "Northern Rough-winged Swallow" = "Continuous aerial forager\n(swallows / swifts)",
  "White-throated Swift"          = "Continuous aerial forager\n(swallows / swifts)",
  "Purple Martin"                 = "Continuous aerial forager\n(swallows / swifts)",
  "Western Kingbird"              = "Sallying flycatcher\n(different foraging mode)"
)

GUILD_COLORS <- c(
  "Continuous aerial forager\n(swallows / swifts)"  = "#2c7bb6",
  "Sallying flycatcher\n(different foraging mode)"  = "#d7191c"
)

df <- df |>
  mutate(
    guild    = GUILD[common_name],
    label    = paste0(common_name, "  (n=", n_cells, ")"),
    pct_10yr = round((1 + ppy_median/100)^10 * 100 - 100, 0),
    # sort within guild by ppy_median
    sort_key = ppy_median
  ) |>
  arrange(guild, sort_key)

# Factor levels preserve within-guild ranking
df$label <- factor(df$label, levels = df$label)

p <- ggplot(df, aes(x = label, y = ppy_median, color = guild)) +
  # shaded background bands per guild
  annotate("rect",
           xmin = 0.5, xmax = sum(df$guild == "Continuous aerial forager\n(swallows / swifts)") + 0.5,
           ymin = -Inf, ymax = Inf, fill = "#2c7bb6", alpha = 0.04) +
  annotate("rect",
           xmin = sum(df$guild == "Continuous aerial forager\n(swallows / swifts)") + 0.5,
           xmax = nrow(df) + 0.5,
           ymin = -Inf, ymax = Inf, fill = "#d7191c", alpha = 0.06) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray50", linewidth = 0.7) +
  geom_pointrange(aes(ymin = ppy_lower, ymax = ppy_upper),
                  linewidth = 1.1, size = 0.55) +
  geom_point(size = 3.8) +
  geom_text(aes(label = paste0(pct_10yr, "% / 10 yr")),
            hjust = -0.12, size = 3.1, color = "gray30") +
  scale_color_manual(values = GUILD_COLORS, name = "Foraging guild") +
  scale_y_continuous(limits = c(-5, 5),
                     labels = function(x) paste0(x, "%")) +
  coord_flip() +
  labs(
    title    = "Breeding season abundance trends — San Joaquin Valley / Kern Co.",
    subtitle = "eBird Status & Trends 2012–2022 | median abd_ppy (median CI) | species recorded at Kern NWR",
    x = NULL,
    y = "Annual abundance change (% per year)",
    caption = "Decline across BOTH foraging guilds suggests shared prey-base collapse rather than foraging-mode-specific mortality"
  ) +
  theme_minimal(base_size = 12) +
  theme(
    panel.grid.major.y = element_blank(),
    legend.position    = "bottom",
    plot.caption       = element_text(face = "italic", color = "gray40", size = 9)
  )

ggsave(file.path(OUT_DIR, "chart_expanded_species.png"),
       p, width = 10, height = 5.5, dpi = 150)
cat("Saved chart_expanded_species.png\n")
