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

import bulletin
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
CANLI_KAPSAM = [53, 55, 60, 64, 287, 109, 600]

CANLI_MAX_MARJ = 0.28      # canli marjlar olculdu %21-25; mac oncesi kapisi (%22) yariyi eliyordu
CANLI_MIN_BACAK_ORAN = 1.15   # 1.05 iken 1,09 gibi anlamsiz bacaklar kuruluyordu
MIN_KUPON_ORAN = 1.40      # bunun altinda kupon onerilmez ("risk almaya degmez")
HAREKET_ESIGI = 0.025      # oran oynamasi bu esigin altindaysa gurultu sayilir
#
# 1.40 TABANININ ARITMETIK SONUCU: marj %17 iken tek secimde
#   olasilik = (1 - 0.17) / oran  ->  oran 1.40 icin p = %59 TAVAN.
# "Az riskli" %70 isabet ISTEYEMEZ; bandlar buna gore ayarlandi.
RISK = [
    ("AZ RİSKLİ",     {"pre": 1, "canli": 2}, 0.50, 0.64, 0.45),
    ("ORTA RİSKLİ",   {"pre": 2, "canli": 2}, 0.55, 0.75, 0.30),
    ("YÜKSEK RİSKLİ", {"pre": 3, "canli": 3}, 0.33, 0.54, 0.12),
]
KAYNAK = [("MAÇ ÖNÜ", "pre"), ("CANLI", "canli")]
GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

ELEME: dict = {}

# Model verisi: gunluk is tarafindan hazirlanan dosyalar. /kupon ESPN'e GITMEZ.
_MODEL_ONBELLEK: dict = {}


_REFERANS: dict = {}


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
            "canli": canli, "sov": sov}


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


def canli_adaylar(now: datetime | None = None) -> list[dict]:
    """Canli havuz. Market adlari katalogdan; secenek sayisi katalogla dogrulanir."""
    now = now or datetime.now(timezone.utc)
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
                out.append(_aday(mtid, o, i, marj, p, ev, now, True, market.get("SOV")))
    return out


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
    havuz.sort(key=lambda x: (
        0 if x.get("dk_deger") is not None else 1,
        -x["dk_deger"] if x.get("dk_deger") is not None else round(x["marj"], 4),
        -x["olasilik"]))
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
        if not (alt <= x["olasilik"] <= ust) or x["id"] in gorulen:
            continue
        if x.get("mbs", 1) > max(n, 1):
            mbs_elendi += 1
            continue
        if len(bacak) >= n and o_t >= MIN_KUPON_ORAN:
            break
        if len(bacak) >= n + 1:
            break
        if bacak and p_t * x["olasilik"] < taban:
            kesildi = True
            continue
        gorulen.add(x["id"])
        bacak.append(x)
        p_t *= x["olasilik"]
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


def uc_kupon(snap: dict, canli: bool = True):
    havuzlar = {"pre": _sirala(model_ekle(referans_ekle(pre_adaylar(snap)))),
                "canli": _sirala(canli_adaylar()) if canli else []}
    cikti, notlar = [], []
    if canli and not havuzlar["canli"]:
        notlar.append(f"CANLI: {ELEME.get('mac',0)} maç tarandı, uygun seçenek çıkmadı.")
    for kaynak_ad, k in KAYNAK:
        if not havuzlar[k]:
            continue
        for ad, bacaklar, alt, ust, taban in RISK:
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
                     havuz=len(havuzlar[k]), bant=(alt, ust))
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
        "Tek": "toplam gol sayısı TEK olur (1, 3, 5…)",
        "Çift": "toplam gol sayısı ÇİFT olur (0, 2, 4…)",
    }
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


def gerekce(b: dict, p: dict) -> list:
    """Bu secenegin NEDEN secildigini anlatan satirlar."""
    alt, ust = p["bant"]
    if b.get("dk_deger") is not None:
        L = [f"    NEDEN SEÇİLDİ: {p['havuz']:,} seçenek arasında DIŞ PİYASAYA "
             f"göre değeri en iyi {b['sira']}.'sı".replace(",", ".")]
    else:
        L = [f"    NEDEN SEÇİLDİ: {p['havuz']:,} seçenek arasında Nesine'nin payı "
             f"en düşük {b['sira']}.'sı (bu maç dış piyasada YOK)".replace(",", ".")]
    L.append("       Bu seçeneği DAHA OLASI yapmaz — daha UCUZ yapar.")
    L.append(f"       Tutma ihtimali {_y(b['olasilik'],0)}; bu seviye "
             f"%{alt*100:.0f}-%{ust*100:.0f} arası arıyor.")
    return L


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
    return [f"    NOT: {h['saat']:g} saat önce {_s(h['eski'])} idi → şimdi "
            f"{_s(h['yeni'])} ({_y(abs(h['degisim']))} {yon})",
            f"         {yorum}"]


TERIMLER = [
    "━━━ TERİMLER ━━━",
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
    return (f"son {ev.get('mac','?')} maç golleri: ev {_s(ev.get('gol_at') or 0,2)} "
            f"attı/{_s(ev.get('gol_ye') or 0,2)} yedi · dep "
            f"{_s(dep.get('gol_at') or 0,2)}/{_s(dep.get('gol_ye') or 0,2)} "
            f"→ beklenen skor {_s(g.get('ev_lambda') or 0,2)}-{_s(g.get('dep_lambda') or 0,2)}")


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


def format_message(paketler: list, notlar: list, deger: list | None = None) -> str:
    if not paketler:
        return "NESINE · /kupon\nUygun kupon bulunamadı.\n" + "\n".join(notlar)
    L = [f"NESINE · KUPON · {trtime.simdi().strftime('%d.%m %H:%M')}"]
    for kaynak_ad, _ in KAYNAK:
        grup = [p for p in paketler if p["kaynak"] == kaynak_ad]
        if not grup:
            continue
        L += ["", f"━━━ {kaynak_ad} ━━━"]
        for p in grup:
            L += ["", f"▸ {p['seviye']}  ({p['n']} maç)"]
            if p.get("neden"):
                L.append(f"  NOT: {p['neden']}")
            for b in p["bacak"]:
                if b.get("canli"):
                    ne_zaman = "ŞU AN OYNANIYOR"
                else:
                    d = trtime.yerel(b["bas"])
                    ne_zaman = f"{d.strftime('%d.%m')} {GUN[d.weekday()]} {d.strftime('%H:%M')}"
                a = anlam(b)
                L.append("")
                L.append(f"  {b['mac']}")
                L.append(f"    Ne zaman : {ne_zaman}")
                L.append(f"    Bahis    : {b['market']} → {b['secenek']}")
                if a:
                    L.append(f"    Yani     : {a}")
                adil = 1.0 / b["olasilik"]
                L.append(f"    Tutma ihtimali {_y(b['olasilik'],0)} → hak ettiği oran {_s(adil)}")
                L.append(f"    Nesine veriyor {_s(b['oran'])}  ({_s(adil-b['oran'])} eksik)")
                if b.get("dk_deger") is not None:
                    L.append(f"    DRAFTKINGS diyor {_y(b['dk_p'],0)}"
                             + (f" (o piyasanın payı {_y(b['dk_marj'],1)})"
                                if b.get("dk_marj") is not None else ""))
                    L.append(f"    → DIŞ PİYASAYA GÖRE DEĞER: {_y(b['dk_deger'])}")
                L += gerekce(b, p)
                L += hareket_satiri(b)
            stake = LIMITS["STAKE_TL"]
            doner = stake * p["toplam_oran"]
            L.append("")
            if p["n"] > 1:
                adil_k = 1.0 / p["isabet_olasiligi"]
                L.append(f"    ── KUPON: tutma ihtimali {_y(p['isabet_olasiligi'])} → "
                         f"hak ettiği oran {_s(adil_k)}, Nesine {_s(p['toplam_oran'])}")
            L.append(f"    {_s(stake,0)} TL → tutarsa {_s(doner)} TL (kâr {_s(doner-stake)} TL)")
            L.append(f"    Uzun vadede her {_s(stake,0)} TL'nin {_s(abs(p['ev'])*stake)} TL'si "
                     f"kaybolur ({_y(p['ev'])})")
    if deger:
        L += deger_bolumu(deger)
    if notlar:
        L.append("")
        L += [f"! {n}" for n in notlar]
    L += [""] + TERIMLER
    L += ["", "Yüksek risk daha İYİ bahis DEĞİL — sadece daha az olası, daha",
          "yüksek oranlı. Her seviyede uzun vade eksidir."]
    if any(p["kaynak"] == "CANLI" for p in paketler):
        L += ["", "CANLI UYARISI: canlı oranlar saniyeler içinde değişir. Nesine'de",
              "gördüğün oran buradakinden farklıysa bu hesap geçersizdir."]
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
    ps, notlar, deger = uc_kupon(s, canli="--canlisiz" not in sys.argv)
    msg = format_message(ps, notlar, deger)
    print(msg)
    print(f"\n[uzunluk: {len(msg)} karakter, {len(parcala(msg))} mesaj]")
    if "--dry" not in sys.argv:
        import notify
        for i, parca in enumerate(parcala(msg)):
            if not notify.send(parca):
                print(f"[HATA] {i+1}. parca gonderilemedi")
