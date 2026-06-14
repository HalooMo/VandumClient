(function () {
    const STATUS_LABELS = {
        uploading: 'Загрузка файла',
        pending: 'Ожидание',
        queued: 'В очереди',
        running: 'Выполняется',
        done: 'Готово',
        error: 'Ошибка',
    };

    const STATUS_PROGRESS = {
        uploading: 10,
        pending: 5,
        queued: 15,
        running: 55,
        done: 100,
        error: 100,
    };

    const circumference = 2 * Math.PI * 52;
    const circle = document.getElementById('progressCircle');
    const label = document.getElementById('progressLabel');
    const badge = document.getElementById('statusBadge');

    if (circle) {
        circle.style.strokeDasharray = circumference;
        const svg = circle.closest('svg');
        if (svg && !svg.querySelector('#grad')) {
            const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
            defs.innerHTML = `<linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#00f0ff"/>
                <stop offset="100%" stop-color="#7b2ff7"/>
            </linearGradient>`;
            svg.prepend(defs);
        }
        circle.style.stroke = 'url(#grad)';
    }

    function labelFor(status) {
        return STATUS_LABELS[status] || status;
    }

    function setProgress(status) {
        const pct = STATUS_PROGRESS[status] || 0;
        if (circle) {
            circle.style.strokeDashoffset = circumference - (pct / 100) * circumference;
        }
        const text = labelFor(status);
        if (label) label.textContent = text;
        if (badge) {
            badge.textContent = text;
            badge.className = 'status-badge status-lg status-' + status;
        }
    }

    setProgress(typeof INITIAL_STATUS !== 'undefined' ? INITIAL_STATUS : 'pending');

    if (typeof INITIAL_STATUS !== 'undefined' && !['done', 'error'].includes(INITIAL_STATUS)) {
        const poll = () => {
            fetch(`/projects/${PROJECT_ID}/status`)
                .then(r => r.json())
                .then(data => {
                    const status = data.status || 'pending';
                    setProgress(status);
                    if (status === 'done') {
                        location.reload();
                    } else if (status !== 'error') {
                        setTimeout(poll, 10000);
                    }
                })
                .catch(() => setTimeout(poll, 20000));
        };
        setTimeout(poll, 3000);
    }
})();
