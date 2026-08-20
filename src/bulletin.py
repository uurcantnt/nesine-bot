"""Nesine bulteni: cek, sadelestir, arsivle.

Arsiv NEDEN: oran hareketi geriye donuk uretilemez. Kacan snapshot geri gelmez.
Kurallar sonra yazilabilir, veri sonra toplanamaz.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from core import FUTBOL, MARKETS

URL = "https://cdnbulten.nesine.com/api/bulten/getprebultenfull"
URL_CANLI = "https://bulten.nesine.com/api/bulten/getlivebultenfull"

# Canli bultende MTID'ler maç oncesinden FARKLI bir uzayda:
#   53 = Mac Sonucu (mevcut skora gore)   -- 19 macin 14'unde 56 ile ayni (0-0 olanlar)
#   56 = Kalan Mac Sonucu (skor sifirlanmis) -- gol atilinca 53'ten ayrisiyor
#   55 = Cifte Sans
# 53 kimligi TEK BASINA kanitlanamadi (55'in bulundugu maclarda 53/56 ayrismiyor).
# Bu yuzden canli maclar CALISMA ANINDA, MAC BAZINDA dogrulanir: 55'in
# olasiliklari 53'un ikiserli toplamlarina esit degilse o mac ATLANIR.
CANLI_MS, CANLI_KALAN, CANLI_CS = 53, 56, 55
CANLI_IMZA_ESIK = 0.02
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ARSIV = Path(__file__).resolve().parent.parent / "data" / "arsiv"


def fetch(timeout: int = 90) -> dict:
    """Ham bulteni indir. UA basligi SART -- yoksa CDN 403 dondurur."""
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_live(timeout: int = 45) -> dict:
    req = urllib.request.Request(URL_CANLI, headers={"User-Agent": UA,
                                                     "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _dv(o: list, kapsam: int = 1) -> list | None:
    if any(x is None or x <= 1.0 for x in o):
        return None
    s = sum(1.0 / x for x in o) / kapsam
    return [(1.0 / x) / s for x in o]


def canli_ms_dogrula(ma: list) -> list | None:
    """Bir canli macin Mac Sonucu oranlarini DOGRULAYARAK dondur.

    Kanit: cifte sans (55) her secenegi 3 sonucun 2'sini kapsar, dolayisiyla
    olasiliklari mac sonucunun (53) ikiserli toplamlarina esit olmalidir.
    Tutmuyorsa market kimligi belirsizdir -> None (mac atlanir).
    """
    mm = {m.get("MTID"): m for m in ma}
    ms, cs = mm.get(CANLI_MS), mm.get(CANLI_CS)
    if not ms or not cs or ms.get("MS") != 1:
        return None
    o_ms = [x.get("O") for x in ms.get("OCA", [])]
    o_cs = [x.get("O") for x in cs.get("OCA", [])]
    if len(o_ms) != 3 or len(o_cs) != 3:
        return None
    p, c = _dv(o_ms), _dv(o_cs, 2)
    if not p or not c:
        return None
    bek = [p[0] + p[1], p[0] + p[2], p[1] + p[2]]
    if max(abs(c[i] - bek[i]) for i in range(3)) > CANLI_IMZA_ESIK:
        return None
    return o_ms


def simplify_live(raw: dict) -> list:
    """Canli futbol maclari -- yalnizca imzasi dogrulanmis olanlar."""
    out = []
    for e in raw.get("sg", {}).get("EA", []):
        if e.get("TYPE") != FUTBOL:
            continue
        o = canli_ms_dogrula(e.get("MA", []))
        if not o:
            continue
        out.append({"id": e.get("C"), "ts": e.get("ESD"), "lig": e.get("LC"),
                    "ev": e.get("HN"), "dep": e.get("AN"), "canli": True,
                    "m": {"53": {"o": o, "mbs": 1, "ms": 1, "sov": 0.0}}})
    return out


def simplify(raw: dict) -> dict:
    """8,5 MB ham JSON -> sadece ihtiyacimiz olan alanlar (~200 KB gz).

    Yalnizca futbol ve yalnizca DOGRULANMIS marketler saklanir.
    """
    sg = raw.get("sg", {})
    olay = []
    for e in sg.get("EA", []):
        if e.get("TYPE") != FUTBOL:
            continue
        m = {}
        for market in e.get("MA", []):
            mtid = market.get("MTID")
            if mtid not in MARKETS:
                continue
            oca = market.get("OCA") or []
            if len(oca) != len(MARKETS[mtid]["secenek"]):
                continue
            m[str(mtid)] = {
                "o": [x.get("O") for x in oca],
                "mbs": market.get("MBS"),
                "ms": market.get("MS"),
                "sov": market.get("SOV"),
                "mv": market.get("MV"),
            }
        if not m:
            continue
        olay.append({
            "id": e.get("C"), "ts": e.get("ESD"), "lig": e.get("LC"),
            "ev": e.get("HN"), "dep": e.get("AN"), "m": m,
        })
    return {
        "cekim": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "oddVersion": sg.get("oddVersion"),
        "drawNo": sg.get("drawNo"),
        "ligler": {str(l["LID"]): l["N"] for l in sg.get("LA", []) if "LID" in l},
        "olay": olay,
    }


def _key(o: dict) -> tuple:
    """Bir macin oran parmak izi -- degisim tespiti icin."""
    return tuple(sorted((k, tuple(v["o"]), v["ms"]) for k, v in o["m"].items()))


def diff(onceki: dict, simdiki: dict) -> dict:
    """Sadece orani/durumu degisen (veya yeni gelen) maclar."""
    eski = {o["id"]: _key(o) for o in onceki.get("olay", [])}
    degisen = [o for o in simdiki["olay"] if eski.get(o["id"]) != _key(o)]
    return {**{k: v for k, v in simdiki.items() if k != "olay"},
            "tam": False, "olay": degisen, "toplam": len(simdiki["olay"])}


def archive(snap: dict, tam_saat: tuple = (0, 12)) -> Path | None:
    """Delta arsiv: 00 ve 12 UTC'de tam snapshot, arada sadece degisenler.

    Yeniden kurma = gunun son tam snapshot'i + uzerine sirayla deltalar.
    Amac: */15 cadence'i yilda 1,6 GB yerine ~100 MB'a indirmek.
    """
    t = datetime.now(timezone.utc)
    d = ARSIV / t.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{t.strftime('%H%M%S')}.json.gz"

    onceki = _son_snapshot()
    # oddVersion degismediyse yazacak bir sey yok (olculdu: 6 cekimde 0 degisim)
    if onceki is not None and onceki.get("oddVersion") == snap.get("oddVersion"):
        return None
    if onceki is None or (t.hour in tam_saat and not list(d.glob(f"{t.hour:02d}[0-5][0-9][0-5][0-9].json.gz"))):
        cikti = {**snap, "tam": True}
    else:
        cikti = diff(onceki, snap)

    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(cikti, f, ensure_ascii=False, separators=(",", ":"))
    return p


def _son_snapshot() -> dict | None:
    """Arsivdeki en son durumu yeniden kur (son tam + sonraki deltalar)."""
    files = sorted(ARSIV.glob("*/*.json.gz"))
    if not files:
        return None
    tam_i = None
    for i in range(len(files) - 1, -1, -1):
        if load(files[i]).get("tam"):
            tam_i = i
            break
    if tam_i is None:
        return None
    durum = load(files[tam_i])
    havuz = {o["id"]: o for o in durum["olay"]}
    for f in files[tam_i + 1:]:
        d = load(f)
        for o in d.get("olay", []):
            havuz[o["id"]] = o
        # meta EN SON dosyadan gelmeli; yoksa oddVersion bayat kalir ve
        # "degismedi" atlamasi hic tetiklenmez (olculdu: her turda bos delta)
        durum = {**durum, **{k: v for k, v in d.items() if k != "olay"}}
    return {**durum, "olay": list(havuz.values())}


def load(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def latest() -> dict | None:
    """En son durum (deltalar uygulanmis halde)."""
    return _son_snapshot()


class BultenBozuk(Exception):
    """Bulten beklenenden kucuk geldi -- arsivi kirletmemek icin durdur."""


def sanity(snap: dict, onceki: dict | None, esik: float = 0.5) -> None:
    """Kismi/bozuk yanit korumasi.

    2026-08-20'de bir cekim 960 yerine 96 mac dondurdu (sebebi tespit
    edilemedi, 6 tekrar denemede yeniden uretilemedi). Boyle bir yanit
    arsive TAM olarak yazilirsa tum gecmis bozulur -- bu yuzden kapi.
    """
    n = len(snap["olay"])
    if n < 20:
        raise BultenBozuk(f"bulten neredeyse bos: {n} mac")
    if onceki and len(onceki.get("olay", [])) * esik > n:
        raise BultenBozuk(
            f"bulten kuculdu: {n} mac, onceki {len(onceki['olay'])} "
            f"(esik %{esik*100:.0f}) -- arsive yazilmadi")


ANOMALI = Path(__file__).resolve().parent.parent / "data" / "anomali.jsonl"


def _anomali(mesaj: str, n: int) -> None:
    ANOMALI.parent.mkdir(parents=True, exist_ok=True)
    with ANOMALI.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "mac": n, "mesaj": mesaj}, ensure_ascii=False) + "\n")


def run(deneme: int = 3, bekle: float = 4.0) -> Path | None:
    """Snapshot al. Kismi yanit gelirse TEKRAR DENE.

    Olculen davranis: CDN seyrek olarak ~960 yerine ~96 mac donduruyor
    (2026-08-20'de 2 kez goruldu; pes pese 10 istekte 0 kez). Sebep muhtemelen
    edge cache yenilenirken yarim nesne servis edilmesi. Tek bir kotu yanit
    yuzunden tur atlanmasin diye tekrar deneme var; hepsi basarisizsa
    arsive YAZILMAZ ve anomali loglanir.
    """
    t0 = time.time()
    for i in range(deneme):
        snap = simplify(fetch())
        try:
            sanity(snap, _son_snapshot())
            break
        except BultenBozuk as e:
            _anomali(str(e), len(snap["olay"]))
            print(f"[arsiv] deneme {i+1}/{deneme} basarisiz: {e}")
            if i == deneme - 1:
                raise
            time.sleep(bekle)
    p = archive(snap)
    if p is None:
        print(f"[arsiv] atlandi (oddVersion degismedi) | {time.time()-t0:.1f}s")
        return None
    kayit = load(p)
    tur = "TAM" if kayit.get("tam") else "delta"
    print(f"[arsiv] {p.name} | {tur} | {len(kayit['olay'])}/{len(snap['olay'])} mac | "
          f"{p.stat().st_size/1024:.0f} KB | {time.time()-t0:.1f}s")
    return p


if __name__ == "__main__":
    run()
