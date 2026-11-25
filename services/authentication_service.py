"""Login, sessões, troca e recuperação de senha.

Decisões de segurança:
- Mensagem de erro única no login (não revela se o e-mail existe) e verificação de hash "falsa" para usuários
  inexistentes, reduzindo diferença de tempo de resposta.
- Bloqueio temporário após falhas seguidas.
- Token de sessão aleatório de 256 bits; no banco fica somente o hash (SHA-256).
- Sessão expira por inatividade e por tempo absoluto; sair revoga a sessão no banco.
- Token de recuperação: emitido por um administrador, uso único e validade curta.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Callable

from config.settings import Settings, load_settings
from database.repositories.accounts import AccountRepository
from models.user import Context
from services.audit_service import AuditService
from services.authorization_service import require
from services.clock import from_iso, to_iso, utcnow
from services.errors import AuthenticationError, NotFoundError, RiskoraError
from services.password_hasher import ScryptHasher
from services.validation import clean_email

_DUMMY_HASHES: dict = {}
GENERIC_LOGIN_ERROR = "Credenciais inválidas ou conta temporariamente bloqueada."
_COMMON_PASSWORDS = {"password", "senha", "12345678", "123456789", "1234567890", "qwertyuiop", "admin", "administrador"}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthenticationService:
    def __init__(self, conn, settings: Settings | None = None, hasher: ScryptHasher | None = None,
                 clock: Callable = utcnow):
        self.conn = conn
        self.settings = settings or load_settings()
        self.hasher = hasher or ScryptHasher(n=self.settings.scrypt_n)
        self.clock = clock
        self.repo = AccountRepository(conn)
        self.audit = AuditService(conn)

    @property
    def _dummy_hash(self) -> str:
        key = (self.hasher.n, self.hasher.r, self.hasher.p)
        if key not in _DUMMY_HASHES:
            _DUMMY_HASHES[key] = self.hasher.hash("senha-ficticia-para-equalizar-tempo")
        return _DUMMY_HASHES[key]

    # -- política de senha -----------------------------------------------------------------
    def validate_password(self, password: str, email: str = "") -> None:
        if not isinstance(password, str) or len(password) < self.settings.min_password_length:
            raise RiskoraError(f"A senha deve ter ao menos {self.settings.min_password_length} caracteres.")
        if len(password) > 128:
            raise RiskoraError("A senha deve ter no máximo 128 caracteres.")
        lowered = password.lower()
        if lowered in _COMMON_PASSWORDS or (email and lowered == email.lower()):
            raise RiskoraError("Escolha uma senha menos previsível.")

    def hash_password(self, password: str) -> str:
        return self.hasher.hash(password)

    # -- login / sessão -----------------------------------------------------------------------
    def login(self, email: str, password: str) -> str:
        """Devolve o token de sessão (guarde-o só em memória do servidor/sessão). Falha com mensagem genérica."""
        now = self.clock()
        try:
            email = clean_email(email)
        except RiskoraError:
            self.hasher.verify(password or "", self._dummy_hash)
            raise AuthenticationError(GENERIC_LOGIN_ERROR)
        user = self.repo.get_user_by_email(email)
        if user is None:
            self.hasher.verify(password or "", self._dummy_hash)
            with self.conn:
                self.audit.log(None, None, "login_failed", "user", None, "usuário inexistente")
            raise AuthenticationError(GENERIC_LOGIN_ERROR)
        locked = user["locked_until"] and from_iso(user["locked_until"]) > now
        valid = self.hasher.verify(password or "", user["password_hash"])
        if locked or user["status"] != "Ativo" or not valid:
            with self.conn:
                if not locked and user["status"] == "Ativo" and not valid:
                    attempts = user["failed_attempts"] + 1
                    lock_until = None
                    if attempts >= self.settings.max_failed_logins:
                        lock_until = to_iso(now + timedelta(minutes=self.settings.lockout_minutes))
                        attempts = 0
                        self.audit.log(None, user["id"], "account_locked", "user", user["id"], "bloqueio temporário")
                    self.repo.record_login_failure(user["id"], attempts, lock_until)
                self.audit.log(None, user["id"], "login_failed", "user", user["id"], "credenciais inválidas")
            raise AuthenticationError(GENERIC_LOGIN_ERROR)
        return self.start_session(user["id"])

    def start_session(self, user_id: int, audit_action: str = "login_success") -> str:
        """Cria a sessão (token aleatório; no banco fica só o hash). Usado pelo login e pelo acesso de visitante."""
        now = self.clock()
        token = secrets.token_urlsafe(32)
        with self.conn:
            self.repo.record_login_success(user_id, to_iso(now))
            self.repo.create_session(hash_token(token), user_id, to_iso(now),
                                     to_iso(now + timedelta(hours=self.settings.session_absolute_hours)))
            self.audit.log(None, user_id, audit_action, "user", user_id)
        return token

    def validate_session(self, token: str | None) -> dict | None:
        """Devolve o usuário da sessão válida (e renova a atividade) ou None."""
        if not token:
            return None
        now = self.clock()
        session = self.repo.get_session(hash_token(token))
        if not session or session["revoked"]:
            return None
        idle_limit = from_iso(session["last_seen_at"]) + timedelta(minutes=self.settings.session_idle_minutes)
        if now > idle_limit or now > from_iso(session["absolute_expires_at"]):
            with self.conn:
                self.repo.revoke_session(hash_token(token))
            return None
        user = self.repo.get_user(session["user_id"])
        if not user or user["status"] != "Ativo":
            return None
        with self.conn:
            self.repo.touch_session(session["id"], to_iso(now))
        return user

    def logout(self, token: str | None) -> None:
        if not token:
            return
        session = self.repo.get_session(hash_token(token))
        with self.conn:
            self.repo.revoke_session(hash_token(token))
            if session:
                self.audit.log(None, session["user_id"], "logout", "user", session["user_id"])

    def list_organizations_for(self, user: dict) -> list[dict]:
        return [m for m in self.repo.list_memberships_for_user(user["id"]) if m["org_status"] == "Ativa"]

    def get_context(self, token: str | None, org_id: int | None) -> Context | None:
        """Cria o Contexto a partir da sessão e do vínculo. Sem vínculo ativo com a organização, devolve None."""
        user = self.validate_session(token)
        if user is None or org_id is None:
            return None
        membership = self.repo.get_membership(org_id, user["id"])
        org = self.repo.get_organization(org_id)
        if not membership or not org or org["status"] != "Ativa":
            return None
        perms = self.repo.permissions_for_role(membership["role_code"])
        return Context(user["id"], user["email"], user["full_name"], org_id, membership["role_code"], perms)

    # -- troca e recuperação de senha ------------------------------------------------------------------
    def change_password(self, user_id: int, current_password: str, new_password: str) -> None:
        user = self.repo.get_user(user_id)
        if not user or not self.hasher.verify(current_password or "", user["password_hash"]):
            raise AuthenticationError("Senha atual incorreta.")
        self.validate_password(new_password, user["email"])
        if self.hasher.verify(new_password, user["password_hash"]):
            raise RiskoraError("A nova senha deve ser diferente da atual.")
        with self.conn:
            self.repo.set_password(user_id, self.hash_password(new_password), False, to_iso(self.clock()))
            self.audit.log(None, user_id, "password_changed", "user", user_id)

    def issue_reset_token(self, ctx: Context, user_id: int) -> str:
        """Administrador gera um token de uso único (exibido uma só vez). Não há envio por e-mail."""
        require(ctx, "user:manage")
        if not self.repo.get_membership(ctx.org_id, user_id):
            raise NotFoundError("Usuário não encontrado.")
        now = self.clock()
        token = secrets.token_urlsafe(24)
        with self.conn:
            self.repo.invalidate_pending_resets(user_id, to_iso(now))
            self.repo.create_reset_token(hash_token(token), user_id, ctx.user_id,
                                         to_iso(now + timedelta(minutes=self.settings.reset_token_minutes)))
            self.audit.log_ctx(ctx, "password_reset_issued", "user", user_id)
        return token

    def reset_password_with_token(self, email: str, token: str, new_password: str) -> None:
        generic = AuthenticationError("Token inválido ou expirado.")
        try:
            email = clean_email(email)
        except RiskoraError:
            raise generic
        user = self.repo.get_user_by_email(email)
        record = self.repo.get_reset_token(hash_token(token or "")) if token else None
        now = self.clock()
        if (not user or not record or record["user_id"] != user["id"] or record["used_at"]
                or from_iso(record["expires_at"]) < now):
            raise generic
        self.validate_password(new_password, email)
        with self.conn:
            self.repo.set_password(user["id"], self.hash_password(new_password), False, to_iso(now))
            self.repo.mark_reset_used(record["id"], to_iso(now))
            self.repo.revoke_user_sessions(user["id"])
            self.audit.log(None, user["id"], "password_reset_used", "user", user["id"])
