"""Definição do módulo de avaliação de Backup e Recuperação de Dados."""
from models.assessment import AssessmentModule
from modules.backup import controls, questions, rules

BACKUP_MODULE = AssessmentModule(
    code=questions.TEMPLATE_CODE,
    name=questions.TEMPLATE_NAME,
    category_code="backup_recuperacao",
    questionnaire_version=questions.QUESTIONNAIRE_VERSION,
    rules_version=rules.RULES_VERSION,
    questions=questions.QUESTIONS,
    rules=rules.RULES,
    controls=controls.CONTROLS,
)
