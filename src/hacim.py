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

# BIRIM: "TUR" (bir /kupon calistirmasi), "KUPON" DEGIL.
#
# NEDEN AYRIM (2026-08-21 konsul 2. tur, 3 danisman ayni hatayi buldu):
# tek bir /kupon kosusu 5-6 KUPON basiyor (mac onu + canli x 3 risk seviyesi)
# ama sayac 1 artiyordu. "Haftalik 5 kupon = 100 TL" ifadesi bu yuzden
# YANILTICIYDI: her turdan 3 kupon oynanirsa gercek 300 TL olur.
#
# Bot kullanicinin NE OYNADIGINI GOREMEZ (yalnizca ne ONERDIGINI bilir).
# Bu yuzden kapi TUR sayisina konur ve butcenin dayandigi VARSAYIM
# mesajda ACIKCA yazilir: her turdan EN FAZLA 1 kupon oynanir.
# Sunulan kupon sayisi da ayrica sayilir ki varsayim izlenebilsin.
GUNLUK_MAX_TUR = 2
HAFTALIK_MAX_TUR = int(HAFTALIK_TAVAN_TL // SABIT_BIRIM_TL)  # 5 tur


def _yukle() -> dict:
    """Defteri oku. ARIZA DURUMUNDA 'PAS' TARAFINA DUS.

    Onceden her hatada bos defter donuyordu -> sayac sifirlaniyor, kapi
    ACILIYORDU. Yani bozulma botu SERBEST BIRAKIYORDU. Bir guvenlik kapisi
    arizalandiginda kapali tarafa dusmelidir.

    Dosya YOKSA bu normaldir (ilk kosu) -> bos defter.
    Dosya VARSA ama okunamiyorsa -> bozuk: {"bozuk": True} donulur ve
    pas_mi() oneri uretimini durdurur.
    """
    if not DEFTER.exists():
        return {"gun": {}}
    try:
        d = json.loads(DEFTER.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            raise ValueError("defter sozluk degil")
        return d
    except Exception as e:
        print(f"[hacim] DEFTER OKUNAMADI ({e}) — guvenli tarafa dusuluyor")
        return {"bozuk": True, "gun": {}}


def _bugun() -> str:
    return trtime.simdi().strftime("%Y-%m-%d")


def _hafta() -> str:
    d = trtime.simdi().isocalendar()
    return f"{d[0]}-H{d[1]:02d}"


def _sayi(v) -> tuple[int, int]:
    """Defter girdisi -> (tur, sunulan_kupon). Eski bicim (duz sayi) desteklenir."""
    if isinstance(v, dict):
        return int(v.get("tur", 0)), int(v.get("kupon", 0))
    return int(v or 0), 0


def durum() -> dict:
    ham = _yukle()
    d = ham.get("gun", {})
    g_tur, g_kup = _sayi(d.get(_bugun()))
    h_tur = h_kup = 0
    for g, v in d.items():
        if _ayni_hafta(g):
            t, k = _sayi(v)
            h_tur += t
            h_kup += k
    return {
        "bozuk": bool(ham.get("bozuk")),
        "gun_tur": g_tur,
        "gun_kupon": g_kup,
        "gun_kalan": max(0, GUNLUK_MAX_TUR - g_tur),
        "hafta_tur": h_tur,
        "hafta_kupon": h_kup,
        "hafta_kalan": max(0, HAFTALIK_MAX_TUR - h_tur),
        "hafta_tl": h_tur * SABIT_BIRIM_TL,
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
    if s["bozuk"]:
        return True, ("Hacim defteri OKUNAMADI. Kaç kupon önerildiğini "
                      "bilemediğim için öneri üretmiyorum — bozuk bir sınır, "
                      "sınırsızlık demektir.")
    if s["gun_kalan"] <= 0:
        return True, (f"Bugün {s['gun_tur']} tur öneri verildi (günlük sınır "
                      f"{GUNLUK_MAX_TUR} tur, {s['gun_kupon']} kupon sunuldu). "
                      "Bugün için PAS.")
    if s["hafta_kalan"] <= 0:
        return True, (f"Bu hafta {s['hafta_tur']} tur öneri verildi "
                      f"({s['hafta_kupon']} kupon sunuldu). Haftalık tavan "
                      f"{HAFTALIK_MAX_TUR} tur = {HAFTALIK_TAVAN_TL:.0f} TL. "
                      "Hafta için PAS.")
    return False, ""


def kaydet(kupon: int = 0, tur: int = 1) -> bool:
    """Bir oneri turunu ve o turda SUNULAN kupon sayisini kaydet."""
    d = _yukle()
    if d.get("bozuk"):
        print("[hacim] defter bozuk — uzerine YAZILMIYOR")
        return False
    d.setdefault("gun", {})
    t, k = _sayi(d["gun"].get(_bugun()))
    d["gun"][_bugun()] = {"tur": t + tur, "kupon": k + int(kupon)}
    return depo.yaz(DEFTER, json.dumps(d, ensure_ascii=False, indent=1))


def satir(sunulan: int = 0) -> list[str]:
    s = durum()
    tur = s["hafta_tur"]
    L = [
        "",
        "🧮 HACİM",
        f"   Bugün {s['gun_tur']}/{GUNLUK_MAX_TUR} tur · "
        f"bu hafta {tur}/{HAFTALIK_MAX_TUR} tur",
    ]
    if sunulan:
        L.append(f"   Bu turda {sunulan} kupon sunuldu — hepsini oynaman "
                 "BEKLENMİYOR.")
    L += [
        f"   Haftalık bütçe {HAFTALIK_TAVAN_TL:.0f} TL, birim "
        f"{SABIT_BIRIM_TL:.0f} TL sabit.",
        f"   ⚠️ Bu bütçe 'her turdan EN FAZLA 1 kupon oynarsın' varsayımına",
        f"   dayanır. Her turdan 3 oynarsan haftalık {HAFTALIK_TAVAN_TL*3:.0f} TL olur.",
        "   Bot ne oynadığını GÖREMEZ — bu sınır bir söz, bir ölçüm değil.",
        "   Negatif beklenen değerde kontrol edebildiğin tek şey KAÇ tane",
        "   oynadığın. Birim büyütmek matematiği değiştirmez, hızlandırır.",
    ]
    return L
