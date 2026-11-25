"""Validação de entradas (texto, escolhas, datas, escalas). Falhas levantam RiskoraError (um ValueError)."""
from __future__ import annotations

import re
from datetime import date

from services.errors import RiskoraError


def clean_text(value, field: str, max_len: int = 2000, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise RiskoraError(f"{field}: valor de texto inválido.")
    text = value.strip()
    if required and not text:
        raise RiskoraError(f"{field}: campo obrigatório.")
    if len(text) > max_len:
        raise RiskoraError(f"{field}: máximo de {max_len} caracteres.")
    if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in text):
        raise RiskoraError(f"{field}: contém caracteres de controle não permitidos.")
    return text


def require_choice(value, choices, field: str):
    if value not in choices:
        raise RiskoraError(f"{field}: opção inválida.")
    return value


def clean_date(value, field: str, required: bool = False) -> str | None:
    if value in (None, ""):
        if required:
            raise RiskoraError(f"{field}: campo obrigatório.")
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise RiskoraError(f"{field}: data inválida (use AAAA-MM-DD).") from exc


def clean_scale(value, field: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise RiskoraError(f"{field}: informe um inteiro de 1 a 5 ou deixe como não informado.")
    return value


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$")


def clean_email(value) -> str:
    email = clean_text(value, "E-mail", 254, required=True).lower()
    if not _EMAIL.match(email):
        raise RiskoraError("E-mail: formato inválido.")
    return email


def clean_slug(value) -> str:
    slug = clean_text(value, "Identificação", 60, required=True).lower()
    if not _SLUG.match(slug):
        raise RiskoraError("Identificação: use letras minúsculas, números e hífen (2 a 60 caracteres).")
    return slug
