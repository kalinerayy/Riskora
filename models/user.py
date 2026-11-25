"""Usuários, perfis e permissões.

As permissões são verificadas nos SERVIÇOS (backend). A interface apenas esconde o que o perfil não pode usar.
"""
from __future__ import annotations

from dataclasses import dataclass

GUEST_EMAIL = "visitante@riskora.local"
GUEST_NAME = "Visitante"

ROLES = {
    "admin": "Administrador",
    "manager": "Gestor",
    "analyst": "Analista",
    "reader": "Leitor",
    "guest": "Visitante",
}
# Perfis que um administrador pode atribuir a usuários reais. O perfil "guest" é só do acesso de visitante.
ASSIGNABLE_ROLES = tuple(role for role in ROLES if role != "guest")

PERMISSIONS = {
    "data:read": "Consultar ativos, avaliações, riscos, tratamentos e dashboard",
    "asset:write": "Cadastrar, editar e desativar ativos",
    "assessment:run": "Iniciar, responder e concluir avaliações",
    "treatment:write": "Registrar e atualizar ações de tratamento e evidências",
    "treatment:validate": "Validar ações e registrar risco residual",
    "report:export": "Gerar e exportar relatórios",
    "user:manage": "Gerenciar usuários e perfis da organização",
    "org:manage": "Editar dados da organização",
    "audit:read": "Consultar registros de auditoria",
}

ROLE_PERMISSIONS = {
    "admin": frozenset(PERMISSIONS),
    "manager": frozenset({"data:read", "treatment:validate", "report:export"}),
    "analyst": frozenset({"data:read", "asset:write", "assessment:run", "treatment:write", "report:export"}),
    "reader": frozenset({"data:read", "report:export"}),
    # Visitante: pode cadastrar, avaliar, tratar e validar, mas NÃO gerencia usuários, organização nem auditoria.
    "guest": frozenset(PERMISSIONS) - {"user:manage", "org:manage", "audit:read"},
}


@dataclass(frozen=True)
class Context:
    """Quem está agindo, em qual organização e com quais permissões. Criado no servidor a cada requisição."""
    user_id: int
    email: str
    full_name: str
    org_id: int
    role: str
    permissions: frozenset

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def is_guest(self) -> bool:
        return (self.email or "").lower() == GUEST_EMAIL
