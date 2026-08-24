---
baslik: Harita uret
durum: tamam
etiketler: temel, komut
---

# Harita uret

Notlar duz metin; harita onlardan URETILIR. Uc komut var:

```
python3 src/kasa.py yap          # kasa/harita.html uret
python3 src/kasa.py yap --ac     # uret ve tarayicida ac
python3 src/kasa.py masaustu     # uret ve Masaustu'ne kopyala
python3 src/kasa.py sun          # http://127.0.0.1:8787
```

`yap` tek bir dosya cikarir: `kasa/harita.html`. Bu dosya kendi kendine
yeter — icinde butun notlar, yerlesim ve arayuz gomulu. Internet, sunucu,
kurulum gerekmez. Baska bilgisayara tasimak icin tek bu dosyayi kopyala.

`sun` not yazarken kullanilir: her yenilemede haritayi bastan uretir, yani
notu kaydet + F5 yeter.

Python 3.11 ve standart kutuphane disinda hicbir sey gerekmiyor.
