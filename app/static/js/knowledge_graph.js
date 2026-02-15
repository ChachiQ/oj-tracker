/**
 * OJ Tracker - Knowledge Graph Visualization
 * Uses ECharts force-directed graph to display knowledge points
 * Features: dependency chain highlighting, efficiency metrics, problem list jump links
 */

// Module-level state for dependency highlighting
var _graphChart = null;
var _lastAssessmentTime = null;  // cached latest report time for duplicate check
var _aiAnalyzing = false;
var _beforeUnloadHandler = function(e) { e.preventDefault(); e.returnValue = ''; };
var _graphNodes = [];
var _graphLinks = [];
var _prerequisiteMap = {};  // nodeId -> [prerequisite nodeIds]
var _dependentMap = {};     // nodeId -> [dependent nodeIds]
var _highlightedNode = null;
var _stageData = {};        // cached stage data for detail panel
var _expandedStage = null;  // currently expanded stage id
var _resizeObserver = null; // ResizeObserver for fullscreen toggle
var _pendingCenter = false;  // flag to center graph after fullscreen resize

// Stage colors matching ECharts category colors
var STAGE_COLORS = {
    1: '#91cc75', 2: '#5470c6', 3: '#73c0de',
    4: '#fac858', 5: '#ee6666', 6: '#9a60b4'
};

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

    // Load assessment history
    loadAssessmentHistory(studentId);

    // Intercept in-app link clicks during analysis
    document.addEventListener('click', function (e) {
        if (!_aiAnalyzing) return;
        var link = e.target.closest('a[href]');
        if (!link) return;
        var href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
        if (!confirm('AI 正在生成分析报告，离开页面将中断分析。确定要离开吗？')) {
            e.preventDefault();
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

    // Update node styles — preserve skill-tree styling for related nodes
    var updatedNodes = _graphNodes.map(function (n) {
        var isRelated = relatedSet[n.id];
        return {
            id: n.id,
            name: n.name,
            symbolSize: n.symbolSize,
            category: n.category,
            itemStyle: {
                color: n.itemStyle.color,
                borderColor: isRelated ? (n.id === nodeId ? '#333' : n.itemStyle.borderColor) : '#e9ecef',
                borderWidth: isRelated ? (n.id === nodeId ? 3 : n.itemStyle.borderWidth) : 1,
                opacity: isRelated ? n.itemStyle.opacity : 0.08,
                shadowBlur: isRelated ? n.itemStyle.shadowBlur : 0,
                shadowColor: isRelated ? n.itemStyle.shadowColor : 'transparent'
            },
            label: {
                show: true,
                fontSize: n.label.fontSize,
                color: n.label.color,
                fontWeight: n.label.fontWeight,
                opacity: isRelated ? n.label.opacity : 0.1
            },
            tooltip: n.tooltip,
            _data: n._data,
            x: n.x, y: n.y, fixed: n.fixed
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
 * Restore graph to original skill-tree state
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
                borderColor: n.itemStyle.borderColor,
                borderWidth: n.itemStyle.borderWidth,
                opacity: n.itemStyle.opacity,
                shadowBlur: n.itemStyle.shadowBlur,
                shadowColor: n.itemStyle.shadowColor
            },
            label: {
                show: n.label.show,
                fontSize: n.label.fontSize,
                color: n.label.color,
                fontWeight: n.label.fontWeight,
                opacity: n.label.opacity
            },
            tooltip: n.tooltip,
            _data: n._data,
            x: n.x, y: n.y, fixed: n.fixed
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

    // Process nodes — skill-tree style: color = stage, brightness = score
    var nodes = nodesList.map(function (n) {
        var status = n.status || 'untouched';
        var score = n.score || 0;
        var nodeSize = n.size || 10;
        if (nodeSize < 14) nodeSize = 14;  // minimum size for labels

        var stageColor = STAGE_COLORS[n.stage] || '#d1d3e2';

        // Node fill color + opacity based on score
        var fillColor, fillOpacity, shadowBlur, shadowColor, borderColor, borderWidth;

        if (status === 'untouched') {
            fillColor = '#d1d3e2';
            fillOpacity = 0.15;
            shadowBlur = 0;
            shadowColor = 'transparent';
            borderColor = '#e9ecef';
            borderWidth = 1;
        } else if (status === 'weak') {
            fillColor = stageColor;
            fillOpacity = 0.3 + score / 100 * 0.7;
            shadowBlur = score >= 60 ? score * 0.2 : 0;
            shadowColor = score >= 60 ? stageColor : 'transparent';
            borderColor = '#e74a3b';
            borderWidth = 2;
        } else if (status === 'mastered') {
            fillColor = stageColor;
            fillOpacity = 1.0;
            shadowBlur = 20;
            shadowColor = stageColor;
            borderColor = '#ffd700';
            borderWidth = 2;
        } else {
            // learning or other involved
            fillColor = stageColor;
            fillOpacity = 0.3 + score / 100 * 0.7;
            shadowBlur = score >= 60 ? score * 0.2 : 0;
            shadowColor = score >= 60 ? stageColor : 'transparent';
            borderColor = '#fff';
            borderWidth = 1;
        }

        // Label styling: always show, size varies with score
        var fontSize = Math.round(9 + score * 0.03);
        var fontWeight = status === 'mastered' ? 'bold' : 'normal';
        var labelOpacity = status === 'untouched' ? 0.4 : fillOpacity;

        return {
            id: String(n.id),
            name: n.name || '未知',
            symbolSize: nodeSize,
            category: (n.stage || 1) - 1,
            itemStyle: {
                color: fillColor,
                borderColor: borderColor,
                borderWidth: borderWidth,
                opacity: fillOpacity,
                shadowBlur: shadowBlur,
                shadowColor: shadowColor
            },
            label: {
                show: true,
                fontSize: fontSize,
                color: '#333',
                fontWeight: fontWeight,
                opacity: labelOpacity
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

    // Build skill-tree legend as ECharts graphic elements (below category legend)
    var legendFontSize = mobile ? 10 : 11;
    // 3-row vertical layout
    var rowH = mobile ? 16 : 18;
    var skillTreeLegend = {
        type: 'group',
        left: 10,
        children: [
            // Row 1: brightness gradient
            { type: 'circle', shape: { r: 4 }, style: { fill: '#d1d3e2', opacity: 0.3 }, left: 0, top: 2 },
            { type: 'circle', shape: { r: 4 }, style: { fill: '#5470c6', opacity: 0.4 }, left: 14, top: 2 },
            { type: 'circle', shape: { r: 4 }, style: { fill: '#5470c6', opacity: 0.7 }, left: 28, top: 2 },
            { type: 'circle', shape: { r: 4 }, style: { fill: '#5470c6', opacity: 1.0 }, left: 42, top: 2 },
            { type: 'text', style: { text: '掌握程度', fill: '#999', fontSize: legendFontSize }, left: 54, top: 0 },
            // Row 2: gold border = mastered
            { type: 'circle', shape: { r: 5 }, style: { fill: '#91cc75', stroke: '#ffd700', lineWidth: 2 }, left: 3, top: rowH + 2 },
            { type: 'text', style: { text: '金边=已掌握', fill: '#999', fontSize: legendFontSize }, left: 16, top: rowH },
            // Row 3: red border = weak
            { type: 'circle', shape: { r: 5 }, style: { fill: '#ee6666', opacity: 0.6, stroke: '#e74a3b', lineWidth: 2 }, left: 3, top: rowH * 2 + 2 },
            { type: 'text', style: { text: '红边=薄弱', fill: '#999', fontSize: legendFontSize }, left: 16, top: rowH * 2 }
        ]
    };
    // Position: on desktop below vertical category legend; on mobile near bottom
    if (mobile) {
        skillTreeLegend.bottom = 6;
    } else {
        skillTreeLegend.top = 185;
    }

    var option = {
        tooltip: {
            trigger: 'item',
            confine: true
        },
        legend: [{
            data: categories.map(function (c) { return c.name; }),
            orient: mobile ? 'horizontal' : 'vertical',
            left: mobile ? 'center' : 10,
            top: mobile ? 'auto' : 10,
            bottom: mobile ? 40 : 'auto',
            textStyle: { fontSize: mobile ? 10 : 11 }
        }],
        graphic: [skillTreeLegend],
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
                repulsion: mobile ? 180 : tablet ? 260 : 350,
                gravity: mobile ? 0.12 : 0.08,
                edgeLength: mobile ? [40, 120] : [80, 200],
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
            labelLayout: {
                hideOverlap: true
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

    // ResizeObserver for fullscreen toggle and window resize
    if (_resizeObserver) _resizeObserver.disconnect();
    _resizeObserver = new ResizeObserver(function() {
        chart.resize();
        if (_pendingCenter) {
            _pendingCenter = false;
            chart.dispatchAction({ type: 'restore' });
        }
    });
    _resizeObserver.observe(container);
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
 * Update stage stacked progress bars and text
 */
function updateStageProgress(stageStats) {
    _stageData = stageStats;

    for (var stageId = 1; stageId <= 6; stageId++) {
        var stats = stageStats[stageId] || stageStats[String(stageId)] || {};
        var total = stats.total || 0;
        var mastered = stats.mastered || 0;
        var learning = stats.learning || 0;
        var weak = stats.weak || 0;

        var masteredPct = total > 0 ? (mastered / total * 100) : 0;
        var learningPct = total > 0 ? (learning / total * 100) : 0;
        var weakPct = total > 0 ? (weak / total * 100) : 0;

        var masteredBar = document.getElementById('stage-' + stageId + '-mastered');
        var learningBar = document.getElementById('stage-' + stageId + '-learning');
        var weakBar = document.getElementById('stage-' + stageId + '-weak');
        var textEl = document.getElementById('stage-' + stageId + '-text');

        if (masteredBar) masteredBar.style.width = masteredPct + '%';
        if (learningBar) learningBar.style.width = learningPct + '%';
        if (weakBar) weakBar.style.width = weakPct + '%';

        if (textEl) {
            textEl.textContent = '掌握 ' + mastered + ' · 学习中 ' + learning + ' · 共 ' + total;
        }
    }
}

/**
 * Toggle stage detail panel showing all tags grouped by status
 */
function toggleStageDetail(stageId) {
    var panel = document.getElementById('stage-detail-panel');
    if (!panel) return;

    // Deactivate all cards
    for (var i = 1; i <= 6; i++) {
        var card = document.getElementById('stage-card-' + i);
        if (card) card.classList.remove('active');
    }

    // If clicking the same stage, close
    if (_expandedStage === stageId) {
        closeStageDetail();
        return;
    }

    _expandedStage = stageId;

    // Activate clicked card
    var activeCard = document.getElementById('stage-card-' + stageId);
    if (activeCard) activeCard.classList.add('active');

    var stats = _stageData[stageId] || _stageData[String(stageId)] || {};
    var tags = stats.tags || [];
    var stageName = STAGE_NAMES[stageId] || ('阶段' + stageId);

    var titleEl = document.getElementById('stage-detail-title');
    if (titleEl) titleEl.innerHTML = '<i class="bi bi-tags"></i> ' + escapeHtml(stageName) + ' 知识点详情';

    // Group tags by status
    var groups = [
        { key: 'mastered', label: '已掌握', items: [] },
        { key: 'learning', label: '学习中', items: [] },
        { key: 'weak',     label: '薄弱',   items: [] },
        { key: 'untouched', label: '未涉及', items: [] }
    ];
    var groupMap = {};
    for (var g = 0; g < groups.length; g++) groupMap[groups[g].key] = groups[g];

    for (var t = 0; t < tags.length; t++) {
        var tag = tags[t];
        var group = groupMap[tag.status] || groupMap['untouched'];
        group.items.push(tag);
    }

    var html = '';
    for (var gi = 0; gi < groups.length; gi++) {
        var grp = groups[gi];
        if (grp.items.length === 0) continue;
        html += '<div class="mb-3">';
        html += '<div class="fw-bold mb-2 small">' + escapeHtml(grp.label) + ' (' + grp.items.length + ')</div>';
        html += '<div class="tag-grid">';
        for (var ti = 0; ti < grp.items.length; ti++) {
            var item = grp.items[ti];
            var title = item.display_name + (item.score > 0 ? ' (评分: ' + item.score + ', 通过: ' + item.solved + '/' + item.attempted + ')' : '');
            html += '<span class="tag-badge status-' + escapeHtml(item.status) + '" title="' + escapeHtml(title) + '">';
            html += escapeHtml(item.display_name);
            html += '</span>';
        }
        html += '</div></div>';
    }

    var content = document.getElementById('stage-detail-content');
    if (content) content.innerHTML = html;
    panel.style.display = 'block';
}

/**
 * Close the stage detail panel
 */
function closeStageDetail() {
    _expandedStage = null;
    var panel = document.getElementById('stage-detail-panel');
    if (panel) panel.style.display = 'none';
    for (var i = 1; i <= 6; i++) {
        var card = document.getElementById('stage-card-' + i);
        if (card) card.classList.remove('active');
    }
}

/**
 * Toggle fullscreen mode for knowledge graph
 */
function toggleGraphFullscreen() {
    var wrapper = document.getElementById('knowledge-graph-wrapper');
    var btn = document.getElementById('btn-graph-fullscreen');
    if (!wrapper) return;

    var isFullscreen = wrapper.classList.toggle('fullscreen');

    // Prevent body scroll in fullscreen
    document.body.style.overflow = isFullscreen ? 'hidden' : '';

    if (btn) {
        var icon = btn.querySelector('i');
        if (icon) {
            icon.className = isFullscreen ? 'bi bi-fullscreen-exit' : 'bi bi-arrows-fullscreen';
        }
        btn.title = isFullscreen ? '退出全屏' : '全屏查看';
    }
    // ResizeObserver will auto-detect size change, resize chart, and re-center
    _pendingCenter = true;
}

/**
 * Rotate the graph by a given angle (degrees) around its visual center
 */
function rotateGraphBy(angleDeg) {
    if (!_graphChart) return;

    var seriesModel = _graphChart.getModel().getSeriesByIndex(0);
    if (!seriesModel) return;
    var data = seriesModel.getData();
    if (!data || data.count() === 0) return;

    var angleRad = angleDeg * Math.PI / 180;
    var cos = Math.cos(angleRad);
    var sin = Math.sin(angleRad);

    // Read current layout positions and compute center
    var cx = 0, cy = 0;
    var count = data.count();
    var layouts = [];
    for (var i = 0; i < count; i++) {
        var layout = data.getItemLayout(i);
        layouts.push(layout ? [layout[0], layout[1]] : [0, 0]);
        cx += layouts[i][0];
        cy += layouts[i][1];
    }
    cx /= count;
    cy /= count;

    // Apply rotation around center and store in _graphNodes
    for (var j = 0; j < _graphNodes.length; j++) {
        var dx = layouts[j][0] - cx;
        var dy = layouts[j][1] - cy;
        _graphNodes[j].x = cx + dx * cos - dy * sin;
        _graphNodes[j].y = cy + dx * sin + dy * cos;
        _graphNodes[j].fixed = true;
    }

    // Build updated nodes preserving current visual state
    var updatedNodes = _graphNodes.map(function(n) {
        return {
            id: n.id, name: n.name, symbolSize: n.symbolSize, category: n.category,
            itemStyle: n.itemStyle, label: n.label, tooltip: n.tooltip, _data: n._data,
            x: n.x, y: n.y, fixed: n.fixed
        };
    });

    _graphChart.setOption({ series: [{ data: updatedNodes }] });
}

// ESC key to exit fullscreen
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        var wrapper = document.getElementById('knowledge-graph-wrapper');
        if (wrapper && wrapper.classList.contains('fullscreen')) {
            toggleGraphFullscreen();
        }
    }
});

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

// ============================================================
// AI Knowledge Assessment — SSE streaming + history management
// ============================================================

/**
 * Format a datetime string as WeChat-style smart relative time.
 * Mirrors the server-side smarttime filter (app/__init__.py:68-89).
 */
function formatSmartTime(dateStr) {
    if (!dateStr) return '-';
    var dt = new Date(dateStr.replace(' ', 'T'));
    if (isNaN(dt.getTime())) return dateStr;

    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var dtDate = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    var deltaDays = Math.round((today - dtDate) / 86400000);

    if (deltaDays === 0) {
        var hh = String(dt.getHours()).padStart(2, '0');
        var mm = String(dt.getMinutes()).padStart(2, '0');
        return hh + ':' + mm;
    } else if (deltaDays === 1) {
        return '昨天';
    } else if (deltaDays === 2) {
        return '前天';
    } else if (deltaDays <= 7) {
        return deltaDays + '天前';
    } else if (dt.getFullYear() === now.getFullYear()) {
        var mon = String(dt.getMonth() + 1).padStart(2, '0');
        var day = String(dt.getDate()).padStart(2, '0');
        return mon + '-' + day;
    } else {
        var y = dt.getFullYear();
        var m = String(dt.getMonth() + 1).padStart(2, '0');
        var d = String(dt.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + d;
    }
}

/**
 * Reload all page data (graph, stage progress, assessment history) after analysis completes
 */
function reloadPageData(studentId) {
    // Close any expanded stage detail panel
    closeStageDetail();

    // Dispose old chart instance and re-init
    if (_graphChart) {
        _graphChart.dispose();
        _graphChart = null;
    }
    _highlightedNode = null;

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
            console.error('Failed to reload knowledge data:', err);
        });

    loadAssessmentHistory(studentId);
}

/**
 * Load all AI assessment history on page load
 */
function loadAssessmentHistory(studentId) {
    fetch('/api/knowledge/' + studentId + '/assessment')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.has_assessment && data.items && data.items.length > 0) {
                renderAssessmentList(data.items, studentId);
            }
            renderNudgeBanner(data, studentId);
        })
        .catch(function (err) {
            console.error('Failed to load assessment history:', err);
        });
}

/**
 * Append a progress log line to the progress panel
 */
function appendProgressLog(step, message, detail) {
    var panel = document.getElementById('ai-progress-panel');
    var container = document.getElementById('ai-progress-steps');
    if (!panel || !container) return;

    panel.style.display = 'block';

    // Mark previous active step as done
    var activeSteps = container.querySelectorAll('.progress-step.active');
    for (var i = 0; i < activeSteps.length; i++) {
        activeSteps[i].classList.remove('active');
        activeSteps[i].classList.add('done');
        // Replace spinner with checkmark
        var icon = activeSteps[i].querySelector('.step-icon');
        if (icon) icon.innerHTML = '<i class="bi bi-check-circle-fill"></i>';
    }

    var div = document.createElement('div');
    div.className = 'progress-step';

    var iconHtml = '';
    if (step === 'done') {
        div.classList.add('done');
        iconHtml = '<i class="bi bi-check-circle-fill"></i>';
    } else if (step === 'error') {
        div.classList.add('error');
        iconHtml = '<i class="bi bi-x-circle-fill"></i>';
    } else {
        div.classList.add('active');
        iconHtml = '<span class="spinner-border spinner-border-sm"></span>';
    }

    var text = escapeHtml(message);
    if (detail) {
        text += ' <span class="text-muted">(' + escapeHtml(detail) + ')</span>';
    }

    div.innerHTML = '<span class="step-icon me-2">' + iconHtml + '</span>' + text;
    container.appendChild(div);

    // Scroll to bottom of progress
    container.scrollTop = container.scrollHeight;
}

/**
 * Trigger a new AI analysis using SSE streaming
 */
function triggerAIAnalysis(studentId) {
    var btn = document.getElementById('btn-ai-analyze');
    if (!btn) return;

    // Check for recent analysis (within 24 hours)
    if (_lastAssessmentTime) {
        var lastTime = new Date(_lastAssessmentTime.replace(' ', 'T'));
        if (!isNaN(lastTime.getTime())) {
            var hoursAgo = (Date.now() - lastTime.getTime()) / 3600000;
            if (hoursAgo < 24) {
                var timeLabel = formatSmartTime(_lastAssessmentTime);
                if (!confirm('上次分析在 ' + timeLabel + ' 完成，短时间内重复分析结果差异不大。确定要继续分析吗？')) {
                    return;
                }
            }
        }
    }

    // Set loading state
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> 分析中...';

    // Register beforeunload warning and show banner
    _aiAnalyzing = true;
    window.addEventListener('beforeunload', _beforeUnloadHandler);
    var banner = document.getElementById('ai-analyzing-banner');
    if (banner) banner.style.cssText = '';  // remove display:none
    var nudgeBanner = document.getElementById('ai-nudge-banner');
    if (nudgeBanner) nudgeBanner.style.display = 'none';

    // Reset progress panel
    var progressPanel = document.getElementById('ai-progress-panel');
    var progressSteps = document.getElementById('ai-progress-steps');
    if (progressSteps) progressSteps.innerHTML = '';
    if (progressPanel) progressPanel.style.display = 'block';

    var csrfToken = document.querySelector('meta[name="csrf-token"]');

    fetch('/api/knowledge/' + studentId + '/analyze', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken ? csrfToken.content : '',
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
        .then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            var reader = response.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';

            function processChunk() {
                return reader.read().then(function (result) {
                    if (result.done) return;

                    buffer += decoder.decode(result.value, { stream: true });
                    var lines = buffer.split('\n');
                    // Keep the last incomplete line in the buffer
                    buffer = lines.pop();

                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i].trim();
                        if (line.startsWith('data: ')) {
                            try {
                                var payload = JSON.parse(line.substring(6));
                                handleProgressEvent(payload, studentId);
                            } catch (e) {
                                console.error('Failed to parse SSE data:', e);
                            }
                        }
                    }

                    return processChunk();
                });
            }

            return processChunk();
        })
        .catch(function (err) {
            console.error('AI analysis SSE failed:', err);
            appendProgressLog('error', 'AI 分析请求失败: ' + err.message);
        })
        .finally(function () {
            _aiAnalyzing = false;
            window.removeEventListener('beforeunload', _beforeUnloadHandler);
            var banner = document.getElementById('ai-analyzing-banner');
            if (banner) banner.style.cssText = 'display: none !important';
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-robot"></i> AI 智能分析';
        });
}

/**
 * Handle a single SSE progress event
 */
function handleProgressEvent(payload, studentId) {
    appendProgressLog(payload.step, payload.message, payload.detail || '');

    if (payload.step === 'done' || payload.step === 'error') {
        _aiAnalyzing = false;
        window.removeEventListener('beforeunload', _beforeUnloadHandler);
        var banner = document.getElementById('ai-analyzing-banner');
        if (banner) banner.style.cssText = 'display: none !important';
    }

    if (payload.step === 'done') {
        // Fade out progress panel after a short delay
        setTimeout(function () {
            var panel = document.getElementById('ai-progress-panel');
            if (panel) {
                panel.style.transition = 'opacity 0.5s';
                panel.style.opacity = '0';
                setTimeout(function () {
                    panel.style.display = 'none';
                    panel.style.opacity = '1';
                    panel.style.transition = '';
                }, 500);
            }
        }, 1500);

        // Reload graph, stage progress, and assessment history
        reloadPageData(studentId);
    } else if (payload.step === 'error') {
        // Keep progress panel visible on error so user can see what happened
    }
}

/**
 * Render the assessment history list as a Bootstrap accordion
 */
var _assessmentItems = [];   // cached full list for pagination
var _assessmentStudentId = null;
var _assessmentPage = 0;
var _assessmentPageSize = 5;

function renderAssessmentList(items, studentId) {
    var card = document.getElementById('ai-assessment-card');
    var container = document.getElementById('ai-assessment-history');
    if (!card || !container) return;

    if (!items || items.length === 0) {
        card.style.display = 'none';
        _lastAssessmentTime = null;
        return;
    }

    // Cache for pagination
    _assessmentItems = items;
    _assessmentStudentId = studentId;
    _assessmentPage = 0;

    // Cache the latest report time for duplicate analysis check
    _lastAssessmentTime = items[0].analyzed_at || null;

    card.style.display = 'block';
    renderAssessmentPage();
}

/**
 * Render current page of assessment history
 */
function renderAssessmentPage() {
    var container = document.getElementById('ai-assessment-history');
    if (!container) return;

    var items = _assessmentItems;
    var studentId = _assessmentStudentId;
    var start = _assessmentPage * _assessmentPageSize;
    var end = Math.min(start + _assessmentPageSize, items.length);
    var totalPages = Math.ceil(items.length / _assessmentPageSize);

    var html = '';

    for (var i = start; i < end; i++) {
        var item = items[i];
        var collapseId = 'assessment-collapse-' + item.id;
        var isFirst = (i === start && _assessmentPage === 0);
        var assessment = item.assessment;

        html += '<div class="accordion-item assessment-item" id="assessment-item-' + item.id + '">';

        // Header
        html += '<h2 class="accordion-header">';
        html += '<div class="d-flex align-items-center">';
        html += '<button class="accordion-button flex-grow-1' + (isFirst ? '' : ' collapsed') + '" ';
        html += 'type="button" data-bs-toggle="collapse" data-bs-target="#' + collapseId + '">';
        html += '<i class="bi bi-file-earmark-text me-2"></i> ';
        html += '<span title="' + escapeHtml(item.analyzed_at) + '">' + escapeHtml(formatSmartTime(item.analyzed_at)) + '</span>';
        if (assessment.overall_level) {
            html += ' <span class="badge bg-primary ms-2">' + escapeHtml(assessment.overall_level) + '</span>';
        }
        html += '</button>';
        html += '<button class="btn btn-sm btn-outline-danger me-2 btn-delete-assessment" ';
        html += 'onclick="deleteAssessment(' + studentId + ', ' + item.id + ')" ';
        html += 'title="删除此报告"><i class="bi bi-trash"></i></button>';
        html += '</div>';
        html += '</h2>';

        // Body
        html += '<div id="' + collapseId + '" class="accordion-collapse collapse' + (isFirst ? ' show' : '') + '">';
        html += '<div class="accordion-body">';
        html += renderSingleAssessment(assessment);
        html += '</div></div>';

        html += '</div>';
    }

    // Pagination controls
    if (totalPages > 1) {
        html += '<nav class="d-flex justify-content-between align-items-center mt-3 px-1">';
        html += '<small class="text-muted">共 ' + items.length + ' 条报告</small>';
        html += '<ul class="pagination pagination-sm mb-0">';
        // Previous
        html += '<li class="page-item' + (_assessmentPage === 0 ? ' disabled' : '') + '">';
        html += '<a class="page-link" href="#" onclick="goAssessmentPage(' + (_assessmentPage - 1) + '); return false;">&laquo;</a></li>';
        // Page numbers
        for (var p = 0; p < totalPages; p++) {
            html += '<li class="page-item' + (p === _assessmentPage ? ' active' : '') + '">';
            html += '<a class="page-link" href="#" onclick="goAssessmentPage(' + p + '); return false;">' + (p + 1) + '</a></li>';
        }
        // Next
        html += '<li class="page-item' + (_assessmentPage === totalPages - 1 ? ' disabled' : '') + '">';
        html += '<a class="page-link" href="#" onclick="goAssessmentPage(' + (_assessmentPage + 1) + '); return false;">&raquo;</a></li>';
        html += '</ul></nav>';
    }

    container.innerHTML = html;
}

/**
 * Navigate to a specific assessment page
 */
function goAssessmentPage(page) {
    var totalPages = Math.ceil(_assessmentItems.length / _assessmentPageSize);
    if (page < 0 || page >= totalPages) return;
    _assessmentPage = page;
    renderAssessmentPage();
    // Scroll the card into view
    var card = document.getElementById('ai-assessment-card');
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Render a single assessment's content (reusable for both history and inline)
 */
function renderSingleAssessment(assessment) {
    var html = '';

    // Overall level + summary
    html += '<div class="mb-3">';
    if (assessment.overall_level) {
        html += '<span class="badge bg-primary fs-6 mb-2">' + escapeHtml(assessment.overall_level) + '</span> ';
    }
    html += '<p class="mb-0">' + escapeHtml(assessment.summary || '') + '</p>';
    html += '</div>';

    // Strengths & Weaknesses in 2 columns
    html += '<div class="row g-3 mb-3">';

    // Strengths
    html += '<div class="col-md-6">';
    html += '<h6 class="fw-bold text-success"><i class="bi bi-check-circle"></i> 优势</h6>';
    html += '<ul class="list-unstyled mb-0">';
    var strengths = assessment.strengths || [];
    for (var i = 0; i < strengths.length; i++) {
        html += '<li class="mb-1"><small>' + escapeHtml(strengths[i]) + '</small></li>';
    }
    html += '</ul></div>';

    // Weaknesses
    html += '<div class="col-md-6">';
    html += '<h6 class="fw-bold text-danger"><i class="bi bi-exclamation-circle"></i> 不足</h6>';
    html += '<ul class="list-unstyled mb-0">';
    var weaknesses = assessment.weaknesses || [];
    for (var j = 0; j < weaknesses.length; j++) {
        html += '<li class="mb-1"><small>' + escapeHtml(weaknesses[j]) + '</small></li>';
    }
    html += '</ul></div>';
    html += '</div>';

    // Stage assessments
    var stageAssessments = assessment.stage_assessments || {};
    var stageKeys = Object.keys(stageAssessments);
    if (stageKeys.length > 0) {
        html += '<div class="mb-3">';
        html += '<h6 class="fw-bold"><i class="bi bi-bar-chart-steps"></i> 分阶段评估</h6>';
        for (var k = 0; k < stageKeys.length; k++) {
            var sid = stageKeys[k];
            var stageName = STAGE_NAMES[parseInt(sid)] || ('阶段' + sid);
            html += '<div class="mb-1"><strong>' + escapeHtml(stageName) + ':</strong> ';
            html += '<small>' + escapeHtml(stageAssessments[sid]) + '</small></div>';
        }
        html += '</div>';
    }

    // Training plan
    var plan = assessment.training_plan || [];
    if (plan.length > 0) {
        html += '<div class="mb-3">';
        html += '<h6 class="fw-bold"><i class="bi bi-list-check"></i> 训练建议</h6>';
        html += '<div class="list-group list-group-flush">';
        for (var p = 0; p < plan.length; p++) {
            var planItem = plan[p];
            html += '<div class="list-group-item px-0 py-1 border-0">';
            html += '<span class="badge bg-secondary me-1">' + (planItem.priority || (p + 1)) + '</span>';
            html += '<strong>' + escapeHtml(planItem.tag_display || planItem.tag || '') + '</strong>: ';
            html += '<small>' + escapeHtml(planItem.suggestion || '') + '</small>';
            html += '</div>';
        }
        html += '</div></div>';
    }

    // Next milestone
    if (assessment.next_milestone) {
        html += '<div class="alert alert-info mb-3 py-2">';
        html += '<i class="bi bi-flag"></i> <strong>下一目标:</strong> ';
        html += escapeHtml(assessment.next_milestone);
        html += '</div>';
    }

    // Encouragement
    if (assessment.encouragement) {
        html += '<div class="alert alert-success mb-3 py-2">';
        html += '<i class="bi bi-emoji-smile"></i> ';
        html += escapeHtml(assessment.encouragement);
        html += '</div>';
    }

    // Contest preparation
    var contestPrep = assessment.contest_preparation || [];
    if (contestPrep.length > 0) {
        html += '<div class="mb-3">';
        html += '<h6 class="fw-bold"><i class="bi bi-trophy"></i> 赛事备赛建议</h6>';
        html += '<div class="row g-2">';
        for (var ci = 0; ci < contestPrep.length; ci++) {
            var cp = contestPrep[ci];
            var daysUntil = cp.days_until || 0;
            var badgeClass = 'bg-primary';
            if (daysUntil <= 30) badgeClass = 'bg-danger';
            else if (daysUntil <= 90) badgeClass = 'bg-warning text-dark';

            html += '<div class="col-md-6">';
            html += '<div class="card border-0 bg-light">';
            html += '<div class="card-body py-2 px-3">';
            html += '<div class="d-flex justify-content-between align-items-center mb-1">';
            html += '<strong>' + escapeHtml(cp.contest || '') + '</strong>';
            html += '<span class="badge ' + badgeClass + '">' + daysUntil + ' 天</span>';
            html += '</div>';
            html += '<small>' + escapeHtml(cp.advice || '') + '</small>';
            html += '</div></div></div>';
        }
        html += '</div></div>';
    }

    return html;
}

/**
 * Render a nudge banner suggesting the user run AI analysis
 */
function renderNudgeBanner(data, studentId) {
    var container = document.getElementById('ai-nudge-banner');
    if (!container) return;

    // Don't show during analysis
    if (_aiAnalyzing) {
        container.style.display = 'none';
        return;
    }

    var latestReportTime = data.latest_report_time || null;
    var newSubmissions = data.new_submissions_since_report || 0;
    var message = '';
    var alertClass = '';

    if (!latestReportTime) {
        // No report ever generated
        alertClass = 'alert-info';
        message = '<i class="bi bi-lightbulb me-2"></i>' +
            '还没有生成过 AI 分析报告，试试 AI 智能分析了解学习情况吧';
    } else if (newSubmissions > 0) {
        // Has new submissions since last report
        alertClass = 'alert-info';
        message = '<i class="bi bi-info-circle me-2"></i>' +
            '自上次分析以来有 <strong>' + newSubmissions + '</strong> 条新做题记录，建议生成新的分析报告';
    } else {
        // All up to date, hide banner
        container.style.display = 'none';
        return;
    }

    container.innerHTML = '<div class="alert ' + alertClass + ' alert-dismissible d-flex align-items-center" role="alert">' +
        '<div class="flex-grow-1">' + message + '</div>' +
        '<button type="button" class="btn btn-primary btn-sm ms-3" onclick="triggerAIAnalysis(' + studentId + ')">' +
        '<i class="bi bi-robot me-1"></i>开始分析</button>' +
        '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>' +
        '</div>';
    container.style.display = '';
}

/**
 * Delete a specific assessment report
 */
function deleteAssessment(studentId, logId) {
    if (!confirm('确定要删除这条分析报告吗？')) return;

    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    fetch('/api/knowledge/' + studentId + '/assessment/' + logId, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': csrfToken ? csrfToken.content : '',
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                // Remove from cached list and re-render page
                _assessmentItems = _assessmentItems.filter(function(item) { return item.id !== logId; });
                if (_assessmentItems.length === 0) {
                    var card = document.getElementById('ai-assessment-card');
                    if (card) card.style.display = 'none';
                    _lastAssessmentTime = null;
                } else {
                    // Adjust page if current page is now out of range
                    var totalPages = Math.ceil(_assessmentItems.length / _assessmentPageSize);
                    if (_assessmentPage >= totalPages) _assessmentPage = totalPages - 1;
                    _lastAssessmentTime = _assessmentItems[0].analyzed_at || null;
                    renderAssessmentPage();
                }
            } else {
                alert(data.error || '删除失败');
            }
        })
        .catch(function (err) {
            console.error('Delete assessment failed:', err);
            alert('删除请求失败');
        });
}
