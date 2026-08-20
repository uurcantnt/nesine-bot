"""Secim mekanizmasi v1.0 -- DONDURULMUS. Bkz. MEKANIZMA_v1.0.md.

Bu mekanizma KAZANAN mac tahmin etmez. Oyle bir yetenegi yok ve olmadigi
olculdu (Nesine marji %21,1; basabas icin gereken CLV de %21,1).

Mekanizmanin optimize ettigi sey MALIYET: ayni bahsi en ucuz markette,
en az bacakla, en yuksek isabet olasiligiyla oynatmak. Beklenen deger
her zaman negatiftir ve her mesajda yazilir.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import odds as O
from core import LIMITS, MARKETS


def _pick(mtid: str, m: dict) -> dict | None:
    """Bir marketten en yuksek olasilikli secenegi cikar."""
    meta = MARKETS[int(mtid)]
    o = m.get("o") or []
    if m.get("ms") != 1 or len(o) != len(meta["secenek"]):
        return None
    if any(x is None or x <= 1.0 for x in o):
        return None
    marj = O.overround(o, meta["kapsam"])
    p = O.devig(o, meta["kapsam"])
    if marj is None or p is None or marj > LIMITS["MAX_OVERROUND"]:
        return None
    i = max(range(len(p)), key=lambda k: p[k])
    if not (LIMITS["MIN_ODD"] <= o[i] <= LIMITS["MAX_ODD"]):
        return None
    return {
        "mtid": int(mtid), "market": meta["ad"], "secenek": meta["secenek"][i],
        "oran": o[i], "olasilik": p[i], "marj": marj, "mbs": m.get("mbs") or 1,
        "ev": O.ev_tek(o[i], p[i]),
    }


def candidates(snap: dict, now: datetime | None = None) -> list[dict]:
    """Mekanizma v1.0 adim 1-4: havuzu suz, sirala.

    Siralama: marj ARTAN (en ucuz once), esitlikte olasilik AZALAN.
    """
    now = now or datetime.now(timezone.utc)
    alt = now + timedelta(hours=LIMITS["MIN_SAAT"])
    ust = now + timedelta(hours=LIMITS["MAX_SAAT"])
    out = []
    for e in snap.get("olay", []):
        ts = e.get("ts")
        if not ts:
            continue
        bas = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        if not (alt <= bas <= ust):
            continue
        for mtid, m in e.get("m", {}).items():
            p = _pick(mtid, m)
            if p:
                out.append({**p, "mac": f"{e['ev']} - {e['dep']}",
                            "id": e["id"], "bas": bas, "lig": e.get("lig")})
    out.sort(key=lambda x: (round(x["marj"], 4), -x["olasilik"]))
    return out


def build_kupon(snap: dict, n: int, now: datetime | None = None) -> dict | None:
    """Istenen bacak sayisinda EN UCUZ kuponu kur.

    Kullanici kupon istedigi icin var. Marj carpimsal oldugundan her ek
    bacak EV'yi kotulestirir; _paket() bunu her seferinde hesaplayip
    mesaja yazar. Bot bacak sayisini kendiliginden ARTIRMAZ.
    """
    n = max(1, min(int(n), LIMITS["MAX_BACAK"]))
    gorulen, bacak = set(), []
    for x in candidates(snap, now):
        if x["id"] in gorulen:      # ayni mac iki bacakta olamaz
            continue
        gorulen.add(x["id"])
        bacak.append(x)
        if len(bacak) == n:
            break
    if len(bacak) < n:
        return None
    gerek = max(b["mbs"] for b in bacak)
    if gerek > len(bacak):          # MBS zorunlulugu saglanmiyor
        return None
    return _paket(bacak, zorunlu=n > 1)


def build(snap: dict, now: datetime | None = None) -> dict | None:
    """Mekanizma v1.0 adim 5: gunun onerisi.

    MBS=1 bir aday varsa TEK bahis onerilir (en ucuz kupon her zaman
    tek maclidir). Yoksa MBS zorunlulugunu karsilayan en az bacakli,
    en dusuk marjli kupon kurulur.
    """
    c = candidates(snap, now)
    if not c:
        return None
    tekler = [x for x in c if x["mbs"] == 1]
    if tekler:
        return _paket([tekler[0]], zorunlu=False)

    # MBS>1: ayni maci iki kez koyamayiz, farkli maclardan en ucuzlari al
    gorulen, bacak = set(), []
    for x in c:
        if x["id"] in gorulen:
            continue
        gorulen.add(x["id"])
        bacak.append(x)
        if len(bacak) >= max(y["mbs"] for y in bacak):
            break
    gerek = max(y["mbs"] for y in bacak)
    if len(bacak) < gerek or gerek > LIMITS["MAX_BACAK"]:
        return None
    return _paket(bacak[:gerek], zorunlu=True)


def _paket(bacak: list[dict], zorunlu: bool) -> dict:
    oranlar = [b["oran"] for b in bacak]
    plar = [b["olasilik"] for b in bacak]
    marjlar = [b["marj"] for b in bacak]
    toplam_marj = O.kupon_marj(marjlar)
    return {
        "bacak": bacak,
        "n": len(bacak),
        "zorunlu_kupon": zorunlu,
        "toplam_oran": O.kupon_oran(oranlar),
        "toplam_marj": toplam_marj,
        "ev": O.kupon_ev(oranlar, plar),
        "isabet_olasiligi": O.kupon_oran(plar),
        "gereken_clv": O.basabas_clv(toplam_marj),
        "stake": LIMITS["STAKE_TL"],
    }


def audit(bacak: list[dict]) -> dict:
    """Kullanicinin kendi kurdugu kuponu denetle (secim yapmaz, olcer)."""
    return _paket(bacak, zorunlu=len(bacak) > 1)
