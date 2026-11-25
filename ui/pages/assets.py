"""Lista de ativos (busca, filtros, cadastro) e acesso à página individual do ativo."""
import streamlit as st

from models.asset import ASSET_STATUSES, CRITICALITY_LEVELS
from services.asset_service import AssetService
from ui.components.forms import asset_form
from ui.components.widgets import can, flash, page_header, run_action, show_flash, table
from ui.pages import asset_detail

def render(conn, ctx):
    svc = AssetService(conn)
    qp = st.query_params.get("ativo")
    if qp and str(qp).isdigit() and st.session_state.get("asset_id") != int(qp):
        st.session_state["asset_id"] = int(qp)
    if st.session_state.get("asset_id"):
        asset_detail.render(conn, ctx, st.session_state["asset_id"])
        return
    page_header("Gestão de ativos", "Ativos", "Busque, classifique e abra um ativo para analisá-lo")
    show_flash()
    categories = svc.list_categories()
    tab_list, tab_new = st.tabs(["Listagem", "Novo ativo"]) if can(ctx, "asset:write") else (st.container(), None)
    with tab_list:
        c = st.columns(4)
        search = c[0].text_input("Buscar (nome, identificador ou responsável)", max_chars=100)
        category = c[1].selectbox("Categoria", [None] + [x["code"] for x in categories],
                                  format_func=lambda x: "Todas" if x is None else next(y["name"] for y in categories if y["code"] == x))
        criticality = c[2].selectbox("Criticidade", [None] + list(CRITICALITY_LEVELS), format_func=lambda x: "Todas" if x is None else x)
        status = c[3].selectbox("Status", [None] + list(ASSET_STATUSES), format_func=lambda x: "Todos" if x is None else x)
        assets = svc.list_assets(ctx, search, category, criticality, status)
        if not assets:
            st.info("Nenhum ativo encontrado." if search or category or criticality or status else
                    "Nenhum ativo cadastrado ainda.")
        else:
            table([{"Identificador": a["asset_code"], "Nome": a["name"], "Categoria": a["category_name"],
                    "Criticidade": a["criticality"], "Responsável": a["owner"] or "-", "Status": a["status"],
                    "Avaliação disponível": "Sim" if svc.get_asset(ctx, a["id"])["has_assessment"] else "Ainda não"}
                   for a in assets])
            c = st.columns([3, 1])
            chosen = c[0].selectbox("Abrir ativo", [a["id"] for a in assets],
                                    format_func=lambda i: next(f"{a['asset_code']} - {a['name']}" for a in assets if a["id"] == i))
            c[1].markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)
            if c[1].button("Abrir", type="primary"):
                st.session_state["asset_id"] = chosen
                st.query_params["ativo"] = str(chosen)
                st.rerun()
    if tab_new is not None:
        with tab_new:
            submitted, data = asset_form("asset_new", categories)
            if submitted and run_action(lambda: svc.create_asset(ctx, data)):
                flash("Ativo cadastrado. Abra-o na listagem para realizar a análise.")
                st.rerun()
