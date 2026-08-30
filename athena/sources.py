"""Source connectors. Each loader returns a pandas DataFrame plus records its
freshness so downstream stages can honestly flag staleness rather than
silently trusting a feed that hasn't updated recently."""
import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"


def load_freshness_manifest():
    with open(DATA_DIR / "freshness.json") as f:
        return json.load(f)


def load_sales(db_path=None):
    db_path = db_path or (DATA_DIR / "sales.db")
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM sales_transactions", conn)
    conn.close()
    df["txn_date"] = pd.to_datetime(df["txn_date"])
    df["revenue"] = df["quantity"] * df["unit_price"]
    return df


def load_marketing(csv_path=None):
    csv_path = csv_path or (DATA_DIR / "marketing_spend.csv")
    df = pd.read_csv(csv_path, parse_dates=["week_start"])
    return df


def load_tickets(json_path=None):
    json_path = json_path or (DATA_DIR / "support_tickets.json")
    with open(json_path) as f:
        tickets = json.load(f)
    df = pd.DataFrame(tickets)
    df["date"] = pd.to_datetime(df["date"])
    return df


def source_is_stale(source_key, as_of, manifest=None, max_age_days=10):
    """A source is stale if its last update is more than max_age_days before
    the analysis date. Returns (is_stale: bool, last_updated: date, age_days: int)."""
    manifest = manifest or load_freshness_manifest()
    entry = manifest[source_key]
    last_updated = date.fromisoformat(entry["last_updated"])
    if isinstance(as_of, pd.Timestamp):
        as_of = as_of.date()
    age_days = (as_of - last_updated).days
    return age_days > max_age_days, last_updated, age_days
