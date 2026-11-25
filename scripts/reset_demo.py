"""Restaura a organização de DEMONSTRAÇÃO (os visitantes podem editá-la, então ela acumula alterações).

A demonstração atual é arquivada (nada é apagado) e uma nova, limpa, é criada.

Uso:  python -m scripts.reset_demo --yes
"""
from __future__ import annotations

import argparse
import sys

from database.connection import get_connection, init_database
from services.demo_data import reset_demo


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura a organização de demonstração da Riskora.")
    parser.add_argument("--yes", action="store_true", help="confirma a restauração")
    args = parser.parse_args()
    if not args.yes:
        print("Isto arquiva a demonstração atual (com as alterações dos visitantes) e cria uma nova.\n"
              "Rode de novo com --yes para confirmar.", file=sys.stderr)
        return 1
    conn = get_connection()
    init_database(conn)
    reset_demo(conn)
    print("Demonstração restaurada. A anterior foi arquivada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
