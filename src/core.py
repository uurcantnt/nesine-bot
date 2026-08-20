"""Tek kaynak: mekanizma v1.0 sabitleri. Diger tum moduller buradan okur.

Bu dosyayi degistirmek mekanizmayi degistirmektir -> ON_KAYIT.md kurali geregi
golge sayaci sifirlanir. Once ON_KAYIT.md oku.
"""
from __future__ import annotations

MECHANISM_VERSION = "1.0"
FREEZE_DATE = "2026-08-20"

# --- Dogrulanmis marketler ---------------------------------------------------
# kapsam = her secenegin kactane temel sonucu kapsadigi (cifte sansta 2).
# Kimligi KANITLANMAMIS hicbir MTID buraya girmez; bkz. README "Market kimligi".
MARKETS = {
    1: {"ad": "Maç Sonucu",  "secenek": ["1", "X", "2"],       "kapsam": 1},
    3: {"ad": "Çifte Şans",  "secenek": ["1-X", "1-2", "X-2"], "kapsam": 2},
}

# --- Secim mekanizmasi (v1.0, DONDURULMUS) -----------------------------------
LIMITS = {
    "MAX_OVERROUND": 0.22,     # bundan pahali market elenir
    "MIN_ODD": 1.20,           # altinda oran onerilmez
    "MAX_ODD": 6.00,           # ustunde oran onerilmez
    "MIN_SAAT": 2,             # maca en az bu kadar saat kalmali
    "MAX_SAAT": 48,            # bu kadar saatten uzagi onerilmez
    "MAX_BACAK": 3,            # kupon en fazla bu kadar mac
    "GUNLUK_PUSH": 1,          # gunde kac oneri gonderilir
    "STAKE_TL": 20.0,          # oneri basina sabit tutar
    "AYLIK_KAYIP_TAVANI_TL": 400.0,   # asilirsa bot oneri gondermez
}

# Sadece futbol (TYPE==1). Diger sporlar v1.0 kapsaminda degil.
FUTBOL = 1
