"""Kalam Web — FastAPI application."""
import json
import os
import re
from pathlib import Path
from typing import Optional

from urllib.parse import urlencode as _urlencode

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

from src.engine.benefit_calculator import calculate_benefit
from src.engine.bureaucratic_distance import BureaucraticDistanceCalculator
from src.engine.confidence import ConfidenceScorer, MatchStatus
from src.engine.gap_analyzer import GapAnalyzer
from src.engine.interaction_detector import InteractionDetector
from src.engine.life_events import LifeEventProjector
from src.engine.path_optimizer import PathOptimizer
from src.engine.rule_engine import evaluate_scheme
from src.engine.sensitivity import SensitivityAnalyzer
from src.engine.sequencer import PrerequisiteDAG
from src.loader import load_all_schemes
from src.models.match_result import MatchResult, RuleEvaluation
from src.models.scheme import Scheme
from src.models.user_profile import (
    UserProfile,
    normalize_bigha_to_hectares,
    normalize_gaj_to_hectares,
    normalize_sqft_to_hectares,
)

app = FastAPI()
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")
templates.env.filters["urlencode"] = lambda d: _urlencode(d) if isinstance(d, dict) else str(d)

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman & Nicobar Islands", "Chandigarh", "Dadra & Nagar Haveli and Daman & Diu",
    "Delhi", "Jammu & Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

STATUS_ORDER = {
    MatchStatus.ELIGIBLE: 0,
    MatchStatus.LIKELY_ELIGIBLE: 1,
    MatchStatus.AMBIGUOUS: 2,
    MatchStatus.INSUFFICIENT_DATA: 3,
    MatchStatus.INELIGIBLE: 4,
}

SCHEME_ICONS = {
    "pm_kisan": "🌾",
    "mgnrega": "⛏️",
    "ayushman_bharat": "🏥",
    "pmay_g": "🏠",
    "pmay_u": "🏙️",
    "pmjdy": "🏦",
    "ujjwala": "🔥",
    "nsap_ignoaps": "👴",
    "nsap_ignwps": "👩",
    "nsap_igndps": "♿",
    "apy": "📊",
    "pm_sym": "👷",
    "pm_svanidhi": "🛒",
    "pm_mudra": "💼",
    "pmegp": "🏭",
    "standup_india": "🚀",
    "sukanya_samriddhi": "👧",
    "pmmvy": "🤰",
    "nfsa": "🌾",
    "pm_vishwakarma": "🔨",
}


def _evaluate_scheme(scheme: Scheme, profile: UserProfile) -> MatchResult:
    """Evaluate a single scheme and return a MatchResult with gap analysis."""
    rule_results = evaluate_scheme(scheme, profile)
    confidence, status = ConfidenceScorer.score(scheme, rule_results)
    rule_map = {r.rule_id: r for r in scheme.rules}
    result = MatchResult(
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
            for rid, res, exp in rule_results
            if rid in rule_map
        ],
        prerequisite_scheme_ids=scheme.prerequisites,
        required_documents=[d.model_dump() for d in scheme.required_documents],
        benefit_summary=scheme.benefit_summary,
    )
    result.gaps = GapAnalyzer.analyze(result)
    return result


def _run_engine(profile: UserProfile) -> list[MatchResult]:
    """Run full engine pipeline and return sorted MatchResult list."""
    results = [_evaluate_scheme(Scheme(**sd), profile) for sd in load_all_schemes()]
    results.sort(key=lambda r: STATUS_ORDER.get(r.status, 99))
    return results


def _build_profile(form: dict) -> UserProfile:
    """Map flat form dict → UserProfile, handling type coercion and unit conversion."""
    land_unit = form.get("land_unit", "hectare")
    land_area_raw = form.get("land_area")
    land_area_hectares = None
    state = form.get("state", "")

    if land_area_raw:
        try:
            val = float(land_area_raw)
            if land_unit == "bigha":
                land_area_hectares = normalize_bigha_to_hectares(val, state)
            elif land_unit == "acre":
                land_area_hectares = round(val * 0.404686, 4)
            elif land_unit == "gaj":
                land_area_hectares = normalize_gaj_to_hectares(val)
            elif land_unit == "sqft":
                land_area_hectares = normalize_sqft_to_hectares(val)
            else:
                land_area_hectares = round(val, 4)
        except (ValueError, TypeError):
            pass

    def _bool(key: str, default: Optional[bool] = None) -> Optional[bool]:
        v = form.get(key)
        if v is None:
            return default
        return v in ("yes", "true", "1", "on")

    def _int(key: str, default: Optional[int] = None) -> Optional[int]:
        v = form.get(key)
        if v is None or v == "":
            return default
        try:
            return int(v)
        except (ValueError, TypeError):
            return default

    disability_map = {"none": 0, "40_79": 60, "80_plus": 85}
    disability_raw = form.get("disability_percent")
    disability_percent = disability_map.get(disability_raw) if disability_raw else None

    is_urban_raw = form.get("is_urban")
    is_urban = (is_urban_raw == "urban") if is_urban_raw else None

    return UserProfile(
        age=_int("age"),
        gender=form.get("gender") or None,
        state=state or None,
        is_urban=is_urban,
        caste_category=form.get("caste_category") or None,
        marital_status=form.get("marital_status") or None,
        annual_income=_int("annual_income"),
        occupation=form.get("occupation") or None,
        family_size=_int("family_size"),
        num_children=_int("num_children"),
        has_girl_child_under_10=_bool("has_girl_child_under_10"),
        is_pregnant_or_lactating=_bool("is_pregnant_or_lactating"),
        num_live_births=_int("num_live_births"),
        land_ownership=form.get("land_ownership") or None,
        land_area_hectares=land_area_hectares,
        has_existing_enterprise=_bool("has_enterprise"),
        has_aadhaar=_bool("has_aadhaar"),
        has_bank_account=_bool("has_bank_account"),
        is_aadhaar_linked=_bool("is_aadhaar_linked"),
        has_ration_card=form.get("has_ration_card") or None,
        disability_percent=disability_percent,
        is_govt_employee=_bool("is_govt_employee"),
        is_income_tax_payer=_bool("is_income_tax_payer"),
        is_epf_member=_bool("is_epf_member"),
        has_motorized_vehicle=_bool("has_motorized_vehicle"),
        has_mechanized_farm_equipment=_bool("has_mechanized_farm_equipment"),
        has_kisan_credit_card=_bool("has_kisan_credit_card"),
        has_refrigerator=_bool("has_refrigerator"),
        has_landline=_bool("has_landline"),
        has_pucca_house=_bool("has_pucca_house"),
    )


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html")


@app.get("/details", response_class=HTMLResponse)
async def details_form(request: Request):
    return templates.TemplateResponse(request, "details.html", {"states": STATES})


@app.get("/results", response_class=HTMLResponse)
async def results_get(request: Request):
    """Same as POST /results but reads profile from query params (for back-navigation)."""
    from urllib.parse import parse_qs
    qs = str(request.query_params)
    form = {k: v[0] for k, v in parse_qs(qs).items()} if qs else {}
    if not form:
        return RedirectResponse("/details")
    return await _render_results(request, form)


async def _render_results(request: Request, form: dict):
    """Shared results rendering — used by both GET (back nav) and POST (form submit)."""
    from src.models.scheme import RuleResult

    profile = _build_profile(form)
    all_results = _run_engine(profile)

    dag = PrerequisiteDAG.from_data_file()
    eligible_ids = [
        r.scheme_id for r in all_results
        if r.status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE)
    ]
    app_order = dag.topological_order(eligible_ids)

    def _missing_mandatory_count(r: MatchResult) -> int:
        return sum(
            1 for ev in r.rule_evaluations
            if ev.is_mandatory and ev.result == RuleResult.MISSING
        )

    insufficient_sorted = sorted(
        [r for r in all_results if r.status == MatchStatus.INSUFFICIENT_DATA],
        key=_missing_mandatory_count,
    )
    grouped = {
        "eligible":    [r for r in all_results if r.status == MatchStatus.ELIGIBLE],
        "likely":      [r for r in all_results if r.status == MatchStatus.LIKELY_ELIGIBLE],
        "ambiguous":   [r for r in all_results if r.status == MatchStatus.AMBIGUOUS],
        "insufficient": insufficient_sorted,
        "ineligible":  [r for r in all_results if r.status == MatchStatus.INELIGIBLE],
    }

    # ── Benefit calculations per eligible scheme ──────────────────────────────
    benefits: dict[str, object] = {}
    for r in all_results:
        if r.status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE,
                        MatchStatus.AMBIGUOUS):
            try:
                benefits[r.scheme_id] = calculate_benefit(r.scheme_id, profile)
            except Exception:
                pass

    # ── Interaction detection + optimal path ─────────────────────────────────
    detector = InteractionDetector()
    interactions = detector.detect(eligible_ids)

    scheme_name_map = {r.scheme_id: r.scheme_name for r in all_results}
    optimizer = PathOptimizer(scheme_name_map)
    optimal_path = optimizer.recommend(profile, eligible_ids, interactions)

    # ── Sensitivity analysis ──────────────────────────────────────────────────
    current_statuses = {r.scheme_id: r.status for r in all_results}
    sensitivity_flags = SensitivityAnalyzer().analyze(profile, current_statuses)

    # ── Life event projection ─────────────────────────────────────────────────
    life_events = LifeEventProjector().project(profile, current_statuses)

    # ── Bureaucratic distance ─────────────────────────────────────────────────
    bur_calc = BureaucraticDistanceCalculator()
    from src.models.scheme import Scheme as _Scheme
    schemes_map = {sd["scheme_id"]: _Scheme(**sd) for sd in load_all_schemes()}
    distances: dict[str, object] = {}
    for r in all_results:
        if r.status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE, MatchStatus.AMBIGUOUS):
            unmet_prereqs = [p for p in (r.prerequisite_scheme_ids or []) if p not in eligible_ids]
            distances[r.scheme_id] = bur_calc.calculate(
                profile, schemes_map[r.scheme_id], unmet_prereqs
            )

    return templates.TemplateResponse(request, "results.html", {
        "profile": profile,
        "profile_dict": form,
        "grouped": grouped,
        "all_results": all_results,
        "app_order": app_order,
        "icons": SCHEME_ICONS,
        "total": len(all_results),
        "eligible_count": len(grouped["eligible"]) + len(grouped["likely"]),
        "benefits": benefits,
        "interactions": interactions,
        "optimal_path": optimal_path,
        "sensitivity_flags": sensitivity_flags,
        "life_events": life_events,
        "distances": distances,
    })


@app.post("/results", response_class=HTMLResponse)
async def results(request: Request):
    form_data = await request.form()
    return await _render_results(request, dict(form_data))


@app.get("/scheme/{scheme_id}", response_class=HTMLResponse)
async def scheme_detail(request: Request, scheme_id: str):
    # Profile is passed as query params (encoded from results page)
    from urllib.parse import parse_qs  # noqa: PLC0415
    qs = str(request.query_params)
    form = {k: v[0] for k, v in parse_qs(qs).items()} if qs else {}

    if not form:
        return RedirectResponse("/details")

    try:
        profile = _build_profile(form)
    except Exception:
        return RedirectResponse("/details")

    schemes_data = load_all_schemes()
    scheme_obj = None
    for sd in schemes_data:
        if sd["scheme_id"] == scheme_id:
            scheme_obj = Scheme(**sd)
            break

    if not scheme_obj:
        return RedirectResponse("/results")

    match_result = _evaluate_scheme(scheme_obj, profile)

    return templates.TemplateResponse(request, "scheme_detail.html", {
        "scheme": scheme_obj,
        "result": match_result,
        "icon": SCHEME_ICONS.get(scheme_id, "📋"),
        "profile_qs": qs,
    })


@app.post("/api/recheck", response_class=JSONResponse)
async def recheck(request: Request):
    """Re-evaluate a single scheme after user answers an inline mini-form."""
    body = await request.json()
    base_form: dict = body.get("profile", {})
    new_fields: dict = body.get("new_fields", {})
    scheme_id: str = body.get("scheme_id", "")

    merged = {**base_form, **new_fields}
    profile = _build_profile(merged)

    schemes_data = load_all_schemes()
    scheme_obj = None
    for sd in schemes_data:
        if sd["scheme_id"] == scheme_id:
            scheme_obj = Scheme(**sd)
            break

    if not scheme_obj:
        return JSONResponse({"error": "scheme not found"}, status_code=404)

    result = _evaluate_scheme(scheme_obj, profile)
    return JSONResponse({
        "scheme_id": scheme_id,
        "status": result.status.value,
        "confidence": round(result.confidence, 1),
    })


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request, "chat.html")


@app.post("/api/chat", response_class=JSONResponse)
async def chat_api(request: Request):
    """Process a chat message, extract profile fields, return a follow-up reply."""
    body = await request.json()
    message: str = body.get("message", "")
    profile: dict = body.get("profile", {})
    turn: int = body.get("turn", 0)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        # Fallback: basic keyword extraction
        extracted = _chat_regex_extract(message)
        reply = _chat_fallback_reply(extracted, profile, turn)
        return JSONResponse({"reply": reply, "extracted": extracted})

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)

        known = {k: v for k, v in profile.items() if v is not None and v != ""}
        context = []
        if known:
            context.append(f"Already collected: {json.dumps(known, ensure_ascii=False)}")
        context.append(f"User just said: {message}")

        system = """You are a friendly government welfare eligibility assistant for India. Speak a mix of Hindi and English (Hinglish is fine).

Your job has two parts:
1. Extract any profile fields the user mentioned and return them in extracted_fields JSON.
2. Ask a natural follow-up question to collect what's still missing — keep it conversational, not like a form.

Priority fields (collect in order): age, state, is_urban (village/city), caste_category (General/OBC/SC/ST), annual_income, occupation, family_size, has_aadhaar, has_bank_account.

VALID VALUES:
- gender: "M" | "F" | "Transgender"
- caste_category: "General" | "OBC" | "SC" | "ST"
- is_urban (bool): true=city, false=village
- land_ownership: "owns" | "leases" | "sharecrop" | "none"
- marital_status: "unmarried" | "married" | "widowed" | "divorced"
- Boolean: has_bank_account, has_aadhaar, is_aadhaar_linked, is_govt_employee, is_income_tax_payer, is_epf_member
- Integer: age, annual_income, family_size
- State: full name e.g. "Uttar Pradesh"

Return exactly this JSON:
{
  "extracted_fields": { ...only what user mentioned... },
  "reply": "Your friendly follow-up message (1-2 sentences, mix Hindi+English)"
}"""

        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": "\n".join(context)}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        return JSONResponse({
            "reply": result.get("reply", "Theek hai! Kuch aur batayein."),
            "extracted": result.get("extracted_fields", {}),
        })
    except Exception as exc:
        extracted = _chat_regex_extract(message)
        reply = _chat_fallback_reply(extracted, profile, turn)
        return JSONResponse({"reply": reply, "extracted": extracted})


def _chat_regex_extract(message: str) -> dict:
    """Very basic field extraction for when Claude API is unavailable."""
    al = message.lower().strip()
    extracted: dict = {}
    nums = re.findall(r"\d+", al.replace(",", ""))
    if nums and not extracted.get("age"):
        val = int(nums[0])
        if 5 < val < 120:
            extracted["age"] = val
    if any(x in al for x in ("gaon", "village", "rural", "gram")):
        extracted["is_urban"] = False
    elif any(x in al for x in ("shehar", "city", "urban", "town")):
        extracted["is_urban"] = True
    for cat in ("General", "OBC", "SC", "ST"):
        if cat.lower() in al:
            extracted["caste_category"] = cat
            break
    if any(x in al for x in ("kisan", "farmer")):
        extracted["occupation"] = "Farmer"
    elif any(x in al for x in ("majdoor", "labourer", "daily wage")):
        extracted["occupation"] = "Daily wage worker"
    if nums and len(nums) >= 1:
        big = [int(n) for n in nums if int(n) > 1000]
        if big:
            extracted["annual_income"] = big[0]
    return extracted


def _chat_fallback_reply(extracted: dict, profile: dict, turn: int) -> str:
    """Simple rule-based follow-up when Claude API unavailable."""
    combined = {**profile, **extracted}
    missing = []
    if not combined.get("age"): missing.append("Aapki umar kitni hai? (What is your age?)")
    elif not combined.get("state"): missing.append("Aap kis rajya mein rehte hain? (Which state?)")
    elif not combined.get("caste_category"): missing.append("Aapka varg kya hai? General, OBC, SC, ya ST?")
    elif not combined.get("annual_income"): missing.append("Saalana amdani kitni hai? (Yearly income?)")
    elif not combined.get("occupation"): missing.append("Aap kya kaam karte hain? (What is your occupation?)")
    else:
        return "Shukriya! Ab aap 'See my results' button dabayein. धन्यवाद!"
    return missing[0] if missing else "Kuch aur batayein apne baare mein?"


@app.post("/api/parse-voice", response_class=JSONResponse)
async def parse_voice(request: Request):
    """Parse a spoken Hindi/Hinglish sentence into profile fields."""
    body = await request.json()
    text: str = body.get("text", "")
    if not text:
        return JSONResponse({"fields": {}, "summary_hindi": ""})

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                system="""Extract profile fields from the Hindi/Hinglish sentence.
Return JSON only:
{"fields": {"age": int|null, "state": str|null, "gender": "M"|"F"|"Transgender"|null,
 "caste_category": "General"|"OBC"|"SC"|"ST"|null,
 "is_urban": true|false|null, "marital_status": "unmarried"|"married"|"widowed"|"divorced"|null,
 "occupation": str|null, "annual_income": int|null,
 "has_aadhaar": true|false|null, "has_bank_account": true|false|null,
 "family_size": int|null},
"summary_hindi": "one-line Hindi summary of what was understood"}
Only include fields explicitly mentioned. Null = not mentioned.""",
                messages=[{"role": "user", "content": text}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            return JSONResponse(json.loads(raw))
        except Exception:
            pass

    # Fallback: reuse the regex extractor
    extracted = _chat_regex_extract(text)
    return JSONResponse({
        "fields": extracted,
        "summary_hindi": f"Samjha: {', '.join(f'{k}={v}' for k, v in extracted.items())}",
    })


@app.get("/checklist", response_class=HTMLResponse)
async def checklist(request: Request):
    from urllib.parse import parse_qs
    qs = str(request.query_params)
    form = {k: v[0] for k, v in parse_qs(qs).items()} if qs else {}

    if not form:
        return RedirectResponse("/details")

    try:
        profile = _build_profile(form)
    except Exception:
        return RedirectResponse("/details")

    all_results = _run_engine(profile)
    eligible_results = [
        r for r in all_results
        if r.status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE, MatchStatus.AMBIGUOUS)
    ]

    # Aggregate documents across eligible schemes
    doc_map: dict[str, dict] = {}
    for r in eligible_results:
        for doc in r.required_documents:
            doc_id = doc.get("document", "")
            if doc_id not in doc_map:
                doc_map[doc_id] = {**doc, "needed_for": []}
            doc_map[doc_id]["needed_for"].append(r.scheme_name)

    docs_list = list(doc_map.values())

    dag = PrerequisiteDAG.from_data_file()
    eligible_ids = [r.scheme_id for r in eligible_results
                    if r.status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE)]
    app_order = dag.topological_order(eligible_ids)

    return templates.TemplateResponse(request, "checklist.html", {
        "docs": docs_list,
        "eligible_results": eligible_results,
        "app_order": app_order,
        "icons": SCHEME_ICONS,
        "profile_qs": qs,
    })
