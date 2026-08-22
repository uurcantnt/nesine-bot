"""UZAKTAKI data/ dosyalarini yereldekiyle ANLAMSAL olarak birlestirir.

NEDEN VAR (2026-08-22): git, uretilmis JSON dosyalarini METIN olarak
birlestirmeye calisiyordu ve surekli cakisiyordu:

    git pull --rebase --autostash origin main || true
    git add data/

Iki is (arsiv 15 dk'da bir, istatistik gunluk) AYNI buyuk JSON dosyalarini
yeniden yaziyor. Autostash geri uygularken cakisiyor, `|| true` hatayi
yutuyor ve `git add data/` CAKISMA ISARETLI dosyayi commit ediyordu.
Sonuc: bot butun mac-oncesi modelleri kaybetti (Premier Lig maci bile
"veri yok" dedi). Bir kez onarildi, ARDINDAN TEKRAR OLUSTU -- yani tek
seferlik kaza degil, YAPISAL sorun.

COZUM: git'e metin birlestirmesi YAPTIRMA. Bu betik uzaktaki surumu okur,
sozluk duzeyinde birlestirir (yerel kazanir, cunku yeni uretilmis olan o)
ve dosyayi yeniden yazar. Boylece cakisma OLUSAMAZ.

KULLANIM (is akisinda, commit'ten ONCE):
    git fetch origin main
    python3 src/veri_birlestir.py
    python3 src/veri_kontrol.py
    git add data/ && git commit && git push
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
DATA = KOK / "data"
# Sozluk yapisindaki birikimli dosyalar. Digerleri (arsiv .gz, jsonl)
# dokunulmaz: arsiv dosyalari ISIMLERI benzersiz oldugu icin cakismaz,
# jsonl'ler ise EKLEME ile buyur.
BIRLESIK = ("eslesme.json", "istatistik.json", "referans.json",
            "iy_gecmis.json", "hacim.json")


def _uzak(ad: str):
    r = subprocess.run(["git", "show", f"origin/main:data/{ad}"],
                       capture_output=True, text=True, cwd=KOK)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None          # uzak bozuksa YOK SAY, yerel kazanir


def _yerel(yol: Path):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception:
        return None


def calis() -> int:
    degisen = 0
    for ad in BIRLESIK:
        yol = DATA / ad
        y = _yerel(yol) if yol.exists() else None
        u = _uzak(ad)
        if y is None and u is None:
            continue
        if y is None:
            print(f"  {ad}: yerel bozuk/yok — UZAK kullanilyor")
            yol.write_text(json.dumps(u, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            degisen += 1
            continue
        if u is None:
            print(f"  {ad}: uzak yok/bozuk — yerel korunuyor ({len(y)})")
            continue
        if not isinstance(y, dict) or not isinstance(u, dict):
            continue
        birlesik = dict(u)
        birlesik.update(y)          # YEREL KAZANIR (yeni uretilmis olan o)
        if birlesik != y:
            yol.write_text(json.dumps(birlesik, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            degisen += 1
        print(f"  {ad}: uzak {len(u)} + yerel {len(y)} -> {len(birlesik)}")
    return degisen


if __name__ == "__main__":
    print("veri birlestirme:")
    n = calis()
    print(f"→ {n} dosya guncellendi")
    sys.exit(0)
