# Mekanizma v1.0 — DONDURULDU

**Dondurulma tarihi:** 2026-08-20
**Kod hash (core.py + odds.py + coupon.py, sha256 ilk 16):** `3387c12c8132a63c`

Bu dosya sartnamedir. `src/core.py` veya `src/coupon.py` degistirilirse hash tutmaz;
o durumda ON_KAYIT.md geregi **golge sayaci sifirlanir**.

## Ne yapar

Mekanizma **kazanan mac tahmin etmez.** Oyle bir yetenegi yok ve olmadigi olculdu.

Optimize ettigi sey **maliyettir**: ayni bahsi en ucuz markette, en az bacakla,
en yuksek isabet olasiligiyla oynatmak.

## Adimlar

1. **Havuz** — futbol (TYPE=1), market durumu acik (MS=1), baslangic
   [simdi+2sa, simdi+48sa].
2. **Market filtresi** — yalnizca kimligi KANITLANMIS marketler:
   `MTID=1` Mac Sonucu, `MTID=3` Cifte Sans. Digerleri kapsam disi.
3. **Marj kapisi** — overround > %22 olan market elenir.
4. **Devig** — carpimsal normalizasyon. Her marketten **en yuksek olasilikli**
   secenek alinir; orani [1.20, 6.00] disindaysa elenir.
5. **Siralama** — marj ARTAN, esitlikte olasilik AZALAN.
6. **Paket** — MBS=1 aday varsa TEK bahis. Kullanici N bacak isterse en ucuz
   N mac (ayni mac iki bacakta olamaz), en fazla 3 bacak.

## Sabitler (`core.LIMITS` tek kaynak)

| Ayar | Deger |
|---|---|
| MAX_OVERROUND | %22 |
| MIN_ODD / MAX_ODD | 1.20 / 6.00 |
| MIN_SAAT / MAX_SAAT | 2 / 48 |
| MAX_BACAK | 3 |
| GUNLUK_PUSH | 1 |
| STAKE_TL | 20 |
| AYLIK_CIRO_TAVANI_TL | 400 |

## Devig yontemi

Carpimsal (multiplicative). Power ve Shin yontemleri v1.0 kapsami DISINDA —
sonradan "daha iyi sonuc verdigi icin" degistirilirse bu, sonuca gore
parametre secmektir (BtcTurk botunda reddedilen davranis).

## Olculen gercekler (2026-08-20, n=936 acik 1X2 marketi)

- Mac Sonucu marji: medyan **%21,05** (min %17,05 / maks %21,73)
- Tek bahiste beklenen getiri: **-%17,4**
- Kupon marji carpimsal: 3 bacak **-%43,6**, 5 bacak -%61,5, 10 bacak -%85,2
- MBS dagilimi: tek mac oynanabilen 169 · min 2 mac 218 · **min 3 mac 549**
- Basabas icin gereken goreli CLV = marjin kendisi = **%21,05**
