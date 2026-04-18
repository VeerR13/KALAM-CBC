"""Deterministic rule evaluator. Takes a Rule + UserProfile → RuleResult + explanation."""
from src.models.scheme import Rule, RuleCondition, RuleResult, Scheme
from src.models.user_profile import UserProfile


def _str_in(value: object, collection: list) -> bool:
    """Check membership with case-insensitive comparison for strings."""
    if isinstance(value, str):
        value_lower = value.lower()
        return any(
            (v.lower() if isinstance(v, str) else v) == value_lower
            for v in collection
        )
    return value in collection


def evaluate_rule(rule: Rule, profile: UserProfile) -> tuple[RuleResult, str]:
    """Evaluate a single rule against a profile. Returns (RuleResult, explanation)."""
    cond = rule.condition

    if cond.type == "field_check":
        value = getattr(profile, cond.field, None)
        if value is None:
            return RuleResult.MISSING, f"{cond.field} not provided"

        # Special handling for list-type fields (e.g. previous_scheme_loans)
        if isinstance(value, list):
            # An empty list means no prior scheme loans — PASS if no values expected
            if not value:
                return RuleResult.PASS, f"{cond.field}=[] (no prior loans)"
            # Check if any item in the list matches ambiguous_values
            if cond.ambiguous_values:
                matched = [item for item in value if _str_in(item, cond.ambiguous_values)]
                if matched:
                    return RuleResult.AMBIGUOUS, (
                        f"{cond.field} contains ambiguous item(s): {matched}"
                    )
            # If values list is empty, non-matching items are neutral (PASS)
            # Only fail if a non-empty disqualifying values list was explicitly defined
            if not cond.values:
                return RuleResult.PASS, f"{cond.field} has prior scheme activity (none disqualifying for this rule)"
            return RuleResult.FAIL, f"{cond.field}={value} contains disqualifying loan(s)"

        # Scalar field_check with case-insensitive string matching
        if cond.values is not None and _str_in(value, cond.values):
            return RuleResult.PASS, f"{cond.field}={value} matches required {cond.values}"
        if cond.ambiguous_values and _str_in(value, cond.ambiguous_values):
            return RuleResult.AMBIGUOUS, f"{cond.field}={value} is ambiguous — eligibility unclear"
        return RuleResult.FAIL, f"{cond.field}={value} not in required {cond.values}"

    elif cond.type == "boolean_check":
        value = getattr(profile, cond.field, None)
        if value is None:
            return RuleResult.MISSING, f"{cond.field} not provided"
        if value == cond.equals:
            return RuleResult.PASS, f"{cond.field} is {value}"
        return RuleResult.FAIL, f"{cond.field} is {value}, required {cond.equals}"

    elif cond.type == "range_check":
        value = getattr(profile, cond.field, None)
        if value is None:
            return RuleResult.MISSING, f"{cond.field} not provided"
        in_range = True
        if cond.min is not None and value < cond.min:
            in_range = False
        if cond.max is not None and value > cond.max:
            in_range = False
        if in_range:
            return RuleResult.PASS, f"{cond.field}={value} within [{cond.min}, {cond.max}]"
        return RuleResult.FAIL, f"{cond.field}={value} outside [{cond.min}, {cond.max}]"

    elif cond.type == "exclusion":
        if not cond.any_true_fails:
            return RuleResult.PASS, "No exclusion criteria"
        for criterion in cond.any_true_fails:
            field = criterion.get("field")
            expected = criterion.get("equals")
            value = getattr(profile, field, None)
            if value is None:
                continue  # Missing field doesn't trigger exclusion
            if value == expected:
                return RuleResult.FAIL, f"Excluded: {field}={value}"
        return RuleResult.PASS, "No exclusion criteria matched"

    elif cond.type == "composite":
        if not cond.sub_conditions:
            return RuleResult.MISSING, "No sub-conditions defined"
        sub_results = []
        for sub in cond.sub_conditions:
            sub_rule = Rule(
                rule_id=f"{rule.rule_id}_sub",
                parameter="sub",
                description="sub",
                condition=RuleCondition(**sub),
                is_mandatory=False,
                weight=0,
            )
            sub_result, sub_exp = evaluate_rule(sub_rule, profile)
            sub_results.append((sub_result, sub_exp))
        logic = cond.logic or "AND"
        if logic == "AND":
            if all(r == RuleResult.PASS for r, _ in sub_results):
                return RuleResult.PASS, "All sub-conditions met"
            if any(r == RuleResult.FAIL for r, _ in sub_results):
                return RuleResult.FAIL, "One or more sub-conditions failed"
            if any(r == RuleResult.AMBIGUOUS for r, _ in sub_results):
                return RuleResult.AMBIGUOUS, "One or more sub-conditions ambiguous"
            return RuleResult.MISSING, "Insufficient data for composite rule"
        else:  # OR
            if any(r == RuleResult.PASS for r, _ in sub_results):
                return RuleResult.PASS, "At least one sub-condition met"
            if any(r == RuleResult.AMBIGUOUS for r, _ in sub_results):
                return RuleResult.AMBIGUOUS, "Sub-conditions ambiguous"
            if all(r == RuleResult.MISSING for r, _ in sub_results):
                return RuleResult.MISSING, "Insufficient data for composite rule"
            return RuleResult.FAIL, "No sub-conditions met"

    elif cond.type == "state_dependent":
        if not cond.state_thresholds:
            return RuleResult.MISSING, "No state thresholds defined"
        threshold = cond.state_thresholds.get(profile.state, cond.state_thresholds.get("default"))
        if threshold is None:
            return RuleResult.AMBIGUOUS, f"No threshold defined for state={profile.state}"
        value = getattr(profile, cond.field, None)
        if value is None:
            return RuleResult.MISSING, f"{cond.field} not provided"
        if value <= threshold:
            return RuleResult.PASS, f"{cond.field}={value} <= state threshold {threshold}"
        return RuleResult.FAIL, f"{cond.field}={value} exceeds state threshold {threshold}"

    return RuleResult.MISSING, f"Unknown condition type: {cond.type}"


def evaluate_scheme(scheme: Scheme, profile: UserProfile) -> list[tuple[str, RuleResult, str]]:
    """Evaluate all rules in a scheme. Returns list of (rule_id, RuleResult, explanation)."""
    return [(rule.rule_id, *evaluate_rule(rule, profile)) for rule in scheme.rules]
