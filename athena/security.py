"""Row-, column-, and domain-level security. Applied at the data boundary —
before any statistical or LLM processing touches the frame — not as a
post-hoc UI-level filter."""


def resolve_scope(contract, persona_name):
    persona = contract["personas"][persona_name]
    role_name = persona["role"]
    role = contract["security"]["roles"][role_name]
    region_scope = role["region_scope"]
    if region_scope == "own_region":
        region_scope = persona["region"]
    return {
        "role": role_name,
        "region_scope": region_scope,   # "all" or a specific region string
        "detail_level": role["detail_level"],
    }


def apply_security(df, contract, persona_name):
    """Returns (filtered_df, security_report). Drops out-of-scope rows and
    all PII columns, and reports exactly what was removed for auditability."""
    scope = resolve_scope(contract, persona_name)
    original_rows = len(df)

    if scope["region_scope"] != "all":
        filtered = df[df["region"] == scope["region_scope"]].copy()
    else:
        filtered = df.copy()

    pii_cols = [c for c in contract["security"]["pii_columns"] if c in filtered.columns]
    filtered = filtered.drop(columns=pii_cols)

    report = {
        "persona": persona_name,
        "role": scope["role"],
        "region_scope": scope["region_scope"],
        "rows_before": original_rows,
        "rows_after": len(filtered),
        "rows_blocked": original_rows - len(filtered),
        "pii_columns_dropped": pii_cols,
    }
    return filtered, report
