"""Modelos de regras de diagnóstico e de resultados de risco."""
from __future__ import annotations

from dataclasses import dataclass

from config.risk_methodology import DEFAULT_INHERENT_PROBABILITY

DEFAULT_LIMITATION = (
    "Conclusão baseada em respostas declaradas. "
    
)


@dataclass(frozen=True)
class DiagnosticRule:
    code: str
    title: str
    # {código da pergunta: respostas que ativam a regra}
    triggers: dict
    weakness: str
    evidence_description: str
    risk_scenario: str
    consequences: str
    probability_criteria: str
    impact_criteria: str
    impact_dimensions: tuple
    control_codes: tuple
    references: tuple
    limitations: str = DEFAULT_LIMITATION
    inherent_probability: int = DEFAULT_INHERENT_PROBABILITY

    @property
    def question_codes(self) -> tuple:
        return tuple(self.triggers.keys())


@dataclass(frozen=True)
class RiskResult:
    probability: int | None
    impact: int | None
    score: int | None
    level: str
    status: str  # "Calculado" ou "Dados insuficientes"


@dataclass(frozen=True)
class ImpactConsolidation:
    value: int | None
    driver: str | None
    missing: tuple
    justification: str
