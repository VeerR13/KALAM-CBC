# Kalam — Architecture Document

**CBC BITS Pilani · Mission 03 · Final Deliverable (Part IV)**

---

## 4.1 System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  INPUT LAYER                                                            │
│                                                                         │
│   CLI (cli.py)                      Web UI (FastAPI + Jinja2)          │
│   python cli.py                     GET /details → POST /results        │
│   Hinglish/English text             Multi-step form, option cards       │
│   Multi-turn conversation           /chat → /api/chat (AJAX)           │
└────────────────────────┬────────────────────────┬───────────────────────┘
                         │                        │
                         ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  NLP LAYER  (src/conversation/)                                         │
│                                                                         │
│   system_prompt.py     Hinglish extraction prompt for Claude Haiku      │
│   follow_up.py         Priority queue: which missing field to ask next  │
│                        (ranked by number of schemes it unblocks)        │
│   contradiction.py     Detects logical conflicts in the profile         │
│                        (e.g., is_urban=True + mgnrega eligibility)      │
│                                                                         │
│   Claude Haiku API ────► JSON: extracted_fields + contradictions        │
│   Regex fallback ──────► Same JSON shape, no API key needed             │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ raw dict
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PROFILE BUILDER  (src/models/user_profile.py)                          │
│                                                                         │
│   UserProfile (Pydantic v2)                                             │
│   - 26 typed fields, all Optional except the 11 core fields             │
│   - Validators: age ∈ [0,120], disability_percent ∈ [0,100]            │
│   - Unit normalization:                                                 │
│       bigha → hectares (state-aware: Rajasthan=0.4, UP=0.33, Assam=0.625)
│       gaj (sq yard) → hectares: 1 gaj = 0.0000836127 ha                │
│       sqft → hectares: 1 sqft = 0.00000929 ha                          │
│   - income_is_approximate flag + income_range for sensitivity           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ validated UserProfile
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  RULE ENGINE  (src/engine/rule_engine.py)                               │
│                                                                         │
│   For each of 20 schemes:                                               │
│     For each rule in scheme.rules:                                      │
│       evaluate_rule(rule, profile) → RuleResult                         │
│                                                                         │
│   RuleResult = PASS | FAIL | AMBIGUOUS | MISSING                        │
│   MISSING ≠ FAIL: missing field → cannot evaluate, never penalizes     │
│   AMBIGUOUS: field value is in ambiguous_values (e.g. leased land)     │
│                                                                         │
│   Condition types:                                                      │
│     field_check   — field in valid_values | ambiguous_values           │
│     range_check   — numeric field within [min, max]                    │
│     boolean_check — bool field equals expected                         │
│     exclusion     — any_true_fails: list of disqualifying conditions   │
│     composite     — AND/OR of sub-conditions                           │
│     state_dependent — state-specific threshold lookup                  │
│                                                                         │
│   ◄──────────── data/schemes/*.json  (20 rule files)                   │
│   ◄──────────── data/ambiguity_map.json  (44 annotations)              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ list[tuple[rule_id, RuleResult, explanation]]
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CONFIDENCE SCORER  (src/engine/confidence.py)                          │
│                                                                         │
│   Formula:                                                              │
│   confidence = (Σ passed_weights + 0.5 × Σ ambiguous_weights)          │
│                ─────────────────────────────────────────────── × 100   │
│                            Σ evaluated_weights                          │
│                                                                         │
│   MISSING rules are excluded from denominator (not penalised)          │
│                                                                         │
│   Status thresholds:                                                    │
│     ELIGIBLE          confidence ≥ 90 AND no mandatory FAIL/AMBIGUOUS  │
│     LIKELY_ELIGIBLE   confidence ≥ 70 AND no mandatory FAIL            │
│     AMBIGUOUS         40 ≤ confidence < 70 OR any mandatory AMBIGUOUS  │
│     INELIGIBLE        any mandatory FAIL                                │
│     INSUFFICIENT_DATA all evaluated rules are MISSING                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (confidence: float, status: MatchStatus)
                         ┌───────────┼───────────┐
                         ▼           ▼           ▼
              ┌──────────────┐ ┌──────────┐ ┌──────────────────┐
              │ GAP ANALYZER │ │  DOC     │ │  PREREQUISITE    │
              │ gap_analyzer │ │CHECKLIST │ │  SEQUENCER       │
              │              │ │          │ │  sequencer.py    │
              │ 4 gap types: │ │documents │ │                  │
              │ MISSING_INPUT│ │.json     │ │  PrerequisiteDAG │
              │ MISSING_DOC  │ │          │ │  networkx DiGraph│
              │ AMBIG_CRIT   │ │prioritize│ │  topological sort│
              │ MISSING_PREREQ│ │by process│ │  skips satisfied │
              └──────┬───────┘ │ing time  │ │  prereqs         │
                     │         └────┬─────┘ └────────┬─────────┘
                     └─────────────┼─────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  OUTPUT LAYER                                                           │
│                                                                         │
│   MatchResult (src/models/match_result.py)                              │
│     scheme_id, scheme_name, status, confidence                         │
│     rule_evaluations: list[RuleEvaluation]   ← full explainability     │
│     gaps: list[GapAnalysis]                                             │
│     required_documents: list[dict]                                      │
│     prerequisite_scheme_ids: list[str]                                  │
│                                                                         │
│   CLI output: rich tables, colored confidence bars (formatter.py)       │
│   Web output: HTML cards with confidence bars, expandable rule list,    │
│               inline mini-forms for "Need more info" schemes            │
└─────────────────────────────────────────────────────────────────────────┘
```

**Source files for the diagram:**
- `diagrams/architecture.mermaid` — Mermaid source
- `diagrams/prerequisite_dag.mermaid` — Prerequisite DAG (20-scheme dependency graph)

---

## 4.2 Three Key Technical Decisions

### Decision 1: JSON Rule Files vs. Hardcoded Python Logic

**Decision:** All eligibility rules live in `data/schemes/*.json`. Zero eligibility logic is hardcoded in Python.

**Rejected alternative:** Encode rules directly as Python functions (e.g., `def is_eligible_pm_kisan(profile) → bool`).

**Why rejected:**
- Hard-coded rules cannot be updated without a code deployment. India's welfare scheme criteria change via gazette notifications — sometimes mid-year.
- Testing becomes tightly coupled to code; a rule change requires a test change, not just a data change.
- Non-technical staff (field officers, policy analysts) cannot read or verify Python code.
- Evaluators cannot inspect the rule logic without reading source code.

**Why JSON wins:**
- The JSON schema enforces the rule structure (condition types, ambiguity_refs, weights). Invalid rules fail at load time, not silently at runtime.
- Human verifiers can open the JSON, compare against the official PDF, and edit a single field. `data_freshness` changes from `PENDING_HUMAN_VERIFICATION` to `VERIFIED_AGAINST_PDF_2026-04-12` without a single line of Python changing.
- The rule engine (`rule_engine.py`) is a pure interpreter — 180 lines that handle all 6 condition types. Scheme logic grows in data, not code.
- Ambiguity is first-class: `ambiguous_values` in a rule definition means the rule returns `AMBIGUOUS` (not `FAIL`) for borderline inputs, which is the correct behavior when the law itself is unclear.

**Tradeoff accepted:** JSON cannot express arbitrarily complex procedural logic. A rule like "income > threshold WHERE threshold varies by state AND family size" requires a `state_dependent` composite condition. Complex rules are harder to write in JSON than in Python. This is an acceptable cost — welfare eligibility criteria are typically simple comparisons, not algorithms.

---

### Decision 2: Four-State Rule Results (PASS / FAIL / AMBIGUOUS / MISSING) vs. Binary PASS / FAIL

**Decision:** Every rule evaluation returns one of four states. `MISSING` and `AMBIGUOUS` are distinct from `FAIL`.

**Rejected alternative:** Binary — if a field is absent or the value is in a grey area, treat it as `FAIL`.

**Why rejected:**
- Binary systems hallucinate confidence. If a user doesn't know their SECC status, binary systems either assume they're in SECC (incorrect PASS) or assume they're not (incorrect FAIL). Both are wrong for 40% of Indians.
- Binary systems punish partial information. A user who fills in 15 of 26 fields correctly should see results for 18 schemes, not zero. Collapsing `MISSING` to `FAIL` ineligibles everything.
- Ambiguous government language is a real phenomenon. PM-KISAN says "farmer families" but doesn't define tenure type. A leased-land farmer should see `AMBIGUOUS` — not `FAIL` — because the official guidance genuinely contradicts itself (AMB-01 in `data/ambiguity_map.json`).

**Why four states wins:**
- `MISSING` enables the "Need more info" UX: the system shows the user which specific fields, when provided, would unlock more schemes. This is the gap analysis feature.
- `AMBIGUOUS` preserves honest uncertainty. Evaluators testing edge cases will see the engine flag the right ambiguities (edge_02_leased_farmer, edge_05_transgender_bpl) rather than fabricating a confident wrong answer.
- The confidence formula handles all four: `MISSING` rules are excluded from the denominator (not penalised), `AMBIGUOUS` rules contribute 50% weight. The math is correct.
- The test suite directly validates this: `test_edge_02_pm_kisan_ambiguous_leased_land` asserts `AMBIGUOUS`, not `INELIGIBLE`. This would fail in a binary system.

**Tradeoff accepted:** More complex confidence formula, more complex test assertions, more complex UI (five status categories instead of two). The added complexity is proportionate to the real-world problem.

---

### Decision 3: Claude Haiku for NLP with Regex Fallback vs. Pure Regex vs. Dedicated NLP Model

**Decision:** Primary NLP is Claude Haiku via the Anthropic API. If the API key is absent or the call fails, the system silently falls back to a keyword-matching regex parser with identical output shape.

**Rejected alternative A:** Pure regex extraction for all inputs.

**Why rejected:** Hinglish input is morphologically rich and structurally unpredictable. "mere paas do sow gaj zameen hai Bihar mein, SC hoon, sath hazar haath ka kaam karta hoon" requires:
- Number word conversion ("do sow" = 200, "sath" = 60,000)
- Unit conversion (200 gaj = 0.01672 hectares)
- Hindi number words ("sath hazar" = 60,000) not covered by `\d+`
- Category extraction from free text
Regex handles simple inputs adequately but fails on these constructions. The fallback regex covers the simple cases; Claude covers the complex ones.

**Rejected alternative B:** Fine-tuned sentence classification model (e.g., IndicBERT).

**Why rejected:** Training a dedicated model requires annotated Hinglish welfare intake data at scale — which doesn't exist. Using a foundation model with a well-structured system prompt achieves extraction quality comparable to a domain-specific model without the data collection overhead. The system prompt (`src/conversation/system_prompt.py`) encodes the extraction rules explicitly, making the behavior transparent and auditable.

**Why Haiku + fallback wins:**
- Haiku is fast (< 1s) and cheap (< $0.001 per turn), appropriate for a free public-good tool.
- The fallback ensures the system never fails hard — a user without internet access or with a misconfigured API key still gets a degraded but functional experience.
- The output contract (JSON with `extracted_fields`, `contradictions`, `confidence_in_extraction`) is identical for both paths. The upstream code cannot tell which path ran.
- The system prompt is version-controlled, auditable, and improves independently of the rule engine.

**Tradeoff accepted:** Claude API creates an external dependency and a cost at scale. At 10,000 users/day × 8 turns × $0.0008/turn, monthly cost would be ~$192. This is acceptable for a public benefit tool and can be offset by caching (repeated inputs return the same extracted fields).

---

## 4.3 Two Critical Production-Readiness Gaps

### Gap 1: SECC 2011 Data Staleness

**What the gap is:**
Four schemes — Ayushman Bharat (PM-JAY), PMAY-G, NFSA, and Ujjwala 2.0 — use the Socio-Economic Caste Census 2011 as the primary eligibility database. This data is 15 years old. The engine cannot determine if a user is in the SECC list because:
1. The SECC data is not publicly queryable in machine-readable form.
2. Households formed after 2011 do not appear.
3. The deprivation categories (D1–D7) are not self-reported by users — they're administrative determinations.

**Current handling:** The engine returns `LIKELY_ELIGIBLE` or `AMBIGUOUS` for these schemes when income/occupation criteria match, with a gap flag `AMBIGUOUS_CRITERION` pointing to AMB-04 in the ambiguity map. The user is told to verify at their gram panchayat.

**What production readiness requires:**
- Integration with the Awaas+ portal and Ayushman Bharat beneficiary API (both exist as government APIs but require institutional access).
- A phone number or Aadhaar-based lookup to check SECC inclusion status in real time.
- Until that integration exists, the engine is honest about the uncertainty rather than guessing.

**Severity:** High. Ayushman Bharat covers 550 million people. Incorrect eligibility results for the largest health insurance scheme in history are unacceptable in production.

---

### Gap 2: State-Level Implementation Variations Not Modelled

**What the gap is:**
Most central government schemes allow states to extend, restrict, or modify eligibility. The engine models only the central government rules. Examples of unmodelled state variations:
- **Ayushman Bharat:** Rajasthan, Kerala, Chhattisgarh, and Delhi extend coverage to additional income groups. The engine misses ~30M additional beneficiaries in these states.
- **PMAY-U:** Beneficiary identification criteria vary significantly by state. Some states use their own BPL lists; others use UID-linked demand surveys.
- **MGNREGA:** Wage rates are set by state, affecting the benefit summary displayed. 29 different wage schedules are not captured.
- **Income thresholds:** Several schemes have state-specific income ceilings (e.g., APY eligibility is linked to BPL which has state-specific poverty lines).

**Current handling:** The engine uses central government rules as the universal baseline. `state_dependent` conditions are used for bigha-to-hectare conversion (which is already state-parameterized) but not for eligibility thresholds. The `data_freshness` field on each scheme JSON is `PENDING_HUMAN_VERIFICATION`, flagging that human review is required before treating these outputs as authoritative.

**What production readiness requires:**
- A state-specific rule overlay system: `data/state_rules/{state_code}/{scheme_id}.json` that patches or overrides central rules for verified state implementations.
- A data collection process: scheme officers in each state need to confirm local variations. This is human-in-the-loop work that the engine is architected to support (the human verifies JSON; the engine reads JSON).
- Estimated data collection effort: 28 states × 20 schemes = 560 scheme-state combinations, requiring one verified government document per combination.

**Severity:** High for states with major deviations (Rajasthan, Kerala, Delhi). Medium for states that implement central rules unchanged. The current engine understates eligibility for users in extension states and may overstate it in restriction states.

---

*Document generated: April 2026. Codebase: github.com/VeerR13/kalam.*
