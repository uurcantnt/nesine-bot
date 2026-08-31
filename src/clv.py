"""CLV — KAPANIS ORANINA GORE DEGER.

BOTUN TEK IDDIASI: "kazandirmiyorum ama ayni riski EN UCUZA aldiriyorum."
Bu iddia bugune kadar KANITSIZDI. CLV onu sinar.

MANTIK: bir macin orani, bahis acildigi andan mac baslayana kadar oynar.
Mac baslarken olusan SON oran piyasanin en iyi tahminidir -- en cok bilgi
ve en cok para o ana kadar birikmistir. CLV sunu sorar:
    Bahsi kapanis oranindan DAHA IYI bir orandan mi aldik?

    CLV = onerilen_oran / kapanis_orani - 1
    pozitif -> daha iyi fiyattan girdik (piyasa sonradan bize hak verdi)
    negatif -> daha kotu fiyattan girdik (piyasa bizim gormedigimizi gordu)

NEDEN SONUCTAN IYI BIR OLCU: sonuc beklemek gerekmiyor. Konsul (kantitatif
danisman) olcmustu: anlamli bir ROI ayrimi icin n>=1500 bahis gerekiyor --
gunde 1-2 kuponla YILLAR surer. CLV her oneride olculur ve varyansi
sonuc-tabanli olcumden 20-50 kat dusuktur.

── ESIKLER: SONUC GORULMEDEN YAZILDI (on-kayit disiplini) ──
  🟢 ortalama CLV > +%2 ve %95 araligin ALTI > 0  -> gercek sinyal
  🟡 aralik sifiri iceriyor                        -> ayirt edilemiyor
  🔴 ortalama < -%2 ve araligin USTU < 0           -> sistematik KOTU
     zamanlama; mekanizmanin "en ucuza aldiriyorum" iddiasi CURUR.

ONYUKLEME MAC DUZEYINDE KUMELENIR: ayni macin birden cok bacagi
bagimsiz degildir (geriye donuk kalibrasyonda bu hata isareti
dondurmustu; bkz. geriye_donuk.py).

YALNIZCA MAC ONCESI: canli bahiste "kapanis" kavrami yok, mac zaten
basladi. Canli bacaklar kapsam disi.
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
from pathlib import Path

import bulletin

DATA = Path(__file__).resolve().parent.parent / "data"
GOLGE = DATA / "golge.jsonl"
IYI = 0.02          # +%2
KOTU = -0.02        # -%2
ONYUKLEME = 4000


def _bahisler() -> list:
    """Golge kaydindaki MAC ONCESI bacaklar (bacak duzeyi kayitlar)."""
    if not GOLGE.exists():
        return []
    out = []
    for x in GOLGE.read_text(encoding="utf-8").splitlines():
        if not x.strip():
            continue
        try:
            k = json.loads(x)
        except Exception:
            continue
        # eski bicim (kupon duzeyi) atlanir: mac_id yok
        if "mac_id" not in k or k.get("canli"):
            continue
        if not isinstance(k.get("oran"), (int, float)):
            continue
        out.append(k)
    return out


def _kapanis_oranlari(gerek: set) -> dict:
    """{(mac_id, mtid): (kapanis_oran_listesi, kickoff_ts)} — mac BASLAMADAN
    once gorulen SON oran.

    Arsiv delta bicimindedir ama her kayit macin TUM oran blogunu tasir,
    yani her snapshot kendi kendine yeterlidir; zincir cozmeye gerek yok.
    """
    son = {}
    for f in sorted(bulletin.ARSIV.glob("*/*.json.gz")):
        try:
            k = bulletin.load(f)
        except Exception:
            continue
        # snapshot zamani dosya adindan: KLASOR/HHMMSS.json.gz
        try:
            gun = f.parent.name
            hh, mm, ss = f.name[0:2], f.name[2:4], f.name[4:6]
            from datetime import datetime, timezone
            snap_ts = datetime.fromisoformat(f"{gun}T{hh}:{mm}:{ss}+00:00").timestamp()
        except Exception:
            continue
        for e in k.get("olay", []):
            mid = str(e.get("id"))
            ts = (e.get("ts") or 0) / 1000
            for mtid_s, m in (e.get("m") or {}).items():
                anahtar = (mid, int(mtid_s))
                if anahtar not in gerek:
                    continue
                o = m.get("o") or []
                if not o or any(x is None or x <= 1 for x in o):
                    continue
                # MAC BASLAMADAN once gorulen en SON oran
                if ts and snap_ts >= ts:
                    continue
                onceki = son.get(anahtar)
                if onceki is None or snap_ts > onceki[2]:
                    son[anahtar] = (o, ts, snap_ts)
    return son


def olc() -> dict:
    bahis = _bahisler()
    if not bahis:
        return {"hata": "mac oncesi golge kaydi yok"}
    gerek = {(str(b["mac_id"]), int(b["mtid"])) for b in bahis}
    kapanis = _kapanis_oranlari(gerek)
    satir, eksik = [], 0
    for b in bahis:
        v = kapanis.get((str(b["mac_id"]), int(b["mtid"])))
        if not v:
            eksik += 1
            continue
        o, ts, snap_ts = v
        i = int(b.get("idx", -1))
        if i < 0 or i >= len(o):
            eksik += 1
            continue
        kap = o[i]
        if not kap or kap <= 1:
            eksik += 1
            continue
        satir.append({"mac": b.get("mac"), "mac_id": str(b["mac_id"]),
                      "market": b.get("market"), "secenek": b.get("secenek"),
                      "oran": b["oran"], "kapanis": kap,
                      "clv": b["oran"] / kap - 1.0,
                      "kaynak": b.get("kaynak"), "sonuc": b.get("sonuc")})
    return {"satir": satir, "eksik": eksik, "toplam": len(bahis)}


def _kumelenmis(satir: list, tohum: int = 20260831) -> tuple:
    """Mac duzeyinde kumelenmis onyukleme -> (ortalama, alt, ust)."""
    gruplar = {}
    for s in satir:
        gruplar.setdefault(s["mac_id"], []).append(s["clv"])
    kume = list(gruplar.values())
    if len(kume) < 5:
        return st.mean(s["clv"] for s in satir), float("nan"), float("nan")
    random.seed(tohum)
    boot = []
    for _ in range(ONYUKLEME):
        sec = [random.choice(kume) for _ in kume]
        duz = [x for g in sec for x in g]
        boot.append(st.mean(duz))
    boot.sort()
    return (st.mean(s["clv"] for s in satir),
            boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))])


def rapor() -> str:
    d = olc()
    if d.get("hata"):
        return f"📉 CLV\n{d['hata']}"
    ham = d["satir"]

    # ── TEKILLESTIRME ──
    # Ayni bahis birden cok kez kaydediliyor:
    #   1. Ayni kuponda BIRDEN COK RISK SEVIYESINDE gorunebiliyor (15 vaka)
    #   2. Farkli gunlerde TEKRAR onerilebiliyor
    # Ikisi de AYNI oran hareketini birden cok kez saydiriyor ve ortalamayi
    # bozuyor. Olculdu: FF Jaro - Oulu'nun tek hareketi (-%34,3) uc kez
    # sayilip ortalamayi asagi cekiyordu.
    # CLV "secilen fiyat iyi miydi" sorusudur; her AYRI bahis bir kez sayilir.
    tekil = {}
    for x in ham:
        tekil[(x["mac_id"], x["market"], x["secenek"])] = x
    s = list(tekil.values())

    if len(s) < 5:
        return (f"📉 CLV RAPORU\nÖlçülebilen bahis: {len(s)} "
                f"({d['eksik']} tanesinin kapanış oranı arşivde yok).")

    durgun = [x for x in s if abs(x["clv"]) < 1e-9]
    hareket = [x for x in s if abs(x["clv"]) >= 1e-9]
    mac = len({x["mac_id"] for x in s})
    L = ["📉 CLV RAPORU — kapanış oranına göre değer", "",
         f"Ölçülen: {len(s)} ayrı bahis · {mac} maç "
         f"(ham kayıt {len(ham)}, tekrarlar birleştirildi)",
         f"Kapanış oranı arşivde yok: {d['eksik']}", ""]

    L.append(f"Oran HİÇ DEĞİŞMEDİ: {len(durgun)} (%{100*len(durgun)/len(s):.0f})")
    L.append("  → bu marketlerde Nesine fiyatı hiç güncellemiyor;")
    L.append("     CLV orada bir şey ÖLÇEMEZ.")
    L.append("")
    if not hareket:
        L.append("Hiçbir oran hareket etmemiş — ölçüm yapılamıyor.")
        return "\n".join(L)

    poz = sum(1 for x in hareket if x["clv"] > 0)
    ort, alt, ust = _kumelenmis(hareket)
    med = st.median([x["clv"] for x in hareket])
    L.append(f"Oran HAREKET ETTİ: {len(hareket)} bahis")
    L.append(f"  lehimize {poz} · aleyhimize {len(hareket)-poz} "
             f"(%{100*poz/len(hareket):.0f} lehimize)")
    L.append(f"  ortalama CLV {ort*100:+.2f}% · MEDYAN {med*100:+.2f}%")
    L.append(f"  %95 aralık (maç düzeyinde kümelenmiş): "
             f"{alt*100:+.2f}% … {ust*100:+.2f}%")
    L.append("")
    L.append("  NOT: ortalama tek bir büyük harekete duyarlıdır; medyan")
    L.append("  daha sağlam. İkisi ters yöndeyse ortalamaya güvenme.")
    L.append("")
    if ort > IYI and alt == alt and alt > 0:
        L.append("🟢 GERÇEK SİNYAL: bot kapanıştan iyi fiyattan giriyor.")
        L.append("   'Aynı riski en ucuza aldırıyorum' iddiası DESTEKLENDİ.")
    elif ort < KOTU and ust == ust and ust < 0:
        L.append("🔴 SİSTEMATİK KÖTÜ ZAMANLAMA: mekanizma gözden geçirilmeli.")
    else:
        L.append("🟡 AYIRT EDİLEMİYOR: aralık sıfırı içeriyor.")
        L.append("   Zamanlama açısından ne iyi ne kötü.")
    L.append("")
    L.append("Eşikler bu ölçüm YAPILMADAN ÖNCE yazıldı (ön-kayıt).")
    from collections import defaultdict
    g = defaultdict(list)
    for x in hareket:
        g[x.get("kaynak") or "?"].append(x["clv"])
    if len(g) > 1:
        L += ["", "KOMUT KIRILIMI (yalnızca oranı hareket edenler)"]
        for ad, v in sorted(g.items(), key=lambda z: -len(z[1])):
            not_ = "  ← n<30, GÜRÜLTÜ" if len(v) < 30 else ""
            L.append(f"  /{ad:<10} n={len(v):<4} medyan "
                     f"{st.median(v)*100:+.2f}%{not_}")
    return "\n".join(L)


if __name__ == "__main__":
    print(rapor())
