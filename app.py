"""Athena demo app. Run: streamlit run app.py

Lets you pick a persona and a scenario toggle, runs the real pipeline live,
and shows the insight card with working feedback controls (accept / reject /
correct this driver) wired to athena/feedback.py's learning loop.
"""
import streamlit as st

from athena.pipeline import run_pipeline
from athena import feedback as feedback_mod

st.set_page_config(page_title="Athena — KPI Intelligence-to-Action Engine", page_icon="⚡", layout="centered")

st.markdown(
    "<h1 style='color:#6538A8;'>⚡ Athena</h1>"
    "<p style='color:#5B5170;'>Math Before Chat. From what changed to what to do — in seconds.</p>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Run Configuration")
    persona = st.selectbox("Persona", ["analyst", "cfo", "west_manager"], index=0)
    region = st.selectbox("Region", ["West", "East", "North", "South"], index=0)
    scenario = st.selectbox(
        "Scenario",
        ["Flagship (multi-factor)", "Simulated data outage (abstention)", "Sparse history"],
    )
    run_clicked = st.button("Run Athena", type="primary")

if run_clicked:
    kwargs = {"persona_name": persona, "region": region}
    if scenario.startswith("Simulated"):
        kwargs["simulate_data_quality_issue"] = "mix"
    elif scenario.startswith("Sparse"):
        kwargs["sparse_history_override"] = 3

    result = run_pipeline(**kwargs)
    st.session_state["result"] = result
    st.session_state["insight_id"] = f"{persona}-{region}-{result.week}"

if "result" in st.session_state:
    r = st.session_state["result"]
    verdict_color = {"ANSWER": "#1E8E3E", "HEDGE": "#8B5CF6", "CLARIFY": "#C77700", "ABSTAIN": "#B3261E"}
    color = verdict_color.get(r.confidence["verdict"], "#5B5170")

    # --- narrative: split the pipeline's single narrative string into readable
    # paragraphs on its natural delimiters (•, →) instead of one dense block ---
    import re
    raw = r.narrative
    parts = re.split(r"\s*(?:•|→)\s*", raw)
    paragraphs = [p.strip() for p in parts if p.strip()]

    narrative_html = "".join(
        f"<p style='margin:0 0 14px 0; color:#1A1523 !important; -webkit-text-fill-color:#1A1523; "
        f"font-size:16px; line-height:1.55;'>{p}</p>"
        for p in paragraphs
    )

    # --- driver bars: scale each bar to the largest |effect| so the biggest
    # driver reads as a full-width bar, matching the reference design ---
    drivers = []
    if r.driver_breakdown:
        db = r.driver_breakdown
        drivers = [
            ("Mix effect", db["mix_effect"]),
            ("Price effect", db["price_effect"]),
            ("Volume effect", db["volume_effect"]),
        ]
        max_abs = max(abs(v) for _, v in drivers) or 1

    def bar_html(label, value, max_abs):
        pct = max(6, round(abs(value) / max_abs * 100))  # floor width so small bars stay visible
        sign = "+" if value >= 0 else "-"
        return (
            "<div style='flex:1; min-width:150px;'>"
            f"<div style='font-weight:700; color:#1A1523; margin-bottom:10px;'>{label}</div>"
            "<div style='background:#E9E5F3; border-radius:6px; height:10px; overflow:hidden;'>"
            f"<div style='width:{pct}%; height:100%; background:#6538A8; border-radius:6px;'></div>"
            "</div>"
            f"<div style='color:#1A1523; margin-top:8px; font-size:15px;'>{sign}${abs(value):,.0f}</div>"
            "</div>"
        )

    drivers_html = ""
    if drivers:
        bars = "".join(bar_html(label, value, max_abs) for label, value in drivers)
        drivers_html = (
            "<div style='margin-top:8px; padding-top:20px; border-top:1px solid #E5DFF5;'>"
            "<div style='font-weight:700; color:#1A1523; font-size:17px; margin-bottom:18px;'>Driver breakdown</div>"
            f"<div style='display:flex; gap:32px; flex-wrap:wrap;'>{bars}</div>"
            f"<div style='color:#8A8299; font-size:13px; margin-top:14px;'>Unexplained: {r.driver_breakdown['unexplained_pct']:.1%}</div>"
            "</div>"
        )

    # --- footer badges: pulled from security_report / telemetry. Key names
    # below are best guesses — adjust to match your actual result schema. ---
    sec = r.security_report or {}
    tel = r.telemetry or {}
    role_value = sec.get("role", sec.get("persona_role", "—"))
    role_ok = sec.get("within_permissions", sec.get("access_ok", True))
    stale_sources = tel.get("stale_sources", tel.get("stale_source_count"))
    freshness_value = f"{stale_sources} source stale" if stale_sources else tel.get("freshness", "up to date")
    method_value = tel.get("method", sec.get("method", "Deterministic"))
    contract_value = tel.get("contract_version", sec.get("contract_version", "v1.0"))

    def badge_html(icon, icon_color, label, value):
        return (
            "<div style='display:flex; align-items:center; gap:10px; flex:1; min-width:150px;'>"
            f"<div style='font-size:20px; color:{icon_color};'>{icon}</div>"
            "<div>"
            f"<div style='font-weight:700; color:#1A1523; font-size:14px;'>{label}</div>"
            f"<div style='color:#5B5170; font-size:14px;'>{value}</div>"
            "</div></div>"
        )

    footer_html = (
        "<div style='margin-top:20px; padding-top:18px; border-top:1px solid #E5DFF5; "
        "display:flex; gap:24px; flex-wrap:wrap;'>"
        + badge_html("🛡️", "#1E8E3E" if role_ok else "#B3261E", "Role access: " + str(role_value),
                     "Within permissions" if role_ok else "Restricted")
        + badge_html("🕐", "#C77700", "Freshness", freshness_value)
        + badge_html("📈", "#3B82F6", "Method", method_value)
        + badge_html("📄", "#6538A8", "Contract", contract_value)
        + "</div>"
    )

    st.markdown(
        f"<div style='border:1px solid #E5DFF5; border-radius:12px; padding:28px; background:#FAF9FD;'>"
        f"<div style='margin-bottom:16px;'>"
        f"<span style='color:{color}; font-weight:700; font-size:20px;'>{r.confidence['verdict']}</span> "
        f"<span style='color:#5B5170; font-size:18px;'>at {r.confidence['confidence_pct']:.0f}% confidence</span>"
        f"</div>"
        f"<h3 style='margin:0 0 16px 0; color:#1A1523;'>{r.region_analyzed} &bull; {r.week}</h3>"
        f"{narrative_html}"
        f"{drivers_html}"
        f"{footer_html}"
        f"</div>",
        unsafe_allow_html=True,
    )

    with st.expander("Raw security & telemetry"):
        st.json({"security": r.security_report, "telemetry": r.telemetry})

    st.subheader("Analyst Feedback")
    fb_col1, fb_col2, fb_col3 = st.columns([1, 1, 2])
    if fb_col1.button("👍 Accept"):
        feedback_mod.submit_feedback(st.session_state["insight_id"], "accept")
        st.success("Feedback logged: accepted.")
    if fb_col2.button("👎 Reject"):
        feedback_mod.submit_feedback(st.session_state["insight_id"], "reject")
        st.warning("Feedback logged: rejected.")

    with fb_col3:
        corrected = st.selectbox("Correct this driver", ["mix", "price", "volume"], key="correct_driver")
        if st.button("Submit correction"):
            feedback_mod.submit_feedback(st.session_state["insight_id"], "correct", corrected_driver=corrected)
            st.info(f"Feedback logged: driver corrected to '{corrected}'. Rule weights updated.")

    with st.expander("Feedback log & current rule weights"):
        st.json(feedback_mod.feedback_summary())
else:
    st.info("Configure a run in the sidebar and click **Run Athena**.")