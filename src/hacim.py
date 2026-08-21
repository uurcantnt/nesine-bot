"""HACIM KONTROLU — negatif EV'de kontrol edilebilen TEK degisken.

KONSUL (5/5 hemfikir): marj %21,1 iken HANGI bahsi sectigin kaybi en fazla
4 kat degistirir (en iyi secenek -%3,7, medyan -%15,2). Ama KAC bahis
oynadigin kaybi SINIRSIZ degistirir.

Pratisyen danismanin cumlesi aynen: "kaybi 4 kat azaltip 4 kat oynarsan
tam olarak basladigin yerdesin, ama artik hakli oldugunu da dusunuyorsun."
Ilk-ilkeler danismani ayni seyi baska turlu soyledi: oneri bir TETIKLEYICIDIR,
hacim x marj = kayip.

Bu yuzden bot artik "bugun pas" diyebiliyor. Kapiya takilinca oneri
URETMEZ ve sebebini yazar.

SABITLER: aylik tavan MUHURLU core.LIMITS'ten okunur (degistirilmedi).
Haftalik tavan ondan turetilir -- yeni bagimsiz bir sayi UYDURULMADI.

YAZMA KILIDI: defter data/ altinda, yani yalnizca GitHub Actions yazabilir
(bkz. depo.py). Yerelde sayac ilerlemez; bu bilincli -- gercek kullanim
Actions uzerinden.
"""
from __future__ import annotations

import json
from pathlib import Path

import depo
import trtime
from core import LIMITS

DEFTER = Path(__file__).resolve().parent.parent / "data" / "hacim.json"

# Aylik tavandan turetildi (4,33 hafta/ay -> yuvarlanmis 4)
HAFTALIK_TAVAN_TL = LIMITS["AYLIK_KAYIP_TAVANI_TL"] / 4.0     # 100 TL
SABIT_BIRIM_TL = LIMITS["STAKE_TL"]                            # 20 TL

# Gunde kac KUPON onerisi uretilir. Haftalik tavan / birim = 5 kupon/hafta;
# gunluk 2, boylece haftanin tamami tek gune sigmaz.
GUNLUK_MAX_KUPON = 2
HAFTALIK_MAX_KUPON = int(HAFTALIK_TAVAN_TL // SABIT_BIRIM_TL)  # 5


def _yukle() -> dict:
    try:
        return json.loads(DEFTER.read_text(encoding="utf-8"))
    except Exception:
        return {"gun": {}}


def _bugun() -> str:
    return trtime.simdi().strftime("%Y-%m-%d")


def _hafta() -> str:
    d = trtime.simdi().isocalendar()
    return f"{d[0]}-H{d[1]:02d}"


def durum() -> dict:
    d = _yukle().get("gun", {})
    bugun = d.get(_bugun(), 0)
    hafta = sum(n for g, n in d.items() if _ayni_hafta(g))
    return {
        "gun_kupon": bugun,
        "gun_kalan": max(0, GUNLUK_MAX_KUPON - bugun),
        "hafta_kupon": hafta,
        "hafta_kalan": max(0, HAFTALIK_MAX_KUPON - hafta),
        "hafta_tl": hafta * SABIT_BIRIM_TL,
        "hafta_tavan_tl": HAFTALIK_TAVAN_TL,
    }


def _ayni_hafta(gun: str) -> bool:
    try:
        from datetime import date
        y, m, g = (int(x) for x in gun.split("-"))
        return f"{date(y,m,g).isocalendar()[0]}-H{date(y,m,g).isocalendar()[1]:02d}" == _hafta()
    except Exception:
        return False


def pas_mi() -> tuple[bool, str]:
    """(pas_verilsin_mi, sebep). Kapiya takilinca oneri URETILMEZ."""
    s = durum()
    if s["gun_kalan"] <= 0:
        return True, (f"Bugün {s['gun_kupon']} kupon önerildi (günlük sınır "
                      f"{GUNLUK_MAX_KUPON}). Bugün için PAS.")
    if s["hafta_kalan"] <= 0:
        return True, (f"Bu hafta {s['hafta_kupon']} kupon önerildi = "
                      f"{s['hafta_tl']:.0f} TL (haftalık tavan "
                      f"{HAFTALIK_TAVAN_TL:.0f} TL). Hafta için PAS.")
    return False, ""


def kaydet(adet: int = 1) -> bool:
    d = _yukle()
    d.setdefault("gun", {})
    d["gun"][_bugun()] = d["gun"].get(_bugun(), 0) + adet
    return depo.yaz(DEFTER, json.dumps(d, ensure_ascii=False, indent=1))


def satir() -> list[str]:
    s = durum()
    return [
        "",
        "🧮 HACİM",
        f"   Bugün {s['gun_kupon']}/{GUNLUK_MAX_KUPON} kupon · "
        f"bu hafta {s['hafta_kupon']}/{HAFTALIK_MAX_KUPON}",
        f"   Haftalık bütçe {s['hafta_tl']:.0f}/{HAFTALIK_TAVAN_TL:.0f} TL "
        f"(birim {SABIT_BIRIM_TL:.0f} TL sabit)",
        "   Negatif beklenen değerde kontrol edebildiğin tek şey KAÇ tane",
        "   oynadığın. Birim büyütmek matematiği değiştirmez, hızlandırır.",
    ]
