import pytest

from models.user import PERMISSIONS, ROLE_PERMISSIONS
from database.repositories.accounts import AccountRepository
from services.asset_service import AssetService
from services.assessment_service import AssessmentService
from services.audit_service import AuditService
from services.authorization_service import require
from services.errors import NotFoundError, PermissionDenied, RiskoraError
from services.organization_service import OrganizationService
from services.report_service import ReportFilters, ReportService
from services.treatment_service import TreatmentService
from tests.helpers import ctx_for, finalized, make_auth, make_org, make_user, new_db, backup_asset


def test_matriz_de_permissoes_por_perfil():
    expected = {
        "admin": set(PERMISSIONS),
        "manager": {"data:read", "treatment:validate", "report:export"},
        "analyst": {"data:read", "asset:write", "assessment:run", "treatment:write", "report:export"},
        "reader": {"data:read", "report:export"},
    }
    for role, perms in expected.items():
        assert set(ROLE_PERMISSIONS[role]) == perms
    # Visitante: pode mexer em tudo, exceto usuários, organização e auditoria
    assert set(ROLE_PERMISSIONS["guest"]) == set(PERMISSIONS) - {"user:manage", "org:manage", "audit:read"}


def test_permissoes_no_banco_sao_iguais_as_do_codigo():
    conn = new_db()
    repo = AccountRepository(conn)
    for role, perms in ROLE_PERMISSIONS.items():
        assert repo.permissions_for_role(role) == perms


def test_sem_contexto_toda_operacao_falha():
    with pytest.raises(PermissionDenied):
        require(None, "data:read")
    conn = new_db()
    with pytest.raises(PermissionDenied):
        AssetService(conn).list_assets(None)
    with pytest.raises(PermissionDenied):
        ReportService(conn).compute_dashboard(None)


def test_permissao_desconhecida_e_erro_de_programacao():
    with pytest.raises(ValueError):
        require(ctx_for(1), "inventada:permissao")


def test_leitor_e_gestor_nao_cadastram_ativos_nem_avaliam():
    conn = new_db()
    org = make_org(conn)
    admin = ctx_for(org, "admin")
    asset_id = backup_asset(conn, admin)
    for role in ("reader", "manager"):
        ctx = ctx_for(org, role)
        with pytest.raises(PermissionDenied):
            backup_asset(conn, ctx, "Outro")
        with pytest.raises(PermissionDenied):
            AssetService(conn).update_asset(ctx, asset_id, {"name": "X", "category_code": "backup_recuperacao"})
        with pytest.raises(PermissionDenied):
            AssetService(conn).set_status(ctx, asset_id, "Desativado")
        with pytest.raises(PermissionDenied):
            AssessmentService(conn).create_assessment(ctx, asset_id)
        assert AssetService(conn).get_asset(ctx, asset_id)["name"] == "Backup ERP"  # leitura é permitida


def test_analista_nao_valida_acoes_nem_registra_residual_nem_gerencia_usuarios():
    conn = new_db()
    org = make_org(conn)
    admin, analyst, manager = ctx_for(org, "admin"), ctx_for(org, "analyst"), ctx_for(org, "manager")
    _, aid, svc = finalized(conn, admin, {"Q10": "nao"})
    risk_id = svc.get_results(admin, aid)[0]["id"]
    tr = TreatmentService(conn)
    action_id = tr.create_action(analyst, risk_id, {"action": "Criar rotina de teste", "status": "Concluído"})
    with pytest.raises(PermissionDenied):
        tr.validate_action(analyst, action_id)
    with pytest.raises(PermissionDenied):
        tr.reassess_risk(analyst, risk_id, 2, 3, "justificativa longa o bastante", "justificativa longa o bastante")
    with pytest.raises(PermissionDenied):
        OrganizationService(conn).list_members(analyst)
    with pytest.raises(PermissionDenied):
        tr.create_action(manager, risk_id, {"action": "x"})  # gestor valida, não registra
    tr.validate_action(manager, action_id)  # gestor valida
    assert tr.action_details(admin, action_id)["lifecycle"] == "Validada"


def test_somente_administrador_ve_auditoria_e_edita_organizacao():
    conn = new_db()
    org = make_org(conn)
    for role in ("manager", "analyst", "reader"):
        with pytest.raises(PermissionDenied):
            AuditService(conn).list_events(ctx_for(org, role))
        with pytest.raises(PermissionDenied):
            OrganizationService(conn).update_organization(ctx_for(org, role), "N", "", "", "", "Ativa")
    assert isinstance(AuditService(conn).list_events(ctx_for(org, "admin")), list)


def test_isolamento_entre_organizacoes_em_ativos_avaliacoes_e_tratamento():
    conn = new_db()
    org_a, org_b = make_org(conn, "org-a", "Org A"), make_org(conn, "org-b", "Org B")
    a, b = ctx_for(org_a, "admin"), ctx_for(org_b, "admin")
    asset_a, aid_a, svc = finalized(conn, a, {"Q10": "nao"})
    risk_a = svc.get_results(a, aid_a)[0]["id"]
    tr = TreatmentService(conn)
    action_a = tr.create_action(a, risk_a, {"action": "Ação da org A"})
    asset_b = backup_asset(conn, b, "Backup da B")

    assets = AssetService(conn)
    with pytest.raises(NotFoundError):
        assets.get_asset(b, asset_a)
    with pytest.raises(NotFoundError):
        assets.update_asset(b, asset_a, {"name": "invadido", "category_code": "backup_recuperacao"})
    with pytest.raises(NotFoundError):
        assets.set_status(b, asset_a, "Desativado")
    with pytest.raises(NotFoundError):
        svc.create_assessment(b, asset_a)
    for call in (svc.get_assessment, svc.get_results, svc.completeness, svc.get_answers, svc.clone_assessment):
        with pytest.raises(NotFoundError):
            call(b, aid_a)
    with pytest.raises(NotFoundError):
        tr.create_action(b, risk_a, {"action": "invadida"})
    for call in (tr.action_details, tr.validate_action):
        with pytest.raises(NotFoundError):
            call(b, action_a)
    with pytest.raises(NotFoundError):
        tr.update_action(b, action_a, {"action": "x"})
    with pytest.raises(NotFoundError):
        tr.add_evidence(b, action_a, "d", "r")
    with pytest.raises(NotFoundError):
        tr.reassess_risk(b, risk_a, 2, 3, "justificativa longa o bastante", "justificativa longa o bastante")
    assert [x["name"] for x in assets.list_assets(b)] == ["Backup da B"]
    assert [x["name"] for x in assets.list_assets(a)] == ["Backup ERP"]
    assert svc.list_assessments(b) == []
    assert asset_b != asset_a


def test_isolamento_em_usuarios_relatorios_e_auditoria():
    conn = new_db()
    auth = make_auth(conn)
    org_a, org_b = make_org(conn, "org-a", "Org A"), make_org(conn, "org-b", "Org B")
    user_a = make_user(conn, org_a, "a@test.com", "admin", auth=auth)
    a, b = ctx_for(org_a, "admin", user_a), ctx_for(org_b, "admin")
    finalized(conn, a, {"Q10": "nao"})
    orgs = OrganizationService(conn, auth)
    with pytest.raises(NotFoundError):
        orgs.change_role(b, user_a, "reader")
    with pytest.raises(NotFoundError):
        orgs.remove_member(b, user_a)
    assert orgs.list_members(b) == []
    rs = ReportService(conn)
    assert rs.compute_dashboard(b)["risks_total"] == 0 and rs.compute_dashboard(a)["risks_total"] == 1
    assert rs.build_report(b, "geral").rows == [] and len(rs.build_report(a, "geral").rows) == 1
    assert all(e["organization_id"] == org_b for e in AuditService(conn).list_events(b))
    assert rs.build_report(b, "geral", ReportFilters(asset_id=1)).rows == []


def test_nao_remove_nem_rebaixa_o_ultimo_administrador():
    conn = new_db()
    auth = make_auth(conn)
    org = make_org(conn)
    admin_id = make_user(conn, org, "admin@test.com", "admin", auth=auth)
    ctx = ctx_for(org, "admin", admin_id)
    orgs = OrganizationService(conn, auth)
    with pytest.raises(RiskoraError):
        orgs.change_role(ctx, admin_id, "reader")
    with pytest.raises(RiskoraError):
        orgs.remove_member(ctx, admin_id)
    other = make_user(conn, org, "outro@test.com", "admin", auth=auth)
    orgs.change_role(ctx, admin_id, "reader")  # agora há outro administrador
    assert other


def test_provisionamento_de_usuario_valida_senha_e_perfil():
    conn = new_db()
    auth = make_auth(conn)
    org = make_org(conn)
    ctx = ctx_for(org, "admin", make_user(conn, org, "admin@test.com", "admin", auth=auth))
    orgs = OrganizationService(conn, auth)
    with pytest.raises(RiskoraError):
        orgs.create_user(ctx, "novo@test.com", "Novo", "analyst", "curta")
    with pytest.raises(RiskoraError):
        orgs.create_user(ctx, "novo@test.com", "Novo", "superuser", "uma-senha-razoavel")
    with pytest.raises(RiskoraError):
        orgs.create_user(ctx, "email-invalido", "Novo", "analyst", "uma-senha-razoavel")
    user_id, created = orgs.create_user(ctx, "novo@test.com", "Novo", "analyst", "uma-senha-razoavel")
    assert created and AccountRepository(conn).get_user(user_id)["must_change_password"] == 1
    with pytest.raises(RiskoraError):
        orgs.create_user(ctx, "novo@test.com", "Novo", "analyst", "uma-senha-razoavel")  # já é membro
