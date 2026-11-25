"""Motor de cálculo de risco (puro, sem acesso a banco ou interface).

Risco = Probabilidade x Impacto, ambos de 1 a 5. Sem dados suficientes, o resultado é
"Dados insuficientes": nenhum número é inventado.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from config.risk_methodology import (
    BASIS_PROBABILITY, IMPACT_DIMENSIONS, IMPACT_SCALE, INSUFFICIENT_DATA, RISK_BANDS,
    TREATMENT_REQUIRED_LEVELS,
)
from models.risk import ImpactConsolidation, RiskResult


def validate_scale_value(value, name: str) -> int | None:
    """Aceita None (desconhecido) ou inteiro de 1 a 5. Rejeita bool, float e fora da faixa."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError(f"{name} deve ser um número inteiro entre 1 e 5 (recebido: {value!r}).")
    return value


def classify_score(score: int) -> str:
    for low, high, label in RISK_BANDS:
        if low <= score <= high:
            return label
    raise ValueError(f"Pontuação fora da escala configurada: {score!r}.")


def calculate_risk(probability, impact) -> RiskResult:
    p = validate_scale_value(probability, "Probabilidade")
    i = validate_scale_value(impact, "Impacto")
    if p is None or i is None:
        return RiskResult(p, i, None, INSUFFICIENT_DATA, INSUFFICIENT_DATA)
    score = p * i
    return RiskResult(p, i, score, classify_score(score), "Calculado")


def requires_treatment(level: str) -> bool:
    return level in TREATMENT_REQUIRED_LEVELS


def consolidate_impact(values: Mapping[str, int | None], relevant: Iterable[str]) -> ImpactConsolidation:
    """Impacto consolidado = MAIOR valor entre as dimensões relevantes informadas (sem médias)."""
    relevant = tuple(relevant)
    unknown_dims = [d for d in relevant if d not in IMPACT_DIMENSIONS]
    if unknown_dims:
        raise ValueError(f"Dimensões de impacto desconhecidas: {unknown_dims}")
    known = {}
    for dim in relevant:
        v = validate_scale_value(values.get(dim), f"Impacto ({dim})")
        if v is not None:
            known[dim] = v
    missing = tuple(d for d in relevant if d not in known)
    if not known:
        return ImpactConsolidation(None, None, missing, "Nenhuma dimensão de impacto relevante foi informada para o ativo.")
    top = max(known.values())
    driver = next(d for d in relevant if known.get(d) == top)
    text = (f"Impacto {top} ({IMPACT_SCALE[top][0]}) definido pela dimensão "
            f"'{IMPACT_DIMENSIONS[driver]}' (maior valor entre as dimensões relevantes).")
    if missing:
        text += " Dimensões relevantes não informadas: " + ", ".join(IMPACT_DIMENSIONS[d] for d in missing) + "."
    return ImpactConsolidation(top, driver, missing, text)


def probability_from_basis(basis: str) -> tuple[int, str]:
    """Probabilidade atual derivada da base da conclusão, conforme tabela configurada."""
    if basis not in BASIS_PROBABILITY:
        raise ValueError(f"Base de conclusão desconhecida: {basis!r}")
    return BASIS_PROBABILITY[basis]
