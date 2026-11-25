"""Área central de relatórios, com filtros e exportação (CSV e Markdown)."""
import streamlit as st

from models.asset import CRITICALITY_LEVELS
from services.asset_service import AssetService
from services.organization_service import OrganizationService
from services.report_service import LEVELS, REPORT_KINDS, ReportFilters, ReportService
from ui.components.widgets import can, page_header, table


def _iso(value):
    return value.isoformat() if value else None


def render(conn, ctx):
    page_header("Análise e exportação", "Relatórios", "CSV e Markdown")
    if not can(ctx, "report:export"):
        st.info("Seu perfil não permite gerar relatórios.")
        return
    rs, assets_svc = ReportService(conn), AssetService(conn)
    kind = st.selectbox("Relatório", list(REPORT_KINDS), format_func=lambda k: REPORT_KINDS[k])
    assets = assets_svc.list_assets(ctx)
    categories = assets_svc.list_categories()
    with st.expander("Filtros", expanded=False):
        c = st.columns(3)
        date_from = c[0].date_input("De (data de conclusão ou prazo)", value=None)
        date_to = c[1].date_input("Até", value=None)
        asset_id = c[2].selectbox("Ativo", [None] + [a["id"] for a in assets],
                                  format_func=lambda i: "Todos" if i is None else next(
                                      f"{a['asset_code']} - {a['name']}" for a in assets if a["id"] == i))
        c = st.columns(3)
        category = c[0].selectbox("Categoria", [None] + [x["code"] for x in categories],
                                  format_func=lambda x: "Todas" if x is None else next(
                                      y["name"] for y in categories if y["code"] == x))
        owner = c[1].text_input("Responsável pelo ativo (contém)", max_chars=200)
        level = c[2].selectbox("Criticidade do risco atual", [None] + list(LEVELS),
                               format_func=lambda x: "Todas" if x is None else x)
    report = rs.build_report(ctx, kind, ReportFilters(_iso(date_from), _iso(date_to), asset_id, category,
                                                      owner.strip() or None, level))
    st.subheader(report.title)
    st.write(report.narrative)
    table(report.rows)
    if report.rows:
        org_name = OrganizationService(conn).get_organization(ctx)["name"]
        c = st.columns(2)
        c[0].download_button("Baixar CSV", rs.csv_text(ctx, report).encode("utf-8-sig"), f"riskora_{kind}.csv",
                             "text/csv", on_click=lambda: rs.log_export(ctx, kind, "csv"))
        c[1].download_button("Baixar relatório (Markdown)", rs.markdown_text(ctx, report, org_name).encode("utf-8"),
                             f"riskora_{kind}.md", "text/markdown", on_click=lambda: rs.log_export(ctx, kind, "md"))
    st.caption("A exportação em PDF não está disponível nesta versão.")
