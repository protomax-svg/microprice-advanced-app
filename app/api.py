from __future__ import annotations

import asyncio
import json
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from plotly.offline.offline import get_plotlyjs

from .config import settings

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.templates_dir))


def get_event_store(request: Request):
    return request.app.state.event_store


def get_live_state(request: Request):
    return request.app.state.live_state


@lru_cache(maxsize=1)
def get_plotly_bundle() -> str:
    return get_plotlyjs()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    event_store = get_event_store(request)
    live_state = get_live_state(request)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "page_name": "dashboard",
            "symbol": settings.symbol,
            "live_json": json.dumps(live_state.build_payload()),
            "events_json": json.dumps({"events": event_store.list_saved_events(limit=40)}),
        },
    )


@router.get("/events", response_class=HTMLResponse)
async def saved_events_page(request: Request) -> HTMLResponse:
    event_store = get_event_store(request)
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "request": request,
            "page_name": "events",
            "symbol": settings.symbol,
            "events_json": json.dumps({"events": event_store.list_saved_events(limit=250)}),
        },
    )


@router.get("/events/{event_id}", response_class=HTMLResponse)
async def event_detail_page(request: Request, event_id: int) -> HTMLResponse:
    event_store = get_event_store(request)
    event_payload = event_store.get_event_payload(event_id)
    if event_payload is None:
        raise HTTPException(status_code=404, detail="Saved event not found")

    return templates.TemplateResponse(
        request,
        "event_detail.html",
        {
            "request": request,
            "page_name": "event-detail",
            "symbol": settings.symbol,
            "event": event_payload["event"],
            "event_json": json.dumps(event_payload),
            "events_json": json.dumps({"events": event_store.list_saved_events(limit=250)}),
        },
    )


@router.get("/api/live")
async def live_snapshot(request: Request) -> dict[str, object]:
    live_state = get_live_state(request)
    return live_state.build_payload()


@router.get("/api/live/stream")
async def live_stream(request: Request) -> StreamingResponse:
    live_state = get_live_state(request)

    async def event_generator():
        last_sequence = -1
        while True:
            if await request.is_disconnected():
                break

            payload = live_state.build_payload()
            if payload["sequence"] != last_sequence:
                yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                last_sequence = payload["sequence"]
            else:
                yield ": keepalive\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/events")
async def saved_events(request: Request, limit: int = 250) -> dict[str, object]:
    event_store = get_event_store(request)
    safe_limit = max(1, min(limit, 1000))
    return {"events": event_store.list_saved_events(limit=safe_limit)}


@router.get("/api/events/export.csv")
async def export_all_events_csv(request: Request) -> StreamingResponse:
    event_store = get_event_store(request)
    filename, generator = event_store.export_all_events_csv()
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/events/{event_id}")
async def saved_event_detail(request: Request, event_id: int) -> dict[str, object]:
    event_store = get_event_store(request)
    event_payload = event_store.get_event_payload(event_id)
    if event_payload is None:
        raise HTTPException(status_code=404, detail="Saved event not found")
    return event_payload


@router.get("/api/events/{event_id}/export.csv")
async def export_event_csv(request: Request, event_id: int) -> StreamingResponse:
    event_store = get_event_store(request)
    event_payload = event_store.get_event_payload(event_id)
    if event_payload is None:
        raise HTTPException(status_code=404, detail="Saved event not found")

    filename, generator = event_store.export_event_csv(event_id)
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/vendor/plotly.min.js", response_class=Response, name="plotly_bundle")
async def plotly_bundle() -> Response:
    return Response(get_plotly_bundle(), media_type="application/javascript")
