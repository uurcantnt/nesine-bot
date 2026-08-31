#!/bin/bash
# GUVENLI PUSH — commit'i ASLA atmaz, HER ZAMAN main'e gonderir.
#
# IKI HATA BURADA COZULDU:
# 1) `git push || git reset --hard origin/main` kalibi UC COMMIT
#    KAYBETTIRDI (2026-08-22): push basarisiz olunca reset commit'i
#    atiyordu, sonraki turda "gonderilecek sey yok" BASARI sayilip
#    ekrana "push tamam" yaziliyordu. Kayip SESSIZ ve BASARI diye
#    raporlaniyordu.
# 2) Cikplak `git push` MEVCUT BRANCH'i kendi upstream'ine gonderir.
#    Ortam `claude/...` gibi bir branch olusturunca push main'e DEGIL
#    oraya gidiyordu; bot ise Actions'ta main'den kosuyor (ref: main).
#    Artik hedef ACIKCA main.
set -e
# Kaydedilmemis degisiklik varsa rebase "cakisma" gibi gorunen ama aslinda
# "unstaged changes" olan bir hata veriyordu -- mesaj yaniltiyordu.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "DURDU: kaydedilmemis degisiklik var, once commit et:"
  git status --short | head -10
  exit 1
fi
for i in 1 2 3; do
  git fetch origin main -q
  if git rebase origin/main -q 2>/dev/null; then
    if git push origin HEAD:main -q 2>/dev/null; then
      echo "push tamam ($i. deneme, hedef: main)"; exit 0
    fi
  else
    echo "rebase cakismasi — geri alindi, commit KORUNDU"
    git rebase --abort 2>/dev/null || true
  fi
  sleep $((i * 4))
done
echo "PUSH EDILEMEDI — commit yerelde DURUYOR, kaybolmadi"
exit 1
