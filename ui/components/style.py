"""Identidade visual: CSS, logotipos e ícone. Os arquivos vêm do próprio projeto (assets/)."""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
LOGO_CLARA = _ASSETS / "images" / "riskora_logo_clara.png"   # off-white, para fundos bordô
LOGO_BORDO = _ASSETS / "images" / "riskora_logo_bordo.png"   # bordô, para fundos claros
ICONE = _ASSETS / "images" / "riskora_icone.png"

@lru_cache(maxsize=None)
def _read_text(relative: str) -> str:
    return (_ASSETS / relative).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def data_uri(path: Path) -> str:
    """Imagem embutida na página (data URI), para usar em HTML sem servir arquivos estáticos."""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def page_icon():
    """Ícone da aba do navegador (PIL.Image)."""
    from PIL import Image
    return Image.open(ICONE)


def inject_css() -> None:
    st.markdown(f"<style>{_read_text('styles/riskora.css')}</style>", unsafe_allow_html=True)


def inject_login_css() -> None:
    """CSS base + CSS exclusivo da tela de login (painel bordô de ponta a ponta, fundo suave, cartão do formulário)."""
    st.markdown(f"<style>{_read_text('styles/riskora.css')}{_read_text('styles/login.css')}</style>",
                unsafe_allow_html=True)


def brand_header() -> None:
    st.markdown(f"<img src='{data_uri(LOGO_BORDO)}' style='height:40px;margin:4px 0 18px 0' alt='Riskora'>",
                unsafe_allow_html=True)
