"""Cópia de segurança do banco SQLite (usa a API de backup do SQLite, segura mesmo com o app aberto).

Uso:  python -m scripts.backup_db        (grava em backups/riskora-AAAAMMDD-HHMMSS.db)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from config.settings import BASE_DIR, load_settings


def main() -> int:
    source_path = load_settings().db_path
    if not source_path.exists():
        print("Banco ainda não existe; nada a copiar.")
        return 1
    target_dir = BASE_DIR / "backups"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f"riskora-{datetime.now():%Y%m%d-%H%M%S}.db"
    src, dst = sqlite3.connect(str(source_path)), sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"Backup criado: {target}\nGuarde-o em local protegido: contém dados da organização.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
