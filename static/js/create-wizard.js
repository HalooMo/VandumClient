document.addEventListener('DOMContentLoaded', () => {
    let step = 0;
    const maxStep = 4;
    const panels = document.querySelectorAll('.wizard-panel');
    const stepItems = document.querySelectorAll('.wizard-step-item');
    const prevBtn = document.getElementById('wizardPrev');
    const nextBtn = document.getElementById('wizardNext');
    const submitBtn = document.getElementById('wizardSubmit');
    const form = document.getElementById('wizardForm');

    const langNames = {
        auto: 'Auto', en: 'English', ru: 'Russian', de: 'Deutsch',
        es: 'Español', fr: 'Français', it: 'Italiano', pt: 'Português',
        zh: '中文', ja: '日本語', ko: '한국어', ar: 'العربية',
    };

    function mediaSource() {
        return document.getElementById('mediaSource')?.value || 'file';
    }

    function setMediaSource(source) {
        const hidden = document.getElementById('mediaSource');
        const filePanel = document.getElementById('mediaSourceFile');
        const urlPanel = document.getElementById('mediaSourceUrl');
        const fileInput = document.getElementById('videoInput');
        const urlInput = document.getElementById('wVideoUrl');
        if (hidden) hidden.value = source;
        if (filePanel) filePanel.hidden = source !== 'file';
        if (urlPanel) urlPanel.hidden = source !== 'url';
        document.querySelectorAll('.media-source-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.source === source);
        });
        if (source === 'url' && fileInput) {
            fileInput.value = '';
            const preview = document.getElementById('uploadPreview');
            const content = document.querySelector('#uploadZone .upload-content');
            if (preview) preview.hidden = true;
            if (content) content.hidden = false;
        }
        if (source === 'file' && urlInput) urlInput.value = '';
    }

    function syncAgeHidden(selector, hiddenId) {
        const checked = [...document.querySelectorAll(selector)]
            .filter(cb => cb.checked)
            .map(cb => cb.value);
        const el = document.getElementById(hiddenId);
        if (el) el.value = checked.join(',');
    }

    function updateCastVisibility() {
        const mode = document.getElementById('wCastMode')?.value;
        const voiceGroup = document.getElementById('castVoiceGroup');
        const voice = document.getElementById('wCastVoice');
        if (voiceGroup) voiceGroup.hidden = mode !== 'voice';
        if (mode !== 'voice' && voice) voice.value = '';
    }

    function showStep(n) {
        step = n;
        panels.forEach(p => p.classList.toggle('active', +p.dataset.panel === n));
        stepItems.forEach(s => {
            const sn = +s.dataset.step;
            s.classList.toggle('active', sn === n);
            s.classList.toggle('done', sn < n);
        });
        prevBtn.disabled = n === 0;
        nextBtn.style.display = n < maxStep ? '' : 'none';
        submitBtn.style.display = n === maxStep ? '' : 'none';
        if (n === maxStep) updateReview();
    }

    function validateStep(n) {
        if (n === 0) {
            const name = document.getElementById('wProjectName');
            const file = document.getElementById('videoInput');
            const url = document.getElementById('wVideoUrl');
            if (!name.value.trim()) { name.focus(); return false; }
            if (!/^[a-zA-Z0-9_-]+$/.test(name.value)) { alert('Имя проекта: только a-z, 0-9, _ и -'); return false; }
            if (mediaSource() === 'url') {
                const u = (url?.value || '').trim();
                if (!u) { alert('Вставьте ссылку на видео или аудио'); url?.focus(); return false; }
                if (!/^https?:\/\//i.test(u)) { alert('Ссылка должна начинаться с http:// или https://'); url?.focus(); return false; }
            } else if (!file?.files?.length) {
                alert('Загрузите видео или аудио файл');
                return false;
            }
        }
        if (n === 2) {
            const mode = document.getElementById('wCastMode')?.value;
            const voice = document.getElementById('wCastVoice')?.value;
            if (mode === 'voice' && !voice) {
                alert('Выберите cast-голос или другой режим');
                document.getElementById('wCastVoice')?.focus();
                return false;
            }
        }
        if (n === 3) {
            const male = document.getElementById('voiceSampleMale');
            const female = document.getElementById('voiceSampleFemale');
            const maxSample = 10 * 1048576;
            for (const input of [male, female]) {
                const f = input?.files[0];
                if (f && f.size > maxSample) {
                    alert(`Сэмпл ${f.name} больше 10 МБ`);
                    return false;
                }
            }
        }
        return true;
    }

    function updateReview() {
        syncAgeHidden('.age-cb-male', 'maleAgesHidden');
        syncAgeHidden('.age-cb-female', 'femaleAgesHidden');

        const name = document.getElementById('wProjectName')?.value || '—';
        const file = document.getElementById('videoInput')?.files[0];
        const url = (document.getElementById('wVideoUrl')?.value || '').trim();
        const src = document.getElementById('wSourceLang');
        const tgt = document.getElementById('wTargetLang');
        const gender = document.getElementById('wGender');
        const age = document.getElementById('wAge');
        const vol = document.getElementById('wVolume');
        const ratio = document.getElementById('wRatioSlider');
        const temp = document.getElementById('wTemperature');
        const maleSample = document.getElementById('voiceSampleMale')?.files[0];
        const femaleSample = document.getElementById('voiceSampleFemale')?.files[0];
        const castMode = document.getElementById('wCastMode');
        const castVoice = document.getElementById('wCastVoice');

        document.getElementById('rvName').textContent = name;
        if (mediaSource() === 'url' && url) {
            const short = url.length > 64 ? url.slice(0, 61) + '…' : url;
            document.getElementById('rvFile').textContent = short;
        } else {
            document.getElementById('rvFile').textContent = file
                ? `${file.name} (${(file.size / 1048576).toFixed(1)} MB)`
                : '—';
        }
        document.getElementById('rvLang').textContent = `${langNames[src?.value] || src?.value} → ${langNames[tgt?.value] || tgt?.value}`;
        let voice = gender?.value || 'auto';
        if (age?.value) voice += `, age ${age.value}`;
        document.getElementById('rvVoice').textContent = voice;
        document.getElementById('rvTemp').textContent = temp?.value || '0.72';
        document.getElementById('rvVol').textContent = (vol?.value || 100) + '%';
        document.getElementById('rvRatio').textContent = (ratio?.value || 30) + '%';

        const castNames = { loki: 'Локи', tom_hardy: 'Том Харди', thor: 'Тор' };
        let castText = '—';
        if (castMode?.value === 'speakers') castText = 'speakers (3 голоса)';
        else if (castMode?.value === 'voice' && castVoice?.value) castText = castNames[castVoice.value] || castVoice.value;
        document.getElementById('rvCast').textContent = castText;

        const cloneParts = [];
        if (maleSample) cloneParts.push(`♂ ${maleSample.name}`);
        if (femaleSample) cloneParts.push(`♀ ${femaleSample.name}`);
        document.getElementById('rvClone').textContent = cloneParts.length ? cloneParts.join(', ') : 'VoiceDesign';

        const sizeMB = file ? file.size / 1048576 : 50;
        const est = sizeMB < 50 ? '10–20 мин' : sizeMB < 200 ? '20–35 мин' : '35–50+ мин';
        document.getElementById('rvTime').textContent = est;
    }

    function updateLangPreview() {
        const src = document.getElementById('wSourceLang')?.value;
        const tgt = document.getElementById('wTargetLang')?.value;
        const ps = document.getElementById('wPreviewSource');
        const pt = document.getElementById('wPreviewTarget');
        if (ps) ps.textContent = `${langNames[src] || src} (source)`;
        if (pt) pt.textContent = `${langNames[tgt] || tgt} (target)`;
    }

    prevBtn?.addEventListener('click', () => { if (step > 0) showStep(step - 1); });
    nextBtn?.addEventListener('click', () => {
        if (validateStep(step) && step < maxStep) showStep(step + 1);
    });

    stepItems.forEach(s => {
        s.addEventListener('click', () => {
            const target = +s.dataset.step;
            if (target < step || validateStep(step)) showStep(target);
        });
    });

    document.querySelectorAll('.media-source-btn').forEach(btn => {
        btn.addEventListener('click', () => setMediaSource(btn.dataset.source));
    });

    document.getElementById('wSourceLang')?.addEventListener('change', updateLangPreview);
    document.getElementById('wTargetLang')?.addEventListener('change', updateLangPreview);

    document.getElementById('wVolume')?.addEventListener('input', (e) => {
        document.getElementById('wVolLabel').textContent = e.target.value;
    });
    document.getElementById('wRatioSlider')?.addEventListener('input', (e) => {
        document.getElementById('wRatioLabel').textContent = e.target.value;
        document.getElementById('wRatio').value = (e.target.value / 100).toFixed(2);
    });
    document.getElementById('wTemperature')?.addEventListener('input', (e) => {
        document.getElementById('wTempLabel').textContent = e.target.value;
    });

    document.querySelectorAll('.age-cb-male, .age-cb-female').forEach(cb => {
        cb.addEventListener('change', () => {
            syncAgeHidden('.age-cb-male', 'maleAgesHidden');
            syncAgeHidden('.age-cb-female', 'femaleAgesHidden');
        });
    });

    const videoInput = document.getElementById('videoInput');
    videoInput?.addEventListener('change', () => {
        const f = videoInput.files[0];
        const sizeEl = document.getElementById('fileSize');
        if (f && sizeEl) sizeEl.textContent = `(${(f.size / 1048576).toFixed(1)} MB)`;
    });

    form?.addEventListener('submit', () => {
        syncAgeHidden('.age-cb-male', 'maleAgesHidden');
        syncAgeHidden('.age-cb-female', 'femaleAgesHidden');
        const overlay = document.createElement('div');
        overlay.className = 'submit-overlay';
        const hint = mediaSource() === 'url'
            ? 'Скачиваем медиа по ссылке и запускаем дубляж…'
            : 'Сохраняем файлы и переходим на страницу проекта';
        overlay.innerHTML = `
            <div class="submit-overlay-card glass-card">
                <div class="submit-spinner"></div>
                <p>Запускаем дубляж…</p>
                <span class="form-hint">${hint}</span>
            </div>`;
        document.body.appendChild(overlay);
        submitBtn.disabled = true;
        nextBtn.disabled = true;
        prevBtn.disabled = true;
    });

    document.getElementById('wCastMode')?.addEventListener('change', updateCastVisibility);

    setMediaSource('file');
    updateLangPreview();
    updateCastVisibility();
    showStep(0);
});
