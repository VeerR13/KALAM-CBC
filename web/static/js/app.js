/* Kalam — Form navigation, no mandatory fields, progressive disclosure */

const TOTAL_STEPS = 5;
let currentStep = 1;
const formState = {};

// ── Audio (Web Speech API) ─────────────────────────────────────────────────
let _hindiVoice = null;

function _pickHindiVoice() {
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return;
    // Prefer Google Hindi (best quality on Android/Chrome), then any hi-IN
    _hindiVoice =
        voices.find(v => v.lang === 'hi-IN' && /google/i.test(v.name)) ||
        voices.find(v => v.lang === 'hi-IN') ||
        voices.find(v => v.lang.startsWith('hi')) ||
        null;
}

// Voices load asynchronously on most browsers
if ('speechSynthesis' in window) {
    _pickHindiVoice();
    window.speechSynthesis.addEventListener('voiceschanged', _pickHindiVoice);
}

function _cleanForTTS(text) {
    return text
        // Currency — say "rupaye" not the symbol
        .replace(/₹\s*([\d,]+)/g, (_, n) => n.replace(/,/g, '') + ' रुपये ')
        .replace(/₹/g, 'रुपये ')
        // Common symbols read as English words
        .replace(/[·•|]/g, ' ')          // separators
        .replace(/[—–\-]+/g, ' ')        // dashes
        .replace(/→|←|↓|↑|»|«/g, ' ')   // arrows
        .replace(/\+/g, ' से अधिक ')     // plus sign
        .replace(/%/g, ' प्रतिशत ')       // percent
        .replace(/\//g, ' ')              // slash in "6,000/year"
        .replace(/&amp;/g, ' और ')        // HTML entity
        .replace(/&/g, ' और ')
        // Remove stray English punctuation that causes TTS to pause oddly
        .replace(/[*#@^~`<>[\]{}\\]/g, '')
        // Collapse whitespace
        .replace(/\s{2,}/g, ' ')
        .trim();
}

function speakHindi(text) {
    if (!('speechSynthesis' in window)) return;
    const cleaned = _cleanForTTS(text);
    if (!cleaned) return;
    // Cancel first, then delay — Chrome cancels asynchronously; calling speak()
    // immediately after cancel() silently kills the new utterance too.
    window.speechSynthesis.cancel();
    setTimeout(() => {
        if (window.speechSynthesis.paused) window.speechSynthesis.resume();
        const u = new SpeechSynthesisUtterance(cleaned);
        u.lang = 'hi-IN';
        u.rate = 0.72;
        u.pitch = 1.0;
        u.volume = 1;
        if (_hindiVoice) u.voice = _hindiVoice;
        window.speechSynthesis.speak(u);
    }, 50);
}

// Event delegation — catches all .speak-btn (data-speak) clicks on every page.
// .speak-btn-big buttons are wired individually in scheme_detail.html (live DOM text).
function initSpeakButtons() {}  // no-op kept so existing callers don't break
document.addEventListener('click', e => {
    const btn = e.target.closest('.speak-btn');
    if (!btn) return;
    e.stopPropagation();
    speakHindi(btn.getAttribute('data-speak') || '');
});

// ── Save / Restore ────────────────────────────────────────────────────────────
function saveStep() {
    const form = document.getElementById('profile-form');
    if (!form) return;
    form.querySelectorAll('input, select').forEach(el => {
        if (el.type === 'radio') {
            if (el.checked) formState[el.name] = el.value;
        } else if (el.value !== '') {
            formState[el.name] = el.value;
        }
    });
}

function restoreStep() {
    const form = document.getElementById('profile-form');
    if (!form) return;
    form.querySelectorAll('.option-card, .occ-card, .range-card').forEach(c => c.classList.remove('selected'));
    Object.entries(formState).forEach(([name, value]) => {
        const radio = form.querySelector(`input[type="radio"][name="${name}"][value="${value}"]`);
        if (radio) {
            radio.checked = true;
            radio.closest('.option-card, .occ-card, .range-card')?.classList.add('selected');
            return;
        }
        const el = form.elements[name];
        if (el && el.type !== 'radio') el.value = value;
    });
    updateConditionals();
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goBack() {
    saveStep();
    if (currentStep > 1) showStep(currentStep - 1);
}

function showStep(n) {
    document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
    document.getElementById('step-' + n)?.classList.add('active');
    updateProgress(n);
    updateNextBtn(n);
    if (n === TOTAL_STEPS) buildSummary();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    currentStep = n;
    initSpeakButtons();
}

function updateProgress(n) {
    for (let i = 1; i <= TOTAL_STEPS; i++) {
        const item = document.getElementById('prog-' + i);
        if (!item) continue;
        item.classList.remove('active', 'done');
        if (i === n) item.classList.add('active');
        else if (i < n) item.classList.add('done');
    }
}

function updateNextBtn(n) {
    const btn = document.getElementById('btn-next');
    if (!btn) return;
    if (n === TOTAL_STEPS) {
        btn.textContent = 'Check eligibility with what I know →';
        btn.classList.add('submit');
    } else {
        btn.textContent = 'Next →';
        btn.classList.remove('submit');
    }
}

// ── Summary ───────────────────────────────────────────────────────────────────
const FIELD_LABELS = {
    age: 'Age / उम्र',
    gender: 'Gender / लिंग',
    state: 'State / राज्य',
    is_urban: 'Location / स्थान',
    caste_category: 'Category / वर्ग',
    marital_status: 'Marital status / वैवाहिक स्थिति',
    occupation: 'Occupation / पेशा',
    annual_income: 'Yearly income / आमदनी',
    land_ownership: 'Land / ज़मीन',
    has_enterprise: 'Business / कारोबार',
    has_aadhaar: 'Aadhaar card',
    has_bank_account: 'Bank account',
    is_aadhaar_linked: 'Aadhaar linked to bank',
    has_ration_card: 'Ration card / राशन कार्ड',
    disability_percent: 'Disability / विकलांगता',
    is_govt_employee: 'Govt employee',
    is_income_tax_payer: 'Income tax payer',
    is_epf_member: 'EPF/PF member',
    family_size: 'Family members / परिवार',
    num_children: 'Children / बच्चे',
    has_girl_child_under_10: 'Girl child under 10',
    is_pregnant_or_lactating: 'Pregnant/nursing',
    num_live_births: 'Live births',
};

const INCOME_RANGE_LABELS = {
    '25000':   '₹50,000 se kam',
    '75000':   '₹50,000 – ₹1 lakh',
    '200000':  '₹1 lakh – ₹3 lakh',
    '450000':  '₹3 lakh – ₹6 lakh',
    '750000':  '₹6 lakh – ₹9 lakh',
    '1000000': '₹9 lakh+',
    '':        'Pata nahi',
};

function buildSummary() {
    const grid = document.getElementById('summary-grid');
    if (!grid) return;
    grid.innerHTML = '';
    Object.entries(FIELD_LABELS).forEach(([key, label]) => {
        const val = formState[key];
        const row = document.createElement('div');
        row.className = 'summary-row';
        let displayVal;
        if (val === undefined || val === '' || val === null) {
            displayVal = '<span class="summary-val muted">Not provided · नहीं बताया</span>';
        } else if (key === 'annual_income') {
            const rangeLabel = INCOME_RANGE_LABELS[String(val)] || '';
            displayVal = `<span class="summary-val">₹${parseInt(val).toLocaleString('en-IN')} / year${rangeLabel ? ' (' + rangeLabel + ')' : ''}</span>`;
        } else if (key === 'is_urban') {
            displayVal = `<span class="summary-val">${val === 'urban' ? 'City / शहर' : 'Village / गाँव'}</span>`;
        } else {
            displayVal = `<span class="summary-val">${val}</span>`;
        }
        row.innerHTML = `<span class="summary-key">${label}</span>${displayVal}`;
        grid.appendChild(row);
    });
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Wire speak buttons on every page (results, path, scheme detail, etc.)
    initSpeakButtons();

    const form = document.getElementById('profile-form');
    if (!form) return;

    showStep(1);

    // Next / submit
    document.getElementById('btn-next')?.addEventListener('click', () => {
        saveStep();
        if (currentStep < TOTAL_STEPS) {
            showStep(currentStep + 1);
            restoreStep();
        } else {
            form.submit();
        }
    });

    // Option card clicks (radio — option-card and occ-card)
    document.querySelectorAll('.option-card, .occ-card').forEach(card => {
        card.addEventListener('click', () => {
            const radio = card.querySelector('input[type="radio"]');
            if (!radio) return;
            document.querySelectorAll(`.option-card input[name="${radio.name}"], .occ-card input[name="${radio.name}"]`)
                .forEach(r => r.closest('.option-card, .occ-card')?.classList.remove('selected'));
            radio.checked = true;
            card.classList.add('selected');
            formState[radio.name] = radio.value;
            updateConditionals();
        });
    });

    // Income range cards
    document.querySelectorAll('.range-card').forEach(card => {
        card.addEventListener('click', () => {
            const radio = card.querySelector('input[type="radio"]');
            if (!radio) return;
            document.querySelectorAll('.range-card').forEach(c => c.classList.remove('selected'));
            radio.checked = true;
            card.classList.add('selected');
            // Set the hidden annual_income field
            const hiddenIncome = document.getElementById('annual_income');
            if (hiddenIncome) hiddenIncome.value = radio.value;
            formState['annual_income'] = radio.value;
            formState['_income_range'] = radio.value;
        });
    });

    updateConditionals();
    form.addEventListener('change', updateConditionals);
});

function getVal(name) {
    const form = document.getElementById('profile-form');
    if (!form) return null;
    const checked = form.querySelector(`input[name="${name}"]:checked`);
    if (checked) return checked.value || null;
    const el = form.elements[name];
    if (el && el.type !== 'radio') return el.value || null;
    return null;
}

function setVisible(id, show) {
    document.getElementById(id)?.classList.toggle('visible', show);
}

function updateConditionals() {
    const landOwn = getVal('land_ownership');
    setVisible('cond-land-area', !!(landOwn && landOwn !== 'none' && landOwn !== ''));

    const hasAadhaar = getVal('has_aadhaar');
    const hasBank    = getVal('has_bank_account');
    setVisible('cond-aadhaar-linked', hasAadhaar === 'yes' && hasBank === 'yes');

    const gender     = getVal('gender');
    const isPregnant = getVal('is_pregnant_or_lactating');
    setVisible('cond-pregnant',        gender === 'F');
    setVisible('cond-pregnant-births', gender === 'F' && isPregnant === 'yes');

    const maritalStatus = getVal('marital_status');
    setVisible('cond-spouse-govt', maritalStatus === 'married');
}
