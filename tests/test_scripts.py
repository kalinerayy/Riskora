import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

from database.connection import get_connection
from database.repositories.accounts import AccountRepository
from scripts import backup_db, create_admin, load_demo


def _run(module, argv, passwords=()):
    with mock.patch.object(sys, "argv", ["script", *argv]), mock.patch("getpass.getpass", side_effect=list(passwords)):
        return module.main()


def _with_temp_db(test):
    old = os.environ.get("RISKORA_DB")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["RISKORA_DB"] = str(Path(tmp) / "t.db")
        try:
            test(Path(tmp))
        finally:
            if old is None:
                os.environ.pop("RISKORA_DB", None)
            else:
                os.environ["RISKORA_DB"] = old


def test_create_admin_cria_organizacao_e_administrador_com_senha_em_hash():
    def body(tmp):
        args = ["--email", "Admin@Empresa.com", "--name", "Admin", "--org-name", "Empresa", "--org-slug", "empresa"]
        assert _run(create_admin, args, ["senha-forte-123", "senha-forte-123"]) == 0
        conn = get_connection()
        repo = AccountRepository(conn)
        user = repo.get_user_by_email("admin@empresa.com")
        assert user and user["password_hash"].startswith("scrypt$") and "senha-forte-123" not in user["password_hash"]
        org = repo.get_organization_by_slug("empresa")
        assert repo.get_membership(org["id"], user["id"])["role_code"] == "admin"
        assert _run(create_admin, args) == 0  # segunda execução: já existe, não pede senha nem duplica
        assert conn.execute("SELECT COUNT(*) FROM organization_members").fetchone()[0] == 1
    _with_temp_db(body)


def test_create_admin_rejeita_senha_fraca_ou_diferente_e_dados_invalidos():
    def body(tmp):
        base = ["--org-name", "Empresa", "--org-slug", "empresa"]
        assert _run(create_admin, ["--email", "a@b.com", *base], ["curta", "curta"]) == 1
        assert _run(create_admin, ["--email", "a@b.com", *base], ["senha-forte-123", "outra-senha-123"]) == 1
        assert _run(create_admin, ["--email", "invalido", *base], ["senha-forte-123", "senha-forte-123"]) == 1
        assert _run(create_admin, ["--email", "a@b.com", "--org-name", "E", "--org-slug", "Slug Inválido!"],
                    ["senha-forte-123", "senha-forte-123"]) == 1
        assert get_connection().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    _with_temp_db(body)


def test_load_demo_exige_usuario_existente_e_concede_acesso():
    def body(tmp):
        assert _run(load_demo, ["--email", "naoexiste@x.com"]) == 1
        _run(create_admin, ["--email", "a@b.com", "--org-name", "Empresa", "--org-slug", "empresa"],
             ["senha-forte-123", "senha-forte-123"])
        assert _run(load_demo, ["--email", "a@b.com"]) == 0
        assert _run(load_demo, ["--email", "a@b.com"]) == 0  # idempotente
        conn = get_connection()
        assert conn.execute("SELECT COUNT(*) FROM organizations WHERE is_demo=1").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 6
    _with_temp_db(body)


def test_backup_do_banco_gera_copia_legivel():
    def body(tmp):
        assert backup_db.main() == 1  # banco ainda não existe
        _run(create_admin, ["--email", "a@b.com", "--org-name", "Empresa", "--org-slug", "empresa"],
             ["senha-forte-123", "senha-forte-123"])
        with mock.patch.object(backup_db, "BASE_DIR", tmp):
            assert backup_db.main() == 0
        copies = list((tmp / "backups").glob("riskora-*.db"))
        assert len(copies) == 1
        import sqlite3
        assert sqlite3.connect(str(copies[0])).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    _with_temp_db(body)


def test_reset_demo_exige_confirmacao_e_restaura():
    from scripts import reset_demo
    def body(tmp):
        assert _run(reset_demo, []) == 1  # sem --yes não faz nada
        _run(create_admin, ["--email", "a@b.com", "--org-name", "Empresa", "--org-slug", "empresa"],
             ["senha-forte-123", "senha-forte-123"])
        _run(load_demo, ["--email", "a@b.com"])
        assert _run(reset_demo, ["--yes"]) == 0
        conn = get_connection()
        statuses = sorted(r[0] for r in conn.execute("SELECT status FROM organizations WHERE is_demo=1"))
        assert statuses == ["Arquivada", "Ativa"]
    _with_temp_db(body)
