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
            initStatusChart(data.status_dist || {});
            initTrendChart(data.weekly_trend || []);
            initPlatformStats(data.platform_stats || []);
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
            if (data && data.items) {
                initRecentSubmissions(data.items);
            }
        })
        .catch(function () {
            // Silently fail - submissions table will show loading state
        });
});

/**
 * Check if current viewport is mobile
 */
function isMobile() {
    return window.innerWidth < 576;
}

/**
 * Update stat cards with data
 */
function updateStatCards(data) {
    var stats = data.stats || {};
    setTextSafe('stat-total', stats.total_problems || 0);
    setTextSafe('stat-ac', stats.ac_count || 0);
    setTextSafe('stat-week', stats.week_submissions || 0);
    setTextSafe('stat-streak', stats.streak_days || 0);
    var firstAc = data.first_ac_rate || 0;
    setTextSafe('stat-first-ac', firstAc + '%');
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

    var mobile = isMobile();
    var option = {
        title: {
            text: '能力雷达图',
            left: 'center',
            textStyle: { fontSize: mobile ? 12 : 14, color: '#5a5c69' }
        },
        tooltip: {
            trigger: 'item'
        },
        radar: {
            indicator: sorted.map(function (item) {
                return { name: item[0], max: 100 };
            }),
            shape: 'polygon',
            splitNumber: mobile ? 3 : 5,
            radius: mobile ? '55%' : '65%',
            axisName: {
                color: '#666',
                fontSize: mobile ? 9 : 11
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

    var mobile = isMobile();
    var option = {
        title: {
            text: '做题日历',
            left: 'center',
            textStyle: { fontSize: mobile ? 12 : 14, color: '#5a5c69' }
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
            show: !mobile,
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
            cellSize: mobile ? ['auto', 10] : ['auto', 15],
            left: mobile ? 30 : 50,
            right: mobile ? 10 : 30,
            top: mobile ? 40 : 50,
            itemStyle: {
                borderWidth: mobile ? 2 : 3,
                borderColor: '#fff'
            },
            yearLabel: { show: false },
            dayLabel: {
                nameMap: 'ZH',
                fontSize: mobile ? 8 : 10
            },
            monthLabel: {
                nameMap: 'ZH',
                fontSize: mobile ? 8 : 10
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

    var mobile = isMobile();
    var option = {
        title: {
            text: '难度分布',
            left: 'center',
            textStyle: { fontSize: mobile ? 12 : 14, color: '#5a5c69' }
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
            axisLabel: { fontSize: mobile ? 9 : 11, rotate: mobile ? 30 : 0 }
        },
        yAxis: {
            type: 'value',
            name: '题数',
            nameTextStyle: { fontSize: mobile ? 9 : 11 },
            axisLabel: { fontSize: mobile ? 9 : 11 }
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
                fontSize: mobile ? 9 : 11,
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

        html += '<div class="col-12 col-sm-6 col-md-4">';
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
 * Initialize status distribution doughnut chart
 */
function initStatusChart(statusDist) {
    var container = document.getElementById('status-chart');
    if (!container) return;
    var chart = echarts.init(container);

    var keys = Object.keys(statusDist);
    if (keys.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">暂无提交状态数据</div>';
        return;
    }

    var statusColors = {
        'AC': '#1cc88a', 'WA': '#e74a3b', 'TLE': '#f6c23e',
        'MLE': '#fd7e14', 'RE': '#6f42c1', 'CE': '#858796'
    };
    var totalCount = 0;
    var pieData = [];
    for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        var v = statusDist[k];
        totalCount += v;
        pieData.push({
            name: k, value: v,
            itemStyle: { color: statusColors[k] || '#adb5bd' }
        });
    }

    var mobile = isMobile();
    var option = {
        title: {
            text: '提交状态分布',
            left: 'center',
            textStyle: { fontSize: mobile ? 12 : 14, color: '#5a5c69' }
        },
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c} ({d}%)'
        },
        graphic: [{
            type: 'text',
            left: 'center',
            top: 'center',
            style: {
                text: totalCount.toString(),
                fontSize: mobile ? 18 : 24,
                fontWeight: 'bold',
                fill: '#5a5c69',
                textAlign: 'center'
            }
        }],
        series: [{
            type: 'pie',
            radius: mobile ? ['35%', '55%'] : ['40%', '65%'],
            center: ['50%', '55%'],
            avoidLabelOverlap: true,
            label: {
                show: !mobile,
                formatter: '{b}: {c}'
            },
            emphasis: {
                label: { show: true, fontWeight: 'bold' }
            },
            data: pieData
        }]
    };
    chart.setOption(option);
    window.addEventListener('resize', function () { chart.resize(); });
}

/**
 * Initialize weekly trend dual-axis chart
 */
function initTrendChart(weeklyTrend) {
    var container = document.getElementById('trend-chart');
    if (!container) return;
    var chart = echarts.init(container);

    if (!weeklyTrend || weeklyTrend.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">暂无周趋势数据</div>';
        return;
    }

    var weeks = weeklyTrend.map(function (w) { return w.week; });
    var submissions = weeklyTrend.map(function (w) { return w.submissions; });
    var acCounts = weeklyTrend.map(function (w) { return w.ac_count; });
    var passRates = weeklyTrend.map(function (w) { return w.pass_rate; });

    var mobile = isMobile();
    var option = {
        title: {
            text: '周趋势（最近12周）',
            left: 'center',
            textStyle: { fontSize: mobile ? 12 : 14, color: '#5a5c69' }
        },
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' }
        },
        legend: {
            data: ['提交量', 'AC量', '通过率'],
            bottom: 0,
            textStyle: { fontSize: mobile ? 10 : 11 }
        },
        grid: {
            left: '3%', right: '4%', bottom: mobile ? '15%' : '12%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: weeks,
            axisLabel: {
                fontSize: mobile ? 8 : 10,
                rotate: mobile ? 45 : 30,
                formatter: function (v) {
                    // Shorten "2025-W03" to "W03"
                    var parts = v.split('-');
                    return parts.length > 1 ? parts[1] : v;
                }
            }
        },
        yAxis: [
            {
                type: 'value',
                name: '数量',
                nameTextStyle: { fontSize: mobile ? 9 : 11 },
                axisLabel: { fontSize: mobile ? 9 : 11 }
            },
            {
                type: 'value',
                name: '通过率',
                nameTextStyle: { fontSize: mobile ? 9 : 11 },
                axisLabel: { fontSize: mobile ? 9 : 11, formatter: '{value}%' },
                max: 100
            }
        ],
        series: [
            {
                name: '提交量',
                type: 'bar',
                data: submissions,
                itemStyle: { color: 'rgba(78,115,223,0.7)' },
                barWidth: '30%'
            },
            {
                name: 'AC量',
                type: 'bar',
                data: acCounts,
                itemStyle: { color: 'rgba(28,200,138,0.7)' },
                barWidth: '30%'
            },
            {
                name: '通过率',
                type: 'line',
                yAxisIndex: 1,
                data: passRates,
                smooth: true,
                lineStyle: { color: '#f6c23e', width: 2 },
                itemStyle: { color: '#f6c23e' },
                symbol: 'circle',
                symbolSize: 6
            }
        ]
    };
    chart.setOption(option);
    window.addEventListener('resize', function () { chart.resize(); });
}

/**
 * Initialize platform stats table
 */
function initPlatformStats(platformStats) {
    var container = document.getElementById('platform-stats');
    if (!container) return;

    if (!platformStats || platformStats.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">暂无平台数据</div>';
        return;
    }

    var html = '<table class="table table-sm table-hover mb-0">';
    html += '<thead><tr><th>平台</th><th>提交</th><th>AC</th><th>通过率</th></tr></thead>';
    html += '<tbody>';
    for (var i = 0; i < platformStats.length; i++) {
        var p = platformStats[i];
        var rateClass = p.pass_rate >= 50 ? 'text-success' : p.pass_rate >= 30 ? 'text-warning' : 'text-danger';
        html += '<tr>';
        html += '<td><span class="badge bg-dark">' + escapeHtml(p.platform) + '</span></td>';
        html += '<td>' + p.submissions + '</td>';
        html += '<td>' + p.ac_count + '</td>';
        html += '<td class="' + rateClass + ' fw-bold">' + p.pass_rate + '%</td>';
        html += '</tr>';
    }
    html += '</tbody></table>';
    container.innerHTML = html;
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
    setTextSafe('stat-first-ac', '0%');
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
