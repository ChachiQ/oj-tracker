/**
 * OJ Tracker - Knowledge Graph Visualization
 * Uses ECharts force-directed graph to display knowledge points
 */
document.addEventListener('DOMContentLoaded', function () {
    var graphContainer = document.getElementById('knowledge-graph');
    var studentId = graphContainer ? graphContainer.dataset.studentId : null;
    if (!studentId) return;

    fetch('/api/knowledge/' + studentId)
        .then(function (response) {
            if (!response.ok) throw new Error('API request failed: ' + response.status);
            return response.json();
        })
        .then(function (data) {
            initKnowledgeGraph(data);
            updateStageProgress(data.stage_stats || {});
        })
        .catch(function (err) {
            console.error('Failed to load knowledge data:', err);
            if (graphContainer) {
                graphContainer.innerHTML = '<div class="text-center text-muted py-5">' +
                    '<i class="bi bi-exclamation-triangle" style="font-size: 2rem;"></i>' +
                    '<p class="mt-2">加载知识图谱失败，请稍后再试。</p></div>';
            }
        });
});

/**
 * Stage name and color mappings
 */
var STAGE_NAMES = {
    1: '语法基础',
    2: '基础算法',
    3: 'CSP-J',
    4: 'CSP-S',
    5: '省选',
    6: 'NOI'
};

var STATUS_COLORS = {
    'mastered': '#1cc88a',
    'learning': '#f6c23e',
    'weak': '#e74a3b',
    'untouched': '#d1d3e2'
};

var STATUS_LABELS = {
    'mastered': '已掌握',
    'learning': '学习中',
    'weak': '薄弱',
    'untouched': '未涉及'
};

/**
 * Initialize the knowledge graph using ECharts force-directed layout
 */
function initKnowledgeGraph(data) {
    var container = document.getElementById('knowledge-graph');
    if (!container) return;
    var chart = echarts.init(container);

    var nodesList = data.nodes || [];
    var linksList = data.links || [];

    if (nodesList.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">' +
            '<i class="bi bi-diagram-3" style="font-size: 2rem;"></i>' +
            '<p class="mt-2">暂无知识图谱数据</p></div>';
        return;
    }

    // Build categories from stages
    var categories = [];
    for (var stageId = 1; stageId <= 6; stageId++) {
        categories.push({ name: STAGE_NAMES[stageId] || ('阶段' + stageId) });
    }

    // Process nodes
    var nodes = nodesList.map(function (n) {
        var status = n.status || 'untouched';
        var nodeSize = n.size || 10;
        // Ensure minimum visibility
        if (nodeSize < 8) nodeSize = 8;

        return {
            id: String(n.id),
            name: n.name || '未知',
            symbolSize: nodeSize,
            category: (n.stage || 1) - 1,
            itemStyle: {
                color: STATUS_COLORS[status] || STATUS_COLORS['untouched'],
                borderColor: '#fff',
                borderWidth: 1
            },
            label: {
                show: nodeSize > 12,
                fontSize: Math.max(9, Math.min(12, nodeSize * 0.7)),
                color: '#333'
            },
            tooltip: {
                formatter: function () {
                    var stageName = STAGE_NAMES[n.stage] || '未知';
                    var statusLabel = STATUS_LABELS[status] || '未知';
                    return '<b>' + escapeHtml(n.name) + '</b><br/>' +
                        '阶段: ' + stageName + '<br/>' +
                        '状态: ' + statusLabel + '<br/>' +
                        '通过: ' + (n.solved || 0) + '/' + (n.attempted || 0) + '<br/>' +
                        '通过率: ' + (n.pass_rate || 0) + '%<br/>' +
                        '评分: ' + (n.score || 0);
                }
            },
            // Store original data for click handler
            _data: n
        };
    });

    // Process links
    var links = linksList.map(function (l) {
        return {
            source: String(l.source),
            target: String(l.target),
            lineStyle: {
                opacity: 0.3,
                width: 1,
                curveness: 0.2,
                color: '#adb5bd'
            }
        };
    });

    var option = {
        title: {
            text: '信息学知识点图谱',
            left: 'center',
            textStyle: {
                fontSize: 16,
                color: '#5a5c69'
            }
        },
        tooltip: {
            trigger: 'item',
            confine: true
        },
        legend: [{
            data: categories.map(function (c) { return c.name; }),
            orient: 'vertical',
            left: 10,
            top: 50,
            textStyle: { fontSize: 11 }
        }],
        animationDurationUpdate: 1500,
        animationEasingUpdate: 'quinticInOut',
        series: [{
            type: 'graph',
            layout: 'force',
            data: nodes,
            links: links,
            categories: categories,
            roam: true,
            draggable: true,
            label: {
                position: 'right'
            },
            force: {
                repulsion: 200,
                gravity: 0.1,
                edgeLength: [50, 150],
                layoutAnimation: true,
                friction: 0.6
            },
            emphasis: {
                focus: 'adjacency',
                lineStyle: { width: 3 },
                itemStyle: {
                    borderWidth: 3,
                    borderColor: '#333'
                }
            },
            scaleLimit: {
                min: 0.4,
                max: 3
            }
        }]
    };

    chart.setOption(option);

    // Click handler to show detail panel
    chart.on('click', function (params) {
        if (params.dataType === 'node' && params.data && params.data._data) {
            showNodeDetail(params.data._data);
        }
    });

    window.addEventListener('resize', function () { chart.resize(); });
}

/**
 * Show node detail panel on the right side
 */
function showNodeDetail(nodeData) {
    var panel = document.getElementById('node-detail-panel');
    if (!panel) return;

    var status = nodeData.status || 'untouched';
    var statusLabel = STATUS_LABELS[status] || '未知';
    var statusColor = STATUS_COLORS[status] || '#d1d3e2';
    var stageName = STAGE_NAMES[nodeData.stage] || ('阶段' + nodeData.stage);
    var passRate = nodeData.pass_rate || 0;

    var progressClass = 'bg-success';
    if (passRate < 30) progressClass = 'bg-danger';
    else if (passRate < 50) progressClass = 'bg-warning';

    var html = '<div class="card">';
    html += '<div class="card-header d-flex justify-content-between align-items-center">';
    html += '<h6 class="mb-0 fw-bold">' + escapeHtml(nodeData.name) + '</h6>';
    html += '<button type="button" class="btn-close btn-close-sm" onclick="document.getElementById(\'node-detail-panel\').style.display=\'none\'"></button>';
    html += '</div>';
    html += '<div class="card-body">';

    // Status badge
    html += '<div class="mb-3">';
    html += '<span class="badge" style="background-color: ' + statusColor + '; color: ' + (status === 'learning' ? '#333' : '#fff') + ';">' + statusLabel + '</span>';
    html += '</div>';

    // Info rows
    html += '<table class="table table-sm table-borderless mb-3">';
    html += '<tr><td class="text-muted" style="width: 70px;">阶段</td><td>' + stageName + '</td></tr>';
    if (nodeData.category) {
        html += '<tr><td class="text-muted">分类</td><td>' + escapeHtml(nodeData.category) + '</td></tr>';
    }
    html += '<tr><td class="text-muted">评分</td><td><strong>' + (nodeData.score || 0) + '</strong> / 100</td></tr>';
    html += '<tr><td class="text-muted">已通过</td><td>' + (nodeData.solved || 0) + ' 题</td></tr>';
    html += '<tr><td class="text-muted">已尝试</td><td>' + (nodeData.attempted || 0) + ' 题</td></tr>';
    html += '<tr><td class="text-muted">通过率</td><td>' + passRate + '%</td></tr>';
    html += '</table>';

    // Progress bar
    html += '<div class="progress mb-3" style="height: 8px;">';
    html += '<div class="progress-bar ' + progressClass + '" style="width: ' + passRate + '%;"></div>';
    html += '</div>';

    // Recommended problems
    if (nodeData.recommended_problems && nodeData.recommended_problems.length > 0) {
        html += '<div class="mt-3">';
        html += '<h6 class="fw-bold mb-2">推荐练习</h6>';
        html += '<ul class="list-unstyled mb-0">';
        for (var i = 0; i < nodeData.recommended_problems.length && i < 5; i++) {
            var prob = nodeData.recommended_problems[i];
            var probTitle = prob.title || prob.platform_pid || '未知题目';
            if (prob.id) {
                html += '<li class="mb-1"><a href="/problem/' + prob.id + '" class="text-decoration-none small">';
                html += '<i class="bi bi-journal-code"></i> ' + escapeHtml(probTitle);
                html += '</a></li>';
            } else {
                html += '<li class="mb-1 small"><i class="bi bi-journal-code"></i> ' + escapeHtml(probTitle) + '</li>';
            }
        }
        html += '</ul>';
        html += '</div>';
    }

    html += '</div></div>';

    panel.innerHTML = html;
    panel.style.display = 'block';
}

/**
 * Update stage progress bars and percentages
 */
function updateStageProgress(stageStats) {
    for (var stageId = 1; stageId <= 6; stageId++) {
        var stats = stageStats[stageId] || stageStats[String(stageId)] || {};
        var coverage = stats.coverage || 0;
        var mastery = stats.mastery || 0;

        var coverageBar = document.getElementById('stage-' + stageId + '-coverage');
        var masteryBar = document.getElementById('stage-' + stageId + '-mastery');
        var textEl = document.getElementById('stage-' + stageId + '-text');

        if (coverageBar) {
            coverageBar.style.width = coverage + '%';
        }
        if (masteryBar) {
            masteryBar.style.width = mastery + '%';
        }
        if (textEl) {
            textEl.textContent = Math.round(coverage) + '% / ' + Math.round(mastery) + '%';
        }
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
