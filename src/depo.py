"""Veri yazma kilidi — git cakismalarini onlemek icin.

KURAL: `data/` altina YALNIZCA GitHub Actions yazar. Yerelde (gelistirme
sirasinda) her sey okunabilir ve hesaplanabilir ama HICBIR SEY yazilmaz.

NEDEN: veri dosyalari hem yerelden hem Actions'tan yazilinca rebase
cakismasi cikti (2 kez), bir kez `reset --hard` yeni kod dosyalarini
sildi (reflog'dan kurtarildi).

Actions'ta `CI=true` ortam degiskeni otomatik tanimlidir. Yerelde bilerek
yazmak gerekirse `NESINE_YAZ=1` verilir.
"""
from __future__ import annotations

import os
from pathlib import Path


def yazilabilir() -> bool:
    if os.environ.get("NESINE_YAZ") == "1":
        return True
    return os.environ.get("CI", "").lower() == "true"


def yaz(yol: Path, icerik: str, encoding: str = "utf-8") -> bool:
    """Dosyaya yaz. Kilit aciksa yazmaz, False doner."""
    if not yazilabilir():
        return False
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(icerik, encoding=encoding)
    return True


def ekle(yol: Path, satir: str, encoding: str = "utf-8") -> bool:
    """Dosyaya satir ekle (jsonl). Kilit aciksa eklemez."""
    if not yazilabilir():
        return False
    yol.parent.mkdir(parents=True, exist_ok=True)
    with yol.open("a", encoding=encoding) as f:
        f.write(satir)
    return True
