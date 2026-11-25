"""Organização e usuários da organização.

create_organization() NÃO tem verificação de permissão porque é de uso restrito a scripts de administração
(scripts/create_admin.py, scripts/load_demo.py). A interface não a expõe na versão 1.
"""
from __future__ import annotations

from database.repositories.accounts import AccountRepository
from models.organization import ORG_STATUSES
from models.user import ASSIGNABLE_ROLES, Context
from services.audit_service import AuditService
from services.authentication_service import AuthenticationService
from services.authorization_service import require
from services.clock import to_iso, utcnow
from services.errors import NotFoundError, RiskoraError
from services.validation import clean_email, clean_slug, clean_text, require_choice


class OrganizationService:
    def __init__(self, conn, auth: AuthenticationService | None = None):
        self.conn = conn
        self.repo = AccountRepository(conn)
        self.audit = AuditService(conn)
        self.auth = auth or AuthenticationService(conn)

    # -- organização -----------------------------------------------------------------------
    def create_organization(self, name, slug, business_description="", context="", responsible="", is_demo=False) -> int:
        slug = clean_slug(slug)
        if self.repo.get_organization_by_slug(slug):
            raise RiskoraError("Já existe uma organização com esta identificação.")
        with self.conn:
            org_id = self.repo.create_organization(
                clean_text(name, "Nome da organização", 200, required=True), slug,
                clean_text(business_description, "Descrição do negócio", 2000),
                clean_text(context, "Contexto organizacional", 4000),
                clean_text(responsible, "Responsável", 200), "Ativa", is_demo)
            self.audit.log(org_id, None, "organization_created", "organization", org_id)
        return org_id

    def get_organization(self, ctx: Context) -> dict:
        require(ctx, "data:read")
        org = self.repo.get_organization(ctx.org_id)
        if not org:
            raise NotFoundError("Organização não encontrada.")
        return org

    def update_organization(self, ctx: Context, name, business_description, context, responsible, status) -> None:
        require(ctx, "org:manage")
        with self.conn:
            self.repo.update_organization(
                ctx.org_id, clean_text(name, "Nome da organização", 200, required=True),
                clean_text(business_description, "Descrição do negócio", 2000),
                clean_text(context, "Contexto organizacional", 4000), clean_text(responsible, "Responsável", 200),
                require_choice(status, ORG_STATUSES, "Situação"), to_iso(utcnow()))
            self.audit.log_ctx(ctx, "organization_updated", "organization", ctx.org_id)

    # -- usuários ----------------------------------------------------------------------------
    def list_members(self, ctx: Context) -> list[dict]:
        require(ctx, "user:manage")
        return self.repo.list_members(ctx.org_id)

    def create_user(self, ctx: Context, email, full_name, role, temp_password) -> tuple[int, bool]:
        """Provisiona um usuário na organização do administrador. Devolve (user_id, criado_agora)."""
        require(ctx, "user:manage")
        email = clean_email(email)
        role = require_choice(role, ASSIGNABLE_ROLES, "Perfil")
        full_name = clean_text(full_name, "Nome", 120)
        existing = self.repo.get_user_by_email(email)
        with self.conn:
            if existing:
                if self.repo.get_membership(ctx.org_id, existing["id"]):
                    raise RiskoraError("Este usuário já faz parte da organização.")
                self.repo.add_member(ctx.org_id, existing["id"], role)
                user_id, created = existing["id"], False
            else:
                self.auth.validate_password(temp_password, email)
                user_id = self.repo.create_user(email, full_name, self.auth.hash_password(temp_password), True)
                self.repo.add_member(ctx.org_id, user_id, role)
                created = True
            self.audit.log_ctx(ctx, "user_provisioned", "user", user_id, f"perfil={role}")
        return user_id, created

    def change_role(self, ctx: Context, user_id: int, role: str) -> None:
        require(ctx, "user:manage")
        role = require_choice(role, ASSIGNABLE_ROLES, "Perfil")
        member = self.repo.get_membership(ctx.org_id, user_id)
        if not member:
            raise NotFoundError("Usuário não encontrado.")
        if member["role_code"] == "admin" and role != "admin" and self.repo.count_admins(ctx.org_id) <= 1:
            raise RiskoraError("A organização precisa de ao menos um administrador ativo.")
        with self.conn:
            self.repo.set_member_role(ctx.org_id, user_id, role)
            self.audit.log_ctx(ctx, "role_changed", "user", user_id, f"novo perfil={role}")

    def remove_member(self, ctx: Context, user_id: int) -> None:
        require(ctx, "user:manage")
        member = self.repo.get_membership(ctx.org_id, user_id)
        if not member:
            raise NotFoundError("Usuário não encontrado.")
        if member["role_code"] == "admin" and self.repo.count_admins(ctx.org_id) <= 1:
            raise RiskoraError("Não é possível remover o último administrador da organização.")
        with self.conn:
            self.repo.remove_member(ctx.org_id, user_id)
            self.audit.log_ctx(ctx, "member_removed", "user", user_id)
