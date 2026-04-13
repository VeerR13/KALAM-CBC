"""Kalam Web — FastAPI application."""
import json
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

    def _clamp(val, lo, hi):
        if val is None:
            return None
        return max(lo, min(hi, val))

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
            "मुझे Stand-Up India ऋण के लिए आवेदन करना है।",
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
    applicant_name = form.get("applicant_name", "").strip()
    applicant_village = form.get("applicant_village", "").strip()
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
