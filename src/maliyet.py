"""Bacak maliyeti aritmetigi ve TEK MAC bolumu.

KONSUL BULGUSU (5 danismanin 4'u bagimsiz olarak ayni yere geldi):
bu isin asil kisiti model degil ARITMETIK. Nesine marji medyan %21,1 ve
kupon marji CARPIMSALDIR:

    n bacakta beklenen getiri = -(1 - 1/(1+marj)^n)

        1 bacak  -%17,4
        2 bacak  -%31,8
        3 bacak  -%43,6
        5 bacak  -%61,5

Yani bacak sayisi, modeldeki HERHANGI bir iyilestirmeden buyuk bir
kaldiractir. Modelin Nesine'den medyan sapmasi ~5 puan; bir bacak eklemek
14 puan maliyet ekliyor. Bu modul o aritmetigi GIZLEMEZ, her kuponun
ustune yazar.

TEK MAC NEDEN AYRI BOLUM: Nesine maclarin %59'unda en az 3 mac zorunlu
kiliyor (MBS). Yalnizca 169/936 mac tek oynanabiliyor. Bu 169 mac
yapisal olarak 2,5 kat ucuz ve havuzun icinde kaybolduklari icin
kullanici onlari goremiyordu.
"""
from __future__ import annotations

# Olculen medyan marj (n=936 acik 1X2 marketi, 2026-08-20)
OLCULEN_MARJ = 0.211


def beklenen_getiri(marj: float, n: int) -> float:
    """n bacakli kuponun beklenen getirisi (negatif sayi)."""
    return -(1.0 - (1.0 / (1.0 + marj)) ** n)


def tablo(marj: float = OLCULEN_MARJ, en_fazla: int = 3) -> list[str]:
    return [f"{n} maç {beklenen_getiri(marj, n)*100:+.1f}%"
            for n in range(1, en_fazla + 1)]


def maliyet_satiri(p: dict) -> list[str]:
    """Bir kuponun kendi maliyet aritmetigi.

    Tek-mac esdegeri, kuponun KENDI marjindan cikarilir: n bacakli kuponun
    bilesik marji (1+m_bacak)^n - 1 oldugundan, bacak basi marj
    (1+toplam_marj)^(1/n) - 1'dir. Boylece kiyas bu kuponun gercek
    fiyatiyla yapilir, genel medyanla degil.
    """
    n = p["n"]
    ev = p.get("ev")
    tm = p.get("toplam_marj")
    L = ["", f"💸 BU KUPONUN MALİYETİ  ({n} maç)"]
    if isinstance(ev, (int, float)):
        L.append(f"   Beklenen getiri  {ev*100:+.1f}%   "
                 f"(100 TL yatırsan uzun vadede ~{100+ev*100:.0f} TL döner)")
    if isinstance(tm, (int, float)):
        L.append(f"   Nesine'nin payı  %{tm*100:.1f}")
    if n > 1 and isinstance(tm, (int, float)):
        bacak_marj = (1.0 + tm) ** (1.0 / n) - 1.0
        tek = beklenen_getiri(bacak_marj, 1)
        L.append("   ⚠️ Bacak sayısı maliyeti ÇARPAR: "
                 + " · ".join(tablo(bacak_marj, n)))
        L.append(f"   Aynı bahisleri tek maç oynayabilseydin {tek*100:+.1f}% "
                 "olacaktı.")
    elif n == 1:
        L.append("   ✅ Tek maç — bu, mümkün olan EN UCUZ biçim.")
    return L


def tekli_adaylar(havuz: list[dict], en_fazla: int = 3,
                  min_oran: float = 1.20) -> list[dict]:
    """MBS=1 (tek basina oynanabilen) en degerli adaylar."""
    v = [b for b in havuz
         if b.get("mbs", 1) == 1
         and b.get("oran", 0) >= min_oran
         and not b.get("canli")]
    v.sort(key=lambda x: -(x.get("deger") if x.get("deger") is not None else -1.0))
    secili, gorulen = [], set()
    for b in v:
        if b["mac"] in gorulen:
            continue
        gorulen.add(b["mac"])
        secili.append(b)
        if len(secili) >= en_fazla:
            break
    return secili


def tekli_bolumu(havuz: list[dict], bicim, anlam_fn) -> list[str]:
    """Tek mac bolumu. bicim=_s (sayi bicimleyici), anlam_fn=anlam()."""
    v = tekli_adaylar(havuz)
    L = ["", "═" * 30, "1️⃣ TEK MAÇ OYNANABİLENLER", "═" * 30, ""]
    L.append(f"   3 maçlık kupon {beklenen_getiri(OLCULEN_MARJ,3)*100:+.1f}%,"
             f" tek maç {beklenen_getiri(OLCULEN_MARJ,1)*100:+.1f}%")
    L.append("   → tek maç 2,5 kat ucuz. Nesine maçların %59'unda en az")
    L.append("   3 maç zorunlu kılıyor; aşağıdakiler o zorunluluğu OLMAYANLAR.")
    if not v:
        L += ["", "   Şu an uygun tek maç yok (hepsi kupon zorunlu)."]
        return L
    for b in v:
        L.append("")
        L.append(f"  ⚽ {b['mac']}")
        if b.get("lig_ad"):
            L.append(f"     {b['lig_ad']}")
        L.append(f"     {b['market']} → {b['secenek']}   oran {bicim(b['oran'])}")
        a = anlam_fn(b)
        if a:
            L.append(f"     yani: {a}")
        tp = b.get("tahmin_p")
        if isinstance(tp, (int, float)):
            L.append(f"     tutma ihtimali %{tp*100:.0f}")
    return L
