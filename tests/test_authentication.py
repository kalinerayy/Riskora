import pytest

from database.repositories.accounts import AccountRepository
from services.authentication_service import GENERIC_LOGIN_ERROR
from services.errors import AuthenticationError, PermissionDenied, RiskoraError
from tests.helpers import PASSWORD, Clock, ctx_for, make_auth, make_org, make_user, new_db


def _setup(role="analyst", **settings):
    conn = new_db()
    clock = Clock()
    auth = make_auth(conn, clock, **settings)
    org = make_org(conn)
    user_id = make_user(conn, org, "ana@test.com", role, auth=auth)
    return conn, clock, auth, org, user_id


def test_login_valido_cria_sessao_e_contexto():
    conn, clock, auth, org, user_id = _setup("manager")
    token = auth.login("ANA@test.com ", PASSWORD)  # e-mail normalizado
    assert auth.validate_session(token)["id"] == user_id
    ctx = auth.get_context(token, org)
    assert ctx.role == "manager" and ctx.has("treatment:validate") and not ctx.has("asset:write")


def test_login_invalido_usa_mensagem_unica_sem_revelar_se_o_email_existe():
    conn, clock, auth, org, _ = _setup()
    messages = set()
    for email, password in (("ana@test.com", "errada-errada"), ("nao-existe@test.com", PASSWORD), ("lixo", "x")):
        with pytest.raises(AuthenticationError) as exc:
            auth.login(email, password)
        messages.add(str(exc.value))
    assert messages == {GENERIC_LOGIN_ERROR}


def test_senha_nunca_e_guardada_em_texto_e_token_so_como_hash():
    conn, clock, auth, org, user_id = _setup()
    stored = AccountRepository(conn).get_user(user_id)["password_hash"]
    assert PASSWORD not in stored and stored.startswith("scrypt$")
    token = auth.login("ana@test.com", PASSWORD)
    rows = conn.execute("SELECT token_hash FROM sessions").fetchall()
    assert rows and all(token not in r[0] and len(r[0]) == 64 for r in rows)


def test_bloqueio_apos_falhas_seguidas_e_liberacao_pelo_tempo():
    conn, clock, auth, org, _ = _setup(max_failed_logins=3, lockout_minutes=10)
    for _ in range(3):
        with pytest.raises(AuthenticationError):
            auth.login("ana@test.com", "errada-errada")
    with pytest.raises(AuthenticationError):  # mesmo com a senha certa, enquanto bloqueada
        auth.login("ana@test.com", PASSWORD)
    clock.advance(minutes=11)
    assert auth.login("ana@test.com", PASSWORD)


def test_sucesso_zera_o_contador_de_falhas():
    conn, clock, auth, org, user_id = _setup(max_failed_logins=3)
    for _ in range(2):
        with pytest.raises(AuthenticationError):
            auth.login("ana@test.com", "errada-errada")
    auth.login("ana@test.com", PASSWORD)
    assert AccountRepository(conn).get_user(user_id)["failed_attempts"] == 0


def test_usuario_inativo_nao_entra():
    conn, clock, auth, org, user_id = _setup()
    with conn:
        AccountRepository(conn).set_user_status(user_id, "Inativo", "2026-01-01T00:00:00Z")
    with pytest.raises(AuthenticationError):
        auth.login("ana@test.com", PASSWORD)


def test_sessao_expira_por_inatividade_e_por_tempo_absoluto():
    conn, clock, auth, org, _ = _setup(session_idle_minutes=30, session_absolute_hours=2)
    token = auth.login("ana@test.com", PASSWORD)
    clock.advance(minutes=20)
    assert auth.validate_session(token)  # atividade renova o limite de inatividade
    clock.advance(minutes=29)
    assert auth.validate_session(token)
    clock.advance(minutes=31)  # ficou parada além de 30 minutos
    assert auth.validate_session(token) is None
    token2 = auth.login("ana@test.com", PASSWORD)
    for _ in range(5):  # uso contínuo, mas passa do limite absoluto de 2 horas
        clock.advance(minutes=25)
        auth.validate_session(token2)
    assert auth.validate_session(token2) is None


def test_logout_revoga_a_sessao_no_servidor():
    conn, clock, auth, org, _ = _setup()
    token = auth.login("ana@test.com", PASSWORD)
    auth.logout(token)
    assert auth.validate_session(token) is None
    assert auth.get_context(token, org) is None
    assert auth.validate_session("token-inventado") is None
    assert auth.validate_session(None) is None


def test_contexto_exige_vinculo_ativo_com_a_organizacao():
    conn, clock, auth, org, _ = _setup()
    other = make_org(conn, "org-b", "Org B")
    token = auth.login("ana@test.com", PASSWORD)
    assert auth.get_context(token, other) is None  # sem vínculo com a outra organização
    assert auth.get_context(token, None) is None


def test_politica_de_senha():
    conn, clock, auth, org, _ = _setup()
    for bad in ("curta", "a" * 129, "password", "ana@test.com"):
        with pytest.raises(RiskoraError):
            auth.validate_password(bad, "ana@test.com")
    auth.validate_password("uma-senha-razoavel", "ana@test.com")


def test_troca_de_senha_exige_a_atual():
    conn, clock, auth, org, user_id = _setup()
    with pytest.raises(AuthenticationError):
        auth.change_password(user_id, "senha-errada-aqui", "nova-senha-forte-1")
    with pytest.raises(RiskoraError):
        auth.change_password(user_id, PASSWORD, PASSWORD)  # igual à atual
    auth.change_password(user_id, PASSWORD, "nova-senha-forte-1")
    with pytest.raises(AuthenticationError):
        auth.login("ana@test.com", PASSWORD)
    assert auth.login("ana@test.com", "nova-senha-forte-1")


def test_recuperacao_por_token_de_uso_unico_emitido_por_administrador():
    conn, clock, auth, org, user_id = _setup("analyst")
    admin_id = make_user(conn, org, "admin@test.com", "admin", auth=auth)
    admin = ctx_for(org, "admin", admin_id)
    old_session = auth.login("ana@test.com", PASSWORD)
    token = auth.issue_reset_token(admin, user_id)
    assert token not in str([tuple(r) for r in conn.execute("SELECT * FROM password_reset_tokens")])  # só o hash
    with pytest.raises(AuthenticationError):  # token errado
        auth.reset_password_with_token("ana@test.com", "token-errado", "outra-senha-forte-1")
    auth.reset_password_with_token("ana@test.com", token, "outra-senha-forte-1")
    assert auth.validate_session(old_session) is None  # sessões antigas são revogadas
    assert auth.login("ana@test.com", "outra-senha-forte-1")
    with pytest.raises(AuthenticationError):  # uso único
        auth.reset_password_with_token("ana@test.com", token, "mais-uma-senha-forte-1")


def test_token_de_recuperacao_expira_e_nao_vale_para_outro_usuario():
    conn, clock, auth, org, user_id = _setup("analyst", reset_token_minutes=30)
    admin_id = make_user(conn, org, "admin@test.com", "admin", auth=auth)
    make_user(conn, org, "bia@test.com", "reader", auth=auth)
    admin = ctx_for(org, "admin", admin_id)
    token = auth.issue_reset_token(admin, user_id)
    with pytest.raises(AuthenticationError):  # token da Ana usado com o e-mail da Bia
        auth.reset_password_with_token("bia@test.com", token, "outra-senha-forte-1")
    clock.advance(minutes=31)
    with pytest.raises(AuthenticationError):
        auth.reset_password_with_token("ana@test.com", token, "outra-senha-forte-1")


def test_somente_administrador_emite_token_e_so_para_membros_da_organizacao():
    conn, clock, auth, org, user_id = _setup("analyst")
    with pytest.raises(PermissionDenied):
        auth.issue_reset_token(ctx_for(org, "manager", 99), user_id)
    other_org = make_org(conn, "org-b", "Org B")
    outsider = make_user(conn, other_org, "fora@test.com", "reader", auth=auth)
    with pytest.raises(RiskoraError):
        auth.issue_reset_token(ctx_for(org, "admin", 1), outsider)


def test_eventos_de_seguranca_sao_auditados_sem_dados_sensiveis():
    conn, clock, auth, org, _ = _setup(max_failed_logins=2)
    auth.login("ana@test.com", PASSWORD)
    for _ in range(2):
        with pytest.raises(AuthenticationError):
            auth.login("ana@test.com", "errada-errada")
    actions = [r[0] for r in conn.execute("SELECT action FROM audit_logs")]
    assert "login_success" in actions and "login_failed" in actions and "account_locked" in actions
    text = str([tuple(r) for r in conn.execute("SELECT * FROM audit_logs")])
    assert PASSWORD not in text and "errada-errada" not in text
