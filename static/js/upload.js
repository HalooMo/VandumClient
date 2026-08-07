document.addEventListener('DOMContentLoaded', () => {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('videoInput');
    const preview = document.getElementById('uploadPreview');
    const content = zone?.querySelector('.upload-content');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const clearBtn = document.getElementById('clearFile');
    const maxMb = Number(zone?.dataset.maxMb || 150);
    const maxBytes = maxMb * 1024 * 1024;

    if (!zone || !input) return;

    function formatSize(bytes) {
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
    }

    function rejectFile(message) {
        input.value = '';
        content.hidden = false;
        preview.hidden = true;
        alert(message);
    }

    function showFile(file) {
        if (!file) return;
        if (file.size > maxBytes) {
            rejectFile(`Файл слишком большой (макс. ${maxMb} МБ). Размер: ${formatSize(file.size)}.`);
            return;
        }
        fileName.textContent = file.name;
        if (fileSize) fileSize.textContent = formatSize(file.size);
        content.hidden = true;
        preview.hidden = false;
    }

    input.addEventListener('change', () => {
        if (input.files.length) showFile(input.files[0]);
    });

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            const file = e.dataTransfer.files[0];
            if (file.size > maxBytes) {
                rejectFile(`Файл слишком большой (макс. ${maxMb} МБ). Размер: ${formatSize(file.size)}.`);
                return;
            }
            input.files = e.dataTransfer.files;
            showFile(file);
        }
    });

    clearBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        input.value = '';
        content.hidden = false;
        preview.hidden = true;
    });
});
