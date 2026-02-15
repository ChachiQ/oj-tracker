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

    // Load assessment history
    loadAssessmentHistory(studentId);
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

// ============================================================
// AI Knowledge Assessment — SSE streaming + history management
// ============================================================

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

    // Set loading state
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> 分析中...';

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
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-robot"></i> AI 智能分析';
        });
}

/**
 * Handle a single SSE progress event
 */
function handleProgressEvent(payload, studentId) {
    appendProgressLog(payload.step, payload.message, payload.detail || '');

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

        // Reload the full history to get the new item with its DB id
        loadAssessmentHistory(studentId);
    } else if (payload.step === 'error') {
        // Keep progress panel visible on error so user can see what happened
    }
}

/**
 * Render the assessment history list as a Bootstrap accordion
 */
function renderAssessmentList(items, studentId) {
    var card = document.getElementById('ai-assessment-card');
    var container = document.getElementById('ai-assessment-history');
    if (!card || !container) return;

    if (!items || items.length === 0) {
        card.style.display = 'none';
        return;
    }

    card.style.display = 'block';
    var html = '';

    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var collapseId = 'assessment-collapse-' + item.id;
        var isFirst = (i === 0);
        var assessment = item.assessment;

        html += '<div class="accordion-item assessment-item" id="assessment-item-' + item.id + '">';

        // Header
        html += '<h2 class="accordion-header">';
        html += '<div class="d-flex align-items-center">';
        html += '<button class="accordion-button flex-grow-1' + (isFirst ? '' : ' collapsed') + '" ';
        html += 'type="button" data-bs-toggle="collapse" data-bs-target="#' + collapseId + '">';
        html += '<i class="bi bi-file-earmark-text me-2"></i> ';
        html += '<span>' + escapeHtml(item.analyzed_at) + '</span>';
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

    container.innerHTML = html;
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
        html += '<div class="alert alert-info mb-0 py-2">';
        html += '<i class="bi bi-flag"></i> <strong>下一目标:</strong> ';
        html += escapeHtml(assessment.next_milestone);
        html += '</div>';
    }

    return html;
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
                // Remove the DOM element
                var el = document.getElementById('assessment-item-' + logId);
                if (el) {
                    el.style.transition = 'opacity 0.3s';
                    el.style.opacity = '0';
                    setTimeout(function () {
                        el.remove();
                        // Hide container if no items left
                        var container = document.getElementById('ai-assessment-history');
                        if (container && container.children.length === 0) {
                            var card = document.getElementById('ai-assessment-card');
                            if (card) card.style.display = 'none';
                        }
                    }, 300);
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
