"""Price-Volume-Mix decomposition. Pure arithmetic — the LLM never computes
this. Mix is defined as the residual after price and volume effects are
removed, which guarantees the three components reconcile exactly to the
observed revenue delta (0% unexplained), unless a component is deliberately
withheld to simulate a real-world data quality issue (see
simulate_data_quality_issue in pipeline.py)."""
from dataclasses import dataclass, field


@dataclass
class DriverBreakdown:
    region: str
    current_week: str
    previous_week: str
    revenue_current: float
    revenue_previous: float
    delta: float
    price_effect: float
    volume_effect: float
    mix_effect: float
    unexplained: float
    unexplained_pct: float
    per_sku: dict = field(default_factory=dict)


def decompose_pvm(df, region, current_week, previous_week, drop_component=None):
    """drop_component: if set to 'price', 'volume', or 'mix', that component's
    contribution is withheld from the reconciliation (its value is still
    computed and reported, but excluded from what "explains" the delta) —
    used only to simulate a genuine data-source outage for the abstention
    scenario. Never used in normal operation."""
    scoped = df[df["region"] == region].copy()
    scoped["week"] = scoped["txn_date"].dt.to_period("W-MON")

    cur = scoped[scoped["week"] == current_week].groupby("sku").agg(qty=("quantity", "sum"), rev=("revenue", "sum"))
    prev = scoped[scoped["week"] == previous_week].groupby("sku").agg(qty=("quantity", "sum"), rev=("revenue", "sum"))

    all_skus = sorted(set(cur.index) | set(prev.index))
    cur = cur.reindex(all_skus, fill_value=0)
    prev = prev.reindex(all_skus, fill_value=0)

    cur["price"] = (cur["rev"] / cur["qty"]).replace([float("inf")], 0).fillna(0)
    prev["price"] = (prev["rev"] / prev["qty"]).replace([float("inf")], 0).fillna(0)

    R0, R1 = float(prev["rev"].sum()), float(cur["rev"].sum())
    Q0, Q1 = float(prev["qty"].sum()), float(cur["qty"].sum())
    avg_price0 = R0 / Q0 if Q0 else 0.0

    price_effect = float(((cur["price"] - prev["price"]) * cur["qty"]).sum())
    volume_effect = float((Q1 - Q0) * avg_price0)
    delta = R1 - R0
    mix_effect = delta - price_effect - volume_effect

    per_sku = {}
    for sku in all_skus:
        per_sku[sku] = {
            "qty_prev": float(prev.loc[sku, "qty"]), "qty_curr": float(cur.loc[sku, "qty"]),
            "price_prev": float(prev.loc[sku, "price"]), "price_curr": float(cur.loc[sku, "price"]),
            "rev_prev": float(prev.loc[sku, "rev"]), "rev_curr": float(cur.loc[sku, "rev"]),
        }

    unexplained = 0.0
    effects = {"price": price_effect, "volume": volume_effect, "mix": mix_effect}
    if drop_component and drop_component in effects:
        unexplained = effects[drop_component]
        effects[drop_component] = 0.0  # withheld — simulates a source outage

    unexplained_pct = abs(unexplained) / abs(delta) if delta else 0.0

    return DriverBreakdown(
        region=region, current_week=str(current_week), previous_week=str(previous_week),
        revenue_current=R1, revenue_previous=R0, delta=delta,
        price_effect=effects["price"], volume_effect=effects["volume"], mix_effect=effects["mix"],
        unexplained=unexplained, unexplained_pct=unexplained_pct, per_sku=per_sku,
    )
