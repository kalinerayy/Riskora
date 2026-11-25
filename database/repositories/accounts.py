"""Organizações, usuários, vínculos, sessões e tokens de recuperação."""
from __future__ import annotations

from database.repositories.base import BaseRepository


class AccountRepository(BaseRepository):
    # -- organizações -----------------------------------------------------------------
    def create_organization(self, name, slug, business_description="", context="", responsible="",
                            status="Ativa", is_demo=False) -> int:
        cur = self.conn.execute(
            "INSERT INTO organizations (name, slug, business_description, context, responsible, status, is_demo) "
            "VALUES (?,?,?,?,?,?,?)", (name, slug, business_description, context, responsible, status, int(is_demo)))
        return cur.lastrowid

    def update_organization(self, org_id, name, business_description, context, responsible, status, now) -> None:
        self.conn.execute(
            "UPDATE organizations SET name=?, business_description=?, context=?, responsible=?, status=?, "
            "updated_at=? WHERE id=?", (name, business_description, context, responsible, status, now, org_id))

    def archive_organization(self, org_id, new_slug, now) -> None:
        """Arquiva a organização e libera o identificador (os dados antigos ficam guardados, inacessíveis)."""
        self.conn.execute("UPDATE organizations SET slug=?, status='Arquivada', updated_at=? WHERE id=?",
                          (new_slug, now, org_id))

    def get_organization(self, org_id):
        return self._one("SELECT * FROM organizations WHERE id=?", (org_id,))

    def get_organization_by_slug(self, slug):
        return self._one("SELECT * FROM organizations WHERE slug=?", (slug,))

    def list_organizations(self):
        return self._all("SELECT * FROM organizations ORDER BY name")

    # -- usuários -----------------------------------------------------------------------
    def create_user(self, email, full_name, password_hash, must_change_password=False) -> int:
        cur = self.conn.execute(
            "INSERT INTO users (email, full_name, password_hash, must_change_password) VALUES (?,?,?,?)",
            (email, full_name, password_hash, int(must_change_password)))
        return cur.lastrowid

    def get_user(self, user_id):
        return self._one("SELECT * FROM users WHERE id=?", (user_id,))

    def get_user_by_email(self, email):
        return self._one("SELECT * FROM users WHERE email=?", (email,))

    def record_login_failure(self, user_id, failed_attempts, locked_until) -> None:
        self.conn.execute("UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?",
                          (failed_attempts, locked_until, user_id))

    def record_login_success(self, user_id, now) -> None:
        self.conn.execute("UPDATE users SET failed_attempts=0, locked_until=NULL, last_login_at=?, updated_at=? "
                          "WHERE id=?", (now, now, user_id))

    def set_password(self, user_id, password_hash, must_change_password, now) -> None:
        self.conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=?, failed_attempts=0, locked_until=NULL, "
            "updated_at=? WHERE id=?", (password_hash, int(must_change_password), now, user_id))

    def set_user_status(self, user_id, status, now) -> None:
        self.conn.execute("UPDATE users SET status=?, updated_at=? WHERE id=?", (status, now, user_id))

    def count_users(self) -> int:
        return self._one("SELECT COUNT(*) AS n FROM users")["n"]

    # -- vínculos ---------------------------------------------------------------------------
    def add_member(self, org_id, user_id, role_code) -> int:
        cur = self.conn.execute("INSERT INTO organization_members (organization_id, user_id, role_code) VALUES (?,?,?)",
                                (org_id, user_id, role_code))
        return cur.lastrowid

    def get_membership(self, org_id, user_id):
        return self._one("SELECT * FROM organization_members WHERE organization_id=? AND user_id=?", (org_id, user_id))

    def list_memberships_for_user(self, user_id):
        return self._all(
            "SELECT m.organization_id, m.role_code, o.name AS organization_name, o.is_demo, o.status AS org_status "
            "FROM organization_members m JOIN organizations o ON o.id=m.organization_id "
            "WHERE m.user_id=? ORDER BY o.is_demo, o.name", (user_id,))

    def list_members(self, org_id):
        return self._all(
            "SELECT u.id AS user_id, u.email, u.full_name, u.status, u.last_login_at, u.must_change_password, "
            "m.role_code FROM organization_members m JOIN users u ON u.id=m.user_id "
            "WHERE m.organization_id=? ORDER BY u.full_name, u.email", (org_id,))

    def set_member_role(self, org_id, user_id, role_code) -> None:
        self.conn.execute("UPDATE organization_members SET role_code=? WHERE organization_id=? AND user_id=?",
                          (role_code, org_id, user_id))

    def remove_member(self, org_id, user_id) -> None:
        self.conn.execute("DELETE FROM organization_members WHERE organization_id=? AND user_id=?", (org_id, user_id))

    def count_admins(self, org_id) -> int:
        return self._one(
            "SELECT COUNT(*) AS n FROM organization_members m JOIN users u ON u.id=m.user_id "
            "WHERE m.organization_id=? AND m.role_code='admin' AND u.status='Ativo'", (org_id,))["n"]

    def permissions_for_role(self, role_code) -> frozenset:
        rows = self._all("SELECT permission_code FROM role_permissions WHERE role_code=?", (role_code,))
        return frozenset(r["permission_code"] for r in rows)

    # -- sessões ----------------------------------------------------------------------------
    def create_session(self, token_hash, user_id, now, absolute_expires_at) -> int:
        cur = self.conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, last_seen_at, absolute_expires_at) "
            "VALUES (?,?,?,?,?)", (token_hash, user_id, now, now, absolute_expires_at))
        return cur.lastrowid

    def get_session(self, token_hash):
        return self._one("SELECT * FROM sessions WHERE token_hash=?", (token_hash,))

    def touch_session(self, session_id, now) -> None:
        self.conn.execute("UPDATE sessions SET last_seen_at=? WHERE id=?", (now, session_id))

    def revoke_session(self, token_hash) -> None:
        self.conn.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (token_hash,))

    def revoke_user_sessions(self, user_id) -> None:
        self.conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (user_id,))

    # -- tokens de recuperação ------------------------------------------------------------------
    def invalidate_pending_resets(self, user_id, now) -> None:
        self.conn.execute("UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL",
                          (now, user_id))

    def create_reset_token(self, token_hash, user_id, issued_by, expires_at) -> int:
        cur = self.conn.execute(
            "INSERT INTO password_reset_tokens (token_hash, user_id, issued_by, expires_at) VALUES (?,?,?,?)",
            (token_hash, user_id, issued_by, expires_at))
        return cur.lastrowid

    def get_reset_token(self, token_hash):
        return self._one("SELECT * FROM password_reset_tokens WHERE token_hash=?", (token_hash,))

    def mark_reset_used(self, token_id, now) -> None:
        self.conn.execute("UPDATE password_reset_tokens SET used_at=? WHERE id=?", (now, token_id))
