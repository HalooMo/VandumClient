document.addEventListener('DOMContentLoaded', () => {
    // ── Typed hero text ──
    const phrases = ['Любой язык.', 'Любой голос.', 'За минуты.', 'Без студии.', 'AI-powered.'];
    const target = document.getElementById('typedTarget');
    if (target) {
        let pi = 0, ci = 0, deleting = false;
        const type = () => {
            const phrase = phrases[pi];
            if (!deleting) {
                target.textContent = phrase.slice(0, ++ci);
                if (ci === phrase.length) { deleting = true; setTimeout(type, 2000); return; }
            } else {
                target.textContent = phrase.slice(0, --ci);
                if (ci === 0) { deleting = false; pi = (pi + 1) % phrases.length; }
            }
            setTimeout(type, deleting ? 40 : 80);
        };
        setTimeout(type, 1000);
    }

    // ── Counter animation ──
    const counters = document.querySelectorAll('[data-count]');
    const countObs = new IntersectionObserver((entries) => {
        entries.forEach(e => {
            if (!e.isIntersecting) return;
            const el = e.target;
            const target = parseInt(el.dataset.count, 10);
            const duration = 1500;
            const start = performance.now();
            const tick = (now) => {
                const p = Math.min((now - start) / duration, 1);
                const ease = 1 - Math.pow(1 - p, 3);
                el.textContent = Math.floor(target * ease);
                if (p < 1) requestAnimationFrame(tick);
                else el.textContent = target;
            };
            requestAnimationFrame(tick);
            countObs.unobserve(el);
        });
    }, { threshold: 0.5 });
    counters.forEach(c => countObs.observe(c));

    // ── Terminal simulation ──
    const termLines = [
        { cmd: 'upload video.mp4 --size 142MB', status: 'UPLOAD' },
        { cmd: 'asr --model whisper-large-v3', status: 'ASR' },
        { cmd: 'translate en→ru --context aware', status: 'NLP' },
        { cmd: 'tts --engine Qwen3-VoiceDesign', status: 'TTS' },
        { cmd: 'mix --dub 100% --orig 30%', status: 'MIX' },
        { cmd: 'export demo_dubbed.mp4 ✓', status: 'DONE' },
    ];
    const termBody = document.getElementById('terminalBody');
    const termStatus = document.getElementById('termStatus');
    let ti = 0;
    if (termBody) {
        setInterval(() => {
            const line = termLines[ti % termLines.length];
            if (termStatus) termStatus.textContent = line.status;
            const div = document.createElement('div');
            div.className = 'term-line';
            div.innerHTML = `<span class="term-prompt">›</span> <span class="term-cmd">${line.cmd}</span>`;
            termBody.insertBefore(div, termBody.lastElementChild);
            while (termBody.children.length > 8) termBody.removeChild(termBody.firstChild);
            ti++;
        }, 3000);
    }

    // ── Wave canvas (hero) ──
    const waveCanvas = document.getElementById('waveCanvas');
    if (waveCanvas) {
        const wctx = waveCanvas.getContext('2d');
        let phase = 0;
        const drawWave = () => {
            const W = waveCanvas.width, H = waveCanvas.height;
            wctx.clearRect(0, 0, W, H);
            wctx.beginPath();
            for (let x = 0; x < W; x++) {
                const y = H / 2 + Math.sin(x * 0.04 + phase) * 15 * Math.sin(x * 0.01 + phase * 0.5)
                    + Math.sin(x * 0.08 + phase * 1.3) * 8;
                x === 0 ? wctx.moveTo(x, y) : wctx.lineTo(x, y);
            }
            const grad = wctx.createLinearGradient(0, 0, W, 0);
            grad.addColorStop(0, '#00f0ff');
            grad.addColorStop(1, '#7b2ff7');
            wctx.strokeStyle = grad;
            wctx.lineWidth = 2;
            wctx.stroke();
            phase += 0.05;
            requestAnimationFrame(drawWave);
        };
        drawWave();
    }

    // ── Holo card tilt ──
    const holoCard = document.getElementById('holoCard');
    if (holoCard) {
        holoCard.addEventListener('mousemove', (e) => {
            const rect = holoCard.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width - 0.5;
            const y = (e.clientY - rect.top) / rect.height - 0.5;
            holoCard.style.transform = `perspective(800px) rotateY(${x * 12}deg) rotateX(${-y * 12}deg)`;
        });
        holoCard.addEventListener('mouseleave', () => {
            holoCard.style.transform = '';
        });
    }

    // ── Pipeline nodes click ──
    document.querySelectorAll('.pipeline-node').forEach(node => {
        node.addEventListener('click', () => {
            document.querySelectorAll('.pipeline-node').forEach(n => n.classList.remove('active'));
            node.classList.add('active');
        });
    });
    document.querySelector('.pipeline-node')?.classList.add('active');

    // ── Language matrix ──
    const langSamples = {
        en: '"Hello, welcome to our platform."',
        ru: '"Здравствуйте, добро пожаловать на нашу платформу."',
        de: '"Hallo, willkommen auf unserer Plattform."',
        es: '"Hola, bienvenido a nuestra plataforma."',
        fr: '"Bonjour, bienvenue sur notre plateforme."',
        ja: '"こんにちは、プラットフォームへようこそ。"',
        zh: '"你好，欢迎来到我们的平台。"',
        auto: '"[Auto-detected speech]"',
        it: '"Ciao, benvenuto sulla nostra piattaforma."',
        pt: '"Olá, bem-vindo à nossa plataforma."',
        ko: '"안녕하세요, 플랫폼에 오신 것을 환영합니다."',
    };
    let srcLang = 'en', tgtLang = 'ru';
    const langRoute = document.getElementById('langRoute');
    const langPreview = document.getElementById('langPreview');

    function updateLang() {
        if (langRoute) langRoute.textContent = `${srcLang.toUpperCase()} → ${tgtLang.toUpperCase()}`;
        if (langPreview) {
            langPreview.querySelector('.source').textContent = langSamples[srcLang] || `"[${srcLang}]"`;
            langPreview.querySelector('.target').textContent = langSamples[tgtLang] || `"[${tgtLang}]"`;
        }
    }

    document.querySelectorAll('#sourceLangs .lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#sourceLangs .lang-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            srcLang = btn.dataset.lang;
            updateLang();
        });
    });
    document.querySelectorAll('#targetLangs .lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#targetLangs .lang-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            tgtLang = btn.dataset.lang;
            updateLang();
        });
    });

    // ── Voice Lab ──
    let vlGender = 'female', vlAge = 32, vlTemp = 0.72, vlVol = 100, vlRatio = 30;
    const vlPrompt = document.getElementById('vlPrompt');
    const genderHints = { male: 'masculine male', female: 'feminine female', auto: 'natural' };
    const ageHints = (a) => a < 14 ? 'child' : a < 20 ? 'teen' : a < 55 ? 'adult' : 'elderly';
    const langNames = { ru: 'Russian', en: 'English', de: 'German', es: 'Spanish', fr: 'French' };

    function updateVoiceLab() {
        if (vlPrompt) {
            vlPrompt.textContent = `Warm ${genderHints[vlGender]} voice, ${langNames[tgtLang] || 'Russian'}. ${ageHints(vlAge)}.`;
        }
        const mixDub = document.getElementById('vlMixDub');
        const mixOrig = document.getElementById('vlMixOrig');
        if (mixDub) mixDub.style.width = (100 - vlRatio) + '%';
        if (mixOrig) mixOrig.style.width = vlRatio + '%';
    }

    document.querySelectorAll('#vlGender .vl-toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#vlGender .vl-toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            vlGender = btn.dataset.val;
            updateVoiceLab();
        });
    });

    ['vlAge', 'vlTemp', 'vlVol', 'vlRatio'].forEach(id => {
        const el = document.getElementById(id);
        const valEl = document.getElementById(id + 'Val');
        if (!el) return;
        el.addEventListener('input', () => {
            if (id === 'vlAge') { vlAge = +el.value; if (valEl) valEl.textContent = vlAge; }
            if (id === 'vlTemp') { vlTemp = (+el.value / 100).toFixed(2); if (valEl) valEl.textContent = vlTemp; }
            if (id === 'vlVol') { vlVol = +el.value; if (valEl) valEl.textContent = vlVol; }
            if (id === 'vlRatio') { vlRatio = +el.value; if (valEl) valEl.textContent = vlRatio; }
            updateVoiceLab();
        });
    });
    updateVoiceLab();

    // Voice lab wave
    const vlWave = document.getElementById('vlWave');
    if (vlWave) {
        const vctx = vlWave.getContext('2d');
        let vPhase = 0;
        const drawVL = () => {
            const W = vlWave.width, H = vlWave.height;
            vctx.clearRect(0, 0, W, H);
            for (let band = 0; band < 3; band++) {
                vctx.beginPath();
                for (let x = 0; x < W; x++) {
                    const amp = (15 - band * 4) * (vlVol / 100);
                    const y = H / 2 + band * 8 + Math.sin(x * 0.05 + vPhase + band) * amp
                        * Math.sin(x * 0.02 + vPhase * 0.7);
                    x === 0 ? vctx.moveTo(x, y) : vctx.lineTo(x, y);
                }
                const colors = ['rgba(0,240,255,0.6)', 'rgba(123,47,247,0.4)', 'rgba(255,45,149,0.3)'];
                vctx.strokeStyle = colors[band];
                vctx.lineWidth = 1.5;
                vctx.stroke();
            }
            vPhase += 0.04 + vlTemp * 0.02;
            requestAnimationFrame(drawVL);
        };
        drawVL();
    }

    // ── FAQ accordion ──
    document.querySelectorAll('.faq-q').forEach(btn => {
        btn.addEventListener('click', () => {
            const item = btn.closest('.faq-item');
            const wasOpen = item.classList.contains('open');
            document.querySelectorAll('.faq-item').forEach(i => {
                i.classList.remove('open');
                i.querySelector('.faq-q').setAttribute('aria-expanded', 'false');
            });
            if (!wasOpen) {
                item.classList.add('open');
                btn.setAttribute('aria-expanded', 'true');
            }
        });
    });

    // ── Tilt cards ──
    document.querySelectorAll('.tilt-card').forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const r = card.getBoundingClientRect();
            const x = (e.clientX - r.left) / r.width - 0.5;
            const y = (e.clientY - r.top) / r.height - 0.5;
            card.style.transform = `perspective(600px) rotateY(${x * 8}deg) rotateX(${-y * 8}deg) translateY(-4px)`;
        });
        card.addEventListener('mouseleave', () => { card.style.transform = ''; });
    });

    // ── Live stats polling ──
    const pollStats = () => {
        fetch('/api/public/stats')
            .then(r => r.json())
            .then(d => {
                const u = document.getElementById('liveUsers');
                const p = document.getElementById('liveProjects');
                const s = document.getElementById('liveServer');
                const f = document.getElementById('footerStatus');
                if (u) u.textContent = d.users;
                if (p) p.textContent = d.projects_done;
                if (s) s.textContent = d.server?.status || 'offline';
                if (f) f.innerHTML = `<span class="pulse-dot"></span> ${d.server?.status === 'ok' ? 'Online' : 'Offline'} · ${d.projects} projects`;
            })
            .catch(() => {});
    };
    pollStats();
    setInterval(pollStats, 30000);
});
