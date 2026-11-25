"""Dashboard executivo (página inicial), no layout da referência visual. Todos os números vêm do banco."""
import pandas as pd
import streamlit as st

from services.report_service import ReportService
from ui.components.widgets import (card, date_pt, esc, kpi_cards, level_badge, page_header, risk_matrix_html,
                                   show_flash)

_BORDO = "#6B1A2D"


def _bar(title: str, data: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if not data or not any(data.values()):
            st.caption("Sem dados.")
        else:
            st.bar_chart(pd.DataFrame({"Quantidade": list(data.values())}, index=list(data.keys())), color=_BORDO)


def _recommendations_html(items: list[dict]) -> str:
    if not items:
        return "<p class='rk-muted'>Conclua uma avaliação para ver as recomendações prioritárias.</p>"
    rows = []
    for r in items:
        action = f"<div class='rk-rec-action'>Ação sugerida: {esc(r['acao'])}</div>" if r["acao"] else ""
        rows.append(f"<div class='rk-rec'>{level_badge(r['nivel'])}<b>{esc(r['ativo'])}</b> — {esc(r['fragilidade'])}"
                    f"{action}</div>")
    return "".join(rows)


def render(conn, ctx):
    rs = ReportService(conn)
    d = rs.compute_dashboard(ctx)
    updated = f"Atualizado em {date_pt(d['last_update'])}" if d["last_update"] else "Sem avaliações concluídas"
    page_header("Visão geral de riscos", "Exposição corporativa", updated)
    show_flash()
    if d["assets_total"] == 0:
        st.info("Ainda não há ativos cadastrados. Comece pela página Ativos.")
    kpi_cards([
        ("Riscos críticos", d["distribution"].get("Crítico", 0), "risco atual", True),
        ("Ativos mapeados", d["assets_active"], f"{d['assets_assessed']} avaliado(s)", False),
        ("Controles avaliados", d["controls_evaluated"], f"{d['controls_deficient']} com deficiência", False),
        ("Planos em atraso", d["actions_overdue"], f"{d['actions_pending']} ação(ões) pendente(s)", False),
    ])
    left, right = st.columns(2, gap="medium")
    with left:
        card("Matriz probabilidade × impacto", risk_matrix_html(d["matrices"]["current"]),
             "Risco atual das avaliações vigentes (uma por ativo). Cada célula mostra quantos riscos caem naquela combinação.")
    with right:
        card("Recomendações prioritárias", _recommendations_html(rs.priority_recommendations(ctx)),
             "Ordenadas pela pontuação do risco atual. São sugestões baseadas em respostas declaradas.")
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    kpi_cards([
        ("Riscos identificados", d["risks_total"], "", False),
        ("Precisam de tratamento", d["needs_treatment"], "alto ou crítico", False),
        ("Fragilidades identificadas", d["findings_total"], f"{d['insufficient_evidence']} sem evidência referenciada", False),
        ("Ações concluídas", d["actions_done"], "", False),
        ("Avaliações pendentes", d["assessments_pending"], "ativos sem avaliação concluída", False),
        ("Avaliações incompletas", d["assessments_incomplete"], "perguntas sem resposta", False),
    ], small=True)
    if d["assessments_incomplete"]:
        st.warning("Há avaliações incompletas: perguntas sem resposta não geram conclusões.")
    if d["actions_overdue"]:
        st.error(f"{d['actions_overdue']} ação(ões) de tratamento vencida(s).")
    if d["insufficient_evidence"]:
        st.warning("Há fragilidades baseadas apenas em declaração ou em lacuna de conhecimento. "
                   "Confirme com evidências antes de decidir.")
    with st.expander("Matrizes de risco inerente e residual"):
        for title, kind in (("Risco inerente (antes dos controles)", "inherent"),
                            ("Risco residual (após reavaliação documentada)", "residual")):
            st.markdown(f"**{title}**")
            if not d["matrices"][kind]:
                st.caption("Nenhum risco reavaliado ainda." if kind == "residual" else "Sem riscos calculados.")
            st.markdown(risk_matrix_html(d["matrices"][kind]), unsafe_allow_html=True)
    c = st.columns(2, gap="medium")
    with c[0]:
        _bar("Distribuição de riscos por criticidade", d["distribution"])
    with c[1]:
        _bar("Riscos por categoria de ativo", d["risks_by_category"])
    c = st.columns(2, gap="medium")
    with c[0]:
        _bar("Fragilidades recorrentes", dict(d["recurring_weaknesses"]))
    with c[1]:
        _bar("Situação dos planos de tratamento", d["treatment_lifecycle"])
    with st.container(border=True):
        st.markdown("**Evolução das avaliações**")
        if d["evolution"]:
            st.line_chart(pd.DataFrame(d["evolution"]).set_index("mes"), color=[_BORDO, "#B58090"])
        else:
            st.caption("Sem avaliações concluídas.")
    st.caption("Totais atuais consideram a avaliação concluída mais recente de cada ativo. A evolução usa todas as "
               "avaliações concluídas. Detalhes e explicações em Relatórios e na página de cada ativo.")
