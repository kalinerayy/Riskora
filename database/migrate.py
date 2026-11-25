"""Executor simples de migrações: arquivos NNN_nome.sql aplicados em ordem, uma única vez cada.

Cada migração roda dentro de uma transação: se algo falhar, nada daquela migração fica aplicado.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME = re.compile(r"^\d{3}_[a-z0-9_]+$")


def apply_migrations(conn: sqlite3.Connection, directory: Path | None = None) -> list[str]:
    """Aplica as migrações pendentes e devolve a lista das versões aplicadas nesta chamada."""
    directory = directory or MIGRATIONS_DIR
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                 "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')))")
    conn.commit()
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    done: list[str] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        version = path.stem
        if not _NAME.match(version):
            raise ValueError(f"Nome de migração inválido: {path.name}")
        if version in applied:
            continue
        script = ("BEGIN;\n" + path.read_text(encoding="utf-8") +
                  f"\nINSERT INTO schema_migrations (version) VALUES ('{version}');\nCOMMIT;")
        try:
            conn.executescript(script)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        done.append(version)
    return done
