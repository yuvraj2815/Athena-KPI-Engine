"""Confidence calibration and abstention. The verdict — ANSWER / HEDGE /
CLARIFY / ABSTAIN — and the confidence score are both the output of
documented rules operating on real signals (staleness, residual, history
depth, bar agreement), never the LLM's self-reported certainty."""
from dataclasses import dataclass, field


@dataclass
class ConfidenceResult:
    verdict: str
    confidence_pct: float
    reasons: list = field(default_factory=list)


def score_confidence(
    contract,
    kpi_def,
    materiality_result,
    driver_breakdown,
    stale_sources: list,
    history_weeks_available: int,
):
    rubric = kpi_def["confidence_rubric"]
    thresholds = rubric["thresholds"]
    reasons = []

    # --- Hard rule: insufficient history -> sparse-history HEDGE, not a normal score walk ---
    if history_weeks_available < thresholds["min_history_weeks"]:
        confidence = max(0, rubric["base"] - rubric["penalties"]["sparse_history_weeks"])
        reasons.append(
            f"Only {history_weeks_available} week(s) of history available "
            f"(minimum {thresholds['min_history_weeks']}) — insufficient baseline for a confident read."
        )
        return ConfidenceResult(verdict="HEDGE", confidence_pct=confidence, reasons=reasons)

    # --- Hard rule: unexplained residual too high -> ABSTAIN ---
    if driver_breakdown is not None and driver_breakdown.unexplained_pct > thresholds["abstain_residual_pct"]:
        reasons.append(
            f"{driver_breakdown.unexplained_pct:.0%} of the movement is unexplained by the three "
            f"tracked drivers (threshold {thresholds['abstain_residual_pct']:.0%}) — likely a data "
            f"quality issue in an upstream source. Withholding a confident explanation."
        )
        return ConfidenceResult(verdict="ABSTAIN", confidence_pct=min(20, rubric["base"] - 70), reasons=reasons)

    # --- Hard rule: statistical and business bars disagree -> CLARIFY ---
    if materiality_result is not None and (
        materiality_result.statistical_bar_cleared != materiality_result.business_bar_cleared
    ):
        reasons.append(
            "Statistical significance and business-impact materiality disagree on this movement "
            "— evidence is contradictory rather than simply weak."
        )
        return ConfidenceResult(verdict="CLARIFY", confidence_pct=50, reasons=reasons)

    # --- Normal path: start from base, apply documented penalties ---
    confidence = rubric["base"]
    if stale_sources:
        confidence -= rubric["penalties"]["stale_critical_source"]
        reasons.append(
            f"Source(s) flagged stale at analysis time: {', '.join(stale_sources)} — "
            f"confidence downgraded accordingly."
        )

    verdict = "ANSWER" if confidence >= 85 and not stale_sources else "HEDGE"
    if verdict == "HEDGE" and not stale_sources:
        reasons.append("Confidence below the ANSWER threshold; hedging rather than overstating certainty.")

    return ConfidenceResult(verdict=verdict, confidence_pct=confidence, reasons=reasons)
