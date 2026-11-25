"""Categorias e ativos. Toda consulta de ativos exige organization_id."""
from __future__ import annotations

from database.repositories.base import BaseRepository, like_pattern
from models.asset import IMPACT_FIELDS

ASSET_FIELDS = ("name", "description", "area", "owner", "environment", "criticality", "information_classification",
                "information_type", "availability_requirement", "interruption_consequences", "status",
                "impact_justification") + IMPACT_FIELDS


class AssetRepository(BaseRepository):
    def list_categories(self, only_active=True):
        sql = "SELECT * FROM asset_categories" + (" WHERE active=1" if only_active else "") + " ORDER BY name"
        return self._all(sql)

    def get_category_by_code(self, code):
        return self._one("SELECT * FROM asset_categories WHERE code=?", (code,))

    def next_asset_code(self, org_id) -> str:
        rows = self._all("SELECT asset_code FROM assets WHERE organization_id=? AND asset_code LIKE 'AT-%'", (org_id,))
        highest = 0
        for r in rows:
            suffix = r["asset_code"][3:]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
        return f"AT-{highest + 1:04d}"

    def create_asset(self, org_id, category_id, asset_code, data: dict) -> int:
        cols = ",".join(ASSET_FIELDS)
        marks = ",".join("?" * len(ASSET_FIELDS))
        cur = self.conn.execute(
            f"INSERT INTO assets (organization_id, category_id, asset_code, {cols}) VALUES (?,?,?,{marks})",
            (org_id, category_id, asset_code, *[data[f] for f in ASSET_FIELDS]))
        return cur.lastrowid

    def update_asset(self, org_id, asset_id, category_id, data: dict, now) -> None:
        sets = ",".join(f"{f}=?" for f in ASSET_FIELDS)  # nomes de colunas vêm de constante, nunca da entrada
        self.conn.execute(f"UPDATE assets SET category_id=?, {sets}, updated_at=? WHERE id=? AND organization_id=?",
                          (category_id, *[data[f] for f in ASSET_FIELDS], now, asset_id, org_id))

    def set_status(self, org_id, asset_id, status, now) -> None:
        self.conn.execute("UPDATE assets SET status=?, updated_at=? WHERE id=? AND organization_id=?",
                          (status, now, asset_id, org_id))

    def get_asset(self, org_id, asset_id):
        return self._one(
            "SELECT a.*, c.code AS category_code, c.name AS category_name FROM assets a "
            "JOIN asset_categories c ON c.id=a.category_id WHERE a.id=? AND a.organization_id=?", (asset_id, org_id))

    def list_assets(self, org_id, search="", category_code=None, criticality=None, status=None, owner=None):
        sql = ("SELECT a.*, c.code AS category_code, c.name AS category_name FROM assets a "
               "JOIN asset_categories c ON c.id=a.category_id WHERE a.organization_id=?")
        params: list = [org_id]
        if search:
            sql += " AND (a.name LIKE ? ESCAPE '\\' OR a.asset_code LIKE ? ESCAPE '\\' OR a.owner LIKE ? ESCAPE '\\')"
            params += [like_pattern(search)] * 3
        if category_code:
            sql += " AND c.code=?"
            params.append(category_code)
        if criticality:
            sql += " AND a.criticality=?"
            params.append(criticality)
        if status:
            sql += " AND a.status=?"
            params.append(status)
        if owner:
            sql += " AND a.owner LIKE ? ESCAPE '\\'"
            params.append(like_pattern(owner))
        sql += " ORDER BY a.asset_code"
        return self._all(sql, params)

    def asset_code_exists(self, org_id, asset_code, exclude_id=None) -> bool:
        row = self._one("SELECT id FROM assets WHERE organization_id=? AND asset_code=?", (org_id, asset_code))
        return bool(row) and row["id"] != exclude_id
