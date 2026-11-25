"""Acesso de visitante: entrar SEM cadastro, somente na organização de demonstração (dados fictícios).

Como funciona e por que é seguro o suficiente para uma demonstração:
- Ligado por padrão. Para desligar: RISKORA_GUEST_ACCESS=off.
- O visitante é um usuário comum ("visitante@riskora.local") com senha aleatória que ninguém conhece:
  não dá para entrar com senha, apenas pelo botão "Entrar como visitante".
- Pertence SOMENTE à organização de demonstração. Os dados reais de outras organizações ficam inacessíveis.
- O perfil padrão é "Visitante": pode cadastrar, avaliar, tratar e validar na demonstração, mas não gerencia
  usuários, organização nem auditoria, e nunca é administrador.
- Privacidade: o visitante nunca vê nome nem e-mail de quem faz login (services/privacy.py).
- Todos os visitantes compartilham a mesma organização de demonstração; o administrador pode restaurá-la
  com scripts/reset_demo.py.
"""
from __future__ import annotations

import secrets

from database.repositories.accounts import AccountRepository
from models.user import GUEST_EMAIL, GUEST_NAME, ROLES
from services.authentication_service import AuthenticationService
from services.demo_data import load_demo
from services.errors import RiskoraError


class GuestAccessService:
    def __init__(self, conn, auth: AuthenticationService | None = None):
        self.conn = conn
        self.auth = auth or AuthenticationService(conn)
        self.repo = AccountRepository(conn)

    @property
    def enabled(self) -> bool:
        return self.auth.settings.guest_access

    def description(self) -> str:
        """Texto exibido na tela de login, conforme o perfil configurado."""
        role = self.auth.settings.guest_role
        if role == "reader":
            return "Explore a organização de demonstração (dados fictícios) em modo somente leitura."
        

    @staticmethod
    def is_guest(email: str) -> bool:
        return (email or "").lower() == GUEST_EMAIL

    def enter(self) -> str:
        """Prepara (se preciso) o visitante e a demonstração e devolve o token de uma nova sessão."""
        if not self.enabled:
            raise RiskoraError("O acesso de visitante não está habilitado.")
        org_id = load_demo(self.conn)
        role = self.auth.settings.guest_role
        user = self.repo.get_user_by_email(GUEST_EMAIL)
        if user is not None and user["status"] != "Ativo":
            raise RiskoraError("O acesso de visitante está desativado.")
        with self.conn:
            if user is None:
                user_id = self.repo.create_user(GUEST_EMAIL, GUEST_NAME,
                                                self.auth.hash_password(secrets.token_urlsafe(48)), False)
            else:
                user_id = user["id"]
            member = self.repo.get_membership(org_id, user_id)
            if member is None:
                self.repo.add_member(org_id, user_id, role)
            elif member["role_code"] != role:
                self.repo.set_member_role(org_id, user_id, role)
            for m in self.repo.list_memberships_for_user(user_id):  # o visitante nunca pertence a outra organização
                if m["organization_id"] != org_id:
                    self.repo.remove_member(m["organization_id"], user_id)
        return self.auth.start_session(user_id, "guest_login")
