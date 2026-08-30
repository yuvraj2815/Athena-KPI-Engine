"""Driver -> Controllable Lever -> Action -> Expected Impact -> Owner ->
Confidence -> Monitoring Plan. An insight without an owner or a monitoring
plan is treated as incomplete — Athena ends in a decision, not an
observation. Rule-based; no LLM involvement."""
from dataclasses import dataclass


@dataclass
class Recommendation:
    driver: str
    lever: str
    action: str
    expected_impact: str
    owner: str
    confidence_pct: float
    monitoring_plan: str


def build_recommendations(contract, driver_breakdown, confidence_pct, min_dollar_impact=5000):
    """Generates one recommendation per driver whose dollar contribution is
    both negative (a headwind worth acting on) and material in isolation."""
    rules = {r["driver"]: r for r in contract["recommendation_rules"]}
    effects = {
        "mix": driver_breakdown.mix_effect,
        "price": driver_breakdown.price_effect,
        "volume": driver_breakdown.volume_effect,
    }

    recs = []
    for driver, effect in sorted(effects.items(), key=lambda kv: kv[1]):
        if abs(effect) < min_dollar_impact:
            continue
        rule = rules[driver]
        direction = "headwind" if effect < 0 else "tailwind"
        impact_str = f"${abs(effect):,.0f} {direction} ({effect:+,.0f} to revenue)"
        recs.append(Recommendation(
            driver=driver,
            lever=rule["lever"],
            action=rule["action"],
            expected_impact=impact_str,
            owner=rule["owner"],
            confidence_pct=confidence_pct,
            monitoring_plan=rule["monitoring"],
        ))
    return recs
