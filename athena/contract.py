"""Loads and validates the KPI semantic contract. Nothing downstream may
redefine a KPI outside of what this module hands back."""
from pathlib import Path
import yaml

CONTRACT_PATH = Path(__file__).parent.parent / "config" / "kpi_contract.yaml"

REQUIRED_KPI_KEYS = {"calculation", "grain", "source", "materiality", "confidence_rubric", "lineage"}


class ContractError(ValueError):
    pass


def load_contract(path=None):
    path = Path(path) if path else CONTRACT_PATH
    with open(path) as f:
        contract = yaml.safe_load(f)

    if "kpis" not in contract:
        raise ContractError("Contract missing top-level 'kpis' section")

    for kpi_name, kpi_def in contract["kpis"].items():
        missing = REQUIRED_KPI_KEYS - set(kpi_def.keys())
        if missing:
            raise ContractError(f"KPI '{kpi_name}' missing required keys: {missing}")

    if "security" not in contract or "pii_columns" not in contract["security"]:
        raise ContractError("Contract missing security.pii_columns")

    return contract


def get_kpi(contract, kpi_name):
    try:
        return contract["kpis"][kpi_name]
    except KeyError:
        raise ContractError(f"Unknown KPI '{kpi_name}' — not defined in the semantic contract")


def get_persona(contract, persona_name):
    try:
        return contract["personas"][persona_name]
    except KeyError:
        raise ContractError(f"Unknown persona '{persona_name}' — not defined in the semantic contract")
