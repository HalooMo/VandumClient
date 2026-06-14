(function () {
    let activeChart, regChart, projChart;
    let currentPeriod = 'month';

    const chartDefaults = {
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { labels: { color: '#8888a0', font: { size: 11 } } } },
        scales: {
            x: { ticks: { color: '#8888a0', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
            y: { ticks: { color: '#8888a0', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true },
        },
    };

    function loadStats(period) {
        fetch(`/dashboard/api/stats?period=${period}`)
            .then(r => r.json())
            .then(data => {
                document.getElementById('totalUsers').textContent = data.totals.users;
                document.getElementById('totalVerified').textContent = data.totals.verified;
                document.getElementById('totalProjects').textContent = data.totals.projects;
                document.getElementById('totalDone').textContent = data.totals.projects_done;

                if (activeChart) activeChart.destroy();
                if (regChart) regChart.destroy();
                if (projChart) projChart.destroy();

                activeChart = new Chart(document.getElementById('activeChart'), {
                    type: 'line',
                    data: {
                        labels: data.labels,
                        datasets: [{
                            label: 'Активные',
                            data: data.active_users,
                            borderColor: '#00f0ff',
                            backgroundColor: 'rgba(0,240,255,0.08)',
                            fill: true,
                            tension: 0.4,
                        }],
                    },
                    options: chartDefaults,
                });

                regChart = new Chart(document.getElementById('regChart'), {
                    type: 'bar',
                    data: {
                        labels: data.labels,
                        datasets: [{
                            label: 'Регистрации',
                            data: data.registrations,
                            backgroundColor: 'rgba(123,47,247,0.6)',
                            borderRadius: 6,
                        }],
                    },
                    options: chartDefaults,
                });

                projChart = new Chart(document.getElementById('projChart'), {
                    type: 'bar',
                    data: {
                        labels: data.labels,
                        datasets: [
                            {
                                label: 'Всего',
                                data: data.projects,
                                backgroundColor: 'rgba(0,240,255,0.5)',
                                borderRadius: 6,
                            },
                            {
                                label: 'Завершено',
                                data: data.projects_done,
                                backgroundColor: 'rgba(0,255,136,0.5)',
                                borderRadius: 6,
                            },
                        ],
                    },
                    options: chartDefaults,
                });
            });
    }

    document.querySelectorAll('.period-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.period-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentPeriod = tab.dataset.period;
            loadStats(currentPeriod);
        });
    });

    loadStats(currentPeriod);
})();
