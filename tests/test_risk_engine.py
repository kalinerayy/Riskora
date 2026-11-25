import pytest

from config.risk_methodology import RISK_BANDS
from services.risk_engine import (
    calculate_risk, classify_score, consolidate_impact, probability_from_basis, requires_treatment,
)


@pytest.mark.parametrize("score,expected", [
    (1, "Baixo"), (4, "Baixo"), (5, "Moderado"), (9, "Moderado"),
    (10, "Alto"), (16, "Alto"), (17, "Crítico"), (25, "Crítico"),
])
def test_classificacao_nos_limites_das_faixas(score, expected):
    assert classify_score(score) == expected


@pytest.mark.parametrize("score", [0, 26, -1])
def test_classificacao_fora_da_escala_levanta_erro(score):
    with pytest.raises(ValueError):
        classify_score(score)


def test_faixas_cobrem_1_a_25_sem_lacunas_nem_sobreposicao():
    covered = []
    for low, high, _ in RISK_BANDS:
        covered.extend(range(low, high + 1))
    assert sorted(covered) == list(range(1, 26))


def test_calculo_em_todas_as_combinacoes_da_matriz():
    for p in range(1, 6):
        for i in range(1, 6):
            r = calculate_risk(p, i)
            assert r.score == p * i
            assert r.level == classify_score(p * i)
            assert r.status == "Calculado"


def test_extremos_da_escala():
    assert calculate_risk(1, 1).level == "Baixo"
    assert calculate_risk(5, 5).score == 25 and calculate_risk(5, 5).level == "Crítico"


@pytest.mark.parametrize("p,i", [(0, 3), (6, 3), (3, 0), (3, 6), (True, 3), (3.5, 3), ("3", 3)])
def test_valores_invalidos_sao_rejeitados(p, i):
    with pytest.raises(ValueError):
        calculate_risk(p, i)


@pytest.mark.parametrize("p,i", [(None, 3), (3, None), (None, None)])
def test_dados_insuficientes_nao_geram_numero(p, i):
    r = calculate_risk(p, i)
    assert r.score is None
    assert r.level == "Dados insuficientes"
    assert r.status == "Dados insuficientes"


def test_consolidacao_usa_maximo_e_nao_media():
    c = consolidate_impact({"availability": 5, "integrity": 1, "operational": 1}, ("availability", "integrity", "operational"))
    assert c.value == 5  # a média seria ~2,3 e esconderia o impacto crítico
    assert c.driver == "availability"


def test_consolidacao_registra_dimensoes_nao_informadas():
    c = consolidate_impact({"availability": 3}, ("availability", "legal"))
    assert c.value == 3
    assert c.missing == ("legal",)
    assert "não informadas" in c.justification


def test_consolidacao_sem_nenhuma_dimensao_resulta_em_dados_insuficientes():
    c = consolidate_impact({}, ("availability", "integrity"))
    assert c.value is None
    assert calculate_risk(4, c.value).level == "Dados insuficientes"


def test_consolidacao_ignora_dimensoes_irrelevantes():
    c = consolidate_impact({"availability": 2, "confidentiality": 5}, ("availability",))
    assert c.value == 2


def test_consolidacao_rejeita_dimensao_desconhecida():
    with pytest.raises(ValueError):
        consolidate_impact({}, ("inventada",))


def test_probabilidade_por_base_e_explicavel():
    p, text = probability_from_basis("declared_gap")
    assert p == 4 and text
    assert probability_from_basis("knowledge_gap")[0] == 3
    with pytest.raises(ValueError):
        probability_from_basis("outra")


def test_necessidade_de_tratamento():
    assert requires_treatment("Alto") and requires_treatment("Crítico")
    assert not requires_treatment("Baixo") and not requires_treatment("Moderado")
