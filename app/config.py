from __future__ import annotations

import os
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.templates_dir = self.base_dir / "app" / "templates"
        self.static_dir = self.base_dir / "app" / "static"

        self.symbol = os.getenv("BINANCE_SYMBOL", "NOMUSDT").upper()
        self.max_points = int(os.getenv("MAX_POINTS", "600"))
        self.price_display_decimals = int(os.getenv("PRICE_DISPLAY_DECIMALS", "8"))
        self.snapshot_interval_seconds = float(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "0.1"))
        self.event_window_seconds = int(os.getenv("EVENT_WINDOW_SECONDS", str(3 * 60)))
        self.market_data_only_endpoint = (
            os.getenv("BINANCE_MARKET_DATA_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}
        )

        sqlite_path_value = os.getenv("SQLITE_PATH", str(self.base_dir / "data" / "events.sqlite3"))
        self.sqlite_path = Path(sqlite_path_value).expanduser()
        if not self.sqlite_path.is_absolute():
            self.sqlite_path = self.base_dir / self.sqlite_path

        export_dir_value = os.getenv("EXPORT_DIR", str(self.base_dir / "exports"))
        self.export_dir = Path(export_dir_value).expanduser()
        if not self.export_dir.is_absolute():
            self.export_dir = self.base_dir / self.export_dir

    @property
    def pre_event_buffer_snapshots(self) -> int:
        return int(self.event_window_seconds / self.snapshot_interval_seconds) + 20

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path.as_posix()}"

    @property
    def csv_export_filename(self) -> str:
        return f"{self.symbol.lower()}_spot_cross_under_events.csv"

    @property
    def ws_url(self) -> str:
        host = "data-stream.binance.vision:9443" if self.market_data_only_endpoint else "stream.binance.com:9443"
        symbol_stream = self.symbol.lower()
        return (
            f"wss://{host}/stream"
            f"?streams={symbol_stream}@depth5@100ms/{symbol_stream}@aggTrade"
        )

    def ensure_directories(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
