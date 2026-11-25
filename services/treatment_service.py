"""Plano de tratamento, validação de ações e reavaliação de risco (residual).

REGRA CENTRAL: concluir uma ação NÃO altera nenhuma pontuação. A redução só ocorre por reavaliação
explícita (risco residual), com justificativa documentada, feita por quem tem permissão de validação.
Ciclo de vida de uma ação: Planejada → Em execução → Concluída → Validada.
"""
from __future__ import annotations

from datetime import date

from config.risk_methodology import METHODOLOGY_VERSION
from database.repositories.assessments import AssessmentRepository
from database.repositories.treatment import TreatmentRepository
from models.treatment import ACTION_STATUSES, OPEN_STATUSES, PRIORITIES
from models.user import Context
from services.audit_service import AuditService
from services.authorization_service import require
from services.clock import to_iso, utcnow
from services.errors import NotFoundError, RiskoraError
from services.privacy import person_label
from services.risk_engine import calculate_risk
from services.validation import clean_date, clean_text, require_choice


def lifecycle(action: dict) -> str:
    if action["status"] == "Cancelado":
        return "Cancelada"
    if action.get("validated_at"):
        return "Validada"
    if action["status"] == "Concluído":
        return "Concluída"
    if action["status"] == "Não iniciado":
        return "Planejada"
    return "Em execução"


def is_overdue(action: dict, today: date | None = None) -> bool:
    if action["status"] not in OPEN_STATUSES or not action.get("due_date"):
        return False
    return date.fromisoformat(action["due_date"]) < (today or date.today())


class TreatmentService:
    def __init__(self, conn):
        self.conn = conn
        self.repo = TreatmentRepository(conn)
        self.assess = AssessmentRepository(conn)
        self.audit = AuditService(conn)

    def _risk(self, ctx: Context, risk_id) -> dict:
        risk = self.assess.get_risk(ctx.org_id, risk_id) if isinstance(risk_id, int) else None
        if not risk:
            raise NotFoundError("Risco não encontrado.")
        if risk["assessment_status"] != "Concluída":
            raise RiskoraError("Conclua a avaliação antes de registrar ações ou reavaliar riscos.")
        return risk

    def _action(self, ctx: Context, action_id) -> dict:
        action = self.repo.get_action(ctx.org_id, action_id) if isinstance(action_id, int) else None
        if not action:
            raise NotFoundError("Ação não encontrada.")
        return action

    @staticmethod
    def _clean(data: dict) -> dict:
        status = require_choice(data.get("status", "Não iniciado"), ACTION_STATUSES, "Status")
        out = {
            "action": clean_text(data.get("action"), "Ação recomendada", 2000, required=True),
            "owner": clean_text(data.get("owner"), "Responsável", 200),
            "priority": require_choice(data.get("priority", "Média"), PRIORITIES, "Prioridade"),
            "due_date": clean_date(data.get("due_date"), "Prazo"),
            "status": status,
            "expected_evidence": clean_text(data.get("expected_evidence"), "Evidência esperada", 1000),
            "notes": clean_text(data.get("notes"), "Observações", 2000),
            "completed_at": clean_date(data.get("completed_at"), "Data de conclusão"),
        }
        if status == "Concluído" and not out["completed_at"]:
            out["completed_at"] = date.today().isoformat()
        if status != "Concluído":
            out["completed_at"] = None
        return out

    def create_action(self, ctx: Context, risk_id: int, data: dict, control_code: str | None = None) -> int:
        require(ctx, "treatment:write")
        self._risk(ctx, risk_id)
        clean = self._clean(data)
        clean["risk_id"] = risk_id
        clean["control_id"] = None
        if control_code:
            control_id = self.assess.get_control_id(control_code)
            if control_id is None:
                raise RiskoraError("Controle inexistente.")
            if control_id not in [c["id"] for c in self.assess.controls_for_risk(ctx.org_id, risk_id)]:
                raise RiskoraError("O controle não está relacionado a este risco.")
            clean["control_id"] = control_id
        with self.conn:
            action_id = self.repo.create_action(ctx.org_id, clean, ctx.user_id)
            self.repo.add_event(ctx.org_id, action_id, ctx.user_id, "criada", clean["status"])
            self.audit.log_ctx(ctx, "action_created", "treatment_action", action_id)
        return action_id

    def update_action(self, ctx: Context, action_id: int, data: dict) -> None:
        require(ctx, "treatment:write")
        current = self._action(ctx, action_id)
        clean = self._clean(data)
        now = to_iso(utcnow())
        with self.conn:
            # Ação reaberta perde a validação ANTES do update (o banco só aceita validação em ação concluída).
            reopened = bool(current["validated_at"]) and clean["status"] != "Concluído"
            if reopened:
                self.repo.clear_validation(ctx.org_id, action_id, now)
            # Somente a ação é atualizada: nenhuma pontuação de risco é tocada aqui (por regra).
            self.repo.update_action(ctx.org_id, action_id, clean, now)
            if clean["status"] != current["status"]:
                self.repo.add_event(ctx.org_id, action_id, ctx.user_id, "status",
                                    f"{current['status']} → {clean['status']}")
            else:
                self.repo.add_event(ctx.org_id, action_id, ctx.user_id, "editada")
            if reopened:
                self.repo.add_event(ctx.org_id, action_id, ctx.user_id, "validação removida", "ação reaberta")
            self.audit.log_ctx(ctx, "action_updated", "treatment_action", action_id)

    def validate_action(self, ctx: Context, action_id: int, notes: str = "") -> None:
        require(ctx, "treatment:validate")
        action = self._action(ctx, action_id)
        if action["status"] != "Concluído":
            raise RiskoraError("Somente ações concluídas podem ser validadas.")
        notes = clean_text(notes, "Observações da validação", 2000)
        with self.conn:
            self.repo.set_validation(ctx.org_id, action_id, ctx.user_id, to_iso(utcnow()), notes)
            self.repo.add_event(ctx.org_id, action_id, ctx.user_id, "validada", notes[:200])
            self.audit.log_ctx(ctx, "action_validated", "treatment_action", action_id)

    def add_evidence(self, ctx: Context, action_id: int, description: str, reference: str) -> int:
        require(ctx, "treatment:write")
        self._action(ctx, action_id)
        reference = clean_text(reference, "Referência da evidência", 500, required=True)
        description = clean_text(description, "Descrição", 1000)
        with self.conn:
            evidence_id = self.repo.add_evidence(ctx.org_id, action_id, description, reference, ctx.user_id)
            self.repo.add_event(ctx.org_id, action_id, ctx.user_id, "evidência registrada", reference[:200])
        return evidence_id

    def action_details(self, ctx: Context, action_id: int) -> dict:
        require(ctx, "data:read")
        action = self._action(ctx, action_id)
        return {**action, "lifecycle": lifecycle(action), "overdue": is_overdue(action),
                "events": [{**e, "user_email": person_label(ctx, e["user_email"])}
                           for e in self.repo.list_events(ctx.org_id, action_id)],
                "evidence": self.repo.list_evidence_for_action(ctx.org_id, action_id)}

    def reassess_risk(self, ctx: Context, risk_id: int, probability, impact, probability_justification,
                      impact_justification, notes: str = "") -> int:
        """Registra um NOVO risco residual (histórico preservado). Exige justificativa documentada."""
        require(ctx, "treatment:validate")
        self._risk(ctx, risk_id)
        pj = clean_text(probability_justification, "Justificativa da probabilidade", 2000, required=True)
        ij = clean_text(impact_justification, "Justificativa do impacto", 2000, required=True)
        if len(pj) < 10 or len(ij) < 10:
            raise RiskoraError("Descreva as justificativas com mais detalhes (mínimo de 10 caracteres).")
        try:
            result = calculate_risk(probability, impact)  # valida a escala
        except ValueError as exc:
            raise RiskoraError(str(exc)) from exc
        with self.conn:
            new_id = self.assess.create_risk_assessment(
                ctx.org_id, risk_id, "residual", result.probability, result.impact, result.score, result.level,
                result.status, pj, ij, clean_text(notes, "Observações", 2000), METHODOLOGY_VERSION, ctx.user_id)
            self.audit.log_ctx(ctx, "risk_reassessed", "risk", risk_id, f"residual={result.level}")
        return new_id
