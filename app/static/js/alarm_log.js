/**
 * Alarm Log page for victron-bm-webui.
 * Fetches /api/v1/alarms and renders a paginated table with notification badges.
 */
(function () {
    "use strict";

    var PAGE_SIZE = 25;
    var currentRange = "24h";
    var allAlarms = [];
    var currentPage = 1;

    var tableBody = document.getElementById("alarm-table-body");
    var statusEl = document.getElementById("alarm-status");
    var paginationBtns = document.getElementById("pagination-btns");
    var btnPrev = document.getElementById("btn-prev");
    var btnNext = document.getElementById("btn-next");
    var btnPageInfo = document.getElementById("btn-page-info");

    /**
     * Compute ISO "from" timestamp for a given range.
     */
    function getFromTimestamp(range) {
        if (range === "all") return null;
        var now = new Date();
        var ms = {
            "1h": 3600000,
            "6h": 21600000,
            "24h": 86400000,
            "7d": 604800000,
            "30d": 2592000000
        };
        var offset = ms[range] || 86400000;
        return new Date(now.getTime() - offset).toISOString();
    }

    /**
     * Format ISO timestamp to a readable local date/time string.
     */
    function formatTimestamp(isoStr) {
        if (!isoStr) return "-";
        var d = new Date(isoStr);
        var pad = function (n) { return n < 10 ? "0" + n : "" + n; };
        return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
            " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    }

    /**
     * Get a Bootstrap badge class for alarm type.
     */
    function getAlarmBadgeClass(alarmType) {
        if (!alarmType) return "bg-secondary";
        var t = alarmType.toUpperCase();
        if (t.indexOf("OFFLINE") >= 0) return "bg-danger";
        if (t.indexOf("ONLINE") >= 0) return "bg-success";
        if (t.indexOf("CLEARED") >= 0) return "bg-info";
        if (t.indexOf("THRESHOLD") >= 0) return "bg-warning text-dark";
        if (t.indexOf("DEVICE_") >= 0) return "bg-danger";
        return "bg-secondary";
    }

    /**
     * Format alarm type for display (make it shorter and readable).
     */
    function formatAlarmType(alarmType) {
        if (!alarmType) return "Unknown";
        return alarmType.replace(/_/g, " ");
    }

    /**
     * Render the current page of alarms into the table.
     */
    function renderTable() {
        var totalPages = Math.max(1, Math.ceil(allAlarms.length / PAGE_SIZE));
        if (currentPage > totalPages) currentPage = totalPages;

        var start = (currentPage - 1) * PAGE_SIZE;
        var pageAlarms = allAlarms.slice(start, start + PAGE_SIZE);

        if (pageAlarms.length === 0) {
            tableBody.innerHTML =
                '<tr><td colspan="4" class="text-center text-body-secondary py-4">' +
                '<i class="bi bi-check-circle display-6 d-block mb-2"></i>' +
                'No alarms in the selected time range.</td></tr>';
            paginationBtns.style.display = "none";
            statusEl.textContent = "No alarms found";
            return;
        }

        var html = "";
        for (var i = 0; i < pageAlarms.length; i++) {
            var a = pageAlarms[i];
            var badgeClass = getAlarmBadgeClass(a.alarm_type);
            var notifiedIcon = a.notified
                ? '<span class="badge bg-success"><i class="bi bi-envelope-check"></i> Sent</span>'
                : '<span class="badge bg-secondary"><i class="bi bi-envelope-slash"></i> No</span>';

            html += "<tr>";
            html += '<td class="text-nowrap"><small>' + formatTimestamp(a.timestamp) + "</small></td>";
            html += '<td><span class="badge ' + badgeClass + '">' + formatAlarmType(a.alarm_type) + "</span></td>";
            html += '<td class="d-none d-md-table-cell"><small>' + (a.message || "-") + "</small></td>";
            html += '<td class="text-center">' + notifiedIcon + "</td>";
            html += "</tr>";
        }
        tableBody.innerHTML = html;

        // Pagination
        if (totalPages > 1) {
            paginationBtns.style.display = "inline-flex";
            btnPrev.disabled = currentPage <= 1;
            btnNext.disabled = currentPage >= totalPages;
            btnPageInfo.textContent = currentPage + " / " + totalPages;
        } else {
            paginationBtns.style.display = "none";
        }

        statusEl.textContent = allAlarms.length + " alarm" + (allAlarms.length !== 1 ? "s" : "") + " found";
    }

    /**
     * Fetch alarms from the API and re-render.
     */
    function fetchAlarms() {
        var fromTs = getFromTimestamp(currentRange);
        var url = "/api/v1/alarms?limit=1000";
        if (fromTs) url += "&from=" + encodeURIComponent(fromTs);

        statusEl.textContent = "Loading...";
        tableBody.innerHTML =
            '<tr><td colspan="4" class="text-center text-body-secondary py-4">' +
            '<div class="spinner-border spinner-border-sm me-2" role="status"></div>' +
            "Loading alarms...</td></tr>";

        fetch(url)
            .then(function (res) {
                if (!res.ok) throw new Error("HTTP " + res.status);
                return res.json();
            })
            .then(function (data) {
                allAlarms = data.alarms || [];
                currentPage = 1;
                renderTable();
            })
            .catch(function () {
                tableBody.innerHTML =
                    '<tr><td colspan="4" class="text-center text-danger py-4">' +
                    '<i class="bi bi-exclamation-triangle me-2"></i>' +
                    "Failed to load alarm data.</td></tr>";
                statusEl.textContent = "Error loading data";
            });
    }

    // Time range buttons
    var rangeButtons = document.querySelectorAll("#time-range-btns .btn");
    for (var i = 0; i < rangeButtons.length; i++) {
        rangeButtons[i].addEventListener("click", function () {
            for (var j = 0; j < rangeButtons.length; j++) {
                rangeButtons[j].classList.remove("active");
            }
            this.classList.add("active");
            currentRange = this.getAttribute("data-range");
            fetchAlarms();
        });
    }

    // Pagination buttons
    btnPrev.addEventListener("click", function () {
        if (currentPage > 1) {
            currentPage--;
            renderTable();
        }
    });
    btnNext.addEventListener("click", function () {
        var totalPages = Math.ceil(allAlarms.length / PAGE_SIZE);
        if (currentPage < totalPages) {
            currentPage++;
            renderTable();
        }
    });

    // Initial load
    fetchAlarms();
})();
