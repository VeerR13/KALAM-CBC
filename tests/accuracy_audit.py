"""
accuracy_audit.py — Verifies internal consistency of all 20 scheme JSONs.

Checks:
  1. Rule counts (eligibility + exclusion)
  2. Document counts
  3. Known benefit amount keywords present in benefit_summary
  4. All ambiguity_refs (AMB-XX) exist in ambiguity_map.json
  5. All prerequisite scheme_ids exist as valid schemes
  6. All condition fields map to valid UserProfile fields
  7. All condition types are recognised
  8. No duplicate rule_ids within a scheme
  9. Rule weight/is_mandatory consistency

Saves report to tests/results/accuracy_audit.json

Usage:
    python tests/accuracy_audit.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCHEMES_DIR = ROOT / "data" / "schemes"
AMB_MAP_FILE = ROOT / "data" / "ambiguity_map.json"
PREREQS_FILE = ROOT / "data" / "prerequisites.json"
RESULTS_DIR = ROOT / "tests" / "results"
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))
from src.models.user_profile import UserProfile  # noqa: E402

# ── Reference data ─────────────────────────────────────────────────────────────
VALID_PROFILE_FIELDS = set(UserProfile.model_fields.keys())

VALID_CONDITION_TYPES = {
    "field_check", "range_check", "boolean_check",
    "exclusion", "composite", "state_dependent",
}

# Benefit keyword expectations per scheme: each keyword must appear in benefit_summary
BENEFIT_KEYWORDS: dict[str, list[str]] = {
    "nsap_ignoaps":       ["200", "500"],          # ₹200/mo (60-79), ₹500 (80+)
    "nsap_ignwps":        ["300", "500"],           # ₹300/mo widow, ₹500 (80+)
    "nsap_igndps":        ["300", "500"],           # ₹300/mo disabled, ₹500 (80+)
    "pm_kisan":           ["6,000", "2,000"],       # ₹6000/yr, 3×₹2000
    "pmay_g":             ["1.20 lakh", "1.30 lakh"],
    "pmay_u":             ["BLC", "AHP"],           # housing verticals
    "ayushman_bharat":    ["5 lakh"],
    "ujjwala":            ["LPG", "free"],
    "pm_sym":             ["3,000"],               # ₹3000/month pension
    "apy":                ["1,000", "5,000"],       # ₹1k-₹5k range
    "pmmvy":              ["5,000"],               # ₹5000 maternity benefit
    "sukanya_samriddhi":  ["8.2%"],                # interest rate
    "pm_kisan":           ["6,000"],
    "pm_svanidhi":        ["10,000"],              # ₹10k first loan
    "pm_mudra":           ["50,000"],              # shishu ≤₹50k
    "stand_up_india":     ["10 lakh", "1 crore"],
    "pmegp":              ["15%", "25%"],           # subsidy percentages
    "nfsa":               ["35 kg", "3"],           # AAY 35kg, ₹3/kg
    "pm_vishwakarma":     ["1 lakh", "5%"],
    "mgnrega":            ["100 days"],
    "pmjdy":              ["Zero-balance", "RuPay"],
}

# Known scheme IDs (used to validate prerequisites)
KNOWN_SCHEME_IDS: set[str] = set()  # populated from loaded JSONs


# ── Condition field collector ──────────────────────────────────────────────────
def collect_condition_fields(cond: dict, fields: set, types: set):
    t = cond.get("type")
    if t:
        types.add(t)
    f = cond.get("field")
    if f:
        fields.add(f)
    for sub in cond.get("sub_conditions", []):
        collect_condition_fields(sub, fields, types)
    for sub in cond.get("any_true_fails", []):
        collect_condition_fields(sub, fields, types)
    # state_dependent thresholds
    for thresh in cond.get("state_thresholds", {}).values():
        if isinstance(thresh, dict):
            collect_condition_fields(thresh, fields, types)


# ── Per-scheme audit ───────────────────────────────────────────────────────────
def audit_scheme(
    path: Path,
    valid_amb_ids: set[str],
    valid_prereq_ids: set[str],
) -> dict:
    with open(path) as f:
        data = json.load(f)

    scheme_id = data.get("scheme_id", path.stem)
    issues: list[str] = []
    warnings: list[str] = []

    rules = data.get("rules", [])
    required_docs = data.get("required_documents", [])
    prerequisites = data.get("prerequisites", [])

    # ── 1. Rule counts ─────────────────────────────────────────────────────────
    excl_rules = [r for r in rules if "EX" in r.get("rule_id", "").split("-")[-1][:3]]
    elig_rules = [r for r in rules if r not in excl_rules]
    n_elig = len(elig_rules)
    n_excl = len(excl_rules)
    n_docs = len(required_docs)
    n_prereqs = len(prerequisites)

    if n_elig == 0:
        issues.append("No eligibility rules found")

    # ── 2. No duplicate rule_ids ───────────────────────────────────────────────
    seen_ids: dict[str, int] = {}
    for rule in rules:
        rid = rule.get("rule_id", "")
        seen_ids[rid] = seen_ids.get(rid, 0) + 1
    dupes = [rid for rid, cnt in seen_ids.items() if cnt > 1]
    if dupes:
        issues.append(f"Duplicate rule_ids: {dupes}")

    # ── 3. Condition field + type validation ──────────────────────────────────
    used_fields: set[str] = set()
    used_types: set[str] = set()
    for rule in rules:
        cond = rule.get("condition", {})
        collect_condition_fields(cond, used_fields, used_types)

    invalid_fields = used_fields - VALID_PROFILE_FIELDS
    if invalid_fields:
        issues.append(f"Condition references unknown UserProfile fields: {sorted(invalid_fields)}")

    invalid_types = used_types - VALID_CONDITION_TYPES
    if invalid_types:
        issues.append(f"Unknown condition types: {sorted(invalid_types)}")

    # ── 4. Ambiguity refs ──────────────────────────────────────────────────────
    all_amb_refs: list[str] = []
    for rule in rules:
        all_amb_refs.extend(rule.get("ambiguity_refs", []))

    broken_amb = [ref for ref in all_amb_refs if ref not in valid_amb_ids]
    if broken_amb:
        issues.append(f"Broken ambiguity_refs: {broken_amb}")

    # ── 5. Prerequisite links ─────────────────────────────────────────────────
    broken_prereqs = [p for p in prerequisites if p not in valid_prereq_ids]
    if broken_prereqs:
        issues.append(f"Prerequisites reference unknown scheme_ids: {broken_prereqs}")

    # ── 6. Benefit amount keywords ────────────────────────────────────────────
    benefit_summary = data.get("benefit_summary", "")
    keywords = BENEFIT_KEYWORDS.get(scheme_id, [])
    missing_keywords: list[str] = []
    for kw in keywords:
        if kw not in benefit_summary:
            missing_keywords.append(kw)
    if missing_keywords:
        issues.append(f"benefit_summary missing expected keywords: {missing_keywords}")

    # ── 7. Rule weight / is_mandatory sanity ──────────────────────────────────
    for rule in rules:
        w = rule.get("weight")
        if w is not None and (w < 0 or w > 100):
            warnings.append(f"Rule {rule.get('rule_id')}: unusual weight={w}")
        rid = rule.get("rule_id", "")
        is_excl = "EX" in rid.split("-")[-1][:3]
        if is_excl and rule.get("is_mandatory") is False:
            warnings.append(f"Exclusion rule {rid} has is_mandatory=False (unusual)")

    # ── 8. Required documents have mandatory fields ───────────────────────────
    for doc in required_docs:
        if not doc.get("document"):
            issues.append("Required document entry missing 'document' field")
        if doc.get("processing_time_days") is None:
            warnings.append(f"Document '{doc.get('document', '?')}' missing processing_time_days")

    # ── 9. Data freshness ─────────────────────────────────────────────────────
    freshness = data.get("data_freshness", "")
    if "PENDING" in freshness.upper():
        warnings.append(f"data_freshness is {freshness!r} — not yet verified against PDF")

    overall = "PASS" if not issues else "FAIL"

    return {
        "scheme_id": scheme_id,
        "name": data.get("name", ""),
        "overall": overall,
        "counts": {
            "eligibility_rules": n_elig,
            "exclusion_rules": n_excl,
            "documents": n_docs,
            "prerequisites": n_prereqs,
            "ambiguity_refs": len(all_amb_refs),
        },
        "benefit_keywords_checked": keywords,
        "missing_benefit_keywords": missing_keywords,
        "broken_ambiguity_refs": broken_amb,
        "broken_prerequisites": broken_prereqs,
        "invalid_condition_fields": sorted(invalid_fields),
        "invalid_condition_types": sorted(invalid_types),
        "duplicate_rule_ids": dupes,
        "issues": issues,
        "warnings": warnings,
        "data_freshness": freshness,
    }


# ── Master runner ──────────────────────────────────────────────────────────────
def run() -> dict:
    # Load ambiguity map
    with open(AMB_MAP_FILE) as f:
        amb_map = json.load(f)
    valid_amb_ids = {entry["id"] for entry in amb_map}

    # Load all scheme files to get valid IDs
    scheme_files = sorted(SCHEMES_DIR.glob("*.json"))
    all_scheme_ids = {p.stem for p in scheme_files}
    KNOWN_SCHEME_IDS.update(all_scheme_ids)

    # Load prerequisites.json to cross-check
    with open(PREREQS_FILE) as f:
        prereqs_data = json.load(f)
    prereq_scheme_ids = set()
    for edge in prereqs_data.get("edges", []):
        prereq_scheme_ids.add(edge["from"])
        prereq_scheme_ids.add(edge["to"])

    # Union of all known valid scheme IDs
    valid_prereq_ids = all_scheme_ids | prereq_scheme_ids

    scheme_reports = []
    for path in scheme_files:
        result = audit_scheme(path, valid_amb_ids, valid_prereq_ids)
        scheme_reports.append(result)

    # Summary
    n_pass = sum(1 for r in scheme_reports if r["overall"] == "PASS")
    n_fail = len(scheme_reports) - n_pass
    all_issues = []
    for r in scheme_reports:
        for issue in r["issues"]:
            all_issues.append(f"[{r['scheme_id']}] {issue}")

    # Print report card
    print(f"\n{'='*72}")
    print(f"  KALAM ACCURACY AUDIT — {len(scheme_reports)} schemes")
    print(f"{'='*72}")
    print(f"  {'SCHEME':<24}  {'RULES':>5}  {'EXCL':>4}  {'DOCS':>4}  {'AMB':>4}  {'STATUS'}")
    print(f"  {'─'*64}")
    for r in scheme_reports:
        c = r["counts"]
        issues_flag = " ⚠️" if r["issues"] else ""
        warns_flag = " ℹ" if r["warnings"] else ""
        print(
            f"  {r['scheme_id']:<24}  {c['eligibility_rules']:>5}  {c['exclusion_rules']:>4}  "
            f"{c['documents']:>4}  {c['ambiguity_refs']:>4}  {r['overall']}{issues_flag}{warns_flag}"
        )

    if all_issues:
        print(f"\n  {'─'*64}")
        print(f"  ISSUES FOUND:")
        for issue in all_issues:
            print(f"  ✗ {issue}")

    all_warnings = []
    for r in scheme_reports:
        for w in r["warnings"]:
            all_warnings.append(f"[{r['scheme_id']}] {w}")
    if all_warnings:
        print(f"\n  WARNINGS:")
        for w in all_warnings:
            print(f"  ℹ {w}")

    verdict = "PASS" if n_fail == 0 else "FAIL"
    print(f"\n  Total: {n_pass} PASS / {n_fail} FAIL  →  VERDICT: {verdict}")
    print(f"{'='*72}\n")

    return {
        "verdict": verdict,
        "total": len(scheme_reports),
        "pass": n_pass,
        "fail": n_fail,
        "schemes": scheme_reports,
        "all_issues": all_issues,
        "all_warnings": all_warnings,
        "ambiguity_map_entries": len(valid_amb_ids),
        "prerequisites_edges": len(prereqs_data.get("edges", [])),
    }


def main():
    report = run()
    out = RESULTS_DIR / "accuracy_audit.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved to {out.relative_to(ROOT)}")
    sys.exit(0 if report["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
