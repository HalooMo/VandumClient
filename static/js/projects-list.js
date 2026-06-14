(function () {
    const ACTIVE = new Set(['uploading', 'pending', 'queued', 'running']);

    function poll() {
        fetch('/projects/status-batch')
            .then(r => r.json())
            .then(data => {
                let needsReload = false;
                (data.projects || []).forEach(p => {
                    const card = document.querySelector(`[data-project-id="${p.id}"]`);
                    if (!card) return;
                    const badge = card.querySelector('[data-status-badge]');
                    if (badge) {
                        badge.textContent = p.status_label || p.status;
                        badge.className = 'status-badge status-' + p.status;
                    }
                    if (!ACTIVE.has(p.status)) {
                        needsReload = true;
                    }
                });
                if (needsReload) {
                    location.reload();
                } else {
                    setTimeout(poll, 15000);
                }
            })
            .catch(() => setTimeout(poll, 30000));
    }

    setTimeout(poll, 5000);
})();
