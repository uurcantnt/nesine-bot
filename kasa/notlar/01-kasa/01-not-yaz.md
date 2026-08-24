---
baslik: Not yaz
durum: tamam
etiketler: temel
---

# Not yaz

Bir not = bir `.md` dosyasi. `kasa/notlar/` altinda hangi klasore koyarsan
haritada o dalin altinda cikar. Baska kural yok.

Dosyanin en ustune istege bagli bas bilgi koyabilirsin:

```
---
baslik: Gorunecek ad
durum: tamam
etiketler: para, acil
---

Notun govdesi buradan baslar.
```

Bas bilgi yoksa:

- **baslik** ilk `# Baslik` satirindan, o da yoksa dosya adindan turer.
- **durum** bos kalir (haritada dolu krem nokta olarak cizilir).

Dosya adinin basina sayi koyarsan siralama ona gore olur: `01-...`, `02-...`.
Sayi haritada gorunmez, sadece siralar.

Desteklenen isaretleme: baslik (`#`, `##`, `###`), liste, numarali liste,
kalin (`**`), egik (`*`), `kod`, ``` blok, `> alinti`, `---` cizgi, baglantı
ve [[Baglar|koseli parantezli ic bag]].
