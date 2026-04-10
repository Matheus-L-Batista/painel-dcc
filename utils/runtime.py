from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from pytz import timezone


BRAZIL_TZ = timezone("America/Sao_Paulo")


def now_sp() -> datetime:
    return datetime.now(BRAZIL_TZ)


def format_datetime_sp(dt: datetime | None) -> str:
    if not dt:
        return "-"
    try:
        return dt.astimezone(BRAZIL_TZ).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return dt.strftime("%d/%m/%Y %H:%M:%S")


def get_default_year() -> int:
    raw_year = os.environ.get("PAINEL_DEFAULT_YEAR")
    if raw_year:
        try:
            return int(raw_year)
        except ValueError:
            pass
    return now_sp().year


def get_cache_root() -> Path:
    raw_dir = (
        os.environ.get("PAINEL_CACHE_DIR")
        or os.environ.get("PAINEL_DCF_CACHE_DIR")
    )
    if raw_dir:
        cache_root = Path(raw_dir)
    else:
        cache_root = Path(tempfile.gettempdir()) / "painel_dcc_cache"

    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def get_cache_dir(name: str) -> Path:
    cache_dir = get_cache_root() / name
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir
