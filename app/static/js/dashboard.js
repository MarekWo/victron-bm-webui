/**
 * Dashboard live data polling for victron-bm-webui.
 * Fetches /api/internal/current every 5 seconds and updates the DOM.
 */
(function () {
    "use strict";

    const POLL_INTERVAL_MS = 5000;

    // DOM elements
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");
    const socValue = document.getElementById("soc-value");
    const socBar = document.getElementById("soc-bar");
    const valVoltage = document.getElementById("val-voltage");
    const valCurrent = document.getElementById("val-current");
    const valPower = document.getElementById("val-power");
    const valConsumed = document.getElementById("val-consumed");
    const valRemaining = document.getElementById("val-remaining");
    const valTemperature = document.getElementById("val-temperature");
    const alarmBanner = document.getElementById("alarm-banner");
    const alarmText = document.getElementById("alarm-text");
    const lastUpdateText = document.getElementById("last-update-text");

    /**
     * Format remaining minutes into human-readable string.
     */
    function formatRemaining(mins) {
        if (mins == null || mins >= 65535) return "\u221E";
        if (mins < 60) return mins + "m";
        const h = Math.floor(mins / 60);
        const m = mins % 60;
        return h + "h " + (m < 10 ? "0" : "") + m + "m";
    }

    /**
     * Get SoC bar color class based on percentage.
     * Green > 50%, Yellow 20-50%, Red < 20%.
     */
    function getSocColorClass(soc) {
        if (soc > 50) return "bg-success";
        if (soc >= 20) return "bg-warning";
        return "bg-danger";
    }

    /**
     * Format time elapsed since a given ISO timestamp.
     */
    function formatTimeAgo(isoString) {
        if (!isoString) return "never";
        const then = new Date(isoString);
        const now = new Date();
        const diffSec = Math.floor((now - then) / 1000);
        if (diffSec < 5) return "just now";
        if (diffSec < 60) return diffSec + "s ago";
        if (diffSec < 3600) return Math.floor(diffSec / 60) + "m ago";
        return Math.floor(diffSec / 3600) + "h ago";
    }

    /**
     * Format a numeric value with fixed decimals, or return "--" if null.
     */
    function fmt(value, decimals, unit) {
        if (value == null) return "-- " + unit;
        return value.toFixed(decimals) + " " + unit;
    }

    /**
     * Update the dashboard DOM with fresh data.
     */
    function updateDashboard(data) {
        // Connection status
        if (data.connected) {
            statusDot.className = "status-dot online";
            statusText.textContent = "Connected";
        } else {
            statusDot.className = "status-dot offline";
            statusText.textContent = "Disconnected";
        }

        // SoC
        const soc = data.soc;
        if (soc != null) {
            socValue.textContent = soc.toFixed(1) + " %";
            socBar.style.width = soc + "%";
            socBar.className = "progress-bar " + getSocColorClass(soc);
        } else {
            socValue.textContent = "-- %";
            socBar.style.width = "0%";
            socBar.className = "progress-bar bg-secondary";
        }

        // Metric cards
        valVoltage.textContent = fmt(data.voltage, 2, "V");
        valCurrent.textContent = fmt(data.current, 2, "A");
        valPower.textContent = fmt(data.power, 1, "W");
        valConsumed.textContent = fmt(data.consumed_ah, 1, "Ah");
        valRemaining.textContent = formatRemaining(data.remaining_mins);
        valTemperature.textContent = fmt(data.temperature, 1, "\u00B0C");

        // Alarm banner
        if (data.alarm) {
            alarmBanner.classList.add("active");
            alarmText.textContent = data.alarm;
        } else {
            alarmBanner.classList.remove("active");
            alarmText.textContent = "";
        }

        // Last update
        lastUpdateText.textContent = "Last update: " + formatTimeAgo(data.last_update);
    }

    /**
     * Fetch current state from the server.
     */
    function poll() {
        fetch("/api/internal/current")
            .then(function (response) {
                if (!response.ok) throw new Error("HTTP " + response.status);
                return response.json();
            })
            .then(function (data) {
                updateDashboard(data);
            })
            .catch(function () {
                statusDot.className = "status-dot offline";
                statusText.textContent = "Connection error";
                lastUpdateText.textContent = "Failed to fetch data";
            });
    }

    // Initial fetch + start polling
    poll();
    setInterval(poll, POLL_INTERVAL_MS);
})();
