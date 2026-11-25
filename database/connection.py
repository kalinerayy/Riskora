"""Conexão com o SQLite e inicialização (migrações + carga do catálogo)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import load_settings


def get_connection(db_path=None) -> sqlite3.Connection:
    if db_path == ":memory:":
        target = ":memory:"
    else:
        path = Path(db_path) if db_path else load_settings().db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        target = str(path)
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database(conn: sqlite3.Connection) -> list[str]:
    """Aplica migrações pendentes e carrega dados fixos (perfis, categorias, módulos, controles)."""
    from database.migrate import apply_migrations
    from database.seed import seed_all

    applied = apply_migrations(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    with conn:
        seed_all(conn)
    return applied
