"""Golge kayit: her oneriyi yaz, sonucunu coz, KALIBRASYONU olc.

NEDEN: "model %74 dedi" cumlesinin dogru olup olmadigi ancak sonuclar
bilinince olculur. Bu dosya olmadan bot kendini degerlendiremez ve
"birkac kupon tuttu" gibi anlamsiz kanitlara mahkum kaliriz.

OLCULEN: her kaynagin (Nesine / modelimiz / DraftKings / gecmis /
Piyasa-fd) tahmin ettigi olasilik ile GERCEKLESEN isabet oraninin
karsilastirmasi.

SURUM ALANI NEDEN VAR: tahmin uretme bicimi degistiginde eski ve yeni
kayitlari ayni kalibrasyon orneklemine atmak, olcumu sessizce bozar --
"%70 dedigimizin %70'i tuttu mu" sorusu iki farkli mekanizmanin
karisimini olcer hale gelir. Bu yuzden her kayit hangi surumle
uretildigini TASIR ve kalibrasyon surum surum ayrilabilir.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
KAYIT = DATA / "golge.jsonl"

# Tahmin uretme surumu. Havuza yeni bir KAYNAK eklendiginde ya da
# agirlik/esik degistiginde ARTIRILIR.
#   v1  (2026-08-21) logit havuzu: Nesine · model · gecmis · DraftKings
#   v2  (2026-08-31) + Piyasa(fd) ikinci fiyati; ayrica eslestirici
#       sikilastirildi (genc/rezerv/kadin takim ayrimi, tek-tarafli
#       kelime eslesmesi reddi) -- bu, MODEL ve GECMIS kaynaklarinin
#       hangi istatistige baglandigini da degistirir.
SURUM = "v2"


def kaydet(paketler: list, kaynak: str = "kupon") -> int:
    """Onerilen her bacagi tum tahmin kaynaklariyla birlikte logla."""
    import json as _j
    esl = {}
    try:
        esl = _j.loads((DATA / "eslesme.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    import depo
    if not depo.yazilabilir():
        print("[depo] yerel calisma: golge kaydi YAPILMADI (kilit)")
        return 0
    n = 0
    KAYIT.parent.mkdir(parents=True, exist_ok=True)
    with KAYIT.open("a", encoding="utf-8") as f:
        for p in paketler:
            for b in p["bacak"]:
                amp = b.get("_ampirik")
                f.write(json.dumps({
                    "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "kaynak": kaynak, "seviye": p.get("seviye"),
                    "kaynak_tur": p.get("kaynak"),
                    "mac_id": b["id"], "mac": b["mac"], "lig": b.get("lig_ad"),
                    "fotmob_id": (esl.get(str(b["id"])) or {}).get("fotmob_id"),
                    "mtid": b["mtid"], "idx": b["idx"], "sov": b.get("sov"),
                    "market": b["market"], "secenek": b["secenek"],
                    "oran": b["oran"], "canli": bool(b.get("canli")),
                    "nesine_p": b["olasilik"], "model_p": b.get("model_p"),
                    "dk_p": b.get("dk_p"), "ampirik_p": (amp or {}).get("oran"),
                    "tahmin_p": b.get("tahmin_p"), "deger": b.get("deger"),
                    # Ikinci fiyat: VARSA sayi, YOKSA neden. Yoklugu de
                    # kaydedilir; sonradan "kapsam ne kadardi" sorusu
                    # ancak boyle cevaplanabilir.
                    "fd_p": (b.get("fd") or {}).get("p"),
                    "fd_kaynak": (b.get("fd") or {}).get("kaynak"),
                    "fd_marj": (b.get("fd") or {}).get("marj"),
                    "fd_yok": None if (b.get("fd") or {}).get("var")
                              else (b.get("fd") or {}).get("neden"),
                    "surum": SURUM,
                    "sonuc": None,
                }, ensure_ascii=False) + "\n")
                n += 1
    return n


def _oku() -> list:
    if not KAYIT.exists():
        return []
    out = []
    for satir in KAYIT.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if satir:
            try:
                out.append(json.loads(satir))
            except json.JSONDecodeError:
                pass
    return out


def _yaz(kayitlar: list) -> None:
    import depo
    depo.yaz(KAYIT, "\n".join(json.dumps(k, ensure_ascii=False)
                               for k in kayitlar) + "\n")


def coz(en_fazla: int = 300) -> tuple:
    """Sonucu bilinmeyen kayitlari cozumle. (cozulen, kalan)"""
    import sonuc as S
    kayitlar = _oku()
    bekleyen = [k for k in kayitlar if k.get("sonuc") is None and k.get("fotmob_id")]
    onbellek: dict = {}
    cozulen = 0
    for k in bekleyen[:en_fazla]:
        fid = k["fotmob_id"]
        if fid not in onbellek:
            onbellek[fid] = S.mac_sonucu(fid)
        s = onbellek[fid]
        if not s:
            continue                      # mac bitmemis
        r = S.degerlendir(k["mtid"], k["idx"], k.get("sov"), s)
        if r is None:
            k["sonuc"] = "belirlenemedi"
        else:
            k["sonuc"] = bool(r)
            k["mac_skoru"] = f"{s['ev_gol']}-{s['dep_gol']}"
        cozulen += 1
    _yaz(kayitlar)
    kalan = sum(1 for k in kayitlar if k.get("sonuc") is None)
    return cozulen, kalan


def rapor() -> str:
    """Kalibrasyon raporu: her kaynak ne kadar isabetli tahmin ediyor?"""
    kayitlar = [k for k in _oku() if isinstance(k.get("sonuc"), bool)]
    if not kayitlar:
        return "📊 GÖLGE RAPOR\nHenüz sonucu belli olan öneri yok."
    L = [f"📊 GÖLGE RAPOR · {len(kayitlar)} sonuçlanmış seçim", ""]
    # SURUM KIRILIMI. Tahmin uretme bicimi degistiginde asagidaki tum
    # sayilar KARISIK bir orneklemi olcer. Bunu gizlemek yerine en ustte
    # yaziyoruz ki okuyan, hangi mekanizmanin olculdugunu bilsin.
    sur = {}
    for k in kayitlar:
        a = k.get("surum") or "v1"
        sur[a] = sur.get(a, 0) + 1
    if len(sur) > 1:
        d = " · ".join(f"{a}:{c}" for a, c in sorted(sur.items()))
        L.append(f"⚠️ KARIŞIK SÜRÜM — {d}")
        L.append("   Aşağıdaki kalibrasyon iki farklı tahmin mekanizmasının")
        L.append("   KARIŞIMINI ölçer. Sürüm başına n≥100 olunca ayrı ayrı")
        L.append("   okunmalı; şu anki tek sayı bir ORTALAMA, kapı DEĞİL.")
        L.append("")
    elif sur:
        L.append(f"Sürüm: {next(iter(sur))} (tek sürüm — kalibrasyon temiz)")
        L.append("")
    tutan = sum(1 for k in kayitlar if k["sonuc"])
    L.append(f"Tutan: {tutan}/{len(kayitlar)} (%{100*tutan/len(kayitlar):.1f})")

    # ── GERCEKLESEN GETIRI + BELIRSIZLIK ──
    # NEDEN ARALIK SART (2026-08-23): rapor once yalniz NOKTA TAHMINI
    # yaziyordu ("-%15,4 · beklenen -%10,5"). Bu, "beklenenden kotu
    # gidiyoruz" sonucuna DAVET EDIYORDU; oysa standart hata %6,8 ve
    # beklenen deger aralik icinde -- fark ANLAMSIZ. ON_KAYIT zaten
    # "ROI KAPI DEGILDIR, n>=1500 gerekir" diyor; rapor bunu her
    # seferinde gostermeli ki yanlis okunmasin.
    import math
    import statistics as _st
    yatirim = len(kayitlar)
    donen = sum(k["oran"] for k in kayitlar if k["sonuc"])
    ger = [(k["oran"] - 1) if k["sonuc"] else -1.0 for k in kayitlar]
    ort = _st.mean(ger)
    se = (_st.pstdev(ger) / math.sqrt(len(ger))) if len(ger) > 1 else 0.0
    alt, ust = ort - 1.96 * se, ort + 1.96 * se
    bek = sum((k.get("tahmin_p") or k["nesine_p"]) * k["oran"] - 1
              for k in kayitlar) / yatirim
    L.append(f"Her seçime 1 birim: {donen:.2f} birim döndü → {100*ort:+.1f}%")
    L.append(f"  %95 aralık: {100*alt:+.1f}% … {100*ust:+.1f}%  "
             f"(standart hata %{100*se:.1f})")
    L.append(f"Beklenen (bot kendi tahminiyle): {100*bek:+.1f}%")
    if alt <= bek <= ust:
        L.append("  → Beklenen değer aralığın İÇİNDE: gerçekleşen getiri "
                 "beklenenden AYIRT EDİLEMİYOR.")
    else:
        L.append("  ⚠️ Beklenen değer aralığın DIŞINDA — bu incelenmeli.")
    L.append(f"  Bu sayıyla karar VERİLMEZ. Anlamlı bir ROI ayrımı için "
             f"n≥1500 gerekir; şu an {len(kayitlar)}.")
    L.append("")

    # kaynak bazli kalibrasyon
    L.append("KAYNAK KALİBRASYONU (tahmin → gerçekleşen)")
    for alan, ad in (("nesine_p", "Nesine"), ("model_p", "Modelimiz"),
                     ("dk_p", "DraftKings"), ("fd_p", "Piyasa(fd)"),
                     ("tahmin_p", "Botun kullandığı")):
        v = [k for k in kayitlar if isinstance(k.get(alan), (int, float))]
        if len(v) < 5:
            L.append(f"  {ad:<18} yetersiz veri ({len(v)})")
            continue
        tahmin = sum(k[alan] for k in v) / len(v)
        gercek = sum(1 for k in v if k["sonuc"]) / len(v)
        brier = sum((k[alan] - (1 if k["sonuc"] else 0)) ** 2 for k in v) / len(v)
        import math as _m
        se_k = _m.sqrt(max(gercek * (1 - gercek), 1e-9) / len(v))
        fark = tahmin - gercek
        kac_se = fark / se_k if se_k else 0.0
        isaret = " ⚠️ SAPMA" if abs(kac_se) > 2 else ""
        L.append(f"  {ad:<18} n={len(v):<4} tahmin %{tahmin*100:.0f} → "
                 f"gerçek %{gercek*100:.0f} ({fark*100:+.1f}p = "
                 f"{kac_se:+.1f} SE){isaret} · Brier {brier:.3f}")
    L.append("")
    # ── KOMUT KIRILIMI ──
    # GOSTERILIYOR AMA GURULTU ISARETIYLE: kucuk orneklemde bir komutun
    # "%92 tutuyor" gorunmesi normaldir. BtcTurk dersi: 81 kombinasyonun
    # ic-orneklem en iyisi +%255,7 idi, dis orneklemde -%68,6 oldu.
    from collections import defaultdict as _dd
    grup = _dd(list)
    for k in kayitlar:
        grup[k.get("kaynak") or "?"].append(k)
    if len(grup) > 1:
        L.append("")
        L.append("KOMUT KIRILIMI")
        for ad, v in sorted(grup.items(), key=lambda z: -len(z[1])):
            t = sum(1 for k in v if k["sonuc"])
            d = sum(k["oran"] for k in v if k["sonuc"])
            g = 100 * (d / len(v) - 1)
            not_ = "  ← n<30, GÜRÜLTÜ" if len(v) < 30 else ""
            L.append(f"  /{ad:<10} n={len(v):<4} tuttu %{100*t/len(v):.0f} · "
                     f"getiri {g:+.0f}%{not_}")
        L.append("")
    L.append("Brier düşük = daha isabetli. Rastgele tahmin ~0,25.")
    L.append("Tahmin ile gerçek arasındaki fark büyükse o kaynak sapmalı.")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    if "--coz" in sys.argv:
        c, k = coz()
        print(f"cozulen {c} · bekleyen {k}")
    print(rapor())
