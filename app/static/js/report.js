/**
 * OJ Tracker - Report Page JavaScript
 * Handles radar chart comparison between previous and current period
 */
document.addEventListener('DOMContentLoaded', function () {
    initReportRadar();
});

/**
 * Initialize the radar chart comparing previous vs current period scores
 */
function initReportRadar() {
    var container = document.getElementById('report-radar');
    if (!container) return;

    var prevData = {};
    var currData = {};

    try {
        prevData = JSON.parse(container.dataset.prev || '{}');
    } catch (e) {
        prevData = {};
    }
    try {
        currData = JSON.parse(container.dataset.curr || '{}');
    } catch (e) {
        currData = {};
    }

    // Collect all unique keys
    var keySet = {};
    Object.keys(prevData).forEach(function (k) { keySet[k] = true; });
    Object.keys(currData).forEach(function (k) { keySet[k] = true; });
    var allKeys = Object.keys(keySet);

    if (allKeys.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-5">暂无能力对比数据</div>';
        return;
    }

    // Ensure at least 3 dimensions for radar
    while (allKeys.length < 3) {
        allKeys.push('--');
    }

    var chart = echarts.init(container);

    var option = {
        title: {
            text: '能力变化对比',
            left: 'center',
            textStyle: {
                fontSize: 14,
                color: '#5a5c69'
            }
        },
        tooltip: {
            trigger: 'item'
        },
        legend: {
            data: ['上期', '本期'],
            bottom: 10,
            textStyle: { fontSize: 12 }
        },
        radar: {
            indicator: allKeys.map(function (k) {
                return { name: k, max: 100 };
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
            data: [
                {
                    value: allKeys.map(function (k) { return prevData[k] || 0; }),
                    name: '上期',
                    lineStyle: {
                        type: 'dashed',
                        opacity: 0.6,
                        color: '#858796',
                        width: 2
                    },
                    areaStyle: {
                        opacity: 0.1,
                        color: '#858796'
                    },
                    itemStyle: {
                        color: '#858796'
                    }
                },
                {
                    value: allKeys.map(function (k) { return currData[k] || 0; }),
                    name: '本期',
                    lineStyle: {
                        color: '#4e73df',
                        width: 2
                    },
                    areaStyle: {
                        opacity: 0.25,
                        color: '#4e73df'
                    },
                    itemStyle: {
                        color: '#4e73df'
                    }
                }
            ]
        }]
    };

    chart.setOption(option);
    window.addEventListener('resize', function () { chart.resize(); });
}
