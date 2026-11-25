import os

import pytest

from config.settings import GUEST_ALLOWED_ROLES, Settings, load_settings
from database.repositories.accounts import AccountRepository
from models.user import ASSIGNABLE_ROLES, GUEST_EMAIL, ROLES, Context
from services.asset_service import AssetService
from services.assessment_service import AssessmentService
from services.audit_service import AuditService
from services.authentication_service import AuthenticationService
from services.demo_data import DEMO_SLUG, attach_user, load_demo, reset_demo
from services.errors import AuthenticationError, PermissionDenied, RiskoraError
from services.guest_service import GuestAccessService
from services.organization_service import OrganizationService
from services.privacy import PRIVATE_LABEL, person_label
from services.report_service import ReportService
from services.treatment_service import TreatmentService
from tests.helpers import FAST, Clock, ctx_for, make_auth, make_org, make_user, new_db


def _guest(conn, enabled=True, role="guest"):
    settings = Settings(db_path=":memory:", scrypt_n=2 ** 10, guest_access=enabled, guest_role=role)
    auth = AuthenticationService(conn, settings=settings, hasher=FAST, clock=Clock())
    return GuestAccessService(conn, auth), auth


def _enter(conn, role="guest"):
    """Entra como visitante e devolve (contexto, serviço, auth)."""
    service, auth = _guest(conn, role=role)
    token = service.enter()
    org = auth.list_organizations_for(auth.validate_session(token))[0]["organization_id"]
    return auth.get_context(token, org), service, auth


def test_visitante_vem_ligado_por_padrao_com_perfil_visitante_e_pode_ser_desligado():
    assert load_settings().guest_access is True and load_settings().guest_role == "guest"
    os.environ["RISKORA_GUEST_ACCESS"] = "off"
    try:
        assert load_settings().guest_access is False
    finally:
        os.environ.pop("RISKORA_GUEST_ACCESS", None)
    service, _ = _guest(new_db(), enabled=False)
    assert service.enabled is False
    with pytest.raises(RiskoraError):  # desligado: o serviço recusa mesmo que alguém o chame direto
        service.enter()


def test_visitante_entra_so_na_demonstracao_e_nunca_enxerga_a_organizacao_real():
    conn = new_db()
    real = make_org(conn, "empresa-real", "Empresa Real")
    service, auth = _guest(conn)
    token = service.enter()
    user = auth.validate_session(token)
    orgs = auth.list_organizations_for(user)
    assert user["email"] == GUEST_EMAIL and len(orgs) == 1 and orgs[0]["is_demo"] == 1
    assert auth.get_context(token, real) is None
    ctx = auth.get_context(token, orgs[0]["organization_id"])
    assert ctx.role == "guest" and ctx.is_guest and ReportService(conn).compute_dashboard(ctx)["risks_total"] == 9


def test_visitante_pode_mexer_cadastrar_avaliar_tratar_e_validar():
    conn = new_db()
    ctx, service, auth = _enter(conn)
    assets, assessments, treatment = AssetService(conn), AssessmentService(conn), TreatmentService(conn)
    asset_id = assets.create_asset(ctx, {"name": "Ativo do visitante", "category_code": "backup_recuperacao",
                                         "impact_availability": 5, "impact_operational": 4})
    assets.update_asset(ctx, asset_id, {"name": "Ativo do visitante (editado)", "category_code": "backup_recuperacao",
                                        "impact_availability": 5})
    aid = assessments.create_assessment(ctx, asset_id)
    assessments.save_answer(ctx, aid, "Q10", "nao")
    assessments.finalize_assessment(ctx, aid)
    risk = assessments.get_results(ctx, aid)[0]
    action_id = treatment.create_action(ctx, risk["id"], {"action": "Testar a restauração", "status": "Concluído"})
    treatment.validate_action(ctx, action_id, "ok")
    treatment.reassess_risk(ctx, risk["id"], 2, 3, "justificativa longa o bastante", "justificativa longa o bastante")
    assert treatment.action_details(ctx, action_id)["lifecycle"] == "Validada"
    assert assets.get_asset(ctx, asset_id)["name"] == "Ativo do visitante (editado)"


def test_visitante_nao_gerencia_usuarios_organizacao_nem_auditoria():
    conn = new_db()
    ctx, service, auth = _enter(conn)
    orgs = OrganizationService(conn, auth)
    with pytest.raises(PermissionDenied):
        orgs.list_members(ctx)
    with pytest.raises(PermissionDenied):
        orgs.create_user(ctx, "novo@test.com", "Novo", "reader", "uma-senha-razoavel")
    with pytest.raises(PermissionDenied):
        orgs.update_organization(ctx, "Invadida", "", "", "", "Ativa")
    with pytest.raises(PermissionDenied):
        AuditService(conn).list_events(ctx)
    with pytest.raises(PermissionDenied):
        auth.issue_reset_token(ctx, ctx.user_id)


def test_visitante_nao_entra_com_senha_nem_vira_administrador():
    conn = new_db()
    service, auth = _guest(conn)
    service.enter()
    for guess in ("visitante", "senha-forte-123", "", "password"):
        with pytest.raises(AuthenticationError):
            auth.login(GUEST_EMAIL, guess)
    assert "admin" not in GUEST_ALLOWED_ROLES and "guest" in GUEST_ALLOWED_ROLES
    for configured in ("admin", "inventado", "READER "):
        os.environ["RISKORA_GUEST_ROLE"] = configured
        try:
            assert load_settings().guest_role in GUEST_ALLOWED_ROLES
            assert load_settings().guest_role != "admin"
        finally:
            os.environ.pop("RISKORA_GUEST_ROLE", None)


def test_usuarios_reais_nunca_recebem_o_perfil_de_visitante():
    conn = new_db()
    auth = make_auth(conn)
    org = make_org(conn)
    admin = ctx_for(org, "admin", make_user(conn, org, "admin@test.com", "admin", auth=auth))
    assert "guest" not in ASSIGNABLE_ROLES and "guest" in ROLES
    orgs = OrganizationService(conn, auth)
    with pytest.raises(RiskoraError):
        orgs.create_user(admin, "novo@test.com", "Novo", "guest", "uma-senha-razoavel")
    other = make_user(conn, org, "outro@test.com", "reader", auth=auth)
    with pytest.raises(RiskoraError):
        orgs.change_role(admin, other, "guest")


def test_perfil_do_visitante_configuravel_leitor_somente_leitura():
    conn = new_db()
    ctx, service, auth = _enter(conn, role="reader")
    assert ctx.role == "reader" and "somente leitura" in service.description()
    with pytest.raises(PermissionDenied):
        AssetService(conn).create_asset(ctx, {"name": "x", "category_code": "nuvem"})
    ctx2, service2, _ = _enter(conn, role="guest")  # a próxima entrada aplica o perfil atual
    assert ctx2.role == "guest" and "edite" in service2.description()


def test_entradas_repetidas_nao_duplicam_usuario_organizacao_nem_vinculos():
    conn = new_db()
    service, auth = _guest(conn)
    assert service.enter() != service.enter()
    assert conn.execute("SELECT COUNT(*) FROM users WHERE email=?", (GUEST_EMAIL,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM organizations WHERE is_demo=1").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM organization_members").fetchone()[0] == 1


def test_visitante_e_removido_de_outras_organizacoes_e_desativacao_e_respeitada():
    conn = new_db()
    service, auth = _guest(conn)
    guest_id = auth.validate_session(service.enter())["id"]
    other = make_org(conn, "outra", "Outra")
    with conn:
        AccountRepository(conn).add_member(other, guest_id, "admin")  # alguém tentou dar acesso indevido
    service.enter()
    memberships = AccountRepository(conn).list_memberships_for_user(guest_id)
    assert memberships and all(m["is_demo"] == 1 for m in memberships)
    with conn:
        AccountRepository(conn).set_user_status(guest_id, "Inativo", "2026-01-01T00:00:00Z")
    with pytest.raises(RiskoraError):
        service.enter()


def test_entrada_do_visitante_e_auditada():
    conn = new_db()
    _guest(conn)[0].enter()
    assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='guest_login'").fetchone()[0] == 1


# ---------------------------------------------------------------- privacidade
def _real_person_in_demo(conn):
    """Uma pessoa real (administrador) com acesso à demonstração, que cria uma avaliação e uma ação."""
    auth = make_auth(conn)
    base = make_org(conn, "empresa-real", "Empresa Real")
    user_id = make_user(conn, base, "maria.real@empresa.com", "admin", auth=auth)
    demo = load_demo(conn, user_id)
    attach_user(conn, demo, user_id, "admin")
    real = Context(user_id, "maria.real@empresa.com", "Maria Real", demo, "admin",
                   __import__("models.user", fromlist=["ROLE_PERMISSIONS"]).ROLE_PERMISSIONS["admin"])
    assets = AssetService(conn)
    asset_id = assets.create_asset(real, {"name": "Ativo de teste B", "category_code": "backup_recuperacao",
                                          "impact_availability": 4})
    svc = AssessmentService(conn)
    aid = svc.create_assessment(real, asset_id)
    svc.save_answer(real, aid, "Q10", "nao")
    svc.finalize_assessment(real, aid)
    risk = svc.get_results(real, aid)[0]
    action_id = TreatmentService(conn).create_action(real, risk["id"], {"action": "Criar rotina de teste"})
    return real, asset_id, aid, action_id


def test_visitante_nao_ve_nome_nem_email_de_pessoas_que_fazem_login():
    conn = new_db()
    real, asset_id, aid, action_id = _real_person_in_demo(conn)
    guest, service, auth = _enter(conn)
    svc, tsvc, rs = AssessmentService(conn), TreatmentService(conn), ReportService(conn)
    # quem tem login vê os nomes reais
    assert svc.get_assessment(real, aid)["assessor_name"] == "Maria Real"
    assert any(e["user_email"] == "maria.real@empresa.com" for e in tsvc.action_details(real, action_id)["events"])
    # o visitante vê o mesmo conteúdo, mas sem identificar pessoas
    assert svc.get_assessment(guest, aid)["assessor_name"] == PRIVATE_LABEL
    assert [a["assessor_name"] for a in svc.list_assessments(guest, asset_id)] == [PRIVATE_LABEL]
    events = tsvc.action_details(guest, action_id)["events"]
    assert events and all(e["user_email"] == PRIVATE_LABEL for e in events)
    historico = rs.build_report(guest, "historico").rows
    assert historico and PRIVATE_LABEL in {r["avaliador"] for r in historico}
    everything = str(historico) + str(events) + str(svc.list_assessments(guest, asset_id))
    assert "Maria" not in everything and "maria.real" not in everything and "empresa.com" not in everything


def test_visitante_ve_o_que_visitantes_fizeram_com_o_rotulo_visitante():
    conn = new_db()
    guest, service, auth = _enter(conn)
    asset_id = AssetService(conn).create_asset(guest, {"name": "A", "category_code": "backup_recuperacao"})
    svc = AssessmentService(conn)
    aid = svc.create_assessment(guest, asset_id)
    assert svc.get_assessment(guest, aid)["assessor_name"] == "Visitante"
    assert person_label(guest, "Visitante") == "Visitante" and person_label(guest, "") == ""
    assert person_label(ctx_for(1, "admin"), "Maria Real") == "Maria Real"  # quem tem login não é afetado


# ---------------------------------------------------------------- restaurar a demonstração
def test_restaurar_demonstracao_arquiva_a_antiga_e_cria_uma_limpa():
    conn = new_db()
    guest, service, auth = _enter(conn)
    AssetService(conn).create_asset(guest, {"name": "Lixo do visitante", "category_code": "nuvem"})
    old_org = guest.org_id
    new_org = reset_demo(conn)
    assert new_org != old_org
    old = AccountRepository(conn).get_organization(old_org)
    assert old["status"] == "Arquivada" and old["slug"] != DEMO_SLUG and old["is_demo"] == 1
    assert conn.execute("SELECT COUNT(*) FROM assets WHERE organization_id=?", (old_org,)).fetchone()[0] == 7  # guardado
    guest2, _, auth2 = _enter(conn)
    assert guest2.org_id == new_org
    names = [a["name"] for a in AssetService(conn).list_assets(guest2)]
    assert len(names) == 6 and "Lixo do visitante" not in names
    assert auth2.repo.get_organization(old_org)["status"] == "Arquivada"


def test_restaurar_demonstracao_devolve_o_acesso_de_quem_ja_tinha():
    conn = new_db()
    auth = make_auth(conn)
    base = make_org(conn, "empresa-real", "Empresa Real")
    user_id = make_user(conn, base, "maria@empresa.com", "admin", auth=auth)
    demo = load_demo(conn, user_id)
    attach_user(conn, demo, user_id, "manager")
    new_demo = reset_demo(conn)
    memberships = {m["organization_id"]: m["role_code"] for m in AccountRepository(conn).list_memberships_for_user(user_id)}
    assert memberships[new_demo] == "manager" and memberships[base] == "admin"
    assert reset_demo(conn) != new_demo  # pode ser repetido sem colisão de identificador
