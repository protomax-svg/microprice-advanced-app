from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.binance_stream import BinanceSpotStreamService
from app.config import settings
from app.database import initialize_database
from app.events import EventStore
from app.live_state import LiveState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()

    event_store = EventStore()
    event_store.mark_incomplete_events_interrupted()

    live_state = LiveState(settings, saved_event_count=event_store.count_saved_events())
    stream_service = BinanceSpotStreamService(settings, live_state, event_store)

    app.state.event_store = event_store
    app.state.live_state = live_state
    app.state.stream_service = stream_service

    stream_service.start()
    try:
        yield
    finally:
        stream_service.stop()


app = FastAPI(
    title="Binance Spot Indicator Monitor",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.include_router(router)
