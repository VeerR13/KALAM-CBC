# Kalam — Welfare Scheme Eligibility Engine

AI-powered eligibility matching for 20 Indian government welfare schemes. Input a user profile in Hinglish/English; get back which schemes they qualify for, why, what documents they need, and in what order to apply.

**CBC BITS Pilani Mission 03 submission.**

## Features

- Deterministic rule engine (no black boxes — every output traces to specific rule evaluations)
- PASS / FAIL / AMBIGUOUS / MISSING per rule (never fabricates a confident answer)
- Confidence scoring with explainability
- Gap analysis: what's blocking eligibility and what to do about it
- Prerequisite DAG: topological sort for application order
- 10 adversarial edge case test profiles
- Hinglish/English CLI via Claude API NLP

## Setup

```bash
# Requires Python 3.11+
git clone <repo>
cd kalam
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

## Usage

```bash
# Interactive CLI
python cli.py

# Load profile from JSON
python cli.py --profile tests/fixtures/profiles/edge_02_leased_farmer.json

# Run all 10 adversarial edge cases
python cli.py --test-edge-cases

# Run tests
pytest -v
```

## Architecture

```
User Input (Hinglish/English)
        │
        ▼
Conversational Interface (Claude API NLP)
        │ UserProfile JSON
        ▼
Profile Builder (Pydantic validation, unit normalization)
        │ Validated UserProfile
        ▼
Rule Engine ◄─── Scheme Knowledge Base (20 JSON rule files)
        │         Ambiguity Map (10+ annotations)
        │ Per-scheme RuleResults (PASS/FAIL/AMBIGUOUS/MISSING)
        ▼
Confidence Scorer (weighted aggregation)
        │ ScoredResults
        ├──► Gap Analyzer
        ├──► Doc Checklist Generator
        └──► Prerequisite Sequencer (networkx topological sort)
                │
                ▼
        Output Formatter (rich CLI)
```

## Scheme coverage

| # | Scheme | Ministry |
|---|--------|----------|
| 1 | PM-KISAN | Agriculture |
| 2 | MGNREGA | Rural Development |
| 3 | Ayushman Bharat (PM-JAY) | Health |
| 4 | PMAY-G | Rural Development |
| 5 | PMAY-U | Housing |
| 6 | PMJDY | Finance |
| 7 | Ujjwala 2.0 | Petroleum |
| 8 | NSAP-IGNOAPS | Rural Development |
| 9 | NSAP-IGNWPS | Rural Development |
| 10 | NSAP-IGNDPS | Rural Development |
| 11 | APY | Finance/PFRDA |
| 12 | PM-SYM | Labour |
| 13 | PM SVANidhi | Housing/Urban |
| 14 | PM-MUDRA | Finance |
| 15 | PMEGP | MSME |
| 16 | Stand-Up India | Finance |
| 17 | Sukanya Samriddhi | Finance |
| 18 | PMMVY | Women & Child |
| 19 | NFSA | Food |
| 20 | PM Vishwakarma | MSME |

## Data freshness

All 20 scheme JSONs are marked `PENDING_HUMAN_VERIFICATION`. Place official PDFs in `data/pdfs/` and update `data_freshness` after verification.

## Tech stack

- Python 3.11+, Pydantic v2, networkx, rich, typer
- Anthropic Claude API (Hinglish NLP)
- pytest (87 tests)
