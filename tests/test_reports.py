import pytest

from services.demo_data import DEMO_SLUG, attach_user, load_demo
from services.errors import PermissionDenied
from services.report_service import REPORT_KINDS, ReportFilters, ReportService, _safe_cell, to_csv
from tests.helpers import ctx_for, finalized, make_org, new_db
from database.repositories.accounts import AccountRepository


def _demo():
    conn = new_db()
    org = load_demo(conn)
    return conn, org, ctx_for(org, "admin"), ReportService(conn)


def test_demo_e_idempotente_separada_e_marcada_como_ficticia():
    conn, org, ctx, rs = _demo()
    assert load_demo(conn) == org
    row = conn.execute("SELECT * FROM organizations WHERE id=?", (org,)).fetchone()
    assert row["is_demo"] == 1 and row["slug"] == DEMO_SLUG and "FICTÍCIOS" in row["business_description"]
    real = make_org(conn, "empresa-real", "Empresa Real")
    d = rs.compute_dashboard(ctx_for(real, "admin"))  # a demonstração não vaza para outra organização
    assert d["assets_total"] == 0 and d["risks_total"] == 0 and d["findings_total"] == 0


def test_demo_ilustra_os_cenarios_pedidos():
    conn, org, ctx, rs = _demo()
    rows = rs.build_report(ctx, "geral").rows
    by_asset = {}
    for r in rows:
        by_asset.setdefault(r["ativo"], set()).add(r["regra"])
    assert "BK-001" in by_asset["Backup do Servidor ERP (fictício)"]            # backup sem teste de restauração
    assert "BK-004" in by_asset["Backup do Sistema de Faturamento (fictício)"]  # cobertura parcial
    assert "BK-002" in by_asset["Backup do Servidor de Arquivos (fictício)"]    # isolamento sem evidência
    assert "Backup do Banco de Dados de RH (fictício)" not in by_asset          # monitoramento documentado
    assert "BK-005" in by_asset["Backup do Portal de Clientes (fictício)"]      # acesso parcial


def test_indicadores_do_dashboard_sao_consistentes_com_o_banco():
    conn, org, ctx, rs = _demo()
    d = rs.compute_dashboard(ctx)
    assert d["assets_total"] == 6 and d["assets_assessed"] == 5 and d["assessments_pending"] == 0
    assert d["risks_total"] == d["findings_total"] == sum(d["distribution"].values()) == 9
    assert sum(d["matrices"]["current"].values()) == d["risks_total"] and d["matrices"]["residual"] == {}
    assert d["actions_pending"] == 1 and d["actions_overdue"] == 1 and d["actions_done"] == 0
    assert d["needs_treatment"] == d["distribution"]["Alto"] + d["distribution"]["Crítico"]
    assert sum(d["risks_by_category"].values()) == 9 and d["evolution"][0]["avaliacoes_concluidas"] == 5
    assert d["controls_evaluated"] == 11 and d["controls_deficient"] >= 1
    assert d["insufficient_evidence"] == 9  # nenhuma fragilidade da demonstração tem evidência referenciada


def test_dashboard_vazio_nao_inventa_numeros():
    conn = new_db()
    ctx = ctx_for(make_org(conn), "admin")
    d = ReportService(conn).compute_dashboard(ctx)
    assert d["assets_total"] == 0 and d["risks_total"] == 0 and d["evolution"] == [] and d["recurring_weaknesses"] == []
    assert all(v == 0 for v in d["distribution"].values())


def test_avaliacao_incompleta_e_contada():
    conn = new_db()
    ctx = ctx_for(make_org(conn), "admin")
    finalized(conn, ctx, {"Q10": "nao"})  # só 1 pergunta respondida
    d = ReportService(conn).compute_dashboard(ctx)
    assert d["assessments_incomplete"] == 1 and d["assets_assessed"] == 1


def test_todos_os_tipos_de_relatorio_sao_gerados_com_texto_explicativo():
    conn, org, ctx, rs = _demo()
    for kind in REPORT_KINDS:
        report = rs.build_report(ctx, kind)
        assert report.narrative and report.title == REPORT_KINDS[kind]
        assert report.rows, kind
    with pytest.raises(ValueError):
        rs.build_report(ctx, "inventado")


def test_filtros_por_ativo_categoria_responsavel_criticidade_e_periodo():
    conn, org, ctx, rs = _demo()
    total = len(rs.build_report(ctx, "geral").rows)
    asset_id = conn.execute("SELECT id FROM assets WHERE name LIKE 'Backup do Servidor ERP%'").fetchone()[0]
    by_asset = rs.build_report(ctx, "geral", ReportFilters(asset_id=asset_id)).rows
    assert by_asset and {r["ativo_id"] for r in by_asset} == {asset_id} and len(by_asset) < total
    assert len(rs.build_report(ctx, "geral", ReportFilters(category_code="backup_recuperacao")).rows) == total
    assert rs.build_report(ctx, "geral", ReportFilters(category_code="nuvem")).rows == []
    assert len(rs.build_report(ctx, "geral", ReportFilters(owner="fictício")).rows) == total
    assert rs.build_report(ctx, "geral", ReportFilters(owner="inexistente")).rows == []
    crit = rs.build_report(ctx, "geral", ReportFilters(criticality="Crítico")).rows
    assert crit and all(r["nivel_atual"] == "Crítico" for r in crit)
    assert rs.build_report(ctx, "geral", ReportFilters(date_from="2999-01-01")).rows == []
    assert len(rs.build_report(ctx, "geral", ReportFilters(date_from="2000-01-01", date_to="2999-12-31")).rows) == total
    assert rs.build_report(ctx, "tratamento", ReportFilters(asset_id=asset_id)).rows
    assert rs.build_report(ctx, "tratamento", ReportFilters(owner="ninguém")).rows == []


def test_ativo_avaliacao_e_risco_estao_corretamente_associados():
    conn, org, ctx, rs = _demo()
    for r in rs.build_report(ctx, "geral").rows:
        row = conn.execute("SELECT a.asset_id, s.name FROM assessments a JOIN assets s ON s.id=a.asset_id WHERE a.id=?",
                           (r["avaliacao_id"],)).fetchone()
        assert (row[0], row[1]) == (r["ativo_id"], r["ativo"])


def test_csv_neutraliza_formulas_e_markdown_traz_avisos():
    assert _safe_cell("=1+1") == "'=1+1" and _safe_cell("@cmd") == "'@cmd" and _safe_cell("texto") == "texto"
    assert _safe_cell(5) == 5
    conn, org, ctx, rs = _demo()
    report = rs.build_report(ctx, "geral")
    csv_text = rs.csv_text(ctx, report)
    header = csv_text.splitlines()[0]
    assert header.startswith("avaliacao_id") and "_categoria_codigo" not in header and "BK-001" in csv_text
    assert to_csv([]) == ""
    md = rs.markdown_text(ctx, report, "Empresa Fictícia")
    assert "Empresa Fictícia" in md and "respostas declaradas" in md
    asset_md = rs.asset_report_markdown(ctx, 1)
    assert "Limitações" in asset_md and "não equivale a vulnerabilidade técnica confirmada" in asset_md


def test_exportacao_exige_permissao_e_e_auditada_so_ao_baixar():
    conn, org, ctx, rs = _demo()
    report = rs.build_report(ctx, "geral")
    before = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='report_exported'").fetchone()[0]
    rs.csv_text(ctx, report)
    rs.markdown_text(ctx, report)
    assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='report_exported'").fetchone()[0] == before
    rs.log_export(ctx, "geral", "csv")
    assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='report_exported'").fetchone()[0] == before + 1
    class NoExport:  # contexto sem a permissão
        pass
    from models.user import Context
    limited = Context(1, "x@y.z", "X", org, "reader", frozenset({"data:read"}))
    with pytest.raises(PermissionDenied):
        rs.csv_text(limited, report)
    with pytest.raises(PermissionDenied):
        rs.log_export(limited, "geral", "csv")


def test_acesso_a_demonstracao_e_concedido_a_um_usuario_existente():
    from tests.helpers import make_auth, make_user
    conn = new_db()
    auth = make_auth(conn)
    base = make_org(conn)
    user_id = make_user(conn, base, "ana@test.com", "analyst", auth=auth)
    org = load_demo(conn, user_id)
    attach_user(conn, org, user_id, "reader")
    memberships = {m["organization_id"]: m["role_code"] for m in AccountRepository(conn).list_memberships_for_user(user_id)}
    assert memberships[org] == "reader" and memberships[base] == "analyst"


def test_recomendacoes_prioritarias_ordenadas_pela_pontuacao_e_com_acao_sugerida():
    conn, org, ctx, rs = _demo()
    recs = rs.priority_recommendations(ctx, limit=5)
    assert len(recs) == 5
    scores = [r["pontuacao"] or 0 for r in recs]
    assert scores == sorted(scores, reverse=True)
    assert recs[0]["nivel"] == "Crítico" and recs[0]["controle"] and recs[0]["acao"]
    assert rs.priority_recommendations(ctx, limit=2) == recs[:2]
    empty_ctx = ctx_for(make_org(conn, "vazia", "Vazia"), "admin")
    assert rs.priority_recommendations(empty_ctx) == []


def test_dashboard_informa_a_data_da_ultima_avaliacao_concluida():
    conn, org, ctx, rs = _demo()
    assert rs.compute_dashboard(ctx)["last_update"][:4].isdigit()
    assert rs.compute_dashboard(ctx_for(make_org(conn, "vazia", "Vazia"), "admin"))["last_update"] is None
