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
            return say(lambda m: _toplam_gol(m) > s, f"{s:g} üstü gol")
        return say(lambda m: _toplam_gol(m) < s, f"{s:g} altı gol")
    if mtid in (38, 287):                                # Karsilikli Gol
        if idx == 0:
            return say(lambda m: m.get("at", 0) >= 1 and m.get("ye", 0) >= 1, "karşılıklı gol")
        return say(lambda m: not (m.get("at", 0) >= 1 and m.get("ye", 0) >= 1),
                   "karşılıklı gol olmaması")
    if mtid in (49, 109):                                # Tek/Cift
        if idx == 0:
            return say(lambda m: _toplam_gol(m) % 2 == 1, "tek sayıda gol")
        return say(lambda m: _toplam_gol(m) % 2 == 0, "çift sayıda gol")
    if mtid == 216 and s is not None:                    # Korner Alt/Ust (TOPLAM)
        cift = [m for m in ma if m.get("korner") is not None]
        if not cift:
            return None
        # tek takimin korneri; toplam mac korneri icin iki takim gerekir ->
        # yaklasik olarak takim korneri x2 kullanilir, bu ACIKCA yazilir
        tutan = sum(1 for m in cift if m["korner"] * 2 > s)
        return {"tutan": tutan, "toplam": len(cift), "oran": tutan / len(cift),
                "metin": f"{s:g} üstü korner (takım kornerinin 2 katı ile tahmin)"}
    if mtid == 301 and s is not None:                    # Kart Alt/Ust
        cift = [m for m in ma if m.get("sari") is not None]
        if not cift:
            return None
        tutan = sum(1 for m in cift
                    if (m["sari"] + 2 * m.get("kirmizi", 0)) * 2 > s)
        return {"tutan": tutan, "toplam": len(cift), "oran": tutan / len(cift),
                "metin": f"{s:g} üstü kart (takım kartının 2 katı ile tahmin)"}
    if mtid in (1, 53) and idx in (0, 2):                # Mac Sonucu (kazanma)
        return say(lambda m: m.get("at", 0) > m.get("ye", 0), "bu takımların kazanması")
    return None
