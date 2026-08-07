(function () {
    const el = document.getElementById('resultPlyr');
    if (!el || typeof Plyr === 'undefined') return;

    const player = new Plyr(el, {
        ratio: '16:9',
        controls: [
            'play-large',
            'play',
            'progress',
            'current-time',
            'duration',
            'mute',
            'volume',
            'settings',
            'pip',
            'fullscreen',
        ],
        settings: ['speed'],
        speed: { selected: 1, options: [0.75, 1, 1.25, 1.5, 2] },
        seekTime: 5,
        keyboard: { focused: true, global: false },
        tooltips: { controls: true, seek: true },
        i18n: {
            play: 'Смотреть',
            pause: 'Пауза',
            mute: 'Без звука',
            unmute: 'Со звуком',
            enterFullscreen: 'На весь экран',
            exitFullscreen: 'Выйти из полноэкранного',
            settings: 'Настройки',
            speed: 'Скорость',
            normal: 'Обычная',
            pip: 'Картинка в картинке',
        },
    });

    window.__resultPlyr = player;
})();
