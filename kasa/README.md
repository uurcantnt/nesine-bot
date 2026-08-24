# Kasa

Masaustunde calisan, tek dosyalik bilgi haritasi. Notlar duz markdown;
harita onlardan uretilir.

```
python3 src/kasa.py masaustu     # harita.html uret + Masaustu'ne kopyala
python3 src/kasa.py yap --ac     # uret ve tarayicida ac
python3 src/kasa.py sun          # http://127.0.0.1:8787 (her F5'te yeniden uretir)
```

Cikan `harita.html` KENDI KENDINE YETER: butun notlar, yerlesim ve arayuz
icine gomulu. Internet, sunucu, kurulum, hesap gerekmez — cift tiklayip
acarsin, cevrimdisi calisir. Baska bilgisayara tasimak icin tek bu dosyayi
kopyalaman yeter.

Python 3.11 ve standart kutuphane disinda bagimlilik yok.

## Yapi

```
kasa/
  notlar/                  <- SENIN icerigin
    01-kasa/               <- klasor = dal (haritadaki halkali govde)
      _dal.md              <- dalin adi/rengi/simgesi (dugum degil)
      01-not-yaz.md        <- dosya = not (haritadaki nokta)
      07-ipuclari/         <- ic ice klasor = agac bir kat uzar
        _klasor.md         <- ara klasorun basligi (dugum degil)
        01-kisayollar.md
  _sablon/harita.html      <- arayuz sablonu
  harita.html              <- URETILEN dosya, elle duzenleme
```

Alt cizgiyle baslayan dosyalar (`_dal.md`, `_klasor.md`) ust bilgidir,
haritada dugum olarak cikmaz. Dosya adinin basindaki sayi (`03-`) yalnizca
siralar, gorunmez.

## Not bicimi

```markdown
---
baslik: Gorunecek ad
durum: tamam | devam | plan
etiketler: para, acil
---

Govde. **Kalin**, *egik*, `kod`, liste, > alinti, --- cizgi calisir.
Baska bir nota bag: [[Dal ac]] veya [[Dal ac|farkli metinle]].
```

Bas bilgi zorunlu degil. Yoksa baslik ilk `# Baslik` satirindan, o da yoksa
dosya adindan turer.

`_dal.md` icin ek alanlar: `ad`, `alt` (baslik altindaki ince yazi),
`renk` (`#4ecdc4`), `simge` (tek karakter).

## Arayuz

- **surukle** kaydir, **tekerlek/kistir** yaklas, **tikla** notu ac
- **cift tikla** odaklan (dal govdesinde: tum dala)
- **/** ara, **f** sigdir, **sol/sag ok** dallar arasi gez, **Esc** kapat
- **LISTE** sekmesi ayni icerigin duz listesi

`durum` haritada goruntuyu belirler: `tamam` dolu nokta, `devam` dolu nokta +
dal renginde halka, `plan` ici bos halka.

## Yedek

`kasa/notlar/` klasorunu kopyalamak yedek almaktir; ozel bicim yok. Notlar
git'te surumleniyor. `harita.html` uretilen dosyadir, kaybolursa `yap` geri
getirir.

Detayli anlatim haritanin **Kasa** dalinda; oradan okumak icin once bir
harita uret.
