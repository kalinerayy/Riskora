"""Modelos do catálogo de controles."""
from __future__ import annotations

from dataclasses import dataclass

CONTROL_TYPES = ("preventivo", "detectivo", "corretivo")
VALIDATION_PENDING = "Referência a validar"
VALIDATION_OK = "Validada"


@dataclass(frozen=True)
class ControlReference:
    framework: str
    ref_code: str
    ref_title: str
    source_consulted: str
    validation_status: str = VALIDATION_PENDING


@dataclass(frozen=True)
class Control:
    code: str
    name: str
    objective: str
    description: str
    control_type: str
    addresses_rules: tuple
    implementation_actions: tuple
    expected_evidence: tuple
    references: tuple
