# Binance Spot Indicator Monitor

Local FastAPI web app that keeps the original `test1_spot.py` behavior as the source of truth for:

- Binance Spot WebSocket ingestion
- indicator formulas
- cross-under event detection
- pre/post event window capture
- CSV-compatible snapshot fields

The app replaces CSV as the primary storage layer with SQLite, while still exposing CSV export from the UI.

## Project structure

```text
.
|-- app/
|   |-- api.py
|   |-- binance_stream.py
|   |-- config.py
|   |-- database.py
|   |-- events.py
|   |-- indicators.py
|   |-- live_state.py
|   |-- models.py
|   |-- static/
|   |   |-- app.js
|   |   `-- styles.css
|   `-- templates/
|       |-- base.html
|       |-- dashboard.html
|       |-- event_detail.html
|       `-- events.html
|-- data/
|-- exports/
|-- main.py
|-- requirements.txt
`-- test1_spot.py
```

## What it does

- streams Binance Spot `depth5@100ms` and `aggTrade`
- computes actual price, optimal price, microprice, imbalance, and OB volatility index
- detects the same cross-under event as the baseline script
- keeps the same time-window behavior around each event
- stores events and snapshots in SQLite
- shows a live dashboard in the browser
- lets you browse saved events by timestamp
- renders full saved-event charts
- exports one event or all events to CSV from the UI

## Install

Use a Python virtual environment on your Linux server:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Initialize and start the app with:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Development reload mode is also fine:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Database initialization

No separate migration step is required for the initial setup. On startup the app:

1. creates the SQLite file if it does not exist
2. creates the `events` and `event_snapshots` tables
3. starts the Binance Spot background stream worker

Default SQLite path:

```text
data/events.sqlite3
```

## Configuration

You can override these with environment variables before starting the server:

- `BINANCE_SYMBOL`
- `MAX_POINTS`
- `PRICE_DISPLAY_DECIMALS`
- `SNAPSHOT_INTERVAL_SECONDS`
- `EVENT_WINDOW_SECONDS`
- `SQLITE_PATH`
- `EXPORT_DIR`
- `BINANCE_MARKET_DATA_ONLY`

Defaults are chosen to match the baseline script, including the default symbol `NOMUSDT`.

## Notes on baseline parity

- The app stays Spot-only.
- The app keeps the same `depth5@100ms` + `aggTrade` stream pairing.
- Actual price still prefers the last trade price and falls back to mid-price.
- Imbalance keeps the baseline `/ 100` scaling.
- OB volatility index keeps the same log-ratio behavior, including undefined early values.
- Cross-under events are still triggered when optimal price moves from not-below to below actual price.
- Each event still captures the buffered pre-event snapshots and continues collecting for the configured post-event window.

## CSV export

- `Export Event CSV` downloads one selected event
- `Export All CSV` downloads all saved events

The exported columns follow the original CSV field structure as closely as possible.
