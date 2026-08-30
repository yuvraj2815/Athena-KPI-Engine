"""Persona resolution: maps a persona name to its role, security scope, and
narrative focus, as defined in the semantic contract."""
from athena.security import resolve_scope


def get_persona_view(contract, persona_name):
    persona = contract["personas"][persona_name]
    scope = resolve_scope(contract, persona_name)
    return {
        "name": persona_name,
        "role": persona["role"],
        "narrative_focus": persona["narrative_focus"],
        "region_scope": scope["region_scope"],
        "detail_level": scope["detail_level"],
    }
