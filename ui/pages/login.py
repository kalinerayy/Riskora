"""Tela de login em dois painéis, botão de visitante e telas de troca/recuperação de senha."""
from __future__ import annotations

import streamlit as st

from services.errors import RiskoraError
from ui.components.style import ICONE, LOGO_CLARA, brand_header, data_uri, inject_login_css
from ui.components.widgets import esc

TOKEN_KEY = "auth_token"


def panel_html() -> str:
    """Painel bordô da esquerda (fixo: ocupa a tela inteira de cima a baixo)."""
    return (f"<div class='rk-login-panel'><img src='{data_uri(LOGO_CLARA)}' alt='Riskora'>"
            "<div class='rk-login-headline'>Inteligência em riscos.<br>Estratégia em proteção.</div>"
            "<p>A Riskora reúne ativos, controles, fragilidades e riscos em um só lugar, para que as decisões "
            "de proteção sejam tomadas com base em evidências e acompanhadas até o fim.</p></div>")


def brand_html() -> str:
    """Ícone grande entre duas linhas finas e o título, como na referência."""
    return ("<div class='rk-login-brand'><span class='rk-line'></span>"
            f"<img class='rk-login-icon' src='{data_uri(ICONE)}' alt='Riskora'><span class='rk-line rk-line-r'></span></div>"
            "<div class='rk-login-title'>Acesse sua conta</div>")


def divider_html() -> str:
    return "<div class='rk-or'><span></span>ou<span></span></div>"


def render(auth, guest=None) -> None:
    inject_login_css()
    left, right = st.columns(2, gap="small")
    with left:
        st.markdown(panel_html(), unsafe_allow_html=True)
    with right:
        st.markdown("<div style='height:9vh'></div>", unsafe_allow_html=True)
        _, center, _ = st.columns([1, 4, 1])
        with center:
            st.markdown(brand_html(), unsafe_allow_html=True)
            with st.form("login_form"):
                email = st.text_input("E-mail")
                password = st.text_input("Senha", type="password")  # o campo já traz o botão de mostrar senha
                submitted = st.form_submit_button("Entrar", type="primary")
            if submitted:
                try:
                    st.session_state[TOKEN_KEY] = auth.login(email, password)
                except RiskoraError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
            if guest is not None and guest.enabled:
                st.markdown(divider_html(), unsafe_allow_html=True)
                if st.button("Entrar como visitante"):
                    try:
                        st.session_state[TOKEN_KEY] = guest.enter()
                    except RiskoraError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()
                st.markdown(f"<div class='rk-guest-note'>{esc(guest.description())}</div>", unsafe_allow_html=True)
            with st.expander("Esqueci minha senha"):
                st.caption("Peça ao administrador da sua organização um token de recuperação (uso único e validade "
                           "curta). Com ele, defina uma nova senha abaixo.")
                with st.form("reset_form"):
                    r_email = st.text_input("E-mail", key="reset_email")
                    r_token = st.text_input("Token de recuperação", type="password")
                    r_pass = st.text_input("Nova senha", type="password", key="reset_pass")
                    r_pass2 = st.text_input("Repita a nova senha", type="password", key="reset_pass2")
                    if st.form_submit_button("Redefinir senha"):
                        if r_pass != r_pass2:
                            st.error("As senhas não coincidem.")
                        else:
                            try:
                                auth.reset_password_with_token(r_email, r_token, r_pass)
                                st.success("Senha redefinida. Entre com a nova senha.")
                            except RiskoraError as exc:
                                st.error(str(exc))
            st.markdown("<div class='rk-login-foot'>Não tem acesso? Solicite ao administrador da sua organização.</div>",
                        unsafe_allow_html=True)


def render_change_password(auth, user: dict, token: str) -> None:
    """Exibida quando o usuário precisa trocar a senha provisória antes de usar a plataforma."""
    brand_header()
    st.subheader("Defina uma nova senha")
    st.write("Sua senha é provisória. Escolha uma nova senha para continuar.")
    with st.form("force_change"):
        current = st.text_input("Senha atual", type="password")
        new = st.text_input("Nova senha", type="password")
        new2 = st.text_input("Repita a nova senha", type="password")
        submitted = st.form_submit_button("Salvar nova senha", type="primary")
    if submitted:
        if new != new2:
            st.error("As senhas não coincidem.")
        else:
            try:
                auth.change_password(user["id"], current, new)
            except RiskoraError as exc:
                st.error(str(exc))
            else:
                st.rerun()
    if st.button("Sair"):
        auth.logout(token)
        st.session_state.pop(TOKEN_KEY, None)
        st.rerun()
