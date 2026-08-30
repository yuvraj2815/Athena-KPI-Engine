"""Narrative synthesis. This is the ONLY module allowed to touch an LLM, and
even here the LLM never sees raw transaction rows — only a pre-computed
"evidence bundle" of numbers that have already been calculated, verified, and
reconciled deterministically. If no ANTHROPIC_API_KEY is set, a deterministic
template renderer produces the full narrative output instead — the pipeline
runs correctly end-to-end at zero LLM cost either way."""
import os


def build_evidence_bundle(persona_view, materiality, drivers, confidence, recommendations, stale_sources):
    """The only thing narrative.py is allowed to see. No raw rows, ever."""
    return {
        "persona": persona_view["name"],
        "narrative_focus": persona_view["narrative_focus"],
        "detail_level": persona_view["detail_level"],
        "region": materiality.region,
        "week": materiality.current_week,
        "pct_change": round(materiality.pct_change * 100, 2),
        "dollar_change": round(materiality.dollar_change, 0),
        "z_score": round(materiality.z_score, 2),
        "verdict": confidence.verdict,
        "confidence_pct": confidence.confidence_pct,
        "confidence_reasons": confidence.reasons,
        "drivers": {
            "price_effect": round(drivers.price_effect, 0) if drivers else None,
            "volume_effect": round(drivers.volume_effect, 0) if drivers else None,
            "mix_effect": round(drivers.mix_effect, 0) if drivers else None,
            "unexplained_pct": round(drivers.unexplained_pct * 100, 1) if drivers else None,
        },
        "stale_sources": stale_sources,
        "recommendations": [
            {"driver": r.driver, "action": r.action, "owner": r.owner, "impact": r.expected_impact}
            for r in recommendations
        ],
    }


def _template_narrative(bundle):
    detail = bundle["detail_level"]
    lines = [f"[{bundle['persona'].upper()} VIEW \u2014 {bundle['narrative_focus']}]"]
    direction = "declined" if bundle["pct_change"] < 0 else "grew"

    if detail == "strategic":
        # CFO: condensed macro roll-up. Headline number + verdict + net dollar
        # exposure only — no SKU-level mechanics, no per-driver monitoring plans.
        net_headwind = sum(v for v in (bundle["drivers"].values()) if isinstance(v, (int, float)) and v is not None and v < 0)
        lines.append(
            f"{bundle['region']} revenue {direction} {abs(bundle['pct_change']):.2f}% "
            f"({bundle['dollar_change']:+,.0f} USD) this week \u2014 a {bundle['verdict']} at "
            f"{bundle['confidence_pct']:.0f}% confidence."
        )
        lines.append(
            f"Net margin exposure from identified headwinds: approximately ${abs(net_headwind):,.0f}. "
            f"Primary lever available: pricing and mix strategy in-region."
        )
        if bundle["confidence_reasons"]:
            lines.append(f"Caveat: {bundle['confidence_reasons'][0]}")
        if bundle["recommendations"]:
            top = bundle["recommendations"][0]
            lines.append(f"Top capital-allocation-relevant action: {top['action']} (Owner: {top['owner']}).")

    elif detail == "tactical":
        # Regional manager: skip the abstract statistical framing, go straight
        # to what changed and what to physically do about it this week.
        lines.append(
            f"{bundle['region']} revenue {direction} {abs(bundle['pct_change']):.2f}% "
            f"({bundle['dollar_change']:+,.0f} USD) this week. Verdict: {bundle['verdict']} "
            f"({bundle['confidence_pct']:.0f}% confidence)."
        )
        d = bundle["drivers"]
        if d["mix_effect"] is not None:
            lines.append(
                f"On the floor, this shows up as customers shifting toward cheaper models "
                f"(mix impact {d['mix_effect']:+,.0f}) and the active promo cutting into margin "
                f"(price impact {d['price_effect']:+,.0f}); unit volume is actually up "
                f"({d['volume_effect']:+,.0f})."
            )
        if bundle["recommendations"]:
            lines.append("This week's action items:")
            for r in bundle["recommendations"]:
                lines.append(f"  \u2192 {r['action']} (Owner: {r['owner']})")

    else:  # "full" — analyst view, everything
        lines.append(
            f"{bundle['region']} revenue {direction} {abs(bundle['pct_change']):.2f}% "
            f"({bundle['dollar_change']:+,.0f} USD) in the week of {bundle['week']}. z={bundle['z_score']}."
        )
        d = bundle["drivers"]
        if d["mix_effect"] is not None:
            lines.append(
                f"Driver breakdown \u2014 mix: {d['mix_effect']:+,.0f} \u00b7 price: {d['price_effect']:+,.0f} "
                f"\u00b7 volume: {d['volume_effect']:+,.0f} (unexplained: {d['unexplained_pct']:.1f}%)."
            )
        lines.append(f"Verdict: {bundle['verdict']} at {bundle['confidence_pct']:.0f}% confidence.")
        for reason in bundle["confidence_reasons"]:
            lines.append(f"  \u2022 {reason}")
        if bundle["recommendations"]:
            lines.append("Recommended actions:")
            for r in bundle["recommendations"]:
                lines.append(f"  \u2192 [{r['driver']}] {r['action']} (Owner: {r['owner']}; Impact: {r['impact']})")
        else:
            lines.append("No individual driver crossed the action threshold in isolation.")

    return "\n".join(lines)


def render_narrative(bundle, use_llm=None):
    """use_llm: None = auto-detect from ANTHROPIC_API_KEY env var. True/False
    force a path explicitly (True raises if no key is present)."""
    if use_llm is None:
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if not use_llm:
        return {"text": _template_narrative(bundle), "engine": "template_fallback", "llm_calls": 0,
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    try:
        import anthropic
    except ImportError:
        return {"text": _template_narrative(bundle), "engine": "template_fallback_no_sdk", "llm_calls": 0,
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    client = anthropic.Anthropic()
    prompt = (
        "You are phrasing a pre-computed, already-verified business analytics evidence bundle "
        "into a short, plain-language narrative for the stated persona. Do NOT invent or alter "
        "any number in the bundle — only phrase what is given.\n\n"
        f"Evidence bundle (JSON): {bundle}"
    )
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if hasattr(block, "text"))
    usage = getattr(response, "usage", None)
    tokens_in = getattr(usage, "input_tokens", 0) if usage else 0
    tokens_out = getattr(usage, "output_tokens", 0) if usage else 0
    # Illustrative Sonnet-class rate; swap in the live rate card for real cost tracking.
    cost = tokens_in * 3e-6 + tokens_out * 15e-6
    return {"text": text, "engine": "llm", "llm_calls": 1, "tokens_in": tokens_in,
            "tokens_out": tokens_out, "cost_usd": round(cost, 6)}
