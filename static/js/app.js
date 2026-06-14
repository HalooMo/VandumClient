document.addEventListener('DOMContentLoaded', () => {
    // Mobile nav
    const toggle = document.getElementById('navToggle');
    const links = document.getElementById('navLinks');
    if (toggle && links) {
        toggle.addEventListener('click', () => links.classList.toggle('open'));
        links.querySelectorAll('a').forEach(a => {
            a.addEventListener('click', () => links.classList.remove('open'));
        });
    }

    // Nav scroll effect
    const nav = document.getElementById('mainNav');
    window.addEventListener('scroll', () => {
        if (nav) nav.classList.toggle('scrolled', window.scrollY > 40);
        const prog = document.getElementById('scrollProgress');
        if (prog) {
            const h = document.documentElement.scrollHeight - window.innerHeight;
            prog.style.width = h > 0 ? (window.scrollY / h * 100) + '%' : '0%';
        }
    });

    // Cursor glow
    const glow = document.getElementById('cursorGlow');
    if (glow) {
        document.addEventListener('mousemove', (e) => {
            glow.style.left = e.clientX + 'px';
            glow.style.top = e.clientY + 'px';
        });
    }

    // Scroll animations
    const animated = document.querySelectorAll('[data-animate]');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const delay = entry.target.dataset.delay || 0;
                setTimeout(() => entry.target.classList.add('visible'), parseInt(delay));
            }
        });
    }, { threshold: 0.12 });
    animated.forEach(el => observer.observe(el));

    // Magnetic buttons
    document.querySelectorAll('.magnetic').forEach(btn => {
        btn.addEventListener('mousemove', (e) => {
            const r = btn.getBoundingClientRect();
            const x = e.clientX - r.left - r.width / 2;
            const y = e.clientY - r.top - r.height / 2;
            btn.style.transform = `translate(${x * 0.15}px, ${y * 0.15}px)`;
        });
        btn.addEventListener('mouseleave', () => { btn.style.transform = ''; });
    });

    // Smooth anchor scroll
    document.querySelectorAll('a[href^="#"]').forEach(a => {
        a.addEventListener('click', (e) => {
            const id = a.getAttribute('href').slice(1);
            const el = document.getElementById(id);
            if (el) {
                e.preventDefault();
                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // Auto-dismiss flash
    document.querySelectorAll('[data-auto-dismiss]').forEach(el => {
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateX(100%)';
            el.style.transition = 'all 0.4s';
            setTimeout(() => el.remove(), 400);
        }, 5000);
    });

    // Landing section links — highlight by hash on homepage
    const sectionLinks = document.querySelectorAll('.nav-link[data-nav-section]');
    if (sectionLinks.length && (location.pathname === '/' || location.pathname === '')) {
        const syncSectionNav = () => {
            const hash = location.hash.replace('#', '');
            sectionLinks.forEach(link => {
                const section = link.dataset.navSection;
                link.classList.toggle('nav-link-active', hash === section);
            });
        };
        syncSectionNav();
        window.addEventListener('hashchange', syncSectionNav);
    }

    // Footer status initial load
    fetch('/api/public/stats')
        .then(r => r.json())
        .then(d => {
            const f = document.getElementById('footerStatus');
            if (f) {
                const online = d.server?.status === 'ok';
                f.innerHTML = `<span class="pulse-dot ${online ? '' : 'offline'}"></span> ${online ? 'Online' : 'Offline'} · ${d.projects} projects`;
            }
        })
        .catch(() => {});
});
