"""Motor de regras de diagnóstico (independente de interface e de banco).

Princípios:
- "Não"/"Parcialmente" geram fragilidade POTENCIAL; "Não sei" gera lacuna de conhecimento/evidência.
- "Sim" e "Não se aplica" não geram fragilidade.
- Perguntas condicionais não visíveis são ignoradas.
- Nenhuma conclusão equivale a vulnerabilidade técnica confirmada.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from models.assessment import Answer, Completeness, FindingResult, Question
from models.risk import DiagnosticRule


def evaluate_rule(rule: DiagnosticRule, questions_by_code: Mapping[str, Question],
                  answers: Mapping[str, Answer]) -> FindingResult | None:
    triggered: list[Answer] = []
    for qcode, trigger_values in rule.triggers.items():
        question = questions_by_code[qcode]
        answer = answers.get(qcode)
        if answer is None or not question.is_visible(answers):
            continue
        if answer.value in trigger_values:
            triggered.append(answer)
    if not triggered:
        return None
    values = {a.value for a in triggered}
    if "nao" in values:
        basis = "declared_gap"
    elif "parcial" in values:
        basis = "partial"
    else:
        basis = "knowledge_gap"
    if basis == "knowledge_gap":
        evidence = "lacuna_de_conhecimento"
    elif any(a.evidence_ref.strip() for a in triggered):
        evidence = "referenciada"
    else:
        evidence = "apenas_declarada"
    return FindingResult(rule.code, basis, evidence, tuple((a.question_code, a.value) for a in triggered))


def evaluate_all(rules: Iterable[DiagnosticRule], questions: Iterable[Question],
                 answers: Mapping[str, Answer]) -> list[FindingResult]:
    by_code = {q.code: q for q in questions}
    results = []
    for rule in rules:
        finding = evaluate_rule(rule, by_code, answers)
        if finding is not None:
            results.append(finding)
    return results


def assessment_completeness(questions: Iterable[Question], answers: Mapping[str, Answer]) -> Completeness:
    visible = [q for q in questions if q.is_visible(answers)]
    missing = tuple(q.code for q in visible if q.code not in answers)
    return Completeness(total=len(visible), answered=len(visible) - len(missing), missing=missing)


def find_unverified_claims(questions: Iterable[Question], answers: Mapping[str, Answer]) -> list[str]:
    """Perguntas visíveis respondidas 'Sim' SEM referência de evidência.

    Não geram risco nem probabilidade (seria inventar um resultado): são um aviso de que a afirmação
    ainda não está comprovada. Um controle declarado e ineficaz passaria despercebido sem este aviso.
    """
    return [q.code for q in questions
            if q.code in answers and q.is_visible(answers)
            and answers[q.code].value == "sim" and not answers[q.code].evidence_ref.strip()]
