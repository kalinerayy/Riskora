"""Riskora - plataforma de GRC (governança, riscos e conformidade) para ativos tecnológicos.

Execute com:  streamlit run app.py
Primeiro acesso: crie o administrador com  python -m scripts.create_admin  (veja o README).
"""
import logging

import streamlit as st

from database.connection import get_connection, init_database
from models.user import ROLES
from services.authentication_service import AuthenticationService
from services.guest_service import GuestAccessService
from ui.components.style import ICONE, LOGO_CLARA, brand_header, inject_css, page_icon
from ui.pages import assets, login, overview, reports, settings

st.set_page_config(page_title="Riskora", page_icon=page_icon(), layout="wide")
log = logging.getLogger("riskora")


@st.cache_resource
def get_resources():
    """Uma conexão e os serviços de acesso compartilhados pelo processo (uso de equipe pequena)."""
    conn = get_connection()
    init_database(conn)
    auth = AuthenticationService(conn)
    return conn, auth, GuestAccessService(conn, auth)


def _make_page(module, name: str, conn, ctx):
    def _run():
        module.render(conn, ctx)
    _run.__name__ = name  # nome único por página
    return _run


def _logout(auth, token):
    auth.logout(token)
    for key in ("auth_token", "org_id", "asset_id", "_last_org"):
        st.session_state.pop(key, None)
    st.rerun()


def main():
    conn, auth, guest = get_resources()
    token = st.session_state.get("auth_token")
    user = auth.validate_session(token)
    if user is None:
        for key in ("auth_token", "org_id", "asset_id"):
            st.session_state.pop(key, None)
        login.render(auth, guest)
        return
    inject_css()
    st.logo(str(LOGO_CLARA), icon_image=str(ICONE))
    if user["must_change_password"]:
        login.render_change_password(auth, user, token)
        return
    orgs = auth.list_organizations_for(user)
    if not orgs:
        brand_header()
        st.warning("Seu usuário ainda não tem acesso a nenhuma organização. Solicite ao administrador.")
        if st.button("Sair"):
            _logout(auth, token)
        return
    ids = [o["organization_id"] for o in orgs]
    names = {o["organization_id"]: o["organization_name"] + (" (demonstração)" if o["is_demo"] else "") for o in orgs}
    if st.session_state.get("org_id") not in ids:
        st.session_state["org_id"] = ids[0]
    if len(ids) > 1:
        st.sidebar.selectbox("Organização", ids, format_func=lambda i: names[i], key="org_id")
    org_id = st.session_state["org_id"]
    if st.session_state.get("_last_org") != org_id:  # trocou de organização: limpa a seleção de ativo
        st.session_state["_last_org"] = org_id
        st.session_state.pop("asset_id", None)
    ctx = auth.get_context(token, org_id)
    if ctx is None:
        st.error("Sessão ou acesso inválido. Entre novamente.")
        _logout(auth, token)
        return
    pages = [
        st.Page(_make_page(overview, "visao_geral", conn, ctx), title="Visão Geral", icon=":material/dashboard:",
                url_path="visao-geral", default=True),
        st.Page(_make_page(assets, "ativos", conn, ctx), title="Ativos", icon=":material/inventory_2:",
                url_path="ativos"),
        st.Page(_make_page(reports, "relatorios", conn, ctx), title="Relatórios", icon=":material/description:",
                url_path="relatorios"),
        st.Page(_make_page(settings, "configuracoes", conn, ctx), title="Configurações", icon=":material/settings:",
                url_path="configuracoes"),
    ]
    navigation = st.navigation(pages)
    with st.sidebar:
        st.markdown("---")
        st.caption(f"{names[org_id]}")
        if ctx.is_guest:
            st.caption("Visitante · demonstração compartilhada")
        else:
            st.caption(f"{ctx.full_name or ctx.email} · {ROLES.get(ctx.role, ctx.role)}")
        if st.button("Sair", key="logout_button"):
            _logout(auth, token)
    try:
        navigation.run()
    except Exception:  # não expõe detalhes internos na interface
        log.exception("Erro inesperado em página")
        st.error("Ocorreu um erro inesperado. Os detalhes técnicos estão no terminal da aplicação.")


main()
