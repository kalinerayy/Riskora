"""Carrega a organização DEMONSTRATIVA (dados fictícios) e concede acesso a um usuário existente.

Uso:  python -m scripts.load_demo --email voce@exemplo.com
"""
from __future__ import annotations

import argparse
import sys

from database.connection import get_connection, init_database
from database.repositories.accounts import AccountRepository
from services.demo_data import attach_user, load_demo
from services.errors import RiskoraError
from services.validation import clean_email


def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega a organização de demonstração da Riskora.")
    parser.add_argument("--email", required=True, help="e-mail de um usuário já existente (será administrador da demo)")
    args = parser.parse_args()
    conn = get_connection()
    init_database(conn)
    try:
        user = AccountRepository(conn).get_user_by_email(clean_email(args.email))
        if not user:
            print("Usuário não encontrado. Crie-o antes com scripts.create_admin.", file=sys.stderr)
            return 1
        org_id = load_demo(conn, user["id"])
        attach_user(conn, org_id, user["id"], "admin")
    except RiskoraError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print("Organização de demonstração pronta (dados fictícios). Escolha-a no seletor de organização.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
