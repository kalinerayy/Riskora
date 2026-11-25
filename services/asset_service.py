"""Gestão de ativos: cadastro, edição, desativação, busca. Sempre dentro da organização do contexto."""
from __future__ import annotations

from database.repositories.assessments import AssessmentRepository
from database.repositories.assets import AssetRepository
from models.asset import (ASSET_STATUSES, AVAILABILITY_REQUIREMENTS, CLASSIFICATIONS, CRITICALITY_LEVELS,
                          IMPACT_FIELDS)
from models.user import Context
from modules.registry import get_module_for_category
from services.audit_service import AuditService
from services.authorization_service import require
from services.clock import to_iso, utcnow
from services.errors import NotFoundError, RiskoraError
from services.validation import clean_scale, clean_text, require_choice


class AssetService:
    def __init__(self, conn):
        self.conn = conn
        self.repo = AssetRepository(conn)
        self.assessments = AssessmentRepository(conn)
        self.audit = AuditService(conn)

    def list_categories(self) -> list[dict]:
        """Categorias disponíveis, com a indicação de haver (ou não) avaliação implementada."""
        out = []
        for c in self.repo.list_categories():
            c["has_assessment"] = get_module_for_category(c["code"]) is not None
            out.append(c)
        return out

    def _clean(self, data: dict) -> dict:
        out = {
            "name": clean_text(data.get("name"), "Nome do ativo", 200, required=True),
            "description": clean_text(data.get("description"), "Descrição", 2000),
            "area": clean_text(data.get("area"), "Área responsável", 200),
            "owner": clean_text(data.get("owner"), "Responsável pelo ativo", 200),
            "environment": clean_text(data.get("environment"), "Localização ou ambiente", 200),
            "criticality": require_choice(data.get("criticality", "Desconhecida"), CRITICALITY_LEVELS, "Criticidade"),
            "information_classification": require_choice(data.get("information_classification", "Não informada"),
                                                         CLASSIFICATIONS, "Classificação da informação"),
            "information_type": clean_text(data.get("information_type"), "Tipo de informação", 500),
            "availability_requirement": require_choice(data.get("availability_requirement", "Não informado"),
                                                       AVAILABILITY_REQUIREMENTS, "Requisito de disponibilidade"),
            "interruption_consequences": clean_text(data.get("interruption_consequences"), "Consequências", 2000),
            "status": require_choice(data.get("status", "Ativo"), ASSET_STATUSES, "Status"),
            "impact_justification": clean_text(data.get("impact_justification"), "Justificativa do impacto", 2000),
        }
        for field in IMPACT_FIELDS:
            out[field] = clean_scale(data.get(field), field)
        return out

    def _category(self, code) -> dict:
        category = self.repo.get_category_by_code(code or "")
        if not category or not category["active"]:
            raise RiskoraError("Categoria de ativo inválida.")
        return category

    def create_asset(self, ctx: Context, data: dict) -> int:
        require(ctx, "asset:write")
        clean = self._clean(data)
        category = self._category(data.get("category_code"))
        code = clean_text(data.get("asset_code"), "Identificador", 40) or self.repo.next_asset_code(ctx.org_id)
        if self.repo.asset_code_exists(ctx.org_id, code):
            raise RiskoraError("Já existe um ativo com este identificador.")
        with self.conn:
            asset_id = self.repo.create_asset(ctx.org_id, category["id"], code, clean)
            self.audit.log_ctx(ctx, "asset_created", "asset", asset_id, code)
        return asset_id

    def update_asset(self, ctx: Context, asset_id: int, data: dict) -> None:
        require(ctx, "asset:write")
        current = self.get_asset(ctx, asset_id)
        clean = self._clean(data)
        category = self._category(data.get("category_code") or current["category_code"])
        if category["id"] != current["category_id"] and self.assessments.has_assessments(ctx.org_id, asset_id):
            raise RiskoraError("Não é possível trocar a categoria de um ativo que já possui avaliações.")
        with self.conn:
            self.repo.update_asset(ctx.org_id, asset_id, category["id"], clean, to_iso(utcnow()))
            self.audit.log_ctx(ctx, "asset_updated", "asset", asset_id)

    def set_status(self, ctx: Context, asset_id: int, status: str) -> None:
        """Desativação em vez de exclusão física: preserva o histórico de avaliações."""
        require(ctx, "asset:write")
        self.get_asset(ctx, asset_id)
        status = require_choice(status, ASSET_STATUSES, "Status")
        with self.conn:
            self.repo.set_status(ctx.org_id, asset_id, status, to_iso(utcnow()))
            self.audit.log_ctx(ctx, "asset_status_changed", "asset", asset_id, status)

    def get_asset(self, ctx: Context, asset_id: int) -> dict:
        require(ctx, "data:read")
        asset = self.repo.get_asset(ctx.org_id, asset_id) if isinstance(asset_id, int) else None
        if not asset:
            raise NotFoundError("Ativo não encontrado.")
        asset["has_assessment"] = get_module_for_category(asset["category_code"]) is not None
        return asset

    def list_assets(self, ctx: Context, search="", category_code=None, criticality=None, status=None, owner=None):
        require(ctx, "data:read")
        return self.repo.list_assets(ctx.org_id, clean_text(search, "Busca", 100), category_code or None,
                                     criticality or None, status or None, clean_text(owner, "Responsável", 200) or None)
