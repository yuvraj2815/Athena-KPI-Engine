"""The orchestrator. Wires Detect -> Decompose -> Explain -> Recommend
together for a given region/week/persona, enforcing security before any
analysis runs, and returning a single structured result plus full telemetry."""
from dataclasses import dataclass, asdict

import pandas as pd

from athena import contract as contract_mod
from athena import sources
from athena import security
from athena import detection
from athena import drivers as drivers_mod
from athena import abstention
from athena import recommend
from athena import personas as personas_mod
from athena import narrative as narrative_mod
from athena.telemetry import Telemetry


@dataclass
class PipelineResult:
    persona: str
    region_analyzed: str
    week: str
    materiality: dict
    driver_breakdown: dict
    confidence: dict
    recommendations: list
    narrative: str
    narrative_engine: str
    security_report: dict
    telemetry: dict


def run_pipeline(
    persona_name="analyst",
    region="West",
    kpi_name="total_revenue",
    as_of_week=None,
    simulate_data_quality_issue=None,   # None | "price" | "volume" | "mix"
    sparse_history_override=None,        # int | None — force a small history-weeks count for the sparse-history scenario
    contract_path=None,
    use_llm=None,
):
    tele = Telemetry()

    with tele.stage("load_contract"):
        c = contract_mod.load_contract(contract_path)
        kpi_def = contract_mod.get_kpi(c, kpi_name)

    with tele.stage("load_sources"):
        sales_df = sources.load_sales()
        manifest = sources.load_freshness_manifest()
        as_of = sales_df["txn_date"].max()

    with tele.stage("freshness_check"):
        stale_sources = []
        for source_key in ["marketing_spend"]:
            is_stale, last_updated, age_days = sources.source_is_stale(source_key, as_of, manifest)
            if is_stale:
                stale_sources.append(f"{source_key} (last updated {last_updated}, {age_days}d ago)")

    with tele.stage("security"):
        scoped_df, security_report = security.apply_security(sales_df, c, persona_name)

    with tele.stage("detection"):
        # Materiality is always computed on true, unrestricted history for the
        # target region — a persona's own row restriction must never change
        # whether a movement is judged material, only what they're allowed to see.
        full_region_series = detection.weekly_revenue(sales_df, region, kpi_def.get("period_convention", "W-MON"))
        history_weeks_available = len(full_region_series) - 1  # minus the current week itself

        if sparse_history_override is not None:
            full_region_series = full_region_series.tail(sparse_history_override + 1)
            history_weeks_available = sparse_history_override

        mat = detection.check_materiality(scoped_df, region, kpi_def, as_of_week=as_of_week,
                                           region_all_history=full_region_series)

    with tele.stage("drivers"):
        weeks_sorted = list(full_region_series.index)
        current_week = mat.current_week
        current_period = [w for w in weeks_sorted if str(w) == current_week][0]
        idx = weeks_sorted.index(current_period)
        previous_period = weeks_sorted[idx - 1] if idx > 0 else None

        drv = None
        if previous_period is not None and history_weeks_available >= 1:
            drv = drivers_mod.decompose_pvm(
                sales_df, region, current_period, previous_period,
                drop_component=simulate_data_quality_issue,
            )

    with tele.stage("abstention"):
        conf = abstention.score_confidence(
            c, kpi_def, mat, drv, stale_sources, history_weeks_available,
        )

    with tele.stage("recommend"):
        recs = []
        if drv is not None and conf.verdict in {"ANSWER", "HEDGE"}:
            recs = recommend.build_recommendations(c, drv, conf.confidence_pct)

    with tele.stage("narrative"):
        persona_view = personas_mod.get_persona_view(c, persona_name)
        bundle = narrative_mod.build_evidence_bundle(persona_view, mat, drv, conf, recs, stale_sources)
        narrative_result = narrative_mod.render_narrative(bundle, use_llm=use_llm)
        tele.record_narrative(narrative_result)

    result = PipelineResult(
        persona=persona_name,
        region_analyzed=region,
        week=mat.current_week,
        materiality=asdict(mat),
        driver_breakdown=asdict(drv) if drv else None,
        confidence={"verdict": conf.verdict, "confidence_pct": conf.confidence_pct, "reasons": conf.reasons},
        recommendations=[asdict(r) for r in recs],
        narrative=narrative_result["text"],
        narrative_engine=narrative_result["engine"],
        security_report=security_report,
        telemetry=tele.summary(),
    )
    return result


def print_result(result: PipelineResult):
    print("=" * 78)
    print(f"PERSONA: {result.persona}  |  REGION: {result.region_analyzed}  |  WEEK: {result.week}")
    print("-" * 78)
    m = result.materiality
    print(f"Detect   : {m['pct_change']*100:+.2f}% ({m['dollar_change']:+,.0f} USD) vs "
          f"{m['baseline_weeks_used']}-week baseline | z={m['z_score']:.2f} | "
          f"material={m['is_material']}")
    if result.driver_breakdown:
        d = result.driver_breakdown
        print(f"Decompose: mix={d['mix_effect']:+,.0f}  price={d['price_effect']:+,.0f}  "
              f"volume={d['volume_effect']:+,.0f}  | unexplained={d['unexplained_pct']*100:.1f}%")
    conf = result.confidence
    print(f"Explain  : verdict={conf['verdict']}  confidence={conf['confidence_pct']:.0f}%")
    for r in conf["reasons"]:
        print(f"           - {r}")
    print(f"Recommend: {len(result.recommendations)} action(s)")
    for r in result.recommendations:
        print(f"           -> [{r['driver']}] {r['action']} (Owner: {r['owner']})")
    print("-" * 78)
    print(f"Security : rows_before={result.security_report['rows_before']} "
          f"rows_after={result.security_report['rows_after']} "
          f"rows_blocked={result.security_report['rows_blocked']} "
          f"pii_dropped={result.security_report['pii_columns_dropped']}")
    t = result.telemetry
    print(f"Telemetry: total={t['total_ms']}ms  deterministic_share={t['deterministic_share_pct']}%  "
          f"llm_calls={t['llm_calls']}  cost=${t['cost_usd']}")
    print("=" * 78)
    print(result.narrative)
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="flagship",
                         choices=["flagship", "abstention", "sparse_history"],
                         help="flagship=normal run | abstention=simulate a dropped 'mix' driver "
                              "(data-source outage) | sparse_history=simulate only 3 weeks of history")
    parser.add_argument("--persona", default="analyst", choices=["analyst", "cfo", "west_manager"])
    parser.add_argument("--region", default="West")
    args = parser.parse_args()

    kwargs = {"persona_name": args.persona, "region": args.region}
    if args.scenario == "abstention":
        kwargs["simulate_data_quality_issue"] = "mix"
    elif args.scenario == "sparse_history":
        kwargs["sparse_history_override"] = 3

    res = run_pipeline(**kwargs)
    print_result(res)
