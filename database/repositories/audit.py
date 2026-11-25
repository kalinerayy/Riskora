"""Registro de auditoria. Nunca grava senhas, tokens ou conteúdo sensível."""
from __future__ import annotations

from database.repositories.base import BaseRepository


class AuditRepository(BaseRepository):
    def add(self, org_id, user_id, action, entity_type="", entity_id=None, detail="") -> int:
        cur = self.conn.execute(
            "INSERT INTO audit_logs (organization_id, user_id, action, entity_type, entity_id, detail) "
            "VALUES (?,?,?,?,?,?)", (org_id, user_id, action, entity_type, entity_id, detail[:500]))
        return cur.lastrowid

    def list_for_org(self, org_id, limit=200):
        return self._all(
            "SELECT a.*, u.email AS user_email FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id "
            "WHERE a.organization_id=? ORDER BY a.id DESC LIMIT ?", (org_id, int(limit)))
