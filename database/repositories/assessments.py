"""Modelos, avaliações, respostas, achados, riscos e catálogo de controles. Tudo escopado por organização."""
from __future__ import annotations

from typing import Iterable

from database.repositories.base import BaseRepository, placeholders


class AssessmentRepository(BaseRepository):
    # -- modelos / catálogo --------------------------------------------------------------
    def get_template(self, code, questionnaire_version, rules_version):
        return self._one("SELECT * FROM assessment_templates WHERE code=? AND questionnaire_version=? AND "
                         "rules_version=?", (code, questionnaire_version, rules_version))

    def get_template_by_id(self, template_id):
        return self._one("SELECT * FROM assessment_templates WHERE id=?", (template_id,))

    def question_texts(self, template_id) -> dict:
        rows = self._all("SELECT code, text FROM questions WHERE template_id=?", (template_id,))
        return {r["code"]: r["text"] for r in rows}

    def latest_concluded_for_asset(self, org_id, asset_id):
        return self._one("SELECT * FROM assessments WHERE organization_id=? AND asset_id=? AND status='Concluída' "
                         "ORDER BY id DESC LIMIT 1", (org_id, asset_id))

    def has_assessments(self, org_id, asset_id) -> bool:
        return bool(self._one("SELECT 1 AS x FROM assessments WHERE organization_id=? AND asset_id=? LIMIT 1",
                              (org_id, asset_id)))

    def get_rule_id(self, template_id, rule_code):
        row = self._one("SELECT id FROM diagnostic_rules WHERE template_id=? AND code=?", (template_id, rule_code))
        return row["id"] if row else None

    def get_control_id(self, code):
        row = self._one("SELECT id FROM controls WHERE code=?", (code,))
        return row["id"] if row else None

    def list_controls(self):
        controls = self._all("SELECT * FROM controls ORDER BY code")
        for c in controls:
            c["references"] = self.list_references(c["id"])
        return controls

    def list_references(self, control_id):
        return self._all("SELECT * FROM control_references WHERE control_id=? ORDER BY framework, ref_code",
                         (control_id,))

    # -- avaliações --------------------------------------------------------------------------
    def create_assessment(self, org_id, asset_id, template_id, user_id, assessor_name, methodology_version,
                          questionnaire_version, rules_version, parent_id=None) -> int:
        cur = self.conn.execute(
            "INSERT INTO assessments (organization_id, asset_id, template_id, assessor_user_id, assessor_name, "
            "methodology_version, questionnaire_version, rules_version, parent_assessment_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (org_id, asset_id, template_id, user_id, assessor_name, methodology_version, questionnaire_version,
             rules_version, parent_id))
        return cur.lastrowid

    def get_assessment(self, org_id, assessment_id):
        return self._one(
            "SELECT a.*, s.name AS asset_name, s.asset_code, t.code AS template_code FROM assessments a "
            "JOIN assets s ON s.id=a.asset_id JOIN assessment_templates t ON t.id=a.template_id "
            "WHERE a.id=? AND a.organization_id=?", (assessment_id, org_id))

    def list_assessments(self, org_id, asset_id=None):
        sql = ("SELECT a.*, s.name AS asset_name, s.asset_code FROM assessments a JOIN assets s ON s.id=a.asset_id "
               "WHERE a.organization_id=?")
        params: list = [org_id]
        if asset_id is not None:
            sql += " AND a.asset_id=?"
            params.append(asset_id)
        return self._all(sql + " ORDER BY a.id DESC", params)

    def set_status(self, org_id, assessment_id, status, completed_at, now) -> None:
        self.conn.execute("UPDATE assessments SET status=?, completed_at=?, updated_at=? WHERE id=? AND organization_id=?",
                          (status, completed_at, now, assessment_id, org_id))

    def latest_concluded_ids(self, org_id) -> list[int]:
        """Avaliação concluída mais recente de cada ativo (as anteriores continuam consultáveis no histórico)."""
        rows = self._all(
            "SELECT a.id FROM assessments a WHERE a.organization_id=? AND a.status='Concluída' AND a.id = ("
            "SELECT MAX(b.id) FROM assessments b WHERE b.organization_id=a.organization_id AND b.asset_id=a.asset_id "
            "AND b.status='Concluída')", (org_id,))
        return [r["id"] for r in rows]

    def list_concluded(self, org_id):
        return self._all(
            "SELECT a.*, s.name AS asset_name, s.asset_code, c.code AS category_code, c.name AS category_name "
            "FROM assessments a JOIN assets s ON s.id=a.asset_id JOIN asset_categories c ON c.id=s.category_id "
            "WHERE a.organization_id=? AND a.status='Concluída' ORDER BY a.completed_at", (org_id,))

    def list_drafts(self, org_id):
        return self._all("SELECT a.*, s.name AS asset_name FROM assessments a JOIN assets s ON s.id=a.asset_id "
                         "WHERE a.organization_id=? AND a.status='Rascunho'", (org_id,))

    # -- respostas -------------------------------------------------------------------------------
    def upsert_answer(self, org_id, assessment_id, question_code, value, justification, evidence_ref, user_id) -> None:
        self.conn.execute(
            "INSERT INTO answers (organization_id, assessment_id, question_code, value, justification, evidence_ref) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(assessment_id, question_code) DO UPDATE SET value=excluded.value, "
            "justification=excluded.justification, evidence_ref=excluded.evidence_ref, "
            "answered_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')",
            (org_id, assessment_id, question_code, value, justification, evidence_ref))
        self.conn.execute("DELETE FROM evidence_records WHERE assessment_id=? AND question_code=? AND organization_id=?",
                          (assessment_id, question_code, org_id))
        if evidence_ref:
            self.conn.execute(
                "INSERT INTO evidence_records (organization_id, assessment_id, question_code, reference, created_by) "
                "VALUES (?,?,?,?,?)", (org_id, assessment_id, question_code, evidence_ref, user_id))

    def list_answers(self, org_id, assessment_id):
        return self._all("SELECT * FROM answers WHERE assessment_id=? AND organization_id=? ORDER BY question_code",
                         (assessment_id, org_id))

    # -- resultados ----------------------------------------------------------------------------------
    def delete_results(self, org_id, assessment_id) -> None:
        sub = "SELECT id FROM risks WHERE assessment_id=? AND organization_id=?"
        self.conn.execute(f"DELETE FROM risk_control_mappings WHERE risk_id IN ({sub})", (assessment_id, org_id))
        self.conn.execute(f"DELETE FROM risk_assessments WHERE risk_id IN ({sub})", (assessment_id, org_id))
        self.conn.execute("DELETE FROM risks WHERE assessment_id=? AND organization_id=?", (assessment_id, org_id))
        self.conn.execute("DELETE FROM findings WHERE assessment_id=? AND organization_id=?", (assessment_id, org_id))

    def create_finding(self, org_id, assessment_id, rule_id, rule_code, title, basis, evidence_status, triggered_json,
                       weakness, evidence_description, limitations) -> int:
        cur = self.conn.execute(
            "INSERT INTO findings (organization_id, assessment_id, rule_id, rule_code, title, basis, evidence_status, "
            "triggered_by, weakness, evidence_description, limitations) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (org_id, assessment_id, rule_id, rule_code, title, basis, evidence_status, triggered_json, weakness,
             evidence_description, limitations))
        return cur.lastrowid

    def create_risk(self, org_id, assessment_id, finding_id, title, scenario, consequences) -> int:
        cur = self.conn.execute(
            "INSERT INTO risks (organization_id, assessment_id, finding_id, title, scenario, consequences) "
            "VALUES (?,?,?,?,?,?)", (org_id, assessment_id, finding_id, title, scenario, consequences))
        return cur.lastrowid

    def create_risk_assessment(self, org_id, risk_id, kind, probability, impact, score, level, status,
                               probability_justification, impact_justification, notes, methodology_version,
                               user_id) -> int:
        cur = self.conn.execute(
            "INSERT INTO risk_assessments (organization_id, risk_id, kind, probability, impact, score, level, status, "
            "probability_justification, impact_justification, notes, methodology_version, assessed_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (org_id, risk_id, kind, probability, impact, score, level, status, probability_justification,
             impact_justification, notes, methodology_version, user_id))
        return cur.lastrowid

    def map_risk_control(self, org_id, risk_id, control_id) -> None:
        self.conn.execute("INSERT OR IGNORE INTO risk_control_mappings (organization_id, risk_id, control_id) "
                          "VALUES (?,?,?)", (org_id, risk_id, control_id))

    def list_findings(self, org_id, assessment_id):
        return self._all("SELECT * FROM findings WHERE assessment_id=? AND organization_id=? ORDER BY rule_code",
                         (assessment_id, org_id))

    def list_risks(self, org_id, assessment_id):
        return self._all(
            "SELECT r.*, f.rule_code, f.basis, f.evidence_status, f.triggered_by, f.weakness, "
            "f.evidence_description, f.limitations FROM risks r JOIN findings f ON f.id=r.finding_id "
            "WHERE r.assessment_id=? AND r.organization_id=? ORDER BY f.rule_code", (assessment_id, org_id))

    def get_risk(self, org_id, risk_id):
        return self._one(
            "SELECT r.*, a.status AS assessment_status, a.asset_id FROM risks r JOIN assessments a ON a.id=r.assessment_id "
            "WHERE r.id=? AND r.organization_id=?", (risk_id, org_id))

    def latest_risk_assessment(self, org_id, risk_id, kind):
        return self._one("SELECT * FROM risk_assessments WHERE risk_id=? AND organization_id=? AND kind=? "
                         "ORDER BY id DESC LIMIT 1", (risk_id, org_id, kind))

    def list_risk_assessments(self, org_id, risk_id):
        return self._all("SELECT * FROM risk_assessments WHERE risk_id=? AND organization_id=? ORDER BY id",
                         (risk_id, org_id))

    def latest_by_kind(self, org_id, kind, assessment_ids: Iterable[int]):
        ids = list(assessment_ids)
        if not ids:
            return []
        return self._all(
            "SELECT ra.*, r.assessment_id, r.title AS risk_title FROM risk_assessments ra "
            "JOIN risks r ON r.id=ra.risk_id "
            f"WHERE ra.organization_id=? AND ra.kind=? AND r.assessment_id IN ({placeholders(len(ids))}) AND ra.id = ("
            "SELECT MAX(x.id) FROM risk_assessments x WHERE x.risk_id=ra.risk_id AND x.kind=ra.kind)",
            (org_id, kind, *ids))

    def controls_for_risk(self, org_id, risk_id):
        controls = self._all(
            "SELECT c.* FROM controls c JOIN risk_control_mappings m ON m.control_id=c.id "
            "WHERE m.risk_id=? AND m.organization_id=? ORDER BY m.id", (risk_id, org_id))
        for c in controls:
            c["references"] = self.list_references(c["id"])
        return controls

    def list_evidence_for_assessment(self, org_id, assessment_id):
        return self._all("SELECT * FROM evidence_records WHERE assessment_id=? AND organization_id=? ORDER BY id",
                         (assessment_id, org_id))
