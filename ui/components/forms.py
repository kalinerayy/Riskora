"""Formulários padronizados reutilizados por mais de uma página."""
import streamlit as st

from config.risk_methodology import IMPACT_DIMENSIONS, IMPACT_SCALE
from models.asset import (ASSET_STATUSES, AVAILABILITY_REQUIREMENTS, CLASSIFICATIONS, CRITICALITY_LEVELS,
                          IMPACT_FIELDS)

_IMPACT_LABELS = dict(zip(IMPACT_FIELDS, IMPACT_DIMENSIONS.values()))


def _index(options, value, default=0):
    return list(options).index(value) if value in options else default


def asset_form(key: str, categories: list[dict], asset: dict | None = None):
    """Formulário padronizado de ativo (cadastro e edição). Devolve (enviado, dados)."""
    a = asset or {}
    codes = [c["code"] for c in categories]
    names = {c["code"]: c["name"] + ("" if c["has_assessment"] else " (avaliação ainda não disponível)") for c in categories}
    with st.form(key):
        c = st.columns(3)
        name = c[0].text_input("Nome do ativo", value=a.get("name", ""), max_chars=200)
        category = c[1].selectbox("Categoria", codes, index=_index(codes, a.get("category_code")),
                                  format_func=lambda x: names[x])
        code = c[2].text_input("Identificador (vazio = automático)", value=a.get("asset_code", ""), max_chars=40,
                               disabled=bool(asset))
        description = st.text_area("Descrição", value=a.get("description", ""), max_chars=2000)
        c = st.columns(3)
        area = c[0].text_input("Área responsável", value=a.get("area", ""), max_chars=200)
        owner = c[1].text_input("Responsável pelo ativo", value=a.get("owner", ""), max_chars=200)
        environment = c[2].text_input("Localização ou ambiente", value=a.get("environment", ""), max_chars=200)
        c = st.columns(4)
        criticality = c[0].selectbox("Criticidade para o negócio", CRITICALITY_LEVELS,
                                     index=_index(CRITICALITY_LEVELS, a.get("criticality")))
        classification = c[1].selectbox("Classificação da informação", CLASSIFICATIONS,
                                        index=_index(CLASSIFICATIONS, a.get("information_classification")))
        availability = c[2].selectbox("Requisito de disponibilidade", AVAILABILITY_REQUIREMENTS,
                                      index=_index(AVAILABILITY_REQUIREMENTS, a.get("availability_requirement")))
        status = c[3].selectbox("Status", ASSET_STATUSES, index=_index(ASSET_STATUSES, a.get("status")))
        info_type = st.text_input("Tipo de informação armazenada", value=a.get("information_type", ""), max_chars=500)
        consequences = st.text_area("Consequências de uma interrupção", value=a.get("interruption_consequences", ""),
                                    max_chars=2000)
        st.markdown("**Impacto por dimensão** (deixe 'Não informado' se desconhecido: o risco ficará como 'Dados insuficientes')")
        options = [None, 1, 2, 3, 4, 5]
        impacts = {}
        cols = st.columns(3)
        for n, field in enumerate(IMPACT_FIELDS):
            impacts[field] = cols[n % 3].selectbox(
                _IMPACT_LABELS[field], options, index=_index(options, a.get(field)),
                format_func=lambda v: "Não informado" if v is None else f"{v} - {IMPACT_SCALE[v][0]}",
                key=f"{key}_{field}")
        justification = st.text_area("Justificativa do impacto", value=a.get("impact_justification", ""), max_chars=2000)
        submitted = st.form_submit_button("Salvar ativo", type="primary")
    data = {"name": name, "category_code": category, "asset_code": code, "description": description, "area": area,
            "owner": owner, "environment": environment, "criticality": criticality,
            "information_classification": classification, "availability_requirement": availability, "status": status,
            "information_type": info_type, "interruption_consequences": consequences,
            "impact_justification": justification, **impacts}
    return submitted, data
