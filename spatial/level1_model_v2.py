"""
level1_model_v2.py — Second-swing models: first-differences, pyrethroid-share,
and a difference-in-differences design around the 2019 chlorpyrifos cancellation.

The first-swing models (level1_model.py) found:
  - Model A (cross-sectional): pyrethroid β positive (habitat confound)
  - Model B (within-route demeaned): null exposure effects; clean −4.4%/yr
    Western Kingbird temporal decline

This script tries three angles the first swing did not:

1. FIRST-DIFFERENCE MODEL
   Δ log(count+1)_t = α + β·Δ exposure_t + γ·year_t + ε
   Equivalent to within-route in expectation but emphasizes high-frequency
   year-to-year covariance and is less sensitive to slow drift.

2. PYRETHROID SHARE MODEL
   The statewide story is composition shift, not absolute load. Replace
   raw pyrethroid tox units with pyrethroid_share = pyr / (pyr + OP).
   Tests whether the *chemistry mix* matters above and beyond total load.

3. DIFFERENCE-IN-DIFFERENCES AROUND 2019 CHLORPYRIFOS CANCELLATION
   Treatment: routes with high 2015–2018 OP exposure ("OP-heavy")
   Control:   routes with low  2015–2018 OP exposure
   Outcome:   Δ log(count) from pre-cliff (2015–2018) to post-cliff (2020–2022)
   Tests whether removing the dominant OP produced a measurable rebound on
   the routes that had been receiving the most OP.
"""

from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.linear_model import OLS

warnings.filterwarnings("ignore")

OUT_DIR = Path(__file__).parent / "outputs"
DATA_PATH = OUT_DIR / "level1_model_input.csv"

FOCAL = {
    "cnt_barn_swallow":     "Barn Swallow",
    "cnt_cliff_swallow":    "Cliff Swallow",
    "cnt_tree_swallow":     "Tree Swallow",
    "cnt_western_kingbird": "Western Kingbird",
    "cnt_swallows_total":   "All Swallows",
}

BUF, LAG = 5000, 90
PYR = f"Pyrethroids_{BUF}m_{LAG}d_tox_units_aquatic"
OP  = f"Organophosphates_{BUF}m_{LAG}d_tox_units_aquatic"


def _sig(p):
    if p is None or not np.isfinite(p): return "  "
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    if p < 0.1:   return "."
    return "ns"


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df = df[df["cnt_aerial_insectivores_total"].notna()].copy()
    df["route_id"] = df["location_id"].str.rsplit("_", n=1).str[0]
    df["year"]     = df["location_id"].str.split("_").str[-1].astype(int)
    for c in [c for c in df.columns if c.startswith("cnt_")]:
        df[f"log1p_{c}"] = np.log1p(df[c].fillna(0))
    return df.sort_values(["route_id", "year"]).reset_index(drop=True)


def first_difference(df: pd.DataFrame, response: str) -> dict:
    """
    Δ log(count) = α + β1·Δpyr + β2·Δop + β3·year + ε
    First differences taken within route between consecutive surveyed years.
    """
    log_col = f"log1p_{response}"
    sub = df[[log_col, PYR, OP, "route_id", "year"]].dropna().copy()
    sub = sub.sort_values(["route_id", "year"])
    g = sub.groupby("route_id")
    sub["dlog"]  = g[log_col].diff()
    sub["dpyr"]  = g[PYR].diff()
    sub["dop"]   = g[OP].diff()
    sub["dyear"] = g["year"].diff()
    fd = sub.dropna(subset=["dlog", "dpyr", "dop"])
    fd = fd[fd["dyear"] > 0]  # consecutive surveyed years; allows gap > 1
    if len(fd) < 20:
        return {"n": len(fd)}

    pyr_sd = fd["dpyr"].std()
    op_sd  = fd["dop"].std()
    fd["dpyr_z"] = (fd["dpyr"] - fd["dpyr"].mean()) / pyr_sd if pyr_sd > 0 else 0
    fd["dop_z"]  = (fd["dop"]  - fd["dop"].mean())  / op_sd  if op_sd  > 0 else 0

    X = sm.add_constant(fd[["dpyr_z", "dop_z", "year"]])
    res = OLS(fd["dlog"], X).fit(cov_type="HC3")
    return {
        "n": len(fd), "r2": res.rsquared,
        "pyr_b": res.params["dpyr_z"], "pyr_p": res.pvalues["dpyr_z"],
        "pyr_lo": res.params["dpyr_z"] - 1.96*res.bse["dpyr_z"],
        "pyr_hi": res.params["dpyr_z"] + 1.96*res.bse["dpyr_z"],
        "op_b":  res.params["dop_z"],  "op_p":  res.pvalues["dop_z"],
        "op_lo": res.params["dop_z"] - 1.96*res.bse["dop_z"],
        "op_hi": res.params["dop_z"] + 1.96*res.bse["dop_z"],
        "yr_b":  res.params["year"],   "yr_p":  res.pvalues["year"],
    }


def pyr_share_model(df: pd.DataFrame, response: str) -> dict:
    """
    Within-route demeaned OLS on pyrethroid share and total insecticide tox.
    Share = pyr / (pyr + op + ε)  (ε floor to avoid divide-by-zero on routes
    with near-zero load — those routes have no chemistry-mix signal anyway
    and are pulled toward the mean by demeaning).
    """
    log_col = f"log1p_{response}"
    sub = df[[log_col, PYR, OP, "route_id", "year"]].dropna().copy()
    sub["total"] = sub[PYR] + sub[OP]
    sub["share"] = sub[PYR] / sub["total"].clip(lower=1.0)
    # Only routes with meaningful total exposure see meaningful share variation
    sub = sub[sub["total"] >= 10].copy()
    if len(sub) < 20:
        return {"n": len(sub)}

    for c in [log_col, "share", "total"]:
        sub[f"{c}_dm"] = sub[c] - sub.groupby("route_id")[c].transform("mean")
    sub["log_total_dm"] = np.log1p(sub["total"]) - sub.groupby("route_id")["total"].transform(lambda s: np.log1p(s).mean())

    # Standardize the demeaned regressors
    for c in ["share_dm", "log_total_dm"]:
        sd = sub[c].std()
        sub[f"{c}_z"] = (sub[c] - sub[c].mean()) / sd if sd > 0 else 0

    sub["year_ctr"] = sub["year"] - 2018
    X = sm.add_constant(sub[["share_dm_z", "log_total_dm_z", "year_ctr"]])
    res = OLS(sub[f"{log_col}_dm"], X).fit(cov_type="HC3")
    return {
        "n": len(sub), "r2": res.rsquared,
        "share_b": res.params["share_dm_z"], "share_p": res.pvalues["share_dm_z"],
        "share_lo": res.params["share_dm_z"] - 1.96*res.bse["share_dm_z"],
        "share_hi": res.params["share_dm_z"] + 1.96*res.bse["share_dm_z"],
        "tot_b":  res.params["log_total_dm_z"], "tot_p": res.pvalues["log_total_dm_z"],
        "yr_b":   res.params["year_ctr"], "yr_p": res.pvalues["year_ctr"],
        "share_mean": sub["share"].mean(),
        "share_p10":  sub["share"].quantile(0.10),
        "share_p90":  sub["share"].quantile(0.90),
    }


def did_chlorpyrifos(df: pd.DataFrame, response: str) -> dict:
    """
    Difference-in-differences around the 2019 chlorpyrifos cancellation.

      log(count+1)_it = α + β1·post_t + β2·heavy_i + β3·(post×heavy) + γ·year + u_i + ε

    Implemented as within-route via demeaning: the level effects α and β2
    (route fixed effect) drop out, leaving the interaction β3 as the DiD
    estimand. Heavy_i is defined from PRE-period mean OP exposure
    (2015–2018), so it is uncorrelated with post-period shocks.

    β3 > 0 (positive interaction) = OP-heavy routes recovered MORE than
                                    OP-light routes after the cliff.
    β3 = 0 = no relative recovery despite massive statewide OP drop.
    """
    log_col = f"log1p_{response}"
    sub = df[[log_col, OP, PYR, "route_id", "year"]].dropna().copy()
    pre = sub[sub["year"].between(2015, 2018)].groupby("route_id")[OP].mean()
    if pre.empty:
        return {"n": 0}
    threshold = pre.median()
    sub["heavy"] = sub["route_id"].map((pre >= threshold).astype(int))
    sub = sub.dropna(subset=["heavy"])
    sub["post"]  = (sub["year"] >= 2020).astype(int)
    # Drop transition year 2019 to clarify pre/post
    sub = sub[sub["year"] != 2019].copy()
    sub["did"]   = sub["heavy"] * sub["post"]

    # Demean within route → kills heavy_i level effect; post and did remain
    for c in [log_col, "post", "did"]:
        sub[f"{c}_dm"] = sub[c] - sub.groupby("route_id")[c].transform("mean")
    sub["year_ctr"] = sub["year"] - 2018

    if len(sub) < 20:
        return {"n": len(sub)}

    X = sm.add_constant(sub[["post_dm", "did_dm"]])
    res = OLS(sub[f"{log_col}_dm"], X).fit(cov_type="HC3")
    return {
        "n": len(sub), "r2": res.rsquared,
        "n_heavy": int((pre >= threshold).sum()),
        "n_light": int((pre <  threshold).sum()),
        "threshold_op": float(threshold),
        "post_b": res.params["post_dm"], "post_p": res.pvalues["post_dm"],
        "did_b":  res.params["did_dm"],  "did_p":  res.pvalues["did_dm"],
        "did_lo": res.params["did_dm"] - 1.96*res.bse["did_dm"],
        "did_hi": res.params["did_dm"] + 1.96*res.bse["did_dm"],
    }


def main():
    df = load_data()
    print("=== Level 1 v2: First-differences, Pyrethroid-share, DiD ===\n")
    print(f"Data: {len(df)} surveyed route-years, "
          f"{df['route_id'].nunique()} routes, "
          f"years {df['year'].min()}–{df['year'].max()}\n")

    # -------------------------------------------------------------------
    print("═" * 70)
    print("1. FIRST-DIFFERENCE OLS  Δ log(count) ~ Δ pyr_z + Δ op_z + year")
    print("   Tests whether year-over-year change in exposure predicts")
    print("   year-over-year change in count, within route.\n")
    fd_rows = []
    for resp, label in FOCAL.items():
        r = first_difference(df, resp)
        if r.get("n", 0) < 20:
            print(f"  {label}: too few first-difference observations ({r.get('n', 0)})")
            continue
        print(f"  {label}  (n={r['n']}, R²={r['r2']:.3f})")
        print(f"    Δ Pyr  β={r['pyr_b']:+.3f} "
              f"[{r['pyr_lo']:+.3f}, {r['pyr_hi']:+.3f}]  "
              f"p={r['pyr_p']:.3f} {_sig(r['pyr_p'])}")
        print(f"    Δ OP   β={r['op_b']:+.3f} "
              f"[{r['op_lo']:+.3f}, {r['op_hi']:+.3f}]  "
              f"p={r['op_p']:.3f} {_sig(r['op_p'])}")
        print(f"    year   β={r['yr_b']:+.4f}  p={r['yr_p']:.3f} {_sig(r['yr_p'])}\n")
        fd_rows.append({"species": label, "response": resp, **r})

    # -------------------------------------------------------------------
    print("═" * 70)
    print("2. PYRETHROID SHARE  Within-route, controls for total tox load")
    print("   share = pyr / (pyr + op);  tests chemistry-mix effect.\n")
    ps_rows = []
    for resp, label in FOCAL.items():
        r = pyr_share_model(df, resp)
        if r.get("n", 0) < 20:
            print(f"  {label}: too few obs ({r.get('n', 0)})")
            continue
        print(f"  {label}  (n={r['n']}, R²_within={r['r2']:.3f})")
        print(f"    share={r['share_mean']:.2f}  "
              f"p10-p90: {r['share_p10']:.2f}–{r['share_p90']:.2f}")
        print(f"    Pyr-share  β={r['share_b']:+.3f} "
              f"[{r['share_lo']:+.3f}, {r['share_hi']:+.3f}]  "
              f"p={r['share_p']:.3f} {_sig(r['share_p'])}")
        print(f"    log(total) β={r['tot_b']:+.3f}  "
              f"p={r['tot_p']:.3f} {_sig(r['tot_p'])}")
        print(f"    year       β={r['yr_b']:+.4f}  "
              f"p={r['yr_p']:.3f} {_sig(r['yr_p'])}\n")
        ps_rows.append({"species": label, "response": resp, **r})

    # -------------------------------------------------------------------
    print("═" * 70)
    print("3. DIFFERENCE-IN-DIFFERENCES around 2019 chlorpyrifos cancellation")
    print("   pre = 2015-2018, post = 2020-2022 (2019 dropped as transition)")
    print("   heavy = pre-period OP exposure ≥ median across routes")
    print("   DiD β > 0  →  OP-heavy routes recovered relative to OP-light\n")
    did_rows = []
    for resp, label in FOCAL.items():
        r = did_chlorpyrifos(df, resp)
        if r.get("n", 0) < 20:
            print(f"  {label}: too few obs ({r.get('n', 0)})")
            continue
        print(f"  {label}  (n={r['n']}, R²={r['r2']:.3f}, "
              f"heavy={r['n_heavy']} routes, light={r['n_light']} routes)")
        print(f"    post (all routes)    β={r['post_b']:+.3f}  "
              f"p={r['post_p']:.3f} {_sig(r['post_p'])}")
        print(f"    DiD (heavy×post)     β={r['did_b']:+.3f} "
              f"[{r['did_lo']:+.3f}, {r['did_hi']:+.3f}]  "
              f"p={r['did_p']:.3f} {_sig(r['did_p'])}")
        rebound_pct = (np.exp(r['did_b']) - 1) * 100
        print(f"    interpretation: heavy routes had {rebound_pct:+.1f}% "
              f"relative count change post-cliff\n")
        did_rows.append({"species": label, "response": resp, **r})

    # -------------------------------------------------------------------
    pd.DataFrame(fd_rows ).to_csv(OUT_DIR / "model_results_first_diff.csv",   index=False)
    pd.DataFrame(ps_rows ).to_csv(OUT_DIR / "model_results_pyr_share.csv",    index=False)
    pd.DataFrame(did_rows).to_csv(OUT_DIR / "model_results_did_chlorpyrifos.csv", index=False)
    print(f"Saved 3 result CSVs to {OUT_DIR}\n")
    print("Done.")


if __name__ == "__main__":
    main()
