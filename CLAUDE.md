# Kalam — Claude Code Guide

This project is built from the approved spec at `docs/superpowers/plans/2026-04-10-kalam-build.md`.

## Quick orientation

- **All eligibility rules live in JSON** — `data/schemes/*.json`. Never hardcode eligibility logic in Python.
- **`data_freshness`** on every scheme JSON is `PENDING_HUMAN_VERIFICATION` until the human verifies against official PDFs (place PDFs in `data/pdfs/`).
- **Run tests** before committing: `pytest -v` (87 tests, should all pass)
- **Linting**: `ruff check src/ tests/`

## Project structure

```
src/
  models/         # Pydantic models: UserProfile, Scheme, MatchResult
  engine/         # rule_engine, confidence, gap_analyzer, doc_checklist, sequencer
  conversation/   # system_prompt, follow_up, contradiction (Hinglish NLP)
  loader.py       # Loads JSON data files
  formatter.py    # Rich CLI output
data/
  schemes/        # 20 scheme JSON rule files
  ambiguity_map.json
  documents.json
  prerequisites.json
  pdfs/           # ★ Human drops official PDFs here for verification
tests/
  fixtures/profiles/         # 10 edge case profiles
  fixtures/expected_results/ # Expected engine outputs
cli.py            # Entry point: python cli.py
```

## Running the CLI

```bash
# Interactive mode
python cli.py

# Load a profile JSON directly
python cli.py --profile tests/fixtures/profiles/edge_02_leased_farmer.json

# Run all 10 edge cases
python cli.py --test-edge-cases
```

## Human integration points

1. **Verify scheme JSONs** against PDFs → edit `data/schemes/*.json`, change `data_freshness` to `VERIFIED_AGAINST_PDF_YYYY-MM-DD`
2. **Add ambiguity entries** to `data/ambiguity_map.json` when discovered
3. **Run edge cases** and compare actual vs expected: `python cli.py --test-edge-cases`
4. **Test Hinglish parsing** manually and log results in `docs/hinglish_test_log.md`

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
