"""
Generates the synthetic, multi-grain dataset Athena analyzes:
  - data/sales.db            SQLite, daily-grain transactional sales (the source of truth)
  - data/marketing_spend.csv weekly-grain marketing spend, DELIBERATELY STALE
  - data/support_tickets.json event-grain support tickets
  - data/freshness.json      per-source freshness manifest

A real, known multi-factor event is planted in the West region during the final
complete analysis week: a promotional price cut on P01, a mix shift toward the
cheaper SKUs (P02, P05) and away from the premium SKUs (P03, P04), and a spike
in delivery-delay support tickets. Marketing spend data is cut off one week
before the event week, so it is genuinely stale at analysis time — not staged.

Run: python data/generate_data.py
"""
import json
import sqlite3
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).parent
ANALYSIS_DATE = date(2024, 9, 30)   # a Monday
HISTORY_WEEKS = 26                   # ~6 months of trailing history
START_DATE = ANALYSIS_DATE - timedelta(weeks=HISTORY_WEEKS)

REGIONS = ["West", "East", "North", "South"]

# Product catalog: base unit price, base daily demand weight (relative), tier
PRODUCTS = {
    "P01": {"name": "Aegis Budget 14",     "price": 480.0,  "weight": 3.0, "tier": "budget"},
    "P02": {"name": "Aegis Value 14",      "price": 640.0,  "weight": 2.6, "tier": "value"},
    "P03": {"name": "Aegis Pro 15",        "price": 1180.0, "weight": 1.6, "tier": "premium"},
    "P04": {"name": "Aegis Pro Max 16",    "price": 1550.0, "weight": 1.1, "tier": "premium"},
    "P05": {"name": "Aegis Value Plus 14", "price": 560.0,  "weight": 2.2, "tier": "value"},
}

# Region relative sizing (share of overall transaction volume)
REGION_WEIGHT = {"West": 1.15, "East": 1.30, "North": 0.95, "South": 0.85}

CUSTOMERS = [f"CUST-{i:04d}" for i in range(1, 241)]
CUSTOMER_EMAIL = {c: f"{c.lower()}@buyer-example.com" for c in CUSTOMERS}  # PII column

# The planted event: last complete W-MON week before ANALYSIS_DATE
# (pandas 'W-MON' periods end on Monday, so this is the Tue-Mon week ending on ANALYSIS_DATE)
EVENT_WEEK_END = ANALYSIS_DATE                      # Mon 2024-09-30
EVENT_WEEK_START = ANALYSIS_DATE - timedelta(days=6)  # Tue 2024-09-24
EVENT_REGION = "West"

P01_PROMO_DISCOUNT = 0.15     # 15% price cut on P01 in West during event week
MIX_SHIFT_AWAY_PREMIUM = 0.55 # premium SKUs lose 55% of their West demand in event week
MIX_SHIFT_TO_VALUE = 0.40     # value SKUs (P02, P05) gain 40% demand in West in event week


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def is_event_week(d, region):
    return region == EVENT_REGION and EVENT_WEEK_START <= d <= EVENT_WEEK_END


def gen_sales_rows():
    rows = []
    txn_id = 1
    for d in daterange(START_DATE, ANALYSIS_DATE):
        dow_factor = 1.25 if d.weekday() < 5 else 0.6  # weekday vs weekend
        for region in REGIONS:
            region_factor = REGION_WEIGHT[region]
            event = is_event_week(d, region)
            for sku, meta in PRODUCTS.items():
                weight = meta["weight"]
                price = meta["price"]

                if event:
                    if sku == "P01":
                        price = price * (1 - P01_PROMO_DISCOUNT)
                    if meta["tier"] == "premium":
                        weight = weight * (1 - MIX_SHIFT_AWAY_PREMIUM)
                    if meta["tier"] == "value":
                        weight = weight * (1 + MIX_SHIFT_TO_VALUE)

                expected_txns = weight * region_factor * dow_factor * 0.75
                n_txns = max(0, int(round(random.gauss(expected_txns, expected_txns * 0.25))))

                for _ in range(n_txns):
                    qty = max(1, int(round(random.gauss(14, 5))))
                    unit_price = round(price * random.uniform(0.98, 1.02), 2)
                    customer = random.choice(CUSTOMERS)
                    rows.append((
                        txn_id, d.isoformat(), region, sku, qty, unit_price,
                        customer, CUSTOMER_EMAIL[customer],
                    ))
                    txn_id += 1
    return rows


def write_sales_db(rows):
    db_path = DATA_DIR / "sales.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE sales_transactions (
            txn_id INTEGER PRIMARY KEY,
            txn_date TEXT NOT NULL,
            region TEXT NOT NULL,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            customer_id TEXT NOT NULL,
            customer_email TEXT NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO sales_transactions VALUES (?,?,?,?,?,?,?,?)", rows
    )
    conn.commit()
    conn.close()
    return db_path


def write_marketing_csv():
    """Weekly marketing spend, deliberately stale: cut off 2 weeks before the
    analysis date, so the most recent (event) week has no marketing figure at all."""
    import csv
    path = DATA_DIR / "marketing_spend.csv"
    stale_cutoff = ANALYSIS_DATE - timedelta(weeks=2)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["week_start", "region", "spend_usd"])
        d = START_DATE
        base = {"West": 42000, "East": 48000, "North": 31000, "South": 27000}
        while d <= stale_cutoff:
            for region in REGIONS:
                spend = round(base[region] * random.uniform(0.85, 1.15), 2)
                w.writerow([d.isoformat(), region, spend])
            d += timedelta(weeks=1)
    return path, stale_cutoff


def write_support_tickets():
    path = DATA_DIR / "support_tickets.json"
    categories = ["delivery_delay", "billing", "product_defect", "general_inquiry"]
    tickets = []
    tid = 1
    d = START_DATE
    while d <= ANALYSIS_DATE:
        for region in REGIONS:
            n = max(0, int(round(random.gauss(2.2, 1.3))))
            if is_event_week(d, region):
                n += int(round(random.gauss(6, 1.5)))  # delivery-delay spike
            for _ in range(n):
                cat = "delivery_delay" if is_event_week(d, region) and random.random() < 0.7 else random.choice(categories)
                tickets.append({
                    "ticket_id": f"TKT-{tid:05d}",
                    "date": d.isoformat(),
                    "region": region,
                    "category": cat,
                })
                tid += 1
        d += timedelta(days=1)
    with open(path, "w") as f:
        json.dump(tickets, f, indent=2)
    return path


def write_freshness(stale_cutoff):
    path = DATA_DIR / "freshness.json"
    manifest = {
        "sales_transactions": {
            "source": "sales.db",
            "grain": "daily",
            "last_updated": ANALYSIS_DATE.isoformat(),
        },
        "marketing_spend": {
            "source": "marketing_spend.csv",
            "grain": "weekly",
            "last_updated": stale_cutoff.isoformat(),
        },
        "support_tickets": {
            "source": "support_tickets.json",
            "grain": "event",
            "last_updated": ANALYSIS_DATE.isoformat(),
        },
    }
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    return path


def main():
    rows = gen_sales_rows()
    db_path = write_sales_db(rows)
    mkt_path, stale_cutoff = write_marketing_csv()
    tix_path = write_support_tickets()
    fresh_path = write_freshness(stale_cutoff)

    print(f"sales.db            : {len(rows):,} transactions -> {db_path}")
    print(f"marketing_spend.csv : stale as of {stale_cutoff.isoformat()} -> {mkt_path}")
    print(f"support_tickets.json: -> {tix_path}")
    print(f"freshness.json       : -> {fresh_path}")
    print(f"Planted event: {EVENT_REGION} region, week {EVENT_WEEK_START} to {EVENT_WEEK_END}")


if __name__ == "__main__":
    main()
