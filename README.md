# कलम · Kalam — Welfare Scheme Eligibility Engine

> **आपके लिए कौन सी सरकारी योजना है?** · Which government schemes do you qualify for?

[![Tests](https://img.shields.io/badge/tests-92%20passing-brightgreen)](#)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#)
[![Deploy](https://img.shields.io/badge/deployed%20on-Render-46E3B7)](#)

Find which Indian government welfare schemes you qualify for. Answer 5 short questions → get eligibility results, benefit amounts, personalised document checklists, Hindi office-visit scripts, and step-by-step application guidance for 20 schemes.

**No API key required. No sign-up. Works with partial information.**

---

## Live demo

The app is deployed at: [https://kalam.onrender.com](https://kalam.onrender.com) *(Render free tier — may take 30s to wake)*

---

## Screenshots

| Landing | Form | Results |
|:---:|:---:|:---:|
| Hindi-first landing page with scheme stats | 5-step profile form, works on mobile | Confidence bars, Hindi scripts, speak buttons |

---

## What it does

- Checks eligibility across 20 central government schemes
- Shows exactly which rules you pass, fail, or need clarification on — no black boxes
- Shows personalised benefit amounts (cash, food ration, insurance) including state-specific top-ups
- Generates a personalised document checklist — only documents you don't already have
- Provides a "How to Apply" guide with office locations, portal links, helpline numbers, and a Hindi script to read at the office
- Projects how eligibility changes as you age (life events)
- Highlights if income or age is near a scheme threshold (sensitivity analysis)
- Detects scheme conflicts and mutual exclusions
- Recommends the optimal order to apply

## Setup

```bash
# Requires Python 3.11+
git clone https://github.com/VeerR13/kalam
cd kalam
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
# Web app (recommended)
uvicorn web.app:app --reload
# Open http://localhost:8000

# CLI
python cli.py
python cli.py --profile tests/fixtures/profiles/edge_02_leased_farmer.json
python cli.py --test-edge-cases

# Tests
pytest -v
```

## Architecture

```
User fills form
      │
      ▼
Profile Builder  ← Pydantic validation, unit normalization (bigha/acre/gaj/sqft)
      │ UserProfile
      ▼
Rule Engine  ◄──── 20 Scheme JSON files (all rules live here, no hardcoding)
      │             Ambiguity Map (edge case annotations)
      │ PASS / FAIL / AMBIGUOUS / MISSING per rule
      ▼
Confidence Scorer  ← Smets-Kennes TBM pignistic transform + Bayesian shrinkage
      │
      ├── Gap Analyzer
      ├── Benefit Calculator       ← Real scheme amounts, state-specific top-ups
      ├── Sensitivity Analyzer
      ├── Life Event Projector
      ├── Interaction Detector
      ├── Bureaucratic Distance Calculator
      ├── Path Optimizer
      └── Prerequisite Sequencer   ← networkx topological sort
                │
                ▼
        FastAPI + Jinja2 Web App
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
| 11 | APY | Finance / PFRDA |
| 12 | PM-SYM | Labour |
| 13 | PM SVANidhi | Housing & Urban Affairs |
| 14 | PM-MUDRA | Finance |
| 15 | PMEGP | MSME |
| 16 | Stand-Up India | Finance |
| 17 | Sukanya Samriddhi | Finance |
| 18 | PMMVY | Women & Child Development |
| 19 | NFSA | Food & Consumer Affairs |
| 20 | PM Vishwakarma | MSME |

## Data

All 20 scheme JSON files are verified against official government PDFs and guidelines. Verification date is in each file's `data_freshness` field. Rules, eligibility conditions, benefit amounts, required documents, helpline numbers, and portal URLs are stored entirely in `data/schemes/*.json` — no eligibility logic is hardcoded in Python.

## Tech stack

- Python 3.11+, Pydantic v2, networkx, FastAPI, Jinja2, uvicorn
- No external API key required
- pytest (92 tests)

## Deploy on Render

`render.yaml` is included. Connect the GitHub repo at render.com — no environment variables needed.
