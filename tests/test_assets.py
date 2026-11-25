import pytest

from services.asset_service import AssetService
from services.assessment_service import AssessmentService
from services.errors import NotFoundError, RiskoraError
from tests.helpers import backup_asset, ctx_for, finalized, make_org, new_db


def _setup():
    conn = new_db()
    org = make_org(conn)
    return conn, org, ctx_for(org, "analyst"), AssetService(conn)


def test_cadastro_minimo_com_dados_desconhecidos_e_identificador_automatico():
    conn, org, ctx, svc = _setup()
    first = svc.create_asset(ctx, {"name": "Servidor X", "category_code": "infraestrutura_servidores"})
    second = svc.create_asset(ctx, {"name": "Servidor Y", "category_code": "infraestrutura_servidores"})
    a = svc.get_asset(ctx, first)
    assert a["asset_code"] == "AT-0001" and svc.get_asset(ctx, second)["asset_code"] == "AT-0002"
    assert a["criticality"] == "Desconhecida" and a["impact_availability"] is None and a["status"] == "Ativo"
    assert a["category_name"] == "Infraestrutura e servidores" and a["has_assessment"] is False


def test_todas_as_categorias_previstas_podem_ser_usadas():
    conn, org, ctx, svc = _setup()
    categories = svc.list_categories()
    assert len(categories) == 11
    with_assessment = [c["code"] for c in categories if c["has_assessment"]]
    assert with_assessment == ["backup_recuperacao"]  # só o módulo de backup está implementado
    for c in categories:
        svc.create_asset(ctx, {"name": f"Ativo {c['code']}", "category_code": c["code"]})


def test_identificador_unico_por_organizacao():
    conn, org, ctx, svc = _setup()
    svc.create_asset(ctx, {"name": "A", "category_code": "nuvem", "asset_code": "SRV-1"})
    with pytest.raises(RiskoraError):
        svc.create_asset(ctx, {"name": "B", "category_code": "nuvem", "asset_code": "SRV-1"})
    other_ctx = ctx_for(make_org(conn, "org-b", "Org B"), "analyst")
    svc.create_asset(other_ctx, {"name": "C", "category_code": "nuvem", "asset_code": "SRV-1"})  # outra org: pode


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("name", "x" * 201), ("category_code", "inventada"), ("criticality", "Muito"),
    ("information_classification", "Secreta"), ("status", "Quebrado"), ("impact_legal", 7), ("impact_financial", True),
    ("availability_requirement", "Sempre"),
])
def test_validacao_de_campos(field, value):
    conn, org, ctx, svc = _setup()
    data = {"name": "Ativo", "category_code": "nuvem", field: value}
    with pytest.raises(RiskoraError):
        svc.create_asset(ctx, data)


def test_edicao_e_consulta():
    conn, org, ctx, svc = _setup()
    asset_id = backup_asset(conn, ctx)
    svc.update_asset(ctx, asset_id, {"name": "Backup ERP v2", "category_code": "backup_recuperacao", "owner": "Marina",
                                    "criticality": "Crítica", "impact_availability": 5})
    a = svc.get_asset(ctx, asset_id)
    assert a["name"] == "Backup ERP v2" and a["owner"] == "Marina" and a["criticality"] == "Crítica"
    with pytest.raises(NotFoundError):
        svc.get_asset(ctx, 9999)
    with pytest.raises(NotFoundError):
        svc.get_asset(ctx, "1; DROP TABLE assets")


def test_categoria_nao_muda_depois_de_haver_avaliacoes():
    conn, org, ctx, svc = _setup()
    asset_id, _, _ = finalized(conn, ctx, {"Q10": "nao"})
    with pytest.raises(RiskoraError):
        svc.update_asset(ctx, asset_id, {"name": "Backup ERP", "category_code": "nuvem"})


def test_desativacao_preserva_historico_e_impede_nova_avaliacao():
    conn, org, ctx, svc = _setup()
    asset_id, aid, asvc = finalized(conn, ctx, {"Q10": "nao"})
    svc.set_status(ctx, asset_id, "Desativado")
    assert svc.get_asset(ctx, asset_id)["status"] == "Desativado"
    assert len(asvc.get_results(ctx, aid)) == 1  # histórico intacto
    with pytest.raises(RiskoraError):
        asvc.create_assessment(ctx, asset_id)
    with pytest.raises(RiskoraError):
        asvc.clone_assessment(ctx, aid)
    svc.set_status(ctx, asset_id, "Ativo")
    assert asvc.create_assessment(ctx, asset_id)


def test_busca_e_filtros_tratam_curingas_como_texto():
    conn, org, ctx, svc = _setup()
    backup_asset(conn, ctx, "Backup ERP", owner="Marina", criticality="Alta")
    backup_asset(conn, ctx, "Backup RH", owner="João", criticality="Baixa")
    svc.create_asset(ctx, {"name": "100%_seguro", "category_code": "nuvem"})
    assert len(svc.list_assets(ctx)) == 3
    assert [a["name"] for a in svc.list_assets(ctx, search="erp")] == ["Backup ERP"]
    assert [a["name"] for a in svc.list_assets(ctx, search="marina")] == ["Backup ERP"]
    assert len(svc.list_assets(ctx, category_code="backup_recuperacao")) == 2
    assert [a["name"] for a in svc.list_assets(ctx, criticality="Baixa")] == ["Backup RH"]
    assert [a["name"] for a in svc.list_assets(ctx, search="%")] == ["100%_seguro"]  # % não é curinga
    assert svc.list_assets(ctx, search="' OR 1=1 --") == []
    assert [a["name"] for a in svc.list_assets(ctx, owner="jo")] == ["Backup RH"]


def test_relacionamento_com_organizacao_e_categoria():
    conn, org, ctx, svc = _setup()
    asset_id = backup_asset(conn, ctx)
    row = conn.execute("SELECT a.organization_id, c.code FROM assets a JOIN asset_categories c ON c.id=a.category_id "
                       "WHERE a.id=?", (asset_id,)).fetchone()
    assert (row[0], row[1]) == (org, "backup_recuperacao")
