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

async function refreshEventLists() {
    const containers = [...document.querySelectorAll("[data-events-list]")];
    if (!containers.length) {
        return;
    }

    try {
        const response = await fetch("/api/events?limit=250", { cache: "no-store" });
        const payload = await response.json();
        const events = payload.events || [];

        containers.forEach((container) => {
            renderEventsList(container, events, container.dataset.activeEventId || "");
        });
    } catch (error) {
        console.error("Failed to refresh saved events list", error);
    }
}

function applyInitialEvents() {
    const initialEvents = readJsonScript("initial-events-data");
    const containers = [...document.querySelectorAll("[data-events-list]")];
    if (!initialEvents || !containers.length) {
        return;
    }

    containers.forEach((container) => {
        renderEventsList(container, initialEvents.events || [], container.dataset.activeEventId || "");
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
