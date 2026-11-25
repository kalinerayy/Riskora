"""Configurações da aplicação, lidas de variáveis de ambiente. Nenhum segredo fica no código-fonte."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    db_path: Path
    session_idle_minutes: int = 30       # expira após inatividade
    session_absolute_hours: int = 8      # expira mesmo com uso contínuo
    max_failed_logins: int = 5           # falhas seguidas antes do bloqueio temporário
    lockout_minutes: int = 15
    reset_token_minutes: int = 30        # validade do token de recuperação emitido pelo administrador
    min_password_length: int = 10
    scrypt_n: int = 2 ** 15              # custo do hash de senha (memória ~32 MB)
    guest_access: bool = False           # valor do objeto; em load_settings() o padrão do ambiente é LIGADO (on)
    guest_role: str = "guest"            # perfil do visitante; nunca administrador


GUEST_ALLOWED_ROLES = ("guest", "reader", "analyst", "manager")  # o visitante nunca recebe perfil de administrador


def _guest_role() -> str:
    role = os.environ.get("RISKORA_GUEST_ROLE", "guest").strip().lower()
    return role if role in GUEST_ALLOWED_ROLES else "guest"


def load_settings() -> Settings:
    return Settings(
        db_path=Path(os.environ.get("RISKORA_DB", BASE_DIR / "data" / "riskora.db")),
        session_idle_minutes=_int_env("RISKORA_SESSION_IDLE_MINUTES", 30),
        session_absolute_hours=_int_env("RISKORA_SESSION_ABSOLUTE_HOURS", 8),
        max_failed_logins=_int_env("RISKORA_MAX_FAILED_LOGINS", 5),
        lockout_minutes=_int_env("RISKORA_LOCKOUT_MINUTES", 15),
        reset_token_minutes=_int_env("RISKORA_RESET_TOKEN_MINUTES", 30),
        min_password_length=_int_env("RISKORA_MIN_PASSWORD_LENGTH", 10, minimum=10),
        scrypt_n=_int_env("RISKORA_SCRYPT_N", 2 ** 15, minimum=2 ** 10),
        guest_access=os.environ.get("RISKORA_GUEST_ACCESS", "on").strip().lower() in ("on", "1", "true", "sim"),
        guest_role=_guest_role(),
    )
