/**
 * Info page for victron-bm-webui.
 * Fetches /api/v1/health, /api/v1/status and /api/v1/config to populate system info.
 */
(function () {
    "use strict";

    var REFRESH_INTERVAL_MS = 10000;

    /**
     * Format uptime seconds into a human-readable string.
     */
    function formatUptime(seconds) {
        if (seconds == null) return "-";
        var d = Math.floor(seconds / 86400);
        var h = Math.floor((seconds % 86400) / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        var parts = [];
        if (d > 0) parts.push(d + "d");
        if (h > 0) parts.push(h + "h");
        parts.push(m + "m");
        return parts.join(" ");
    }

    /**
     * Format bytes into a readable string (KB/MB).
     */
    function formatBytes(bytes) {
        if (bytes == null) return "-";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1048576).toFixed(1) + " MB";
    }

    /**
     * Format ISO timestamp to local date/time.
     */
    function formatTimestamp(isoStr) {
        if (!isoStr) return "-";
        var d = new Date(isoStr);
        var pad = function (n) { return n < 10 ? "0" + n : "" + n; };
        return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
            " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    }

    /**
     * Format a threshold value with unit, or show "Disabled".
     */
    function formatThreshold(val, unit) {
        if (val == null) return '<span class="text-body-secondary">Disabled</span>';
        return val + " " + unit;
    }

    /**
     * Set element text content by ID.
     */
    function setText(id, text) {
        var el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    /**
     * Set element innerHTML by ID.
     */
    function setHtml(id, html) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = html;
    }

    /**
     * Fetch all info data and update the page.
     */
    function refresh() {
        Promise.all([
            fetch("/api/v1/health").then(function (r) { return r.ok ? r.json() : null; }),
            fetch("/api/v1/status").then(function (r) { return r.ok ? r.json() : null; }),
            fetch("/api/v1/config").then(function (r) { return r.ok ? r.json() : null; })
        ])
            .then(function (results) {
                var health = results[0];
                var status = results[1];
                var config = results[2];

                // Device info
                if (status) {
                    setText("info-device-name", status.device_name || "-");
                    if (status.connected) {
                        setHtml("info-ble-status",
                            '<span class="badge bg-success">Connected</span>');
                    } else {
                        setHtml("info-ble-status",
                            '<span class="badge bg-danger">Disconnected</span>');
                    }
                    setText("info-last-update", formatTimestamp(status.last_update));
                }

                // Health info
                if (health) {
                    setHtml("info-app-status",
                        '<span class="badge bg-success">' + (health.status || "ok") + "</span>");
                    setText("info-uptime", formatUptime(health.uptime_seconds));
                    setText("info-server-time", formatTimestamp(health.timestamp));

                    // BLE mode
                    if (health.ble) {
                        var modeLabel = health.ble.mode === "mock" ? "Mock (simulated data)" : "BLE (real device)";
                        var modeBadge = health.ble.mode === "mock" ? "bg-warning text-dark" : "bg-primary";
                        setHtml("info-ble-mode",
                            '<span class="badge ' + modeBadge + '">' + modeLabel + "</span>");
                    }

                    // Database
                    if (health.database) {
                        setText("info-readings-count",
                            (health.database.readings_count || 0).toLocaleString());
                        setText("info-alarms-count",
                            (health.database.alarms_count || 0).toLocaleString());
                        setText("info-db-size", formatBytes(health.database.size_bytes));
                    }
                }

                // Config info
                if (config) {
                    // SMTP
                    if (config.smtp_enabled) {
                        setHtml("info-smtp-status",
                            '<span class="badge bg-success">Enabled</span>');
                    } else {
                        setHtml("info-smtp-status",
                            '<span class="badge bg-secondary">Disabled</span>');
                    }
                    setText("info-smtp-recipients",
                        config.smtp_recipients && config.smtp_recipients.length > 0
                            ? config.smtp_recipients.join(", ")
                            : "None configured");

                    // Thresholds
                    if (config.alarms) {
                        setHtml("info-th-low-voltage",
                            formatThreshold(config.alarms.low_voltage, "V"));
                        setHtml("info-th-high-voltage",
                            formatThreshold(config.alarms.high_voltage, "V"));
                        setHtml("info-th-low-soc",
                            formatThreshold(config.alarms.low_soc, "%"));
                        setHtml("info-th-high-temperature",
                            formatThreshold(config.alarms.high_temperature, "\u00B0C"));
                        setHtml("info-th-low-temperature",
                            formatThreshold(config.alarms.low_temperature, "\u00B0C"));
                    }
                }

                setText("info-refresh-status",
                    "Last refreshed: " + new Date().toLocaleTimeString());
            })
            .catch(function () {
                setText("info-refresh-status", "Error loading data");
            });
    }

    // Initial load + periodic refresh
    refresh();
    setInterval(refresh, REFRESH_INTERVAL_MS);
})();
