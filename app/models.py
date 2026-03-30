from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    event_time_utc: Mapped[str] = mapped_column(String(48), index=True)
    event_ts: Mapped[float] = mapped_column(Float, index=True)
    end_ts: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="capturing", index=True)
    snapshot_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at_utc: Mapped[str] = mapped_column(String(48))
    updated_at_utc: Mapped[str] = mapped_column(String(48))

    snapshots: Mapped[list["EventSnapshot"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventSnapshot.snapshot_ts",
    )


class EventSnapshot(Base):
    __tablename__ = "event_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    snapshot_time_utc: Mapped[str] = mapped_column(String(48), index=True)
    snapshot_ts: Mapped[float] = mapped_column(Float, index=True)
    seconds_from_event: Mapped[float] = mapped_column(Float)
    window_side: Mapped[str] = mapped_column(String(16))
    optimal_below_actual: Mapped[bool] = mapped_column(Boolean)
    actual_price: Mapped[float] = mapped_column(Float)
    mid_price: Mapped[float] = mapped_column(Float)
    best_bid: Mapped[float] = mapped_column(Float)
    best_ask: Mapped[float] = mapped_column(Float)
    spread: Mapped[float] = mapped_column(Float)
    optimal_price: Mapped[float] = mapped_column(Float)
    microprice_3: Mapped[float] = mapped_column(Float)
    imbalance_3: Mapped[float] = mapped_column(Float)
    ob_vol_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid_1_price: Mapped[float] = mapped_column(Float)
    bid_1_qty: Mapped[float] = mapped_column(Float)
    ask_1_price: Mapped[float] = mapped_column(Float)
    ask_1_qty: Mapped[float] = mapped_column(Float)
    bid_2_price: Mapped[float] = mapped_column(Float)
    bid_2_qty: Mapped[float] = mapped_column(Float)
    ask_2_price: Mapped[float] = mapped_column(Float)
    ask_2_qty: Mapped[float] = mapped_column(Float)
    bid_3_price: Mapped[float] = mapped_column(Float)
    bid_3_qty: Mapped[float] = mapped_column(Float)
    ask_3_price: Mapped[float] = mapped_column(Float)
    ask_3_qty: Mapped[float] = mapped_column(Float)

    event: Mapped[Event] = relationship(back_populates="snapshots")
