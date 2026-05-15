"""
level1_model.py — Level 1 mixed-effects models: pesticide exposure vs.
aerial insectivore abundance at California BBS routes, 2015–2022.

Response: log(count + 1) for focal species/groups
Primary predictors: pyrethroid and organophosphate aquatic toxicity units
                    at 5 km buffer, 90-day pre-survey lag
Random effect: route (intercept)
Fixed effects: year (factor), standardized exposure variables

Two model families:
  A. Full mixed-effects model (route random intercept + year fixed effect)
     Estimates cross-sectional + temporal exposure associations jointly.
  B. Within-route (demeaned) model
     Removes between-route variation entirely; tests whether a route's
     count is lower in years when its own exposure is higher than average.
     This is the cleaner causal test — it is not confounded by habitat
     quality differences between routes.

Outputs:
  outputs/model_results_primary.csv       — main model coefficients
  outputs/model_results_sensitivity.csv   — lag × buffer sensitivity grid
  outputs/model_results_within_route.csv  — within-route demeaned models
  outputs/model_diagnostics.txt           — fit stats and data summary
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.regression.linear_model import OLS
import statsmodels.api as sm
from scipy import stats

warnings.filterwarnings("ignore")

OUT_DIR = Path(__file__).parent / "outputs"
DATA_PATH = OUT_DIR / "level1_model_input.csv"

FOCAL_SPECIES = {
    "cnt_barn_swallow":    "Barn Swallow",
    "cnt_cliff_swallow":   "Cliff Swallow",
    "cnt_tree_swallow":    "Tree Swallow",
    "cnt_western_kingbird": "Western Kingbird",
    "cnt_swallows_total":  "All Swallows",
}

BUFFERS = [500, 1000, 2000, 5000]
LAGS    = [30, 60, 90]
PRIMARY_BUFFER = 5000
PRIMARY_LAG    = 90


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df = df[df["cnt_aerial_insectivores_total"].notna()].copy()

    df["route_id"] = df["location_id"].str.rsplit("_", n=1).str[0]
    df["year"]     = df["location_id"].str.split("_").str[-1].astype(int)
    df["year_fac"] = df["year"].astype(str)
    df["year_ctr"] = df["year"] - 2018  # center at midpoint

    for col in [c for c in df.columns if c.startswith("cnt_")]:
        df[f"log1p_{col}"] = np.log1p(df[col].fillna(0))

    return df


def exposure_col(class_name: str, buffer: int, lag: int, metric: str) -> str:
    return f"{class_name}_{buffer}m_{lag}d_{metric}"


def standardize(series: pd.Series):
    mu, sd = series.mean(), series.std()
    if sd == 0:
        return series * 0, mu, 1.0
    return (series - mu) / sd, mu, sd


def compute_aic(fit, n_params: int) -> float:
    """Compute AIC from log-likelihood (works even when fit.aic returns NaN)."""
    try:
        llf = fit.llf
        if np.isfinite(llf):
            return -2 * llf + 2 * n_params
    except Exception:
        pass
    return np.nan


def n_params_mixedlm(fit) -> int:
    """Count free parameters in a MixedLM fit."""
    return len(fit.params) + 1  # +1 for the random-effect variance


def _sig(p):
    if p is None or not np.isfinite(p): return "  "
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    if p < 0.1:   return "."
    return "ns"


def fit_mixedlm(df: pd.DataFrame, response_col: str, pyr_col: str, op_col: str,
                route_col: str = "route_id") -> dict | None:
    """Fit LMM: log1p(response) ~ pyr_z + op_z + C(year) + (1|route)"""
    log_col = f"log1p_{response_col}"
    tmp = df[[log_col, pyr_col, op_col, "year_fac", route_col]].dropna()
    if len(tmp) < 20:
        return None

    tmp = tmp.copy()
    tmp["pyr_z"], pyr_mu, pyr_sd = standardize(tmp[pyr_col])
    tmp["op_z"],  op_mu,  op_sd  = standardize(tmp[op_col])

    try:
        md  = smf.mixedlm(f"{log_col} ~ pyr_z + op_z + C(year_fac)",
                          data=tmp, groups=tmp[route_col])
        fit = md.fit(method="lbfgs", maxiter=1000, disp=False)
    except Exception as e:
        return {"error": str(e)}

    def _coef(key):
        idx = fit.params.index
        if key not in idx: return (None,) * 5
        b = fit.params[key]; se = fit.bse[key]; p = fit.pvalues[key]
        return b, se, p, b - 1.96*se, b + 1.96*se

    pyr = _coef("pyr_z")
    op  = _coef("op_z")
    aic = compute_aic(fit, n_params_mixedlm(fit))

    return {
        "n_obs": len(tmp), "n_routes": tmp[route_col].nunique(), "aic": aic,
        "pyr_beta": pyr[0], "pyr_se": pyr[1], "pyr_p": pyr[2],
        "pyr_ci_lo": pyr[3], "pyr_ci_hi": pyr[4],
        "pyr_mu": pyr_mu, "pyr_sd": pyr_sd,
        "op_beta": op[0], "op_se": op[1], "op_p": op[2],
        "op_ci_lo": op[3], "op_ci_hi": op[4],
        "op_mu": op_mu, "op_sd": op_sd,
    }


def fit_within_route(df: pd.DataFrame, response_col: str, pyr_col: str,
                     op_col: str) -> dict | None:
    """
    Within-route demeaned OLS.

    Subtracts each route's mean from log-count and from exposure, then
    fits OLS with no intercept. This is a standard within-estimator
    (equivalent to route fixed effects). Standard errors are
    heteroskedasticity-robust (HC3).

    Causal interpretation: β < 0 means that a route's count is lower in
    years when that route's own pyrethroid exposure is above its average.
    This cannot be confounded by stable differences in habitat quality
    across routes.
    """
    log_col = f"log1p_{response_col}"
    tmp = df[[log_col, pyr_col, op_col, "route_id", "year_ctr"]].dropna().copy()
    if len(tmp) < 20:
        return None

    # Demean within route
    for col in [log_col, pyr_col, op_col]:
        tmp[f"{col}_dm"] = tmp[col] - tmp.groupby("route_id")[col].transform("mean")

    # Standardize demeaned exposure (for interpretable betas)
    tmp["pyr_dm_z"], pyr_mu_dm, pyr_sd_dm = standardize(tmp[f"{pyr_col}_dm"])
    tmp["op_dm_z"],  op_mu_dm,  op_sd_dm  = standardize(tmp[f"{op_col}_dm"])

    X = sm.add_constant(tmp[["pyr_dm_z", "op_dm_z", "year_ctr"]])
    y = tmp[f"{log_col}_dm"]

    try:
        res = OLS(y, X).fit(cov_type="HC3")
    except Exception as e:
        return {"error": str(e)}

    def _coef_ols(key):
        if key not in res.params.index: return (None,) * 5
        b = res.params[key]; se = res.bse[key]; p = res.pvalues[key]
        return b, se, p, b - 1.96*se, b + 1.96*se

    pyr = _coef_ols("pyr_dm_z")
    op  = _coef_ols("op_dm_z")
    yr  = _coef_ols("year_ctr")

    return {
        "n_obs": len(tmp), "n_routes": tmp["route_id"].nunique(),
        "r2_within": res.rsquared,
        "pyr_beta": pyr[0], "pyr_se": pyr[1], "pyr_p": pyr[2],
        "pyr_ci_lo": pyr[3], "pyr_ci_hi": pyr[4],
        "op_beta": op[0],  "op_se": op[1],  "op_p": op[2],
        "op_ci_lo": op[3], "op_ci_hi": op[4],
        "yr_beta": yr[0], "yr_p": yr[2],
    }


def main():
    print("=== Level 1 Models: Pesticide Exposure × Aerial Insectivore Abundance ===\n")

    df = load_data()
    print(f"Data: {len(df)} surveyed route-years | "
          f"{df['route_id'].nunique()} routes | "
          f"years {sorted(df['year'].unique())}\n")

    pyr_col = exposure_col("Pyrethroids",      PRIMARY_BUFFER, PRIMARY_LAG, "tox_units_aquatic")
    op_col  = exposure_col("Organophosphates", PRIMARY_BUFFER, PRIMARY_LAG, "tox_units_aquatic")
    pyr_op_corr = df[[pyr_col, op_col]].corr().iloc[0, 1]
    print(f"Exposure (5 km / 90-day):  pyr mean={df[pyr_col].mean():.1f}  "
          f"op mean={df[op_col].mean():.1f}  pyr×op r={pyr_op_corr:.3f}\n")

    # -----------------------------------------------------------------------
    # Model A — Mixed-effects (cross-sectional + temporal)
    # -----------------------------------------------------------------------
    print("═" * 70)
    print("MODEL A  Mixed-effects LMM: log(count+1) ~ pyr_z + op_z + C(year)")
    print("         Random intercept per route  |  5 km / 90-day exposure")
    print("         Positive β = more birds where more pesticide (habitat confound)")
    print("         Negative β = more pesticide → fewer birds\n")

    primary_rows = []
    for resp_col, label in FOCAL_SPECIES.items():
        if resp_col not in df.columns:
            continue
        res = fit_mixedlm(df, resp_col, pyr_col, op_col)
        if not res or "error" in res:
            print(f"  {label}: FAILED")
            continue

        primary_rows.append({"species": label, "response": resp_col, **res})
        aic_str = f"{res['aic']:.1f}" if np.isfinite(res.get("aic", np.nan)) else "—"
        print(f"  {label}  (n={res['n_obs']}, routes={res['n_routes']}, AIC={aic_str})")
        b, se, p = res["pyr_beta"], res["pyr_se"], res["pyr_p"]
        lo, hi   = res["pyr_ci_lo"], res["pyr_ci_hi"]
        print(f"    Pyrethroid  β={b:+.3f} [{lo:+.3f}, {hi:+.3f}]  "
              f"SE={se:.3f}  p={p:.4f} {_sig(p)}")
        b, se, p = res["op_beta"], res["op_se"], res["op_p"]
        lo, hi   = res["op_ci_lo"], res["op_ci_hi"]
        print(f"    Organophos  β={b:+.3f} [{lo:+.3f}, {hi:+.3f}]  "
              f"SE={se:.3f}  p={p:.4f} {_sig(p)}")
        print()

    # Year fixed effects from the all-swallows model
    print("  Year fixed effects — All Swallows model (ref = 2015):")
    tmp_sw = df[["log1p_cnt_swallows_total", pyr_col, op_col,
                 "year_fac", "route_id"]].dropna().copy()
    tmp_sw["pyr_z"], *_ = standardize(tmp_sw[pyr_col])
    tmp_sw["op_z"],  *_ = standardize(tmp_sw[op_col])
    md = smf.mixedlm("log1p_cnt_swallows_total ~ pyr_z + op_z + C(year_fac)",
                     data=tmp_sw, groups=tmp_sw["route_id"])
    fit_sw = md.fit(method="lbfgs", maxiter=1000, disp=False)
    for nm in fit_sw.params.index:
        if "year_fac" in str(nm):
            yr  = str(nm).replace("C(year_fac)[T.", "").replace("]", "")
            b   = fit_sw.params[nm]
            se  = fit_sw.bse[nm]
            p   = fit_sw.pvalues[nm]
            pct = (np.exp(b) - 1) * 100
            print(f"    {yr}: β={b:+.3f}  SE={se:.3f}  p={p:.4f} {_sig(p)}"
                  f"  ({pct:+.0f}% vs 2015)")
    print()

    # -----------------------------------------------------------------------
    # Model B — Within-route demeaned (causal estimator)
    # -----------------------------------------------------------------------
    print("═" * 70)
    print("MODEL B  Within-route demeaned OLS (HC3 SEs): isolates temporal signal")
    print("         β tests: does a route have fewer birds in its high-exposure years?")
    print("         Removes stable habitat-quality differences between routes.\n")

    within_rows = []
    for resp_col, label in FOCAL_SPECIES.items():
        if resp_col not in df.columns:
            continue
        res = fit_within_route(df, resp_col, pyr_col, op_col)
        if not res or "error" in res:
            print(f"  {label}: FAILED")
            continue

        within_rows.append({"species": label, "response": resp_col, **res})
        r2 = res.get("r2_within", np.nan)
        print(f"  {label}  (n={res['n_obs']}, routes={res['n_routes']}, "
              f"R²_within={r2:.3f})")
        b, se, p = res["pyr_beta"], res["pyr_se"], res["pyr_p"]
        lo, hi   = res["pyr_ci_lo"], res["pyr_ci_hi"]
        print(f"    Pyrethroid  β={b:+.3f} [{lo:+.3f}, {hi:+.3f}]  "
              f"SE={se:.3f}  p={p:.4f} {_sig(p)}")
        b, se, p = res["op_beta"], res["op_se"], res["op_p"]
        lo, hi   = res["op_ci_lo"], res["op_ci_hi"]
        print(f"    Organophos  β={b:+.3f} [{lo:+.3f}, {hi:+.3f}]  "
              f"SE={se:.3f}  p={p:.4f} {_sig(p)}")
        if res.get("yr_beta") is not None:
            print(f"    Year trend  β={res['yr_beta']:+.3f}  p={res['yr_p']:.4f} {_sig(res['yr_p'])}")
        print()

    # -----------------------------------------------------------------------
    # Sensitivity: All Swallows across buffer × lag (within-route model)
    # -----------------------------------------------------------------------
    print("═" * 70)
    print("SENSITIVITY  Within-route pyrethroid β — All Swallows")
    print(f"{'Buffer':>8} | " + " | ".join(f"Lag {l}d  β (p)" for l in LAGS))
    print("-" * 72)

    sens_rows = []
    for buf in BUFFERS:
        parts = []
        for lag in LAGS:
            pc = exposure_col("Pyrethroids",      buf, lag, "tox_units_aquatic")
            oc = exposure_col("Organophosphates", buf, lag, "tox_units_aquatic")
            if pc not in df.columns:
                parts.append("  n/a       "); continue
            r = fit_within_route(df, "cnt_swallows_total", pc, oc)
            if r and "pyr_beta" in r and r["pyr_beta"] is not None:
                b = r["pyr_beta"]; p = r["pyr_p"]
                parts.append(f"{b:+.3f}{_sig(p):3s} (p={p:.3f})")
                sens_rows.append({"buffer_m": buf, "lag_d": lag,
                                  "pyr_beta": b, "pyr_p": p,
                                  "op_beta": r["op_beta"], "op_p": r["op_p"]})
            else:
                parts.append("  FAIL      ")
        print(f"  {buf:>5}m | " + " | ".join(parts))
    print()

    # -----------------------------------------------------------------------
    # Effect-size interpretation (within-route primary model)
    # -----------------------------------------------------------------------
    print("═" * 70)
    wr_sw = [r for r in within_rows if r["response"] == "cnt_swallows_total"]
    if wr_sw:
        r = wr_sw[0]
        b = r["pyr_beta"]
        # SD of the demeaned pyrethroid variable
        tmp_sw2 = df[[pyr_col, "route_id"]].dropna().copy()
        tmp_sw2["pyr_dm"] = tmp_sw2[pyr_col] - tmp_sw2.groupby("route_id")[pyr_col].transform("mean")
        sd_dm = tmp_sw2["pyr_dm"].std()
        p10_dm = tmp_sw2["pyr_dm"].quantile(0.10)
        p90_dm = tmp_sw2["pyr_dm"].quantile(0.90)
        z_diff = (p90_dm - p10_dm) / sd_dm
        log_diff = b * z_diff
        pct_diff = (np.exp(log_diff) - 1) * 100

        print("EFFECT SIZE — Within-route pyrethroid, All Swallows\n")
        print(f"  Demeaned pyr 10th–90th pctile range: {p10_dm:.1f} – {p90_dm:.1f} tox units")
        print(f"  Standardized range: {z_diff:.2f} SD (within-route variation)")
        print(f"  Predicted log-count change (p10→p90): {log_diff:+.3f}")
        print(f"  Predicted % change in swallow count:  {pct_diff:+.1f}%")
        print(f"  (negative = fewer birds in high-exposure years within same route)\n")

    # -----------------------------------------------------------------------
    # Save outputs
    # -----------------------------------------------------------------------
    pd.DataFrame(primary_rows).to_csv(OUT_DIR / "model_results_primary.csv",      index=False)
    pd.DataFrame(within_rows ).to_csv(OUT_DIR / "model_results_within_route.csv", index=False)
    pd.DataFrame(sens_rows   ).to_csv(OUT_DIR / "model_results_sensitivity.csv",  index=False)

    # Diagnostics text
    diag = [
        "=== Level 1 Model Diagnostics ===\n",
        f"Data: {len(df)} surveyed route-years, {df['route_id'].nunique()} routes",
        f"Years: {sorted(df['year'].unique())}",
        f"Primary exposure: 5 km / 90-day lag / aquatic tox units\n",
        f"Pyr: mean={df[pyr_col].mean():.1f}  SD={df[pyr_col].std():.1f}"
        f"  min={df[pyr_col].min():.1f}  max={df[pyr_col].max():.1f}",
        f"OP:  mean={df[op_col].mean():.1f}  SD={df[op_col].std():.1f}"
        f"  min={df[op_col].min():.1f}  max={df[op_col].max():.1f}",
        f"Pyr × OP Pearson r: {pyr_op_corr:.3f}\n",
        "Model A (mixed-effects) — All Swallows:",
    ]
    sw_a = [r for r in primary_rows if r["response"] == "cnt_swallows_total"]
    if sw_a:
        r = sw_a[0]
        diag += [f"  pyr β={r['pyr_beta']:+.4f}  p={r['pyr_p']:.4f}",
                 f"  op  β={r['op_beta']:+.4f}  p={r['op_p']:.4f}"]
    diag.append("Model B (within-route) — All Swallows:")
    if wr_sw:
        r = wr_sw[0]
        diag += [f"  pyr β={r['pyr_beta']:+.4f}  p={r['pyr_p']:.4f}",
                 f"  op  β={r['op_beta']:+.4f}  p={r['op_p']:.4f}"]
    (OUT_DIR / "model_diagnostics.txt").write_text("\n".join(diag))

    print(f"Saved: model_results_primary.csv, model_results_within_route.csv,")
    print(f"       model_results_sensitivity.csv, model_diagnostics.txt\n")
    print("Done.")


if __name__ == "__main__":
    main()
