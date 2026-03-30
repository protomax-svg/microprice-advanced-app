from __future__ import annotations

import math
import threading
from collections import deque

from .config import Settings
from .events import format_utc_timestamp, sanitize_number


class LiveState:
    def __init__(self, app_settings: Settings, saved_event_count: int = 0) -> None:
        self.settings = app_settings
        self.lock = threading.Lock()

        self.times = deque(maxlen=app_settings.max_points)
        self.actual_prices = deque(maxlen=app_settings.max_points)
        self.optimal_prices = deque(maxlen=app_settings.max_points)
        self.microprices = deque(maxlen=app_settings.max_points)
        self.imbalances = deque(maxlen=app_settings.max_points)
        self.ob_vol_indexes = deque(maxlen=app_settings.max_points)

        self.last_trade_price: float | None = None
        self.last_mid_price: float | None = None
        self.prev_net_depth: float | None = None
        self.last_optimal_below_actual: bool | None = None

        self.saved_event_count = saved_event_count
        self.snapshot_history = deque(maxlen=app_settings.pre_event_buffer_snapshots)
        self.active_event_windows: list[dict[str, object]] = []
        self.sequence = 0
        self.connection_status = "starting"
        self.last_error: str | None = None

    def set_connection_status(self, status: str, error: str | None = None) -> None:
        with self.lock:
            self.connection_status = status
            self.last_error = error
            self.sequence += 1

    def append_snapshot(self, snapshot: dict[str, object]) -> None:
        self.times.append(float(snapshot["ts"]))
        self.actual_prices.append(float(snapshot["actual_price"]))
        self.optimal_prices.append(float(snapshot["optimal_price"]))
        self.microprices.append(float(snapshot["microprice_3"]))
        self.imbalances.append(float(snapshot["imbalance_3"]))
        ob_vol = snapshot["ob_vol_index"]
        self.ob_vol_indexes.append(float(ob_vol) if ob_vol is not None else math.nan)
        self.snapshot_history.append(dict(snapshot))
        self.sequence += 1

    def build_event_rows(self, snapshot: dict[str, object]) -> list[dict[str, object]]:
        window_start = float(snapshot["ts"]) - self.settings.event_window_seconds
        return [dict(row) for row in self.snapshot_history if float(row["ts"]) >= window_start]

    def advance_active_event_windows(self, snapshot: dict[str, object]) -> list[dict[str, object]]:
        finished_events: list[dict[str, object]] = []
        snapshot_ts = float(snapshot["ts"])

        for event_window in self.active_event_windows:
            if snapshot_ts <= float(event_window["end_ts"]):
                if event_window["last_snapshot_ts"] != snapshot_ts:
                    event_window["rows"].append(dict(snapshot))
                    event_window["last_snapshot_ts"] = snapshot_ts
            else:
                finished_events.append(event_window)

        return finished_events

    def register_event_window(self, event_window: dict[str, object]) -> None:
        with self.lock:
            self.active_event_windows.append(event_window)
            self.sequence += 1

    def mark_event_saved(self, event_window: dict[str, object]) -> None:
        with self.lock:
            if event_window in self.active_event_windows:
                self.active_event_windows.remove(event_window)
            self.saved_event_count += 1
            self.sequence += 1

    def build_payload(self) -> dict[str, object]:
        with self.lock:
            timestamps = [format_utc_timestamp(ts) for ts in self.times]
            actual_prices = [sanitize_number(value) for value in self.actual_prices]
            optimal_prices = [sanitize_number(value) for value in self.optimal_prices]
            microprices = [sanitize_number(value) for value in self.microprices]
            imbalances = [sanitize_number(value) for value in self.imbalances]
            ob_vol_indexes = [sanitize_number(value) for value in self.ob_vol_indexes]

            def last_or_none(values: deque[float]) -> float | None:
                return sanitize_number(values[-1]) if values else None

            updated_at = timestamps[-1] if timestamps else None
            return {
                "sequence": self.sequence,
                "symbol": self.settings.symbol,
                "price_display_decimals": self.settings.price_display_decimals,
                "connection_status": self.connection_status,
                "last_error": self.last_error,
                "saved_event_count": self.saved_event_count,
                "active_event_windows_count": len(self.active_event_windows),
                "updated_at": updated_at,
                "current": {
                    "actual_price": last_or_none(self.actual_prices),
                    "optimal_price": last_or_none(self.optimal_prices),
                    "microprice_3": last_or_none(self.microprices),
                    "imbalance_3": last_or_none(self.imbalances),
                    "ob_vol_index": last_or_none(self.ob_vol_indexes),
                },
                "series": {
                    "timestamps": timestamps,
                    "actual_price": actual_prices,
                    "optimal_price": optimal_prices,
                    "microprice_3": microprices,
                    "imbalance_3": imbalances,
                    "ob_vol_index": ob_vol_indexes,
                },
            }
