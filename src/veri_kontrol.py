"""data/ altindaki dosyalarin BOZUK OLMADIGINI dogrular.

NEDEN VAR (2026-08-22): data/eslesme.json'a GIT CAKISMA ISARETLERI
(<<<<<<< / ======= / >>>>>>>) girdi ve COMMIT EDILDI. Sonuc: bot butun
mac-oncesi modelleri kaybetti -- Premier Lig maci (Nottingham F - Leeds)
bile "veri yok" dedi.

NASIL OLDU: is akislarindaki push dongusu
    git pull --rebase --autostash origin main || true
    git add data/
seklindeydi. Autostash geri uygularken CAKISIRSA `git pull` basarisiz olur,
ama `|| true` hatayi YUTAR; ardindan `git add data/` cakisma isaretli
dosyayi sahneler ve commit eder. Sessiz veri bozulmasi.

BU BETIK SON SAVUNMA HATTIDIR: commit'ten ONCE calisir, bozuk dosya
bulursa is akisini DUSURUR. Bozuk veriyi commit etmektense isi kirmizi
yapmak yeglenir -- birincisi sessiz, ikincisi gorunur.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
ISARET = ("<<<<<<< ", "=======", ">>>>>>> ")


def kontrol() -> list[str]:
    hatalar: list[str] = []
    for yol in sorted(DATA.rglob("*")):
        if not yol.is_file() or yol.suffix not in (".json", ".jsonl"):
            continue
        try:
            metin = yol.read_text(encoding="utf-8")
        except Exception as e:
            hatalar.append(f"{yol.name}: okunamadi ({e})")
            continue
        for i, satir in enumerate(metin.splitlines(), 1):
            if satir.startswith(ISARET[0]) or satir.startswith(ISARET[2]) \
                    or satir.rstrip() == ISARET[1]:
                hatalar.append(f"{yol.relative_to(DATA)}: {i}. satirda "
                               f"GIT CAKISMA ISARETI")
                break
        else:
            try:
                if yol.suffix == ".json":
                    json.loads(metin)
                else:
                    for i, satir in enumerate(metin.splitlines(), 1):
                        if satir.strip():
                            json.loads(satir)
            except Exception as e:
                hatalar.append(f"{yol.relative_to(DATA)}: gecersiz JSON ({e})")
    return hatalar


if __name__ == "__main__":
    h = kontrol()
    if h:
        print("VERI BOZUK — commit ENGELLENDI:")
        for x in h:
            print("  ✗", x)
        sys.exit(1)
    print("veri kontrolu TAMAM")
