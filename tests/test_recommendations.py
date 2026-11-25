from modules.backup.controls import CONTROLS, CONTROLS_BY_CODE
from modules.backup.rules import RULES, RULES_BY_CODE
from services.recommendation_engine import controls_for_rule, explain_finding, has_unvalidated_references
import pytest


def test_toda_regra_aponta_para_controles_existentes():
    for rule in RULES:
        assert controls_for_rule(rule, CONTROLS_BY_CODE)


def test_relacao_regra_controle_e_consistente_nos_dois_sentidos():
    for rule in RULES:
        for code in rule.control_codes:
            assert rule.code in CONTROLS_BY_CODE[code].addresses_rules, f"{code} deveria listar {rule.code}"
    for control in CONTROLS:
        for rule_code in control.addresses_rules:
            assert rule_code in RULES_BY_CODE
            assert control.code in RULES_BY_CODE[rule_code].control_codes, f"{rule_code} deveria listar {control.code}"


def test_codigo_de_controle_inexistente_e_rejeitado():
    rule = RULES[0]
    with pytest.raises(KeyError):
        controls_for_rule(rule, {})


def test_todas_as_referencias_estao_marcadas_como_a_validar():
    for control in CONTROLS:
        assert control.references, control.code
        assert has_unvalidated_references(control)
        for ref in control.references:
            assert ref.validation_status == "Referência a validar"
            assert ref.source_consulted


def test_controles_tem_campos_obrigatorios_e_tipo_valido():
    for c in CONTROLS:
        assert c.code.startswith("RC-BK-") and c.name and c.objective and c.description
        assert c.control_type in ("preventivo", "detectivo", "corretivo")
        assert c.implementation_actions and c.expected_evidence


def test_catalogo_tem_codigos_unicos():
    codes = [c.code for c in CONTROLS]
    assert len(codes) == len(set(codes))


def test_explicacao_menciona_limitacao_e_classificacao():
    text = explain_finding("Teste", "declared_gap", "apenas_declarada", [("Q10", "nao")], "Alto", 16)
    assert "Alto" in text and "não equivale a vulnerabilidade técnica confirmada" in text
    insuf = explain_finding("Teste", "knowledge_gap", "lacuna_de_conhecimento", [("Q06", "nao_sei")], "Dados insuficientes", None)
    assert "dados insuficientes" in insuf.lower()
