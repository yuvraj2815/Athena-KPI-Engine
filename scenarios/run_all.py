"""Scenario runner: exercises all six minimum-expectation scenarios from the
Round 2 brief and prints a pass/fail summary. Each scenario asserts a
specific, checkable property of the pipeline's real output — nothing here is
narrated after the fact; if an assertion fails, the script says so.

Run: python -m scenarios.run_all
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from athena.pipeline import run_pipeline


PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, condition, detail):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    print(f"[{status}] {name} — {detail}")


def scenario_1_multi_factor():
    r = run_pipeline(persona_name="analyst", region="West")
    ok = (
        r.confidence["verdict"] == "HEDGE"
        and r.driver_breakdown is not None
        and r.driver_breakdown["unexplained_pct"] == 0.0
        and len(r.recommendations) >= 2
    )
    check(
        "S1 Multi-Factor Movement",
        ok,
        f"verdict={r.confidence['verdict']} @ {r.confidence['confidence_pct']:.0f}%, "
        f"mix={r.driver_breakdown['mix_effect']:+,.0f} price={r.driver_breakdown['price_effect']:+,.0f} "
        f"volume={r.driver_breakdown['volume_effect']:+,.0f}, unexplained={r.driver_breakdown['unexplained_pct']:.0%}, "
        f"{len(r.recommendations)} recommendation(s)",
    )


def scenario_2_personas():
    cfo = run_pipeline(persona_name="cfo", region="West")
    mgr = run_pipeline(persona_name="west_manager", region="West")
    analyst = run_pipeline(persona_name="analyst", region="West")
    narratives = {cfo.narrative, mgr.narrative, analyst.narrative}
    ok = len(narratives) == 3
    check(
        "S2 Persona Differentiation",
        ok,
        f"{len(narratives)} distinct narratives generated from one evidence bundle (CFO/Manager/Analyst)",
    )


def scenario_3_security():
    cfo = run_pipeline(persona_name="cfo", region="West")
    mgr = run_pipeline(persona_name="west_manager", region="West")
    ok = (
        cfo.security_report["rows_after"] == cfo.security_report["rows_before"]
        and mgr.security_report["rows_after"] < mgr.security_report["rows_before"]
        and "customer_email" in cfo.security_report["pii_columns_dropped"]
        and "customer_email" in mgr.security_report["pii_columns_dropped"]
    )
    check(
        "S3 Role-Based Security",
        ok,
        f"CFO sees {cfo.security_report['rows_after']:,} rows; West Manager sees "
        f"{mgr.security_report['rows_after']:,} of {mgr.security_report['rows_before']:,} "
        f"(blocked {mgr.security_report['rows_blocked']:,}); PII dropped for both",
    )


def scenario_4_staleness():
    r = run_pipeline(persona_name="analyst", region="West")
    ok = any("stale" in reason.lower() for reason in r.confidence["reasons"])
    check(
        "S4 Source Staleness",
        ok,
        f"stale source correctly named in confidence reasoning: {r.confidence['reasons']}",
    )


def scenario_5_abstention():
    r = run_pipeline(persona_name="analyst", region="West", simulate_data_quality_issue="mix")
    ok = r.confidence["verdict"] == "ABSTAIN" and r.driver_breakdown["unexplained_pct"] > 0.5
    check(
        "S5 Low-Confidence Abstention",
        ok,
        f"verdict={r.confidence['verdict']}, unexplained={r.driver_breakdown['unexplained_pct']:.0%} "
        f"(simulated outage on the 'mix' driver)",
    )


def scenario_6_sparse_history():
    r = run_pipeline(persona_name="analyst", region="West", sparse_history_override=3)
    ok = r.confidence["verdict"] == "HEDGE" and r.confidence["confidence_pct"] <= 30
    check(
        "S6 Sparse-History Product",
        ok,
        f"verdict={r.confidence['verdict']} @ {r.confidence['confidence_pct']:.0f}% confidence "
        f"with only 3 weeks of simulated history",
    )


def main():
    print("Running all six required scenarios against the live pipeline...\n")
    scenario_1_multi_factor()
    scenario_2_personas()
    scenario_3_security()
    scenario_4_staleness()
    scenario_5_abstention()
    scenario_6_sparse_history()

    print()
    n_pass = sum(1 for _, s, _ in results if s == PASS)
    print(f"{n_pass}/{len(results)} scenarios passed.")
    if n_pass != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
