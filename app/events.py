from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import func, select

from .config import settings
from .database import session_scope
from .indicators import safe_float
from .models import Event, EventSnapshot

CSV_FIELDNAMES = [
    "event_id",
    "symbol",
    "event_time_utc",
    "snapshot_time_utc",
    "seconds_from_event",
    "window_side",
    "optimal_below_actual",
    "actual_price",
    "mid_price",
    "best_bid",
    "best_ask",
    "spread",
    "optimal_price",
    "microprice_3",
    "imbalance_3",
    "ob_vol_index",
    "bid_1_price",
    "bid_1_qty",
    "ask_1_price",
    "ask_1_qty",
    "bid_2_price",
    "bid_2_qty",
    "ask_2_price",
    "ask_2_qty",
    "bid_3_price",
    "bid_3_qty",
    "ask_3_price",
    "ask_3_qty",
]


def format_utc_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds")


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


def sanitize_number(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_snapshot(
    ts: float,
    actual_price: float,
    mid_price: float,
    optimal_price: float,
    microprice: float,
    imbalance: float,
    ob_vol: float | None,
    bids: list[list[str]],
    asks: list[list[str]],
) -> dict[str, float | bool]:
    best_bid = safe_float(bids[0][0])
    best_ask = safe_float(asks[0][0])
    return {
        "ts": ts,
        "actual_price": actual_price,
        "mid_price": mid_price,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": best_ask - best_bid,
        "optimal_price": optimal_price,
        "microprice_3": microprice,
        "imbalance_3": imbalance,
        "ob_vol_index": ob_vol,
        "optimal_below_actual": optimal_price < actual_price,
        "bid_1_price": safe_float(bids[0][0]),
        "bid_1_qty": safe_float(bids[0][1]),
        "ask_1_price": safe_float(asks[0][0]),
        "ask_1_qty": safe_float(asks[0][1]),
        "bid_2_price": safe_float(bids[1][0]),
        "bid_2_qty": safe_float(bids[1][1]),
        "ask_2_price": safe_float(asks[1][0]),
        "ask_2_qty": safe_float(asks[1][1]),
        "bid_3_price": safe_float(bids[2][0]),
        "bid_3_qty": safe_float(bids[2][1]),
        "ask_3_price": safe_float(asks[2][0]),
        "ask_3_qty": safe_float(asks[2][1]),
    }


def classify_window_side(snapshot_ts: float, event_ts: float) -> str:
    if abs(snapshot_ts - event_ts) < 1e-9:
        return "event"
    if snapshot_ts < event_ts:
        return "pre"
    return "post"


class EchoBuffer:
    def write(self, value: str) -> str:
        return value


class EventStore:
    def mark_incomplete_events_interrupted(self) -> None:
        with session_scope() as session:
            incomplete_events = session.scalars(
                select(Event).where(Event.status == "capturing")
            ).all()
            if not incomplete_events:
                return

            now = utc_now_iso()
            for event in incomplete_events:
                event.status = "interrupted"
                event.updated_at_utc = now

    def count_saved_events(self) -> int:
        with session_scope() as session:
            count = session.scalar(
                select(func.count()).select_from(Event).where(Event.status == "saved")
            )
            return int(count or 0)

    def create_pending_event(self, symbol: str, event_ts: float, end_ts: float) -> int:
        with session_scope() as session:
            now = utc_now_iso()
            event = Event(
                symbol=symbol,
                event_time_utc=format_utc_timestamp(event_ts),
                event_ts=event_ts,
                end_ts=end_ts,
                status="capturing",
                snapshot_count=0,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(event)
            session.flush()
            return int(event.id)

    def finalize_event_window(self, event_window: dict[str, object]) -> int:
        with session_scope() as session:
            event = session.get(Event, int(event_window["event_id"]))
            if event is None:
                raise ValueError(f"Event #{event_window['event_id']} does not exist")

            if event.status == "saved":
                return event.snapshot_count

            unique_rows = self._deduplicate_event_rows(event_window["rows"])
            snapshots = [
                self._snapshot_dict_to_model(event_id=event.id, event_ts=event.event_ts, snapshot=row)
                for row in unique_rows
            ]
            session.add_all(snapshots)
            event.snapshot_count = len(snapshots)
            event.status = "saved"
            event.updated_at_utc = utc_now_iso()
            return len(snapshots)

    def list_saved_events(self, limit: int = 250) -> list[dict[str, object]]:
        with session_scope() as session:
            events = session.scalars(
                select(Event)
                .where(Event.status == "saved")
                .order_by(Event.event_ts.desc())
                .limit(limit)
            ).all()
            return [self._serialize_event_summary(event) for event in events]

    def get_event_payload(self, event_id: int) -> dict[str, object] | None:
        with session_scope() as session:
            event = session.get(Event, event_id)
            if event is None or event.status != "saved":
                return None

            snapshots = session.scalars(
                select(EventSnapshot)
                .where(EventSnapshot.event_id == event_id)
                .order_by(EventSnapshot.snapshot_ts.asc())
            ).all()
            return {
                "event": self._serialize_event_summary(event),
                "snapshots": {
                    "snapshot_time_utc": [row.snapshot_time_utc for row in snapshots],
                    "seconds_from_event": [row.seconds_from_event for row in snapshots],
                    "window_side": [row.window_side for row in snapshots],
                    "actual_price": [sanitize_number(row.actual_price) for row in snapshots],
                    "optimal_price": [sanitize_number(row.optimal_price) for row in snapshots],
                    "microprice_3": [sanitize_number(row.microprice_3) for row in snapshots],
                    "imbalance_3": [sanitize_number(row.imbalance_3) for row in snapshots],
                    "ob_vol_index": [sanitize_number(row.ob_vol_index) for row in snapshots],
                },
            }

    def export_event_csv(self, event_id: int) -> tuple[str, Iterator[str]]:
        filename = f"{settings.symbol.lower()}_spot_cross_under_event_{event_id}.csv"
        return filename, self._generate_event_csv(event_id)

    def export_all_events_csv(self) -> tuple[str, Iterator[str]]:
        return settings.csv_export_filename, self._generate_all_events_csv()

    def _snapshot_dict_to_model(
        self,
        event_id: int,
        event_ts: float,
        snapshot: dict[str, object],
    ) -> EventSnapshot:
        snapshot_ts = float(snapshot["ts"])
        return EventSnapshot(
            event_id=event_id,
            snapshot_time_utc=format_utc_timestamp(snapshot_ts),
            snapshot_ts=snapshot_ts,
            seconds_from_event=round(snapshot_ts - event_ts, 3),
            window_side=classify_window_side(snapshot_ts, event_ts),
            optimal_below_actual=bool(snapshot["optimal_below_actual"]),
            actual_price=float(snapshot["actual_price"]),
            mid_price=float(snapshot["mid_price"]),
            best_bid=float(snapshot["best_bid"]),
            best_ask=float(snapshot["best_ask"]),
            spread=float(snapshot["spread"]),
            optimal_price=float(snapshot["optimal_price"]),
            microprice_3=float(snapshot["microprice_3"]),
            imbalance_3=float(snapshot["imbalance_3"]),
            ob_vol_index=(
                None
                if snapshot["ob_vol_index"] is None
                else float(snapshot["ob_vol_index"])
            ),
            bid_1_price=float(snapshot["bid_1_price"]),
            bid_1_qty=float(snapshot["bid_1_qty"]),
            ask_1_price=float(snapshot["ask_1_price"]),
            ask_1_qty=float(snapshot["ask_1_qty"]),
            bid_2_price=float(snapshot["bid_2_price"]),
            bid_2_qty=float(snapshot["bid_2_qty"]),
            ask_2_price=float(snapshot["ask_2_price"]),
            ask_2_qty=float(snapshot["ask_2_qty"]),
            bid_3_price=float(snapshot["bid_3_price"]),
            bid_3_qty=float(snapshot["bid_3_qty"]),
            ask_3_price=float(snapshot["ask_3_price"]),
            ask_3_qty=float(snapshot["ask_3_qty"]),
        )

    def _deduplicate_event_rows(
        self,
        rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        unique_rows: dict[float, dict[str, object]] = {}
        for row in rows:
            unique_rows[float(row["ts"])] = dict(row)

        return [
            unique_rows[snapshot_ts]
            for snapshot_ts in sorted(unique_rows)
        ]

    def _serialize_event_summary(self, event: Event) -> dict[str, object]:
        return {
            "id": event.id,
            "symbol": event.symbol,
            "event_time_utc": event.event_time_utc,
            "snapshot_count": event.snapshot_count,
            "status": event.status,
        }

    def _snapshot_model_to_csv_row(self, event: Event, snapshot: EventSnapshot) -> dict[str, object]:
        return {
            "event_id": event.id,
            "symbol": event.symbol,
            "event_time_utc": event.event_time_utc,
            "snapshot_time_utc": snapshot.snapshot_time_utc,
            "seconds_from_event": round(snapshot.seconds_from_event, 3),
            "window_side": snapshot.window_side,
            "optimal_below_actual": snapshot.optimal_below_actual,
            "actual_price": snapshot.actual_price,
            "mid_price": snapshot.mid_price,
            "best_bid": snapshot.best_bid,
            "best_ask": snapshot.best_ask,
            "spread": snapshot.spread,
            "optimal_price": snapshot.optimal_price,
            "microprice_3": snapshot.microprice_3,
            "imbalance_3": snapshot.imbalance_3,
            "ob_vol_index": snapshot.ob_vol_index,
            "bid_1_price": snapshot.bid_1_price,
            "bid_1_qty": snapshot.bid_1_qty,
            "ask_1_price": snapshot.ask_1_price,
            "ask_1_qty": snapshot.ask_1_qty,
            "bid_2_price": snapshot.bid_2_price,
            "bid_2_qty": snapshot.bid_2_qty,
            "ask_2_price": snapshot.ask_2_price,
            "ask_2_qty": snapshot.ask_2_qty,
            "bid_3_price": snapshot.bid_3_price,
            "bid_3_qty": snapshot.bid_3_qty,
            "ask_3_price": snapshot.ask_3_price,
            "ask_3_qty": snapshot.ask_3_qty,
        }

    def _generate_event_csv(self, event_id: int) -> Iterator[str]:
        buffer = EchoBuffer()
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES)
        yield writer.writeheader()

        with session_scope() as session:
            event = session.get(Event, event_id)
            if event is None or event.status != "saved":
                return

            snapshots = session.scalars(
                select(EventSnapshot)
                .where(EventSnapshot.event_id == event_id)
                .order_by(EventSnapshot.snapshot_ts.asc())
            ).all()
            for snapshot in snapshots:
                yield writer.writerow(self._snapshot_model_to_csv_row(event, snapshot))

    def _generate_all_events_csv(self) -> Iterator[str]:
        buffer = EchoBuffer()
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES)
        yield writer.writeheader()

        with session_scope() as session:
            rows = session.execute(
                select(Event, EventSnapshot)
                .join(EventSnapshot, EventSnapshot.event_id == Event.id)
                .where(Event.status == "saved")
                .order_by(Event.event_ts.asc(), EventSnapshot.snapshot_ts.asc())
            ).all()
            for event, snapshot in rows:
                yield writer.writerow(self._snapshot_model_to_csv_row(event, snapshot))
