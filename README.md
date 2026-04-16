# कलम · Kalam

> **आपके लिए सरकारी योजनाएं खोजें** · Find which Indian government welfare schemes you qualify for

[![Tests](https://img.shields.io/badge/tests-158%20passing-brightgreen)](#)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#)
[![Deploy](https://img.shields.io/badge/deployed%20on-Render-46E3B7)](https://kalam-ac7c.onrender.com)

Answer 5 short questions. Get personalised eligibility results across 20 central government schemes — with benefit amounts, document checklists, application guidance, and Hindi audio for every card. **No sign-up. No API key. Works with partial information.**

**Live:** [kalam-ac7c.onrender.com](https://kalam-ac7c.onrender.com) *(Render free tier — may take 30 s to wake)*

---

## Screenshots

### Home page
![Home page](docs/screenshots/home.png)
*Hindi-first landing with live scheme stats and a single CTA*

### Eligibility results
![Eligibility results](docs/screenshots/results.png)
*Per-scheme confidence bars, benefit totals, rule-by-rule breakdown, and 🔊 Hindi audio on every card*

### Scheme detail — Atal Pension Yojana
![Scheme detail](docs/screenshots/scheme_detail.png)
*Full description in Hindi + English, 100% confidence score, Benefits tab, How-to-Apply tab*

### Important choices & what's coming up
![Choices and life events](docs/screenshots/choices_coming_up.png)
*Scheme interaction warnings (e.g. "bank account unlocks 8 others") and age-based life-event projections*

### Optimal application order
![Optimal order](docs/screenshots/optimal_order.png)
*Prerequisite-aware sequencing — which office to visit first, estimated days, Hindi office script*

### My Applications tracker
![Applications tracker](docs/screenshots/applications.png)
*localStorage-based tracker: mark schemes as Applied / Pending, see all required documents at a glance*

---

## Features

### Eligibility engine
- Evaluates 20 central government schemes against your profile
- Every rule is **transparent** — you see exactly which conditions pass, fail, or need clarification
- Handles ambiguous rules (e.g. "BPL-equivalent") with annotated edge cases in `data/ambiguity_map.json`

### Confidence scoring
- **Dempster-Shafer TBM pignistic transform** converts multi-valued rule outputs (PASS / FAIL / AMBIGUOUS / MISSING) into a calibrated 0–100% confidence score
- **Bayesian shrinkage** scales confidence by data completeness — a profile with 3 fields gets a wider uncertainty band than a complete one
- All scoring is deterministic; the same inputs always produce the same output

### Hindi audio (TTS)
- Every scheme card, benefit line, and application step has a **🔊 speak button**
- Primary: server-side **Google Cloud Neural2 Hindi TTS** (`hi-IN-Neural2-A`) — natural, human-quality voice
- Fallback: browser **Web Speech API** (`hi-IN`) when no server key is set — zero cost
- Audio is **cached** so repeated taps don't re-fetch
- Handles Android Chrome 30 s idle bug, iOS Safari autoplay restrictions, and Chrome voice-load race conditions

### Benefit calculator
- Real rupee amounts: ₹6,000/yr PM-KISAN, ₹1,000–5,000/month APY, ₹1.2 lakh PMAY-G, etc.
- **State-specific top-ups** (e.g. Odisha CM-KALIA + UP state housing supplement)
- Subsidised food value computed from NFSA ration × FCI open-market price differential
- Total potential annual benefit shown on the results summary

### Bureaucratic distance
- Per-scheme **difficulty badge**: Easy / Moderate / Involved / Complex
- Documents you **already have** vs still need (personalised to your profile)
- Estimated processing days, which offices to visit, and whether online application is available

### Interaction detector
- Flags **mutual exclusions** (e.g. can't hold PMJJBY + PMSBY from two different providers)
- Flags **enablers**: "Open PMJDY bank account first — it unlocks 8 other schemes"
- Flags **threshold risks**: income or age close to a cut-off

### Life event projector
- Projects eligibility changes over the next 1–5 years based on your current age
- E.g. "APY closes at 40 — you have 2 years left to enrol", "NSAP old-age pension opens at 60"
- Surfaces both deadlines (act now) and upcoming opportunities

### Sensitivity analysis
- Varies your income and age by small margins to find **fragile eligibility**
- "If your income were ₹5,000 less you would qualify for three more schemes"

### Optimal application order
- **networkx topological sort** of prerequisites across all eligible schemes
- Tells you which scheme to apply for first, why, and how long each step takes
- Hindi office-visit script for every step so you know exactly what to say

### My Applications tracker
- **localStorage-based** — no login, no server, fully private
- Track any eligible scheme: Not tracked → Applied → Pending → (clear)
- Dedicated `/applications` page shows all tracked schemes with documents needed, office info, and benefit summary in Hindi

---

## Scheme coverage (20 schemes)

| # | Scheme | Ministry | What it gives |
|---|--------|----------|---------------|
| 1 | PM-KISAN | Agriculture | ₹6,000/yr direct cash |
| 2 | MGNREGA | Rural Dev | 100 days guaranteed wage work |
| 3 | Ayushman Bharat (PM-JAY) | Health | ₹5 lakh/yr health insurance |
| 4 | PMAY-G | Rural Dev | ₹1.2–1.3 lakh house grant |
| 5 | PMAY-U | Housing | ₹1–2.5 lakh housing subsidy |
| 6 | PMJDY | Finance | Zero-balance bank account + insurance |
| 7 | Ujjwala 2.0 | Petroleum | Free LPG connection |
| 8 | NSAP-IGNOAPS | Rural Dev | ₹200–500/month old-age pension |
| 9 | NSAP-IGNWPS | Rural Dev | ₹300/month widow pension |
| 10 | NSAP-IGNDPS | Rural Dev | ₹300/month disability pension |
| 11 | APY | Finance / PFRDA | ₹1,000–5,000/month pension at 60 |
| 12 | PM-SYM | Labour | ₹3,000/month pension (informal workers) |
| 13 | PM SVANidhi | Housing & Urban | ₹10,000–50,000 micro-credit (street vendors) |
| 14 | PM-MUDRA | Finance | ₹50,000–10 lakh business loan |
| 15 | PMEGP | MSME | 15–35% capital subsidy on new enterprise |
| 16 | Stand-Up India | Finance | ₹10 lakh–1 crore SC/ST/women entrepreneur loan |
| 17 | Sukanya Samriddhi | Finance | 8.2% tax-free savings for girl child |
| 18 | PMMVY | Women & Child Dev | ₹5,000 maternity benefit (first child) |
| 19 | NFSA | Food & Consumer Affairs | 5 kg subsidised grain/month per person |
| 20 | PM Vishwakarma | MSME | ₹1–2 lakh credit + skill training (artisans) |

---

## Architecture

```
User fills 5-step form (age · income · location · occupation · documents)
      │
      ▼
Profile Builder  ← Pydantic v2 validation, unit normalisation
                   (bigha / acre / gaj / sqft → hectares)
      │ UserProfile (38 optional fields)
      ▼
Rule Engine  ◄──── data/schemes/*.json  (all rules in JSON, zero hardcoding)
      │             data/ambiguity_map.json
      │ PASS / FAIL / AMBIGUOUS / INSUFFICIENT_DATA per rule
      ▼
Confidence Scorer  ← Dempster-Shafer TBM pignistic + Bayesian shrinkage
      │
      ├── Benefit Calculator        ← real amounts, state top-ups
      ├── Bureaucratic Distance     ← difficulty, docs, offices, days
      ├── Sensitivity Analyzer      ← threshold proximity flags
      ├── Life Event Projector      ← age-based opportunity/deadline
      ├── Interaction Detector      ← mutual exclusions, enablers
      ├── Path Optimizer            ← greedy value-first ordering
      └── Prerequisite Sequencer    ← networkx topological sort
                │
                ▼
        FastAPI + Jinja2 · uvicorn · Render
```

---

## Quick start

```bash
git clone https://github.com/VeerR13/KALAM-CBC
cd KALAM-CBC
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Web app
uvicorn web.app:app --reload
# → http://localhost:8000

# CLI (no browser needed)
python cli.py
python cli.py --profile tests/fixtures/profiles/edge_02_leased_farmer.json

# Tests (158 passing)
pytest -v
```

### Environment variables (all optional)

| Variable | Purpose | Default behaviour |
|----------|---------|-------------------|
| `GOOGLE_TTS_KEY` | Google Cloud TTS Neural2 Hindi voice | Falls back to browser Web Speech API |
| `ANTHROPIC_API_KEY` | (future) AI chat features | Not required |

Copy `.env.example` to `.env` and fill in any keys you have.

---

## Deploy on Render

`render.yaml` is included. Connect the repo at [render.com](https://render.com) → New Web Service. No environment variables are required for base functionality — the app works fully without any API keys.

---

## Data

All 20 scheme JSON files are sourced from official government PDFs and guidelines. Each file's `data_freshness` field records the verification date. Eligibility rules, benefit amounts, required documents, helpline numbers, and portal URLs live entirely in `data/schemes/*.json` — no eligibility logic is hardcoded in Python.

---

## Tech stack

Python 3.11+ · Pydantic v2 · FastAPI · Jinja2 · uvicorn · networkx · pytest (158 tests)
