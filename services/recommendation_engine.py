"""Relaciona fragilidades a controles recomendados e monta explicações textuais."""
from __future__ import annotations

from config.risk_methodology import ANSWER_OPTIONS, BASIS_LABELS, EVIDENCE_LABELS
from models.control import Control
from models.risk import DiagnosticRule


def controls_for_rule(rule: DiagnosticRule, controls_by_code: dict[str, Control]) -> list[Control]:
    """Controles recomendados para a regra, na ordem de prioridade definida na própria regra."""
    missing = [c for c in rule.control_codes if c not in controls_by_code]
    if missing:
        raise KeyError(f"Regra {rule.code} referencia controles inexistentes: {missing}")
    return [controls_by_code[c] for c in rule.control_codes]


def has_unvalidated_references(control: Control) -> bool:
    return any(ref.validation_status != "Validada" for ref in control.references)


def explain_finding(rule_title: str, basis: str, evidence_status: str, triggered: list[tuple[str, str]],
                    level: str, score) -> str:
    answers_text = "; ".join(f"{code} = {ANSWER_OPTIONS.get(val, val)}" for code, val in triggered)
    text = (f"{rule_title}. Base: {BASIS_LABELS[basis]} ({answers_text}). "
            f"Evidência: {EVIDENCE_LABELS[evidence_status]}. ")
    if score is None:
        text += "Classificação: dados insuficientes para calcular o risco (verifique os impactos do ativo)."
    else:
        text += f"Classificação atual: {level} (pontuação {score})."
    text += " Conclusão baseada em respostas declaradas; não equivale a vulnerabilidade técnica confirmada."
    return text
