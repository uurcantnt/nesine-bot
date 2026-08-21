"""SOFASCORE — canli skor + dakika + KORNER + KART. Anahtarsiz.

NEDEN GEREKLI: canli korner/kart istatistigi icin elimizde calisan tek
kaynak Fotmob'du ve kapsamasi dardi (Misir 2. Lig gibi ligler yok).
TheSportsDB skor/dakika veriyor ama istatistik ucu ucretsiz katmanda BOS.

ERISIM — IKI KATMANLI ENGEL (olculdu 2026-08-21, sonda ile):
  YERELDE (Turkiye, ev IP'si):
    duz urllib + her turlu tarayici basligi -> 403
    curl_cffi impersonate="chrome"          -> 200 · 143 canli olay
  GITHUB ACTIONS'TA:
    duz urllib   -> 403
    curl_cffi    -> 403      <-- TLS taklidi BURADA YETMIYOR

Yani Cloudflare IKI ayri kontrol uyguluyor: TLS parmak izi (curl_cffi asiyor)
VE veri merkezi IP itibari (asilamiyor). GitHub Actions IP'leri engelli.

⚠️ SONUC: Sofascore YALNIZCA YERELDEN calisir. Bot verisini Actions'ta
uretiyor (bkz. depo.py yazma kilidi), dolayisiyla Sofascore BORU HATTININ
GUVENILIR PARCASI DEGILDIR. Kod burada duruyor cunku:
  - yerel calistirmada (gelistirme/elle kosu) gercek kazanc sagliyor
  - Actions'ta sessizce devre disi kalir, hicbir seyi bozmaz
Actions'ta bos yere denenmemesi icin ilk 403'ten sonra SUREC BOYUNCA
kapatilir (bkz. _KAPALI).

OLCULEN KAPSAMA (2026-08-21): Sofascore 83 canli mac · Nesine 31 canli mac
-> basit isim eslestirmesiyle 22 eslesme (%71). Fotmob'da olmayan Misir
Premier Lig maci (Wadi Degla - ZED) korner 1-2 / sari 2-1 ile GELDI.

DONEM AYRIMI: istatistik ucu ALL / 1ST / 2ND doner -> ilk yari korner
bahisleri icin de dogrudan kullanilabilir (Fotmob'da bu ayrim zahmetliydi).
"""
from __future__ import annotations

import time

try:
    from curl_cffi import requests as _rq
except ImportError:      # kurulu degilse modul sessizce devre disi kalir
    _rq = None

CANLI = "https://api.sofascore.com/api/v1/sport/football/events/live"
ISTATISTIK = "https://api.sofascore.com/api/v1/event/{}/statistics"
TAKLIT = "chrome"
ONBELLEK_SN = 45          # canli veri; 45 sn'den taze tutmanin anlami yok
_ONB: dict = {}
# Ilk 403'ten sonra surec boyunca kapatilir. Actions'ta her cagride bos yere
# HTTP denemenin anlami yok (olculdu: orada her zaman 403).
_KAPALI = False

# Sofascore status.code -> bizim devre adi
DEVRE = {6: "1H", 7: "2H", 31: "HT", 32: "HT", 33: "ET", 100: "FT"}


def kullanilabilir() -> bool:
    return _rq is not None


def _get(url: str, timeout: int = 25):
    global _KAPALI
    if _rq is None or _KAPALI:
        return None
    try:
        r = _rq.get(url, impersonate=TAKLIT, timeout=timeout)
        if r.status_code == 403:
            _KAPALI = True
            print("[sofascore] 403 — bu ortamdan erisilemiyor "
                  "(veri merkezi IP engeli), surec boyunca kapatildi")
            return None
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        print(f"[sofascore] {url[-40:]}: {e}")
        return None


def canli() -> list:
    """Devam eden futbol maclari. Ulasilamazsa BOS liste (hata firlatmaz)."""
    simdi = time.time()
    if _ONB.get("t", 0) + ONBELLEK_SN > simdi:
        return _ONB.get("v", [])
    d = _get(CANLI)
    ev = (d or {}).get("events") or []
    if ev:
        _ONB.update(t=simdi, v=ev)
    return ev


def dakika(e: dict) -> int | None:
    """Gercek dakika. initial = periyodun basladigi saniye (2. yari icin 2700)."""
    t = e.get("time") or {}
    cp, init = t.get("currentPeriodStartTimestamp"), t.get("initial")
    kod = (e.get("status") or {}).get("code")
    if kod in (31, 32):          # devre arasi
        return 45
    if cp is None or init is None:
        return None
    dk = int((init + (time.time() - cp)) / 60)
    return max(0, min(dk, 120))


def skor(e: dict) -> tuple:
    return ((e.get("homeScore") or {}).get("current"),
            (e.get("awayScore") or {}).get("current"))


def _sayi(v):
    """'59%' -> 59 · '1' -> 1 · digerleri None."""
    try:
        return int(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


ILGI = {                      # Sofascore adi -> bizim anahtar
    "corner kicks": "korner",
    "yellow cards": "sari",
    "red cards": "kirmizi",
    "ball possession": "topla_oynama",
    "shots on target": "isabetli_sut",
    "total shots": "sut",
}


def istatistik(event_id) -> dict | None:
    """{'ALL': {'korner': (ev,dep), ...}, '1ST': {...}} — yoksa None."""
    d = _get(ISTATISTIK.format(event_id))
    if not d:
        return None
    out = {}
    for grup in d.get("statistics") or []:
        donem = grup.get("period") or "ALL"
        alan = {}
        for g in grup.get("groups") or []:
            for it in g.get("statisticsItems") or []:
                k = ILGI.get(str(it.get("name", "")).strip().lower())
                if not k:
                    continue
                h, a = _sayi(it.get("home")), _sayi(it.get("away"))
                if h is not None and a is not None:
                    alan[k] = (h, a)
        if alan:
            out[donem] = alan
    return out or None


def durum(e: dict) -> dict:
    """Tek macin ozeti — canli_durum.py ile ayni bicimde."""
    ev_s, dep_s = skor(e)
    return {
        "ev_skor": ev_s, "dep_skor": dep_s,
        "dakika": dakika(e),
        "devre": DEVRE.get((e.get("status") or {}).get("code")),
        "sofa_id": e.get("id"),
        "ev_ad": (e.get("homeTeam") or {}).get("name"),
        "dep_ad": (e.get("awayTeam") or {}).get("name"),
        "lig": (e.get("tournament") or {}).get("name"),
    }


# ─────────────────────────── ISIM ESLESTIRME ───────────────────────────
# fotmob.py / canli_durum.py ile AYNI sadelestirme kullanilir ki bir takim
# ismi duzeltmesi (stats.ELLE) her uc kaynakta birden gecerli olsun.

def indeks(olaylar: list | None = None) -> dict:
    """(sade_ev, sade_dep) -> olay."""
    import stats as ST
    out = {}
    for e in (olaylar if olaylar is not None else canli()):
        h = ST.sadelestir((e.get("homeTeam") or {}).get("name") or "")
        a = ST.sadelestir((e.get("awayTeam") or {}).get("name") or "")
        if h and a:
            out[(h, a)] = e
    return out


def esle(idx: dict, ev: str, dep: str) -> dict | None:
    """Nesine takim adlariyla Sofascore olayini bul (tam, sonra parcali)."""
    import stats as ST
    h = ST.sadelestir(ST.ELLE.get((ev or "").lower(), ev or ""))
    a = ST.sadelestir(ST.ELLE.get((dep or "").lower(), dep or ""))
    if not h or not a:
        return None
    if (h, a) in idx:
        return idx[(h, a)]
    for (ih, ia), v in idx.items():
        if (h in ih or ih in h) and (a in ia or ia in a):
            return v
    return None


# ─────────────────── CLOUDFLARE KOPRUSU (Actions icin) ───────────────────
# Sofascore veri merkezi IP'lerinden erisilemiyor (Actions 403, Worker 403).
# Mac'teki toplayici (sofa_toplayici.py) veriyi cekip Worker KV'ye birakir;
# bot BURADAN okur. Boylece Actions Sofascore'a HIC gitmez.
KOPRU = "https://nesine-bot.tantaugur.workers.dev/sofa/oku"
KOPRU_MAX_YAS = 900        # 15 dk'dan eski veri KULLANILMAZ
_KOPRU_ONB: dict = {}


def kopru(max_yas: int = KOPRU_MAX_YAS) -> dict | None:
    """Mac toplayicisinin biraktigi veri: {"3069296": {"skor":[1,0],...}}.

    BAYAT VERI KULLANILMAZ: Mac kapaliysa KV kaydi 20 dk TTL ile zaten
    duser, ayrica burada 15 dk yas siniri var. Bayat canli skor, veri
    yoklugundan TEHLIKELIDIR -- dolu gorunur ama yanlistir.

    NOT: User-Agent SART. workers.dev, Python'un varsayilan
    "Python-urllib/3.x" ajanini 403 ile reddediyor (olculdu).
    """
    import json as _j
    import urllib.request as _u
    simdi = time.time()
    if _KOPRU_ONB.get("t", 0) + 40 > simdi:
        return _KOPRU_ONB.get("v")
    try:
        req = _u.Request(KOPRU, headers={"User-Agent": "nesine-bot/1.0"})
        with _u.urlopen(req, timeout=15) as r:
            d = _j.loads(r.read())
    except Exception as e:
        print(f"[sofa-kopru] okunamadi: {e}")
        return None
    yas = simdi - float(d.get("t") or 0)
    if yas > max_yas:
        print(f"[sofa-kopru] veri BAYAT ({yas/60:.0f} dk) — kullanilmiyor")
        return None
    _KOPRU_ONB.update(t=simdi, v=d)
    print(f"[sofa-kopru] {d.get('n')} mac · {yas:.0f} sn yasinda")
    return d
