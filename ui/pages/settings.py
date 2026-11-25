"""Configurações: minha conta, usuários, organização, metodologia, controles, auditoria e segurança."""
import pandas as pd
import streamlit as st

from config import risk_methodology as m
from models.organization import ORG_STATUSES
from models.user import ASSIGNABLE_ROLES, ROLES
from modules.registry import MODULES
from services.assessment_service import AssessmentService
from services.audit_service import AuditService
from services.authentication_service import AuthenticationService
from services.organization_service import OrganizationService
from ui.components.widgets import can, flash, page_header, run_action, show_flash, table


def _account(conn, ctx):
    st.markdown(f"**{ctx.full_name or ctx.email}** · {ctx.email} · perfil: {ROLES.get(ctx.role, ctx.role)}")
    with st.form("change_password"):
        current = st.text_input("Senha atual", type="password")
        new = st.text_input("Nova senha", type="password")
        new2 = st.text_input("Repita a nova senha", type="password")
        if st.form_submit_button("Alterar senha", type="primary"):
            if new != new2:
                st.error("As senhas não coincidem.")
            elif run_action(lambda: AuthenticationService(conn).change_password(ctx.user_id, current, new)):
                st.success("Senha alterada.")


def _users(conn, ctx):
    org, auth = OrganizationService(conn), AuthenticationService(conn)
    members = org.list_members(ctx)
    table([{"E-mail": x["email"], "Nome": x["full_name"], "Perfil": ROLES[x["role_code"]], "Situação": x["status"],
            "Último acesso": (x["last_login_at"] or "")[:16], "Troca de senha pendente": "Sim" if x["must_change_password"] else ""}
           for x in members])
    with st.expander("Novo usuário"):
        with st.form("new_user"):
            email = st.text_input("E-mail")
            name = st.text_input("Nome", max_chars=120)
            role = st.selectbox("Perfil", list(ASSIGNABLE_ROLES), index=2, format_func=lambda r: ROLES[r])
            password = st.text_input("Senha provisória (o usuário trocará no primeiro acesso)", type="password")
            if st.form_submit_button("Criar usuário", type="primary"):
                if run_action(lambda: org.create_user(ctx, email, name, role, password)):
                    flash("Usuário provisionado.")
                    st.rerun()
    if members:
        by_id = {x["user_id"]: x for x in members}
        user_id = st.selectbox("Usuário", list(by_id), format_func=lambda i: by_id[i]["email"])
        c = st.columns(3)
        roles = list(ASSIGNABLE_ROLES)
        current_role = by_id[user_id]["role_code"]
        new_role = c[0].selectbox("Novo perfil", roles, index=roles.index(current_role) if current_role in roles else 0,
                                  format_func=lambda r: ROLES[r])
        if c[0].button("Alterar perfil") and run_action(lambda: org.change_role(ctx, user_id, new_role)):
            flash("Perfil alterado.")
            st.rerun()
        if c[1].button("Gerar token de recuperação de senha"):
            try:
                token = auth.issue_reset_token(ctx, user_id)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success(f"Token válido por {auth.settings.reset_token_minutes} minutos e de uso único. "
                           "Ele não será exibido novamente: repasse ao usuário por um canal seguro.")
                st.code(token)
        if c[2].button("Remover da organização") and run_action(lambda: org.remove_member(ctx, user_id)):
            flash("Usuário removido da organização.")
            st.rerun()


def _organization(conn, ctx):
    svc = OrganizationService(conn)
    org = svc.get_organization(ctx)
    with st.form("org_form"):
        name = st.text_input("Nome da organização", value=org["name"], max_chars=200)
        st.text_input("Identificação", value=org["slug"], disabled=True)
        business = st.text_area("Descrição do negócio", value=org["business_description"], max_chars=2000)
        context = st.text_area("Contexto organizacional", value=org["context"], max_chars=4000)
        responsible = st.text_input("Responsável", value=org["responsible"], max_chars=200)
        status = st.selectbox("Situação", ORG_STATUSES, index=ORG_STATUSES.index(org["status"]))
        st.caption(f"Cadastrada em {org['created_at'][:10]}")
        if st.form_submit_button("Salvar", type="primary"):
            if run_action(lambda: svc.update_organization(ctx, name, business, context, responsible, status)):
                flash("Organização atualizada.")
                st.rerun()


def _methodology(conn, ctx):
    st.caption(m.METHODOLOGY_NOTICE)
    st.caption(f"Metodologia v{m.METHODOLOGY_VERSION}. Para alterar os parâmetros, edite config/risk_methodology.py e "
               "incremente a versão: cada avaliação grava a versão usada.")
    st.markdown("**Probabilidade**")
    st.dataframe(pd.DataFrame([(k, *v) for k, v in m.PROBABILITY_SCALE.items()], columns=["Nível", "Rótulo", "Critério"]), hide_index=True)
    st.markdown("**Impacto**")
    st.dataframe(pd.DataFrame([(k, *v) for k, v in m.IMPACT_SCALE.items()], columns=["Nível", "Rótulo", "Critério"]), hide_index=True)
    st.markdown("Dimensões: " + ", ".join(m.IMPACT_DIMENSIONS.values()))
    st.markdown(f"**Consolidação do impacto:** {m.IMPACT_CONSOLIDATION_RULE}")
    st.markdown("**Cálculo:** Risco = Probabilidade × Impacto (1 a 25). Faixas iniciais:")
    st.dataframe(pd.DataFrame(m.RISK_BANDS, columns=["De", "Até", "Classificação"]), hide_index=True)
    st.markdown("**Probabilidade atual por base da conclusão:**")
    for basis, (p, text) in m.BASIS_PROBABILITY.items():
        st.markdown(f"- {m.BASIS_LABELS[basis]}: **{p}**. {text}")
    st.markdown(f"Probabilidade inerente padrão: **{m.DEFAULT_INHERENT_PROBABILITY}**. O risco residual só existe por "
                "reavaliação documentada; concluir ações não reduz pontuações.")
    for module in MODULES:
        st.markdown(f"**Regras de diagnóstico: {module.name}** (questionário v{module.questionnaire_version}, regras v{module.rules_version})")
        st.dataframe(pd.DataFrame([(r.code, r.title, ", ".join(r.question_codes), ", ".join(r.control_codes))
                                   for r in module.rules], columns=["Regra", "Fragilidade", "Perguntas", "Controles"]),
                     hide_index=True)


def _controls(conn, ctx):
    st.caption("Catálogo central de controles. As referências marcadas como 'a validar' ainda não foram verificadas "
               "nas fontes oficiais e não são equivalências oficiais entre frameworks. Usar um controle não garante "
               "conformidade nem elimina riscos.")
    for c in AssessmentService(conn).list_controls(ctx):
        with st.expander(f"{c['code']} - {c['name']} ({c['control_type']})"):
            st.markdown(f"**Objetivo:** {c['objective']}")
            st.markdown(f"**Descrição:** {c['description']}")
            st.markdown(f"**Fragilidades relacionadas:** {c['addresses_rules'].replace(',', ', ')}")
            st.markdown("**Ações de implementação:**")
            for line in c["implementation_actions"].splitlines():
                st.markdown(f"- {line}")
            st.markdown("**Evidências esperadas:**")
            for line in c["expected_evidence"].splitlines():
                st.markdown(f"- {line}")
            st.markdown("**Referências:**")
            for ref in c["references"]:
                st.markdown(f"- {ref['framework']} {ref['ref_code']} - {ref['ref_title']} :orange[({ref['validation_status']})]")
                st.caption(f"Fonte: {ref['source_consulted']}")


def _audit(conn, ctx):
    events = AuditService(conn).list_events(ctx)
    table([{"Quando": e["created_at"], "Usuário": e["user_email"] or "-", "Ação": e["action"],
            "Entidade": e["entity_type"], "ID": e["entity_id"] or "", "Detalhe": e["detail"]} for e in events])
    st.caption("Os registros não armazenam senhas, tokens nem o conteúdo das respostas.")


def _security(conn, ctx):
    st.markdown("**Medidas implementadas**\n"
                "- Senhas protegidas com hash scrypt; sessões no servidor (somente o hash do token é guardado), com expiração por inatividade e por tempo absoluto.\n"
                "- Bloqueio temporário após falhas seguidas de login; mensagem de erro única.\n"
                "- Autorização verificada nos serviços (backend) e isolamento entre organizações também por chaves estrangeiras compostas.\n"
                "- Consultas SQL parametrizadas, validação de entradas, auditoria de eventos relevantes.\n"
                "- Avaliações concluídas imutáveis (inclusive por gatilhos no banco).\n"
                "- Nenhum envio de dados a serviços externos e nenhuma varredura de rede.")
    st.markdown("**Limitações conhecidas**\n"
                "- A aplicação roda em HTTP por padrão: para uso em rede, coloque-a atrás de um proxy com HTTPS.\n"
                "- Banco SQLite sem criptografia em repouso; um escritor por vez.\n"
                "- Sem autenticação multifator e sem envio de e-mail (a recuperação de senha usa token emitido pelo administrador).\n"
                "- Sem upload de evidências: apenas referências textuais.\n"
                "- Sem revisão de segurança independente.")


def render(conn, ctx):
    page_header("Administração", "Configurações")
    show_flash()
    sections = []
    if not ctx.is_guest:  # o visitante não tem senha para alterar
        sections.append(("Minha conta", _account))
    if can(ctx, "user:manage"):
        sections.append(("Usuários", _users))
    if can(ctx, "org:manage"):
        sections.append(("Organização", _organization))
    sections += [("Metodologia", _methodology), ("Controles", _controls)]
    if can(ctx, "audit:read"):
        sections += [("Auditoria", _audit), ("Segurança", _security)]
    for tab, (_, fn) in zip(st.tabs([name for name, _ in sections]), sections):
        with tab:
            fn(conn, ctx)
