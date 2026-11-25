# Riskora: arquitetura técnica

## Camadas e dependências (um único sentido)
```
ui  →  services  →  repositories  →  SQLite
            ↓
   engines (diagnóstico, risco, recomendação)  →  modules (perguntas, regras, controles)
            ↓
         config (metodologia, configurações)
```
- `ui/` (Streamlit) não contém regra de negócio nem SQL. `services/` não importa o Streamlit.
- Todo serviço recebe um `Context` (usuário, organização, perfil, permissões) criado no servidor a partir da sessão e
  chama `require(ctx, permissão)` antes de agir. Sem contexto, a operação falha.
- Repositórios sempre recebem `organization_id` e usam SQL parametrizado. Não fazem commit nem decidem permissão.

## Fluxo de navegação
Login → Visão Geral (dashboard) · Ativos (listagem → página do ativo com abas Visão Geral, Análise, Riscos e Controles,
Tratamento, Relatórios) · Relatórios · Configurações (conta, usuários, organização, metodologia, controles, auditoria,
segurança, conforme o perfil).

Fluxo funcional: organização → ativo → avaliação (rascunho) → respostas → processamento → fragilidades → riscos →
controles → ações → validação/reavaliação (residual) → dashboard e relatórios.

## Modelo de dados (resumo)
- Acesso: `organizations`, `users`, `roles`, `permissions`, `role_permissions`, `organization_members`, `sessions`,
  `password_reset_tokens`, `audit_logs`.
- Ativos: `asset_categories`, `assets`.
- Avaliação: `assessment_templates`, `questions`, `assessments`, `answers`, `diagnostic_rules`.
- Resultados: `findings`, `risks`, `risk_assessments` (inerente, atual, residual; nunca sobrescritos).
- Catálogo: `controls`, `control_references`, `risk_control_mappings`.
- Tratamento: `treatment_actions` (com validação), `treatment_action_events`, `evidence_records`.
- Isolamento: tabelas de dados têm `organization_id` e chaves estrangeiras compostas `(id, organization_id)`, de modo que
  o banco recusa vínculos entre organizações. Avaliações concluídas são protegidas por gatilhos.
- Migrações: `database/migrations/NNN_nome.sql`, aplicadas uma única vez cada, em transação (`schema_migrations`).

## Regras de negócio e metodologia
Risco = probabilidade × impacto (1 a 25). Impacto consolidado pelo maior valor das dimensões relevantes. Probabilidade
atual derivada de tabela explícita por base da conclusão (lacuna declarada, controle parcial, lacuna de conhecimento).
Sem dados suficientes: "Dados insuficientes". Concluir uma ação não altera pontuações: o residual só nasce de reavaliação
justificada, por perfil com permissão de validação. Parâmetros em `config/risk_methodology.py` (versionado).

## Como acrescentar uma nova categoria de ativo
1. Crie `modules/<nome>/` com `questions.py`, `rules.py`, `controls.py` e `assessment.py` (um `AssessmentModule`).
2. Registre-o em `modules/registry.py` (`MODULES`). A categoria já existe em `models/asset.py`.
3. Escreva os testes das regras. O núcleo (serviços, banco, interface) não muda.

## Acesso de visitante (ligado por padrão; RISKORA_GUEST_ACCESS=off desliga)
`services/guest_service.py` cria (sob demanda) o usuário `visitante@riskora.local`, com senha aleatória, vinculado apenas
à organização de demonstração e ao perfil `guest` (`RISKORA_GUEST_ROLE`; nunca administrador): pode editar, mas não
gerencia usuários, organização nem auditoria. `services/privacy.py` troca nomes e e-mails de pessoas reais por um rótulo
genérico em tudo que o visitante consulta. `scripts/reset_demo.py` restaura a demonstração (arquiva e recria). A sessão nasce por
`AuthenticationService.start_session`, a mesma usada no login, então expiração, auditoria e permissões são idênticas.
