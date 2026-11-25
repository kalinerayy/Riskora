"""Carga idempotente de dados fixos: perfis, permissões, categorias, modelos de avaliação e controles."""
from __future__ import annotations

from models.asset import ASSET_CATEGORIES
from models.user import PERMISSIONS, ROLE_PERMISSIONS, ROLES
from modules.registry import MODULES, all_controls


def seed_all(conn) -> None:
    for code, name in ROLES.items():
        conn.execute("INSERT OR IGNORE INTO roles (code, name) VALUES (?, ?)", (code, name))
    for code, description in PERMISSIONS.items():
        conn.execute("INSERT OR IGNORE INTO permissions (code, description) VALUES (?, ?)", (code, description))
    for role, perms in ROLE_PERMISSIONS.items():
        for perm in perms:
            conn.execute("INSERT OR IGNORE INTO role_permissions (role_code, permission_code) VALUES (?, ?)", (role, perm))
    for code, name in ASSET_CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO asset_categories (code, name) VALUES (?, ?)", (code, name))
    for module in MODULES:
        _seed_module(conn, module)
    for control in all_controls():
        _seed_control(conn, control)


def _seed_module(conn, module) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO assessment_templates (code, name, category_code, questionnaire_version, rules_version) "
        "VALUES (?, ?, ?, ?, ?)",
        (module.code, module.name, module.category_code, module.questionnaire_version, module.rules_version))
    template_id = conn.execute(
        "SELECT id FROM assessment_templates WHERE code=? AND questionnaire_version=? AND rules_version=?",
        (module.code, module.questionnaire_version, module.rules_version)).fetchone()["id"]
    for position, q in enumerate(module.questions, start=1):
        conn.execute(
            "INSERT OR IGNORE INTO questions (template_id, code, domain_no, domain, text, purpose, parent_code, "
            "parent_answers, position) VALUES (?,?,?,?,?,?,?,?,?)",
            (template_id, q.code, q.domain_no, q.domain, q.text, q.purpose, q.parent_code,
             ",".join(q.parent_answers), position))
    for r in module.rules:
        conn.execute(
            "INSERT OR IGNORE INTO diagnostic_rules (template_id, code, title, weakness, risk_scenario, consequences, "
            "limitations) VALUES (?,?,?,?,?,?,?)",
            (template_id, r.code, r.title, r.weakness, r.risk_scenario, r.consequences, r.limitations))


def _seed_control(conn, c) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO controls (code, name, objective, description, control_type, addresses_rules, "
        "implementation_actions, expected_evidence) VALUES (?,?,?,?,?,?,?,?)",
        (c.code, c.name, c.objective, c.description, c.control_type, ",".join(c.addresses_rules),
         "\n".join(c.implementation_actions), "\n".join(c.expected_evidence)))
    control_id = conn.execute("SELECT id FROM controls WHERE code=?", (c.code,)).fetchone()["id"]
    for ref in c.references:
        conn.execute(
            "INSERT OR IGNORE INTO control_references (control_id, framework, ref_code, ref_title, source_consulted, "
            "validation_status) VALUES (?,?,?,?,?,?)",
            (control_id, ref.framework, ref.ref_code, ref.ref_title, ref.source_consulted, ref.validation_status))
