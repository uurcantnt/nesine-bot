"""/kupon komutu: MAC ONU ve CANLI icin ayri ayri uc risk seviyesi.

Mekanizma v1.0 CEKIRDEGINE DOKUNMAZ. Aday havuzu ayni `coupon.candidates()`
ile uretilir; burada yalnizca havuzdan SECIM yapilir. Canliya ozgu sabitler de
core.py'ye DEGIL buraya yazilir -- boylece core/odds/coupon hash'i degismez ve
ON_KAYIT'taki gunluk push mekanizmasi etkilenmez.

Risk = isabet olasiligi. Yuksek risk DAHA IYI bir bahis degildir; sadece daha az
olasi ve daha yuksek oranlidir. Her seviyede EV negatiftir ve yazilir.
"""
from __future__ import annotations

from datetime import datetime, timezone

import bulletin
import coupon
import odds as O
import trtime
from core import LIMITS, MARKETS

# Canliya ozgu marj tavani. Olculdu: canli marjlar %21-25 bandinda, mac
# oncesinin en ucuzu %17,3. core.LIMITS["MAX_OVERROUND"] = %22 kapisi
# dogrulanmis canli maclarin yarisini eliyordu (4 macin 2'si). Bu tavan
# yalnizca CANLI bolumu icin gecerli ve her bacakta marj yazili.
CANLI_MAX_MARJ = 0.28

# Canlida BACAK basina minimum oran. core.LIMITS["MIN_ODD"]=1.20 bacak
# duzeyinde uygulaninca canli cifte sanslar (tipik 1.06-1.15) eleniyordu --
# oysa iki tanesi birlesince 1.10 x 1.10 = 1.21'e cikiyor ve %57 isabetli
# gercek bir "az riskli" kupon oluyor. Oran tabani KUPON duzeyinde uygulanir.
CANLI_MIN_BACAK_ORAN = 1.05
MIN_KUPON_ORAN = 1.40      # bunun altinda kalan kupon onerilmez (risk almaya degmez)
#
# 1.40 TABANININ ARITMETIK SONUCU: marj %17 iken tek macta
#   olasilik = (1 - 0.17) / oran  ->  oran 1.40 icin p = %59 TAVAN.
# Yani "az riskli" %70 isabet ISTEYEMEZ; 1.40 tabani ile birlikte
# ulasilabilir en yuksek isabet ~%59'dur. Bandlar buna gore ayarlandi.

# Canlida kullanilabilir marketler: MTID -> (ad, kapsam, secenek adlari)
# Ikisi de ayni imza testiyle birlikte kanitlanir (bkz. bulletin.canli_ms_dogrula).
CANLI_MARKET = {
    "53": ("Maç Sonucu (CANLI)", 1, ["1", "X", "2"]),
    "55": ("Çifte Şans (CANLI)", 2, ["1-X", "1-2", "X-2"]),
}

# (ad, {kaynak: MAKS bacak}, bacak basina olasilik alt, ust, KUPON ISABET TABANI)
#
# Bacak sayisi HEDEF degil TAVAN. Bir bacak daha eklemek kuponun toplam isabet
# olasiligini tabanin altina dusuruyorsa O BACAK EKLENMEZ -- kupon 1 veya 2
# bacakla kalir. "Uc mac verecegim" diye anlamsiz riskli bacak eklemek, marj
# carpimsal oldugu icin hem isabeti hem EV'yi cifte bozar.
RISK = [
    ("AZ RISKLI",     {"pre": 1, "canli": 2}, 0.50, 0.64, 0.45),
    ("ORTA RISKLI",   {"pre": 2, "canli": 2}, 0.55, 0.75, 0.30),
    ("YUKSEK RISKLI", {"pre": 3, "canli": 3}, 0.33, 0.54, 0.12),
]
KAYNAK = [("MAC ONU", "pre"), ("CANLI", "canli")]


# canli_adaylar()'in son cagrida NEDEN eledigi -- notlarda raporlanir
CANLI_ELEME: dict = {}


def canli_adaylar(now: datetime | None = None) -> list[dict]:
    """Canli maclardan aday uret (yalnizca market imzasi dogrulanmis olanlar)."""
    try:
        ham = bulletin.simplify_live(bulletin.fetch_live())
    except Exception as e:
        print(f"[canli] alinamadi: {e}")
        return []
    now = now or datetime.now(timezone.utc)
    CANLI_ELEME.clear()
    CANLI_ELEME.update(dogrulanan_mac=len(ham), marj=0, dusuk_oran=0,
                       dusuk_oran_ornek=[])
    out = []
    for e in ham:
        for mtid, (ad, kapsam, secenekler) in CANLI_MARKET.items():
            m = e["m"].get(mtid)
            if not m:
                continue
            o = m["o"]
            marj, p = O.overround(o, kapsam), O.devig(o, kapsam)
            if marj is None or p is None:
                continue
            if marj > CANLI_MAX_MARJ:
                CANLI_ELEME["marj"] += 1
                continue
            i = max(range(3), key=lambda k: p[k])
            if not (CANLI_MIN_BACAK_ORAN <= o[i] <= LIMITS["MAX_ODD"]):
                if o[i] < CANLI_MIN_BACAK_ORAN:
                    CANLI_ELEME["dusuk_oran"] += 1
                    if len(CANLI_ELEME["dusuk_oran_ornek"]) < 3:
                        CANLI_ELEME["dusuk_oran_ornek"].append(
                            f"{ad.split()[0]} @{o[i]:.2f} (p=%{p[i]*100:.0f})")
                continue
            out.append({
                "mtid": int(mtid), "market": ad, "secenek": secenekler[i],
                "oran": o[i], "olasilik": p[i], "marj": marj, "mbs": 1,
                "ev": O.ev_tek(o[i], p[i]),
                "mac": f"{e['ev']} - {e['dep']}", "id": e["id"],
                "bas": now, "lig": e.get("lig"), "canli": True,
            })
    out.sort(key=lambda x: (round(x["marj"], 4), -x["olasilik"]))
    return out


def _kur(havuz: list[dict], n: int, alt: float, ust: float,
         taban: float) -> tuple[list[dict], str]:
    """Bantta kalan en ucuz maclarla kupon kur; isabet tabanini KORU.

    Bacak eklemek toplam isabeti tabanin altina dusuruyorsa eklenmez.
    Donus: (bacaklar, neden). Neden bos degilse kupon eksik/yok demektir.
    """
    gorulen, bacak, p_toplam, oran_toplam = set(), [], 1.0, 1.0
    kesildi = False
    for x in havuz:
        if not (alt <= x["olasilik"] <= ust) or x["id"] in gorulen:
            continue
        # Bacak sayisi tavani -- ama odeme hala 1.20'nin altindaysa devam et
        if len(bacak) >= n and oran_toplam >= MIN_KUPON_ORAN:
            break
        if len(bacak) >= n + 1:          # mutlak tavan: tavan+1'i asma
            break
        if bacak and p_toplam * x["olasilik"] < taban:
            kesildi = True               # isabet tabani: bu bacak eklenmez
            continue
        gorulen.add(x["id"])
        bacak.append(x)
        p_toplam *= x["olasilik"]
        oran_toplam *= x["oran"]
        # Hedef bacaga ulasildi ve odeme yeterliyse dur
        if len(bacak) >= n and oran_toplam >= MIN_KUPON_ORAN:
            break
    if not bacak:
        return [], f"bantta ({alt:.2f}-{ust:.2f}) aday yok"
    if oran_toplam < MIN_KUPON_ORAN:
        return [], (f"toplam oran {oran_toplam:.2f} < {MIN_KUPON_ORAN} "
                    "(odeme anlamsiz)")
    if kesildi and len(bacak) < n:
        return bacak, f"isabet tabani %{taban*100:.0f} korundu"
    if len(bacak) > n:
        return bacak, f"odeme {MIN_KUPON_ORAN} uzerine cikarildi"
    return bacak, ""


def uc_kupon(snap: dict, canli: bool = True) -> tuple[list[dict], list[str]]:
    """Her kaynak x her risk seviyesi icin kupon. Ikinci donus: uyarilar."""
    havuzlar = {"pre": coupon.candidates(snap),
                "canli": canli_adaylar() if canli else []}
    cikti, notlar = [], []
    if canli:
        el = CANLI_ELEME
        if not havuzlar["canli"] and not el.get("dogrulanan_mac"):
            notlar.append("CANLI: su an market imzasi dogrulanan canli mac yok.")
        elif el.get("dusuk_oran"):
            notlar.append(
                f"CANLI: yuksek olasilikli {el['dusuk_oran']} secim VAR ama orani "
                f"1.20 altinda ({', '.join(el['dusuk_oran_ornek'])}) — odeme anlamsiz, "
                "onerilmedi.")
        if el.get("marj"):
            notlar.append(f"CANLI: {el['marj']} market marj tavanini (%"
                          f"{CANLI_MAX_MARJ*100:.0f}) astigi icin elendi.")
    for kaynak_ad, k in KAYNAK:
        if not havuzlar[k]:
            continue
        for ad, bacaklar, alt, ust, taban in RISK:
            hedef = bacaklar[k]
            bacak, neden = _kur(havuzlar[k], hedef, alt, ust, taban)
            if not bacak:
                notlar.append(f"{kaynak_ad} · {ad}: {neden}.")
                continue
            if max(b["mbs"] for b in bacak) > len(bacak):
                notlar.append(f"{kaynak_ad} · {ad}: MBS zorunlulugu saglanamadi.")
                continue
            p = coupon.audit(bacak)
            p.update(seviye=ad, kaynak=kaynak_ad, hedef_bacak=hedef,
                     eksik=len(bacak) < hedef, neden=neden)
            cikti.append(p)
    return cikti, notlar


def format_message(paketler: list[dict], notlar: list[str]) -> str:
    if not paketler:
        return ("NESINE · /kupon\nUygun kupon bulunamadi.\n" + "\n".join(notlar))
    L = [f"NESINE · /kupon · {trtime.simdi().strftime('%d.%m %H:%M')}"]
    for kaynak_ad, _ in KAYNAK:
        grup = [p for p in paketler if p["kaynak"] == kaynak_ad]
        if not grup:
            continue
        L.append("")
        L.append(f"═══ {kaynak_ad} ═══")
        for p in grup:
            ek = ""
            if p.get("neden"):
                ek = f"  ({p['n']} bacak — {p['neden']})"
            L.append("")
            L.append(f"— {p['seviye']} —{ek}")
            for b in p["bacak"]:
                saat = "CANLI" if b.get("canli") else trtime.bicim(b["bas"])
                L.append(f"  • {b['mac']}  [{saat}]")
                L.append(f"    {b['market']}: {b['secenek']} @{b['oran']:.2f}"
                         f"  (p=%{b['olasilik']*100:.0f}, marj %{b['marj']*100:.1f})")
            L.append(f"  Oran {p['toplam_oran']:.2f} · isabet %{p['isabet_olasiligi']*100:.1f}"
                     f" · EV %{p['ev']*100:.1f}")
    if notlar:
        L.append("")
        for n in notlar:
            L.append(f"! {n}")
    L.append("")
    L.append("Yuksek risk daha iyi bahis DEGIL: daha az olasi, daha yuksek oranli.")
    L.append("Her seviyede beklenen deger NEGATIF; bacak arttikca daha da kotu.")
    if any(p["kaynak"] == "CANLI" for p in paketler):
        L.append("CANLI marjlari olculdu %21-25 (mac oncesinin en ucuzu %17,3):")
        L.append("canli oynamak SISTEMATIK OLARAK daha pahali.")
        L.append("Canli oranlar saniyeler icinde degisir — Nesine'de gordugun oran")
        L.append("farkliysa bu hesap gecersizdir.")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    bulletin.run()
    s = bulletin.latest()
    ps, notlar = uc_kupon(s, canli="--canlisiz" not in sys.argv)
    msg = format_message(ps, notlar)
    print(msg)
    if "--dry" not in sys.argv:
        import notify
        notify.send(msg)
