/* Kalam — Voice input via Web Speech API. Progressive enhancement: no-op if unsupported. */

(function () {
    'use strict';

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) return;  // silently skip on unsupported browsers

    const btn = document.getElementById('mic-btn');
    const statusEl = document.getElementById('voice-status');
    if (!btn) return;

    // Show the button only when speech is supported
    btn.style.display = 'flex';

    const rec = new Recognition();
    rec.lang = 'hi-IN';
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    let isListening = false;

    function setStatus(text, color) {
        if (!statusEl) return;
        statusEl.textContent = text;
        statusEl.style.display = 'block';
        statusEl.style.color = color || 'var(--text-secondary)';
    }

    function fillField(name, value) {
        // Try hidden input, then visible input, then select
        const hidden = document.getElementById(name);
        if (hidden && hidden.type === 'hidden') { hidden.value = value; return; }

        const inp = document.querySelector(`[name="${name}"]`);
        if (!inp) return;

        if (inp.type === 'number' || inp.type === 'text') {
            inp.value = value;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
        } else if (inp.tagName === 'SELECT') {
            inp.value = value;
            inp.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    function selectRadio(name, value) {
        const radio = document.querySelector(`input[type="radio"][name="${name}"][value="${value}"]`);
        if (!radio) return;
        radio.checked = true;
        radio.closest('.option-card, .occ-card, .range-card')?.classList.add('selected');
        radio.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function applyParsed(parsed) {
        const f = parsed.fields || parsed;
        if (f.age)             fillField('age', f.age);
        if (f.state)           fillField('state', f.state);
        if (f.gender)          selectRadio('gender', f.gender);
        if (f.caste_category)  selectRadio('caste_category', f.caste_category);
        if (f.is_urban !== undefined) selectRadio('is_urban', f.is_urban ? 'urban' : 'rural');
        if (f.marital_status)  selectRadio('marital_status', f.marital_status);
        if (f.occupation)      selectRadio('occupation', f.occupation);
        if (f.annual_income) {
            fillField('annual_income', f.annual_income);
            // Also map to nearest range card
            const ranges = [25000, 75000, 200000, 450000, 750000, 1000000];
            const nearest = ranges.reduce((a, b) => Math.abs(b - f.annual_income) < Math.abs(a - f.annual_income) ? b : a);
            selectRadio('_income_range', nearest);
        }
        if (f.has_aadhaar !== undefined)     selectRadio('has_aadhaar', f.has_aadhaar ? 'yes' : 'no');
        if (f.has_bank_account !== undefined) selectRadio('has_bank_account', f.has_bank_account ? 'yes' : 'no');
        if (f.family_size)     fillField('family_size', f.family_size);
    }

    btn.addEventListener('click', () => {
        if (isListening) {
            rec.stop();
            return;
        }

        isListening = true;
        btn.classList.add('listening');
        setStatus('🎤 Bol rahe hain… / Listening…', 'var(--primary)');

        rec.start();
    });

    rec.onresult = async (event) => {
        const transcript = Array.from(event.results)
            .map(r => r[0].transcript)
            .join(' ');
        setStatus('🔄 Samajh rahe hain: "' + transcript + '"', 'var(--text-secondary)');

        if (event.results[0].isFinal) {
            try {
                const resp = await fetch('/api/parse-voice', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: transcript }),
                });
                const data = await resp.json();
                applyParsed(data);
                const summary = data.summary_hindi || data.summary || transcript;
                setStatus('✅ Samjha: ' + summary, 'var(--eligible)');
            } catch (e) {
                setStatus('✅ Suna: "' + transcript + '" — fields updated', 'var(--eligible)');
            }
        }
    };

    rec.onerror = (e) => {
        setStatus('❌ Sun nahi paye. Dobara try karein.', 'var(--ineligible)');
        isListening = false;
        btn.classList.remove('listening');
    };

    rec.onend = () => {
        isListening = false;
        btn.classList.remove('listening');
        setTimeout(() => {
            if (statusEl && statusEl.style.display !== 'none') {
                // keep visible for 4s then fade
                statusEl.style.transition = 'opacity 0.5s';
                setTimeout(() => { statusEl.style.opacity = '0'; }, 4000);
                setTimeout(() => { statusEl.style.display = 'none'; statusEl.style.opacity = '1'; }, 4600);
            }
        }, 500);
    };
}());
