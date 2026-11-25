from datetime import date, timedelta

import pytest

from services.errors import NotFoundError, PermissionDenied, RiskoraError
from services.treatment_service import TreatmentService, is_overdue, lifecycle
from services.assessment_service import AssessmentService
from tests.helpers import backup_asset, ctx_for, finalized, make_org, new_db


def _setup():
    conn = new_db()
    org = make_org(conn)
    admin = ctx_for(org, "admin", None)
    _, aid, svc = finalized(conn, admin, {"Q10": "nao"})
    risk = svc.get_results(admin, aid)[0]
    return conn, org, admin, aid, svc, risk, TreatmentService(conn)


def _snapshot(conn, risk_id):
    return [tuple(r) for r in conn.execute(
        "SELECT kind, probability, impact, score, level FROM risk_assessments WHERE risk_id=? ORDER BY id", (risk_id,))]


def test_criacao_e_associacao_ao_risco_e_ao_controle():
    conn, org, admin, aid, svc, risk, tr = _setup()
    action_id = tr.create_action(admin, risk["id"], {"action": "Criar rotina de teste de restauração",
                                                     "owner": "Marina", "priority": "Alta"}, control_code="RC-BK-09")
    details = tr.action_details(admin, action_id)
    assert details["risk_id"] == risk["id"] and details["lifecycle"] == "Planejada"
    assert [e["event_type"] for e in details["events"]] == ["criada"]
    assert svc.get_results(admin, aid)[0]["actions"][0]["id"] == action_id


def test_concluir_acao_nao_reduz_automaticamente_o_risco():
    conn, org, admin, aid, svc, risk, tr = _setup()
    before = _snapshot(conn, risk["id"])
    action_id = tr.create_action(admin, risk["id"], {"action": "Criar rotina de teste"}, control_code="RC-BK-09")
    tr.update_action(admin, action_id, {"action": "Criar rotina de teste", "status": "Concluído"})
    details = tr.action_details(admin, action_id)
    assert details["status"] == "Concluído" and details["completed_at"] == date.today().isoformat()
    assert _snapshot(conn, risk["id"]) == before
    after = svc.get_results(admin, aid)[0]
    assert after["current"]["level"] == risk["current"]["level"] and after["residual"] is None


def test_validacao_exige_acao_concluida_e_e_removida_ao_reabrir():
    conn, org, admin, aid, svc, risk, tr = _setup()
    action_id = tr.create_action(admin, risk["id"], {"action": "Criar rotina de teste"})
    with pytest.raises(RiskoraError):
        tr.validate_action(admin, action_id)
    tr.update_action(admin, action_id, {"action": "Criar rotina de teste", "status": "Concluído"})
    assert tr.action_details(admin, action_id)["lifecycle"] == "Concluída"
    tr.validate_action(admin, action_id, "Relatório de teste conferido")
    d = tr.action_details(admin, action_id)
    assert d["lifecycle"] == "Validada" and d["validated_at"] and d["validation_notes"]
    tr.update_action(admin, action_id, {"action": "Criar rotina de teste", "status": "Em andamento"})
    d = tr.action_details(admin, action_id)
    assert d["lifecycle"] == "Em execução" and d["validated_at"] is None and d["completed_at"] is None
    events = [e["event_type"] for e in d["events"]]
    assert "validada" in events and "validação removida" in events


def test_historico_e_evidencias_da_acao():
    conn, org, admin, aid, svc, risk, tr = _setup()
    action_id = tr.create_action(admin, risk["id"], {"action": "Criar rotina de teste"})
    tr.update_action(admin, action_id, {"action": "Criar rotina de teste", "status": "Em andamento"})
    tr.add_evidence(admin, action_id, "Relatório do primeiro teste", "Pasta TI/restauracao/2026-01.pdf")
    d = tr.action_details(admin, action_id)
    assert [e["event_type"] for e in d["events"]] == ["criada", "status", "evidência registrada"]
    assert d["evidence"][0]["reference"].endswith(".pdf")
    with pytest.raises(RiskoraError):
        tr.add_evidence(admin, action_id, "sem referência", "")


def test_reavaliacao_cria_residual_sem_apagar_o_atual():
    conn, org, admin, aid, svc, risk, tr = _setup()
    before = _snapshot(conn, risk["id"])
    tr.reassess_risk(admin, risk["id"], 2, 3, "Testes trimestrais comprovam a recuperação", "Impacto mantido pelo ativo")
    res = svc.get_results(admin, aid)[0]
    assert res["residual"]["kind"] == "residual" and res["residual"]["score"] == 6 and res["residual"]["level"] == "Moderado"
    assert _snapshot(conn, risk["id"])[:len(before)] == before
    assert res["current"]["score"] == risk["current"]["score"]
    tr.reassess_risk(admin, risk["id"], 1, 3, "Segunda reavaliação, já com evidências", "Impacto mantido pelo ativo")
    assert len(svc.repo.list_risk_assessments(org, risk["id"])) == 4  # histórico preservado


def test_reavaliacao_exige_justificativa_e_escala_valida():
    conn, org, admin, aid, svc, risk, tr = _setup()
    with pytest.raises(RiskoraError):
        tr.reassess_risk(admin, risk["id"], 2, 3, "", "")
    with pytest.raises(RiskoraError):
        tr.reassess_risk(admin, risk["id"], 2, 3, "curto", "curto")
    with pytest.raises(RiskoraError):
        tr.reassess_risk(admin, risk["id"], 9, 3, "justificativa longa o bastante", "justificativa longa o bastante")
    tr.reassess_risk(admin, risk["id"], None, 3, "Ainda sem evidências dos testes", "Impacto mantido")
    assert svc.get_results(admin, aid)[0]["residual"]["level"] == "Dados insuficientes"


def test_acao_e_reavaliacao_exigem_avaliacao_concluida():
    conn = new_db()
    org = make_org(conn)
    admin = ctx_for(org, "admin")
    asset_id = backup_asset(conn, admin)
    svc = AssessmentService(conn)
    aid = svc.create_assessment(admin, asset_id)
    svc.save_answer(admin, aid, "Q10", "nao")
    svc.process_assessment(admin, aid)  # ainda rascunho
    risk = svc.get_results(admin, aid)[0]
    tr = TreatmentService(conn)
    with pytest.raises(RiskoraError):
        tr.create_action(admin, risk["id"], {"action": "x"})
    with pytest.raises(RiskoraError):
        tr.reassess_risk(admin, risk["id"], 2, 3, "justificativa longa o bastante", "justificativa longa o bastante")


def test_controle_nao_relacionado_ou_inexistente_e_rejeitado():
    conn, org, admin, aid, svc, risk, tr = _setup()
    with pytest.raises(RiskoraError):
        tr.create_action(admin, risk["id"], {"action": "x"}, control_code="RC-BK-04")
    with pytest.raises(RiskoraError):
        tr.create_action(admin, risk["id"], {"action": "x"}, control_code="RC-XX-99")
    with pytest.raises(NotFoundError):
        tr.create_action(admin, 99999, {"action": "x"})


@pytest.mark.parametrize("bad", [{"action": ""}, {"action": "x", "status": "Feito"}, {"action": "x", "priority": "Máxima"},
                                  {"action": "x", "due_date": "31/12/2026"}])
def test_validacao_de_campos_da_acao(bad):
    conn, org, admin, aid, svc, risk, tr = _setup()
    with pytest.raises(RiskoraError):
        tr.create_action(admin, risk["id"], bad)


def test_ciclo_de_vida_e_vencimento():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert is_overdue({"status": "Em andamento", "due_date": yesterday})
    assert is_overdue({"status": "Bloqueado", "due_date": yesterday})
    assert not is_overdue({"status": "Concluído", "due_date": yesterday})
    assert not is_overdue({"status": "Cancelado", "due_date": yesterday})
    assert not is_overdue({"status": "Não iniciado", "due_date": tomorrow})
    assert not is_overdue({"status": "Não iniciado", "due_date": None})
    assert lifecycle({"status": "Não iniciado"}) == "Planejada"
    assert lifecycle({"status": "Bloqueado"}) == "Em execução"
    assert lifecycle({"status": "Concluído"}) == "Concluída"
    assert lifecycle({"status": "Concluído", "validated_at": "2026-01-01T00:00:00Z"}) == "Validada"
    assert lifecycle({"status": "Cancelado"}) == "Cancelada"
