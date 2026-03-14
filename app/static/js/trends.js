/**
 * Trends chart page for victron-bm-webui.
 * Dual-axis Chart.js time-series with selectable metrics and time ranges.
 */
(function () {
    "use strict";

    // Metric definitions: label, unit, color, y-axis range hints
    var METRICS = {
        voltage:     { label: "Voltage",     unit: "V",  color: "#0d6efd", min: 10, max: 16 },
        current:     { label: "Current",     unit: "A",  color: "#198754", min: null, max: null },
        power:       { label: "Power",       unit: "W",  color: "#6f42c1", min: null, max: null },
        soc:         { label: "SoC",         unit: "%",  color: "#ffc107", min: 0, max: 100 },
        consumed_ah: { label: "Consumed",    unit: "Ah", color: "#fd7e14", min: null, max: null },
        temperature: { label: "Temperature", unit: "\u00B0C", color: "#dc3545", min: null, max: null }
    };

    // Time range -> { hours, resolution }
    var RANGES = {
        "1h":  { hours: 1,    resolution: "raw" },
        "6h":  { hours: 6,    resolution: "1min" },
        "24h": { hours: 24,   resolution: "5min" },
        "7d":  { hours: 168,  resolution: "15min" },
        "30d": { hours: 720,  resolution: "1h" }
    };

    // State
    var currentRange = "24h";
    var chart = null;

    // DOM
    var canvas = document.getElementById("trends-chart");
    var chartStatus = document.getElementById("chart-status");
    var metricLeft = document.getElementById("metric-left");
    var metricRight = document.getElementById("metric-right");
    var rangeButtons = document.querySelectorAll("#time-range-btns button");

    /**
     * Build the Chart.js config for dual-axis display.
     */
    function buildChart(readings, leftKey, rightKey) {
        var leftMeta = METRICS[leftKey];
        var rightMeta = rightKey ? METRICS[rightKey] : null;

        var timestamps = readings.map(function (r) { return r.timestamp; });
        var leftData = readings.map(function (r) { return r[leftKey]; });

        var datasets = [
            {
                label: leftMeta.label + " (" + leftMeta.unit + ")",
                data: leftData,
                borderColor: leftMeta.color,
                backgroundColor: leftMeta.color + "20",
                yAxisID: "y-left",
                tension: 0.3,
                pointRadius: 0,
                pointHitRadius: 8,
                borderWidth: 2,
                fill: false
            }
        ];

        var scales = {
            x: {
                type: "time",
                time: {
                    tooltipFormat: "yyyy-MM-dd HH:mm:ss",
                    displayFormats: {
                        minute: "HH:mm",
                        hour: "HH:mm",
                        day: "MMM d"
                    }
                },
                grid: { color: "rgba(255,255,255,0.08)" },
                ticks: { color: "rgba(255,255,255,0.6)", maxTicksLimit: 10 }
            },
            "y-left": {
                type: "linear",
                position: "left",
                title: {
                    display: true,
                    text: leftMeta.label + " (" + leftMeta.unit + ")",
                    color: leftMeta.color
                },
                grid: { color: "rgba(255,255,255,0.08)" },
                ticks: { color: leftMeta.color },
                min: leftMeta.min,
                max: leftMeta.max
            }
        };

        if (rightMeta && rightKey !== leftKey) {
            var rightData = readings.map(function (r) { return r[rightKey]; });
            datasets.push({
                label: rightMeta.label + " (" + rightMeta.unit + ")",
                data: rightData,
                borderColor: rightMeta.color,
                backgroundColor: rightMeta.color + "20",
                yAxisID: "y-right",
                tension: 0.3,
                pointRadius: 0,
                pointHitRadius: 8,
                borderWidth: 2,
                borderDash: [5, 3],
                fill: false
            });
            scales["y-right"] = {
                type: "linear",
                position: "right",
                title: {
                    display: true,
                    text: rightMeta.label + " (" + rightMeta.unit + ")",
                    color: rightMeta.color
                },
                grid: { drawOnChartArea: false },
                ticks: { color: rightMeta.color },
                min: rightMeta.min,
                max: rightMeta.max
            };
        }

        return {
            type: "line",
            data: {
                labels: timestamps,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: "index",
                    intersect: false
                },
                plugins: {
                    legend: {
                        labels: { color: "rgba(255,255,255,0.8)" }
                    },
                    tooltip: {
                        backgroundColor: "rgba(30,30,30,0.95)",
                        titleColor: "#fff",
                        bodyColor: "#ccc",
                        borderColor: "rgba(255,255,255,0.1)",
                        borderWidth: 1
                    }
                },
                scales: scales
            }
        };
    }

    /**
     * Fetch data and render (or update) the chart.
     */
    function loadChart() {
        var leftKey = metricLeft.value;
        var rightKey = metricRight.value;
        var range = RANGES[currentRange];

        var now = new Date();
        var from = new Date(now.getTime() - range.hours * 3600 * 1000);
        var fields = [leftKey];
        if (rightKey && rightKey !== leftKey) fields.push(rightKey);

        var url = "/api/v1/history?from=" + encodeURIComponent(from.toISOString())
                + "&to=" + encodeURIComponent(now.toISOString())
                + "&fields=" + fields.join(",")
                + "&resolution=" + range.resolution;

        chartStatus.textContent = "Loading...";

        fetch(url)
            .then(function (resp) {
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                return resp.json();
            })
            .then(function (data) {
                var readings = data.readings || [];
                chartStatus.textContent = readings.length + " data points (" + data.resolution + ")";

                if (chart) {
                    chart.destroy();
                }

                var config = buildChart(readings, leftKey, rightKey);
                chart = new Chart(canvas, config);
            })
            .catch(function (err) {
                chartStatus.textContent = "Error loading data: " + err.message;
            });
    }

    // Event: time range buttons
    rangeButtons.forEach(function (btn) {
        btn.addEventListener("click", function () {
            rangeButtons.forEach(function (b) { b.classList.remove("active"); });
            btn.classList.add("active");
            currentRange = btn.getAttribute("data-range");
            loadChart();
        });
    });

    // Event: metric selectors
    metricLeft.addEventListener("change", loadChart);
    metricRight.addEventListener("change", loadChart);

    // Initial load
    loadChart();
})();
