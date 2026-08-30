"""Detection: is a KPI movement real, or just normal weekly noise?

Applies dual-bar materiality — a movement must clear BOTH a statistical bar
(MAD-based robust z-score against trailing baseline weeks) AND a business bar
(minimum percentage and dollar impact) before it is surfaced as material.
This is deterministic arithmetic; the LLM never sees raw rows."""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class MaterialityResult:
    region: str
    current_week: str
    current_week_revenue: float
    baseline_mean: float
    baseline_weeks_used: int
    pct_change: float
    dollar_change: float
    robust_std: float
    z_score: float
    statistical_bar_cleared: bool
    business_bar_cleared: bool
    is_material: bool


def weekly_revenue(df, region, period_convention="W-MON"):
    scoped = df[df["region"] == region].copy()
    scoped["week"] = scoped["txn_date"].dt.to_period(period_convention)
    return scoped.groupby("week")["revenue"].sum().sort_index()


def robust_z_score(current_value, baseline_values):
    baseline_values = np.asarray(baseline_values, dtype=float)
    median = np.median(baseline_values)
    mad = np.median(np.abs(baseline_values - median))
    robust_std = mad * 1.4826  # consistency constant for normal distribution
    if robust_std == 0:
        return 0.0, robust_std
    z = (current_value - baseline_values.mean()) / robust_std
    return z, robust_std


def check_materiality(df, region, kpi_def, as_of_week=None, region_all_history=None):
    """region_all_history lets the caller pass an unfiltered (pre-security)
    revenue series so materiality is always computed on the true history,
    even when the persona's own view is row-restricted."""
    period_convention = kpi_def.get("period_convention", "W-MON")
    series = region_all_history if region_all_history is not None else weekly_revenue(df, region, period_convention)

    if as_of_week is None:
        as_of_week = series.index.max()

    baseline_weeks = kpi_def["materiality"]["statistical"]["baseline_weeks"]
    history_before_current = series[series.index < as_of_week]
    baseline = history_before_current.tail(baseline_weeks)

    current_value = float(series.loc[as_of_week])
    baseline_mean = float(baseline.mean()) if len(baseline) else float("nan")
    pct_change = (current_value - baseline_mean) / baseline_mean if baseline_mean else float("nan")
    dollar_change = current_value - baseline_mean

    z, robust_std = robust_z_score(current_value, baseline.values) if len(baseline) >= 2 else (0.0, 0.0)

    z_threshold = kpi_def["materiality"]["statistical"]["z_threshold"]
    min_pct = kpi_def["materiality"]["business"]["min_pct_change"]
    min_dollar = kpi_def["materiality"]["business"]["min_dollar_impact"]

    statistical_bar_cleared = abs(z) >= z_threshold
    business_bar_cleared = (abs(pct_change) >= min_pct) and (abs(dollar_change) >= min_dollar)

    return MaterialityResult(
        region=region,
        current_week=str(as_of_week),
        current_week_revenue=current_value,
        baseline_mean=baseline_mean,
        baseline_weeks_used=len(baseline),
        pct_change=pct_change,
        dollar_change=dollar_change,
        robust_std=robust_std,
        z_score=z,
        statistical_bar_cleared=statistical_bar_cleared,
        business_bar_cleared=business_bar_cleared,
        is_material=statistical_bar_cleared and business_bar_cleared,
    )
