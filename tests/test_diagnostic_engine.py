from modules.backup.questions import QUESTIONS, QUESTIONS_BY_CODE
from modules.backup.rules import RULES, RULES_BY_CODE
from services.diagnostic_engine import assessment_completeness, evaluate_all, evaluate_rule
from tests.helpers import answers_of


def _find(answers, code):
    return next((f for f in evaluate_all(RULES, QUESTIONS, answers) if f.rule_code == code), None)


def test_regras_referenciam_perguntas_existentes():
    for rule in RULES:
        for q in rule.question_codes:
            assert q in QUESTIONS_BY_CODE, f"{rule.code} -> {q}"


def test_banco_inicial_tem_pelo_menos_12_perguntas_com_ids_unicos():
    codes = [q.code for q in QUESTIONS]
    assert len(codes) == len(set(codes))
    for n in range(1, 13):
        assert f"Q{n:02d}" in codes


def test_cobre_os_11_dominios():
    assert {q.domain_no for q in QUESTIONS} == set(range(1, 12))


def test_nao_em_testes_de_restauracao_identifica_bk001():
    f = _find(answers_of(Q10="nao"), "BK-001")
    assert f is not None and f.basis == "declared_gap"
    assert f.evidence_status == "apenas_declarada"


def test_sim_nao_gera_fragilidade():
    assert evaluate_all(RULES, QUESTIONS, answers_of(**{q.code: "sim" for q in QUESTIONS})) == []


def test_parcial_gera_controle_parcial():
    assert _find(answers_of(Q06="parcial"), "BK-002").basis == "partial"


def test_nao_sei_e_lacuna_de_conhecimento_e_nao_ausencia_do_controle():
    f = _find(answers_of(Q06="nao_sei"), "BK-002")
    assert f.basis == "knowledge_gap"
    assert f.basis != "declared_gap"
    assert f.evidence_status == "lacuna_de_conhecimento"


def test_nao_se_aplica_nao_gera_fragilidade():
    assert _find(answers_of(Q06=("nao_se_aplica", "Sem ambiente local", "")), "BK-002") is None


def test_evidencia_referenciada_e_registrada():
    f = _find(answers_of(Q09=("nao", "", "Relatório X")), "BK-003")
    assert f.evidence_status == "referenciada"


def test_resposta_ausente_nao_gera_conclusao():
    assert evaluate_all(RULES, QUESTIONS, {}) == []


def test_pergunta_condicional_oculta_e_ignorada():
    # Q10 = não: Q10A não se aplica, mesmo que exista uma resposta antiga armazenada
    ans = answers_of(Q10="nao", Q10A="nao")
    f = _find(ans, "BK-001")
    assert f.triggered_by == (("Q10", "nao"),)


def test_backup_regular_nao_dispensa_avaliar_restauracao():
    # Backups automáticos, testes existem, mas o último teste falhou -> ainda há fragilidade
    ans = answers_of(Q04="sim", Q10="sim", Q10A="nao")
    f = _find(ans, "BK-001")
    assert f is not None and ("Q10A", "nao") in f.triggered_by


def test_completude_considera_apenas_perguntas_visiveis():
    # Q10 = não: Q10A fica oculta e, portanto, não é exigida para a avaliação estar completa
    ans = answers_of(**{q.code: "sim" for q in QUESTIONS if q.code not in ("Q10", "Q10A")}, Q10="nao")
    assert assessment_completeness(QUESTIONS, ans).complete


def test_completude_com_q10_sim_exige_q10a():
    ans = answers_of(**{q.code: "sim" for q in QUESTIONS if q.code != "Q10A"})
    comp = assessment_completeness(QUESTIONS, ans)
    assert not comp.complete and comp.missing == ("Q10A",)
    assert comp.percent < 100


def test_avaliacao_incompleta_lista_o_que_falta():
    comp = assessment_completeness(QUESTIONS, answers_of(Q01="sim"))
    assert not comp.complete and "Q02" in comp.missing and comp.answered == 1
    assert "Q10A" not in comp.missing  # condicional oculta


def test_resposta_negativa_nao_equivale_a_vulnerabilidade_confirmada():
    rule = RULES_BY_CODE["BK-002"]
    f = evaluate_rule(rule, QUESTIONS_BY_CODE, answers_of(Q06="nao"))
    assert f.basis == "declared_gap" and f.evidence_status == "apenas_declarada"
    assert "constatação técnica confirmada" in rule.limitations or "verificação técnica" in rule.limitations
    assert all(r.limitations for r in RULES)
