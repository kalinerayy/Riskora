"""Registro de eventos relevantes. Não recebe nem grava senhas, tokens ou conteúdo de respostas."""
from __future__ import annotations

from database.repositories.audit import AuditRepository
from models.user import Context
from services.authorization_service import require


class AuditService:
    def __init__(self, conn):
        self.conn = conn
        self.repo = AuditRepository(conn)

    def log(self, org_id, user_id, action, entity_type="", entity_id=None, detail="") -> None:
        """Grava na transação corrente do chamador (o commit é de quem orquestra)."""
        self.repo.add(org_id, user_id, action, entity_type, entity_id, detail)

    def log_ctx(self, ctx: Context, action, entity_type="", entity_id=None, detail="") -> None:
        self.log(ctx.org_id, ctx.user_id, action, entity_type, entity_id, detail)

    def list_events(self, ctx: Context, limit=200):
        require(ctx, "audit:read")
        return self.repo.list_for_org(ctx.org_id, limit)
