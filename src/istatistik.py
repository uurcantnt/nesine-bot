"""Takim istatistiklerini ESPN'den topla ve onbellege yaz.

NEREDE CALISIR: ESPN Turkiye'den engelli; YALNIZCA GitHub Actions'ta calisir.
Toplanan veri `data/istatistik.json` dosyasina yazilir ve repoya commit'lenir;
boylece /kupon calisirken yeniden cekmeye gerek kalmaz.

NEDEN CLI DEGIL: her cagri icin ayri Python sureci baslatmak cok yavas
(60 mac 20+ dakika surdu). Python API dogrudan cagriliyor.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ONBELLEK = Path(__file__).resolve().parent.parent / "data" / "istatistik.json"
SON_MAC = 10          # takim basina kac gecmis mac
TAZE_SAAT = 20        # onbellek bu kadar saat sonra bayat sayilir


def _api():
    from sports_skills import football
    return football


def _skorlar(ev: dict, takim_id: str) -> tuple | None:
    """(attigi, yedigi, ev_sahibi_mi) veya None."""
    rak = ev.get("competitors") or []
    if len(rak) != 2 or ev.get("status") != "closed":
        return None
    bizim = next((c for c in rak if str(c.get("team", {}).get("id")) == str(takim_id)), None)
    rakip = next((c for c in rak if c is not bizim), None)
    if not bizim or not rakip:
        return None
    a, y = bizim.get("score"), rakip.get("score")
    if a is None or y is None:
        return None
    return int(a), int(y), bizim.get("qualifier") == "home"


def _program(fb, takim_id: str, lig: str | None, yil: int | None) -> list:
    kw = {"team_id": str(takim_id)}
    if lig:
        kw["league_slug"] = lig
    if yil:
        kw["season_year"] = str(yil)
    try:
        d = fb.get_team_schedule(**kw)
    except Exception as e:
        print(f"[ist] {takim_id} ({lig},{yil}) hata: {e}")
        return []
    return ((d or {}).get("data") or {}).get("events") or []


def takim_verisi(takim_id: str, lig: str | None = None,
                 yillar: tuple = (None, 2025)) -> dict | None:
    """Bir takimin son maclarindan gol/korner/kart oranlari.

    league_slug SART: onsuz Turk takimlari disinda cogu takim bos donuyor
    (olculdu: 14 takimin 8'i). yillar: gecerli sezon + onceki -- Agustos'ta
    sezon yeni basladigi icin tek sezon 1 mac veriyor, model kurulamaz.
    """
    fb = _api()
    olaylar, gorulen = [], set()
    for yil in yillar:
        for e in _program(fb, takim_id, lig, yil):
            if e.get("id") and e["id"] not in gorulen:
                gorulen.add(e["id"])
                olaylar.append(e)
        if len([e for e in olaylar if e.get("status") == "closed"]) >= SON_MAC:
            break
    bitmis = [e for e in olaylar if e.get("status") == "closed"]
    bitmis.sort(key=lambda e: e.get("start_time") or "", reverse=True)
    bitmis = bitmis[:SON_MAC]
    if not bitmis:
        return None

    gol_at = gol_ye = 0
    korner_l: list = []
    sari_l: list = []
    kirmizi_l: list = []
    maclar: list = []      # HAM mac listesi -> ampirik isabet orani icin
    mac = 0
    for e in bitmis:
        s = _skorlar(e, takim_id)
        if not s:
            continue
        mac += 1
        gol_at += s[0]
        gol_ye += s[1]
        kayit = {"at": s[0], "ye": s[1], "ev": s[2],
                 "t": (e.get("start_time") or "")[:10]}
        try:
            st = fb.get_event_statistics(event_id=str(e["id"]))
        except Exception:
            continue
        for t in ((st or {}).get("data") or {}).get("teams", []):
            if str(t.get("team", {}).get("id")) != str(takim_id):
                continue
            d = t.get("statistics") or {}
            try:
                kayit["korner"] = float(d.get("corner_kicks") or 0)
                korner_l.append(kayit["korner"])
            except (TypeError, ValueError):
                pass
            try:
                # Sari ve kirmizi AYRI saklanir; puanlama modelde yapilir.
                # OLCULDU: Nesine'nin "Kart Puani" baraji 2,5-6,5 arasi,
                # yani KART SAYISI olcegi (sari=10 olsaydi baraj 35,5 olurdu).
                kayit["sari"] = float(d.get("yellow_cards") or 0)
                kayit["kirmizi"] = float(d.get("red_cards") or 0)
                sari_l.append(kayit["sari"])
                kirmizi_l.append(kayit["kirmizi"])
            except (TypeError, ValueError):
                pass
        maclar.append(kayit)
    if mac == 0:
        return None
    return {
        "maclar": maclar,
        "mac": mac,
        "lig": lig,
        "gol_at": gol_at / mac,
        "gol_ye": gol_ye / mac,
        "korner": (sum(korner_l) / len(korner_l)) if korner_l else None,
        "korner_n": len(korner_l),
        "sari": (sum(sari_l) / len(sari_l)) if sari_l else None,
        "kirmizi": (sum(kirmizi_l) / len(kirmizi_l)) if kirmizi_l else None,
        "kart_n": len(sari_l),
        "guncelleme": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def yukle() -> dict:
    if ONBELLEK.exists():
        try:
            return json.loads(ONBELLEK.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def kaydet(d: dict) -> None:
    ONBELLEK.parent.mkdir(parents=True, exist_ok=True)
    ONBELLEK.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def taze(kayit: dict) -> bool:
    try:
        t = datetime.fromisoformat(kayit["guncelleme"])
    except Exception:
        return False
    return (datetime.now(timezone.utc) - t).total_seconds() < TAZE_SAAT * 3600
