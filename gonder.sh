#!/bin/bash
# GUVENLI PUSH — commit'i ASLA atmaz.
#
# ONCEKI DONGU YANLISTI ve UC COMMIT KAYBETTIRDI (2026-08-22):
#     git push || { git reset --hard origin/main; }
# push basarisiz olunca reset commit'i ATIYORDU; sonraki turda
# "gonderilecek bir sey yok" durumu `git push` icin BASARI sayiliyor ve
# ekrana "push tamam" yaziliyordu. Yani veri kaybi SESSIZ, ustelik
# BASARI diye raporlaniyordu.
#
# Dogrusu: uzagi cek, commit'i onun USTUNE tasi (rebase), oyle gonder.
# Cakisma olursa DUR ve soyle -- sessizce bir sey atma.
set -e
for i in 1 2 3; do
  git fetch origin main -q
  if git rebase origin/main -q 2>/dev/null; then
    if git push -q 2>/dev/null; then
      echo "push tamam ($i. deneme)"; exit 0
    fi
  else
    echo "rebase cakismasi — geri alindi, commit KORUNDU"
    git rebase --abort 2>/dev/null || true
  fi
  sleep $((i * 4))
done
echo "PUSH EDILEMEDI — commit yerelde DURUYOR, kaybolmadi"
exit 1
