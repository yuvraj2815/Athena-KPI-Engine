# Athena — The KPI Intelligence-to-Action Engine

**Math Before Chat.** From what changed to what to do — in seconds.

Athena is a governed KPI storytelling engine built for Round 2 of the BusinessIntelligence.ai challenge. It detects material KPI movements, decomposes them into exact quantitative drivers, reconciles context across heterogeneous data sources, and generates persona-specific, action-oriented narratives — while communicating uncertainty honestly and abstaining when evidence is insufficient.

The core design principle: **the LLM is never the source of quantitative truth.** All detection, decomposition, security, and confidence scoring are deterministic Python. The LLM is used only to phrase a pre-computed evidence bundle into a narrative — and the system runs correctly with zero LLM calls via a deterministic template fallback.

> Every number in this README was produced by actually running the code in this repo, not written by hand. Re-running `python data/generate_data.py` (seeded, so it's reproducible) followed by `python -m scenarios.run_all` will reproduce these exact figures.

---

## Table of Contents

1. [Why Athena](#why-athena)
2. [The Four-Step Pipeline](#the-four-step-pipeline)
3. [Repository Structure](#repository-structure)
4. [Getting Started](#getting-started)
5. [Configuration — The KPI Semantic Contract](#configuration--the-kpi-semantic-contract)
6. [Running the Engine](#running-the-engine)
7. [The Six Required Scenarios — Verified](#the-six-required-scenarios--verified)
8. [Verified Flagship Result](#verified-flagship-result)
9. [Security Model](#security-model)
10. [Feedback & Learning Loop](#feedback--learning-loop)
11. [Telemetry & Economics](#telemetry--economics)
12. [Testing](#testing)
13. [Limitations & Future Work](#limitations--future-work)
14. [License](#license)

---

## Why Athena

Most enterprise KPI tools stop at the dashboard: they show *what* happened but leave the *why* and *what to do next* to an analyst manually reconciling data across systems with different refresh cadences and grains. Generic LLM chatbots don't solve this safely — asking a language model to aggregate rows or compute variance invites fabricated numbers and eroded trust.

Athena's answer is a governed hybrid architecture: deterministic computation proves *what* happened and *why*, and generative synthesis only explains it in plain language, adapted to who's asking.

## The Four-Step Pipeline

| Step | Name | What it does |
|---|---|---|
| 1 | **Detect** | Applies dual-bar materiality — a movement must clear both a statistical bar (MAD-based robust z-score against an 8-week trailing baseline) and a business bar (minimum % and $ impact) — to separate signal from normal weekly noise. |
| 2 | **Decompose** | Executes a Price-Volume-Mix (PVM) bridge that isolates exact dollar contributions per driver, comparing the current week to the immediately preceding week. Mix is defined as the residual after price and volume effects are removed, which guarantees the three components reconcile exactly to the observed delta. The LLM does not calculate. |
| 3 | **Explain** | Ingests source freshness and applies rule-based confidence scoring — including explicit abstention when evidence is insufficient or contradictory. |
| 4 | **Recommend** | Translates the proven math into persona-specific narratives, each structured as Driver → Controllable Lever → Action → Expected Impact → Owner → Confidence → Monitoring Plan. |

## Repository Structure

```
athena-kpi-engine/
├── config/
│   └── kpi_contract.yaml       # governed KPI definitions — the single source of truth
├── data/
│   ├── generate_data.py        # synthetic data generator (plants a known ground-truth event)
│   ├── sales.db                # SQLite, daily-grain transactional data (generated)
│   ├── marketing_spend.csv     # weekly-grain spend data, deliberately stale (generated)
│   ├── support_tickets.json    # event-grain support tickets (generated)
│   └── freshness.json          # per-source freshness manifest (generated)
├── athena/
│   ├── contract.py             # loads and validates the KPI semantic contract
│   ├── sources.py              # source connectors + freshness tracking
│   ├── security.py             # row / column / PII enforcement
│   ├── detection.py            # statistical materiality (robust z-score + baseline)
│   ├── drivers.py               # price-volume-mix decomposition
│   ├── abstention.py           # confidence calibration + when to abstain
│   ├── recommend.py            # driver → lever → action rule engine
│   ├── personas.py             # CFO / Regional Manager / Analyst views
│   ├── narrative.py            # LLM phrasing OR deterministic template fallback
│   ├── telemetry.py            # latency, token, and cost tracking
│   ├── feedback.py             # accept / reject / correct + learning loop
│   └── pipeline.py             # orchestrator tying every stage together
├── scenarios/
│   └── run_all.py              # scenario runner covering all six required cases
├── app.py                      # Streamlit demo application
├── tests/
│   └── test_engine.py          # automated test suite
└── requirements.txt
```

`sales.db`, `marketing_spend.csv`, `support_tickets.json`, and `freshness.json` are generated, not checked in — run the generator once (below) to produce them. It's seeded (`random.seed(42)`), so re-running it reproduces the same dataset and the same numbers reported in this document.

## Getting Started

**Prerequisites:** Python 3.10+, pip.

```bash
git clone <repo-url> athena-kpi-engine
cd athena-kpi-engine
pip install -r requirements.txt

# Generate the synthetic, multi-grain dataset (plants the flagship West-region event)
python data/generate_data.py
```

An Anthropic API key is **optional**. If `ANTHROPIC_API_KEY` is not set, `narrative.py` automatically falls back to a deterministic template renderer — the full pipeline, including the flagship scenario, runs correctly offline at zero LLM cost. This is also what every number in this README was actually generated with.

## Configuration — The KPI Semantic Contract

`config/kpi_contract.yaml` is the governed, auditable definition of every KPI Athena reasons about: calculation logic, drivers, materiality thresholds, lineage, and access restrictions. Nothing downstream — including the LLM — is permitted to redefine a KPI outside this contract.

Key calibrated setting: the statistical materiality bar is set to **z ≥ 1.75** (≈92% one-sided confidence), a deliberate, documented choice rather than the stricter conventional z ≥ 2.0 (≈95%), reviewable per-KPI in the contract rather than hard-coded in application logic.

The confidence rubric is also contract-driven and equally simple to audit: start from a base of 95, subtract a documented penalty for a stale critical source (−25) or sparse history (−70), and apply hard rule overrides for abstention (unexplained residual > 50%) and contradictory signals. This is why the flagship scenario lands at exactly 70% confidence (95 − 25) and the sparse-history scenario lands at exactly 25% (95 − 70) — the arithmetic is intentionally legible, not a black-box score.

## Running the Engine

```bash
# Run the full pipeline on the flagship multi-factor scenario
python -m athena.pipeline --persona analyst --region West

# Run any individual persona view
python -m athena.pipeline --persona cfo --region West
python -m athena.pipeline --persona west_manager --region West

# Run the full scenario suite (all six required cases)
python -m scenarios.run_all

# Launch the interactive demo
streamlit run app.py
```

## The Six Required Scenarios — Verified

Running `python -m scenarios.run_all` against the live pipeline produces:

```
[PASS] S1 Multi-Factor Movement — verdict=HEDGE @ 70%, mix=-123,242 price=-18,351
       volume=+8,509, unexplained=0%, 3 recommendation(s)
[PASS] S2 Persona Differentiation — 3 distinct narratives generated from one
       evidence bundle (CFO/Manager/Analyst)
[PASS] S3 Role-Based Security — CFO sees 6,517 rows; West Manager sees 1,762
       of 6,517 (blocked 4,755); PII dropped for both
[PASS] S4 Source Staleness — stale source correctly named in confidence
       reasoning: marketing_spend (last updated 2024-09-16, 14d ago)
[PASS] S5 Low-Confidence Abstention — verdict=ABSTAIN, unexplained=93%
       (simulated outage on the 'mix' driver)
[PASS] S6 Sparse-History Product — verdict=HEDGE @ 25% confidence with only
       3 weeks of simulated history

6/6 scenarios passed.
```

| # | Scenario | Verified Result |
|---|---|---|
| S1 | Multi-factor movement | HEDGE at 70% confidence, with the full mix / price / volume driver breakdown |
| S2 | Persona differentiation | Three genuinely distinct narratives — CFO (strategic roll-up), West Manager (tactical actions), Analyst (full evidence) |
| S3 | Role-based security | CFO sees all 6,517 rows; the West Manager is blocked from 4,755 of them (1,762 remain), with PII dropped for both |
| S4 | Source staleness | Stale marketing source flagged by name and age (14 days); confidence downgraded accordingly |
| S5 | Low-confidence abstention | Correctly ABSTAINS with a 93% unexplained residual, triggered by a simulated source outage (`simulate_data_quality_issue="mix"`) |
| S6 | Sparse-history product | Simulated new-product history (3 weeks) hedged at exactly 25% confidence rather than projecting a false trend |

## Verified Flagship Result

The flagship scenario plants a real, multi-factor event in the West region's final analysis week (2024-09-24 to 2024-09-30) — a 15% promotional price cut on SKU P01, a deliberate demand shift away from the two premium SKUs (P03, P04) and toward the two value SKUs (P02, P05), and a marketing feed that is genuinely stale (cut off two weeks before the event, not staged after the fact):

- **Detect:** West revenue **−10.37%** vs. its 8-week baseline mean (−$73,960); robust z ≈ **−2.79**, clearing the calibrated z ≥ 1.75 materiality bar
- **Decompose (week-over-week):** mix **−$123,242** (the dominant driver) · price **−$18,351** (the P01 promo) · volume **+$8,509** (units are actually up) — the three effects reconcile **exactly** to the observed −$133,083 week-over-week delta, **0% unexplained**
- **Explain:** verdict **HEDGE at 70% confidence** — the marketing spend source is correctly flagged stale (14 days old at analysis time)
- **Recommend:** three owner-tagged actions, one per driver, each with a controllable lever, expected impact, and monitoring plan

*(Note: "Detect" compares the current week to an 8-week trailing baseline mean, for a statistically robust significance test; "Decompose" compares the current week to the single immediately-preceding week, which is the standard convention for a week-over-week PVM bridge. The two percentages therefore describe slightly different comparisons — this is intentional and documented in `config/kpi_contract.yaml`.)*

## Security Model

Row-, column-, and domain-level security is enforced at the data boundary — before analysis, not after. A West Manager querying the system never obtains East/North/South-region rows or the PII column; both are filtered out of the frame before any statistical or LLM processing. Verified: the CFO persona sees the full 6,517-row dataset, while the West Manager persona is provably restricted to 1,762 rows, with `customer_email` dropped for both.

## Feedback & Learning Loop

Every insight card (in the Streamlit app) supports analyst validation — accept, reject, or explicitly correct the identified root cause. Corrections are logged to `data/feedback.json` and nudge `data/rule_weights.json`, a small bounded weighting of driver prioritization, giving Athena a human-in-the-loop mechanism for catching drift between the semantic contract and changing business reality.

## Telemetry & Economics

Every pipeline run is fully instrumented, stage by stage:

- **~40–80ms** verified end-to-end latency on the flagship scenario (varies slightly by run/machine)
- **~99.9%** of wall-clock time spent in deterministic Python stages, not narrative generation
- **$0** LLM cost on the fallback path — the deterministic template renderer requires no API key and produces the full narrative output for every persona
- Full stage-by-stage latency, token, and cost breakdown available per run via `result.telemetry`

## Testing

```bash
pytest tests/
```

`tests/test_engine.py` covers the PVM bridge reconciliation invariant (contributions must sum exactly to the observed delta), the dual-bar materiality check, the abstention and sparse-history rules, the row/column/PII security filters, and persona narrative differentiation. Every assertion in this file was also independently verified with a plain-Python runner during development (no pytest dependency required to confirm correctness).

## Limitations & Future Work

- Synthetic, single-scenario-focused dataset for the prototype; production deployment would connect to real source systems via the same `sources.py` connector pattern.
- The learning loop currently reweights rules locally (`data/rule_weights.json`); a production version would persist this centrally and monitor for drift at scale.
- LLM narrative synthesis is implemented (`athena/narrative.py`, active when `ANTHROPIC_API_KEY` is set) but was validated against the deterministic template fallback in this submission; live-model output should be spot-checked against the evidence bundle before wider rollout.

## License

This prototype was built for the BusinessIntelligence.ai Round 2 challenge submission.

---

**Team NiceGuys**
