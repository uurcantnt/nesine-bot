"""Turkiye saati. Mekanizma hash'ine DAHIL DEGIL (yalnizca goruntuleme).

NEDEN SABIT OFSET: Turkiye 2016'dan beri kalici UTC+3, yaz saati uygulamiyor.
zoneinfo kullanmak macOS'ta tzdata bagimliligi getirirdi; sabit ofset hem
dogru hem bagimsiz.

NEDEN GEREKLI: GitHub Actions runner'lari UTC'de kosuyor, `datetime.now()`
UTC donduruyor ve mesajlarda saat 3 saat geri gorunuyordu (16:47 vs 19:47).
`.astimezone()` de ise yaramaz -- runner'in yerel saati zaten UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

TR = timezone(timedelta(hours=3), "TRT")


def simdi() -> datetime:
    return datetime.now(TR)


def yerel(dt: datetime) -> datetime:
    """UTC (veya baska) bir zamani Turkiye saatine cevir."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TR)


def bicim(dt: datetime, f: str = "%d.%m %H:%M") -> str:
    return yerel(dt).strftime(f)
