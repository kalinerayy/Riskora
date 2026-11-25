"""Privacidade: o visitante nunca vê nomes nem e-mails de pessoas que fazem login.

O visitante pode ver o que ELE e outros visitantes fizeram (rótulo "Visitante"). Qualquer outra identificação de
pessoa (nome ou e-mail de usuários reais) é trocada por um rótulo genérico antes de sair do serviço.
"""
from __future__ import annotations

from models.user import GUEST_EMAIL, GUEST_NAME, Context

PRIVATE_LABEL = "Usuário da organização"


def person_label(ctx: Context, value: str | None) -> str:
    text = value or ""
    if not ctx.is_guest or not text:
        return text
    return text if text in (GUEST_NAME, GUEST_EMAIL) else PRIVATE_LABEL
