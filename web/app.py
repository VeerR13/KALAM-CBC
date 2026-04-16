"""Kalam Web — FastAPI application."""
import base64 as _b64
import json
import os
import urllib.request as _http
from functools import lru_cache as _lru_cache
from pathlib import Path
from typing import Optional

from urllib.parse import urlencode as _urlencode

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
from src.models.scheme import RuleResult, Scheme
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
    "stand_up_india": "🚀",
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


_MINI_FORM_UNSUPPORTED = {"previous_scheme_loans"}


def _missing_mandatory_fields(result: MatchResult) -> list[str]:
    """Return field names that are mandatory, missing, and collectable via mini-form."""
    seen: set[str] = set()
    fields: list[str] = []
    for ev in result.rule_evaluations:
        if ev.result == RuleResult.MISSING and ev.is_mandatory and ev.explanation:
            if " not provided" in ev.explanation:
                field = ev.explanation.split(" not provided")[0].strip()
                if field and field not in seen and field not in _MINI_FORM_UNSUPPORTED:
                    seen.add(field)
                    fields.append(field)
    return fields


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

    def _clamp(val, lo, hi):
        if val is None:
            return None
        return max(lo, min(hi, val))

    # Parse previous scheme loan checkboxes → list of scheme IDs
    _loan_map = {
        "prev_loan_pm_mudra": "pm_mudra",
        "prev_loan_pmegp": "pmegp",
        "prev_loan_pm_svanidhi": "pm_svanidhi",
        "prev_loan_pm_vishwakarma": "pm_vishwakarma",
    }
    _prev_loans_list = [sid for key, sid in _loan_map.items() if form.get(key) == "yes"]
    _prev_loans = _prev_loans_list if _prev_loans_list else None

    return UserProfile(
        age=_clamp(_int("age"), 0, 150),
        gender=form.get("gender") or None,
        state=state or None,
        is_urban=is_urban,
        caste_category=form.get("caste_category") or None,
        marital_status=form.get("marital_status") or None,
        annual_income=_clamp(_int("annual_income"), 0, 10_00_00_000),
        occupation=form.get("occupation") or None,
        family_size=_clamp(_int("family_size"), 1, 50),
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
        is_family_head=_bool("is_family_head"),
        spouse_is_govt_employee=_bool("spouse_is_govt_employee"),
        has_lpg_connection=_bool("has_lpg_connection"),
        has_existing_pension=_bool("has_existing_pension"),
        previous_scheme_loans=_prev_loans,
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

    missing_fields_map = {
        r.scheme_id: _missing_mandatory_fields(r)
        for r in grouped["insufficient"]
    }

    _schemes_raw = load_all_schemes()
    scheme_hindi_map = {
        sd["scheme_id"]: {
            "name": sd.get("name_hindi") or "",
            "benefit": sd.get("benefit_summary_hindi") or "",
        }
        for sd in _schemes_raw
    }

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
        "missing_fields_map": missing_fields_map,
        "scheme_hindi_map": scheme_hindi_map,
    })


@app.post("/results", response_class=HTMLResponse)
async def results(request: Request):
    form_data = await request.form()
    return await _render_results(request, dict(form_data))



def _personalized_docs(profile: UserProfile, scheme: Scheme, bur_score=None):
    """Return (has_docs, needs_docs) lists for the scheme, using BureaucraticScore if available."""
    if bur_score is not None:
        return bur_score.docs_already_have, bur_score.missing_docs
    calc = BureaucraticDistanceCalculator()
    score = calc.calculate(profile, scheme, [])
    return score.docs_already_have, score.missing_docs


def _doc_name_where(doc) -> tuple[str, str]:
    """Extract (name, where) from a doc that may be a dict or an object."""
    if isinstance(doc, dict):
        return doc.get("name", ""), doc.get("where", "")
    return getattr(doc, "name", str(doc)), getattr(doc, "where", "")


def _office_script(profile: UserProfile, scheme: Scheme, needs_docs: list = None,
                   applicant_name: str = "", applicant_village: str = "") -> dict:
    """Generate office visit scripts in both Hindi and Hinglish.

    Returns a dict with keys 'hindi' (Devanagari, for TTS) and
    'hinglish' (Latin script, for on-screen reading).
    """
    doc_keywords = {
        "has_aadhaar": ("आधार कार्ड", "Aadhaar card"),
        "has_bank_account": ("बैंक पासबुक", "bank passbook"),
        "has_ration_card": ("राशन कार्ड", "ration card"),
        "is_aadhaar_linked": ("आधार-लिंक्ड बैंक खाता", "Aadhaar-linked bank account"),
    }
    docs_have_hi, docs_have_hl = [], []
    for field, (label_hi, label_hl) in doc_keywords.items():
        val = getattr(profile, field, None)
        if val and val is not False and val != "none":
            docs_have_hi.append(label_hi)
            docs_have_hl.append(label_hl)

    name_hindi = scheme.name_hindi or scheme.name

    # Scheme-specific action lines — (Hindi, Hinglish) tuples
    _fam = profile.family_size or "?"
    scheme_actions = {
        "pm_kisan": (
            "मुझे PM-KISAN में पंजीकरण करवाना है।",
            "Mujhe PM-KISAN mein registration karwana hai.",
        ),
        "mgnrega": (
            f"मुझे NREGA जॉब कार्ड बनवाना है। मेरे परिवार में {_fam} लोग कार्य कर सकते हैं।",
            f"Mujhe NREGA job card banwana hai. Mere ghar mein {_fam} log kaam kar sakte hain.",
        ),
        "ayushman_bharat": (
            "मुझे आयुष्मान भारत कार्ड बनवाना है। कृपया जांचें कि मेरा नाम सूची में है या नहीं।",
            "Mujhe Ayushman Bharat card banwana hai. Please check karein ki mera naam list mein hai ya nahi.",
        ),
        "pmjdy": (
            "मुझे जन धन खाता खोलना है — जीरो बैलेंस वाला।",
            "Mujhe Jan Dhan khata kholna hai — zero balance wala.",
        ),
        "pmay_g": (
            "मुझे प्रधानमंत्री आवास योजना (ग्रामीण) में आवेदन करना है।",
            "Mujhe PMAY-Gramin mein aavedan karna hai.",
        ),
        "pmay_u": (
            "मुझे प्रधानमंत्री आवास योजना (शहरी) में आवेदन करना है।",
            "Mujhe PMAY-Urban mein aavedan karna hai.",
        ),
        "ujjwala": (
            "मुझे उज्ज्वला योजना के तहत मुफ़्त LPG कनेक्शन लेना है।",
            "Mujhe Ujjwala Yojana ke tahat free LPG connection lena hai.",
        ),
        "nsap_ignoaps": (
            "मुझे वृद्धावस्था पेंशन (IGNOAPS) के लिए आवेदन करना है।",
            "Mujhe vridhavastha pension (IGNOAPS) ke liye aavedan karna hai.",
        ),
        "nsap_ignwps": (
            "मुझे विधवा पेंशन (IGNWPS) के लिए आवेदन करना है।",
            "Mujhe vidhwa pension (IGNWPS) ke liye aavedan karna hai.",
        ),
        "nsap_igndps": (
            "मुझे विकलांगता पेंशन (IGNDPS) के लिए आवेदन करना है।",
            "Mujhe viklangta pension (IGNDPS) ke liye aavedan karna hai.",
        ),
        "apy": (
            "मुझे अटल पेंशन योजना में पंजीकरण करना है।",
            "Mujhe Atal Pension Yojana mein registration karna hai.",
        ),
        "pm_sym": (
            "मुझे PM-SYM पेंशन योजना में पंजीकरण करना है।",
            "Mujhe PM-SYM pension yojana mein registration karna hai.",
        ),
        "pm_svanidhi": (
            "मुझे PM SVANidhi के तहत ₹10,000 का ऋण चाहिए।",
            "Mujhe PM SVANidhi ke tahat ₹10,000 ka loan chahiye.",
        ),
        "pm_mudra": (
            "मुझे मुद्रा ऋण के लिए आवेदन करना है।",
            "Mujhe Mudra loan ke liye aavedan karna hai.",
        ),
        "pmegp": (
            "मुझे PMEGP के तहत नया उद्यम शुरू करने के लिए आवेदन करना है।",
            "Mujhe PMEGP ke tahat naya udyam shuru karne ke liye aavedan karna hai.",
        ),
        "stand_up_india": (
            "मुझे स्टैंड-अप इंडिया ऋण के लिए आवेदन करना है।",
            "Mujhe Stand-Up India loan ke liye aavedan karna hai.",
        ),
        "sukanya_samriddhi": (
            "मुझे अपनी बेटी के नाम सुकन्या समृद्धि खाता खोलना है।",
            "Mujhe apni beti ke naam Sukanya Samriddhi khata kholna hai.",
        ),
        "pmmvy": (
            "मुझे प्रधानमंत्री मातृ वंदना योजना में पंजीकरण करना है।",
            "Mujhe Pradhan Mantri Matru Vandana Yojana mein registration karna hai.",
        ),
        "nfsa": (
            "मुझे राशन कार्ड बनवाना है — NFSA के तहत।",
            "Mujhe ration card banwana hai — NFSA ke tahat.",
        ),
        "pm_vishwakarma": (
            "मुझे PM Vishwakarma योजना में पंजीकरण करना है।",
            "Mujhe PM Vishwakarma yojana mein registration karna hai.",
        ),
    }

    action_hi, action_hl = scheme_actions.get(
        scheme.scheme_id,
        (f"{name_hindi} में आवेदन करना है।", f"{scheme.name} mein aavedan karna hai."),
    )

    # Gender-inflected verb: female → आई/aayi, everyone else → आया/aaya
    is_female = (profile.gender or "").upper() == "F"
    aaya_hi = "आई" if is_female else "आया"
    aaya_hl = "aayi" if is_female else "aaya"

    # Build greeting — personalised if name provided
    if applicant_name and applicant_village:
        greet_hi = f"नमस्ते, मेरा नाम {applicant_name} है, मैं {applicant_village} से {aaya_hi} हूँ।"
        greet_hl = f"Namaskar, mera naam {applicant_name} hai, main {applicant_village} se {aaya_hl} hoon."
    elif applicant_name:
        greet_hi = f"नमस्ते, मेरा नाम {applicant_name} है।"
        greet_hl = f"Namaskar, mera naam {applicant_name} hai."
    else:
        greet_hi = "नमस्ते,"
        greet_hl = "Namaskar,"

    # Build Hindi script
    hi_lines = [f"{greet_hi} मुझे {name_hindi} के लिए आवेदन करना है।"]
    if docs_have_hi:
        hi_lines.append(f"मेरे पास {', '.join(docs_have_hi)} है।")
    hi_lines.append(action_hi)
    if needs_docs:
        for doc in needs_docs[:3]:
            doc_name, doc_where = _doc_name_where(doc)
            if not doc_name:
                continue
            if doc_where:
                hi_lines.append(f"{doc_name} अभी नहीं है — {doc_where} से मिलेगा।")
            else:
                hi_lines.append(f"{doc_name} अभी नहीं है।")
    hi_lines.append("\nक्या और कोई दस्तावेज़ चाहिए?")

    # Build Hinglish script (Latin script — easier for users who can't read Devanagari)
    hl_lines = [f"{greet_hl} Mujhe {scheme.name} ke liye aavedan karna hai."]
    if docs_have_hl:
        hl_lines.append(f"Mere paas {', '.join(docs_have_hl)} hai.")
    hl_lines.append(action_hl)
    if needs_docs:
        for doc in needs_docs[:3]:
            doc_name, doc_where = _doc_name_where(doc)
            if not doc_name:
                continue
            if doc_where:
                hl_lines.append(f"{doc_name} abhi nahi hai — {doc_where} se milega.")
            else:
                hl_lines.append(f"{doc_name} abhi nahi hai.")
    hl_lines.append("\nKya aur koi document chahiye?")

    return {
        "hindi": "\n".join(hi_lines),
        "hinglish": "\n".join(hl_lines),
    }


@app.get("/scheme/{scheme_id}", response_class=HTMLResponse)
async def scheme_detail(request: Request, scheme_id: str):
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

    bur_calc = BureaucraticDistanceCalculator()
    bur_score = bur_calc.calculate(profile, scheme_obj, [])
    has_docs, needs_docs = _personalized_docs(profile, scheme_obj, bur_score)
    applicant_name = form.get("applicant_name", "").strip()[:80]
    applicant_village = form.get("applicant_village", "").strip()[:80]
    scripts = _office_script(profile, scheme_obj, needs_docs,
                             applicant_name=applicant_name,
                             applicant_village=applicant_village)

    return templates.TemplateResponse(request, "scheme_detail.html", {
        "scheme": scheme_obj,
        "result": match_result,
        "icon": SCHEME_ICONS.get(scheme_id, "📋"),
        "profile_qs": qs,
        "bur": bur_score,
        "has_docs": has_docs,
        "needs_docs": needs_docs,
        "office_script_hindi": scripts["hindi"],
        "office_script_hinglish": scripts["hinglish"],
        "profile_gender": (profile.gender or "").upper(),
    })


@app.post("/api/recheck", response_class=JSONResponse)
async def recheck(request: Request):
    """Re-evaluate a single scheme after user answers an inline mini-form."""
    body = await request.json()
    base_form: dict = body.get("profile", {})
    new_fields: dict = body.get("new_fields", {})
    scheme_id: str = body.get("scheme_id", "")

    merged = {**base_form, **new_fields}
    # previous_scheme_loans can't be collected via mini-form — default to no prior loans
    merged.setdefault("_previous_scheme_loans_empty", "true")
    profile = _build_profile(merged)
    if profile.previous_scheme_loans is None:
        profile = profile.model_copy(update={"previous_scheme_loans": []})

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






# ── Simple in-process rate limiter ───────────────────────────────────────────
import time as _time
from collections import defaultdict as _defaultdict

_rate_store: dict[str, list[float]] = _defaultdict(list)
_RATE_WINDOW = 60.0   # seconds
_RATE_MAX    = 20     # requests per IP per window

def _is_rate_limited(ip: str) -> bool:
    now = _time.monotonic()
    hits = _rate_store[ip]
    # Drop timestamps outside the window
    _rate_store[ip] = [t for t in hits if now - t < _RATE_WINDOW]
    if len(_rate_store[ip]) >= _RATE_MAX:
        return True
    _rate_store[ip].append(now)
    return False


# ── Hugging Face TTS (facebook/mms-tts-hin) ───────────────────────────────────
_HF_KEY = os.getenv("HUGGINGFACE_API_KEY", "")
_HF_TTS_URL = "https://api-inference.huggingface.co/models/facebook/mms-tts-hin"

@_lru_cache(maxsize=512)
def _tts_audio(text: str) -> bytes | None:
    """Call HuggingFace MMS Hindi TTS, return audio bytes. LRU-cached per text."""
    if not _HF_KEY:
        return None
    req = _http.Request(
        _HF_TTS_URL,
        data=json.dumps({"inputs": text}).encode(),
        headers={
            "Authorization": f"Bearer {_HF_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with _http.urlopen(req, timeout=30) as resp:
            data = resp.read()
            # HF returns JSON error on model loading — treat as transient failure
            if resp.headers.get("Content-Type", "").startswith("application/json"):
                return None
            return data
    except Exception:
        return None


@app.post("/api/speak")
async def speak(request: Request):
    """Return audio for Hindi text via HuggingFace MMS TTS.
    Returns 503 if HUGGINGFACE_API_KEY is not set or model is loading —
    the client falls back to Web Speech API automatically."""
    ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(ip):
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    text = (body.get("text") or "").strip()[:1000]  # MMS works best under 1000 chars
    if not text:
        return JSONResponse({"error": "empty"}, status_code=400)
    audio = _tts_audio(text)
    if audio is None:
        return JSONResponse({"error": "unavailable"}, status_code=503)
    from fastapi.responses import Response as _BinaryResp
    return _BinaryResp(content=audio, media_type="audio/flac",
                       headers={"Cache-Control": "public, max-age=86400"})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request, "chat.html")


def _extract_from_message(text: str, current_profile: dict) -> tuple[dict, str]:
    """Simple Hinglish/Hindi/English extractor. Returns (extracted_fields, follow_up_question)."""
    import re
    t = text.lower().strip()
    extracted: dict = {}

    # ── Age ──────────────────────────────────────────────────────────────────
    age_m = re.search(r'\b(\d{1,3})\s*(?:saal|sal|year|years|varsh|वर्ष|साल|yrs|yr)\b', t)
    if not age_m:
        # "meri umar 34 hai", "I am 34"
        age_m = re.search(r'(?:umar|age|umra)\s*(?:hai|he|is)?\s*(\d{1,3})', t)
    if not age_m:
        age_m = re.search(r'\bI\s+am\s+(\d{1,3})\b', text, re.IGNORECASE)
    if age_m:
        age = int(age_m.group(1))
        if 0 < age < 130:
            extracted["age"] = age

    # ── Income ───────────────────────────────────────────────────────────────
    inc_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:lakh|lacs?|लाख)', t)
    if inc_m:
        extracted["annual_income"] = int(float(inc_m.group(1)) * 100_000)
    else:
        inc_k = re.search(r'(\d+)\s*(?:hazaar|hazar|thousand|हज़ार|हजार|k\b)', t)
        if inc_k:
            extracted["annual_income"] = int(inc_k.group(1)) * 1000

    # ── Family size ───────────────────────────────────────────────────────────
    fam_m = re.search(r'(\d+)\s*(?:log|member|pariwar|family|परिवार|angg|sadasy)', t)
    if fam_m:
        n = int(fam_m.group(1))
        if 1 <= n <= 30:
            extracted["family_size"] = n

    # ── Gender ────────────────────────────────────────────────────────────────
    if re.search(r'\b(?:main\s+(?:ek\s+)?(?:aurat|mahila|lady|woman)|female|महिला|औरत|she|her)\b', t):
        extracted["gender"] = "F"
    elif re.search(r'\b(?:main\s+(?:ek\s+)?(?:aadmi|purush|mard|man)|male|पुरुष|आदमी|he|his|mr\.?)\b', t):
        extracted["gender"] = "M"

    # ── Urban/Rural ───────────────────────────────────────────────────────────
    if re.search(r'\b(?:gaon|village|gram|गाँव|गांव|rural|gramin)\b', t):
        extracted["is_urban"] = "rural"
    elif re.search(r'\b(?:shehar|shahr|city|town|urban|शहर|नगर)\b', t):
        extracted["is_urban"] = "urban"

    # ── State ────────────────────────────────────────────────────────────────
    state_patterns = {
        "Uttar Pradesh": r'\b(?:up|uttar\s*pradesh|u\.p\.)\b',
        "Bihar": r'\bbihar\b',
        "Rajasthan": r'\brajasthan\b',
        "Madhya Pradesh": r'\b(?:mp|madhya\s*pradesh|m\.p\.)\b',
        "Maharashtra": r'\bmaharashtra\b',
        "West Bengal": r'\b(?:west\s*bengal|bengal|wb)\b',
        "Gujarat": r'\bgujarat\b',
        "Odisha": r'\b(?:odisha|orissa)\b',
        "Karnataka": r'\bkarnataka\b',
        "Jharkhand": r'\bjharkhand\b',
        "Assam": r'\bassam\b',
        "Kerala": r'\bkerala\b',
        "Tamil Nadu": r'\b(?:tamil\s*nadu|tamilnadu|tn)\b',
        "Telangana": r'\btelangana\b',
        "Andhra Pradesh": r'\b(?:andhra|andhra\s*pradesh|ap)\b',
        "Punjab": r'\bpunjab\b',
        "Haryana": r'\bharyana\b',
        "Chhattisgarh": r'\b(?:chhattisgarh|chattisgarh)\b',
        "Uttarakhand": r'\b(?:uttarakhand|uttaranchal)\b',
        "Himachal Pradesh": r'\b(?:himachal|himachal\s*pradesh|hp)\b',
        "Delhi": r'\b(?:delhi|dilli|new\s*delhi)\b',
        "Jammu & Kashmir": r'\b(?:jammu|kashmir|j\s*&?\s*k)\b',
    }
    for state, pat in state_patterns.items():
        if re.search(pat, t):
            extracted["state"] = state
            break

    # ── Caste ────────────────────────────────────────────────────────────────
    if re.search(r'\b(?:sc|scheduled\s*caste|anusuchit\s*jati|dalit)\b', t):
        extracted["caste_category"] = "SC"
    elif re.search(r'\b(?:st|scheduled\s*tribe|anusuchit\s*janjati|tribal|adivasi)\b', t):
        extracted["caste_category"] = "ST"
    elif re.search(r'\b(?:obc|other\s*backward|pichda\s*varg|पिछड़ा)\b', t):
        extracted["caste_category"] = "OBC"
    elif re.search(r'\b(?:general|gen\b|saamanye|सामान्य|unreserved|open)\b', t):
        extracted["caste_category"] = "General"

    # ── Occupation ───────────────────────────────────────────────────────────
    if re.search(r'\b(?:kisan|farmer|kheti|krishi|खेती|किसान|agriculture)\b', t):
        extracted["occupation"] = "Farmer"
    elif re.search(r'\b(?:majdoor|mazdoor|daily\s*wage|labourer|laborer|मजदूर|दिहाड़ी)\b', t):
        extracted["occupation"] = "Daily wage worker"
    elif re.search(r'\b(?:vendor|hawker|rehdi|pheri|feriwala|फेरीवाला|street)\b', t):
        extracted["occupation"] = "street_vendor"
    elif re.search(r'\b(?:artisan|karigar|craftsman|कारीगर|shilpkar)\b', t):
        extracted["occupation"] = "Artisan"
    elif re.search(r'\b(?:dukaan|shopkeeper|shop|dukaandar|दुकानदार)\b', t):
        extracted["occupation"] = "Shopkeeper"
    elif re.search(r'\b(?:student|padh|school|college|university|छात्र|पढ़)\b', t):
        extracted["occupation"] = "Student"
    elif re.search(r'\b(?:grahini|housewife|homemaker|घरेलू|गृहिणी)\b', t):
        extracted["occupation"] = "Homemaker"
    elif re.search(r'\b(?:berozgaar|unemployed|naukri\s*nahi|job\s*nahi|बेरोज़गार)\b', t):
        extracted["occupation"] = "Unemployed"

    # ── Documents ─────────────────────────────────────────────────────────────
    if re.search(r'\b(?:aadhaar|aadhar|adhar|आधार)\b', t):
        if re.search(r'\b(?:nahi|no\b|nahin|नहीं)\b', t):
            extracted["has_aadhaar"] = "no"
        else:
            extracted["has_aadhaar"] = "yes"
    if re.search(r'\b(?:bank\s*(?:account|khata|khata)|बैंक\s*खाता)\b', t):
        if re.search(r'\b(?:nahi|no\b|nahin|नहीं)\b', t):
            extracted["has_bank_account"] = "no"
        else:
            extracted["has_bank_account"] = "yes"
    if re.search(r'\b(?:ration\s*card|ration\s*card|राशन\s*कार्ड|pds)\b', t):
        extracted["has_ration_card"] = "PHH"

    # ── LPG / Gas ─────────────────────────────────────────────────────────────
    if re.search(r'\b(?:lpg|gas|cylinder|गैस)\b', t):
        if re.search(r'\b(?:nahi|no\b|nahin|नहीं)\b', t):
            extracted["has_lpg_connection"] = "no"
        else:
            extracted["has_lpg_connection"] = "yes"

    # ── Marital status ────────────────────────────────────────────────────────
    if re.search(r'\b(?:widow|vidhwa|vidhur|विधवा|विधुर|pati\s*guzar|wife\s*guzar)\b', t):
        extracted["marital_status"] = "widowed"
    elif re.search(r'\b(?:shaadi|married|vivahit|विवाहित|shadi)\b', t):
        extracted["marital_status"] = "married"
    elif re.search(r'\b(?:unmarried|single|avivahit|अविवाहित|kuanra|kunwara|kunwari)\b', t):
        extracted["marital_status"] = "unmarried"

    # ── Build follow-up question ──────────────────────────────────────────────
    from src.conversation.follow_up import FIELD_PRIORITY, MANDATORY_FIELDS
    merged = {**current_profile, **extracted}
    followup = None
    for field, question in FIELD_PRIORITY:
        if field in MANDATORY_FIELDS and not merged.get(field):
            followup = question
            break

    # Build a reply
    n_extracted = len(extracted)
    if n_extracted == 0:
        reply = "Maaf kijiye, yeh samajh nahi aaya. / माफ़ करें, यह समझ नहीं आया।\n\n" + (followup or "Aap form bhar sakte hain: /details")
    else:
        fields_got = ", ".join(extracted.keys())
        reply = f"✓ Samajh gaya: {fields_got}.<br><br>" + (followup or "Lagta hai kaafi jankari aa gayi! Niche <strong>See my results</strong> dabayein. / नीचे <strong>नतीजे देखें</strong> दबाएं।")

    return extracted, reply


@app.post("/api/chat", response_class=JSONResponse)
async def api_chat(request: Request):
    body = await request.json()
    message: str = str(body.get("message", ""))[:500]   # cap at 500 chars
    current_profile: dict = body.get("profile", {})
    extracted, reply = _extract_from_message(message, current_profile)
    return JSONResponse({"reply": reply, "extracted": extracted})


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

    _schemes_raw = load_all_schemes()
    scheme_hindi_map = {
        sd["scheme_id"]: {
            "name": sd.get("name_hindi") or "",
            "benefit": sd.get("benefit_summary_hindi") or "",
        }
        for sd in _schemes_raw
    }

    return templates.TemplateResponse(request, "checklist.html", {
        "docs": docs_list,
        "eligible_results": eligible_results,
        "app_order": app_order,
        "icons": SCHEME_ICONS,
        "profile_qs": qs,
        "scheme_hindi_map": scheme_hindi_map,
    })
