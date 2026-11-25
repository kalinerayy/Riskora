"""Componentes reutilizáveis da interface (sem regra de negócio)."""
from __future__ import annotations

import html
from typing import Callable

import pandas as pd
import streamlit as st

from config.risk_methodology import LEVEL_COLORS, PROBABILITY_SCALE
from models.user import Context
from services.errors import RiskoraError
from services.risk_engine import classify_score

_LEVEL_CLASS = {"Baixo": "baixo", "Moderado": "moderado", "Alto": "alto", "Crítico": "critico"}
_MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def can(ctx: Context, permission: str) -> bool:
    """Apenas para esconder controles. A verificação de verdade acontece nos serviços."""
    return ctx.has(permission)


def esc(value) -> str:
    """Escapa texto que pode vir do usuário antes de colocá-lo em HTML."""
    return html.escape(str(value if value is not None else ""))


def date_pt(iso_text: str | None) -> str:
    """'2026-11-17...' -> '17 nov 2026'."""
    if not iso_text:
        return ""
    year, month, day = iso_text[:10].split("-")
    return f"{int(day)} {_MONTHS[int(month) - 1]} {year}"


def page_header(eyebrow: str, title: str, right: str = "") -> None:
    st.markdown(f"<div class='rk-header'><div><div class='rk-eyebrow'>{esc(eyebrow)}</div>"
                f"<h1 class='rk-title'>{esc(title)}</h1></div><div class='rk-updated'>{esc(right)}</div></div>",
                unsafe_allow_html=True)


def kpi_cards(items: list[tuple], small: bool = False) -> None:
    """items: (rótulo, valor, subtítulo ou '', destaque em bordô). Valores são números ou textos curtos."""
    size = " rk-kpi-sm" if small else ""
    cards = "".join(
        f"<div class='rk-kpi{size}'><div class='rk-kpi-label'>{esc(label)}</div>"
        f"<div class='rk-kpi-value{' rk-accent' if accent else ''}'>{esc(value)}</div>"
        + (f"<div class='rk-kpi-sub'>{esc(sub)}</div>" if sub else "") + "</div>"
        for label, value, sub, accent in items)
    grid = "rk-kpi-grid rk-kpi-grid-sm" if small else "rk-kpi-grid"
    st.markdown(f"<div class='{grid}'>{cards}</div>", unsafe_allow_html=True)


def level_badge(level: str) -> str:
    cls = _LEVEL_CLASS.get(level, "neutro")
    return f"<span class='rk-badge rk-b-{cls}'>{esc(level)}</span>"


def level_label(level: str) -> str:
    return f":{LEVEL_COLORS.get(level, 'gray')}[**{level}**]"


def format_risk(row) -> str:
    if not row:
        return "Sem reavaliação"
    return f"{row['level']} ({row['score']})" if row["score"] else row["level"]


def risk_matrix_html(counts: dict) -> str:
    """Matriz 5x5 em tons de bordô. Só números e rótulos fixos entram no HTML (nunca texto do usuário).
    O significado não depende só da cor: cada célula mostra a contagem e há legenda com os nomes dos níveis."""
    cells = ["<div class='rk-matrix'><div></div>"]
    cells += [f"<div class='rk-m-head'>Impacto {i}</div>" for i in range(1, 6)]
    for p in range(5, 0, -1):
        cells.append(f"<div class='rk-m-row'>Prob. {p}<br>{esc(PROBABILITY_SCALE[p][0])}</div>")
        for i in range(1, 6):
            n = int(counts.get((p, i), 0))
            level = classify_score(p * i)
            title = f"Probabilidade {p} x Impacto {i} = {p * i} ({level}): {n} risco(s)"
            cells.append(f"<div class='rk-m-cell rk-m-{_LEVEL_CLASS[level]}{'' if n else ' rk-empty'}' "
                         f"title='{esc(title)}'>{n if n else '·'}</div>")
    cells.append("</div>")
    legend = "".join(f"<span><i class='rk-m-{cls}'></i>{name}</span>" for name, cls in _LEVEL_CLASS.items())
    return "".join(cells) + f"<div class='rk-legend'>{legend}</div>"


def card(title: str, body_html: str, note: str = "") -> None:
    """Cartão do dashboard. body_html deve ser HTML já seguro (feito com esc() onde houver texto do usuário)."""
    note_html = f"<p class='rk-card-note'>{esc(note)}</p>" if note else ""
    st.markdown(f"<div class='rk-card'><h3 class='rk-card-title'>{esc(title)}</h3>{body_html}{note_html}</div>",
                unsafe_allow_html=True)


def flash(message: str, kind: str = "success") -> None:
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("_flash", None)
    if item:
        getattr(st, item[0])(item[1])


def run_action(action: Callable[[], object]) -> bool:
    """Executa uma operação de serviço e mostra a mensagem de erro de negócio, se houver."""
    try:
        action()
        return True
    except RiskoraError as exc:
        st.error(str(exc))
        return False


def table(rows: list[dict], rename: dict | None = None) -> None:
    """Mostra uma lista de dicionários como tabela, escondendo colunas internas (iniciadas por '_')."""
    if not rows:
        st.caption("Sem registros.")
        return
    df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])
    if rename:
        df = df.rename(columns=rename)
    st.dataframe(df, hide_index=True)
