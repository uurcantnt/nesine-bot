"""Ampirik isabet orani: "son N macin kacinda bu bahis tuttu?"

NEDEN: model olasiligi turetilmis bir sayidir; ham gerceklesme orani
kullanicinin kendi tartabilecegi ciplak bilgidir. Ikisi ayni sey degildir
ve ikisi de gosterilir.

SINIR: iki takimin maclari BIRLESTIRILIR (ev sahibinin son 10'u + deplasmanin
son 10'u = 20 gozlem). Bu, o iki takimin BIRBIRIYLE oynadigi mac degildir;
"bu takimlarin maclarinda ne siklikla oluyor" sorusunun cevabidir.
"""
from __future__ import annotations


def _toplam_gol(m: dict) -> int:
    return int(m.get("at", 0)) + int(m.get("ye", 0))


IY_MARKET = {7, 61, 8, 14, 209, 70, 15, 452, 453, 450, 218, 219}


def isabet_iy(mtid: int, idx: int, sov, iy_ev: list, iy_dep: list) -> dict | None:
    """Ilk yari marketleri icin gerceklesme orani.

    Iki takimin ILK YARI sonuclari BIRLESTIRILIR: "bu takimlarin maclarinda
    ilk yari ne siklikla boyle bitiyor" sorusunun cevabi.
    """
    ma = (iy_ev or []) + (iy_dep or [])
    if not ma:
        return None
    s = None if sov is None else float(sov)

    def say(kosul, metin):
        uygun = [m for m in ma if kosul(m) is not None]
        if not uygun:
            return None
        tutan = sum(1 for m in uygun if kosul(m))
        return {"tutan": tutan, "toplam": len(uygun),
                "oran": tutan / len(uygun), "metin": metin}

    top = lambda m: m["at"] + m["ye"]
    if mtid in (7, 61):
        if idx == 0:
            return say(lambda m: m["at"] > m["ye"], "ilk yarıyı bu takımlar önde bitirdi")
        if idx == 1:
            return say(lambda m: m["at"] == m["ye"], "ilk yarı berabere bitti")
        return say(lambda m: m["at"] < m["ye"], "ilk yarıyı rakip önde bitirdi")
    if mtid == 8:
        if idx == 0:
            return say(lambda m: m["at"] >= m["ye"], "ilk yarıda önde veya berabere")
        if idx == 1:
            return say(lambda m: m["at"] != m["ye"], "ilk yarı berabere BİTMEDİ")
        return say(lambda m: m["at"] <= m["ye"], "ilk yarıda önde değildi")
    if mtid in (14, 209, 70, 15) and s is not None:
        if idx == 1:
            return say(lambda m: top(m) > s, f"ilk yarıda {s:g} üstü gol".replace(".", ","))
        return say(lambda m: top(m) < s, f"ilk yarıda {s:g} altı gol".replace(".", ","))
    if mtid in (452, 453):
        kg = lambda m: m["at"] >= 1 and m["ye"] >= 1
        return say(kg if idx == 0 else (lambda m: not kg(m)),
                   "ilk yarıda karşılıklı gol" if idx == 0
                   else "ilk yarıda karşılıklı gol OLMAMASI")
    if mtid == 450:
        return say((lambda m: top(m) % 2 == 1) if idx == 0 else (lambda m: top(m) % 2 == 0),
                   "ilk yarıda tek sayıda gol" if idx == 0 else "ilk yarıda çift sayıda gol")
    if mtid in (218, 219) and s is not None:
        cift = [m for m in ma if m.get("iy_korner") is not None]
        if not cift:
            return None
        tutan = sum(1 for m in cift if (m["iy_korner"] > s) == (idx == 1))
        return {"tutan": tutan, "toplam": len(cift), "oran": tutan / len(cift),
                "metin": f"ilk yarıda {s:g} {'üstü' if idx==1 else 'altı'} korner".replace(".", ",")}
    return None


def isabet(mtid: int, idx: int, sov, ev: dict, dep: dict) -> dict | None:
    """(tutan, toplam, aciklama) — hesaplanamiyorsa None."""
    ma = (ev.get("maclar") or []) + (dep.get("maclar") or [])
    if not ma:
        return None
    s = None if sov is None else float(sov)

    def say(kosul, metin):
        uygun = [m for m in ma if kosul(m) is not None]
        if not uygun:
            return None
        tutan = sum(1 for m in uygun if kosul(m))
        return {"tutan": tutan, "toplam": len(uygun),
                "oran": tutan / len(uygun), "metin": metin}

    if mtid in (11, 12, 13) and s is not None:          # Gol Alt/Ust
        if idx == 1:
            return say(lambda m: _toplam_gol(m) > s, f"{s:g} üstü gol".replace(".", ","))
        return say(lambda m: _toplam_gol(m) < s, f"{s:g} altı gol".replace(".", ","))
    if mtid in (38, 287):                                # Karsilikli Gol
        if idx == 0:
            return say(lambda m: m.get("at", 0) >= 1 and m.get("ye", 0) >= 1, "karşılıklı gol")
        return say(lambda m: not (m.get("at", 0) >= 1 and m.get("ye", 0) >= 1),
                   "karşılıklı gol olmaması")
    if mtid in (49, 109):                                # Tek/Cift
        if idx == 0:
            return say(lambda m: _toplam_gol(m) % 2 == 1, "tek sayıda gol")
        return say(lambda m: _toplam_gol(m) % 2 == 0, "çift sayıda gol")
    if mtid in (216, 217) and s is not None:              # Korner Alt/Ust (TOPLAM)
        cift = [m for m in ma if m.get("korner") is not None]
        if not cift:
            return None
        # tek takimin korneri; toplam mac korneri icin iki takim gerekir ->
        # yaklasik olarak takim korneri x2 kullanilir, bu ACIKCA yazilir
        tutan = sum(1 for m in cift if m["korner"] * 2 > s)
        return {"tutan": tutan, "toplam": len(cift), "oran": tutan / len(cift),
                "metin": f"{s:g} üstü korner".replace(".", ",")}
    if mtid in (301, 605) and s is not None:              # Kart Alt/Ust
        cift = [m for m in ma if m.get("sari") is not None]
        if not cift:
            return None
        tutan = sum(1 for m in cift
                    if (m["sari"] + 2 * m.get("kirmizi", 0)) * 2 > s)
        return {"tutan": tutan, "toplam": len(cift), "oran": tutan / len(cift),
                "metin": f"{s:g} üstü kart".replace(".", ",")}
    if mtid in (1, 53) and idx in (0, 2):                # Mac Sonucu (kazanma)
        return say(lambda m: m.get("at", 0) > m.get("ye", 0), "bu takımların kazanması")
    return None
