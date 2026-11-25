"""Ações de tratamento, histórico de eventos e evidências de execução. Escopado por organização."""
from __future__ import annotations

from typing import Iterable

from database.repositories.base import BaseRepository, placeholders


class TreatmentRepository(BaseRepository):
    def create_action(self, org_id, data: dict, created_by) -> int:
        cur = self.conn.execute(
            "INSERT INTO treatment_actions (organization_id, risk_id, control_id, action, owner, priority, due_date, "
            "status, expected_evidence, notes, completed_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (org_id, data["risk_id"], data.get("control_id"), data["action"], data["owner"], data["priority"],
             data.get("due_date"), data["status"], data["expected_evidence"], data["notes"], data.get("completed_at"),
             created_by))
        return cur.lastrowid

    def get_action(self, org_id, action_id):
        return self._one("SELECT * FROM treatment_actions WHERE id=? AND organization_id=?", (action_id, org_id))

    def update_action(self, org_id, action_id, data: dict, now) -> None:
        self.conn.execute(
            "UPDATE treatment_actions SET action=?, owner=?, priority=?, due_date=?, status=?, expected_evidence=?, "
            "notes=?, completed_at=?, updated_at=? WHERE id=? AND organization_id=?",
            (data["action"], data["owner"], data["priority"], data.get("due_date"), data["status"],
             data["expected_evidence"], data["notes"], data.get("completed_at"), now, action_id, org_id))

    def set_validation(self, org_id, action_id, user_id, now, notes) -> None:
        self.conn.execute(
            "UPDATE treatment_actions SET validated_by=?, validated_at=?, validation_notes=?, updated_at=? "
            "WHERE id=? AND organization_id=?", (user_id, now, notes, now, action_id, org_id))

    def clear_validation(self, org_id, action_id, now) -> None:
        self.conn.execute(
            "UPDATE treatment_actions SET validated_by=NULL, validated_at=NULL, validation_notes='', updated_at=? "
            "WHERE id=? AND organization_id=?", (now, action_id, org_id))

    def list_actions_for_risk(self, org_id, risk_id):
        return self._all("SELECT * FROM treatment_actions WHERE risk_id=? AND organization_id=? ORDER BY id",
                         (risk_id, org_id))

    def list_actions_for_assessments(self, org_id, assessment_ids: Iterable[int]):
        ids = list(assessment_ids)
        if not ids:
            return []
        return self._all(
            "SELECT t.*, r.title AS risk_title, r.assessment_id, s.id AS asset_id, s.name AS asset_name, "
            "c.code AS control_code FROM treatment_actions t JOIN risks r ON r.id=t.risk_id "
            "JOIN assessments a ON a.id=r.assessment_id JOIN assets s ON s.id=a.asset_id "
            "LEFT JOIN controls c ON c.id=t.control_id "
            f"WHERE t.organization_id=? AND r.assessment_id IN ({placeholders(len(ids))}) "
            "ORDER BY t.due_date IS NULL, t.due_date, t.id", (org_id, *ids))

    def add_event(self, org_id, action_id, user_id, event_type, detail="") -> int:
        cur = self.conn.execute(
            "INSERT INTO treatment_action_events (organization_id, action_id, user_id, event_type, detail) "
            "VALUES (?,?,?,?,?)", (org_id, action_id, user_id, event_type, detail[:500]))
        return cur.lastrowid

    def list_events(self, org_id, action_id):
        return self._all(
            "SELECT e.*, u.email AS user_email FROM treatment_action_events e LEFT JOIN users u ON u.id=e.user_id "
            "WHERE e.action_id=? AND e.organization_id=? ORDER BY e.id", (action_id, org_id))

    def add_evidence(self, org_id, action_id, description, reference, user_id) -> int:
        cur = self.conn.execute(
            "INSERT INTO evidence_records (organization_id, action_id, description, reference, created_by) "
            "VALUES (?,?,?,?,?)", (org_id, action_id, description, reference, user_id))
        return cur.lastrowid

    def list_evidence_for_action(self, org_id, action_id):
        return self._all("SELECT * FROM evidence_records WHERE action_id=? AND organization_id=? ORDER BY id",
                         (action_id, org_id))
