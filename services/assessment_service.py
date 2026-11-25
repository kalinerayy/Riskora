"""Avaliações: respostas, processamento (diagnóstico + risco) e consulta de resultados.

Ciclo de vida:
- Rascunho: respostas editáveis; processar substitui os resultados derivados do próprio rascunho.
- Concluída: imutável (também protegida por gatilhos no banco). Revisar = criar uma NOVA versão (cópia).
"""
from __future__ import annotations

import json

from config.risk_methodology import ANSWER_OPTIONS, IMPACT_DIMENSIONS, METHODOLOGY_VERSION
from database.repositories.assessments import AssessmentRepository
from database.repositories.assets import AssetRepository
from database.repositories.treatment import TreatmentRepository
from models.assessment import Answer, AssessmentModule, Completeness
from models.user import Context
from modules.registry import all_controls, get_module_by_versions, get_module_for_category
from services.audit_service import AuditService
from services.authorization_service import require
from services.clock import to_iso, utcnow
from services.diagnostic_engine import assessment_completeness, evaluate_all
from services.errors import NotFoundError, RiskoraError
from services.privacy import person_label
from services.recommendation_engine import controls_for_rule, explain_finding
from services.risk_engine import calculate_risk, consolidate_impact, probability_from_basis
from services.validation import clean_text


class AssessmentService:
    def __init__(self, conn):
        self.conn = conn
        self.repo = AssessmentRepository(conn)
        self.assets = AssetRepository(conn)
        self.treatment = TreatmentRepository(conn)
        self.audit = AuditService(conn)

    # -- acesso interno (sem permissão): usado por serviços de leitura já autorizados ----------
    def _get(self, org_id: int, assessment_id) -> dict:
        row = self.repo.get_assessment(org_id, assessment_id) if isinstance(assessment_id, int) else None
        if not row:
            raise NotFoundError("Avaliação não encontrada.")
        return row

    def _module(self, assessment: dict) -> AssessmentModule:
        module = get_module_by_versions(assessment["template_code"], assessment["questionnaire_version"],
                                        assessment["rules_version"])
        if module is None:
            raise RiskoraError("Esta avaliação usa uma versão de questionário que não está mais disponível no código.")
        return module

    def completeness_internal(self, org_id: int, assessment_id: int) -> Completeness:
        assessment = self._get(org_id, assessment_id)
        return assessment_completeness(self._module(assessment).questions, self._answers(org_id, assessment_id))

    def _answers(self, org_id, assessment_id) -> dict[str, Answer]:
        return {r["question_code"]: Answer(r["question_code"], r["value"], r["justification"], r["evidence_ref"])
                for r in self.repo.list_answers(org_id, assessment_id)}

    # -- criação -----------------------------------------------------------------------------
    def create_assessment(self, ctx: Context, asset_id: int) -> int:
        require(ctx, "assessment:run")
        asset = self.assets.get_asset(ctx.org_id, asset_id) if isinstance(asset_id, int) else None
        if not asset:
            raise NotFoundError("Ativo não encontrado.")
        if asset["status"] == "Desativado":
            raise RiskoraError("Ativo desativado não pode ser avaliado.")
        module = get_module_for_category(asset["category_code"])
        if module is None:
            raise RiskoraError("A avaliação ainda não está disponível para esta categoria de ativo.")
        template = self.repo.get_template(module.code, module.questionnaire_version, module.rules_version)
        if not template:
            raise RiskoraError("Modelo de avaliação não carregado.")
        with self.conn:
            new_id = self.repo.create_assessment(ctx.org_id, asset_id, template["id"], ctx.user_id,
                                                 ctx.full_name or ctx.email, METHODOLOGY_VERSION,
                                                 module.questionnaire_version, module.rules_version)
            self.audit.log_ctx(ctx, "assessment_started", "assessment", new_id)
        return new_id

    def clone_assessment(self, ctx: Context, assessment_id: int) -> int:
        """Nova versão (rascunho) com as mesmas respostas; a original permanece intacta."""
        require(ctx, "assessment:run")
        old = self._get(ctx.org_id, assessment_id)
        asset = self.assets.get_asset(ctx.org_id, old["asset_id"])
        if asset["status"] == "Desativado":
            raise RiskoraError("Ativo desativado não pode ser avaliado.")
        module = get_module_for_category(asset["category_code"])
        if module is None:
            raise RiskoraError("A avaliação ainda não está disponível para esta categoria de ativo.")
        template = self.repo.get_template(module.code, module.questionnaire_version, module.rules_version)
        valid_codes = {q.code for q in module.questions}
        with self.conn:
            new_id = self.repo.create_assessment(ctx.org_id, old["asset_id"], template["id"], ctx.user_id,
                                                 ctx.full_name or ctx.email, METHODOLOGY_VERSION,
                                                 module.questionnaire_version, module.rules_version, assessment_id)
            for a in self.repo.list_answers(ctx.org_id, assessment_id):
                if a["question_code"] in valid_codes:
                    self.repo.upsert_answer(ctx.org_id, new_id, a["question_code"], a["value"], a["justification"],
                                            a["evidence_ref"], ctx.user_id)
            self.audit.log_ctx(ctx, "assessment_cloned", "assessment", new_id, f"origem={assessment_id}")
        return new_id

    # -- respostas -----------------------------------------------------------------------------
    def _draft(self, ctx: Context, assessment_id: int) -> dict:
        assessment = self._get(ctx.org_id, assessment_id)
        if assessment["status"] != "Rascunho":
            raise RiskoraError("Avaliação concluída não pode ser alterada. Crie uma nova versão.")
        return assessment

    def save_answer(self, ctx: Context, assessment_id: int, question_code: str, value: str,
                    justification="", evidence_ref="") -> None:
        require(ctx, "assessment:run")
        assessment = self._draft(ctx, assessment_id)
        module = self._module(assessment)
        if question_code not in {q.code for q in module.questions}:
            raise RiskoraError("Pergunta inexistente.")
        if value not in ANSWER_OPTIONS:
            raise RiskoraError("Resposta inválida.")
        justification = clean_text(justification, "Observações", 2000)
        evidence_ref = clean_text(evidence_ref, "Referência de evidência", 500)
        if value == "nao_se_aplica" and not justification:
            raise RiskoraError("'Não se aplica' exige justificativa nas observações.")
        with self.conn:
            self.repo.upsert_answer(ctx.org_id, assessment_id, question_code, value, justification, evidence_ref,
                                    ctx.user_id)

    def get_answers(self, ctx: Context, assessment_id: int) -> dict[str, Answer]:
        require(ctx, "data:read")
        self._get(ctx.org_id, assessment_id)
        return self._answers(ctx.org_id, assessment_id)

    @staticmethod
    def _masked(ctx: Context, row: dict) -> dict:
        """Esconde o nome do avaliador quando quem consulta é visitante (privacidade de quem faz login)."""
        return {**row, "assessor_name": person_label(ctx, row["assessor_name"])}

    def get_assessment(self, ctx: Context, assessment_id: int) -> dict:
        require(ctx, "data:read")
        return self._masked(ctx, self._get(ctx.org_id, assessment_id))

    def get_module(self, ctx: Context, assessment_id: int) -> AssessmentModule:
        require(ctx, "data:read")
        return self._module(self._get(ctx.org_id, assessment_id))

    def completeness(self, ctx: Context, assessment_id: int) -> Completeness:
        require(ctx, "data:read")
        return self.completeness_internal(ctx.org_id, assessment_id)

    def list_assessments(self, ctx: Context, asset_id: int | None = None) -> list[dict]:
        require(ctx, "data:read")
        return [self._masked(ctx, a) for a in self.repo.list_assessments(ctx.org_id, asset_id)]

    # -- processamento --------------------------------------------------------------------------
    def process_assessment(self, ctx: Context, assessment_id: int, finalize: bool = False) -> dict:
        require(ctx, "assessment:run")
        assessment = self._draft(ctx, assessment_id)
        module = self._module(assessment)
        answers = self._answers(ctx.org_id, assessment_id)
        findings = evaluate_all(module.rules, module.questions, answers)
        asset = self.assets.get_asset(ctx.org_id, assessment["asset_id"])
        dims = {d: asset[f"impact_{d}"] for d in IMPACT_DIMENSIONS}
        rules_by_code = {r.code: r for r in module.rules}
        controls_by_code = {c.code: c for c in all_controls()}
        completeness = assessment_completeness(module.questions, answers)
        now = to_iso(utcnow())
        with self.conn:
            self.repo.delete_results(ctx.org_id, assessment_id)
            for f in findings:
                rule = rules_by_code[f.rule_code]
                rule_id = self.repo.get_rule_id(assessment["template_id"], rule.code)
                finding_id = self.repo.create_finding(
                    ctx.org_id, assessment_id, rule_id, rule.code, rule.title, f.basis, f.evidence_status,
                    json.dumps(f.triggered_by), rule.weakness, rule.evidence_description, rule.limitations)
                risk_id = self.repo.create_risk(ctx.org_id, assessment_id, finding_id, rule.title, rule.risk_scenario,
                                                rule.consequences)
                impact = consolidate_impact(dims, rule.impact_dimensions)
                current_p, current_text = probability_from_basis(f.basis)
                notes = []
                if impact.value is not None and impact.missing:
                    notes.append("Impacto parcial: há dimensões relevantes não informadas.")
                if impact.value is None:
                    notes.append("Impactos do ativo não informados: classificação não calculada.")
                if f.basis == "knowledge_gap":
                    notes.append("Probabilidade provisória (lacuna de conhecimento).")
                inherent = calculate_risk(rule.inherent_probability, impact.value)
                current = calculate_risk(current_p, impact.value)
                impact_text = f"{rule.impact_criteria} {impact.justification}"
                self.repo.create_risk_assessment(
                    ctx.org_id, risk_id, "inherent", inherent.probability, inherent.impact, inherent.score,
                    inherent.level, inherent.status,
                    f"Cenário considerado sem controles existentes (probabilidade inerente padrão "
                    f"{rule.inherent_probability} nesta metodologia). {rule.probability_criteria}",
                    impact_text, " ".join(notes), METHODOLOGY_VERSION, ctx.user_id)
                self.repo.create_risk_assessment(
                    ctx.org_id, risk_id, "current", current.probability, current.impact, current.score, current.level,
                    current.status, f"{current_text} {rule.probability_criteria}", impact_text, " ".join(notes),
                    METHODOLOGY_VERSION, ctx.user_id)
                for control in controls_for_rule(rule, controls_by_code):
                    control_id = self.repo.get_control_id(control.code)
                    if control_id:
                        self.repo.map_risk_control(ctx.org_id, risk_id, control_id)
            if finalize:
                self.repo.set_status(ctx.org_id, assessment_id, "Concluída", now, now)
                self.audit.log_ctx(ctx, "assessment_finalized", "assessment", assessment_id,
                                   f"achados={len(findings)}")
        return {"findings": len(findings), "completeness": completeness, "finalized": finalize}

    def finalize_assessment(self, ctx: Context, assessment_id: int) -> dict:
        return self.process_assessment(ctx, assessment_id, finalize=True)

    # -- consulta de resultados ------------------------------------------------------------------
    def get_results(self, ctx: Context, assessment_id: int) -> list[dict]:
        require(ctx, "data:read")
        assessment = self._get(ctx.org_id, assessment_id)
        org = ctx.org_id
        answers = {a["question_code"]: a for a in self.repo.list_answers(org, assessment_id)}
        texts = self.repo.question_texts(assessment["template_id"])
        results = []
        for r in self.repo.list_risks(org, assessment_id):
            pairs = [tuple(p) for p in json.loads(r["triggered_by"])]
            triggered = []
            for code, value in pairs:
                a = answers.get(code, {})
                triggered.append({"code": code, "question": texts.get(code, code), "value": value,
                                  "value_label": ANSWER_OPTIONS.get(value, value),
                                  "justification": a.get("justification", ""), "evidence_ref": a.get("evidence_ref", "")})
            current = self.repo.latest_risk_assessment(org, r["id"], "current")
            actions = self.treatment.list_actions_for_risk(org, r["id"])
            results.append({
                **r, "triggered": triggered, "controls": self.repo.controls_for_risk(org, r["id"]),
                "inherent": self.repo.latest_risk_assessment(org, r["id"], "inherent"), "current": current,
                "residual": self.repo.latest_risk_assessment(org, r["id"], "residual"),
                "actions": actions,
                "explanation": explain_finding(r["title"], r["basis"], r["evidence_status"], pairs, current["level"],
                                               current["score"]),
            })
        return results

    def list_controls(self, ctx: Context) -> list[dict]:
        """Catálogo central de controles com suas referências (leitura)."""
        require(ctx, "data:read")
        return self.repo.list_controls()

    def asset_summary(self, ctx: Context, asset_id: int) -> dict:
        """Resumo para a aba Visão Geral do ativo: última avaliação concluída e contagem de riscos por nível."""
        require(ctx, "data:read")
        latest = self.repo.latest_concluded_for_asset(ctx.org_id, asset_id)
        drafts = [a for a in self.repo.list_assessments(ctx.org_id, asset_id) if a["status"] == "Rascunho"]
        counts: dict[str, int] = {}
        if latest:
            for ra in self.repo.latest_by_kind(ctx.org_id, "current", [latest["id"]]):
                counts[ra["level"]] = counts.get(ra["level"], 0) + 1
        return {"latest": latest, "drafts": drafts, "level_counts": counts}
