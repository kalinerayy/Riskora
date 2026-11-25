"""Autorização no backend: toda operação de serviço chama require() antes de agir."""
from __future__ import annotations

from models.user import PERMISSIONS, Context
from services.errors import PermissionDenied


def require(ctx: Context | None, permission: str) -> Context:
    """Garante que existe um contexto autenticado com a permissão. Sem contexto, a operação falha."""
    if ctx is None:
        raise PermissionDenied("Sessão inválida. Faça login novamente.")
    if permission not in PERMISSIONS:
        raise ValueError(f"Permissão desconhecida: {permission}")  # erro de programação, não do usuário
    if not ctx.has(permission):
        raise PermissionDenied("Seu perfil não permite esta operação.")
    return ctx
