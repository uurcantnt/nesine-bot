---
baslik: Dal ac
durum: tamam
etiketler: temel
---

# Dal ac

`kasa/notlar/` altindaki HER KLASOR bir daldir — haritadaki halkali
govdelerden biri. Yeni dal acmak icin klasor acmak yeterli:

```
kasa/notlar/07-hukuk/
```

Adini, rengini ve simgesini vermek istersen icine `_dal.md` koy:

```
---
ad: Hukuk
alt: sozlesme · dava · uyum
renk: #7fb069
simge: ◆
---
```

`_dal.md` haritada AYRI bir dugum olmaz; dalin ust bilgisidir. Vermezsen
renk ve simge sirayla otomatik dagitilir.

Ic ice klasor de acabilirsin — o zaman agac bir kat daha uzar. Ara klasore
baslik vermek istersen icine `_klasor.md` koy; o da dugum degil, ust bilgidir.

Alt cizgiyle baslayan (`_`) her dosya bu yuzden haritada gorunmez.

Dal sayisi arttikca daire kalabaliklasir; 5 ile 9 arasi iyi durur.
Devami: [[Harita uret]].
