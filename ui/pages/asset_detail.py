"""Página individual do ativo, organizada em abas: Visão Geral, Análise, Riscos e Controles, Tratamento, Relatórios."""
import streamlit as st

from config.risk_methodology import ANSWER_OPTIONS, BASIS_LABELS, EVIDENCE_LABELS, IMPACT_SCALE, PROBABILITY_SCALE
from models.assessment import Answer
from models.treatment import ACTION_STATUSES, PRIORITIES
from services.asset_service import AssetService
from services.assessment_service import AssessmentService
from services.errors import RiskoraError
from services.report_service import ReportFilters, ReportService
from services.treatment_service import TreatmentService, is_overdue, lifecycle
from ui.components.forms import asset_form
from ui.components.widgets import (can, flash, format_risk, level_label, page_header, risk_matrix_html, run_action,
                                   show_flash, table)

_OPTIONS = list(ANSWER_OPTIONS)


def _leave() -> None:
    st.session_state.pop("asset_id", None)
    st.query_params.clear()
    st.rerun()


def render(conn, ctx, asset_id: int) -> None:
    assets = AssetService(conn)
    try:
        asset = assets.get_asset(ctx, asset_id)
    except RiskoraError:
        st.error("Ativo não encontrado.")
        if st.button("Voltar para Ativos"):
            _leave()
        return
    if st.button("Voltar para Ativos"):
        _leave()
    page_header(f"{asset['category_name']} · {asset['asset_code']}", asset["name"],
                f"Status: {asset['status']} · Criticidade: {asset['criticality']}")
    show_flash()
    tabs = st.tabs(["Visão Geral", "Análise", "Riscos e Controles", "Tratamento", "Relatórios"])
    with tabs[0]:
        _overview(conn, ctx, asset)
    with tabs[1]:
        _analysis(conn, ctx, asset)
    with tabs[2]:
        _risks(conn, ctx, asset)
    with tabs[3]:
        _treatment(conn, ctx, asset)
    with tabs[4]:
        _reports(conn, ctx, asset)


# --------------------------------------------------------------------------------------------- Visão Geral
def _overview(conn, ctx, asset):
    summary = AssessmentService(conn).asset_summary(ctx, asset["id"])
    c = st.columns(3)
    c[0].markdown(f"**Área responsável:** {asset['area'] or '-'}  \n**Responsável:** {asset['owner'] or '-'}  \n"
                  f"**Ambiente:** {asset['environment'] or '-'}")
    c[1].markdown(f"**Classificação da informação:** {asset['information_classification']}  \n"
                  f"**Tipo de informação:** {asset['information_type'] or '-'}  \n"
                  f"**Disponibilidade:** {asset['availability_requirement']}")
    c[2].markdown(f"**Cadastrado em:** {asset['created_at'][:10]}  \n**Atualizado em:** {asset['updated_at'][:10]}")
    if asset["description"]:
        st.markdown(f"**Descrição:** {asset['description']}")
    if asset["interruption_consequences"]:
        st.markdown(f"**Consequências de uma interrupção:** {asset['interruption_consequences']}")
    st.subheader("Indicadores")
    latest = summary["latest"]
    if not asset["has_assessment"]:
        st.info("A avaliação ainda não está disponível para esta categoria de ativo.")
    elif latest is None:
        st.info("Este ativo ainda não possui avaliação concluída." + (" Há uma avaliação em rascunho." if summary["drafts"] else ""))
    else:
        c = st.columns(5)
        c[0].metric("Última avaliação", (latest["completed_at"] or "")[:10])
        for col, level in zip(c[1:], ("Crítico", "Alto", "Moderado", "Baixo")):
            col.metric(f"Riscos {level.lower()}s" if level != "Alto" else "Riscos altos", summary["level_counts"].get(level, 0))
        if summary["level_counts"].get("Dados insuficientes"):
            st.warning(f"{summary['level_counts']['Dados insuficientes']} risco(s) com dados insuficientes: "
                       "informe os impactos do ativo e crie uma nova avaliação.")
    if summary["drafts"]:
        st.caption(f"{len(summary['drafts'])} avaliação(ões) em rascunho.")
    if can(ctx, "asset:write"):
        with st.expander("Editar ativo"):
            submitted, data = asset_form(f"asset_edit_{asset['id']}", AssetService(conn).list_categories(), asset)
            if submitted:
                if run_action(lambda: AssetService(conn).update_asset(ctx, asset["id"], data)):
                    st.warning("Ativo atualizado. Avaliações já concluídas NÃO são alteradas: crie uma nova versão da "
                               "avaliação para refletir novos impactos.")
        if asset["status"] != "Desativado":
            if st.button("Desativar ativo", key=f"deactivate_{asset['id']}"):
                if run_action(lambda: AssetService(conn).set_status(ctx, asset["id"], "Desativado")):
                    flash("Ativo desativado. O histórico foi preservado.")
                    st.rerun()
        elif st.button("Reativar ativo", key=f"reactivate_{asset['id']}"):
            if run_action(lambda: AssetService(conn).set_status(ctx, asset["id"], "Ativo")):
                flash("Ativo reativado.")
                st.rerun()


# --------------------------------------------------------------------------------------------- Análise
def _analysis(conn, ctx, asset):
    svc = AssessmentService(conn)
    if not asset["has_assessment"]:
        st.info("A avaliação ainda não está disponível para esta categoria de ativo.")
        return
    assessments = svc.list_assessments(ctx, asset["id"])
    if can(ctx, "assessment:run") and asset["status"] != "Desativado":
        if st.button("Iniciar nova avaliação", type="primary", key=f"start_{asset['id']}"):
            try:
                st.session_state["_pending_assessment"] = svc.create_assessment(ctx, asset["id"])
            except RiskoraError as exc:
                st.error(str(exc))
            else:
                flash("Avaliação criada em rascunho. Responda ao questionário.")
                st.rerun()
    if not assessments:
        st.info("Nenhuma avaliação registrada para este ativo.")
        return
    sel_key = f"sel_assessment_{asset['id']}"
    if "_pending_assessment" in st.session_state:
        st.session_state[sel_key] = st.session_state.pop("_pending_assessment")
    by_id = {a["id"]: a for a in assessments}
    aid = st.selectbox("Avaliação", list(by_id), key=sel_key,
                       format_func=lambda i: f"#{i} - {by_id[i]['status']} - {(by_id[i]['completed_at'] or by_id[i]['created_at'])[:10]}")
    a = by_id[aid]
    st.caption(f"Metodologia v{a['methodology_version']} · questionário v{a['questionnaire_version']} · "
               f"regras v{a['rules_version']} · avaliador: {a['assessor_name'] or '-'}")
    editable = a["status"] == "Rascunho" and can(ctx, "assessment:run")
    if a["status"] == "Concluída":
        st.info("Avaliação concluída: respostas somente para consulta. Para revisar, crie uma nova versão.")
        if can(ctx, "assessment:run") and asset["status"] != "Desativado" and st.button("Criar nova versão (cópia editável)", key=f"clone_{aid}"):
            if run_action(lambda: st.session_state.__setitem__("_pending_assessment", svc.clone_assessment(ctx, aid))):
                flash("Nova versão criada como rascunho; a original permanece intacta.")
                st.rerun()
    try:
        module = svc.get_module(ctx, aid)
    except RiskoraError as exc:
        st.warning(str(exc))
        module = None
    if module is not None:
        stored = svc.get_answers(ctx, aid)
        live: dict[str, Answer] = {}
        collected: dict[str, tuple] = {}
        current_domain = None
        for q in module.questions:
            if q.domain_no != current_domain:
                current_domain = q.domain_no
                st.markdown(f"#### Domínio {q.domain_no} - {q.domain}")
            if not q.is_visible(live):
                continue
            prev = stored.get(q.code)
            key = f"ans_{aid}_{q.code}"
            st.markdown(f"**{q.code}** - {q.text}")
            st.caption(f"Finalidade: {q.purpose}" + (" (pergunta condicional)" if q.parent_code else ""))
            value = st.radio("Resposta", _OPTIONS, index=_OPTIONS.index(prev.value) if prev else None,
                             format_func=lambda v: ANSWER_OPTIONS[v], horizontal=True, key=key + "_v",
                             disabled=not editable, label_visibility="collapsed")
            c = st.columns(2)
            just = c[0].text_input("Observações (obrigatória se 'Não se aplica')", value=prev.justification if prev else "",
                                   key=key + "_j", disabled=not editable, max_chars=2000)
            evidence = c[1].text_input("Referência de evidência (nome do registro, ticket etc.)",
                                       value=prev.evidence_ref if prev else "", key=key + "_e",
                                       disabled=not editable, max_chars=500)
            if value is not None:
                live[q.code] = Answer(q.code, value, just, evidence)
                collected[q.code] = (value, just, evidence)
        total_visible = len([q for q in module.questions if q.is_visible(live)])
        st.progress(0 if total_visible == 0 else len(live) / total_visible,
                    text=f"{len(live)} de {total_visible} perguntas respondidas")
        if len(live) < total_visible:
            st.warning("Avaliação incompleta: perguntas sem resposta não geram conclusões e podem deixar riscos "
                       "como 'Dados insuficientes'.")
        if editable:
            def save_all() -> bool:
                errors = []
                for code, (value, just, evidence) in collected.items():
                    try:
                        svc.save_answer(ctx, aid, code, value, just, evidence)
                    except RiskoraError as exc:
                        errors.append(f"{code}: {exc}")
                for message in errors:
                    st.error(message)
                return not errors

            c = st.columns(2)
            if c[0].button("Salvar respostas", key=f"save_{aid}") and save_all():
                st.success("Respostas salvas.")
            if c[1].button("Processar e concluir avaliação", type="primary", key=f"finalize_{aid}") and save_all():
                try:
                    result = svc.finalize_assessment(ctx, aid)
                except RiskoraError as exc:
                    st.error(str(exc))
                else:
                    flash(f"Avaliação concluída: {result['findings']} fragilidade(s) potencial(is). "
                          "Consulte a aba Riscos e Controles.")
                    st.rerun()
    with st.expander("Histórico das avaliações deste ativo"):
        table([{"Avaliação": x["id"], "Situação": x["status"], "Avaliador": x["assessor_name"],
                "Iniciada em": x["created_at"][:10], "Concluída em": (x["completed_at"] or "")[:10],
                "Origem": x["parent_assessment_id"] or "", "Metodologia": x["methodology_version"],
                "Questionário": x["questionnaire_version"], "Regras": x["rules_version"]} for x in assessments])


# --------------------------------------------------------------------------------------------- Riscos e Controles
def _concluded_selector(svc, ctx, asset, key):
    concluded = [a for a in svc.list_assessments(ctx, asset["id"]) if a["status"] == "Concluída"]
    if not concluded:
        return None
    by_id = {a["id"]: a for a in concluded}
    return st.selectbox("Avaliação concluída", list(by_id), key=key,
                        format_func=lambda i: f"#{i} - {(by_id[i]['completed_at'] or '')[:10]}")


def _risks(conn, ctx, asset):
    svc = AssessmentService(conn)
    if not asset["has_assessment"]:
        st.info("A avaliação ainda não está disponível para esta categoria de ativo.")
        return
    aid = _concluded_selector(svc, ctx, asset, f"risk_sel_{asset['id']}")
    if aid is None:
        st.info("Conclua uma avaliação para ver riscos e controles.")
        return
    comp = svc.completeness(ctx, aid)
    if not comp.complete:
        st.warning(f"AVALIAÇÃO INCOMPLETA: perguntas sem resposta ({', '.join(comp.missing)}).")
    results = svc.get_results(ctx, aid)
    if not results:
        st.success("Nenhuma fragilidade potencial foi identificada nas respostas. Isso não comprova ausência de risco: "
                   "depende da qualidade das respostas e das evidências.")
        return
    counts: dict = {}
    for r in results:
        cur = r["current"]
        if cur["probability"] and cur["impact"]:
            counts[(cur["probability"], cur["impact"])] = counts.get((cur["probability"], cur["impact"]), 0) + 1
    st.markdown(risk_matrix_html(counts), unsafe_allow_html=True)
    table([{"Regra": r["rule_code"], "Fragilidade potencial": r["title"], "Inerente": format_risk(r["inherent"]),
            "Atual": format_risk(r["current"]), "Residual": format_risk(r["residual"]),
            "Evidência": EVIDENCE_LABELS[r["evidence_status"]]} for r in results])
    if any(r["current"]["level"] == "Dados insuficientes" for r in results):
        st.warning("Há riscos com 'Dados insuficientes': informe os impactos do ativo (aba Visão Geral → Editar ativo) "
                   "e crie uma nova avaliação.")
    for r in results:
        cur = r["current"]
        with st.expander(f"{r['rule_code']} - {r['title']} - {cur['level']}"):
            st.markdown("**1. Respostas que contribuíram**")
            for t in r["triggered"]:
                st.markdown(f"- {t['code']} - {t['question']} → **{t['value_label']}**"
                            + (f" | Obs.: {t['justification']}" if t["justification"] else "")
                            + (f" | Evidência: {t['evidence_ref']}" if t["evidence_ref"] else ""))
            st.markdown(f"**2. Fragilidade potencial:** {r['weakness']}")
            st.caption(f"Base: {BASIS_LABELS[r['basis']]} · Evidência: {EVIDENCE_LABELS[r['evidence_status']]}")
            st.markdown(f"**3. Cenário de risco:** {r['scenario']}")
            st.markdown(f"Consequências possíveis: {r['consequences']}")
            st.markdown(f"**4. Justificativa de probabilidade:** {cur['probability_justification']}")
            st.markdown(f"**5. Justificativa de impacto:** {cur['impact_justification']}")
            st.markdown(f"**6. Classificação** — Inerente: {format_risk(r['inherent'])} | Atual: "
                        f"{level_label(cur['level'])} ({cur['score'] or '-'}) | Residual: {format_risk(r['residual'])}")
            if cur["notes"]:
                st.warning("Incertezas: " + cur["notes"])
            st.markdown("**7. Controles recomendados**")
            for c in r["controls"]:
                pending = any(ref["validation_status"] != "Validada" for ref in c["references"])
                st.markdown(f"- **{c['code']}** - {c['name']} ({c['control_type']})"
                            + (" · :orange[referências a validar]" if pending else ""))
                for ref in c["references"]:
                    st.caption(f"{ref['framework']} {ref['ref_code']} - {ref['ref_title']} ({ref['validation_status']})")
            st.markdown("**8. Ações de tratamento**")
            if r["actions"]:
                for act in r["actions"]:
                    st.markdown(f"- [{lifecycle(act)}] {act['action']} (prazo: {act['due_date'] or '-'})"
                                + (" · :red[vencida]" if is_overdue(act) else ""))
            else:
                st.caption("Nenhuma ação registrada (aba Tratamento).")
            st.markdown("**9. Evidências e limitações**")
            st.markdown(f"Evidência disponível: {r['evidence_description']}")
            st.info(r["limitations"])


# --------------------------------------------------------------------------------------------- Tratamento
def _treatment(conn, ctx, asset):
    svc, tsvc = AssessmentService(conn), TreatmentService(conn)
    if not asset["has_assessment"]:
        st.info("A avaliação ainda não está disponível para esta categoria de ativo.")
        return
    summary = svc.asset_summary(ctx, asset["id"])
    if summary["latest"] is None:
        st.info("Conclua uma avaliação para registrar ações de tratamento.")
        return
    results = svc.get_results(ctx, summary["latest"]["id"])
    if not results:
        st.success("Não há riscos a tratar na avaliação concluída mais recente.")
        return
    risks = {r["id"]: r for r in results}
    label = lambda i: f"{risks[i]['rule_code']} - {risks[i]['title']}"
    st.info("Concluir uma ação NÃO reduz automaticamente o risco. A redução exige reavaliação documentada (risco residual).")
    actions = [(r, a) for r in results for a in r["actions"]]
    st.subheader("Recomendações")
    for r in results:
        with st.expander(f"{label(r['id'])} — {r['current']['level']}"):
            for c in r["controls"]:
                st.markdown(f"**{c['code']} - {c['name']}**")
                for line in c["implementation_actions"].splitlines():
                    st.markdown(f"- {line}")
                st.caption("Evidências esperadas: " + "; ".join(c["expected_evidence"].splitlines()))
    st.subheader("Ações de tratamento")
    table([{"ID": a["id"], "Risco": r["rule_code"], "Ação": a["action"], "Responsável": a["owner"],
            "Prioridade": a["priority"], "Prazo": a["due_date"] or "-", "Status": a["status"], "Ciclo": lifecycle(a),
            "Vencida": "Sim" if is_overdue(a) else ""} for r, a in actions])
    if any(is_overdue(a) for _, a in actions):
        st.error("Existem ações vencidas.")
    tab_new, tab_edit, tab_re = st.tabs(["Nova ação", "Atualizar, evidências e validação", "Reavaliar risco"])
    with tab_new:
        if not can(ctx, "treatment:write"):
            st.caption("Seu perfil não permite registrar ações.")
        else:
            rid = st.selectbox("Risco relacionado", list(risks), format_func=label, key=f"new_action_risk_{asset['id']}")
            controls = {c["code"]: c for c in risks[rid]["controls"]}
            with st.form(f"new_action_{asset['id']}"):
                control = st.selectbox("Controle relacionado", [None] + list(controls),
                                       format_func=lambda c: "(nenhum)" if c is None else f"{c} - {controls[c]['name']}")
                action = st.text_area("Ação recomendada", max_chars=2000)
                c = st.columns(3)
                owner = c[0].text_input("Responsável", max_chars=200)
                priority = c[1].selectbox("Prioridade", PRIORITIES, index=1)
                due = c[2].date_input("Prazo", value=None)
                evidence = st.text_input("Evidência esperada", max_chars=1000)
                notes = st.text_area("Observações", max_chars=2000)
                if st.form_submit_button("Registrar ação", type="primary"):
                    if run_action(lambda: tsvc.create_action(ctx, rid, {
                            "action": action, "owner": owner, "priority": priority, "due_date": due,
                            "expected_evidence": evidence, "notes": notes}, control_code=control)):
                        flash("Ação registrada.")
                        st.rerun()
    with tab_edit:
        if not actions:
            st.info("Nenhuma ação para atualizar.")
        else:
            by_id = {a["id"]: a for _, a in actions}
            action_id = st.selectbox("Ação", list(by_id), key=f"edit_action_{asset['id']}",
                                     format_func=lambda i: f"#{i} - {by_id[i]['action'][:70]}")
            details = tsvc.action_details(ctx, action_id)
            st.caption(f"Ciclo: {details['lifecycle']}" + (" · VENCIDA" if details["overdue"] else ""))
            if can(ctx, "treatment:write"):
                with st.form(f"edit_form_{action_id}"):
                    action = st.text_area("Ação recomendada", value=details["action"], max_chars=2000)
                    c = st.columns(3)
                    owner = c[0].text_input("Responsável", value=details["owner"], max_chars=200)
                    priority = c[1].selectbox("Prioridade", PRIORITIES, index=PRIORITIES.index(details["priority"]))
                    status = c[2].selectbox("Status", ACTION_STATUSES, index=ACTION_STATUSES.index(details["status"]))
                    due = st.text_input("Prazo (AAAA-MM-DD)", value=details["due_date"] or "")
                    evidence = st.text_input("Evidência esperada", value=details["expected_evidence"], max_chars=1000)
                    notes = st.text_area("Observações", value=details["notes"], max_chars=2000)
                    if st.form_submit_button("Atualizar ação", type="primary"):
                        if run_action(lambda: tsvc.update_action(ctx, action_id, {
                                "action": action, "owner": owner, "priority": priority, "status": status,
                                "due_date": due, "expected_evidence": evidence, "notes": notes})):
                            flash("Ação atualizada. A classificação do risco NÃO foi alterada.")
                            st.rerun()
                with st.form(f"evidence_form_{action_id}"):
                    st.markdown("**Registrar evidência de execução**")
                    description = st.text_input("Descrição", max_chars=1000)
                    reference = st.text_input("Referência (nome do documento, ticket, local de guarda)", max_chars=500)
                    if st.form_submit_button("Registrar evidência"):
                        if run_action(lambda: tsvc.add_evidence(ctx, action_id, description, reference)):
                            flash("Evidência registrada.")
                            st.rerun()
            if can(ctx, "treatment:validate"):
                with st.form(f"validate_form_{action_id}"):
                    st.markdown("**Validar ação concluída**")
                    notes = st.text_input("Observações da validação", max_chars=2000)
                    if st.form_submit_button("Validar ação"):
                        if run_action(lambda: tsvc.validate_action(ctx, action_id, notes)):
                            flash("Ação validada.")
                            st.rerun()
            st.markdown("**Evidências**")
            table([{"Descrição": e["description"], "Referência": e["reference"], "Registrada em": e["created_at"][:10]}
                   for e in details["evidence"]])
            st.markdown("**Histórico**")
            table([{"Quando": e["created_at"], "Quem": e["user_email"] or "-", "Evento": e["event_type"],
                    "Detalhe": e["detail"]} for e in details["events"]])
    with tab_re:
        if not can(ctx, "treatment:validate"):
            st.caption("Somente gestores e administradores registram o risco residual.")
        else:
            rid = st.selectbox("Risco a reavaliar", list(risks), format_func=label, key=f"reassess_{asset['id']}")
            r = risks[rid]
            st.markdown(f"Atual: {format_risk(r['current'])} · Residual registrado: {format_risk(r['residual'])}")
            options_p, options_i = [None] + list(PROBABILITY_SCALE), [None] + list(IMPACT_SCALE)
            with st.form(f"reassess_form_{rid}"):
                p = st.selectbox("Probabilidade residual", options_p, key=f"re_p_{rid}",
                                 format_func=lambda v: "Não informado" if v is None else f"{v} - {PROBABILITY_SCALE[v][0]}")
                i = st.selectbox("Impacto residual", options_i, key=f"re_i_{rid}",
                                 index=options_i.index(r["current"]["impact"]) if r["current"]["impact"] in options_i else 0,
                                 format_func=lambda v: "Não informado" if v is None else f"{v} - {IMPACT_SCALE[v][0]}")
                pj = st.text_area("Justificativa da probabilidade (com evidências da eficácia dos controles)", max_chars=2000)
                ij = st.text_area("Justificativa do impacto", max_chars=2000)
                notes = st.text_area("Observações", max_chars=2000)
                if st.form_submit_button("Registrar risco residual", type="primary"):
                    if run_action(lambda: tsvc.reassess_risk(ctx, rid, p, i, pj, ij, notes)):
                        flash("Reavaliação registrada como risco residual (histórico preservado).")
                        st.rerun()


# --------------------------------------------------------------------------------------------- Relatórios
def _reports(conn, ctx, asset):
    rs = ReportService(conn)
    if not can(ctx, "report:export"):
        st.caption("Seu perfil não permite gerar relatórios.")
        return
    flt = ReportFilters(asset_id=asset["id"])
    st.markdown("**Relatório do ativo**")
    md = rs.asset_report_markdown(ctx, asset["id"])
    c = st.columns(2)
    c[0].download_button("Baixar relatório do ativo (Markdown)", md.encode("utf-8"),
                         file_name=f"riskora_{asset['asset_code']}.md", mime="text/markdown",
                         on_click=lambda: rs.log_export(ctx, "asset", "md", asset["id"]))
    risks_report = rs.build_report(ctx, "geral", flt)
    if risks_report.rows:
        c[1].download_button("Baixar riscos do ativo (CSV)", rs.csv_text(ctx, risks_report).encode("utf-8-sig"),
                             file_name=f"riskora_{asset['asset_code']}_riscos.csv", mime="text/csv",
                             on_click=lambda: rs.log_export(ctx, "geral", "csv", asset["id"]))
    with st.expander("Pré-visualizar relatório do ativo"):
        st.markdown(md)
    for kind, title in (("geral", "Riscos associados"), ("controles", "Controles avaliados"),
                        ("tratamento", "Planos de tratamento"), ("historico", "Histórico das avaliações")):
        st.markdown(f"**{title}**")
        report = rs.build_report(ctx, kind, flt)
        st.caption(report.narrative)
        table(report.rows)
