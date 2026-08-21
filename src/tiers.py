"""/kupon: MAC ONU ve CANLI icin ayri ayri uc risk seviyesi.

Mekanizma v1.0 CEKIRDEGINE DOKUNMAZ: core/odds/coupon degismez, hash saglam
kalir. Buradaki secim mantigi ON_KAYIT'a tabi degildir (talep uzerine calisir,
gunluk push mekanizmasi ayridir).

Bot TAHMIN YAPMAZ. Istatistige, forma, sakatliga bakmaz. Yaptigi tek sey
Nesine'nin kendi oranlarindan komisyonu cikarip EN UCUZ secenekleri bulmak.
Her onerinin gerekcesi mesajda yazilidir.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import ampirik
import bulletin
import canli_durum
import canli_model as CM
import fotmob
import catalog
import coupon
import model as M
import odds as O
import trtime
from core import LIMITS

# Secenekleri ortusen marketler (her secenek 2 temel sonucu kapsar)
KAPSAM2 = {3, 8, 55}

# Canlida kullanilacak marketler -- adlari Nesine'nin kendi sozlugunden.
# 53/55/56 kimlikleri once davranistan cikarilmis, sonra katalogla DOGRULANMISTI.
# Canli MTID'ler mac oncesinden FARKLI bir uzayda (67 = canli 2,5 A/U,
# mac oncesinde 12). Katalogdan dogrulanmis adlar:
CANLI_KAPSAM = [
    53,   # Maç Sonucu
    55,   # Çifte Şans
    60,   # Handikaplı Maç Sonucu
    64,   # 2. Yarı Sonucu
    287,  # Karşılıklı Gol
    109,  # Tek/Çift
    600,  # 2. Yarı Karşılıklı Gol
    66, 67, 68,   # 1,5 / 2,5 / 3,5 Gol Alt/Üst
    61,   # 1. Yarı Sonucu
    70,   # 1. Yarı 1,5 Alt/Üst
    453,  # 1. Yarı Karşılıklı Gol
    86,   # Deplasman 1,5 Gol Alt/Üst
    257,  # Deplasman 0,5 Gol Alt/Üst
    320,  # Ev Sahibi 2,5 Gol Alt/Üst
    605,  # Kart Puanı Alt/Üst
    108,  # En Çok Gol Olacak Yarı
    217,  # Korner Alt/Üst          (mac oncesinde 216)
    219,  # 1. Yarı Korner Alt/Üst  (mac oncesinde 218)
    523,  # Korner Tek/Çift
    604,  # Hangi Takım Daha Çok Kart Puanı Alır?
]

CANLI_MAX_MARJ = 0.28      # canli marjlar olculdu %21-25; mac oncesi kapisi (%22) yariyi eliyordu
CANLI_MIN_BACAK_ORAN = 1.15   # 1.05 iken 1,09 gibi anlamsiz bacaklar kuruluyordu
MIN_KUPON_ORAN = 1.40      # bunun altinda kupon onerilmez ("risk almaya degmez")
HAREKET_ESIGI = 0.025      # oran oynamasi bu esigin altindaysa gurultu sayilir
#
# 1.40 TABANININ ARITMETIK SONUCU: marj %17 iken tek secimde
#   olasilik = (1 - 0.17) / oran  ->  oran 1.40 icin p = %59 TAVAN.
# "Az riskli" %70 isabet ISTEYEMEZ; bandlar buna gore ayarlandi.
SEVIYE_EMOJI = {"AZ RİSKLİ": "🟢", "ORTA RİSKLİ": "🟡", "YÜKSEK RİSKLİ": "🔴"}
KAYNAK_EMOJI = {"MAÇ ÖNÜ": "📅", "CANLI": "📡"}

RISK = [
    ("AZ RİSKLİ",     {"pre": 1, "canli": 2}, 0.50, 0.64, 0.45),
    ("ORTA RİSKLİ",   {"pre": 2, "canli": 2}, 0.55, 0.75, 0.30),
    ("YÜKSEK RİSKLİ", {"pre": 3, "canli": 3}, 0.33, 0.54, 0.12),
]
KAYNAK = [("MAÇ ÖNÜ", "pre"), ("CANLI", "canli")]

# /kuponiy /kuponau /kupon2oran /kupon2li komutlari icin suzgecler
FILTRELER = {
    "iy":    ("sadece İLK YARI bahisleri",
              lambda b: "1. Yarı" in b["market"] or "1.Y" in b["market"]),
    "au":    ("sadece ALT/ÜST bahisleri",
              lambda b: "Alt/Üst" in b["market"] or b["secenek"] in ("Alt", "Üst")),
    "oran2": ("sadece 2,00 ve üstü oranlar", lambda b: b["oran"] >= 2.0),
    "iki":   ("2 maçlık kuponlar", None),      # bacak sayisini zorlar
    # OLCULDU: korner/kart secenekleri havuzda 72 tane ve EN IYI sirasi 2.501;
    # ilk 500'e hic giremiyor, kupona HIC girmiyor. Cunku degerleri -%17,2
    # iken gol marketlerinin en iyisi -%14,6 -- Nesine korner/kart marketinden
    # daha cok pay aliyor. Ayri komut olmadan kullanici bunlari HIC goremez.
    "korner": ("sadece KORNER bahisleri", lambda b: "Korner" in b["market"]),
    "kart":   ("sadece KART bahisleri",   lambda b: "Kart" in b["market"]),
}
GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

ELEME: dict = {}

# Model verisi: gunluk is tarafindan hazirlanan dosyalar. /kupon ESPN'e GITMEZ.
_MODEL_ONBELLEK: dict = {}


_REFERANS: dict = {}


_ESLESME: dict = {}


def eslesme_yukle() -> dict:
    """data/eslesme.json — Nesine mac id -> ESPN takim id (gunluk is uretir)."""
    global _ESLESME
    if _ESLESME:
        return _ESLESME
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / "data" / "eslesme.json"
    try:
        _ESLESME = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        _ESLESME = {}
    return _ESLESME


def referans_yukle() -> dict:
    """data/referans.json — DraftKings olasiliklari (gunluk is uretir)."""
    global _REFERANS
    if _REFERANS:
        return _REFERANS
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / "data" / "referans.json"
    try:
        _REFERANS = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        _REFERANS = {}
    return _REFERANS


def referans_ekle(havuz: list) -> list:
    """Adaylara DraftKings olasiligini ve DK-referansli DEGERI ekle.

    deger = DK_olasiligi x Nesine_orani - 1
    Marjdan neden daha iyi: marj MARKET seviyesinde tek sayidir, ama kasa
    payi secenekler arasina esit dagitmaz. Olculdu: ayni market icinde
    secenekler arasi deger farki medyan 1,9 / maks 12,1 puan; marja gore
    siralama en degerli 20 secenegin 16'sini kaciriyordu.
    """
    ref = referans_yukle()
    for b in havuz:
        k = ref.get(str(b["id"]))
        if not k:
            continue
        plar = k.get(str(b["mtid"]))
        if not plar or b["idx"] >= len(plar):
            continue
        b["dk_p"] = plar[b["idx"]]
        b["dk_deger"] = plar[b["idx"]] * b["oran"] - 1.0
        b["dk_marj"] = k.get("dk_marj")
    return havuz


def model_yukle() -> dict:
    """data/istatistik.json + data/eslesme.json -> {nesine_mac_id: tahmin}."""
    global _MODEL_ONBELLEK
    if _MODEL_ONBELLEK:
        return _MODEL_ONBELLEK
    import json
    from pathlib import Path
    kok = Path(__file__).resolve().parent.parent / "data"
    try:
        ist = json.loads((kok / "istatistik.json").read_text(encoding="utf-8"))
        esl = json.loads((kok / "eslesme.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for mac_id, e in esl.items():
        a, b = ist.get(e.get("ev", "")), ist.get(e.get("dep", ""))
        if a and b:
            out[str(mac_id)] = {"tahmin": M.tahmin(a, b), "ev": a, "dep": b,
                                "espn": (e.get("espn_ev"), e.get("espn_dep"))}
    _MODEL_ONBELLEK = out
    return out


def _s(x: float, b: int = 2) -> str:
    return f"{x:,.{b}f}".replace(",", "~").replace(".", ",").replace("~", ".")


def _y(o: float, b: int = 1) -> str:
    return ("-" if o < 0 else "") + "%" + _s(abs(o) * 100, b)


def _aday(mtid, o, i, marj, p, e, bas, canli, sov):
    return {"mtid": mtid, "idx": i, "market": catalog.ad(mtid, sov),
            "secenek": catalog.secenek(mtid, i), "oran": o[i], "olasilik": p[i],
            "marj": marj, "mbs": e.get("mbs", 1), "ev": O.ev_tek(o[i], p[i]),
            "mac": f"{e['ev']} - {e['dep']}", "id": e["id"], "bas": bas,
            "canli": canli, "sov": sov, "lig_ad": e.get("lig_ad", "")}


def pre_adaylar(snap: dict, now: datetime | None = None) -> list[dict]:
    """Mac oncesi havuz: kapsamdaki HER marketin HER secenegi.

    Onceden yalnizca her marketin favorisi aday oluyordu; bu, "Ust 2,5" gibi
    yuksek oranli secenekleri tamamen disarida birakiyordu.
    """
    now = now or datetime.now(timezone.utc)
    alt = now + timedelta(hours=LIMITS["MIN_SAAT"])
    ust = now + timedelta(hours=LIMITS["MAX_SAAT"])
    out = []
    for e in snap.get("olay", []):
        if not e.get("ts"):
            continue
        bas = datetime.fromtimestamp(e["ts"] / 1000, tz=timezone.utc)
        if not (alt <= bas <= ust):
            continue
        for k, m in e.get("m", {}).items():
            mtid = int(k)
            if not catalog.kapsamda(mtid) or m.get("ms") != 1:
                continue
            o = m.get("o") or []
            if len(o) != catalog.secenek_sayisi(mtid) or any(
                    x is None or x <= 1.0 for x in o):
                continue
            kap = 2 if mtid in KAPSAM2 else 1
            marj, p = O.overround(o, kap), O.devig(o, kap)
            if marj is None or p is None or marj > LIMITS["MAX_OVERROUND"]:
                continue
            ev = {**e, "mbs": m.get("mbs") or 1}
            for i in range(len(o)):
                if LIMITS["MIN_ODD"] <= o[i] <= LIMITS["MAX_ODD"]:
                    out.append(_aday(mtid, o, i, marj, p, ev, bas, False, m.get("sov")))
    return out


_FOTMOB_ONBELLEK: list = []


def canli_state() -> dict:
    """Canli durumlar: TheSportsDB (genis kapsama) + Fotmob (KORNER/KART)."""
    global _FOTMOB_ONBELLEK
    _FOTMOB_ONBELLEK = fotmob.canli_maclar()
    return canli_durum.durumlar()


def canli_adaylar(now: datetime | None = None) -> list[dict]:
    """Canli havuz. Market adlari katalogdan; secenek sayisi katalogla dogrulanir."""
    now = now or datetime.now(timezone.utc)
    durum = canli_state()
    mo = model_yukle()
    ELEME.clear()
    ELEME.update(mac=0, marj=0, dusuk_oran=0, ornek=[])
    try:
        raw = bulletin.fetch_live()
    except Exception as e:
        print(f"[canli] alinamadi: {e}")
        return []
    out = []
    for e in raw.get("sg", {}).get("EA", []):
        if e.get("TYPE") != 1:
            continue
        ELEME["mac"] += 1
        ev = {"id": e.get("C"), "ev": e.get("HN"), "dep": e.get("AN"), "mbs": 1}
        # TheSportsDB isimle eslesir (ESPN id eslesmesi burada gecerli degil)
        d = canli_durum.esle(durum, e.get("HN") or "", e.get("AN") or "")
        # Fotmob: canli KORNER/KART + yedek skor/dakika
        fm = fotmob.esle(_FOTMOB_ONBELLEK, e.get("HN") or "", e.get("AN") or "")
        fm_ist = fotmob.istatistik(fm["id"]) if fm else None
        if fm and not d and fm.get("dakika") is not None:
            d = {"ev_skor": fm.get("ev_skor") or 0, "dep_skor": fm.get("dep_skor") or 0,
                 "dakika": fm["dakika"], "devre": None,
                 "guvenli": fm["dakika"] <= canli_durum.GUVENLI_DAKIKA}
        canli_t = None
        k = mo.get(str(e.get("C")))       # takim istatistikleri (skordan bagimsiz)
        if d and d.get("guvenli") and k:
            g = (k.get("tahmin") or {}).get("gol") or {}
            canli_t = CM.tahmin(g.get("ev_lambda", 1.2), g.get("dep_lambda", 1.0),
                                d["ev_skor"], d["dep_skor"], d["dakika"])
        for market in e.get("MA", []):
            mtid = market.get("MTID")
            if mtid not in CANLI_KAPSAM or market.get("MS") != 1:
                continue
            o = [x.get("O") for x in market.get("OCA", [])]
            if len(o) != catalog.secenek_sayisi(mtid) or any(
                    x is None or x <= 1.0 for x in o):
                continue
            kap = 2 if mtid in KAPSAM2 else 1
            marj, p = O.overround(o, kap), O.devig(o, kap)
            if marj is None or p is None:
                continue
            if marj > CANLI_MAX_MARJ:
                ELEME["marj"] += 1
                continue
            for i in range(len(o)):
                if o[i] < CANLI_MIN_BACAK_ORAN:
                    ELEME["dusuk_oran"] += 1
                    if len(ELEME["ornek"]) < 3:
                        ELEME["ornek"].append(f"{catalog.ad(mtid)} @{_s(o[i])}")
                    continue
                if o[i] > LIMITS["MAX_ODD"]:
                    continue
                aday = _aday(mtid, o, i, marj, p, ev, now, True, market.get("SOV"))
                if k:
                    # Takim gecmisi canli macta da gecerli: "son 20 macin
                    # kacinda ust oldu" sorusu skordan bagimsizdir.
                    aday["model_kaynak"] = k
                if d:
                    aday["canli_durum"] = d
                if fm_ist:
                    aday["canli_ist"] = fm_ist
                if canli_t:
                    mp = CM.olasilik(mtid, i, market.get("SOV"), canli_t)
                    if mp is not None:
                        aday["model_p"] = mp
                        aday["model_ev"] = mp * o[i] - 1.0
                        aday["canli_model"] = canli_t
                out.append(aday)
    return out


def tahmin_birlestir(havuz: list[dict]) -> list[dict]:
    """Her adaya EN KOTUMSER tahmini yaz ve secimde ONU kullan.

    NEDEN: bot bandi ve siralamayi Nesine'nin olasiligina gore yapiyordu;
    kendi modelini ve gecmis veriyi yalnizca EKRANDA gosteriyordu. Sonuc:
    model "%20" ve gecmis "%25" derken Nesine'nin "%36"sina bakip o bahsi
    oneriyordu (Fagiano-Tokyo Verdy 1,5 Alt vakasi). Artik elimizdeki en
    kotumser tahmin secimde de gecerli.

    Kotumser secilmesinin sebebi: bahiste hata pahalidir; iyimser tahmin
    seni kotu fiyata sokar, kotumser tahmin en fazla firsat kacirtir.
    """
    for b in havuz:
        kaynaklar = {"Nesine": b["olasilik"]}
        # Model ancak IKI takimda da yeterli mac varsa soz sahibi olur.
        # UYARI: model DOGRULANMIS DEGIL. Espanyol-Real Madrid'de Nesine %66,
        # model %38 dedi -- orada muhtemelen MODEL yaniliyor (kupa+lig karisik
        # veri). Kotumser kural iyi bahsi de eleyebilir; bu, sonuc takibi
        # kurulana kadar bilincli olarak kabul edilen bir maliyettir.
        k = b.get("model_kaynak") or {}
        yeterli = (min((k.get("ev") or {}).get("mac", 0),
                       (k.get("dep") or {}).get("mac", 0)) >= 8)
        if b.get("model_p") is not None and yeterli:
            kaynaklar["Modelimiz"] = b["model_p"]
        amp = ampirik_kaydi(b)
        if amp and amp["toplam"] >= 8:      # az orneklemli gecmise guvenme
            kaynaklar["Geçmiş"] = amp["oran"]
        if b.get("dk_p") is not None:
            kaynaklar["DraftKings"] = b["dk_p"]
        en_dusuk_ad = min(kaynaklar, key=kaynaklar.get)
        b["tahmin_p"] = kaynaklar[en_dusuk_ad]
        b["tahmin_kaynak"] = en_dusuk_ad
        b["tahmin_kaynaklar"] = kaynaklar
        b["deger"] = b["tahmin_p"] * b["oran"] - 1.0
    return havuz


def _sirala(havuz: list[dict]) -> list[dict]:
    """DK degeri varsa ONA gore (azalan), yoksa marja gore (artan) sirala.

    NEDEN DEGISTI: marj MARKET seviyesinde tek sayidir, ama kasa payi
    secenekler arasina esit dagitmaz. OLCULDU (254 secenek, DraftKings
    referansi): ayni market icinde secenekler arasi deger farki medyan
    1,9 / maks 12,1 puan; marja gore siralama en degerli 20 secenegin
    16'sini KACIRIYORDU (ort. -%13,9 yerine -%11,1 elde edilebilirdi).

    DK referansi olan secenekler once gelir: onlarin fiyati gercek bir dis
    piyasaya karsi olculmustur, digerleri yalnizca marj tahminidir.
    """
    havuz.sort(key=lambda x: (-(x.get("deger") if x.get("deger") is not None
                                else -round(x["marj"], 4)),
                              -x.get("tahmin_p", x["olasilik"])))
    for n, x in enumerate(havuz, 1):
        x["sira"] = n
    return havuz


def _kur(havuz, n, alt, ust, taban):
    """Bacaklari sec. MBS (Nesine'nin zorunlu kupon mac sayisi) BASTAN suzulur.

    Onceden en ucuz aday MBS=3 ise butun seviye iptal oluyordu; oysa havuzda
    MBS=1 olan baska uygun secenekler vardi. Simdi sigmayan MBS'li adaylar
    atlanip aramaya devam ediliyor.
    """
    gorulen, bacak, p_t, o_t = set(), [], 1.0, 1.0
    kesildi = False
    mbs_elendi = 0
    for x in havuz:
        p_ = x.get("tahmin_p", x["olasilik"])
        if not (alt <= p_ <= ust) or x["id"] in gorulen:
            continue
        if x.get("mbs", 1) > max(n, 1):
            mbs_elendi += 1
            continue
        if len(bacak) >= n and o_t >= MIN_KUPON_ORAN:
            break
        if len(bacak) >= n + 1:
            break
        if bacak and p_t * x.get("tahmin_p", x["olasilik"]) < taban:
            kesildi = True
            continue
        gorulen.add(x["id"])
        bacak.append(x)
        p_t *= x.get("tahmin_p", x["olasilik"])
        o_t *= x["oran"]
        if len(bacak) >= n and o_t >= MIN_KUPON_ORAN:
            break
    if not bacak:
        ek = (f"; {mbs_elendi} seçenek Nesine daha fazla maçlı kupon zorunlu "
              "kıldığı için elendi") if mbs_elendi else ""
        return [], (f"bu risk seviyesine uyan seçenek yok "
                    f"(tutma ihtimali %{alt*100:.0f}-%{ust*100:.0f} aranıyor{ek})")
    if o_t < MIN_KUPON_ORAN:
        return [], (f"bulunanların toplam oranı {_s(o_t)}, {_s(MIN_KUPON_ORAN)} "
                    "altında — bu kadar düşük ödeme için risk almaya değmez")
    if kesildi and len(bacak) < n:
        return bacak, (f"{n} maç yerine {len(bacak)} — bir maç daha eklemek tutma "
                       f"ihtimalini %{taban*100:.0f} altına düşürüyordu")
    if len(bacak) > n:
        return bacak, (f"{len(bacak)} maç — ödemeyi {_s(MIN_KUPON_ORAN)} üstüne "
                       "çıkarmak için bir seçenek eklendi")
    return bacak, ""


def uc_kupon(snap: dict, canli: bool = True, filtre: str | None = None):
    havuzlar = {"pre": _sirala(tahmin_birlestir(
                    model_ekle(referans_ekle(pre_adaylar(snap))))),
                "canli": _sirala(tahmin_birlestir(
                    referans_ekle(canli_adaylar()))) if canli else []}
    tam_havuz = {k: len(v) for k, v in havuzlar.items()}
    risk = RISK
    if filtre in FILTRELER:
        ad, kosul = FILTRELER[filtre]
        if kosul:
            for k in havuzlar:
                havuzlar[k] = [b for b in havuzlar[k] if kosul(b)]
        if filtre == "iki":
            risk = [(a, {"pre": 2, "canli": 2}, alt, ust, taban)
                    for a, _, alt, ust, taban in RISK]
    cikti, notlar = [], []
    if filtre in FILTRELER:
        notlar.append(f"SÜZGEÇ: {FILTRELER[filtre][0]}.")
    if canli and not havuzlar["canli"]:
        notlar.append(f"CANLI: {ELEME.get('mac',0)} maç tarandı, uygun seçenek çıkmadı.")
    for kaynak_ad, k in KAYNAK:
        if not havuzlar[k]:
            continue
        for ad, bacaklar, alt, ust, taban in risk:
            bacak, neden = _kur(havuzlar[k], bacaklar[k], alt, ust, taban)
            if not bacak:
                notlar.append(f"{kaynak_ad} · {ad}: {neden}.")
                continue
            if max(b["mbs"] for b in bacak) > len(bacak):
                notlar.append(f"{kaynak_ad} · {ad}: Nesine bu maçlar için daha "
                              "fazla maçlı kupon zorunlu kılıyor.")
                continue
            p = coupon.audit(bacak)
            p.update(seviye=ad, kaynak=kaynak_ad, neden=neden,
                     havuz=tam_havuz[k], suzgecli=len(havuzlar[k]),
                     bant=(alt, ust))
            cikti.append(p)
    if canli:
        if ELEME.get("dusuk_oran"):
            notlar.append(f"CANLI: {ELEME['dusuk_oran']} seçenek oranı çok düşük "
                          f"olduğu için elendi ({', '.join(ELEME['ornek'])}).")
        if ELEME.get("marj"):
            notlar.append(f"CANLI: {ELEME['marj']} market Nesine payı çok yüksek "
                          f"olduğu için elendi (%{CANLI_MAX_MARJ*100:.0f} üstü).")
    return cikti, notlar, deger_adaylari(havuzlar["pre"])


# ─────────────────────────── ANLAM VE GEREKÇE ───────────────────────────

def anlam(b: dict) -> str:
    """Bahsin duz Turkce karsiligi. Bilinmeyen markette UYDURMAZ, bos doner."""
    import math
    ad, s, sov = b["market"], b["secenek"], b.get("sov")
    yari = ("ilk yarıda " if ("1. Yarı" in ad or "1.Y" in ad)
            else "ikinci yarıda " if "2. Yarı" in ad else "maçta ")
    kim = ("ev sahibi " if ad.startswith("Ev Sahibi")
           else "deplasman " if ad.startswith("Deplasman") else "")

    if s in ("Alt", "Üst") and sov is not None:
        birim = ("korner" if "Korner" in ad else
                 "kart puanı" if "Kart" in ad else "gol")
        n = float(sov)
        if s == "Üst":
            return f"{yari}{kim}{birim} sayısı {math.floor(n)+1} veya daha fazla olur"
        return f"{yari}{kim}{birim} sayısı en fazla {math.floor(n)} olur"

    duz = {
        "MS 1": "ev sahibi kazanır", "MS X": "berabere biter",
        "MS 2": "deplasman kazanır",
        "1.Y 1": "ilk yarıyı ev sahibi önde bitirir",
        "1.Y X": "ilk yarı berabere biter",
        "1.Y 2": "ilk yarıyı deplasman önde bitirir",
        "2.Y 1": "ikinci yarıyı ev sahibi kazanır",
        "2.Y X": "ikinci yarı berabere biter",
        "2.Y 2": "ikinci yarıyı deplasman kazanır",
        "ÇŞ 1-X": "ev sahibi kazanır VEYA berabere biter",
        "ÇŞ 1-2": "berabere BİTMEZ",
        "ÇŞ X-2": "ev sahibi KAZANAMAZ",
        "1.Y 1-X": "ilk yarıda ev sahibi önde veya berabere",
        "1.Y 1-2": "ilk yarı berabere BİTMEZ",
        "1.Y X-2": "ilk yarıda ev sahibi önde OLAMAZ",
    }
    if s in ("Tek", "Çift"):
        # BIRIM MARKETE GORE degisir: "Korner Tek/Cift"te gol demek YANLIS
        birim = ("korner" if "Korner" in ad else
                 "kart" if "Kart" in ad else "gol")
        if s == "Tek":
            return f"{yari}toplam {birim} sayısı TEK olur (1, 3, 5…)"
        return f"{yari}toplam {birim} sayısı ÇİFT olur (0, 2, 4…)"
    if s in duz:
        return duz[s]
    if s == "Var":
        return f"{yari}iki takım da gol atar"
    if s == "Yok":
        return f"{yari}en az bir takım gol atamaz"
    if s.startswith("HMS") and sov is not None:
        h = float(sov)
        taraf = {"HMS 1": "ev sahibi", "HMS X": "beraberlik", "HMS 2": "deplasman"}[s]
        return f"{taraf}, {h:+g} gol handikapla önde bitirir"
    if "Gol" in ad and "Aralığı" in ad:
        return f"maçtaki toplam gol sayısı {s} arasında olur"
    if "Korner" in ad and "Aralığı" in ad:
        return f"maçtaki toplam korner sayısı {s} arasında olur"
    return ""


def hareket_satiri(b: dict) -> list:
    """Oranin arsivdeki gecmisi (varsa)."""
    if b.get("canli"):
        return []
    h = bulletin.hareket(b["id"], str(b["mtid"]), b["idx"])
    if not h or abs(h["degisim"]) < HAREKET_ESIGI:
        return []
    yon = "yükseldi" if h["degisim"] > 0 else "düştü"
    yorum = ("piyasa bu ihtimali artık daha DÜŞÜK görüyor"
             if h["degisim"] > 0 else "piyasa bu ihtimali artık daha YÜKSEK görüyor")
    return [f"📈 {h['saat']:g} saat önce {_s(h['eski'])} idi → şimdi "
            f"{_s(h['yeni'])} ({_y(abs(h['degisim']))} {yon})",
            f"         {yorum}"]


TERIMLER = [
    "📖 TERİMLER",
    "• TUTMA İHTİMALİ ile FİYAT DEĞERİ ayrı şeylerdir:",
    "  – tutma ihtimali: bahis kazanır mı",
    "  – fiyat değeri: bu fiyat adil mi (olasılık × oran − 1)",
    "  Yüksek olasılık = düşük oran olduğu için ikisi birbirini götürür.",
    "  Sıralama DEĞERE göredir. Ama değerler birbirine çok yakın:",
    "  aynı maçta 1. sıra -%14,7 iken 1900. sıra -%16,4 — arada 1,7 puan.",
    "  Yani 'sırası geride' kötü bahis demek DEĞİL, biraz daha pahalı demek.",
    "• SEÇİMDE hangi sayı kullanıldı: elimizdeki EN KÖTÜMSER tahmin.",
    "  Model veya geçmiş 'Nesine fazla iyimser' diyorsa o bahis sıralamada",
    "  aşağı düşer. Modelimiz DOĞRULANMIŞ DEĞİL — bazen o yanılıyordur.",
    "• Tutma ihtimali: bahsin gerçekleşme olasılığı. Bizim tahminimiz DEĞİL —",
    "  Nesine'nin kendi oranından payını çıkarınca kalan sayı.",
    "• Hak ettiği oran: o ihtimalin adil karşılığı (1 ÷ ihtimal). %60 ihtimal",
    "  1,67 oranı hak eder. Kimse pay almasaydı oran bu olurdu.",
    "• Nesine veriyor / eksik: aradaki fark Nesine'nin payıdır. KAYBIN ASIL",
    "  SEBEBİ BUDUR — tahmin gücü değil.",
    "• DRAFTKINGS: dünya piyasasından bağımsız bir fiyat. Payı ~%6,7,",
    "  Nesine'nin %17,7'sine karşı. Nesine'nin fiyatı ondan ne kadar sapmış,",
    "  onu ölçüyoruz. ÖLÇÜLDÜ: 254 seçeneğin 254'ü eksi değerli — yani",
    "  Nesine'de artı değerli bahis YOK. Bot en az kötüyü buluyor.",
    "• NEDEN SEÇİLDİ: bot maç tahmini YAPMAZ. Korner ortalamasına, forma,",
    "  sakatlığa, kadroya BAKMAZ. Tek yaptığı aynı riski en ucuz veren",
    "  seçeneği bulmaktır.",
    "  DİKKAT: düşük pay, kuponun TUTMA İHTİMALİNİ ARTIRMAZ. Sadece",
    "  tuttuğunda daha çok ödeme alırsın. Pay sonucu değil FİYATI etkiler.",
    "• NOT: oranın geçmişi (15 dakikada bir arşivleniyor).",
]


# ─────────────────────── MODEL DEĞER ADAYLARI ───────────────────────

def model_ekle(havuz: list) -> list:
    """Havuzdaki adaylara model olasiligini ve model EV'sini ekle."""
    mo = model_yukle()
    for b in havuz:
        k = mo.get(str(b["id"]))
        if not k:
            continue
        p = M.olasilik(b["mtid"], b["idx"], b.get("sov"), k["tahmin"])
        if p is None:
            continue
        b["model_p"] = p
        b["model_ev"] = p * b["oran"] - 1.0
        b["model_kaynak"] = k
    return havuz


def deger_adaylari(havuz: list, en_fazla: int = 4) -> list:
    """Modelin Nesine'den EN COK ayrildigi secenekler (model EV'ye gore)."""
    var = [b for b in havuz if b.get("model_ev") is not None]
    var.sort(key=lambda b: -b["model_ev"])
    secilen, gorulen = [], set()
    for b in var:
        if b["id"] in gorulen:
            continue
        gorulen.add(b["id"])
        secilen.append(b)
        if len(secilen) >= en_fazla:
            break
    return secilen


def ampirik_kaydi(b: dict):
    """Ampirik isabet kaydini dondur ve adayda sakla (guven puani da kullanir)."""
    if "_ampirik" in b:
        return b["_ampirik"]
    k = b.get("model_kaynak") or {}
    ev, dep = k.get("ev"), k.get("dep")
    r = ampirik.isabet(b["mtid"], b["idx"], b.get("sov"), ev, dep) if ev and dep else None
    b["_ampirik"] = r
    return r


def ampirik_satiri(b: dict) -> list:
    """Son maclarda bu bahis kac kez tuttu — ciplak gerceklesme orani."""
    k = b.get("model_kaynak") or {}
    ev, dep = k.get("ev"), k.get("dep")
    if not ev or not dep:
        return []
    r = ampirik.isabet(b["mtid"], b["idx"], b.get("sov"), ev, dep)
    if not r:
        return []
    return [f"    GEÇMİŞTE: bu iki takımın son {r['toplam']} maçının "
            f"{r['tutan']}'inde {r['metin']} oldu ({_y(r['oran'],0)})"]


def _model_kaynak_satiri(b: dict) -> str:
    """Modelin bu tahmini NEYE dayandirdigi."""
    k = b.get("model_kaynak") or {}
    ev, dep = k.get("ev") or {}, k.get("dep") or {}
    mt = b["mtid"]
    if mt in (216, 299):
        return (f"son {ev.get('mac','?')} maç korner ort.: "
                f"{_s(ev.get('korner') or 0,1)} + {_s(dep.get('korner') or 0,1)} "
                f"= {_s((ev.get('korner') or 0)+(dep.get('korner') or 0),1)} bekleniyor")
    if mt == 301:
        return (f"son {ev.get('mac','?')} maç kart ort.: "
                f"{_s(ev.get('sari') or 0,1)} + {_s(dep.get('sari') or 0,1)}")
    g = (k.get("tahmin") or {}).get("gol") or {}
    le, ld = g.get("ev_lambda") or 0, g.get("dep_lambda") or 0
    ev_ad, dep_ad = b["mac"].split(" - ")[0], b["mac"].split(" - ")[-1]
    return (f"{ev_ad} son {ev.get('mac','?')} maçta maç başı "
            f"{_s(ev.get('gol_at') or 0,1)} gol attı / {_s(ev.get('gol_ye') or 0,1)} yedi; "
            f"{dep_ad} {_s(dep.get('gol_at') or 0,1)} attı / "
            f"{_s(dep.get('gol_ye') or 0,1)} yedi. Buradan bu maçta ortalama "
            f"{_s(le,1)} + {_s(ld,1)} = {_s(le+ld,1)} GOL bekleniyor "
            f"(kesin skor tahmini DEĞİL, ortalama)")


def deger_bolumu(adaylar: list) -> list:
    if not adaylar:
        return []
    L = ["", "━━━ MODEL DEĞER ADAYLARI ━━━",
         "(kendi modelimizin Nesine'den en çok ayrıldığı seçenekler)"]
    for b in adaylar:
        basabas = 1.0 / b["oran"]
        d = trtime.yerel(b["bas"])
        a = anlam(b)
        L.append("")
        L.append(f"  {b['mac']}  [{d.strftime('%d.%m')} {GUN[d.weekday()]} {d.strftime('%H:%M')}]")
        L.append(f"    Bahis    : {b['market']} → {b['secenek']}")
        if a:
            L.append(f"    Yani     : {a}")
        L.append(f"    Nesine diyor    : {_y(b['olasilik'],0)}   (oran {_s(b['oran'])})")
        L.append(f"    BİZİM MODELİMİZ : {_y(b['model_p'],0)}")
        L.append(f"       dayanak: {_model_kaynak_satiri(b)}")
        L.append(f"    Başabaş için gereken: {_y(basabas,0)}")
        if b["model_ev"] > 0:
            L.append(f"    Model EV: {_y(b['model_ev'])}  → model başabaşı GEÇİYOR")
        else:
            L.append(f"    Model EV: {_y(b['model_ev'])}  → model Nesine'den iyimser "
                     "ama başabaşı GEÇMİYOR")
    L += ["",
          "UYARI: model EV artı olması KAR demek DEĞİLDİR. Model basittir —",
          "sakatlık, kadro, motivasyon, hakem, hava HESABA GİRMEZ. Piyasa",
          "genellikle haklıdır. Bu bölüm 'modelimiz nerede ayrışıyor' sorusunun",
          "cevabıdır, 'buradan para kazanılır' değil."]
    return L


def ilk_mac_satiri(b: dict) -> list:
    """Kupa/eleme ronvansiysa ilk macin skoru ve sahibi.

    Veri: takimin son maclari icinde RAKIBIYLE oynadigi mac aranir
    (data/istatistik.json icindeki `rakip` alani). Ek API cagrisi gerekmez.
    Son 60 gun siniri: ayni takimlar ligde de karsilasabilir.
    """
    k = b.get("model_kaynak") or {}
    ev, dep = k.get("ev"), k.get("dep")
    esl = eslesme_yukle().get(str(b["id"])) or {}
    dep_id = esl.get("dep")
    if not ev or not dep_id:
        return []
    from datetime import date
    bugun = date.today()
    aday = []
    for m in (ev.get("maclar") or []):
        if str(m.get("rakip") or "") != str(dep_id):
            continue
        try:
            y, ay, g = (int(x) for x in (m.get("t") or "").split("-"))
            fark = (bugun - date(y, ay, g)).days
        except Exception:
            continue
        if 0 <= fark <= 60:
            aday.append((fark, m))
    if not aday:
        return []
    fark, m = min(aday)
    yer = "kendi sahasında" if m.get("ev") else "deplasmanda"
    return [f"🔁 İLK MAÇ  {b['mac'].split(' - ')[0]} {yer}: "
            f"{m['at']}-{m['ye']}  ({fark} gün önce)"]


def guven_puani(b: dict) -> tuple:
    """(puan, gerekce_satirlari) — kaynaklar ne kadar hemfikir?

    BANKO = en yuksek olasilikli DEGIL, kaynaklarin en cok ortustugu secim.
    Puan = en dusuk kaynak olasiligi (muhafazakar) + kaynak sayisi bonusu.
    """
    kaynaklar = [("Nesine", b["olasilik"])]
    if b.get("model_p") is not None:
        kaynaklar.append(("Modelimiz", b["model_p"]))
    if b.get("dk_p") is not None:
        kaynaklar.append(("DraftKings", b["dk_p"]))
    amp = b.get("_ampirik")
    if amp:
        kaynaklar.append(("Geçmiş", amp["oran"]))
    en_dusuk = min(p for _, p in kaynaklar)
    # kaynaklar birbirine ne kadar yakin
    yayilim = max(p for _, p in kaynaklar) - en_dusuk
    puan = en_dusuk - yayilim * 0.5 + 0.02 * (len(kaynaklar) - 1)
    return puan, kaynaklar


def banko_bolumu(paketler: list) -> list:
    """Botun en cok guvendigi tek secim."""
    hepsi = [b for p in paketler for b in p["bacak"]]
    if not hepsi:
        return []
    for b in hepsi:
        b["_puan"], b["_kaynaklar"] = guven_puani(b)
    b = max(hepsi, key=lambda x: x["_puan"])
    L = ["", "═" * 30, "⭐ BANKOYA EN YAKIN", "═" * 30, "",
         f"  {b['mac']}",
         f"  {b.get('lig_ad','')}" if b.get("lig_ad") else "",
         f"  BAHİS   {b['market']} → {b['secenek']}"]
    a = anlam(b)
    if a:
        L.append(f"  YANİ    {a}")
    L.append(f"  ORAN    {_s(b['oran'])}")
    L.append("")
    L.append("  Neden bu: elimizdeki kaynaklar en çok burada aynı şeyi söylüyor")
    for ad, p in b["_kaynaklar"]:
        L.append(f"    {ad:<11} {_y(p,0)}")
    if len(b["_kaynaklar"]) == 1:
        L.append("    (tek kaynak var — bu maç dış veride yok, güven düşük)")
    L.append("")
    L.append("  BANKO GARANTI DEGILDIR. En yüksek olasılık değil, kaynakların")
    L.append("  en çok uyuştuğu seçimdir. Yine de tutmayabilir.")
    return [x for x in L if x is not None]


def format_message(paketler: list, notlar: list, deger: list | None = None) -> str:
    if not paketler:
        return "NESINE · /kupon\nUygun kupon bulunamadı.\n" + "\n".join(notlar)
    L = [f"🎫 NESINE · KUPON · {trtime.simdi().strftime('%d.%m %H:%M')}"]
    for kaynak_ad, _ in KAYNAK:
        grup = [p for p in paketler if p["kaynak"] == kaynak_ad]
        if not grup:
            continue

        for p in grup:
            L += ["", "━" * 30,
                  f"{KAYNAK_EMOJI.get(kaynak_ad,'')} {kaynak_ad} · "
                  f"{SEVIYE_EMOJI.get(p['seviye'],'')} {p['seviye']}  ({p['n']} maç)",
                  "━" * 30]
            if p.get("neden"):
                L.append(f"ℹ️ NOT: {p['neden']}")
            for b in p["bacak"]:
                if b.get("canli"):
                    cd = b.get("canli_durum")
                    ne_zaman = (f"CANLI · {cd['ev_skor']}-{cd['dep_skor']} · "
                                    f"{cd['dakika']}. dk"
                                    + (f" ({cd['devre']})" if cd.get("devre") else "")
                                if cd and cd.get("dakika") is not None
                                else "CANLI · skor/dakika bilgisi yok")
                else:
                    d = trtime.yerel(b["bas"])
                    ne_zaman = (f"{d.strftime('%d.%m')} {GUN[d.weekday()]} "
                                f"{d.strftime('%H:%M')}")
                L.append("")
                L.append(f"⚽ {b['mac']}")
                if b.get("lig_ad"):
                    L.append(f"🏆 {b['lig_ad']}")
                L.append(("📡 " if b.get("canli") else "🕐 ") + ne_zaman)
                L += ilk_mac_satiri(b)
                L.append("")
                L.append(f"🎯 BAHİS  {b['market']} → {b['secenek']}")
                a = anlam(b)
                if a:
                    L.append(f"   YANİ   {a}")
                adil = 1.0 / b["olasilik"]
                L.append(f"💰 ORAN   {_s(b['oran'])}   (adil {_s(adil)} — aradaki "
                         f"{_s(adil-b['oran'])} Nesine'nin payı)")
                L.append("")
                L.append(f"📊 Nesine      {_y(b['olasilik'],0):<5}")
                if b.get("model_p") is not None:
                    L.append(f"   Modelimiz   {_y(b['model_p'],0):<5} · "
                             f"{_model_kaynak_satiri(b)}")
                amp = ampirik_kaydi(b)
                if amp:
                    L.append(f"   Geçmiş      {_y(amp['oran'],0):<5} · son "
                             f"{amp['toplam']} maçta {amp['tutan']} kez {amp['metin']}")
                    if b.get("canli"):
                        # Gecmis oran TAM MACLARI sayar; canli macta bir kismi
                        # ZATEN OLMUS olabilir. Uyarmadan gostermek yanlis olur.
                        L.append("               ⚠️ bu oran TAM maçları sayar; "
                                 "bu maçta olanlar hesaba KATILMAZ")
                if b.get("dk_p") is not None:
                    L.append(f"   DraftKings  {_y(b['dk_p'],0):<5} · dış piyasaya göre "
                             f"değer {_y(b['dk_deger'])}")
                L += hareket_satiri(b)
                L.append("")
                nerede = ("dış piyasaya göre değeri" if b.get("dk_deger") is not None
                          else "Nesine payı en düşük")
                if b.get("tahmin_kaynak") and b["tahmin_kaynak"] != "Nesine":
                    L.append(f"   ⇒ Seçimde {_y(b['tahmin_p'],0)} kullanıldı "
                             f"({b['tahmin_kaynak']} — en kötümser tahmin)")
                # Bitisik f-string'lerde .replace() TUM metne uygulaniyordu ve
                # "-%17,5" -> "-%17.5" yapiyordu. Yalniz sayiya uygulanmali.
                # SIRA tum havuzda (suzgecten once); suzgecli sayiyla
                # karistirilmasin diye ikisi de yazilir.
                havuz_s = f"{p['havuz']:,}".replace(",", ".")
                sz = p.get("suzgecli")
                ek = (f" · süzgeçten geçen {sz}"
                      if sz is not None and sz != p["havuz"] else "")
                L.append(f"🔢 FİYAT DEĞERİ {_y(b.get('deger') or 0)} · "
                         f"tüm havuzda ({havuz_s}) {b['sira']}. sırada{ek}")
            stake = LIMITS["STAKE_TL"]
            doner = stake * p["toplam_oran"]
            L.append("")
            if p["n"] > 1:
                adil_k = 1.0 / p["isabet_olasiligi"]
                L.append("")
                L.append(f"🎟️ KUPON: tutma ihtimali {_y(p['isabet_olasiligi'])} → "
                         f"hak ettiği oran {_s(adil_k)}, Nesine {_s(p['toplam_oran'])}")
            L.append("")
            L.append(f"💵 {_s(stake,0)} TL → tutarsa {_s(doner)} TL "
                     f"(kâr {_s(doner-stake)} TL)")
            L.append(f"📉 Uzun vadede her {_s(stake,0)} TL'nin "
                     f"{_s(abs(p['ev'])*stake)} TL'si kaybolur ({_y(p['ev'])})")
    L += banko_bolumu(paketler)
    if deger:
        L += deger_bolumu(deger)
    if notlar:
        L.append("")
        L += [f"⚠️ {n}" for n in notlar]
    L += [""] + TERIMLER
    L += ["", "Yüksek risk daha İYİ bahis DEĞİL — sadece daha az olası, daha",
          "yüksek oranlı. Her seviyede uzun vade eksidir."]
    if any(p["kaynak"] == "CANLI" for p in paketler):
        L += ["", "📡 CANLI HAKKINDA",
              "• Oranlar saniyeler içinde değişir. Nesine'de gördüğün oran",
              "  buradakinden farklıysa bu hesap geçersizdir.",
              "• DraftKings satırı canlıda YOK: elimizdeki dış piyasa oranı maç",
              "  ÖNCESİNE ait, maç 1-0 olduktan sonra geçersiz. Bayat veriyi",
              "  göstermek yanlış güven verir.",
              "• Modelimiz canlıda ancak skor+dakika biliniyorsa çalışır.",
              "  'skor/dakika bilgisi yok' yazıyorsa sadece fiyata bakılmıştır.",
              "• GEÇMİŞ satırı canlıda da geçerlidir — takımların geçmişi",
              "  maç sırasında değişmez."]
    return "\n".join(L)


def parcala(msg: str, sinir: int = 3800) -> list:
    """Telegram 4096 karakter siniri; asan mesaj SESSIZCE dusuyor."""
    if len(msg) <= sinir:
        return [msg]
    parcalar, cur, n = [], [], 0
    for satir in msg.split("\n"):
        if n + len(satir) + 1 > sinir and cur:
            parcalar.append("\n".join(cur)); cur, n = [], 0
        cur.append(satir); n += len(satir) + 1
    if cur:
        parcalar.append("\n".join(cur))
    return parcalar


if __name__ == "__main__":
    import sys
    bulletin.run()
    s = bulletin.latest()
    filtre = None
    for a in sys.argv[1:]:
        if a.startswith("--filtre="):
            filtre = a.split("=", 1)[1]
    ps, notlar, deger = uc_kupon(s, canli="--canlisiz" not in sys.argv, filtre=filtre)
    msg = format_message(ps, notlar, deger)
    print(msg)
    print(f"\n[uzunluk: {len(msg)} karakter, {len(parcala(msg))} mesaj]")
    if "--dry" not in sys.argv:
        import notify
        for i, parca in enumerate(parcala(msg)):
            if not notify.send(parca):
                print(f"[HATA] {i+1}. parca gonderilemedi")
