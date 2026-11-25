"""Organização DEMONSTRATIVA com dados fictícios, separada dos dados reais (is_demo=1).

Não cria usuários nem senhas: o acesso é concedido por scripts/load_demo.py a um usuário já existente.
"""
from __future__ import annotations

import secrets
from datetime import date, timedelta

from database.repositories.accounts import AccountRepository
from models.user import ROLE_PERMISSIONS, Context
from services.asset_service import AssetService
from services.clock import to_iso, utcnow
from services.assessment_service import AssessmentService
from services.organization_service import OrganizationService
from services.treatment_service import TreatmentService

DEMO_SLUG = "demo-riskora"
DEMO_NAME = "Empresa Fictícia Alfa Ltda"

_BACKUP = "backup_recuperacao"
_ALL_YES = {f"Q{n:02d}": "sim" for n in range(1, 13)} | {"Q10A": "sim"}

# nome, categoria, impactos (D, I, C, Op, Fin, Leg), respostas, descrição do cenário
_ASSETS = (
    ("Backup do Servidor ERP (fictício)", _BACKUP, (5, 4, 3, 5, 4, 3),
     _ALL_YES | {"Q07": "parcial", "Q10": "nao", "Q12": "parcial"} ,
     "Backups automatizados, mas sem testes de restauração."),
    ("Backup do Sistema de Faturamento (fictício)", _BACKUP, (4, 4, 3, 4, 5, 4),
     _ALL_YES | {"Q02": "parcial", "Q03": "parcial", "Q10A": "parcial", "Q11": "parcial"},
     "Ativo crítico parcialmente coberto."),
    ("Backup do Servidor de Arquivos (fictício)", _BACKUP, (3, 3, 4, 3, 3, 2),
     _ALL_YES | {"Q06": "nao_sei", "Q07": "nao_sei"},
     "Sem evidências sobre o isolamento das cópias."),
    ("Backup do Banco de Dados de RH (fictício)", _BACKUP, (4, 5, 5, 3, 3, 5),
     _ALL_YES, "Processo de backup com monitoramento documentado."),
    ("Backup do Portal de Clientes (fictício)", _BACKUP, (4, 4, 5, 4, 4, 4),
     _ALL_YES | {"Q08": "parcial"}, "Controle de acesso aos backups com implementação parcial."),
)
_EVIDENCES = {"Backup do Banco de Dados de RH (fictício)": {
    "Q09": "Relatório diário de backup (fictício)", "Q12": "Pasta de registros (fictícia)"}}


def load_demo(conn, actor_user_id: int | None = None) -> int:
    """Cria (uma única vez) a organização demonstrativa. Devolve o id da organização."""
    accounts = AccountRepository(conn)
    existing = accounts.get_organization_by_slug(DEMO_SLUG)
    if existing:
        return existing["id"]
    org_id = OrganizationService(conn).create_organization(
        DEMO_NAME, DEMO_SLUG, "DADOS FICTÍCIOS para demonstração.", "Organização de demonstração.",
        "Responsável fictício", is_demo=True)
    ctx = Context(actor_user_id, "demo@local", "Avaliador Demo", org_id, "admin", ROLE_PERMISSIONS["admin"])
    assets, assessments, treatment = AssetService(conn), AssessmentService(conn), TreatmentService(conn)
    erp_risk = None
    for name, category, imp, answers, scenario in _ASSETS:
        asset_id = assets.create_asset(ctx, {
            "name": name, "category_code": category, "description": f"[FICTÍCIO] {scenario}", "area": "TI",
            "owner": "Responsável fictício", "environment": "Produção", "criticality": "Alta",
            "information_classification": "Confidencial", "availability_requirement": "Alta",
            "impact_availability": imp[0], "impact_integrity": imp[1], "impact_confidentiality": imp[2],
            "impact_operational": imp[3], "impact_financial": imp[4], "impact_legal": imp[5],
            "impact_justification": "Valores fictícios para demonstração."})
        aid = assessments.create_assessment(ctx, asset_id)
        evidence = _EVIDENCES.get(name, {})
        for code, value in answers.items():
            assessments.save_answer(ctx, aid, code, value, "Resposta fictícia.", evidence.get(code, ""))
        assessments.finalize_assessment(ctx, aid)
        if erp_risk is None:
            erp_risk = next((r for r in assessments.get_results(ctx, aid) if r["rule_code"] == "BK-001"), None)
    assets.create_asset(ctx, {"name": "Servidor de Aplicações (fictício)", "category_code": "infraestrutura_servidores",
                              "description": "[FICTÍCIO] Categoria sem avaliação implementada.", "area": "TI",
                              "owner": "Responsável fictício", "criticality": "Média"})
    if erp_risk:
        treatment.create_action(ctx, erp_risk["id"], {
            "action": "Estabelecer rotina trimestral de teste de restauração com critérios de sucesso.",
            "owner": "Responsável fictício", "priority": "Alta", "status": "Em andamento",
            "due_date": (date.today() - timedelta(days=10)).isoformat(),
            "expected_evidence": "Relatório do teste de restauração",
            "notes": "Ação fictícia (exemplo de ação vencida)."}, control_code="RC-BK-09")
    return org_id


def attach_user(conn, org_id: int, user_id: int, role: str = "admin") -> None:
    """Concede acesso de um usuário existente à organização de demonstração."""
    accounts = AccountRepository(conn)
    with conn:
        if accounts.get_membership(org_id, user_id):
            accounts.set_member_role(org_id, user_id, role)
        else:
            accounts.add_member(org_id, user_id, role)


def reset_demo(conn) -> int:
    """Restaura a demonstração: arquiva a organização atual (com tudo que os visitantes fizeram) e cria uma nova.

    Nada é apagado: a antiga fica com situação "Arquivada" e novo identificador, inacessível pela interface.
    Quem tinha acesso à demonstração (por exemplo, um administrador) o recebe de volta na nova.
    """
    repo = AccountRepository(conn)
    old = repo.get_organization_by_slug(DEMO_SLUG)
    members = []
    if old:
        members = [(m["user_id"], m["role_code"]) for m in repo.list_members(old["id"])]
        stamp = to_iso(utcnow()).replace("-", "").replace(":", "").lower()
        with conn:
            repo.archive_organization(old["id"], f"{DEMO_SLUG}-arq-{stamp}-{secrets.token_hex(2)}", to_iso(utcnow()))
    new_id = load_demo(conn)
    for user_id, role in members:
        attach_user(conn, new_id, user_id, role)
    return new_id
