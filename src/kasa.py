"""Kasa — masaustunde calisan, tek dosyalik bilgi haritasi.

`kasa/notlar/` altindaki markdown dosyalarini okur, klasor yapisini isinsal
(radial) bir agaca cevirir ve TEK bir `harita.html` uretir. Uretilen dosya
kendi kendine yeter: internet, sunucu, kurulum gerekmez — cift tiklayip acarsin.

    python3 src/kasa.py yap                  # kasa/harita.html uret
    python3 src/kasa.py yap --ac             # uret ve tarayicida ac
    python3 src/kasa.py masaustu             # uret ve Masaustu'ne kopyala
    python3 src/kasa.py sun                  # her istekte yeniden uretip sun

YAPI: klasor = dal, dosya = not. Ic ice klasorler agacin dallarini uzatir.
`_dal.md` bir dalin adini/rengini/simgesini, `_klasor.md` bir alt klasorun
basligini ve govdesini verir; ikisi de dugum OLARAK degil, ust bilgi olarak
okunur.

BAGLAR: bir notun icinde `[[baska not]]` yazarsan harita ikisi arasina kesik
cizgi ceker ve panelde tiklanabilir olur. Klasor hiyerarsisi govdeyi, koseli
parantezler capraz baglari kurar.

Bu dosya `data/` altina yazmaz; `depo.py` kilidiyle isi yoktur.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import math
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KASA = KOK / "kasa"
NOTLAR = KASA / "notlar"
SABLON = KASA / "_sablon" / "harita.html"
CIKTI = KASA / "harita.html"

# Dal rengi verilmemisse sirayla bunlar dagitilir.
RENKLER = ["#4ecdc4", "#5b9bd5", "#e8798f", "#e0b545", "#d4664f", "#9b7fd4"]
SIMGELER = ["◇", "○", "△", "◎", "◈", "◍"]

# Yerlesim sabitleri (dunya birimi). Agac MERKEZDEN degil, her dalin KENDI
# govdesinden acilir: govde bir cemberin uzerinde durur, cocuklar oradan disa
# dogru yelpaze yapar.
TABAN_YARICAP = 300.0      # merkez -> dal govdesi (en az)
KATMAN = 180.0             # govdeden itibaren her derinligin ek yaricapi
EN_AZ_ARALIK = 34.0        # en dis halkada iki dugum arasi en az yay
ETIKET_PAYI = 120.0        # dal basligi yelpazenin ne kadar disinda
YELPAZE = math.radians(126)   # bir dalin kendi govdesinde actigi aci
EN_GENIS = 4000.0          # bir yelpazenin yariacap tavani


# --------------------------------------------------------------------------
# okuma
# --------------------------------------------------------------------------
def _sadelestir(s: str) -> str:
    """Turkce harfleri ASCII'ye indirger, kucuk harfe cevirir."""
    esle = {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
            "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"}
    s = "".join(esle.get(k, k) for k in s)
    s = unicodedata.normalize("NFKD", s)
    return "".join(k for k in s if not unicodedata.combining(k)).lower()


def _kimlik(s: str) -> str:
    s = _sadelestir(s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def _insanlastir(ad: str) -> str:
    """`03-veri-akisi` -> `Veri akisi`."""
    ad = re.sub(r"^\d+[-_. ]+", "", ad)
    ad = ad.replace("-", " ").replace("_", " ").strip()
    return ad[:1].upper() + ad[1:] if ad else ad


def _sira_anahtari(yol: Path):
    """Once sayisal onek, sonra ad."""
    m = re.match(r"^(\d+)", yol.name)
    return (int(m.group(1)) if m else 9999, _sadelestir(yol.name))


def _on_bilgi(metin: str) -> tuple[dict, str]:
    """`---` ile cevrili bas bilgiyi ayikla. Yoksa bos sozluk doner."""
    if not metin.startswith("---"):
        return {}, metin
    son = metin.find("\n---", 3)
    if son < 0:
        return {}, metin
    bas = metin[3:son].strip("\n")
    govde = metin[son + 4:].lstrip("\n")
    bilgi: dict[str, str] = {}
    for satir in bas.split("\n"):
        if ":" not in satir or satir.lstrip().startswith("#"):
            continue
        k, _, d = satir.partition(":")
        bilgi[_sadelestir(k.strip())] = d.strip().strip('"').strip("'")
    return bilgi, govde


def _baslik(bilgi: dict, govde: str, yedek: str) -> str:
    if bilgi.get("baslik"):
        return bilgi["baslik"]
    m = re.search(r"^#\s+(.+)$", govde, re.M)
    return m.group(1).strip() if m else _insanlastir(yedek)


# --------------------------------------------------------------------------
# markdown -> html
# --------------------------------------------------------------------------
def _satir_ici(s: str, coz) -> str:
    """Satir ici markdown. `coz(ad) -> (dugum_kimligi|None, gosterilecek_ad)`."""
    kutu: list[str] = []

    def sakla(parca: str) -> str:
        kutu.append(parca)
        return "\x00%d\x00" % (len(kutu) - 1)

    s = re.sub(r"`([^`]+)`",
               lambda m: sakla("<code>%s</code>" % _html.escape(m.group(1), quote=False)), s)
    s = _html.escape(s, quote=False)

    def _wiki(m):
        ham = m.group(1).strip()
        gorunen = ham.split("|", 1)[1].strip() if "|" in ham else ham
        hedef = ham.split("|", 1)[0].strip()
        kimlik, _ = coz(hedef)
        if kimlik:
            return sakla('<span class="ic" data-id="%s">%s</span>'
                         % (_html.escape(kimlik, quote=True), _html.escape(gorunen, quote=False)))
        return sakla('<span class="kirik" title="bulunamadi">%s</span>'
                     % _html.escape(gorunen, quote=False))

    s = re.sub(r"\[\[([^\]]+)\]\]", _wiki, s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               lambda m: sakla('<a href="%s" target="_blank" rel="noopener">%s</a>'
                               % (_html.escape(m.group(2), quote=True), m.group(1))), s)
    s = re.sub(r"(?<![\w/])(https?://[^\s<]+)",
               lambda m: sakla('<a href="%s" target="_blank" rel="noopener">%s</a>'
                               % (_html.escape(m.group(1), quote=True), m.group(1))), s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", s)

    for i, parca in enumerate(kutu):
        s = s.replace("\x00%d\x00" % i, parca)
    return s


def _md(metin: str, coz) -> str:
    """Ihtiyac duyulan kadar markdown: baslik, liste, kod, alinti, cizgi."""
    satirlar = metin.split("\n")
    cikti: list[str] = []
    paragraf: list[str] = []
    liste_etiket: str | None = None
    i = 0

    def paragrafi_kapat():
        nonlocal paragraf
        if paragraf:
            cikti.append("<p>%s</p>" % _satir_ici(" ".join(paragraf), coz))
            paragraf = []

    def listeyi_kapat():
        nonlocal liste_etiket
        if liste_etiket:
            cikti.append("</%s>" % liste_etiket)
            liste_etiket = None

    while i < len(satirlar):
        ham = satirlar[i]
        s = ham.strip()

        if s.startswith("```"):                       # kod blogu
            paragrafi_kapat(); listeyi_kapat()
            i += 1
            kod = []
            while i < len(satirlar) and not satirlar[i].strip().startswith("```"):
                kod.append(satirlar[i]); i += 1
            i += 1
            cikti.append("<pre><code>%s</code></pre>"
                         % _html.escape("\n".join(kod), quote=False))
            continue

        if not s:
            paragrafi_kapat(); listeyi_kapat(); i += 1; continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            paragrafi_kapat(); listeyi_kapat()
            cikti.append("<hr>"); i += 1; continue

        m = re.match(r"^(#{1,6})\s+(.+)$", s)
        if m:
            paragrafi_kapat(); listeyi_kapat()
            n = min(len(m.group(1)), 3)               # h1-h3 yeter
            cikti.append("<h%d>%s</h%d>" % (n, _satir_ici(m.group(2), coz), n))
            i += 1; continue

        if s.startswith(">"):
            paragrafi_kapat(); listeyi_kapat()
            alinti = []
            while i < len(satirlar) and satirlar[i].strip().startswith(">"):
                alinti.append(satirlar[i].strip()[1:].strip()); i += 1
            cikti.append("<blockquote>%s</blockquote>" % _satir_ici(" ".join(alinti), coz))
            continue

        m = re.match(r"^([-*+]|\d+[.)])\s+(.+)$", s)
        if m:
            paragrafi_kapat()
            etiket = "ol" if m.group(1)[0].isdigit() else "ul"
            if liste_etiket != etiket:
                listeyi_kapat()
                cikti.append("<%s>" % etiket)
                liste_etiket = etiket
            cikti.append("<li>%s</li>" % _satir_ici(m.group(2), coz))
            i += 1; continue

        listeyi_kapat()
        paragraf.append(s)
        i += 1

    paragrafi_kapat(); listeyi_kapat()
    return "\n".join(cikti)


# --------------------------------------------------------------------------
# agac
# --------------------------------------------------------------------------
@dataclass
class Dugum:
    kimlik: str
    ad: str
    yol: str
    ham: str = ""
    bilgi: dict = field(default_factory=dict)
    cocuklar: list["Dugum"] = field(default_factory=list)
    ust: "Dugum | None" = None
    dal: str = ""
    dal_mi: bool = False
    seviye: int = 0
    derinlik: int = 0          # dal govdesinden itibaren derinlik
    yaprak: int = 1
    aci: float = 0.0
    x: float = 0.0
    y: float = 0.0
    r: float = 4.3


def _dosya_oku(yol: Path) -> tuple[dict, str]:
    try:
        return _on_bilgi(yol.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}, ""


def _agac_kur(dizin: Path, ust: Dugum, dal: str, onek: str) -> None:
    """Bir klasorun icerigini `ust` altina dugum olarak ekler."""
    girisler = sorted([p for p in dizin.iterdir() if not p.name.startswith(".")],
                      key=_sira_anahtari)
    for p in girisler:
        if p.is_dir():
            bilgi, govde = _dosya_oku(p / "_klasor.md")
            kimlik = "%s-%s" % (onek, _kimlik(p.name))
            d = Dugum(kimlik=kimlik,
                      ad=_baslik(bilgi, govde, p.name),
                      yol=str(p.relative_to(KASA)),
                      ham=govde, bilgi=bilgi, ust=ust, dal=dal,
                      seviye=ust.seviye + 1)
            ust.cocuklar.append(d)
            _agac_kur(p, d, dal, kimlik)
        elif p.suffix.lower() in (".md", ".markdown", ".txt"):
            if p.name.startswith("_"):
                continue
            bilgi, govde = _dosya_oku(p)
            d = Dugum(kimlik="%s-%s" % (onek, _kimlik(p.stem)),
                      ad=_baslik(bilgi, govde, p.stem),
                      yol=str(p.relative_to(KASA)),
                      ham=govde, bilgi=bilgi, ust=ust, dal=dal,
                      seviye=ust.seviye + 1)
            ust.cocuklar.append(d)


def _yapraklari_say(d: Dugum) -> int:
    d.yaprak = 1 if not d.cocuklar else sum(_yapraklari_say(c) for c in d.cocuklar)
    return d.yaprak


def _acilari_dagit(d: Dugum, a0: float, a1: float, derinlik: int) -> int:
    """Dilimi cocuklara yaprak sayisiyla orantili bolusturur. En derin katmani doner."""
    d.aci = (a0 + a1) / 2.0
    d.derinlik = derinlik
    en_derin = derinlik
    if not d.cocuklar:
        return en_derin
    toplam = sum(c.yaprak for c in d.cocuklar) or 1
    a = a0
    for c in d.cocuklar:
        pay = (a1 - a0) * (c.yaprak / toplam)
        en_derin = max(en_derin, _acilari_dagit(c, a, a + pay, derinlik + 1))
        a += pay
    return en_derin


def _tara(d: Dugum, liste: list[Dugum]) -> None:
    liste.append(d)
    for c in d.cocuklar:
        _tara(c, liste)


# --------------------------------------------------------------------------
# harita
# --------------------------------------------------------------------------
def harita_uret() -> dict:
    if not NOTLAR.is_dir():
        raise SystemExit("kasa/notlar/ yok — once bir dal klasoru ac.")

    dal_dizinleri = sorted([p for p in NOTLAR.iterdir()
                            if p.is_dir() and not p.name.startswith(".")],
                           key=_sira_anahtari)
    if not dal_dizinleri:
        raise SystemExit("kasa/notlar/ altinda hic dal klasoru yok.")

    kok = Dugum(kimlik="kok", ad="KASA", yol="", seviye=0, r=9.0)
    dallar: list[dict] = []

    for i, p in enumerate(dal_dizinleri):
        bilgi, govde = _dosya_oku(p / "_dal.md")
        kimlik = _kimlik(p.name)
        govde_dugum = Dugum(
            kimlik=kimlik,
            ad=_baslik(bilgi, govde, p.name),
            yol=str(p.relative_to(KASA)),
            ham=govde, bilgi=bilgi, ust=kok, dal=kimlik,
            dal_mi=True, seviye=1, r=24.0,
        )
        kok.cocuklar.append(govde_dugum)
        _agac_kur(p, govde_dugum, kimlik, kimlik)
        dallar.append({
            "id": kimlik,
            "ad": bilgi.get("ad") or govde_dugum.ad,
            "alt": bilgi.get("alt", ""),
            "renk": bilgi.get("renk") or RENKLER[i % len(RENKLER)],
            "simge": bilgi.get("simge") or SIMGELER[i % len(SIMGELER)],
        })

    # --- yerlesim: her dal kendi govdesinden acilan isinsal agac ---
    n = len(kok.cocuklar)
    dilim = 2 * math.pi / n
    baslangic = -math.pi / 2 - dilim / 2          # iki dal tepenin iki yanina dussun
    yelpaze = min(YELPAZE, dilim * 2.1)
    _yapraklari_say(kok)

    # 1) Her dalin yelpaze yaricapi: derinlik kadar katman, ama en dis halkada
    #    komsu iki dugum EN_AZ_ARALIK'tan yakin olmayacak kadar genis.
    olculer = []
    for dal_dugum in kok.cocuklar:
        en_derin = _acilari_dagit(dal_dugum, -yelpaze / 2, yelpaze / 2, 0)
        gereken = EN_AZ_ARALIK * max(dal_dugum.yaprak, 1) / yelpaze
        capi = min(max(KATMAN * max(en_derin, 1), gereken), EN_GENIS)
        olculer.append((en_derin, capi))

    # 2) Govde cemberi: en genis yelpaze komsusuna degmeyecek kadar acilsin.
    en_genis = max(c for _, c in olculer)
    gerekli = n * 2 * en_genis * math.sin(yelpaze / 2) * 1.15 / (2 * math.pi) - en_genis
    govde_yaricap = max(TABAN_YARICAP, gerekli)

    for i, dal_dugum in enumerate(kok.cocuklar):
        en_derin, capi = olculer[i]
        yon = baslangic + i * dilim
        gx = math.cos(yon) * govde_yaricap
        gy = math.sin(yon) * govde_yaricap

        icerik: list[Dugum] = []
        _tara(dal_dugum, icerik)
        for d in icerik:
            yerel = capi * (d.derinlik / max(en_derin, 1))
            aci = yon + d.aci                     # d.aci govdeye GORE sapma
            d.x = gx + math.cos(aci) * yerel
            d.y = gy + math.sin(aci) * yerel
            if not d.dal_mi:
                d.r = 6.0 if d.seviye == 2 else 5.0

        etiket = govde_yaricap + capi + ETIKET_PAYI
        dallar[i]["ex"] = math.cos(yon) * etiket
        dallar[i]["ey"] = math.sin(yon) * etiket

    hepsi: list[Dugum] = []
    _tara(kok, hepsi)

    # --- capraz bag cozumu: kimlik, baslik ve dosya adi uzerinden ---
    dizin: dict[str, str] = {}
    for d in hepsi:
        if d.seviye == 0:
            continue
        for anahtar in (d.kimlik, _kimlik(d.ad), _kimlik(Path(d.yol).stem)):
            dizin.setdefault(anahtar, d.kimlik)

    baglar: set[tuple[str, str]] = set()
    govde_ciftleri = {(d.ust.kimlik, d.kimlik) for d in hepsi if d.ust}

    def coz_uret(kaynak: Dugum):
        def coz(ad: str):
            hedef = dizin.get(_kimlik(ad))
            if hedef and hedef != kaynak.kimlik:
                cift = (kaynak.kimlik, hedef)
                ters = (hedef, kaynak.kimlik)
                if cift not in govde_ciftleri and ters not in govde_ciftleri:
                    baglar.add(cift if cift < ters else ters)
            return hedef, ad
        return coz

    dugumler = []
    for d in hepsi:
        govde_html = _md(d.ham, coz_uret(d)) if d.ham else ""
        etiketler = [t.strip() for t in re.split(r"[,\s]+", d.bilgi.get("etiketler", "")) if t.strip()]
        dugumler.append({
            "id": d.kimlik,
            "ad": d.ad,
            "dal": d.dal,
            "dalMi": d.dal_mi,
            "seviye": d.seviye,
            "ust": d.ust.kimlik if d.ust else None,
            "yol": d.yol,
            "durum": _sadelestir(d.bilgi.get("durum", "")),
            "etiketler": etiketler,
            "govde": govde_html,
            "arama": _sadelestir(d.ad + " " + re.sub(r"<[^>]+>", " ", govde_html))[:1400],
            "x": round(d.x, 1), "y": round(d.y, 1), "r": round(d.r, 1),
        })

    return {
        "uretim": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "dallar": dallar,
        "dugumler": dugumler,
        "kenarlar": [[d.ust.kimlik, d.kimlik] for d in hepsi if d.ust],
        "baglar": [list(c) for c in sorted(baglar)],
    }


def yaz(hedef: Path | None = None) -> Path:
    veri = harita_uret()
    sablon = SABLON.read_text(encoding="utf-8")
    gomulu = json.dumps(veri, ensure_ascii=False).replace("<", "\\u003c")
    html = sablon.replace("VERI_JSON", gomulu)
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(html, encoding="utf-8")
    yol = CIKTI
    if hedef:
        hedef.mkdir(parents=True, exist_ok=True)
        yol = hedef / CIKTI.name
        shutil.copy2(CIKTI, yol)
    print("%d dugum, %d dal, %d capraz bag -> %s (%.0f KB)"
          % (len(veri["dugumler"]), len(veri["dallar"]), len(veri["baglar"]),
             yol, len(html) / 1024))
    return yol


def _masaustu() -> Path:
    """Masaustu klasorunu bul.

    Windows'ta Masaustu cogu kurulumda OneDrive'a tasinmis oluyor; ev
    dizininde `Desktop` DIYE BIR SEY OLMUYOR. Once gercekten var olan
    adaylara bakilir, hicbiri yoksa `~/Desktop` acilir.
    """
    ev = Path.home()
    adaylar = [ev / "Desktop", ev / "Masaüstü", ev / "Masaustu"]
    for bulut in sorted(ev.glob("OneDrive*")):        # OneDrive, OneDrive - Sirket
        adaylar += [bulut / "Desktop", bulut / "Masaüstü", bulut / "Masaustu"]
    for aday in adaylar:
        if aday.is_dir():
            return aday
    return ev / "Desktop"


def sun(port: int) -> None:
    """Her istekte haritayi yeniden uretip sunar — not yazarken F5 yeter."""
    import http.server
    import socketserver

    class Isleyici(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(KASA), **k)

        def do_GET(self):
            if self.path in ("/", "/index.html", "/harita.html"):
                try:
                    yaz()
                except SystemExit as e:
                    self.send_error(500, str(e)); return
                self.path = "/harita.html"
            return super().do_GET()

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("127.0.0.1", port), Isleyici) as s:
        print("kasa: http://127.0.0.1:%d  (durdurmak icin Ctrl+C)" % port)
        try:
            s.serve_forever()
        except KeyboardInterrupt:
            print()


def main() -> None:
    ayrastirici = argparse.ArgumentParser(description="Kasa — bilgi haritasi uretici")
    alt = ayrastirici.add_subparsers(dest="komut")

    p = alt.add_parser("yap", help="harita.html uret")
    p.add_argument("--ac", action="store_true", help="uretince tarayicida ac")
    p.add_argument("--hedef", help="ayrica bu dizine kopyala")

    m = alt.add_parser("masaustu", help="uret ve Masaustu'ne kopyala")
    m.add_argument("--ac", action="store_true")

    s = alt.add_parser("sun", help="yerel sunucu (her istekte yeniden uretir)")
    s.add_argument("--port", type=int, default=8787)

    a = ayrastirici.parse_args()
    komut = a.komut or "yap"

    if komut == "sun":
        sun(a.port)
        return

    hedef = _masaustu() if komut == "masaustu" else (Path(a.hedef).expanduser() if a.hedef else None)
    yol = yaz(hedef)
    if getattr(a, "ac", False):
        import webbrowser
        webbrowser.open(yol.resolve().as_uri())


if __name__ == "__main__":
    main()
