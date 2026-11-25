"""Base dos repositórios: SQL SEMPRE parametrizado. Repositórios não fazem commit nem decidem permissão."""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Sequence


def placeholders(n: int) -> str:
    return ",".join("?" * n)


def like_pattern(term: str) -> str:
    """Escapa curingas do LIKE para que a busca do usuário seja tratada como texto literal."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class BaseRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _one(self, sql: str, params: Sequence[Any] = ()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def _all(self, sql: str, params: Sequence[Any] = ()):
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def _in(self, ids: Iterable[int]) -> list[int]:
        return list(ids)
