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
import iy_gecmis
import canli_durum
import canli_model as CM
import fotmob
import sofascore as SF
import catalog
import coupon
import havuz as HV
import fd as FD
import hacim
import maliyet
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
# Kupon komutlari YALNIZCA bugunun maclarini verir (kullanici istegi).
# Bugunden bu kadar AYRI mac cikmazsa pencere yarina uzatilir ve yazilir.
BUGUN_MIN_MAC = 15
# Gecmis (ampirik) verinin SECIME girmesi icin gereken en az mac sayisi.
# 5 macta gorulen %80'in guven araligi kabaca %45-%96 -- yani "cok gol
# oluyor" ile "normal" ayrimini bile yapamaz. Bu yuzden esik var.
# ONEMLI: bu esik GOSTERIME degil SECIME uygulanir; istatistik yine
# yazilir ama karara girip girmedigi ACIKCA belirtilir (bkz ampirik_satiri).
AMPIRIK_MIN_MAC = 8
# Suzgece ozel CANLI minimum bacak orani (kullanici istegi 2026-08-21).
# NEDEN: korner/kart marketi anlik canli maclarin yalnizca 1-2'sinde acik
# oluyor, dolayisiyla kupon TEK BACAK kuruluyor. Tek bacakta kupon orani =
# bacagin orani, yani MIN_KUPON_ORAN (1,40) altindaki her bacak "odeme cok
# dusuk" diye eleniyordu ve bolum bos donuyordu. Bu suzgeclerde canli
# bacak dogrudan 1,40 tabanina tabi tutulur.
SUZGEC_CANLI_MIN_ORAN = {"korner": 1.40, "kart": 1.40}

# /kuponihtimal — DEGERE degil TUTMA IHTIMALINE gore siralar.
# ARITMETIK DUVAR (olculdu 2026-08-23, 2724 secenek):
#   marj %17 iken  ihtimal x oran ≈ 0,83   ->   ihtimal = 0,83 / oran
#   oran tabani 1,20 -> en yuksek ihtimal %71,0
#              1,40 ->                     %60,8
#              1,45 ->                     %58,7
#              2,00 ->                     %42,5
# Yani "yuksek ihtimal" ve "yuksek oran" AYNI ANDA OLAMAZ; taban yukseldikce
# tavan duser. Kullanici tabani secer, tavani aritmetik belirler.
IHTIMAL_MIN_ORAN = 1.45

# ── BELIRSIZLIK CEZASI (2026-08-23) ──
# SORUN ARITMETIK, VARSAYIM DEGIL:
#     deger = ihtimal x oran - 1
# Ihtimal tahminindeki d puanlik hata degere d x ORAN olarak yansir.
# Olculen tahmin hatamiz ~5 puan (modelin Nesine'den medyan sapmasi):
#     oran 1,5 ->  7,5 puan gurultu
#     oran 4,0 -> 20,0 puan gurultu
# Ham degere gore siralamak bu yuzden en tepeye TAHMININ EN GURULTULU
# oldugu secenekleri cikariyordu -- konsulun "gurultunun kuyrugunu
# secmek" dedigi seyin ters yonu (secim yanliligi / winner's curse).
#
# ONEMLI — NE OLCULDU, NE OLCULMEDI:
# "Model uzun atislarda sistematik sisiriyor" HIPOTEZI TEST EDILDI VE
# DOGRULANMADI (315 secim, cozulmus sonuclar):
#     oran 1,0-1,6  model sapmasi -1,5p
#         1,6-2,2                 +5,6p   <- en buyuk sapma ORTA oranlarda
#         2,2-3,0                 -4,7p
#         3,0-4,5                 +1,4p
#         4,5+                   +15,0p   (n=10, anlamsiz)
# Yani ceza bir YANLILIK duzeltmesi DEGIL, BELIRSIZLIK duzeltmesidir.
# Tahmin yansiz olsa bile varyansi oranla buyudugu icin gereklidir.
#
# ETKI (olculdu, 2652 secenek): ilk 50'de oran>=3,00 olan 35 -> 12,
# ort. oran 4,25 -> 3,11, ort. ihtimal %28 -> %43, ort. marj %20,3 -> %19,4.
# Marjin da dusmesi bonus: daha ucuz secenekler one cikiyor.
# ── UYUM VE IHTIMAL TABANI (kullanici istegi 2026-08-23) ──
# "Bot Nesine ile ihtimal olarak UYUSTUGU, %50 ve uzeri kuponlari versin."
#
# 22 AGUSTOS OLCUMU (354 mac, 10.258 secim, gelecegi bilme ONLENDI --
# o gunun sonuclari takim istatistiklerinden cikarildi):
#   ayrisma bandi        n     model   Nesine   GERCEK
#   model COK dusuk    270    %27,9    %54,0    %42,2
#   model dusuk        934    %34,8    %48,5    %47,5
#   BENZER (|f|<0,10) 7834    %44,9    %44,9    %44,9   <- KUSURSUZ
#   model yuksek       942    %59,6    %45,8    %47,3
#   model COK yuksek   278    %68,8    %42,6    %53,6
# Ikisi hemfikirken kalibrasyon TAM tutuyor; ayristiklarinda gercek
# ORTADA kaliyor -- yani model bilgi tasiyor ama abartiyor, Nesine de
# eksik kaliyor. En guvenilir bolge UYUM bolgesi.
#
# MODEL YOKSA NE OLUR: ayrisma OLCULEMEZ, aday elenmez. Canlida
# adaylarin yalnizca %12'sinde model var (mac oncesi %75); model zorunlu
# kilinsa canli havuz 1098'den 34'e duserdi.
UYUM_MAX_FARK = 0.10      # model varsa Nesine'den bu kadar ayrisabilir
MIN_IHTIMAL = 0.50        # bunun altinda tutma ihtimali OLAN aday alinmaz

TAHMIN_HATASI = 0.05      # olculen medyan sapma (~5 puan)
BELIRSIZLIK_K = 1.0       # kac standart hata cezalandirilir (yargi)

# ── KAPSAM DISI: TEK/CIFT MARKETLERI (kullanici istegi 2026-08-23) ──
# Gol tek/cift, korner tek/cift, ilk yari tek/cift...
# NEDEN CIKARILDI:
#   1. Bilgi tasimiyor — bir macta toplam golun tek mi cift mi olacagi
#      pratikte yazi-tura. Modelimiz de bu marketi HIC modellemiyordu;
#      mesajda "bu market modellenmiyor" yaziyordu.
#   2. Havuzu isgal ediyordu: mac oncesi 264/2724 aday (%10),
#      CANLI 99/732 (%14). Canli kuponlarda bacaklarin cogu tek/cift
#      cikiyordu cunku olasiliklari %50 civari oldugu icin risk
#      bantlarina cok kolay giriyorlar.
#   3. Marji digerlerinden dusuk degil -- yani "ucuz" da degiller.
# Katalogdan cikarildi (16 tip), tekil MTID tahmini YAPILMADI.
# NOT: bu liste katalogdan turetildi ama IKI TANESI KACTI (49 mac oncesi,
# 109 canli) -- katalog taramasi eksik kaldi, ancak GERCEK HAVUZDA test
# edilince ortaya cikti. Bu yuzden asagida ISIM TABANLI EMNIYET de var:
# gelecekte yeni bir tek/cift MTID'i cikarsa liste guncellenmeden yakalanir.
TEK_CIFT = {49, 109, 299, 300, 308, 309, 310, 311, 324, 363, 370,
            418, 419, 450, 523, 639, 677, 680}


def _tek_cift_mi(mtid: int, sov=None) -> bool:
    """MTID listede mi, DEGILSE market adinda 'Tek/Cift' geciyor mu."""
    if mtid in TEK_CIFT:
        return True
    try:
        return "Tek/Çift" in str(catalog.ad(mtid, sov))
    except Exception:
        return False
#
# 1.40 TABANININ ARITMETIK SONUCU: marj %17 iken tek secimde
#   olasilik = (1 - 0.17) / oran  ->  oran 1.40 icin p = %59 TAVAN.
# "Az riskli" %70 isabet ISTEYEMEZ; bandlar buna gore ayarlandi.
SEVIYE_EMOJI = {"AZ RİSKLİ": "🟢", "ORTA RİSKLİ": "🟡", "YÜKSEK RİSKLİ": "🔴"}
KAYNAK_EMOJI = {"MAÇ ÖNÜ": "📅", "CANLI": "📡"}

RISK = [
    ("AZ RİSKLİ",     {"pre": 1, "canli": 2}, 0.50, 0.64, 0.45),
    ("ORTA RİSKLİ",   {"pre": 2, "canli": 2}, 0.55, 0.75, 0.30),
    # MIN_IHTIMAL=0,50 gelince eski 0,33-0,54 bandi 0,50-0,54'e sikisiyordu;
    # bant yukari genisletildi ki seviye anlamini korusun.
    ("YÜKSEK RİSKLİ", {"pre": 3, "canli": 3}, 0.50, 0.62, 0.12),
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
    # DEGER degil IHTIMAL siralamasi (kullanici istegi 2026-08-23)
    "ihtimal": (f"tutma ihtimali EN YÜKSEK olanlar (oran {IHTIMAL_MIN_ORAN} ve üstü)",
                lambda b: b["oran"] >= IHTIMAL_MIN_ORAN),
    "korner": ("sadece KORNER bahisleri", lambda b: "Korner" in b["market"]),
    "kart":   ("sadece KART bahisleri",   lambda b: "Kart" in b["market"]),
}
GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

ELEME: dict = {}
PENCERE: dict = {}

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
            "ev_ad": e.get("ev"), "dep_ad": e.get("dep"),
            "canli": canli, "sov": sov, "lig_ad": e.get("lig_ad", "")}


def _gun_sonu_utc(gun_ekle: int = 0) -> datetime:
    """Turkiye saatiyle (bugun+gun_ekle) gununun BITISI, UTC olarak."""
    tr = trtime.simdi() + timedelta(days=gun_ekle)
    bitis_tr = tr.replace(hour=23, minute=59, second=59, microsecond=0)
    return bitis_tr.astimezone(timezone.utc)


def pre_adaylar(snap: dict, now: datetime | None = None) -> list[dict]:
    """Mac oncesi havuz: kapsamdaki HER marketin HER secenegi.

    Onceden yalnizca her marketin favorisi aday oluyordu; bu, "Ust 2,5" gibi
    yuksek oranli secenekleri tamamen disarida birakiyordu.

    ZAMAN PENCERESI = BUGUN (2026-08-21'de degisti, kullanici bildirdi).
    Onceden muhurlu LIMITS["MAX_SAAT"]=48 kullaniliyordu, yani 2 gun
    sonrasinin maclari oneriliyordu. Kupon komutlari artik yalnizca
    TURKIYE SAATIYLE BUGUN baslayan maclari verir.

    GEC SAAT YEDEGI: gece gec calistirildiginda bugunden mac kalmayabilir.
    Havuzdaki AYRI MAC sayisi BUGUN_MIN_MAC altina duserse pencere yarin
    gun sonuna uzatilir ve bu mesaja YAZILIR (sessizce genisletilmez).

    NOT: muhurlu gunluk push (coupon.py) hala 48 saat kullanir -- orasi
    ON_KAYIT kapsaminda ve DEGISTIRILMEDI.
    """
    now = now or datetime.now(timezone.utc)
    alt = now + timedelta(hours=LIMITS["MIN_SAAT"])

    def topla(ust: datetime) -> list:
        out = []
        for e in snap.get("olay", []):
            if not e.get("ts"):
                continue
            bas = datetime.fromtimestamp(e["ts"] / 1000, tz=timezone.utc)
            if not (alt <= bas <= ust):
                continue
            for k, m in e.get("m", {}).items():
                mtid = int(k)
                if _tek_cift_mi(mtid, m.get("sov")):
                    continue
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
                        out.append(_aday(mtid, o, i, marj, p, ev, bas, False,
                                         m.get("sov")))
        return out

    out = topla(_gun_sonu_utc(0))
    PENCERE.clear()
    PENCERE.update({"gun": "bugün", "mac": len({b["id"] for b in out})})
    if PENCERE["mac"] < BUGUN_MIN_MAC:
        genis = topla(_gun_sonu_utc(1))
        PENCERE.update({"gun": "bugün+yarın", "mac": len({b["id"] for b in genis}),
                        "uzatildi": True, "bugun_mac": PENCERE["mac"]})
        out = genis
    return out


_FOTMOB_ONBELLEK: list = []
_SOFA_INDEKS: dict = {}
_SOFA_KOPRU: dict = {}
_SEZON_ONB: dict = {}


def sezon_yukle() -> dict:
    """Kopruden GECEN SEZON takim ortalamalari (sade ad -> istatistik).

    Sezon basinda Fotmob'da korner/kart verisi HIC olusmuyor (Serie A'da
    iki takimin da ligde 1 maci vardi). Mac'teki toplayici Sofascore'dan
    gecen sezon ortalamalarini cekip kopruye birakiyor; burada okunur.
    """
    global _SEZON_ONB
    if _SEZON_ONB:
        return _SEZON_ONB
    import json as _j
    import urllib.request as _u
    try:
        req = _u.Request(SF.KOPRU + "?k=takim",
                         headers={"User-Agent": "nesine-bot/1.0"})
        with _u.urlopen(req, timeout=15) as r:
            d = _j.loads(r.read())
        _SEZON_ONB = d.get("takim") or {}
        print(f"[sezon-kopru] {len(_SEZON_ONB)} takim")
    except Exception as e:
        print(f"[sezon-kopru] okunamadi: {e}")
        _SEZON_ONB = {}
    return _SEZON_ONB
# Canli korner/kart marketleri — Sofascore istatistigi YALNIZCA bu marketleri
# sunan maclar icin cekilir (mac basina 1 HTTP; hepsini cekmek israf olurdu).
KORNER_KART_CANLI = {217, 219, 523, 604, 605}


def canli_state() -> dict:
    """Canli durumlar: TheSportsDB (genis kapsama) + Fotmob (KORNER/KART)."""
    global _FOTMOB_ONBELLEK, _SOFA_INDEKS
    _FOTMOB_ONBELLEK = fotmob.canli_maclar()
    # Sofascore: skor/dakika YEDEGI + canli KORNER/KART (donem ayrimli).
    # Kurulu degilse veya ulasilamazsa bos kalir, akis bozulmaz.
    # ONCE KOPRU: Mac'teki toplayici Sofascore'u cekip Worker KV'ye
    # birakiyor ve ESLESTIRMEYI de yapmis oluyor (Nesine mac id'sine gore).
    # Actions Sofascore'a erisemedigi icin ASIL YOL BUDUR.
    global _SOFA_KOPRU
    _SOFA_KOPRU = (SF.kopru() or {}).get("mac") or {}
    # Kopru bossa (Mac kapali) DOGRUDAN dene -- yerel calistirmada calisir,
    # Actions'ta ilk 403'te kendini kapatir.
    if not _SOFA_KOPRU:
        try:
            _SOFA_INDEKS = SF.indeks()
        except Exception as e:
            print(f"[sofascore] indeks kurulamadi: {e}")
            _SOFA_INDEKS = {}
    else:
        _SOFA_INDEKS = {}
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
        # KOPRU verisi: Nesine mac id'siyle DOGRUDAN eslesir, isim
        # eslestirmesine gerek yok (Mac tarafinda zaten yapildi).
        sk = _SOFA_KOPRU.get(str(e.get("C"))) if _SOFA_KOPRU else None
        # Bu macta korner/kart marketi acik mi? Istatistik SADECE onlar icin
        # gerekli. OLCULDU: 49 canli macin 34'u Fotmob'a esleşiyor ama
        # yalnizca 5'inde korner/kart marketi acik -- yani her kosuda
        # 29 HTTP cagrisi BOSA gidiyordu.
        ist_gerek = bool({m.get("MTID") for m in (e.get("MA") or [])}
                         & KORNER_KART_CANLI)

        # ── SKOR/DAKIKA: TheSportsDB -> kopru -> Fotmob ──
        if not d and sk and sk.get("dakika") is not None:
            d = {"ev_skor": sk["skor"][0], "dep_skor": sk["skor"][1],
                 "dakika": sk["dakika"], "devre": sk.get("devre"),
                 "guvenli": sk["dakika"] <= canli_durum.GUVENLI_DAKIKA}
        if not d and fm and fm.get("dakika") is not None:
            d = {"ev_skor": fm.get("ev_skor") or 0, "dep_skor": fm.get("dep_skor") or 0,
                 "dakika": fm["dakika"], "devre": None,
                 "guvenli": fm["dakika"] <= canli_durum.GUVENLI_DAKIKA}
        # Kopru de Fotmob de yoksa DOGRUDAN Sofascore (yalnizca yerelde calisir)
        if not d and _SOFA_INDEKS:
            sf = SF.esle(_SOFA_INDEKS, e.get("HN") or "", e.get("AN") or "")
            if sf:
                sd = SF.durum(sf)
                if sd.get("dakika") is not None and sd.get("ev_skor") is not None:
                    d = {"ev_skor": sd["ev_skor"], "dep_skor": sd["dep_skor"],
                         "dakika": sd["dakika"], "devre": sd.get("devre"),
                         "guvenli": sd["dakika"] <= canli_durum.GUVENLI_DAKIKA}

        # ── KORNER/KART ISTATISTIGI: once KOPRU (bedava), sonra Fotmob ──
        fm_ist = None
        if ist_gerek:
            if sk and sk.get("ist"):
                fm_ist = dict(sk["ist"])
                fm_ist["kaynak"] = "Sofascore"
            elif fm:
                fm_ist = fotmob.istatistik(fm["id"])

        canli_t = None
        k = mo.get(str(e.get("C")))       # takim istatistikleri (skordan bagimsiz)
        # FOTMOB YOKSA SOFASCORE TAKIM ISTATISTIGI (kopruden).
        # Fotmob bazi ligleri HIC kapsamiyor (Paraguay, Misir 2. Lig,
        # Litvanya). O maclarda model uretilemiyor ve mesajda
        # "bu maç dış istatistik verisinde bulunamadı" yaziyordu -- oysa
        # CANLI veri geliyordu. Eksik olan takim SEZON ortalamalariydi.
        # Sofascore'unki Fotmob'unkinden IYI: `matches` alani var, yani
        # bolen dogru (Fotmob'da fikstur penceresinden sayiliyordu ve
        # 23,5 korner/mac gibi imkansiz degerler cikiyordu).
        if not k and sk and sk.get("takim"):
            t_ev, t_dep = sk["takim"].get("ev"), sk["takim"].get("dep")
            if t_ev and t_dep:
                try:
                    k = {"ev": t_ev, "dep": t_dep,
                         "tahmin": M.tahmin(t_ev, t_dep), "kaynak": "Sofascore"}
                except Exception as ex:
                    print(f"[sofa-model] uretilemedi: {ex}")
        if d and d.get("guvenli") and k:
            g = (k.get("tahmin") or {}).get("gol") or {}
            canli_t = CM.tahmin(g.get("ev_lambda", 1.2), g.get("dep_lambda", 1.0),
                                d["ev_skor"], d["dep_skor"], d["dakika"])
        for market in e.get("MA", []):
            mtid = market.get("MTID")
            if _tek_cift_mi(mtid, market.get("SOV")):
                continue
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
    """Her adaya kaynaklarin HAVUZLANMIS tahminini yaz ve secimde onu kullan.

    2026-08-21 DEGISIKLIGI (konsul bulgusu): burada eskiden kaynaklarin
    MINIMUMU aliniyordu. Olculdu ki bu kural, secenek olasiliklari toplamini
    1'den 0,93'e dusuruyordu -- yani ~6,9 PUANLIK SISTEMATIK ASAGI YANLILIK.
    Bunun bedeli sadece kacan firsat degildi: ON_KAYIT'taki tek basarisizlik
    kapisi (R1) KALIBRASYON'dur, ve yanli bir tahminle kalibrasyon
    olculemez. Yani eski kural botun kendi sinavini imkansiz kiliyordu.

    Yerine ters-varyans agirlikli LOGIT HAVUZU geldi (src/havuz.py). Ayni
    testte havuzun sapmasi 0,06 puan. Ihtiyat kayboldu mu? Hayir -- gizli
    olmaktan cikip GORUNUR bir kalem oldu: havuz.GUVENLIK_PAYI.

    NE DEGISMEDI: modele hala Nesine kadar guvenilmiyor. Eskiden bu "modeli
    yalnizca asagi yonde dinle" kuraliydi; simdi modele DUSUK AGIRLIK
    (Nesine'nin yarisi) verilerek ifade ediliyor. Ayni inanc, ama olasiligi
    bozmadan.

    Iki ayri sayi uretilir:
      tahmin_p : YANSIZ havuz tahmini -> ekranda ve kalibrasyonda kullanilir
      secim_p  : tahmin_p - sabit ihtiyat -> yalnizca SECIM KAPISINDA
    """
    for b in havuz:
        kaynaklar = {"Nesine": b["olasilik"]}
        # Model ancak IKI takimda da yeterli mac varsa soz sahibi olur.
        k = b.get("model_kaynak") or {}
        yeterli = (min((k.get("ev") or {}).get("mac", 0),
                       (k.get("dep") or {}).get("mac", 0)) >= 8)
        if b.get("model_p") is not None and yeterli:
            kaynaklar["Modelimiz"] = b["model_p"]
        amp = ampirik_kaydi(b)
        if amp and amp["toplam"] >= AMPIRIK_MIN_MAC:   # az orneklemli gecmise guvenme
            kaynaklar["Geçmiş"] = amp["oran"]
        if b.get("dk_p") is not None:
            kaynaklar["DraftKings"] = b["dk_p"]
        # IKINCI FIYAT (football-data.co.uk). Nesine'nin 1X2 marji ~%18-21;
        # tek fiyata bakip "deger" demek kendi hatasini olcmemektir.
        # Kapsam ~22 lig / bultenin ~%15'i. YOKSA GIZLENMEZ: sonuc (neden
        # dahil) b["fd"]'ye yazilir ve mesajda kullaniciya bildirilir.
        f = FD.secenek_p(b.get("ev_ad") or "", b.get("dep_ad") or "",
                         b.get("mtid"), b.get("secenek") or "")
        b["fd"] = f
        ek_ag = {}
        if f.get("var"):
            kaynaklar["Piyasa(fd)"] = f["p"]
            ek_ag["Piyasa(fd)"] = FD.agirlik(f["marj"])

        h = HV.birlestir(kaynaklar, ek_ag)
        if h is None:
            b["tahmin_p"] = b["olasilik"]
            b["secim_p"] = b["olasilik"]
            b["tahmin_kaynaklar"] = kaynaklar
            b["tahmin_kaynak"] = "Nesine"
            b["ayrisma"] = 0.0
        else:
            b["tahmin_p"] = h["tahmin_p"]
            b["secim_p"] = h["secim_p"]
            b["tahmin_kaynaklar"] = kaynaklar
            b["tahmin_kaynak"] = ("havuz" if len(kaynaklar) > 1 else "Nesine")
            b["ayrisma"] = h["ayrisma"]
            b["agirlik"] = h["agirlik"]
        # Deger DURUST tahminle hesaplanir (ihtiyat payi burada DUSULMEZ --
        # ihtiyat bir risk kapisidir, fiyat degerlendirmesi degil).
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
    def _siralama_degeri(x):
        """Belirsizlik cezasi DUSULMUS deger. Gosterimde ham deger kalir."""
        d = x.get("deger")
        if d is None:
            return -round(x["marj"], 4) - 9.0     # DK'sizlar en sona
        return d - BELIRSIZLIK_K * TAHMIN_HATASI * x["oran"]

    havuz.sort(key=lambda x: (-_siralama_degeri(x),
                              -x.get("tahmin_p", x["olasilik"])))
    for n, x in enumerate(havuz, 1):
        x["sira"] = n
    return havuz


def _kur(havuz, n, alt, ust, taban):
    """Bacaklari sec. MBS (Nesine'nin zorunlu kupon mac sayisi) BASTAN suzulur.

    Onceden en ucuz aday MBS=3 ise butun seviye iptal oluyordu; oysa havuzda
    MBS=1 olan baska uygun secenekler vardi. Simdi sigmayan MBS'li adaylar
    atlanip aramaya devam ediliyor.

    IKI AYRI OLASILIK (2026-08-21):
      secim_p  -> BANT ve TABAN kapilarinda (ihtiyat payi dusulmus)
      tahmin_p -> kullaniciya gosterilen isabet olasiligi (yansiz)
    Boylece ihtiyat secimi sikilastirir ama ekrandaki sayiyi YALAN yapmaz.

    AZ BACAK TERCIHI (konsul, 5/5 hemfikir): marj carpimsaldir --
    1 bacak -%17,4 · 2 bacak -%31,8 · 3 bacak -%43,6. Bu yuzden hedef orana
    ULASIR ULASMAZ durulur; bacak "daha cok kazanmak icin" EKLENMEZ.
    """
    gorulen, bacak, p_t, o_t = set(), [], 1.0, 1.0
    ps_t = 1.0
    kesildi = False
    mbs_elendi = 0
    for x in havuz:
        p_ham = x.get("tahmin_p", x["olasilik"])          # yansiz tahmin
        p_ = x.get("secim_p", p_ham)                      # ihtiyat dusulmus
        # IHTIYAT YALNIZ ALT SINIRA UYGULANIR.
        #
        # HATA (2026-08-21 ikinci konsul turu): pay iki tarafa birden
        # uygulaniyordu -> bant DARALMIYOR, 3 puan YUKARI KAYIYORDU:
        #   bant %50-%64 · pay 3 puan
        #     gercek %51 -> elenir (dogru, ihtiyat)
        #     gercek %67 -> GIRERDI  (YANLIS: bant disi, favoriye kayma)
        # Sonuc: daha kisa oranlar -> 1,40 tabanina ulasmak icin daha cok
        # bacak -> carpimsal marj artiyordu. Yani "ihtiyat" maliyeti
        # YUKSELTIYORDU. Ust sinir artik YANSIZ tahminle karsilastirilir.
        if not (alt <= p_ and p_ham <= ust) or x["id"] in gorulen:
            continue
        if x.get("mbs", 1) > max(n, 1):
            mbs_elendi += 1
            continue
        if len(bacak) >= n and o_t >= MIN_KUPON_ORAN:
            break
        if len(bacak) >= n + 1:
            break
        if bacak and ps_t * p_ < taban:
            kesildi = True
            continue
        gorulen.add(x["id"])
        bacak.append(x)
        ps_t *= p_
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
    # ── UYUM + IHTIMAL TABANI (tum komutlarda) ──
    eski_boy = {k: len(v) for k, v in havuzlar.items()}
    for k in havuzlar:
        havuzlar[k] = [
            b for b in havuzlar[k]
            # IKISI DE tabani gecmeli: havuzlanmis tahmin VE Nesine'nin
            # kendi sayisi. Yalnizca havuza bakinca "Nesine %49 · model %55"
            # gibi adaylar geciyordu; kullanici "Nesine ile uyustugu %50 ve
            # uzeri" dedi, dolayisiyla Nesine'nin de tabani gecmesi gerekir.
            if b.get("tahmin_p", b["olasilik"]) >= MIN_IHTIMAL
            and b["olasilik"] >= MIN_IHTIMAL
            and (b.get("model_p") is None
                 or abs(b["model_p"] - b["olasilik"]) <= UYUM_MAX_FARK)]
    tam_havuz = {k: len(v) for k, v in havuzlar.items()}
    risk = RISK
    if filtre in FILTRELER:
        ad, kosul = FILTRELER[filtre]
        if kosul:
            for k in havuzlar:
                havuzlar[k] = [b for b in havuzlar[k] if kosul(b)]
        # Suzgece ozel canli oran tabani (korner/kart tek bacak kuruluyor)
        _min_o = SUZGEC_CANLI_MIN_ORAN.get(filtre)
        if _min_o:
            once = len(havuzlar["canli"])
            havuzlar["canli"] = [b for b in havuzlar["canli"]
                                 if b["oran"] >= _min_o]
            ELEME["suzgec_oran"] = once - len(havuzlar["canli"])
            ELEME["suzgec_min"] = _min_o
        if filtre == "iki":
            risk = [(a, {"pre": 2, "canli": 2}, alt, ust, taban)
                    for a, _, alt, ust, taban in RISK]
    cikti, notlar = [], []
    notlar.append(
        f"SEÇİM KURALI: hem Nesine hem bizim tahminimiz %{MIN_IHTIMAL*100:.0f} ve üzeri, "
        f"VE modelin Nesine'den {UYUM_MAX_FARK*100:.0f} puandan fazla ayrışmadığı "
        f"bahisler. (Ölçüldü 22.08, 10.258 seçim: ikisi hemfikirken kalibrasyon "
        f"tam tutuyor — %44,9 dedi %44,9 oldu; ayrıştıklarında ikisi de yanılıyor.) "
        f"Havuz {eski_boy.get('pre',0)}+{eski_boy.get('canli',0)} → "
        f"{tam_havuz.get('pre',0)}+{tam_havuz.get('canli',0)} adaya indi.")
    if filtre in FILTRELER:
        notlar.append(f"SÜZGEÇ: {FILTRELER[filtre][0]}.")
    if filtre == "ihtimal":
        notlar.append(
            f"İHTİMAL MODU: sıralama fiyat değerine değil TUTMA İHTİMALİNE göre. "
            f"Ölçüldü — normal moda kıyasla 3 maçlık kupon %4 yerine %23 tutuyor, "
            f"ama beklenen getiri %2 daha kötü (-%41,7 → -%43,8). Marj aynı. "
            f"Daha sık kazanırsın, daha az ödeme alırsın.")
        notlar.append(
            f"ARİTMETİK TAVAN: marj %17 iken ihtimal = 0,83 ÷ oran. "
            f"Oran {IHTIMAL_MIN_ORAN} tabanında en yüksek ihtimal ~%58. "
            f"Daha yüksek ihtimal istiyorsan oran tabanı düşmeli.")
        if ELEME.get("suzgec_oran"):
            notlar.append(f"CANLI: {ELEME['suzgec_oran']} seçenek oranı "
                          f"{_s(ELEME['suzgec_min'])} altında olduğu için elendi "
                          "(tek bacaklı kuponda ödeme çok düşük kalıyor).")
    if PENCERE.get("uzatildi"):
        notlar.append(f"ZAMAN: bugün sadece {PENCERE.get('bugun_mac',0)} maç "
                      f"kaldığı için pencere YARINA uzatıldı "
                      f"({PENCERE.get('mac',0)} maç).")

    # BACAK SAYISINI HAVUZDAKI MAC SAYISINA GORE KIS.
    #
    # NEDEN (2026-08-21, kullanici bildirdi -- /kuponkorner canli vermiyordu):
    # _kur mac basina TEK bacak alir (gorulen kumesi x["id"] = MAC id).
    # CANLI seviyeler 2-3 bacak istiyordu, yani 2-3 AYRI canli mac gerekiyordu.
    # Ama anlik canli mac sayisi ~12 ve korner marketi bunlarin yalnizca
    # 1-2'sinde aciliyor -- olculdu: 14 canli korner adayinin tamami TEK
    # macin market setiydi (Korner Tek/Cift + 10,5/11,5/12,5/13,5 A/U +
    # 1.Y 6,5/7,5 A/U, her biri 2 secenek). Yani sart hicbir zaman
    # saglanamiyordu ve bolum SESSIZCE bos donuyordu.
    #
    # Cozum: havuzdaki AYRI MAC sayisi istenen bacaktan azsa bacak sayisi
    # ona indirilir. Az bacak zaten UCUZDUR (1 bacak -%17,4 · 3 bacak
    # -%43,6), yani bu kisitlama maliyeti dusurur.
    # IHTIMAL MODU: siralamayi DEGERden IHTIMALe cevir.
    # Normalde siralama fiyat degerine gore (en ucuz risk). Burada
    # kullanici bilerek baska bir sey istiyor: en cok tutacak bahis.
    # DIKKAT: bu beklenen degeri IYILESTIRMEZ, risk profilini degistirir --
    # daha sik tutar, daha az oder. Marj ayni kalir.
    if filtre == "ihtimal":
        for k in havuzlar:
            havuzlar[k] = sorted(havuzlar[k],
                                 key=lambda x: -x.get("tahmin_p", x["olasilik"]))
            for n, x in enumerate(havuzlar[k], 1):
                x["sira"] = n

    mac_sayisi = {k: len({b["id"] for b in v}) for k, v in havuzlar.items()}

    def _bacak(k: str, istenen: int) -> tuple[int, tuple | None]:
        """(bacak_sayisi, kisitlama_bilgisi). Bilgi SEVIYEYE OZELDIR.

        Onceden kisitlama bilgisi tum seviyelerin paylastigi bir sozlukte
        tutuluyordu ve bir kez yazilinca SILINMIYORDU; kisitlanmamis
        seviyeler de "N mac istenmisti" notunu miras aliyordu. Artik
        her seviye kendi bilgisini alir.
        """
        m = mac_sayisi.get(k, 0)
        if m and m < istenen:
            return max(1, m), (istenen, m)
        return istenen, None
    if canli and not havuzlar["canli"]:
        notlar.append(f"CANLI: {ELEME.get('mac',0)} maç tarandı, uygun seçenek çıkmadı.")
    for kaynak_ad, k in KAYNAK:
        if not havuzlar[k]:
            continue
        for ad, bacaklar, alt, ust, taban in risk:
            n_bacak, kisit = _bacak(k, bacaklar[k])
            bacak, neden = _kur(havuzlar[k], n_bacak, alt, ust, taban)
            if not bacak:
                notlar.append(f"{kaynak_ad} · {ad}: {neden}.")
                continue
            if kisit and not neden:
                ist, var = kisit
                neden = (f"{ist} maç istenmişti ama süzgece uyan sadece {var} "
                         f"maç var — {len(bacak)} maçlık kuruldu "
                         "(az bacak daha ucuz)")
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
    return cikti, notlar, deger_adaylari(havuzlar["pre"]), havuzlar["pre"]


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
    "• SEÇİMDE hangi sayı kullanıldı: kaynakların AĞIRLIKLI ORTALAMASI",
    "  (Nesine · modelimiz · geçmiş · DraftKings · Piyasa). Ağırlıklar",
    "  piyasa payına göre: DraftKings payı %6,7 olduğu için Nesine'nin ~3",
    "  katı ağırlıkta,",
    "  modelimiz Nesine'nin yarısı kadar (isabetli olduğu KANITLANMADI).",
    "  21.08'e kadar burada kaynakların EN DÜŞÜĞÜ alınıyordu. Ölçüldü:",
    "  o kural seçenek olasılıklarının toplamını 1'den 0,93'e düşürüyordu —",
    "  yani her tahmine ~6,9 puan gizli aşağı sapma ekliyordu. Ağırlıklı",
    "  ortalamada bu sapma 0,06 puan. Tahmin artık yansız; ihtiyat ayrı ve",
    "  sabit bir kalem (seçim kapısında 3 puan düşülür).",
    "• Modelimiz DOĞRULANMIŞ DEĞİL. 40 maçta ölçüldü: Nesine'den daha",
    "  isabetli olduğu gösterilemedi (fark -0,003, %95 aralık sıfırı",
    "  içeriyor). Bu yüzden düşük ağırlık taşıyor.",
    "• Tutma ihtimali: bahsin gerçekleşme olasılığı. Bizim tahminimiz DEĞİL —",
    "  Nesine'nin kendi oranından payını çıkarınca kalan sayı.",
    "• Hak ettiği oran: o ihtimalin adil karşılığı (1 ÷ ihtimal). %60 ihtimal",
    "  1,67 oranı hak eder. Kimse pay almasaydı oran bu olurdu.",
    "• Nesine veriyor / eksik: aradaki fark Nesine'nin payıdır. KAYBIN ASIL",
    "  SEBEBİ BUDUR — tahmin gücü değil.",
    "• PİYASA (ikinci fiyat): football-data.co.uk üzerinden Betfair borsası",
    "  ya da bukmeker ortalaması. 31.08 ölçümü: aynı 41 maçta Nesine'nin",
    "  payı %17,8, bu kaynağın payı %8,1 (borsa varken %4,9) — yani 2-4 kat",
    "  keskin. İki kaynağın paydan arındırılmış olasılıkları arasında",
    "  SİSTEMATİK kayma yok (-0,00 puan); ayrılık medyan 1,0 puan, seçimlerin",
    "  %12'sinde 3 puandan fazla. YANİ: Nesine fiyatı keskin piyasaya çok",
    "  yakın; ayrışma nadir ve küçük.",
    "  KAPSAMA DÜRÜSTÇE: bu kaynak ~22 ligi kapsıyor, bültenin yaklaşık",
    "  %15'i. Kalan maçlarda ikinci fiyat YOKTUR ve o maçlarda tek kaynak",
    "  Nesine'dir. Her bacakta 'Piyasa' satırı VARSA sayıyı, YOKSA nedenini",
    "  yazar — yokluğu gizlenmez.",
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
    """Havuzdaki adaylara model olasiligini ve model EV'sini ekle.

    SEZON BASI TAMAMLAMA (2026-08-22): Fotmob'da korner/kart verisi
    olusmadiysa (lig yeni basladi) kopruden gelen GECEN SEZON ortalamasi
    kullanilir. Gol modeli Fotmob'un guncel verisiyle kalir -- yalnizca
    EKSIK alanlar tamamlanir, saglam veri EZILMEZ.
    """
    mo = model_yukle()
    sez = sezon_yukle()
    import stats as _ST
    for b in havuz:
        k = mo.get(str(b["id"]))
        if k and sez and (k.get("ev") or {}).get("korner") is None:
            a2 = sez.get(_ST.sadelestir(b.get("ev_ad") or ""))
            d2 = sez.get(_ST.sadelestir(b.get("dep_ad") or ""))
            if a2 and d2:
                ev2 = {**k["ev"], **{x: y for x, y in a2.items()
                                     if x in ("korner", "korner_yenilen", "sari",
                                              "kirmizi", "korner_n", "kart_n")}}
                dep2 = {**k["dep"], **{x: y for x, y in d2.items()
                                       if x in ("korner", "korner_yenilen", "sari",
                                                "kirmizi", "korner_n", "kart_n")}}
                k = {**k, "ev": ev2, "dep": dep2,
                     "tahmin": M.tahmin(ev2, dep2),
                     "sezon_kaynak": a2.get("sezon") or "gecen"}
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


IY_MARKETLER = {7, 61, 8, 14, 209, 70, 15, 452, 453, 450, 218, 219}


def _iy_veri(b: dict):
    """Bahsin iki takiminin ILK YARI gecmisi (gerektiginde cekilir)."""
    if "_iy" in b:
        return b["_iy"]
    k = b.get("model_kaynak") or {}
    ev, dep = k.get("ev"), k.get("dep")
    esl = eslesme_yukle().get(str(b["id"])) or {}
    if not ev or not dep or not esl:
        b["_iy"] = (None, None)
        return b["_iy"]
    b["_iy"] = (iy_gecmis.takim_iy(ev, esl.get("ev", "")),
                iy_gecmis.takim_iy(dep, esl.get("dep", "")))
    return b["_iy"]


def canli_ist_satiri(b: dict) -> list:
    """CANLI macta SU ANA KADAR olan istatistikler.

    2026-08-21: bu veri `canli_ist` alaninda ATANIYOR ama HICBIR YERDE
    OKUNMUYORDU -- yani Fotmob'dan mac basina bir HTTP cagrisiyla cekilip
    COPE ATILIYORDU. Kullanici "canlida cogu macin verilerini cekemiyor"
    dedigi sey buydu: veri vardi, gosterilmiyordu.

    Korner/kart bahsinde bu satir bahsin KENDISIYLE ilgilidir: "13,5 korner
    ustu" oynarken 78. dakikada 6 korner olmasi belirleyicidir.
    """
    ist = b.get("canli_ist")
    if not ist:
        return []
    tam = ist.get("tam") or {}
    ilk = ist.get("ilk_yari") or {}
    if not tam:
        return []
    kaynak = ist.get("kaynak") or "Fotmob"
    L = [f"📊 ŞU ANA KADAR ({kaynak})"]

    def cift(d, anahtar):
        v = d.get(anahtar)
        if not v or len(v) != 2 or None in v:
            return None
        return int(v[0]), int(v[1])

    korner = cift(tam, "korner")
    if korner:
        satir = f"   Korner   {korner[0]}-{korner[1]} (toplam {sum(korner)})"
        ik = cift(ilk, "korner")
        if ik:
            satir += f" · ilk yarı {sum(ik)}"
        L.append(satir)
    sari = cift(tam, "sari")
    if sari:
        kirmizi = cift(tam, "kirmizi")
        satir = f"   Sarı     {sari[0]}-{sari[1]} (toplam {sum(sari)})"
        if kirmizi and sum(kirmizi):
            satir += f" · kırmızı {sum(kirmizi)}"
        L.append(satir)
    top = cift(tam, "topla_oynama")
    if top:
        L.append(f"   Topla oynama  %{top[0]} - %{top[1]}")
    sut = cift(tam, "isabetli_sut")
    if sut:
        L.append(f"   İsabetli şut  {sut[0]}-{sut[1]}")
    return L if len(L) > 1 else []


def iy_satirlari(b: dict) -> list:
    """Ilk yari bahsinde HEM ilk yari HEM mac geneli bilgisi.

    Kullanici istedi: "ilk yari diyorsa ilk yari VE mac sonu bilgisini de
    gormek isterim" -- cunku kornerin/golun ne kadarinin ilk yarida oldugu
    baglam veriyor.
    """
    if b["mtid"] not in IY_MARKETLER:
        return []
    iy_ev, iy_dep = _iy_veri(b)
    if not iy_ev and not iy_dep:
        return []
    L = []
    r = ampirik.isabet_iy(b["mtid"], b["idx"], b.get("sov"), iy_ev, iy_dep)
    if r:
        L.append(f"   İlk yarı    {_y(r['oran'],0):<5} · son {r['toplam']} maçta "
                 f"{r['tutan']} kez {r['metin']}")
    ma = (iy_ev or []) + (iy_dep or [])
    k = b.get("model_kaynak") or {}
    ev, dep = k.get("ev") or {}, k.get("dep") or {}
    korner_mu = b["mtid"] in (218, 219)
    if korner_mu:
        iyk = [m["iy_korner"] for m in ma if m.get("iy_korner") is not None]
        tam = (ev.get("korner") or 0) + (dep.get("korner") or 0)
        if iyk and tam:
            o = sum(iyk) / len(iyk)
            L.append(f"   Maç geneli  ort. {_s(tam,1)} korner · ilk yarıda "
                     f"{_s(o,1)} ({_y(o/tam,0)}'si ilk yarıda)")
    else:
        iyg = [m["at"] + m["ye"] for m in ma]
        tam = ((ev.get("gol_at") or 0) + (ev.get("gol_ye") or 0)
               + (dep.get("gol_at") or 0) + (dep.get("gol_ye") or 0)) / 2
        if iyg and tam:
            o = sum(iyg) / len(iyg)
            L.append(f"   Maç geneli  ort. {_s(tam,1)} gol · ilk yarıda "
                     f"{_s(o,1)} ({_y(o/tam,0)}'si ilk yarıda)")
    return L


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
    """Son maclarda bu bahis kac kez tuttu + KARARA GIRDI MI.

    2026-08-21 DUZELTMESI (kullanici bildirdi): bu satir esik olmadan
    yaziliyordu, ama SECIM tarafinda 8 mac esigi vardi. Sonuc: bot
    "son 5 macin 1'inde 2,5 alt oldu (%20)" yazip 2,5 ALT oneriyordu.
    Okuyan haklı olarak celiski goruyordu -- oysa o istatistik karara
    HIC GIRMEMISTI (5 < 8), sadece ekrana basiliyordu.

    Ornek (Standard Liege - RAAL La Louviere, 2,5 Alt/Ust):
      Nesine %54 Alt · DraftKings %54 Alt -> havuz %54, Alt secildi
      Gecmis %80 Ust ama 5 mac -> SECIME GIRMEDI
    Yani secim piyasayi takip etti; hata muhakemede degil ANLATIMDAYDI.

    Bilgi gizlenmiyor -- gosteriliyor ama etiketleniyor.
    """
    k = b.get("model_kaynak") or {}
    ev, dep = k.get("ev"), k.get("dep")
    if not ev or not dep:
        return []
    r = ampirik.isabet(b["mtid"], b["idx"], b.get("sov"), ev, dep)
    if not r:
        return []
    L = [f"    GEÇMİŞTE: bu iki takımın son {r['toplam']} maçının "
         f"{r['tutan']}'inde {r['metin']} oldu ({_y(r['oran'],0)})"]
    if r["toplam"] < AMPIRIK_MIN_MAC:
        L.append(f"      ⚠️ Bu istatistik SEÇİME GİRMEDİ — {r['toplam']} maç "
                 f"çok az (en az {AMPIRIK_MIN_MAC} gerekiyor). {r['toplam']} maçta")
        L.append(f"      görülen bir oran tesadüf olabilir; seçim Nesine ve")
        L.append(f"      DraftKings fiyatlarına göre yapıldı.")
    else:
        L.append(f"      ✓ Bu istatistik seçime girdi (ağırlık "
                 f"{HV.AGIRLIK.get('Geçmiş', 0.25)}, en düşük ağırlıklı kaynak).")
    return L


def _model_kaynak_satiri(b: dict) -> str:
    """Modelin bu tahmini NEYE dayandirdigi."""
    k = b.get("model_kaynak") or {}
    ev, dep = k.get("ev") or {}, k.get("dep") or {}
    mt = b["mtid"]
    # TUM korner ve kart MTID'leri (mac oncesi + canli + ilk yari).
    # Onceden yalnizca 216/299 ve 301 taniniyor, digerleri GOL aciklamasina
    # dusuyordu -- korner bahsinde "gol atti/yedi" yaziyordu.
    KORNER = {216, 217, 218, 219, 299, 523, 338, 339, 340, 341, 220, 221,
              222, 223, 798, 799, 601, 602, 662, 663, 561, 454, 562}
    KART = {301, 605, 604, 603, 800}
    if mt in KORNER:
        e_k, d_k = ev.get("korner"), dep.get("korner")
        if e_k is None or d_k is None:
            # SEBEBI AYIR: "veri yok" ile "sezon yeni basladi" ayri seylerdir.
            # Olculdu (Genoa-Napoli, 2026-08-22): Fotmob'da iki takimin da
            # PRIMARY LIGDE oynanmis 1 maci var (Serie A yeni basladi) ve
            # korner/kart/xG alanlari HIC YOK. Sofascore da veremiyor --
            # veri henuz hicbir kaynakta OLUSMADI. Bu bir eslesme hatasi
            # DEGIL; oyle sunmak kullaniciyi yanlis yere baktiriyordu.
            lm = min(ev.get("lig_mac") or 0, dep.get("lig_mac") or 0)
            if lm and lm < 3:
                return (f"ligde daha {lm} maç oynandı — korner ortalaması "
                        "çıkarmak için çok erken (en az 3 maç gerekiyor). "
                        "Gol modeli çalışıyor, korner modeli YOK")
            return (f"son {ev.get('mac') or '?'} maçta korner verisi eksik "
                    "— bu tahmin gol istatistiğine dayanmıyor, model yok")
        yari = " (ilk yarı için ~%45'i)" if mt in (218, 219, 340, 341, 662, 663,
                                                   799, 222, 223) else ""
        return (f"son maçlarda korner ort.: {_s(e_k,1)} + {_s(d_k,1)} "
                f"= {_s(e_k + d_k,1)} korner bekleniyor{yari}")
    if mt in KART:
        e_s, d_s = ev.get("sari"), dep.get("sari")
        if e_s is None or d_s is None:
            lm = min(ev.get("lig_mac") or 0, dep.get("lig_mac") or 0)
            if lm and lm < 3:
                return (f"ligde daha {lm} maç oynandı — kart ortalaması "
                        "çıkarmak için çok erken (en az 3 maç gerekiyor)")
            return f"son {ev.get('mac') or '?'} maçta kart verisi eksik"
        return (f"son maçlarda kart ort.: {_s(e_s,1)} + {_s(d_s,1)} "
                f"= {_s(e_s + d_s,1)} kart bekleniyor")
    g = (k.get("tahmin") or {}).get("gol") or {}
    le, ld = g.get("ev_lambda") or 0, g.get("dep_lambda") or 0
    ev_ad, dep_ad = b["mac"].split(" - ")[0], b["mac"].split(" - ")[-1]
    # HAZIRLIK MACI UYARISI (2026-08-22, kullanici bildirdi):
    # "Le Mans son 3 maçta 2,3 gol attı" deniyordu ama o UC MAC DA
    # HAZIRLIK MACIYDI (Club Friendlies, 22-01 Temmuz). Kullanici Nesine'de
    # resmi maclara bakinca tutmadi -- haklı olarak.
    # Sezon basinda resmi mac bulunamayinca devreye giren yedek kural
    # (`hazirlik_dahil`) sessizce calisiyordu. OLCULDU: onbellekteki 1593
    # takimin 305'i (%19) boyle hesaplaniyor; bugunun havuzunda 13 mac
    # etkileniyor (Espanyol-Real Madrid, Toulouse-Lyon, Genoa-Napoli dahil).
    # Hazirlik maci zayif bir gostergedir (kadro deneme, tempo dusuk);
    # rakam kullanilmaya devam eder ama ARTIK SOYLENIR.
    def _etiket(t, ad):
        n = t.get("mac", "?")
        if t.get("hazirlik_dahil"):
            return f"{ad} son {n} HAZIRLIK maçında"
        return f"{ad} son {n} maçta"
    temel = (f"{_etiket(ev, ev_ad)} maç başı "
             f"{_s(ev.get('gol_at') or 0,1)} gol attı / "
             f"{_s(ev.get('gol_ye') or 0,1)} yedi; "
             f"{_etiket(dep, dep_ad).replace(' son ', ' son ')} "
             f"{_s(dep.get('gol_at') or 0,1)} attı / "
             f"{_s(dep.get('gol_ye') or 0,1)} yedi")
    if ev.get("hazirlik_dahil") or dep.get("hazirlik_dahil"):
        temel += (". ⚠️ Sezon yeni başladığı için RESMİ maç yok, hazırlık "
                  "maçları kullanıldı — kadrolar deneme amaçlı olduğu için "
                  "bu rakamlar zayıf gösterge")
    # CANLI BAHISTE MAC ONCESI SAYIYI TEK BASINA YAZMA.
    #
    # HATA (2026-08-22, kullanici bildirdi): "Canberra macinda 4,4 gol
    # bekliyorum deyip 3,5 ALT oneriyor". Model DOGRUYDU, mesaj yaniltiyordu:
    # 4,4 MAC ONCESI beklentiydi; mac 54. dakikada 1-0 idi ve 3,5 ustu icin
    # kalan 36 dakikada 3 GOL daha gerekiyordu. Canli modelin 3,5 Alt
    # tahmini %74 -- yani secim tutarliydi. Ama satirda ne skor ne dakika
    # vardi, okuyan haklı olarak celiski goruyordu.
    cd = b.get("canli_durum") if b.get("canli") else None
    if cd and cd.get("dakika") is not None:
        atilan = (cd.get("ev_skor") or 0) + (cd.get("dep_skor") or 0)
        kalan = max(0, 90 - int(cd["dakika"]))
        beklenen_kalan = (le + ld) * kalan / 90.0
        return (temel + f". Maç ÖNCESİ beklenti {_s(le+ld,1)} goldü — ama maç "
                f"{cd['dakika']}. dakikada {atilan} golle gidiyor. "
                f"Kalan {kalan} dakikada ~{_s(beklenen_kalan,1)} gol daha "
                f"bekleniyor, yani toplam ~{_s(atilan + beklenen_kalan,1)}. "
                "Seçim BU hesaba göre yapıldı, maç öncesi sayıya göre değil")
    return (temel + f". Buradan bu maçta ortalama "
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

    2026-08-21: burada da min() kullaniliyordu (bkz. havuz.py). Artik puan
    HAVUZLANMIS tahminden baslar ve ayrisma kadar cezalandirilir. Fark: eski
    haliyle "tek kaynagi cok dusuk olan" secim banko cikabiliyordu; simdi
    yalnizca kaynaklarin GERCEKTEN ortustugu secim one cikar.
    """
    kaynaklar = [("Nesine", b["olasilik"])]
    if b.get("model_p") is not None:
        kaynaklar.append(("Modelimiz", b["model_p"]))
    if b.get("dk_p") is not None:
        kaynaklar.append(("DraftKings", b["dk_p"]))
    amp = b.get("_ampirik")
    if amp:
        kaynaklar.append(("Geçmiş", amp["oran"]))
    ek_ag = {}
    f = b.get("fd") or {}
    if f.get("var"):
        kaynaklar.append(("Piyasa(fd)", f["p"]))
        ek_ag["Piyasa(fd)"] = FD.agirlik(f["marj"])
    h = HV.birlestir(dict(kaynaklar), ek_ag)
    if h is None:
        return b["olasilik"], kaynaklar
    puan = h["tahmin_p"] - h["ayrisma"] * 0.5 + 0.02 * (len(kaynaklar) - 1)
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


def format_message(paketler: list, notlar: list, deger: list | None = None,
                   pre_havuz: list | None = None) -> str:
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
                L += canli_ist_satiri(b)
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
                    # SECIME GIRDI MI: model de en az 8 mac istiyor
                    # (bkz. tahmin_birlestir). Ampirik satirdaki ayni hata
                    # burada da vardi: gosterimde esik YOKTU, secimde VARDI.
                    mk = b.get("model_kaynak") or {}
                    n_mac = min((mk.get("ev") or {}).get("mac", 0),
                                (mk.get("dep") or {}).get("mac", 0))
                    girdi = n_mac >= AMPIRIK_MIN_MAC
                    L.append(f"   Modelimiz   {_y(b['model_p'],0):<5} · "
                             f"{_model_kaynak_satiri(b)}")
                    if not girdi:
                        L.append(f"      ⚠️ Model SEÇİME GİRMEDİ — takımların "
                                 f"maç sayısı yetersiz ({n_mac}, en az "
                                 f"{AMPIRIK_MIN_MAC} gerekiyor).")
                else:
                    # Model YOKSA sebebini yaz. Sessiz bosluk, kullanicinin
                    # "neden model yok" diye tahmin yurutmesine yol aciyordu.
                    kk = b.get("model_kaynak") or {}
                    ev_, dep_ = kk.get("ev"), kk.get("dep")
                    KOR = {216, 217, 218, 219, 299, 523, 338, 220}
                    KRT = {301, 605, 604}
                    if not ev_ or not dep_:
                        # NE EKSIK OLDUGUNU AYIR: kullanici bu satiri
                        # "canli veri gelmiyor" diye okuyordu, oysa canli
                        # skor/dakika geliyordu; eksik olan takimlarin
                        # SEZON ORTALAMALARIYDI.
                        if b.get("canli") and b.get("canli_durum"):
                            L.append("   Modelimiz   yok · canlı skor/dakika VAR "
                                     "ama takımların sezon ortalaması yok")
                            L.append("               (bu lig Fotmob ve "
                                     "Sofascore'da istatistiksiz)")
                        else:
                            L.append("   Modelimiz   yok · bu maç dış istatistik "
                                     "verisinde bulunamadı")
                    elif b["mtid"] in KOR:
                        eks = [a for a, v in (("ev sahibi", ev_.get("korner")),
                                              ("deplasman", dep_.get("korner")))
                               if v is None]
                        L.append("   Modelimiz   yok · korner verisi eksik"
                                 + (f" ({', '.join(eks)})" if eks else "")
                                 + " — uydurmuyoruz")
                    elif b["mtid"] in KRT:
                        L.append("   Modelimiz   yok · kart verisi güvenilmez "
                                 "veya eksik — uydurmuyoruz")
                    else:
                        L.append("   Modelimiz   yok · bu market modellenmiyor")
                L += iy_satirlari(b)
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
                # IKINCI FIYAT — VARSA da YOKSA da yazilir. Yoklugu gizlemek
                # kullaniciya "bu sayi iki kaynakla dogrulandi" izlenimi
                # verir; oysa cogu macta tek kaynak (Nesine) var.
                f = b.get("fd") or {}
                if f.get("var"):
                    ek = ""
                    if f.get("turetilmis"):
                        # Cifte Sans 1X2'den TOPLANDI. Ayri bir fiyat DEGIL;
                        # bagimsiz ikinci gorus sayisi bir artmis olmaz.
                        ek += " · 1X2'den türetildi"
                    ys = f.get("yas_sn") or 0
                    if ys > 3600:
                        ek += f" · {ys/3600:.0f} saat BAYAT"
                    L.append(f"   Piyasa      {_y(f['p'],0):<5} · {f['kaynak']} "
                             f"(pay {_y(f['marj'])} — Nesine "
                             f"{_y(b.get('marj') or 0, 0)}){ek}")
                    # Keskin kaynak Nesine'den belirgin ayrisiyorsa bu, karar
                    # verirken BAKILACAK sey. Ayrisma buyukse ikisinden biri
                    # yaniliyor; hangisi oldugunu BILMIYORUZ, ama bunu
                    # gostermemek kullanicidan bilgi saklamaktir.
                    d = f["p"] - b["olasilik"]
                    if abs(d) >= 0.05:
                        yon = "YÜKSEK" if d > 0 else "DÜŞÜK"
                        L.append(f"   ⚠️ Piyasa bu ihtimali Nesine'den "
                                 f"{abs(d)*100:.0f} puan {yon} görüyor")
                else:
                    L.append(f"   Piyasa      —     · ikinci fiyat YOK "
                             f"({f.get('neden','bilinmiyor')})")
                L += hareket_satiri(b)
                L.append("")
                nerede = ("dış piyasaya göre değeri" if b.get("dk_deger") is not None
                          else "Nesine payı en düşük")
                if b.get("tahmin_kaynak") and b["tahmin_kaynak"] != "Nesine":
                    n_k = len(b.get("tahmin_kaynaklar") or {})
                    L.append(f"   ⇒ Seçimde {_y(b['tahmin_p'],0)} kullanıldı "
                             f"({n_k} kaynağın ağırlıklı ortalaması)")
                    ay = b.get("ayrisma")
                    if isinstance(ay, (int, float)) and ay >= 0.20:
                        L.append(f"   ⚠️ Kaynaklar {ay*100:.0f} puan AYRIŞIYOR — "
                                 "bu seçimde bilgi zayıf")
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
            L += maliyet.maliyet_satiri(p)
    if pre_havuz:
        L += maliyet.tekli_bolumu(pre_havuz, _s, anlam)
    L += banko_bolumu(paketler)
    if deger:
        L += deger_bolumu(deger)
    if notlar:
        L.append("")
        L += [f"⚠️ {n}" for n in notlar]
    if any(p["kaynak"] == "CANLI" for p in paketler):
        L += SF.kaynak_satiri()
    L += hacim.satir(len(paketler))
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
    # ARSIV YAN ISTIR, KUPONU OLDURMEMELI.
    # 2026-08-22 gecesi: bulten gece yarisi devrinde 871 -> 419 -> 895
    # arasinda salindi; sanity kapisi (onceki snapshot'in %50'si) bunu
    # bozulma sanip HATA FIRLATTI ve `bulletin.run()` /kupon'u komple
    # oldurdu. Arka arkaya 6 kosu kirmizi dustu.
    # Arsiv yazilamazsa en son SAGLAM snapshot ile devam edilir; kullanici
    # kuponsuz kalmaz, ama verinin tazeligi mesaja YAZILIR.
    arsiv_notu = None
    try:
        bulletin.run()
    except Exception as e:
        arsiv_notu = str(e)
        print(f"[arsiv] YAZILAMADI: {e} — son saglam snapshot kullanilacak")
    s = bulletin.latest()
    if not s:
        print("[HATA] arsivde snapshot yok, devam edilemiyor")
        raise SystemExit(1)
    filtre = None
    for a in sys.argv[1:]:
        if a.startswith("--filtre="):
            filtre = a.split("=", 1)[1]
    # HACIM KAPISI (konsul 5/5): kapiya takilinca oneri URETILMEZ.
    # --zorla ile gecilebilir ama gecildigi mesaja YAZILIR.
    pas, sebep = hacim.pas_mi()
    if pas and "--zorla" not in sys.argv:
        msg = ("🛑 NESINE · BUGÜN PAS\n\n" + sebep +
               "\n\nNegatif beklenen değerde kaç kez oynadığın, hangi bahsi\n"
               "seçtiğinden daha belirleyici. Sınır bu yüzden var.\n"
               + "\n".join(hacim.satir()))
        print(msg)
        if "--dry" not in sys.argv:
            import notify
            notify.send(msg)
        raise SystemExit(0)
    ps, notlar, deger, pre_havuz = uc_kupon(
        s, canli="--canlisiz" not in sys.argv, filtre=filtre)
    if pas:
        notlar.append("HACİM SINIRI AŞILDI, --zorla ile geçildi: " + sebep)
    if arsiv_notu:
        notlar.append("VERİ TAZELİĞİ: bülten yenilenemedi, en son kaydedilen "
                      f"anlık görüntü kullanıldı ({arsiv_notu})")
    msg = format_message(ps, notlar, deger, pre_havuz)
    print(msg)
    print(f"\n[uzunluk: {len(msg)} karakter, {len(parcala(msg))} mesaj]")
    if "--dry" not in sys.argv:
        import golge
        import notify
        n = golge.kaydet(ps, kaynak=(filtre or "kupon"))
        print(f"[golge] {n} secim kaydedildi")
        for i, parca in enumerate(parcala(msg)):
            if not notify.send(parca):
                print(f"[HATA] {i+1}. parca gonderilemedi")
        if ps:
            hacim.kaydet(kupon=len(ps))
            print(f"[hacim] {hacim.durum()}")
