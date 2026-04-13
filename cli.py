"""Kalam CLI — Hinglish welfare eligibility engine."""
import json
import os
import re
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from src.conversation.contradiction import detect_contradictions
from src.conversation.follow_up import get_next_question
from src.conversation.system_prompt import SYSTEM_PROMPT
from src.engine.confidence import ConfidenceScorer, MatchStatus
from src.models.user_profile import (
    normalize_bigha_to_hectares,
    normalize_gaj_to_hectares,
    normalize_sqft_to_hectares,
)
from src.engine.gap_analyzer import GapAnalyzer
from src.engine.rule_engine import evaluate_scheme
from src.engine.sequencer import PrerequisiteDAG
from src.formatter import console, format_results_table, format_gaps, format_application_order
from src.loader import load_all_schemes
from src.models.match_result import MatchResult, RuleEvaluation
from src.models.scheme import Scheme
from src.models.user_profile import UserProfile

load_dotenv()
app = typer.Typer(add_completion=False)


# ── Engine pipeline ────────────────────────────────────────────────────────────

def run_engine_for_profile(profile: UserProfile) -> list[MatchResult]:
    """Evaluate all schemes for a profile and return MatchResults."""
    results = []
    for scheme_data in load_all_schemes():
        scheme = Scheme(**scheme_data)
        rule_results = evaluate_scheme(scheme, profile)
        confidence, status = ConfidenceScorer.score(scheme, rule_results)
        rule_map = {r.rule_id: r for r in scheme.rules}
        match_result = MatchResult(
            scheme_id=scheme.scheme_id,
            scheme_name=scheme.name,
            status=status,
            confidence=confidence,
            rule_evaluations=[
                RuleEvaluation(
                    rule_id=rid, result=res, explanation=exp,
                    is_mandatory=rule_map[rid].is_mandatory,
                    weight=rule_map[rid].weight,
                )
                for rid, res, exp in rule_results if rid in rule_map
            ],
            prerequisite_scheme_ids=scheme.prerequisites,
            required_documents=[d.model_dump() for d in scheme.required_documents],
            benefit_summary=scheme.benefit_summary,
        )
        match_result.gaps = GapAnalyzer.analyze(match_result)
        results.append(match_result)
    return results


def _show_results(profile: UserProfile) -> None:
    console.print("\n[dim]Running eligibility check across 20 schemes...[/dim]\n")
    results = run_engine_for_profile(profile)
    format_results_table(results)
    for r in results:
        if r.status in (MatchStatus.LIKELY_ELIGIBLE, MatchStatus.AMBIGUOUS) and r.gaps:
            format_gaps(r)
    eligible_ids = [r.scheme_id for r in results
                    if r.status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE)]
    dag = PrerequisiteDAG.from_data_file()
    format_application_order(dag.topological_order(eligible_ids))


def _run_edge_cases() -> None:
    fixtures_dir = Path(__file__).parent / "tests" / "fixtures" / "profiles"
    for profile_file in sorted(fixtures_dir.glob("edge_*.json")):
        console.print(f"\n[bold cyan]── {profile_file.stem} ──[/bold cyan]")
        data = json.loads(profile_file.read_text())
        try:
            _show_results(UserProfile(**data))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


# ── NLP parsing ────────────────────────────────────────────────────────────────

def _coerce_types(raw: dict) -> dict:
    """Coerce extracted values to the types UserProfile expects."""
    int_fields = {"age", "annual_income", "family_size", "num_children",
                  "num_live_births", "disability_percent"}
    bool_fields = {"is_urban", "has_bank_account", "has_aadhaar", "is_aadhaar_linked",
                   "is_govt_employee", "is_income_tax_payer", "is_epf_member",
                   "has_existing_enterprise", "has_girl_child_under_10",
                   "is_pregnant_or_lactating", "income_is_approximate"}
    float_fields = {"land_area_hectares"}
    truthy = {"true", "yes", "haan", "hai", "h", "y", "1"}

    result = {}
    for k, v in raw.items():
        if v is None:
            continue
        try:
            if k in int_fields:
                result[k] = int(v)
            elif k in bool_fields:
                result[k] = v if isinstance(v, bool) else str(v).lower() in truthy
            elif k in float_fields:
                result[k] = float(v)
            else:
                result[k] = v
        except (ValueError, TypeError):
            pass  # skip values that can't be coerced
    return result


def _regex_parse(answer: str, question: str) -> dict:
    """Fallback: extract fields from a single answer using keyword matching.
    Used when no ANTHROPIC_API_KEY is set or the API call fails."""
    al = answer.lower().strip()
    extracted: dict = {}

    if question and ("umar" in question.lower() or "age" in question.lower()):
        nums = re.findall(r"\d+", al)
        if nums:
            extracted["age"] = int(nums[0])
    if question and "state" in question.lower():
        extracted["state"] = answer.strip().title()
    if question and ("gaon" in question.lower() or "urban" in question.lower()):
        extracted["is_urban"] = al in ("shehar", "city", "urban", "town", "yes", "haan")
    if question and "category" in question.lower():
        for cat in ("General", "OBC", "SC", "ST"):
            if cat.lower() in al:
                extracted["caste_category"] = cat
                break
    if question and ("purush" in question.lower() or "gender" in question.lower()):
        if any(x in al for x in ("purush", "male", "mr")):
            extracted["gender"] = "M"
        elif any(x in al for x in ("mahila", "female", "woman", "ms")):
            extracted["gender"] = "F"
        elif "transgender" in al:
            extracted["gender"] = "Transgender"
    if question and ("income" in question.lower() or "saalana" in question.lower()):
        nums = re.findall(r"\d+", al.replace(",", ""))
        if nums:
            extracted["annual_income"] = int(nums[0])
    if question and ("kaam" in question.lower() or "occupation" in question.lower()):
        extracted["occupation"] = answer.strip()
    if question and ("ghar" in question.lower() or "family" in question.lower()):
        nums = re.findall(r"\d+", al)
        if nums:
            extracted["family_size"] = int(nums[0])
    if question and "linked" in question.lower():
        extracted["is_aadhaar_linked"] = al in ("haan", "yes", "hai", "h", "y")
    if question and "bank" in question.lower():
        extracted["has_bank_account"] = al in ("haan", "yes", "hai", "h", "y")
    if question and "aadhaar" in question.lower():
        extracted["has_aadhaar"] = al in ("haan", "yes", "hai", "h", "y")

    # Land area — detect unit keyword from the answer itself
    if question and ("zameen" in question.lower() or "land" in question.lower()):
        nums = re.findall(r"[\d.]+", al.replace(",", ""))
        if nums:
            val = float(nums[0])
            if any(u in al for u in ("sqft", "sq ft", "square feet", "feet")):
                extracted["land_area_hectares"] = normalize_sqft_to_hectares(val)
            elif any(u in al for u in ("gaj", "गज", "sq yard", "square yard")):
                extracted["land_area_hectares"] = normalize_gaj_to_hectares(val)
            elif any(u in al for u in ("acre", "एकड़")):
                extracted["land_area_hectares"] = round(val * 0.404686, 4)
            elif any(u in al for u in ("bigha", "बीघा")):
                extracted["land_area_hectares"] = normalize_bigha_to_hectares(val, "")
            elif any(u in al for u in ("hectare", "hectares", "ha")):
                extracted["land_area_hectares"] = round(val, 4)

    return extracted


def _nlp_parse(answer: str, profile_so_far: dict, question: Optional[str]) -> dict:
    """Extract profile fields from natural language using Claude API.
    Falls back to regex parser if API key is unavailable or call fails."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[dim](No ANTHROPIC_API_KEY — using basic parser)[/dim]")
        return _regex_parse(answer, question or "")

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)

        context_parts = []
        if question:
            context_parts.append(f"Question asked: {question}")
        context_parts.append(f"User said: {answer}")
        if profile_so_far:
            known = {k: v for k, v in profile_so_far.items() if v is not None}
            if known:
                context_parts.append(f"Already collected: {json.dumps(known, ensure_ascii=False)}")

        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "\n".join(context_parts)}],
        )

        text = resp.content[0].text.strip()
        # Strip markdown code fences if model wraps output
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        result = json.loads(text)
        extracted = result.get("extracted_fields", {})

        # Surface any contradictions Claude noticed
        for c in result.get("contradictions", []):
            console.print(f"[yellow]⚠  {c}[/yellow]")

        return _coerce_types(extracted)

    except Exception as exc:
        console.print(f"[dim](Claude parse error: {exc} — using basic parser)[/dim]")
        return _regex_parse(answer, question or "")


# ── Interactive conversation ───────────────────────────────────────────────────

def _run_conversation() -> UserProfile:
    """Collect profile via natural language + targeted follow-ups."""
    profile_data: dict = {}

    # Opening: let user describe their full situation at once
    console.print(
        "\n[bold]Namaste![/bold] Apni situation batayein — kahan rehte hain, "
        "kya kaam karte hain, income kitni hai, parivaar mein kitne log hain, etc."
    )
    console.print("[dim](Hindi, English, ya Hinglish — jaise comfortable ho. "
                  "Jitna pata ho utna batayein.)[/dim]\n")

    opening = input("You: ").strip()
    if opening.lower() in ("quit", "exit", "q"):
        raise typer.Exit()

    console.print("[dim]Samajh raha hoon...[/dim]")
    extracted = _nlp_parse(opening, {}, None)
    profile_data.update(extracted)

    if profile_data:
        filled = ", ".join(k for k in profile_data)
        console.print(f"[dim]Samjha: {filled}[/dim]")

    for c in detect_contradictions(profile_data):
        console.print(f"[yellow]⚠  {c.description}[/yellow]")
        console.print(f"[dim]   → {c.suggestion}[/dim]")

    # Targeted follow-ups for remaining missing fields
    while True:
        question = get_next_question(profile_data)
        if question is None:
            break

        console.print(f"\n[bold yellow]?[/bold yellow] {question}")
        answer = input("You: ").strip()

        if answer.lower() in ("quit", "exit", "q"):
            raise typer.Exit()
        if answer.strip() in ("", "skip", "pata nahi", "nahi pata"):
            console.print("[dim]  (skipping — will show as 'need more info')[/dim]")
            continue

        extracted = _nlp_parse(answer, profile_data, question)
        profile_data.update({k: v for k, v in extracted.items() if v is not None})

        for c in detect_contradictions(profile_data):
            console.print(f"[yellow]⚠  {c.description}[/yellow]")
            console.print(f"[dim]   → {c.suggestion}[/dim]")

    return UserProfile(**{k: v for k, v in profile_data.items() if v is not None})


# ── Entry point ────────────────────────────────────────────────────────────────

@app.command()
def main(
    profile_json: Optional[Path] = typer.Option(None, "--profile", help="Load profile from JSON file"),
    test_edge_cases: bool = typer.Option(False, "--test-edge-cases", help="Run all 10 edge case profiles"),
) -> None:
    """Kalam — AI-powered welfare scheme eligibility engine (Hinglish)."""
    console.print(Panel(
        "[bold cyan]KALAM — Welfare Scheme Eligibility Engine[/bold cyan]\n"
        "   Sarkari yojanaon ke liye aapki eligibility check karein.\n"
        "   Type 'quit' to exit  ·  Type 'skip' / 'pata nahi' to skip a question.",
        border_style="cyan",
    ))

    if test_edge_cases:
        _run_edge_cases()
        return

    if profile_json:
        _show_results(UserProfile(**json.loads(profile_json.read_text())))
        return

    # Interactive conversational mode
    try:
        profile = _run_conversation()
    except Exception as e:
        console.print(f"[red]Could not build profile: {e}[/red]")
        raise typer.Exit(1)

    _show_results(profile)


if __name__ == "__main__":
    app()
