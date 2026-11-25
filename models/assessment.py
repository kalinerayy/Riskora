"""Modelos de questionário e resultados de diagnóstico."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Answer:
    question_code: str
    value: str
    justification: str = ""
    evidence_ref: str = ""


@dataclass(frozen=True)
class Question:
    code: str
    domain_no: int
    domain: str
    text: str
    purpose: str
    # Pergunta condicional: só é exibida/considerada se a pergunta-pai tiver uma destas respostas.
    parent_code: str | None = None
    parent_answers: tuple[str, ...] = ()

    def is_visible(self, answers: Mapping[str, Answer]) -> bool:
        if self.parent_code is None:
            return True
        parent = answers.get(self.parent_code)
        return parent is not None and parent.value in self.parent_answers


@dataclass(frozen=True)
class FindingResult:
    rule_code: str
    basis: str  # declared_gap | partial | knowledge_gap
    evidence_status: str  # referenciada | apenas_declarada | lacuna_de_conhecimento
    triggered_by: tuple[tuple[str, str], ...]  # (código da pergunta, valor da resposta)


@dataclass(frozen=True)
class Completeness:
    total: int
    answered: int
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.total > 0 and not self.missing

    @property
    def percent(self) -> int:
        return 0 if self.total == 0 else round(100 * self.answered / self.total)


@dataclass(frozen=True)
class AssessmentModule:
    """Um módulo de avaliação = perguntas + regras + controles de UMA categoria de ativo.

    Para criar um novo tipo de avaliação (ex.: Bancos de dados), crie modules/<nome>/ com um
    AssessmentModule e registre-o em modules/registry.py. O núcleo do sistema não muda.
    """
    code: str
    name: str
    category_code: str
    questionnaire_version: str
    rules_version: str
    questions: tuple
    rules: tuple
    controls: tuple
