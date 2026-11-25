import pytest

from services.assessment_service import AssessmentService
from services.asset_service import AssetService
from services.errors import RiskoraError
from tests.helpers import backup_asset, ctx_for, finalized, make_org, new_db


def _setup():
    conn = new_db()
    org = make_org(conn)
    ctx = ctx_for(org, "analyst")
    asset_id = backup_asset(conn, ctx)
    return conn, org, ctx, asset_id, AssessmentService(conn)


def test_inicio_de_avaliacao_associado_ao_ativo_com_versoes():
    conn, org, ctx, asset_id, svc = _setup()
    aid = svc.create_assessment(ctx, asset_id)
    a = svc.get_assessment(ctx, aid)
    assert a["asset_id"] == asset_id and a["status"] == "Rascunho" and a["organization_id"] == org
    assert a["methodology_version"] and a["questionnaire_version"] and a["rules_version"]


def test_categoria_sem_modulo_nao_permite_avaliacao():
    conn, org, ctx, asset_id, svc = _setup()
    other = AssetService(conn).create_asset(ctx, {"name": "Servidor", "category_code": "infraestrutura_servidores"})
    with pytest.raises(RiskoraError):
        svc.create_assessment(ctx, other)


def test_respostas_salvas_incompletas_e_evidencias():
    conn, org, ctx, asset_id, svc = _setup()
    aid = svc.create_assessment(ctx, asset_id)
    svc.save_answer(ctx, aid, "Q10", "nao", "Nunca testamos", "Chamado 123")
    got = svc.get_answers(ctx, aid)["Q10"]
    assert (got.value, got.justification, got.evidence_ref) == ("nao", "Nunca testamos", "Chamado 123")
    assert conn.execute("SELECT reference FROM evidence_records WHERE assessment_id=?", (aid,)).fetchone()[0] == "Chamado 123"
    comp = svc.completeness(ctx, aid)
    assert not comp.complete and "Q01" in comp.missing and "Q10A" not in comp.missing and comp.answered == 1
    svc.save_answer(ctx, aid, "Q10", "sim")  # sobrescreve a mesma pergunta; evidência some
    assert len(svc.get_answers(ctx, aid)) == 1
    assert conn.execute("SELECT COUNT(*) FROM evidence_records").fetchone()[0] == 0
    assert "Q10A" in svc.completeness(ctx, aid).missing  # agora a condicional é exigida


@pytest.mark.parametrize("code,value,just", [("Q99", "sim", ""), ("Q10", "talvez", ""), ("Q10", "sim", "x" * 3000),
                                              ("Q11", "nao_se_aplica", "")])
def test_respostas_invalidas_sao_rejeitadas(code, value, just):
    conn, org, ctx, asset_id, svc = _setup()
    aid = svc.create_assessment(ctx, asset_id)
    with pytest.raises(RiskoraError):
        svc.save_answer(ctx, aid, code, value, just)


def test_nao_se_aplica_com_justificativa_nao_gera_fragilidade():
    conn, org, ctx, asset_id, svc = _setup()
    aid = svc.create_assessment(ctx, asset_id)
    svc.save_answer(ctx, aid, "Q11", "nao_se_aplica", "Ativo estático sem requisito de recuperação")
    svc.finalize_assessment(ctx, aid)
    assert svc.get_results(ctx, aid) == []


def test_regras_bk001_a_bk005_geram_riscos_com_controles():
    conn = new_db()
    ctx = ctx_for(make_org(conn), "analyst")
    answers = {"Q10": "nao", "Q06": "nao", "Q09": "parcial", "Q02": "nao_sei", "Q08": "nao"}
    _, aid, svc = finalized(conn, ctx, answers)
    results = {r["rule_code"]: r for r in svc.get_results(ctx, aid)}
    assert {"BK-001", "BK-002", "BK-003", "BK-004", "BK-005"} <= set(results)
    assert results["BK-004"]["basis"] == "knowledge_gap" and results["BK-001"]["basis"] == "declared_gap"
    assert results["BK-003"]["basis"] == "partial"
    for r in results.values():
        assert r["controls"] and r["limitations"] and r["current"] and r["inherent"] and r["residual"] is None


def test_nao_sei_gera_lacuna_provisoria_e_nao_constatacao():
    conn = new_db()
    ctx = ctx_for(make_org(conn), "analyst")
    _, aid, svc = finalized(conn, ctx, {"Q06": "nao_sei"})
    r = svc.get_results(ctx, aid)[0]
    assert r["basis"] == "knowledge_gap" and r["evidence_status"] == "lacuna_de_conhecimento"
    assert r["current"]["probability"] == 3 and "provisória" in r["current"]["notes"]
    assert "não equivale a vulnerabilidade técnica confirmada" in r["explanation"]


def test_ativo_sem_impactos_resulta_em_dados_insuficientes():
    conn = new_db()
    ctx = ctx_for(make_org(conn), "analyst")
    _, aid, svc = finalized(conn, ctx, {"Q10": "nao"}, impacts={})
    cur = svc.get_results(ctx, aid)[0]["current"]
    assert cur["level"] == "Dados insuficientes" and cur["score"] is None and "não informados" in cur["notes"]


def test_avaliacao_concluida_e_imutavel_e_nova_versao_preserva_a_anterior():
    conn = new_db()
    ctx = ctx_for(make_org(conn), "analyst")
    asset_id, aid, svc = finalized(conn, ctx, {"Q10": "nao"})
    before = svc.get_results(ctx, aid)
    with pytest.raises(RiskoraError):
        svc.save_answer(ctx, aid, "Q10", "sim")
    with pytest.raises(RiskoraError):
        svc.process_assessment(ctx, aid)
    new_id = svc.clone_assessment(ctx, aid)
    svc.save_answer(ctx, new_id, "Q10", "sim")
    svc.save_answer(ctx, new_id, "Q10A", "sim")
    svc.finalize_assessment(ctx, new_id)
    assert svc.get_results(ctx, aid) == before and svc.get_results(ctx, new_id) == []
    assert svc.get_assessment(ctx, new_id)["parent_assessment_id"] == aid
    history = svc.list_assessments(ctx, asset_id)
    assert [h["id"] for h in history] == [new_id, aid]  # histórico completo, mais recente primeiro


def test_reprocessar_rascunho_nao_duplica_resultados():
    conn, org, ctx, asset_id, svc = _setup()
    aid = svc.create_assessment(ctx, asset_id)
    svc.save_answer(ctx, aid, "Q10", "nao")
    svc.process_assessment(ctx, aid)
    svc.process_assessment(ctx, aid)
    assert len(svc.get_results(ctx, aid)) == 1
    svc.save_answer(ctx, aid, "Q10", "sim")
    svc.save_answer(ctx, aid, "Q10A", "sim")
    svc.process_assessment(ctx, aid)
    assert svc.get_results(ctx, aid) == []


def test_resumo_do_ativo_usa_a_ultima_avaliacao_concluida():
    conn = new_db()
    ctx = ctx_for(make_org(conn), "analyst")
    asset_id, aid, svc = finalized(conn, ctx, {"Q10": "nao", "Q06": "nao"})
    svc.create_assessment(ctx, asset_id)  # rascunho novo não substitui a concluída
    summary = svc.asset_summary(ctx, asset_id)
    assert summary["latest"]["id"] == aid and len(summary["drafts"]) == 1
    assert sum(summary["level_counts"].values()) == 2
