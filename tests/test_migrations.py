import sqlite3
import tempfile
from pathlib import Path

import pytest

from database.connection import get_connection, init_database
from database.migrate import apply_migrations
from tests.helpers import backup_asset, ctx_for, make_org, new_db


def test_migracao_aplica_uma_vez_e_e_idempotente():
    conn = get_connection(":memory:")
    assert init_database(conn) == ["001_initial"]
    assert init_database(conn) == []
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations")]
    assert versions == ["001_initial"]


def test_todas_as_entidades_previstas_existem():
    conn = new_db()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"organizations", "users", "roles", "permissions", "organization_members", "asset_categories", "assets",
                "assessment_templates", "questions", "assessments", "answers", "diagnostic_rules", "findings", "risks",
                "risk_assessments", "controls", "control_references", "risk_control_mappings", "treatment_actions",
                "evidence_records", "audit_logs", "role_permissions", "sessions", "password_reset_tokens",
                "treatment_action_events"}
    assert expected <= tables


def test_migracao_com_erro_nao_deixa_nada_aplicado():
    conn = get_connection(":memory:")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "001_ok.sql").write_text("CREATE TABLE a (id INTEGER);", encoding="utf-8")
        (folder / "002_quebrada.sql").write_text("CREATE TABLE b (id INTEGER); INSERT INTO tabela_inexistente VALUES (1);",
                                                 encoding="utf-8")
        with pytest.raises(sqlite3.Error):
            apply_migrations(conn, folder)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "a" in tables and "b" not in tables  # a 002 foi desfeita por completo
        applied = [r[0] for r in conn.execute("SELECT version FROM schema_migrations")]
        assert applied == ["001_ok"]


def test_nome_de_migracao_invalido_e_rejeitado():
    conn = get_connection(":memory:")
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "001_Nome Ruim.sql").write_text("SELECT 1;", encoding="utf-8")
        with pytest.raises(ValueError):
            apply_migrations(conn, Path(tmp))


def test_catalogo_inicial_e_carregado_sem_duplicar():
    conn = new_db()
    init_database(conn)
    assert conn.execute("SELECT COUNT(*) FROM asset_categories").fetchone()[0] == 11
    assert conn.execute("SELECT COUNT(*) FROM controls").fetchone()[0] == 11
    assert conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 13
    assert conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 5


def test_banco_recusa_vinculo_entre_organizacoes_diferentes():
    conn = new_db()
    org_a, org_b = make_org(conn, "org-a"), make_org(conn, "org-b", "Org B")
    asset_a = backup_asset(conn, ctx_for(org_a))
    template_id = conn.execute("SELECT id FROM assessment_templates").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):  # ativo da org A com avaliação da org B
        conn.execute("INSERT INTO assessments (organization_id, asset_id, template_id, methodology_version, "
                     "questionnaire_version, rules_version) VALUES (?,?,?,?,?,?)",
                     (org_b, asset_a, template_id, "1", "1", "1"))


def test_chaves_estrangeiras_e_restricoes():
    conn = new_db()
    org = make_org(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO treatment_actions (organization_id, risk_id, action) VALUES (?, 999, 'x')", (org,))
    with pytest.raises(sqlite3.IntegrityError):  # criticidade fora do domínio
        conn.execute("INSERT INTO assets (organization_id, category_id, asset_code, name, criticality) "
                     "VALUES (?, 1, 'X', 'X', 'Muito')", (org,))
    with pytest.raises(sqlite3.IntegrityError):  # impacto fora da escala
        conn.execute("INSERT INTO assets (organization_id, category_id, asset_code, name, impact_legal) "
                     "VALUES (?, 1, 'Y', 'Y', 9)", (org,))


def test_banco_protege_respostas_de_avaliacao_concluida():
    from tests.helpers import finalized
    conn = new_db()
    org = make_org(conn)
    ctx = ctx_for(org)
    _, aid, _ = finalized(conn, ctx, {"Q10": "nao"})
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE answers SET value='sim' WHERE assessment_id=?", (aid,))
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM answers WHERE assessment_id=?", (aid,))
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("INSERT INTO answers (organization_id, assessment_id, question_code, value) VALUES (?,?,?,?)",
                     (org, aid, "Q01", "sim"))
