document.addEventListener('DOMContentLoaded', () => {
    const copyBtn = document.getElementById('copyKeyBtn');
    const keyEl = document.getElementById('newKeyValue');
    if (copyBtn && keyEl) {
        copyBtn.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(keyEl.textContent.trim());
                copyBtn.textContent = 'Скопировано!';
                setTimeout(() => { copyBtn.textContent = 'Копировать'; }, 2000);
            } catch {
                const range = document.createRange();
                range.selectNode(keyEl);
                window.getSelection().removeAllRanges();
                window.getSelection().addRange(range);
            }
        });
    }
});
