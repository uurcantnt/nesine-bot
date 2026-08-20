"""/kupon komutu: uc risk seviyesinde kupon uretir (mac oncesi + canli).

Mekanizma v1.0 CEKIRDEGINE DOKUNMAZ -- aday havuzu ayni `coupon.candidates()`
ile uretilir, burada yalnizca havuzdan SECIM yapilir. Bu yuzden core/odds/coupon
hash'i degismez ve ON_KAYIT'taki gunluk push mekanizmasi etkilenmez.

Risk = isabet olasiligi. Yuksek risk DAHA IYI bir bahis degildir; sadece daha
az olasi ve daha yuksek oranlidir. Her seviyede EV negatiftir ve yazilir --
bacak sayisi arttikca DAHA DA negatif olur (marj carpimsal).
"""
from __future__ import annotations

from datetime import datetime, timezone

import bulletin
import coupon
import odds as O
from core import LIMITS, MARKETS

# (ad, bacak, olasilik alt, olasilik ust, kaynak)
# kaynak: "hepsi" = mac oncesi + canli havuzu, "canli" = yalnizca canli maclar
#
# CANLI seviyesi NEDEN ayri: canli marjlar olculdu, %21-25 bandinda -- mac
# oncesinin en ucuzu %17,3. Ortak havuzda marja gore siralaninca canli maclar
# HICBIR ZAMAN secilmiyor. Kullanici canli kupon istedigi icin ayri seviye,
# ama pahali oldugu mesajda yazili.
SEVIYE = [
    ("AZ RISKLI",     1, 0.60, 0.90, "hepsi"),
    ("ORTA RISKLI",   3, 0.58, 0.75, "hepsi"),
    ("YUKSEK RISKLI", 3, 0.38, 0.55, "hepsi"),
    ("CANLI",         2, 0.35, 0.90, "canli"),
]


def canli_adaylar(now: datetime | None = None) -> list[dict]:
    """Canli maclardan aday uret (yalnizca imzasi dogrulanmis olanlar)."""
    try:
        ham = bulletin.simplify_live(bulletin.fetch_live())
    except Exception as e:
        print(f"[canli] alinamadi: {e}")
        return []
    now = now or datetime.now(timezone.utc)
    out = []
    for e in ham:
        m = e["m"]["53"]
        o = m["o"]
        marj = O.overround(o, 1)
        p = O.devig(o, 1)
        if marj is None or p is None or marj > LIMITS["MAX_OVERROUND"]:
            continue
        i = max(range(3), key=lambda k: p[k])
        if not (LIMITS["MIN_ODD"] <= o[i] <= LIMITS["MAX_ODD"]):
            continue
        out.append({
            "mtid": 53, "market": "Maç Sonucu (CANLI)",
            "secenek": MARKETS[1]["secenek"][i], "oran": o[i], "olasilik": p[i],
            "marj": marj, "mbs": 1, "ev": O.ev_tek(o[i], p[i]),
            "mac": f"{e['ev']} - {e['dep']}", "id": e["id"],
            "bas": now, "lig": e.get("lig"), "canli": True,
        })
    return out


def havuz(snap: dict, canli: bool = True) -> list[dict]:
    """Mac oncesi + canli adaylar, marj ARTAN sirali."""
    h = [dict(x, canli=False) for x in coupon.candidates(snap)]
    if canli:
        h += canli_adaylar()
    h.sort(key=lambda x: (round(x["marj"], 4), -x["olasilik"]))
    return h


def uc_kupon(snap: dict, canli: bool = True) -> list[dict]:
    """Her seviye icin en ucuz kuponu kur. Uretilemeyen seviye atlanir."""
    h = havuz(snap, canli)
    canli_h = [x for x in h if x.get("canli")]
    cikti = []
    for ad, n, alt, ust, kaynak in SEVIYE:
        kaynak_h = canli_h if kaynak == "canli" else h
        if kaynak == "canli" and not canli_h:
            continue
        uygun = [x for x in kaynak_h if alt <= x["olasilik"] <= ust]
        gorulen, bacak = set(), []
        for x in uygun:
            if x["id"] in gorulen:          # ayni mac iki bacakta olamaz
                continue
            gorulen.add(x["id"])
            bacak.append(x)
            if len(bacak) == n:
                break
        if len(bacak) < n:
            if kaynak == "canli" and bacak:      # tek canli mac varsa onu ver
                pass
            else:
                continue
        if max(b["mbs"] for b in bacak) > len(bacak):   # MBS zorunlulugu
            continue
        p = coupon.audit(bacak)
        p["seviye"] = ad
        cikti.append(p)
    return cikti


def format_message(paketler: list[dict]) -> str:
    if not paketler:
        return "NESINE · uygun kupon bulunamadi (marj/oran/saat filtrelerini gecen aday yok)."
    L = [f"NESINE · /kupon · {datetime.now().strftime('%d.%m %H:%M')}", ""]
    for p in paketler:
        canli_var = any(b.get("canli") for b in p["bacak"])
        L.append(f"— {p['seviye']} —" + ("  (canli bacak var)" if canli_var else ""))
        for b in p["bacak"]:
            et = " [CANLI]" if b.get("canli") else ""
            L.append(f"  • {b['mac']}{et}")
            L.append(f"    {b['market']}: {b['secenek']} @{b['oran']:.2f}"
                     f"  (p=%{b['olasilik']*100:.0f}, marj %{b['marj']*100:.1f})")
        L.append(f"  Oran {p['toplam_oran']:.2f} · isabet %{p['isabet_olasiligi']*100:.1f}"
                 f" · EV %{p['ev']*100:.1f}")
        L.append("")
    L.append("Yuksek risk daha iyi bahis DEGIL: daha az olasi, daha yuksek oranli.")
    if any(p["seviye"] == "CANLI" for p in paketler):
        L.append("CANLI marjlari olculdu: %21-25 (mac oncesinin en ucuzu %17,3) —")
        L.append("yani canli oynamak SISTEMATIK OLARAK daha pahali.")
    L.append("Her seviyede beklenen deger NEGATIF; bacak arttikca daha da kotu.")
    if any(b.get("canli") for p in paketler for b in p["bacak"]):
        L.append("CANLI bacaklarin orani saniyeler icinde degisir — Nesine'de gordugun")
        L.append("oran farkliysa bu hesap gecersizdir.")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    bulletin.run()
    s = bulletin.latest()
    ps = uc_kupon(s, canli="--canlisiz" not in sys.argv)
    msg = format_message(ps)
    print(msg)
    if "--dry" not in sys.argv:
        import notify
        notify.send(msg)
