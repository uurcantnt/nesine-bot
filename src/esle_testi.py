"""Eslestirici kapisi: YANLIS eslesmeyi bloke ettigini KANITLAYAN test.

Neden ayri test: yanlis eslesme HATA FIRLATMAZ. Sessizce baska takimin
istatistigini baglar ve bot yanlis tahmin uretir. Tek koruma budur.

Kosum:  python3 src/esle_testi.py     (cikis kodu 0 = temiz, 1 = BLOKE)
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")
import stats as ST  # noqa: E402


def ix(*ciftler):
    return {(ST.sadelestir(h), ST.sadelestir(a)): f"{h}-{a}" for h, a in ciftler}


# (aciklama, indeks, sorgu_ev, sorgu_dep, beklenen)  beklenen None = REDDET
DURUM = [
    # ---- REDDEDILMESI GEREKENLER ----
    ("tek taraf tutup oteki alakasiz (olculdu 2026-08-31)",
     ix(("Aston Villa", "Arsenal")), "Galatasaray", "Arsenal", None),
    ("genc takim A takimina baglanmamali",
     ix(("Aston Villa", "Arsenal")), "Brighton U21", "Arsenal U21", None),
    ("A takimi indeksinde genc takim sorgusu",
     ix(("Arsenal", "Chelsea")), "Arsenal U21", "Chelsea U21", None),
    ("genc indeksinde A takimi sorgusu",
     ix(("Arsenal U21", "Chelsea U21")), "Arsenal", "Chelsea", None),
    ("rezerv takim A takimina baglanmamali",
     ix(("Real Sociedad", "Celta Vigo")), "R. Sociedad B", "Celta Vigo B", None),
    ("kadin takimi erkek takimina baglanmamali",
     ix(("Bayern Munich", "Mainz 05")), "B. Münih (K)", "Mainz 05 (K)", None),
    ("iki aday esit skorluysa KURA degil RET",
     ix(("Manchester United", "Leeds"), ("Manchester City", "Leeds")),
     "Manchester", "Leeds", None),

    # ---- KABUL EDILMESI GEREKENLER (kapi fazla siki olmamali) ----
    ("birebir", ix(("Arsenal", "Chelsea")), "Arsenal", "Chelsea",
     "Arsenal-Chelsea"),
    ("alt-dize: AC Oulu / SJK",
     ix(("AC Oulu", "SJK")), "Oulu", "SJK Seinöjoen", "AC Oulu-SJK"),
    ("alt-dize: Sp Braga / Guimaraes",
     ix(("Sp Braga", "Guimaraes")), "Braga", "V. Guimaraes",
     "Sp Braga-Guimaraes"),
    ("ELLE takma ad: Kopenhag → FC Copenhagen",
     ix(("FC Copenhagen", "Sonderjyske")), "Kopenhag", "Sonderjyske",
     "FC Copenhagen-Sonderjyske"),
    ("rezerv-rezerv eslesmeli",
     ix(("Real Madrid Castilla", "Barcelona B")), "Real Madrid B",
     "Barcelona B", "Real Madrid Castilla-Barcelona B"),
    ("genc-genc eslesmeli",
     ix(("Brighton & Hove Albion U21", "Arsenal U21")), "Brighton U21",
     "Arsenal U21", "Brighton & Hove Albion U21-Arsenal U21"),
    ("baglac farki: Union de Santa Fe",
     ix(("Union Santa Fe", "Sarmiento")), "Union de Santa Fe",
     "Sarmiento Junin", "Union Santa Fe-Sarmiento"),
    ("B. kisaltmasi rezerv SANILMAMALI",
     ix(("Borussia Dortmund", "Bayern Munich")), "B. Dortmund",
     "Bayern Münih", "Borussia Dortmund-Bayern Munich"),
    ("C. = City/County, rezerv SANILMAMALI",
     ix(("Chelmsford City", "Haverfordwest County")), "Chelmsford C.",
     "Haverfordwest C.", "Chelmsford City-Haverfordwest County"),
]


def main() -> int:
    hata = []
    for ad, idx, ev, dep, bek in DURUM:
        got = ST.esle(idx, ev, dep)
        if got != bek:
            hata.append(f"  ✗ {ad}\n      {ev} - {dep}\n"
                        f"      beklenen={bek!r}  cikan={got!r}")
    for ad, ham, bek in [("Arsenal U21", "Arsenal U21", "u21"),
                         ("Real Madrid B", "Real Madrid B", "rez"),
                         ("Lyn 1896 FK II", "Lyn 1896 FK II", "rez"),
                         ("B. Münih (K)", "B. Münih (K)", "kad"),
                         ("Chelmsford C.", "Chelmsford C.", ""),
                         ("B. Dortmund", "B. Dortmund", ""),
                         ("Arsenal", "Arsenal", "")]:
        got = ST.seviye(ham) if hasattr(ST, "seviye") else "<yok>"
        if got != bek:
            hata.append(f"  ✗ seviye({ham!r}) beklenen={bek!r} cikan={got!r}")
    if hata:
        print(f"BLOKE — {len(hata)} durum basarisiz:")
        print("\n".join(hata))
        return 1
    print(f"TEMIZ — {len(DURUM)} eslesme + 7 seviye durumu gecti")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
