from __future__ import annotations

import json
import logging
import threading
import time

import websocket

from .config import Settings
from .events import EventStore, build_snapshot, format_utc_timestamp
from .indicators import (
    compute_imbalance_3levels,
    compute_microprice_3levels,
    compute_ob_volatility_index_3levels,
    compute_optimal_price,
    safe_float,
)
from .live_state import LiveState

logger = logging.getLogger(__name__)


class BinanceSpotStreamService:
    def __init__(self, app_settings: Settings, live_state: LiveState, event_store: EventStore) -> None:
        self.settings = app_settings
        self.live_state = live_state
        self.event_store = event_store
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.ws_app: websocket.WebSocketApp | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self.run_forever,
            name="binance-spot-stream",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.ws_app is not None:
            try:
                self.ws_app.close()
            except Exception:
                logger.exception("Failed to close Binance WebSocket cleanly")
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

    def run_forever(self) -> None:
        self.live_state.set_connection_status("connecting")
        while not self.stop_event.is_set():
            try:
                self.ws_app = websocket.WebSocketApp(
                    self.settings.ws_url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )
                self.ws_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                logger.exception("Binance Spot stream loop failed")
                self.live_state.set_connection_status("error", "Binance stream loop failed")

            if not self.stop_event.is_set():
                self.live_state.set_connection_status("reconnecting")
                time.sleep(3)

    def on_open(self, ws: websocket.WebSocketApp) -> None:
        logger.info("Connected to Binance Spot stream for %s", self.settings.symbol)
        self.live_state.set_connection_status("connected")

    def on_error(self, ws: websocket.WebSocketApp, error: object) -> None:
        logger.error("WebSocket error: %s", error)
        self.live_state.set_connection_status("error", str(error))

    def on_close(
        self,
        ws: websocket.WebSocketApp,
        close_status_code: int | None,
        close_msg: str | None,
    ) -> None:
        logger.warning("WebSocket closed: %s %s", close_status_code, close_msg)
        if self.stop_event.is_set():
            self.live_state.set_connection_status("stopped")
        else:
            self.live_state.set_connection_status(
                "disconnected",
                f"{close_status_code or 'n/a'} {close_msg or ''}".strip(),
            )

    def on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        try:
            msg = json.loads(message)
            stream = msg.get("stream")
            data = msg.get("data", {})

            if stream is None:
                return

            if stream.endswith("@aggTrade") or data.get("e") == "aggTrade":
                with self.live_state.lock:
                    self.live_state.last_trade_price = safe_float(data["p"])
                return

            if "@depth5@100ms" not in stream and data.get("lastUpdateId") is None:
                return

            bids = data.get("bids") or data.get("b") or []
            asks = data.get("asks") or data.get("a") or []
            if len(bids) < 3 or len(asks) < 3:
                return

            best_bid = safe_float(bids[0][0])
            best_ask = safe_float(asks[0][0])
            mid_price = (best_bid + best_ask) / 2.0

            with self.live_state.lock:
                prev_net_depth = self.live_state.prev_net_depth
                last_trade_price = self.live_state.last_trade_price

            microprice = compute_microprice_3levels(bids, asks)
            imbalance = compute_imbalance_3levels(bids, asks)
            ob_vol, next_prev_net_depth = compute_ob_volatility_index_3levels(
                bids,
                asks,
                prev_net_depth,
            )
            optimal_price = compute_optimal_price(microprice, imbalance)
            actual_price = last_trade_price if last_trade_price is not None else mid_price
            ts = time.time()

            if actual_price is None or optimal_price is None:
                return

            snapshot = build_snapshot(
                ts=ts,
                actual_price=actual_price,
                mid_price=mid_price,
                optimal_price=optimal_price,
                microprice=microprice,
                imbalance=imbalance,
                ob_vol=ob_vol,
                bids=bids,
                asks=asks,
            )

            event_rows: list[dict[str, object]] | None = None
            finished_windows: list[dict[str, object]] = []
            should_create_event = False

            with self.live_state.lock:
                self.live_state.last_mid_price = mid_price
                self.live_state.prev_net_depth = next_prev_net_depth
                self.live_state.append_snapshot(snapshot)

                current_below = bool(snapshot["optimal_below_actual"])
                if self.live_state.last_optimal_below_actual is None:
                    self.live_state.last_optimal_below_actual = current_below
                elif (not self.live_state.last_optimal_below_actual) and current_below:
                    should_create_event = True
                    event_rows = self.live_state.build_event_rows(snapshot)
                    self.live_state.last_optimal_below_actual = current_below
                else:
                    self.live_state.last_optimal_below_actual = current_below

                finished_windows = list(self.live_state.advance_active_event_windows(snapshot))

            if should_create_event and event_rows is not None:
                event_id = self.event_store.create_pending_event(
                    symbol=self.settings.symbol,
                    event_ts=ts,
                    end_ts=ts + self.settings.event_window_seconds,
                )
                event_window = {
                    "event_id": event_id,
                    "event_ts": ts,
                    "end_ts": ts + self.settings.event_window_seconds,
                    "rows": event_rows,
                    "last_snapshot_ts": event_rows[-1]["ts"] if event_rows else None,
                }
                logger.info(
                    "Detected cross-under event #%s at %s",
                    event_id,
                    format_utc_timestamp(ts),
                )
                self.live_state.register_event_window(event_window)

            for event_window in finished_windows:
                try:
                    snapshot_count = self.event_store.finalize_event_window(event_window)
                except Exception:
                    logger.exception("Failed to persist event #%s", event_window["event_id"])
                    continue

                self.live_state.mark_event_saved(event_window)
                logger.info(
                    "Saved event #%s with %s snapshots to SQLite",
                    event_window["event_id"],
                    snapshot_count,
                )

        except Exception:
            logger.exception("Unhandled on_message error")
