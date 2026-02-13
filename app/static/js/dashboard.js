/**
 * OJ Tracker - Dashboard Charts Initialization
 * Loads data from API and renders ECharts visualizations
 */
document.addEventListener('DOMContentLoaded', function () {
    const container = document.getElementById('dashboard-container');
    const studentId = container ? container.dataset.studentId : null;
    if (!studentId) return;

    // Fetch dashboard data from API
    fetch('/api/dashboard/' + studentId)
        .then(function (response) {
            if (!response.ok) throw new Error('API request failed: ' + response.status);
            return response.json();
        })
        .then(function (data) {
            updateStatCards(data);
            initRadarChart(data.tag_scores || {});
            initHeatmap(data.heatmap || []);
            initDifficultyChart(data.difficulty_dist || {});
            initRecentSubmissions(data.recent_submissions || []);
            initWeaknessAlerts(data.weaknesses || []);
        })
        .catch(function (err) {
            console.error('Failed to load dashboard data:', err);
            showEmptyState();
        });

    // Also fetch submission data
    fetch('/api/submissions/' + studentId)
        .then(function (response) {
            if (!response.ok) return null;
            return response.json();
        })
        .then(function (data) {
            if (data && data.submissions) {
                initRecentSubmissions(data.submissions);
            }
        })
        .catch(function () {
            // Silently fail - submissions table will show loading state
        });
});

/**
 * Update stat cards with data
 */
function updateStatCards(data) {
    var stats = data.stats || {};
    setTextSafe('stat-total', stats.total_problems || 0);
    setTextSafe('stat-ac', stats.ac_count || 0);
    setTextSafe('stat-week', stats.week_submissions || 0);
    setTextSafe('stat-streak', stats.streak_days || 0);
}

/**
 * Initialize radar chart for ability scores
 */
function initRadarChart(tagScores) {
    var container = document.getElementById('radar-chart');
    if (!container) return;
    var chart = echarts.init(container);

    // Build radar dimensions from tag scores
    var categories = {};
    var entries = Object.entries(tagScores);
    if (entries.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">暂无能力评分数据</div>';
        return;
    }

    entries.forEach(function (entry) {
        var name = entry[0];
        var info = entry[1];
        var displayName = (typeof info === 'object' && info.display_name) ? info.display_name : name;
        var score = (typeof info === 'object') ? (info.score || 0) : info;
        if (!categories[displayName] || score > categories[displayName]) {
            categories[displayName] = score;
        }
    });

    // Take top 7 categories by score
    var sorted = Object.entries(categories)
        .sort(function (a, b) { return b[1] - a[1]; })
        .slice(0, 7);

    if (sorted.length < 3) {
        // Need at least 3 dimensions for a meaningful radar
        while (sorted.length < 3) {
            sorted.push(['--', 0]);
        }
    }

    var option = {
        title: {
            text: '能力雷达图',
            left: 'center',
            textStyle: { fontSize: 14, color: '#5a5c69' }
        },
        tooltip: {
            trigger: 'item'
        },
        radar: {
            indicator: sorted.map(function (item) {
                return { name: item[0], max: 100 };
            }),
            shape: 'polygon',
            splitNumber: 5,
            axisName: {
                color: '#666',
                fontSize: 11
            },
            splitArea: {
                areaStyle: {
                    color: ['rgba(78,115,223,0.02)', 'rgba(78,115,223,0.05)']
                }
            }
        },
        series: [{
            type: 'radar',
            data: [{
                value: sorted.map(function (item) { return Math.round(item[1]); }),
                name: '能力评分',
                areaStyle: { opacity: 0.25, color: '#4e73df' },
                lineStyle: { color: '#4e73df', width: 2 },
                itemStyle: { color: '#4e73df' }
            }]
        }]
    };
    chart.setOption(option);
    window.addEventListener('resize', function () { chart.resize(); });
}

/**
 * Initialize GitHub-style heatmap calendar
 */
function initHeatmap(heatmapData) {
    var container = document.getElementById('heatmap-chart');
    if (!container) return;
    var chart = echarts.init(container);

    // Process data
    var data = [];
    if (Array.isArray(heatmapData)) {
        data = heatmapData.map(function (d) {
            return [d.date, d.count];
        });
    }

    var year = new Date().getFullYear();

    if (data.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">暂无做题日历数据</div>';
        return;
    }

    var option = {
        title: {
            text: '做题日历',
            left: 'center',
            textStyle: { fontSize: 14, color: '#5a5c69' }
        },
        tooltip: {
            formatter: function (params) {
                return params.value[0] + ': ' + params.value[1] + ' 次提交';
            }
        },
        visualMap: {
            min: 0,
            max: 10,
            type: 'piecewise',
            orient: 'horizontal',
            left: 'center',
            bottom: 0,
            pieces: [
                { min: 0, max: 0, label: '0', color: '#ebedf0' },
                { min: 1, max: 2, label: '1-2', color: '#9be9a8' },
                { min: 3, max: 5, label: '3-5', color: '#40c463' },
                { min: 6, max: 9, label: '6-9', color: '#30a14e' },
                { min: 10, label: '10+', color: '#216e39' }
            ],
            textStyle: { fontSize: 11 }
        },
        calendar: {
            range: year.toString(),
            cellSize: ['auto', 15],
            left: 50,
            right: 30,
            top: 50,
            itemStyle: {
                borderWidth: 3,
                borderColor: '#fff'
            },
            yearLabel: { show: false },
            dayLabel: {
                nameMap: 'ZH',
                fontSize: 10
            },
            monthLabel: {
                nameMap: 'ZH',
                fontSize: 10
            }
        },
        series: [{
            type: 'heatmap',
            coordinateSystem: 'calendar',
            data: data
        }]
    };
    chart.setOption(option);
    window.addEventListener('resize', function () { chart.resize(); });
}

/**
 * Initialize difficulty distribution bar chart
 */
function initDifficultyChart(diffDist) {
    var container = document.getElementById('difficulty-chart');
    if (!container) return;
    var chart = echarts.init(container);

    var keys = Object.keys(diffDist);
    if (keys.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">暂无难度分布数据</div>';
        return;
    }

    // Sort keys numerically
    keys.sort(function (a, b) { return parseInt(a) - parseInt(b); });
    var labels = keys.map(function (d) { return '难度' + d; });
    var values = keys.map(function (d) { return diffDist[d]; });

    var barColors = ['#91cc75', '#73c0de', '#5470c6', '#fac858', '#ee6666',
                     '#fc8452', '#9a60b4', '#ea7ccc', '#e74a3b', '#c23531'];

    var option = {
        title: {
            text: '难度分布',
            left: 'center',
            textStyle: { fontSize: 14, color: '#5a5c69' }
        },
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter: function (params) {
                var p = params[0];
                return p.name + ': ' + p.value + ' 题';
            }
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: labels,
            axisLabel: { fontSize: 11 }
        },
        yAxis: {
            type: 'value',
            name: '题数',
            nameTextStyle: { fontSize: 11 },
            axisLabel: { fontSize: 11 }
        },
        series: [{
            type: 'bar',
            data: values.map(function (v, i) {
                return {
                    value: v,
                    itemStyle: { color: barColors[i % barColors.length] }
                };
            }),
            barWidth: '60%',
            label: {
                show: true,
                position: 'top',
                fontSize: 11,
                color: '#666'
            }
        }]
    };
    chart.setOption(option);
    window.addEventListener('resize', function () { chart.resize(); });
}

/**
 * Initialize recent submissions table
 */
function initRecentSubmissions(submissions) {
    var tbody = document.getElementById('recent-submissions-body');
    if (!tbody) return;

    if (!submissions || submissions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-3">暂无提交记录</td></tr>';
        return;
    }

    var statusClasses = {
        'AC': 'badge-ac',
        'WA': 'badge-wa',
        'TLE': 'badge-tle',
        'MLE': 'badge-mle',
        'RE': 'badge-re',
        'CE': 'badge-ce'
    };

    var html = '';
    var displaySubs = submissions.slice(0, 15);
    for (var i = 0; i < displaySubs.length; i++) {
        var sub = displaySubs[i];
        var statusClass = statusClasses[sub.status] || 'bg-secondary';
        var time = sub.submitted_at || sub.time || '-';
        if (time.length > 16) time = time.substring(5, 16);

        html += '<tr>';
        html += '<td><small>' + escapeHtml(time) + '</small></td>';
        html += '<td><span class="badge bg-dark">' + escapeHtml(sub.platform || '-') + '</span></td>';
        html += '<td>';
        if (sub.problem_id) {
            html += '<a href="/problem/' + sub.problem_id + '" class="text-decoration-none">';
            html += escapeHtml(sub.problem_title || sub.platform_pid || '-');
            html += '</a>';
        } else {
            html += escapeHtml(sub.problem_title || sub.platform_pid || '-');
        }
        html += '</td>';
        html += '<td><span class="badge ' + statusClass + '">' + escapeHtml(sub.status || '-') + '</span></td>';
        html += '</tr>';
    }
    tbody.innerHTML = html;
}

/**
 * Initialize weakness alert cards
 */
function initWeaknessAlerts(weaknesses) {
    var section = document.getElementById('weakness-section');
    var cardsContainer = document.getElementById('weakness-cards');
    if (!section || !cardsContainer) return;

    if (!weaknesses || weaknesses.length === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    var html = '';

    for (var i = 0; i < weaknesses.length; i++) {
        var w = weaknesses[i];
        var severity = w.severity || 'mild';
        var severityClass = 'weakness-' + severity;
        var severityLabel = severity === 'critical' ? '严重' : severity === 'moderate' ? '中等' : '轻微';
        var severityBadge = severity === 'critical' ? 'bg-danger' : severity === 'moderate' ? 'bg-warning text-dark' : 'bg-secondary';

        html += '<div class="col-md-4">';
        html += '<div class="weakness-card ' + severityClass + '">';
        html += '<div class="d-flex justify-content-between align-items-start">';
        html += '<h6 class="fw-bold mb-1">' + escapeHtml(w.tag || w.name || '未知') + '</h6>';
        html += '<span class="badge ' + severityBadge + '">' + severityLabel + '</span>';
        html += '</div>';
        html += '<small class="text-muted">';
        if (w.pass_rate !== undefined) {
            html += '通过率: ' + w.pass_rate + '%';
        }
        if (w.attempted !== undefined) {
            html += ' | 尝试: ' + w.attempted + '题';
        }
        html += '</small>';
        if (w.suggestion) {
            html += '<p class="mt-2 mb-0 small">' + escapeHtml(w.suggestion) + '</p>';
        }
        html += '</div>';
        html += '</div>';
    }
    cardsContainer.innerHTML = html;
}

/**
 * Show empty data state
 */
function showEmptyState() {
    var emptyState = document.getElementById('empty-data-state');
    if (emptyState) {
        emptyState.style.display = 'block';
    }
    // Hide chart areas
    var charts = document.querySelectorAll('.chart-container');
    for (var i = 0; i < charts.length; i++) {
        charts[i].style.display = 'none';
    }
    // Set stat values to 0
    setTextSafe('stat-total', 0);
    setTextSafe('stat-ac', 0);
    setTextSafe('stat-week', 0);
    setTextSafe('stat-streak', 0);
}

/* Helper Functions */
function setTextSafe(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
}

function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
