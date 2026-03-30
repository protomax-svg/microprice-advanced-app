const pageName = document.body.dataset.page || "";

function readJsonScript(id) {
    const element = document.getElementById(id);
    if (!element) {
        return null;
    }

    try {
        return JSON.parse(element.textContent);
    } catch (error) {
        console.error(`Failed to parse JSON from #${id}`, error);
        return null;
    }
}

function formatNumber(value, digits) {
    if (value === null || value === undefined || Number.isNaN(value)) {
        return "n/a";
    }
    return Number(value).toFixed(digits);
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function parseEventTimestamp(event) {
    const numericTs = Number(event.event_ts);
    if (Number.isFinite(numericTs)) {
        return numericTs * 1000;
    }

    const parsedTs = Date.parse(event.event_time_utc || "");
    return Number.isFinite(parsedTs) ? parsedTs : NaN;
}

let belowActualMetrics = null;
let belowActualMetricsRequest = null;

function setConnectionStatus(status, detail) {
    const element = document.getElementById("connection-status");
    if (!element) {
        return;
    }

    element.textContent = detail ? `${status}: ${detail}` : status;
    element.className = `status-pill ${status}`;
}

function updateLiveMetrics(payload) {
    const current = payload.current || {};
    const priceDigits = payload.price_display_decimals || 8;

    const metricMap = {
        "metric-symbol": payload.symbol || "n/a",
        "metric-actual-price": formatNumber(current.actual_price, priceDigits),
        "metric-optimal-price": formatNumber(current.optimal_price, priceDigits),
        "metric-microprice": formatNumber(current.microprice_3, priceDigits),
        "metric-imbalance": formatNumber(current.imbalance_3, 6),
        "metric-ob-vol": formatNumber(current.ob_vol_index, 6),
        "metric-saved-events": String(payload.saved_event_count ?? 0),
        "metric-active-windows": String(payload.active_event_windows_count ?? 0),
    };

    Object.entries(metricMap).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    });

    const lastUpdated = document.getElementById("last-updated");
    if (lastUpdated) {
        lastUpdated.textContent = payload.updated_at ? `updated ${payload.updated_at}` : "waiting for data";
    }

    setConnectionStatus(payload.connection_status || "starting", payload.last_error || "");
}

function buildFigure(dataset, options = {}) {
    const xValues = dataset.x || [];
    const customdata = dataset.customdata || null;
    const xaxis = {
        domain: [0, 1],
        anchor: "y",
        showticklabels: false,
        matches: "x3",
        gridcolor: "#203048",
        zeroline: false,
    };
    const xaxis2 = {
        domain: [0, 1],
        anchor: "y2",
        showticklabels: false,
        matches: "x3",
        gridcolor: "#203048",
        zeroline: false,
    };
    const xaxis3 = {
        domain: [0, 1],
        anchor: "y3",
        title: options.xTitle || "UTC Time",
        gridcolor: "#203048",
        zeroline: false,
    };

    if (!options.relativeTime) {
        xaxis.type = "date";
        xaxis2.type = "date";
        xaxis3.type = "date";
    }

    function makeTrace(name, values, color, xaxis, yaxis, digits) {
        return {
            type: "scatter",
            mode: "lines",
            name,
            x: xValues,
            y: values,
            xaxis,
            yaxis,
            line: { color, width: 2 },
            customdata,
            connectgaps: false,
            hovertemplate: customdata
                ? `${name}<br>offset: %{x:.3f}s<br>time: %{customdata}<br>value: %{y:.${digits}f}<extra></extra>`
                : `${name}<br>%{x}<br>value: %{y:.${digits}f}<extra></extra>`,
        };
    }

    return {
        data: [
            makeTrace("Actual Price", dataset.actual_price || [], "#f8fafc", "x", "y", 8),
            makeTrace("Optimal Price", dataset.optimal_price || [], "#ff6b6b", "x", "y", 8),
            makeTrace("Microprice", dataset.microprice_3 || [], "#4dabf7", "x", "y", 8),
            makeTrace("Imbalance", dataset.imbalance_3 || [], "#f59e0b", "x2", "y2", 6),
            makeTrace("OB Volatility Index", dataset.ob_vol_index || [], "#34d399", "x3", "y3", 6),
        ],
        layout: {
            paper_bgcolor: "#07111e",
            plot_bgcolor: "#07111e",
            font: {
                color: "#eef4ff",
                family: '"Segoe UI", Tahoma, Geneva, Verdana, sans-serif',
            },
            margin: { l: 58, r: 28, t: 26, b: 48 },
            legend: {
                orientation: "h",
                yanchor: "bottom",
                y: 1.02,
                xanchor: "left",
                x: 0,
            },
            hovermode: "x unified",
            uirevision: options.uirevision || "chart",
            xaxis,
            yaxis: {
                domain: [0.42, 1],
                title: "Price",
                gridcolor: "#203048",
            },
            xaxis2,
            yaxis2: {
                domain: [0.21, 0.38],
                title: "Imbalance",
                gridcolor: "#203048",
                zeroline: true,
                zerolinecolor: "#52667f",
            },
            xaxis3,
            yaxis3: {
                domain: [0, 0.17],
                title: "OB Vol",
                gridcolor: "#203048",
                zeroline: true,
                zerolinecolor: "#52667f",
            },
            annotations: xValues.length
                ? []
                : [{
                    text: options.emptyText || "Waiting for data",
                    x: 0.5,
                    y: 0.5,
                    xref: "paper",
                    yref: "paper",
                    showarrow: false,
                    font: { color: "#98a8c3", size: 15 },
                }],
            shapes: options.showEventMarker
                ? [{
                    type: "line",
                    xref: "x3",
                    yref: "paper",
                    x0: 0,
                    x1: 0,
                    y0: 0,
                    y1: 1,
                    line: { color: "#ffb86b", width: 1.5, dash: "dot" },
                }]
                : [],
        },
        config: {
            responsive: true,
            displaylogo: false,
        },
    };
}

function renderLiveChart(payload) {
    const target = document.getElementById("live-chart");
    if (!target || !window.Plotly) {
        return;
    }

    const figure = buildFigure({
        x: payload.series?.timestamps || [],
        actual_price: payload.series?.actual_price || [],
        optimal_price: payload.series?.optimal_price || [],
        microprice_3: payload.series?.microprice_3 || [],
        imbalance_3: payload.series?.imbalance_3 || [],
        ob_vol_index: payload.series?.ob_vol_index || [],
    }, {
        xTitle: "UTC Time",
        emptyText: "Waiting for Binance Spot data",
        uirevision: "live",
    });

    window.Plotly.react(target, figure.data, figure.layout, figure.config);
}

function renderEventChart(payload) {
    const target = document.getElementById("event-chart");
    if (!target || !window.Plotly) {
        return;
    }

    const figure = buildFigure({
        x: payload.snapshots?.seconds_from_event || [],
        customdata: payload.snapshots?.snapshot_time_utc || [],
        actual_price: payload.snapshots?.actual_price || [],
        optimal_price: payload.snapshots?.optimal_price || [],
        microprice_3: payload.snapshots?.microprice_3 || [],
        imbalance_3: payload.snapshots?.imbalance_3 || [],
        ob_vol_index: payload.snapshots?.ob_vol_index || [],
    }, {
        xTitle: "Seconds from Event",
        emptyText: "No snapshots stored for this event",
        relativeTime: true,
        showEventMarker: true,
        uirevision: `event-${payload.event?.id || "detail"}`,
    });

    window.Plotly.react(target, figure.data, figure.layout, figure.config);
}

function renderEventsList(container, events, activeEventId) {
    if (!container) {
        return;
    }

    if (!events.length) {
        container.innerHTML = `
            <div class="empty-state">
                No saved events yet. Once a full pre/post event window is captured, it will appear here automatically.
            </div>
        `;
        return;
    }

    container.innerHTML = events.map((event) => {
        const isActive = activeEventId && String(activeEventId) === String(event.id);
        return `
            <a href="/events/${event.id}" class="event-row ${isActive ? "active" : ""}">
                <span class="event-time">${escapeHtml(event.event_time_utc)}</span>
                <span class="event-meta">#${event.id} · ${escapeHtml(event.symbol)} · status ${escapeHtml(event.status)}</span>
                <span class="event-count">${event.snapshot_count} snapshots</span>
            </a>
        `;
    }).join("");
}

function isBelowActualThresholdFilterEnabled() {
    return eventBrowsers.some((browser) => browser.querySelector("[data-filter-below-actual-threshold]")?.checked);
}

function applyBelowActualMetrics(events) {
    events.forEach((event) => {
        const metricValue = belowActualMetrics?.[String(event.id)] ?? belowActualMetrics?.[event.id] ?? 0;
        event.max_below_actual_seconds_10s = Number(metricValue) || 0;
    });
}

function hasMissingBelowActualMetrics(events) {
    if (!belowActualMetrics) {
        return events.length > 0;
    }

    return events.some((event) => belowActualMetrics[String(event.id)] === undefined && belowActualMetrics[event.id] === undefined);
}

async function ensureBelowActualMetrics(forceRefresh = false) {
    if (!forceRefresh && belowActualMetrics) {
        return belowActualMetrics;
    }

    if (!forceRefresh && belowActualMetricsRequest) {
        return belowActualMetricsRequest;
    }

    belowActualMetricsRequest = fetch("/api/events/metrics/below-actual?window_seconds=10", { cache: "no-store" })
        .then((response) => response.json())
        .then((payload) => {
            belowActualMetrics = payload.metrics || {};
            belowActualMetricsRequest = null;
            return belowActualMetrics;
        })
        .catch((error) => {
            belowActualMetricsRequest = null;
            throw error;
        });

    return belowActualMetricsRequest;
}

function refreshAllEventBrowsers() {
    eventBrowsers.forEach((browser) => {
        updateEventBrowser(browser, browser._events || []);
    });
}

function applyEventFilters(events, browser) {
    const fromInput = browser.querySelector("[data-filter-from]");
    const toInput = browser.querySelector("[data-filter-to]");
    const dedupeInput = browser.querySelector("[data-filter-dedupe]");
    const belowActualThresholdInput = browser.querySelector("[data-filter-below-actual-threshold]");

    const fromValue = fromInput?.value ? new Date(fromInput.value).getTime() : NaN;
    const toValue = toInput?.value ? new Date(toInput.value).getTime() : NaN;
    const shouldDedupe = Boolean(dedupeInput?.checked);
    const shouldRequireBelowActualThreshold = Boolean(belowActualThresholdInput?.checked);

    const rangeFiltered = events.filter((event) => {
        const eventMs = parseEventTimestamp(event);
        if (!Number.isFinite(eventMs)) {
            return false;
        }
        if (Number.isFinite(fromValue) && eventMs < fromValue) {
            return false;
        }
        if (Number.isFinite(toValue) && eventMs > toValue) {
            return false;
        }
        return true;
    });

    const thresholdFiltered = shouldRequireBelowActualThreshold
        ? rangeFiltered.filter((event) => Number(event.max_below_actual_seconds_10s || 0) >= 3)
        : rangeFiltered;

    if (!shouldDedupe) {
        return thresholdFiltered;
    }

    const dedupedEvents = [];
    let lastKeptMs = NaN;
    thresholdFiltered.forEach((event) => {
        const eventMs = parseEventTimestamp(event);
        if (!Number.isFinite(lastKeptMs) || Math.abs(lastKeptMs - eventMs) > 30000) {
            dedupedEvents.push(event);
            lastKeptMs = eventMs;
        }
    });
    return dedupedEvents;
}

function updateEventBrowser(browser, events) {
    const container = browser.querySelector("[data-events-list]");
    if (!container) {
        return;
    }

    const belowActualThresholdEnabled = browser.querySelector("[data-filter-below-actual-threshold]")?.checked;
    if (belowActualThresholdEnabled && !belowActualMetrics) {
        renderEventsList(container, events, container.dataset.activeEventId || "");
        const loadingSummary = browser.querySelector("[data-events-summary]");
        if (loadingSummary) {
            loadingSummary.textContent = `Loading 10-second under-actual metrics for ${events.length} saved events...`;
        }
        return;
    }

    const filteredEvents = applyEventFilters(events, browser);
    renderEventsList(container, filteredEvents, container.dataset.activeEventId || "");

    const summary = browser.querySelector("[data-events-summary]");
    if (summary) {
        const dedupeEnabled = browser.querySelector("[data-filter-dedupe]")?.checked;
        const belowActualThresholdSuffix = belowActualThresholdEnabled ? ", 3s-in-10s filter on" : "";
        const dedupeSuffix = dedupeEnabled ? ", 30s dedupe on" : "";
        summary.textContent = `Showing ${filteredEvents.length} of ${events.length} saved events${belowActualThresholdSuffix}${dedupeSuffix}.`;
    }
}

function initializeEventBrowsers() {
    const browsers = [...document.querySelectorAll("[data-events-browser]")];
    if (!browsers.length) {
        return [];
    }

    browsers.forEach((browser) => {
        browser.querySelectorAll("[data-filter-from], [data-filter-to], [data-filter-dedupe], [data-filter-below-actual-threshold]").forEach((control) => {
            control.addEventListener("input", () => {
                updateEventBrowser(browser, browser._events || []);
            });
            control.addEventListener("change", async () => {
                if (control.matches("[data-filter-below-actual-threshold]") && control.checked) {
                    try {
                        await ensureBelowActualMetrics(hasMissingBelowActualMetrics(browser._events || []));
                        applyBelowActualMetrics(browser._events || []);
                    } catch (error) {
                        console.error("Failed to load under-actual event metrics", error);
                    }
                }
                updateEventBrowser(browser, browser._events || []);
            });
        });

        const resetButton = browser.querySelector("[data-filter-reset]");
        if (resetButton) {
            resetButton.addEventListener("click", () => {
                const fromInput = browser.querySelector("[data-filter-from]");
                const toInput = browser.querySelector("[data-filter-to]");
                const dedupeInput = browser.querySelector("[data-filter-dedupe]");
                const belowActualThresholdInput = browser.querySelector("[data-filter-below-actual-threshold]");
                if (fromInput) {
                    fromInput.value = "";
                }
                if (toInput) {
                    toInput.value = "";
                }
                if (dedupeInput) {
                    dedupeInput.checked = true;
                }
                if (belowActualThresholdInput) {
                    belowActualThresholdInput.checked = false;
                }
                updateEventBrowser(browser, browser._events || []);
            });
        }
    });

    return browsers;
}

const eventBrowsers = initializeEventBrowsers();

async function refreshEventLists() {
    if (!eventBrowsers.length) {
        return;
    }

    try {
        const response = await fetch("/api/events", { cache: "no-store" });
        const payload = await response.json();
        const events = payload.events || [];
        if (belowActualMetrics) {
            applyBelowActualMetrics(events);
        }

        eventBrowsers.forEach((browser) => {
            browser._events = events;
            updateEventBrowser(browser, events);
        });

        if (isBelowActualThresholdFilterEnabled() && hasMissingBelowActualMetrics(events)) {
            try {
                await ensureBelowActualMetrics(true);
                applyBelowActualMetrics(events);
                refreshAllEventBrowsers();
            } catch (error) {
                console.error("Failed to refresh under-actual event metrics", error);
            }
        }
    } catch (error) {
        console.error("Failed to refresh saved events list", error);
    }
}

function applyInitialEvents() {
    const initialEvents = readJsonScript("initial-events-data");
    if (!initialEvents || !eventBrowsers.length) {
        return;
    }

    eventBrowsers.forEach((browser) => {
        browser._events = initialEvents.events || [];
        if (belowActualMetrics) {
            applyBelowActualMetrics(browser._events);
        }
        updateEventBrowser(browser, browser._events);
    });
}

function initializeDashboard() {
    const initialLive = readJsonScript("initial-live-data");
    if (initialLive) {
        updateLiveMetrics(initialLive);
        renderLiveChart(initialLive);
    }

    applyInitialEvents();
    refreshEventLists();
    window.setInterval(refreshEventLists, 10000);

    const source = new EventSource("/api/live/stream");
    source.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        updateLiveMetrics(payload);
        renderLiveChart(payload);
    };
    source.onerror = () => {
        setConnectionStatus("reconnecting", "waiting for stream");
    };
}

function initializeEventsPage() {
    applyInitialEvents();
    refreshEventLists();
    window.setInterval(refreshEventLists, 10000);
}

function initializeEventDetail() {
    const initialEvent = readJsonScript("initial-event-data");
    if (initialEvent) {
        renderEventChart(initialEvent);
    }

    applyInitialEvents();
    refreshEventLists();
    window.setInterval(refreshEventLists, 10000);
}

if (pageName === "dashboard") {
    initializeDashboard();
} else if (pageName === "events") {
    initializeEventsPage();
} else if (pageName === "event-detail") {
    initializeEventDetail();
}
