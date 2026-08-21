#!/bin/bash
# Sofascore toplayicisini Mac'te 7/24 calisacak sekilde kurar.
#
# NEDEN GEREKLI: Sofascore veri merkezi IP'lerini engelliyor (GitHub Actions
# 403, Cloudflare Worker 403 -- olculdu). Gecen tek yer bu Mac'in ev IP'si.
# Toplayici veriyi cekip Cloudflare KV'ye birakir, bot oradan okur.
#
# NEDEN sudo: ~/Library/LaunchAgents bu makinede root'a ait (normalde
# kullaniciya ait olur). Sahipligi duzeltmek icin bir kez sudo gerekiyor.
set -e
PLIST="$HOME/Library/LaunchAgents/com.nesine.sofa.plist"
KAYNAK="$HOME/nesine-bot/launchd/com.nesine.sofa.plist"

if [ ! -w "$HOME/Library/LaunchAgents" ]; then
  echo "→ ~/Library/LaunchAgents root'a ait, sahiplik duzeltiliyor (sifre isteyecek)"
  sudo chown -R "$USER":staff "$HOME/Library/LaunchAgents"
fi

cp "$KAYNAK" "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✓ kuruldu. 180 saniyede bir calisacak."
echo
sleep 12
echo "— ilk calisma —"
tail -3 "$HOME/nesine-bot/logs/sofa.log" 2>/dev/null || echo "(henuz log yok, birkac saniye bekle)"
tail -3 "$HOME/nesine-bot/logs/sofa.err" 2>/dev/null || true
echo
echo "Durdurmak icin:  launchctl unload $PLIST"
