/**
 * OJ Tracker - Knowledge Graph Visualization
 * Uses ECharts force-directed graph to display knowledge points
 * Features: dependency chain highlighting, efficiency metrics, problem list jump links
 */

// Module-level state for dependency highlighting
var _graphChart = null;
var _graphNodes = [];
var _graphLinks = [];
var _prerequisiteMap = {};  // nodeId -> [prerequisite nodeIds]
var _dependentMap = {};     // nodeId -> [dependent nodeIds]
var _highlightedNode = null;

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
            updateStageProgress(data.stages || {});
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
 * Check if current viewport is mobile
 */
function isMobile() {
    return window.innerWidth < 576;
}

function isTablet() {
    return window.innerWidth < 768;
}

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
 * Build prerequisite and dependent maps from links data
 */
function buildDependencyMaps(linksList) {
    _prerequisiteMap = {};
    _dependentMap = {};
    for (var i = 0; i < linksList.length; i++) {
        var link = linksList[i];
        var src = String(link.source);
        var tgt = String(link.target);
        // target depends on source (source is prerequisite of target)
        if (!_prerequisiteMap[tgt]) _prerequisiteMap[tgt] = [];
        _prerequisiteMap[tgt].push(src);
        if (!_dependentMap[src]) _dependentMap[src] = [];
        _dependentMap[src].push(tgt);
    }
}

/**
 * Recursively find all ancestors (prerequisites) of a node
 */
function findAllAncestors(nodeId, visited) {
    if (!visited) visited = {};
    if (visited[nodeId]) return [];
    visited[nodeId] = true;
    var result = [];
    var prereqs = _prerequisiteMap[nodeId] || [];
    for (var i = 0; i < prereqs.length; i++) {
        result.push(prereqs[i]);
        result = result.concat(findAllAncestors(prereqs[i], visited));
    }
    return result;
}

/**
 * Recursively find all descendants (dependents) of a node
 */
function findAllDescendants(nodeId, visited) {
    if (!visited) visited = {};
    if (visited[nodeId]) return [];
    visited[nodeId] = true;
    var result = [];
    var deps = _dependentMap[nodeId] || [];
    for (var i = 0; i < deps.length; i++) {
        result.push(deps[i]);
        result = result.concat(findAllDescendants(deps[i], visited));
    }
    return result;
}

/**
 * Highlight dependency chain for a clicked node, or restore all if same node clicked again
 */
function toggleDependencyHighlight(nodeId) {
    if (!_graphChart) return;

    // If clicking the same node again, or clicking blank, restore
    if (_highlightedNode === nodeId) {
        restoreGraph();
        return;
    }

    _highlightedNode = nodeId;

    var ancestors = findAllAncestors(nodeId, {});
    var descendants = findAllDescendants(nodeId, {});
    var relatedSet = {};
    relatedSet[nodeId] = true;
    for (var i = 0; i < ancestors.length; i++) relatedSet[ancestors[i]] = true;
    for (var j = 0; j < descendants.length; j++) relatedSet[descendants[j]] = true;

    // Update node styles
    var updatedNodes = _graphNodes.map(function (n) {
        var isRelated = relatedSet[n.id];
        return {
            id: n.id,
            name: n.name,
            symbolSize: n.symbolSize,
            category: n.category,
            itemStyle: {
                color: n.itemStyle.color,
                borderColor: isRelated ? '#333' : '#fff',
                borderWidth: isRelated ? 2 : 1,
                opacity: isRelated ? 1 : 0.15
            },
            label: {
                show: isRelated || n.label.show,
                fontSize: n.label.fontSize,
                color: n.label.color,
                opacity: isRelated ? 1 : 0.15
            },
            tooltip: n.tooltip,
            _data: n._data
        };
    });

    // Update link styles
    var updatedLinks = _graphLinks.map(function (l) {
        var src = typeof l.source === 'object' ? l.source.id : String(l.source);
        var tgt = typeof l.target === 'object' ? l.target.id : String(l.target);
        var isRelated = relatedSet[src] && relatedSet[tgt];
        return {
            source: src,
            target: tgt,
            lineStyle: {
                opacity: isRelated ? 0.8 : 0.05,
                width: isRelated ? 2.5 : 1,
                curveness: 0.2,
                color: isRelated ? '#4e73df' : '#adb5bd'
            }
        };
    });

    _graphChart.setOption({
        series: [{
            data: updatedNodes,
            links: updatedLinks
        }]
    });
}

/**
 * Restore graph to original state
 */
function restoreGraph() {
    if (!_graphChart) return;
    _highlightedNode = null;

    var restoredNodes = _graphNodes.map(function (n) {
        return {
            id: n.id,
            name: n.name,
            symbolSize: n.symbolSize,
            category: n.category,
            itemStyle: {
                color: n.itemStyle.color,
                borderColor: '#fff',
                borderWidth: 1,
                opacity: 1
            },
            label: {
                show: n.label.show,
                fontSize: n.label.fontSize,
                color: n.label.color,
                opacity: 1
            },
            tooltip: n.tooltip,
            _data: n._data
        };
    });

    var restoredLinks = _graphLinks.map(function (l) {
        var src = typeof l.source === 'object' ? l.source.id : String(l.source);
        var tgt = typeof l.target === 'object' ? l.target.id : String(l.target);
        return {
            source: src,
            target: tgt,
            lineStyle: {
                opacity: 0.3,
                width: 1,
                curveness: 0.2,
                color: '#adb5bd'
            }
        };
    });

    _graphChart.setOption({
        series: [{
            data: restoredNodes,
            links: restoredLinks
        }]
    });
}

/**
 * Initialize the knowledge graph using ECharts force-directed layout
 */
function initKnowledgeGraph(data) {
    var container = document.getElementById('knowledge-graph');
    if (!container) return;
    var chart = echarts.init(container);
    _graphChart = chart;

    var nodesList = data.nodes || [];
    var linksList = data.links || [];

    if (nodesList.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">' +
            '<i class="bi bi-diagram-3" style="font-size: 2rem;"></i>' +
            '<p class="mt-2">暂无知识图谱数据</p></div>';
        return;
    }

    // Build dependency maps
    buildDependencyMaps(linksList);

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

    // Store for highlight operations
    _graphNodes = nodes;

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

    _graphLinks = links;

    var mobile = isMobile();
    var tablet = isTablet();
    var option = {
        title: {
            text: '信息学知识点图谱',
            left: 'center',
            textStyle: {
                fontSize: mobile ? 13 : 16,
                color: '#5a5c69'
            }
        },
        tooltip: {
            trigger: 'item',
            confine: true
        },
        legend: [{
            data: categories.map(function (c) { return c.name; }),
            orient: mobile ? 'horizontal' : 'vertical',
            left: mobile ? 'center' : 10,
            top: mobile ? 'auto' : 50,
            bottom: mobile ? 0 : 'auto',
            textStyle: { fontSize: mobile ? 10 : 11 }
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
                repulsion: mobile ? 120 : tablet ? 160 : 200,
                gravity: mobile ? 0.15 : 0.1,
                edgeLength: mobile ? [30, 100] : [50, 150],
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

    // Click handler to show detail panel and highlight dependencies
    chart.on('click', function (params) {
        if (params.dataType === 'node' && params.data && params.data._data) {
            showNodeDetail(params.data._data);
            toggleDependencyHighlight(params.data.id);
        } else {
            // Click on blank area — restore
            restoreGraph();
            var panel = document.getElementById('node-detail-panel');
            if (panel) panel.style.display = 'none';
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
    var firstAcRate = nodeData.first_ac_rate || 0;
    var avgAttempts = nodeData.avg_attempts || 0;

    var progressClass = 'bg-success';
    if (passRate < 30) progressClass = 'bg-danger';
    else if (passRate < 50) progressClass = 'bg-warning';

    var firstAcClass = 'bg-success';
    if (firstAcRate < 30) firstAcClass = 'bg-danger';
    else if (firstAcRate < 50) firstAcClass = 'bg-warning';

    var html = '<div class="card">';
    html += '<div class="card-header d-flex justify-content-between align-items-center">';
    html += '<h6 class="mb-0 fw-bold">' + escapeHtml(nodeData.name) + '</h6>';
    html += '<button type="button" class="btn-close btn-close-sm" onclick="document.getElementById(\'node-detail-panel\').style.display=\'none\'; restoreGraph();"></button>';
    html += '</div>';
    html += '<div class="card-body">';

    // Status badge
    html += '<div class="mb-3">';
    html += '<span class="badge" style="background-color: ' + statusColor + '; color: ' + (status === 'learning' ? '#333' : '#fff') + ';">' + statusLabel + '</span>';
    html += '</div>';

    // Info rows
    html += '<table class="table table-sm table-borderless mb-3">';
    html += '<tr><td class="text-muted" style="width: 80px;">阶段</td><td>' + stageName + '</td></tr>';
    if (nodeData.category) {
        html += '<tr><td class="text-muted">分类</td><td>' + escapeHtml(nodeData.category) + '</td></tr>';
    }
    html += '<tr><td class="text-muted">评分</td><td><strong>' + (nodeData.score || 0) + '</strong> / 100</td></tr>';
    html += '<tr><td class="text-muted">已通过</td><td>' + (nodeData.solved || 0) + ' 题</td></tr>';
    html += '<tr><td class="text-muted">已尝试</td><td>' + (nodeData.attempted || 0) + ' 题</td></tr>';
    html += '</table>';

    // Pass rate progress bar
    html += '<div class="mb-2">';
    html += '<div class="d-flex justify-content-between"><small class="text-muted">通过率</small><small>' + passRate + '%</small></div>';
    html += '<div class="progress" style="height: 6px;">';
    html += '<div class="progress-bar ' + progressClass + '" style="width: ' + passRate + '%;"></div>';
    html += '</div></div>';

    // First AC rate progress bar
    html += '<div class="mb-2">';
    html += '<div class="d-flex justify-content-between"><small class="text-muted">首次AC率</small><small>' + firstAcRate + '%</small></div>';
    html += '<div class="progress" style="height: 6px;">';
    html += '<div class="progress-bar ' + firstAcClass + '" style="width: ' + firstAcRate + '%;"></div>';
    html += '</div></div>';

    // Average attempts
    html += '<div class="mb-3">';
    html += '<div class="d-flex justify-content-between"><small class="text-muted">平均尝试次数</small><small>' + avgAttempts + ' 次</small></div>';
    html += '</div>';

    // Jump to problem list link
    html += '<div class="mb-3">';
    html += '<a href="/problem/?tag_name=' + encodeURIComponent(nodeData.id) + '" class="btn btn-outline-primary btn-sm w-100">';
    html += '<i class="bi bi-search"></i> 查看所有相关题目';
    html += '</a>';
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
