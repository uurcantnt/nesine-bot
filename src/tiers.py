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
    ("AZ RİSKLİ",     {"pre": 1, "canli": 2}, 0.50, 0.64, 0.45),
    ("ORTA RİSKLİ",   {"pre": 2, "canli": 2}, 0.55, 0.75, 0.30),
    ("YÜKSEK RİSKLİ", {"pre": 3, "canli": 3}, 0.33, 0.54, 0.12),
]
KAYNAK = [("MAÇ ÖNÜ", "pre"), ("CANLI", "canli")]


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
        return [], ("bu risk seviyesine uyan maç yok "
                    f"(tutma ihtimali %{alt*100:.0f}-%{ust*100:.0f} arası aranıyor)")
    if oran_toplam < MIN_KUPON_ORAN:
        return [], (f"bulunan maçların toplam oranı {_s(oran_toplam)}, "
                    f"{_s(MIN_KUPON_ORAN)} altında — bu kadar düşük ödeme için "
                    "risk almaya değmez")
    if kesildi and len(bacak) < n:
        return bacak, (f"{n} maç yerine {len(bacak)} — bir maç daha eklemek "
                       f"tutma ihtimalini %{taban*100:.0f} altına düşürüyordu")
    if len(bacak) > n:
        return bacak, (f"{len(bacak)} maç — ödemeyi {_s(MIN_KUPON_ORAN)} üstüne "
                       "çıkarmak için bir maç eklendi")
    return bacak, ""


def uc_kupon(snap: dict, canli: bool = True) -> tuple[list[dict], list[str]]:
    """Her kaynak x her risk seviyesi icin kupon. Ikinci donus: uyarilar."""
    havuzlar = {"pre": coupon.candidates(snap),
                "canli": canli_adaylar() if canli else []}
    cikti, notlar = [], []
    if canli:
        el = CANLI_ELEME
        if not havuzlar["canli"] and not el.get("dogrulanan_mac"):
            notlar.append("CANLI: şu an oynanan maçlarda oranları güvenle "
                          "doğrulayabildiğim market yok.")
        elif el.get("dusuk_oran"):
            notlar.append(
                f"CANLI: tutma ihtimali yüksek {el['dusuk_oran']} seçenek var ama "
                f"oranları çok düşük ({', '.join(el['dusuk_oran_ornek'])}) — "
                "kazancı yatırdığın parayı hak etmiyor, önerilmedi.")
        if el.get("marj"):
            notlar.append(f"CANLI: {el['marj']} seçenek Nesine payı çok yüksek "
                          f"olduğu için (%{CANLI_MAX_MARJ*100:.0f} üstü) elendi.")
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


GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

# Bu esigin altindaki oynamalar gurultu sayilir, mesaja yazilmaz
HAREKET_ESIGI = 0.025


def _secenek_idx(b: dict) -> int | None:
    """Bacagin secenek indeksi. coupon.py MUHURLU oldugu icin oradan
    alinmaz; secenek adindan turetilir."""
    mtid = b["mtid"]
    if b.get("canli"):
        liste = CANLI_MARKET.get(str(mtid), (None, None, []))[2]
    else:
        liste = MARKETS.get(mtid, {}).get("secenek", [])
    return liste.index(b["secenek"]) if b["secenek"] in liste else None


def _hareket_satiri(b: dict) -> list:
    """Oranin gecmiste nerede oldugunu anlatan NOT satiri (varsa)."""
    if b.get("canli"):
        return []                     # canli oranlar arsivlenmiyor
    idx = _secenek_idx(b)
    if idx is None:
        return []
    h = bulletin.hareket(b["id"], str(b["mtid"]), idx)
    if not h or abs(h["degisim"]) < HAREKET_ESIGI:
        return []
    yon = "yükseldi" if h["degisim"] > 0 else "düştü"
    yorum = ("piyasa bu ihtimali artık daha DÜŞÜK görüyor"
             if h["degisim"] > 0 else
             "piyasa bu ihtimali artık daha YÜKSEK görüyor")
    saat = f"{h['saat']:g}"
    return [f"    NOT: {saat} saat önce {_s(h['eski'])} idi → şimdi "
            f"{_s(h['yeni'])} ({_y(abs(h['degisim']))} {yon})",
            f"         {yorum}"]


def _s(x: float, basamak: int = 2) -> str:
    """Turkce sayi: ondalik ayirici virgul."""
    return f"{x:,.{basamak}f}".replace(",", "~").replace(".", ",").replace("~", ".")


def _y(oran: float, basamak: int = 1) -> str:
    """Yuzde: isaret onde, ondalik virgul. -0.148 -> '-%14,8'"""
    isaret = "-" if oran < 0 else ""
    return f"{isaret}%{_s(abs(oran) * 100, basamak)}"

# Secenek kodlarinin duz Turkce karsiligi -- "1-2" ne demek bilmek gerekmesin
ACIKLAMA = {
    "1": "ev sahibi kazanır",
    "X": "berabere biter",
    "2": "deplasman kazanır",
    "1-X": "ev sahibi kazanır VEYA berabere",
    "1-2": "berabere BİTMEZ",
    "X-2": "ev sahibi KAZANAMAZ",
}

TERIMLER = [
    "━━━ TERİMLER ━━━",
    "• Tutma ihtimali: bahsin gerçekleşme olasılığı. Bizim tahminimiz",
    "  DEĞİL — Nesine'nin kendi oranından payı çıkarınca kalan sayı.",
    "  %60 demek: 10 kupondan yaklaşık 6'sı tutar.",
    "• Hak ettiği oran: o ihtimalin adil karşılığı (1 ÷ ihtimal). %60",
    "  ihtimal 1,67 oranı hak eder. Kimse pay almasaydı oran bu olurdu.",
    "• Nesine veriyor / eksik: aradaki fark Nesine'nin payıdır. 1,67 yerine",
    "  1,42 vermesi, doğru tahmin etsen bile her kupondan bir miktarın",
    "  kasada kalması demektir. KAYBIN ASIL SEBEBİ BUDUR, tahmin gücü değil.",
    "• Uzun vadede: aynı bahsi yüzlerce kez oynasan ortalama ne olur.",
    "  Tek kupon elbette tutabilir; bu satır bahsin FİYATINI gösterir.",
    "• NOT satırı: oranın geçmişi. Bot bülteni 15 dakikada bir arşivliyor,",
    "  bu yüzden oranın nereden nereye geldiğini görebiliyor. Oran YÜKSELDİYSE",
    "  piyasa o ihtimali daha düşük görmeye başlamış, DÜŞTÜYSE tersi.",
]


def format_message(paketler: list[dict], notlar: list[str]) -> str:
    if not paketler:
        return ("NESINE · /kupon\nUygun kupon bulunamadi.\n" + "\n".join(notlar))
    L = [f"NESINE · /kupon · {trtime.simdi().strftime('%d.%m %H:%M')}"]
    for kaynak_ad, _ in KAYNAK:
        grup = [p for p in paketler if p["kaynak"] == kaynak_ad]
        if not grup:
            continue
        L.append("")
        L.append(f"━━━ {kaynak_ad} ━━━")
        for p in grup:
            ek = f"\n  NOT: {p['neden']}" if p.get("neden") else ""
            L.append("")
            L.append(f"▸ {p['seviye']}  ({p['n']} maç){ek}")
            for b in p["bacak"]:
                if b.get("canli"):
                    ne_zaman = "ŞU AN OYNANIYOR"
                else:
                    d = trtime.yerel(b["bas"])
                    ne_zaman = f"{d.strftime('%d.%m')} {GUN[d.weekday()]} {d.strftime('%H:%M')}"
                acik = ACIKLAMA.get(b["secenek"], b["secenek"])
                L.append(f"  {b['mac']}")
                L.append(f"    Ne zaman : {ne_zaman}")
                L.append(f"    Bahis    : {b['market']} → \"{b['secenek']}\" ({acik})")
                adil = 1.0 / b["olasilik"]
                L.append(f"    Tutma ihtimali {_y(b['olasilik'], 0)} → "
                         f"hak ettiği oran {_s(adil)}")
                L.append(f"    Nesine veriyor {_s(b['oran'])}  "
                         f"({_s(adil - b['oran'])} eksik — Nesine'nin payı)")
                L.extend(_hareket_satiri(b))
            stake = LIMITS["STAKE_TL"]
            doner = stake * p["toplam_oran"]
            if p["n"] > 1:      # tek macta bu satirlar bacakla birebir ayni olurdu
                adil_k = 1.0 / p["isabet_olasiligi"]
                L.append(f"    ── KUPON: tutma ihtimali {_y(p['isabet_olasiligi'])} → "
                         f"hak ettiği oran {_s(adil_k)}")
                L.append(f"       Nesine veriyor {_s(p['toplam_oran'])}  "
                         f"({_s(adil_k - p['toplam_oran'])} eksik)")
            L.append(f"    {_s(stake,0)} TL yatırırsan: tutarsa {_s(doner)} TL döner "
                     f"(kârın {_s(doner-stake)} TL), tutmazsa {_s(stake,0)} TL gider")
            L.append(f"    Uzun vadede: her {_s(stake,0)} TL'nin ortalama "
                     f"{_s(abs(p['ev'])*stake)} TL'si kaybolur ({_y(p['ev'])})")
    if notlar:
        L.append("")
        for n in notlar:
            L.append(f"! {n}")
    L.append("")
    L.append("")
    L.extend(TERIMLER)
    L.append("")
    L.append("Yüksek risk daha İYİ bahis DEĞİL — sadece daha az olası, daha")
    L.append("yüksek oranlı. Her seviyede uzun vade eksidir; kupona her ek maç")
    L.append("bunu daha da kötüleştirir (komisyonlar çarpılır).")
    if any(p["kaynak"] == "CANLI" for p in paketler):
        L.append("")
        L.append("CANLI UYARISI: Nesine'nin canlı maçlardaki payı ölçüldü, %21-25.")
        L.append("Maç öncesinde en ucuzu %17. Yani canlı oynamak her zaman daha")
        L.append("pahalı. Ayrıca canlı oranlar saniyeler içinde değişir — Nesine'de")
        L.append("gördüğün oran buradakinden farklıysa bu hesap geçersizdir.")
    return "\n".join(L)


def parcala(msg: str, sinir: int = 3800) -> list[str]:
    """Telegram mesaj siniri 4096 karakter; asan mesaj SESSIZCE dusuyor.

    Bolme satir sinirinda yapilir, boylece bir kupon ikiye bolunmez.
    """
    if len(msg) <= sinir:
        return [msg]
    parcalar, cur = [], []
    n = 0
    for satir in msg.split("\n"):
        if n + len(satir) + 1 > sinir and cur:
            parcalar.append("\n".join(cur))
            cur, n = [], 0
        cur.append(satir)
        n += len(satir) + 1
    if cur:
        parcalar.append("\n".join(cur))
    return parcalar


if __name__ == "__main__":
    import sys
    bulletin.run()
    s = bulletin.latest()
    ps, notlar = uc_kupon(s, canli="--canlisiz" not in sys.argv)
    msg = format_message(ps, notlar)
    print(msg)
    print(f"\n[uzunluk: {len(msg)} karakter, {len(parcala(msg))} mesaj]")
    if "--dry" not in sys.argv:
        import notify
        for i, parca in enumerate(parcala(msg)):
            if not notify.send(parca):
                print(f"[HATA] {i+1}. parca gonderilemedi")
