"""
Automated tests for the Athena engine. Run: pytest tests/

Covers the properties that actually matter for trust: the PVM bridge must
reconcile exactly, the materiality bar must be a real dual-bar check, security
filtering must actually remove rows and PII, and abstention must actually
trigger rather than being a decorative code path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from athena import contract as contract_mod
from athena.pipeline import run_pipeline
from athena import sources


@pytest.fixture(scope="module")
def contract():
    return contract_mod.load_contract()


@pytest.fixture(scope="module")
def sales_df():
    return sources.load_sales()


def test_contract_loads_and_validates(contract):
    assert "total_revenue" in contract["kpis"]
    assert contract["kpis"]["total_revenue"]["materiality"]["statistical"]["z_threshold"] == 1.75


def test_unknown_kpi_raises(contract):
    with pytest.raises(contract_mod.ContractError):
        contract_mod.get_kpi(contract, "not_a_real_kpi")


def test_pvm_reconciles_exactly():
    """The core trust invariant: price + volume + mix must sum exactly to the
    observed revenue delta. This is what 'math before chat' actually means."""
    r = run_pipeline(persona_name="analyst", region="West")
    d = r.driver_breakdown
    total_effects = d["price_effect"] + d["volume_effect"] + d["mix_effect"]
    assert abs(total_effects - d["delta"]) < 0.01
    assert d["unexplained_pct"] == 0.0


def test_flagship_scenario_is_flagged_material():
    r = run_pipeline(persona_name="analyst", region="West")
    assert r.materiality["is_material"] is True
    assert r.materiality["statistical_bar_cleared"] is True
    assert r.materiality["business_bar_cleared"] is True


def test_flagship_scenario_hedges_on_stale_source():
    r = run_pipeline(persona_name="analyst", region="West")
    assert r.confidence["verdict"] == "HEDGE"
    assert any("stale" in reason.lower() for reason in r.confidence["reasons"])


def test_abstention_triggers_on_simulated_outage():
    r = run_pipeline(persona_name="analyst", region="West", simulate_data_quality_issue="mix")
    assert r.confidence["verdict"] == "ABSTAIN"
    assert r.driver_breakdown["unexplained_pct"] > 0.5


def test_sparse_history_hedges_at_low_confidence():
    r = run_pipeline(persona_name="analyst", region="West", sparse_history_override=3)
    assert r.confidence["verdict"] == "HEDGE"
    assert r.confidence["confidence_pct"] <= 30


def test_security_blocks_out_of_region_rows_for_regional_persona():
    cfo = run_pipeline(persona_name="cfo", region="West")
    mgr = run_pipeline(persona_name="west_manager", region="West")
    assert cfo.security_report["rows_blocked"] == 0
    assert mgr.security_report["rows_blocked"] > 0
    assert mgr.security_report["rows_after"] < cfo.security_report["rows_after"]


def test_security_drops_pii_column_for_every_persona():
    for persona in ["cfo", "west_manager", "analyst"]:
        r = run_pipeline(persona_name=persona, region="West")
        assert "customer_email" in r.security_report["pii_columns_dropped"]


def test_personas_produce_distinct_narratives():
    cfo = run_pipeline(persona_name="cfo", region="West")
    mgr = run_pipeline(persona_name="west_manager", region="West")
    analyst = run_pipeline(persona_name="analyst", region="West")
    assert len({cfo.narrative, mgr.narrative, analyst.narrative}) == 3


def test_narrative_fallback_used_with_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = run_pipeline(persona_name="analyst", region="West")
    assert r.narrative_engine.startswith("template_fallback")
    assert r.telemetry["llm_calls"] == 0
    assert r.telemetry["cost_usd"] == 0.0


def test_telemetry_is_recorded_for_every_stage():
    r = run_pipeline(persona_name="analyst", region="West")
    expected_stages = {"load_contract", "load_sources", "freshness_check", "security",
                        "detection", "drivers", "abstention", "recommend", "narrative"}
    assert expected_stages.issubset(set(r.telemetry["stage_ms"].keys()))
    assert r.telemetry["total_ms"] > 0
