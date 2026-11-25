"""Cria a organização inicial e o primeiro administrador. A senha é pedida no terminal (nunca vai no código).

Uso (na pasta do projeto, com o ambiente virtual ativo):
    python -m scripts.create_admin --email voce@exemplo.com --name "Seu Nome" --org-name "Minha Organização" --org-slug minha-org
"""
from __future__ import annotations

import argparse
import getpass
import sys

from database.connection import get_connection, init_database
from database.repositories.accounts import AccountRepository
from services.audit_service import AuditService
from services.authentication_service import AuthenticationService
from services.errors import RiskoraError
from services.organization_service import OrganizationService
from services.validation import clean_email, clean_slug


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria organização e administrador inicial da Riskora.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--org-name", required=True)
    parser.add_argument("--org-slug", required=True)
    args = parser.parse_args()
    conn = get_connection()
    init_database(conn)
    auth = AuthenticationService(conn)
    accounts = AccountRepository(conn)
    try:
        email, slug = clean_email(args.email), clean_slug(args.org_slug)
        org = accounts.get_organization_by_slug(slug)
        org_id = org["id"] if org else OrganizationService(conn, auth).create_organization(args.org_name, slug)
        user = accounts.get_user_by_email(email)
        with conn:
            if user is None:
                password = getpass.getpass("Senha do administrador: ")
                if password != getpass.getpass("Repita a senha: "):
                    print("As senhas não coincidem.", file=sys.stderr)
                    return 1
                auth.validate_password(password, email)
                user_id = accounts.create_user(email, args.name.strip(), auth.hash_password(password), False)
            else:
                user_id = user["id"]
            if accounts.get_membership(org_id, user_id):
                print("Este usuário já faz parte da organização.")
            else:
                accounts.add_member(org_id, user_id, "admin")
                AuditService(conn).log(org_id, None, "admin_provisioned", "user", user_id, "via script")
    except RiskoraError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print(f"Pronto. Administrador {email} na organização '{slug}'. Execute: streamlit run app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
