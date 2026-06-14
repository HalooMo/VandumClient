document.addEventListener('DOMContentLoaded', () => {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('videoInput');
    const preview = document.getElementById('uploadPreview');
    const content = zone?.querySelector('.upload-content');
    const fileName = document.getElementById('fileName');
    const clearBtn = document.getElementById('clearFile');

    if (!zone || !input) return;

    function showFile(file) {
        if (!file) return;
        fileName.textContent = file.name;
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
            input.files = e.dataTransfer.files;
            showFile(e.dataTransfer.files[0]);
        }
    });

    clearBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        input.value = '';
        content.hidden = false;
        preview.hidden = true;
    });
});
