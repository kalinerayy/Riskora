"""Registro central dos módulos de avaliação e do catálogo de controles."""
from __future__ import annotations

from models.assessment import AssessmentModule
from models.control import Control
from modules.backup.assessment import BACKUP_MODULE

MODULES: tuple[AssessmentModule, ...] = (BACKUP_MODULE,)


def get_module_for_category(category_code: str) -> AssessmentModule | None:
    return next((m for m in MODULES if m.category_code == category_code), None)


def get_module_by_versions(code: str, questionnaire_version: str, rules_version: str) -> AssessmentModule | None:
    return next((m for m in MODULES if (m.code, m.questionnaire_version, m.rules_version)
                 == (code, questionnaire_version, rules_version)), None)


def all_controls() -> list[Control]:
    """Catálogo centralizado: união dos controles de todos os módulos (sem duplicar códigos)."""
    seen: dict[str, Control] = {}
    for module in MODULES:
        for control in module.controls:
            seen.setdefault(control.code, control)
    return list(seen.values())
