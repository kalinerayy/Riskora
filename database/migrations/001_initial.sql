-- Riskora: esquema inicial. Datas em UTC, formato ISO 8601 (AAAA-MM-DDTHH:MM:SSZ), comparáveis como texto.
-- Isolamento entre organizações: tabelas de dados têm organization_id e chaves estrangeiras COMPOSTAS
-- (id, organization_id), de modo que o próprio banco recusa vínculos entre organizações diferentes.

CREATE TABLE organizations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    slug TEXT NOT NULL UNIQUE CHECK (length(slug) BETWEEN 2 AND 60),
    business_description TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '',
    responsible TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Ativa' CHECK (status IN ('Ativa','Suspensa','Arquivada')),
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(email) BETWEEN 3 AND 254),
    full_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Ativo' CHECK (status IN ('Ativo','Inativo')),
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0,1)),
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE roles (code TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE permissions (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE role_permissions (
    role_code TEXT NOT NULL REFERENCES roles(code),
    permission_code TEXT NOT NULL REFERENCES permissions(code),
    PRIMARY KEY (role_code, permission_code)
);

CREATE TABLE organization_members (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    role_code TEXT NOT NULL REFERENCES roles(code),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (organization_id, user_id)
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,          -- somente o hash do token é guardado
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    absolute_expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0,1))
);

CREATE TABLE password_reset_tokens (
    id INTEGER PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    issued_by INTEGER NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE asset_categories (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);

CREATE TABLE assets (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    category_id INTEGER NOT NULL REFERENCES asset_categories(id),
    asset_code TEXT NOT NULL CHECK (length(asset_code) BETWEEN 1 AND 40),
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    description TEXT NOT NULL DEFAULT '',
    area TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    environment TEXT NOT NULL DEFAULT '',
    criticality TEXT NOT NULL DEFAULT 'Desconhecida' CHECK (criticality IN ('Desconhecida','Baixa','Média','Alta','Crítica')),
    information_classification TEXT NOT NULL DEFAULT 'Não informada'
        CHECK (information_classification IN ('Não informada','Pública','Interna','Confidencial','Restrita')),
    information_type TEXT NOT NULL DEFAULT '',
    availability_requirement TEXT NOT NULL DEFAULT 'Não informado',
    interruption_consequences TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Ativo' CHECK (status IN ('Ativo','Em implantação','Desativado')),
    impact_availability INTEGER CHECK (impact_availability IS NULL OR impact_availability BETWEEN 1 AND 5),
    impact_integrity INTEGER CHECK (impact_integrity IS NULL OR impact_integrity BETWEEN 1 AND 5),
    impact_confidentiality INTEGER CHECK (impact_confidentiality IS NULL OR impact_confidentiality BETWEEN 1 AND 5),
    impact_operational INTEGER CHECK (impact_operational IS NULL OR impact_operational BETWEEN 1 AND 5),
    impact_financial INTEGER CHECK (impact_financial IS NULL OR impact_financial BETWEEN 1 AND 5),
    impact_legal INTEGER CHECK (impact_legal IS NULL OR impact_legal BETWEEN 1 AND 5),
    impact_justification TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (organization_id, asset_code),
    UNIQUE (id, organization_id)
);

CREATE TABLE assessment_templates (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    category_code TEXT NOT NULL,
    questionnaire_version TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    UNIQUE (code, questionnaire_version, rules_version)
);

CREATE TABLE questions (
    id INTEGER PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES assessment_templates(id),
    code TEXT NOT NULL,
    domain_no INTEGER NOT NULL,
    domain TEXT NOT NULL,
    text TEXT NOT NULL,
    purpose TEXT NOT NULL,
    parent_code TEXT,
    parent_answers TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL,
    UNIQUE (template_id, code)
);

CREATE TABLE diagnostic_rules (
    id INTEGER PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES assessment_templates(id),
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    weakness TEXT NOT NULL,
    risk_scenario TEXT NOT NULL,
    consequences TEXT NOT NULL,
    limitations TEXT NOT NULL,
    UNIQUE (template_id, code)
);

CREATE TABLE assessments (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    asset_id INTEGER NOT NULL,
    template_id INTEGER NOT NULL REFERENCES assessment_templates(id),
    assessor_user_id INTEGER REFERENCES users(id),
    assessor_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Rascunho' CHECK (status IN ('Rascunho','Concluída')),
    methodology_version TEXT NOT NULL,
    questionnaire_version TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    parent_assessment_id INTEGER REFERENCES assessments(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    completed_at TEXT,
    UNIQUE (id, organization_id),
    FOREIGN KEY (asset_id, organization_id) REFERENCES assets(id, organization_id)
);

CREATE TABLE answers (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    assessment_id INTEGER NOT NULL,
    question_code TEXT NOT NULL,
    value TEXT NOT NULL CHECK (value IN ('sim','parcial','nao','nao_sei','nao_se_aplica')),
    justification TEXT NOT NULL DEFAULT '',
    evidence_ref TEXT NOT NULL DEFAULT '',
    answered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (assessment_id, question_code),
    FOREIGN KEY (assessment_id, organization_id) REFERENCES assessments(id, organization_id) ON DELETE CASCADE
);

CREATE TABLE findings (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    assessment_id INTEGER NOT NULL,
    rule_id INTEGER NOT NULL REFERENCES diagnostic_rules(id),
    rule_code TEXT NOT NULL,
    title TEXT NOT NULL,
    basis TEXT NOT NULL CHECK (basis IN ('declared_gap','partial','knowledge_gap')),
    evidence_status TEXT NOT NULL CHECK (evidence_status IN ('referenciada','apenas_declarada','lacuna_de_conhecimento')),
    triggered_by TEXT NOT NULL,
    weakness TEXT NOT NULL,
    evidence_description TEXT NOT NULL,
    limitations TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (assessment_id, rule_code),
    UNIQUE (id, organization_id),
    FOREIGN KEY (assessment_id, organization_id) REFERENCES assessments(id, organization_id)
);

CREATE TABLE risks (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    assessment_id INTEGER NOT NULL,
    finding_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    scenario TEXT NOT NULL,
    consequences TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (id, organization_id),
    FOREIGN KEY (assessment_id, organization_id) REFERENCES assessments(id, organization_id),
    FOREIGN KEY (finding_id, organization_id) REFERENCES findings(id, organization_id)
);

CREATE TABLE risk_assessments (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    risk_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('inherent','current','residual')),
    probability INTEGER CHECK (probability IS NULL OR probability BETWEEN 1 AND 5),
    impact INTEGER CHECK (impact IS NULL OR impact BETWEEN 1 AND 5),
    score INTEGER CHECK (score IS NULL OR score BETWEEN 1 AND 25),
    level TEXT NOT NULL,
    status TEXT NOT NULL,
    probability_justification TEXT NOT NULL DEFAULT '',
    impact_justification TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    methodology_version TEXT NOT NULL,
    assessed_by INTEGER REFERENCES users(id),
    assessed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    FOREIGN KEY (risk_id, organization_id) REFERENCES risks(id, organization_id)
);

CREATE TABLE controls (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    objective TEXT NOT NULL,
    description TEXT NOT NULL,
    control_type TEXT NOT NULL CHECK (control_type IN ('preventivo','detectivo','corretivo')),
    addresses_rules TEXT NOT NULL DEFAULT '',
    implementation_actions TEXT NOT NULL DEFAULT '',
    expected_evidence TEXT NOT NULL DEFAULT ''
);

CREATE TABLE control_references (
    id INTEGER PRIMARY KEY,
    control_id INTEGER NOT NULL REFERENCES controls(id),
    framework TEXT NOT NULL,
    ref_code TEXT NOT NULL,
    ref_title TEXT NOT NULL,
    source_consulted TEXT NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'Referência a validar'
        CHECK (validation_status IN ('Referência a validar','Validada')),
    UNIQUE (control_id, framework, ref_code)
);

CREATE TABLE risk_control_mappings (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    risk_id INTEGER NOT NULL,
    control_id INTEGER NOT NULL REFERENCES controls(id),
    UNIQUE (risk_id, control_id),
    FOREIGN KEY (risk_id, organization_id) REFERENCES risks(id, organization_id)
);

CREATE TABLE treatment_actions (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    risk_id INTEGER NOT NULL,
    control_id INTEGER REFERENCES controls(id),
    action TEXT NOT NULL CHECK (length(action) BETWEEN 1 AND 2000),
    owner TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'Média' CHECK (priority IN ('Baixa','Média','Alta','Urgente')),
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'Não iniciado'
        CHECK (status IN ('Não iniciado','Em andamento','Bloqueado','Concluído','Cancelado')),
    expected_evidence TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    completed_at TEXT,
    validated_by INTEGER REFERENCES users(id),
    validated_at TEXT,
    validation_notes TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    CHECK (validated_at IS NULL OR status = 'Concluído'),
    UNIQUE (id, organization_id),
    FOREIGN KEY (risk_id, organization_id) REFERENCES risks(id, organization_id)
);

CREATE TABLE treatment_action_events (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    action_id INTEGER NOT NULL,
    user_id INTEGER REFERENCES users(id),
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    FOREIGN KEY (action_id, organization_id) REFERENCES treatment_actions(id, organization_id)
);

CREATE TABLE evidence_records (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    assessment_id INTEGER,
    question_code TEXT,
    action_id INTEGER,
    description TEXT NOT NULL DEFAULT '',
    reference TEXT NOT NULL CHECK (length(reference) BETWEEN 1 AND 500),
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    CHECK (assessment_id IS NOT NULL OR action_id IS NOT NULL),
    FOREIGN KEY (assessment_id, organization_id) REFERENCES assessments(id, organization_id),
    FOREIGN KEY (action_id, organization_id) REFERENCES treatment_actions(id, organization_id)
);
CREATE UNIQUE INDEX ux_evidence_answer ON evidence_records(assessment_id, question_code) WHERE question_code IS NOT NULL;

CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id),
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id INTEGER,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Avaliação concluída é imutável: o banco recusa alterar suas respostas.
CREATE TRIGGER trg_answers_locked_insert BEFORE INSERT ON answers
WHEN (SELECT status FROM assessments WHERE id = NEW.assessment_id) = 'Concluída'
BEGIN SELECT RAISE(ABORT, 'Avaliação concluída é imutável'); END;
CREATE TRIGGER trg_answers_locked_update BEFORE UPDATE ON answers
WHEN (SELECT status FROM assessments WHERE id = OLD.assessment_id) = 'Concluída'
BEGIN SELECT RAISE(ABORT, 'Avaliação concluída é imutável'); END;
CREATE TRIGGER trg_answers_locked_delete BEFORE DELETE ON answers
WHEN (SELECT status FROM assessments WHERE id = OLD.assessment_id) = 'Concluída'
BEGIN SELECT RAISE(ABORT, 'Avaliação concluída é imutável'); END;

CREATE INDEX idx_assets_org ON assets(organization_id, status);
CREATE INDEX idx_assessments_asset ON assessments(asset_id, status);
CREATE INDEX idx_findings_assessment ON findings(assessment_id);
CREATE INDEX idx_risks_assessment ON risks(assessment_id);
CREATE INDEX idx_ra_risk ON risk_assessments(risk_id, kind);
CREATE INDEX idx_actions_risk ON treatment_actions(risk_id);
CREATE INDEX idx_audit_org ON audit_logs(organization_id, created_at);
CREATE INDEX idx_sessions_user ON sessions(user_id);
